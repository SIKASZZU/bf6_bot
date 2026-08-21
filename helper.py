import json
import aiohttp
import time
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import datetime

from globals import *
from ranks import getRankNameFromCareerRank, get_role_dict

def load_data() -> dict:
    conn = get_conn()
    rows = conn.execute(f'SELECT key, value FROM {DB_DATA_FILE}').fetchall()
    conn.close()
    return {key: json.loads(value) for key, value in rows}

def save_data(data: dict):
    if not isinstance(data, dict):
        print('Returning! No data provided for save_data.')
        return

    conn = get_conn()
    for key, value in data.items():
        conn.execute(
            f'INSERT OR REPLACE INTO {DB_DATA_FILE} (key, value) VALUES (?, ?)',
            (key, json.dumps(value))
        )
    conn.commit()
    conn.close()

def _get_tree_commands():
    tree_commands = getattr(bot.tree, 'get_commands', None)
    if callable(tree_commands):
        try:
            return list(tree_commands())
        except TypeError:
            return []
    return list(getattr(bot.tree, 'commands', []))

def check_guild_requirements(guild: discord.Guild) -> dict:
    """Checks everything the bot needs to run an update in this guild.

    Returns {"ok": bool, "issues": [str, ...]} - issues is empty when ok is True.
    Call this before _run_guild_update so a whole run fails fast with a clear
    reason instead of dying partway through with a raw Discord exception.
    """
    issues = []

    # 1. Base permission - can the bot manage roles here at all?
    if not guild.me.guild_permissions.manage_roles:
        issues.append("Bot is missing the 'Manage Roles' permission in this server.")

    # 2. Hierarchy - bot's top role must sit above every rank role it assigns/removes.
    #    Checked per-role rather than just "highest rank role" so you get the exact
    #    offending role name instead of a vague pass/fail.
    bot_top_position = guild.me.top_role.position
    for rank_name in get_role_dict().keys():
        role = discord.utils.get(guild.roles, name=rank_name)
        if role is None:
            issues.append(f"Rank role '{rank_name}' doesn't exist in this server yet (run role setup).")
            continue
        if role.position >= bot_top_position:
            issues.append(f"Bot's role is positioned below '{rank_name}' - move the bot's role higher.")

    # 3. Report channel - configured and still resolvable (not deleted).
    channel_id = load_config().get(str(guild.id), {}).get('channel_id')
    if not channel_id:
        issues.append("No report channel configured - run /set-channel.")
    elif not bot.get_channel(channel_id):
        issues.append(f"Configured report channel ({channel_id}) no longer exists or bot can't see it.")

    return {"ok": not issues, "issues": issues}

def _build_commands_message():
    embed = discord.Embed(
        title="📋 All commands",
        color=discord.Color.blue()
    )

    command_fields = []

    seen_names = set()
    all_commands = list(bot.commands) + list(_get_tree_commands())
    for cmd in sorted(all_commands, key=lambda c: c.name):
        if getattr(cmd, 'hidden', False):
            continue

        name = getattr(cmd, 'name', None)
        if not name or name in seen_names:
            continue
        seen_names.add(name)


        prefix = COMMAND_PREFIX if isinstance(cmd, commands.Command) else '/'

        help_text = getattr(cmd, 'help', None) or getattr(cmd, 'description', None) or "No description."
        field_value = f"`{prefix}{name}` — {help_text}"

        command_fields.append(field_value)

    if command_fields:
        embed.add_field(name="", value="\n".join(command_fields), inline=False)

    return embed

def _build_linked_message(guild: discord.Guild, data: dict) -> discord.Embed:
    server_data = data.get(str(guild.id))

    embed = discord.Embed(
        title="📊 Linked accounts",
        color=discord.Color.blue()
    )

    if not server_data:
        embed.description = "No linked accounts found for this server in the database."
        return embed

    lines = []

    for discord_id, entry in server_data.items():
        lines.append(
            f"{guild.get_member(int(discord_id)).display_name if guild.get_member(int(discord_id)) else f"<left server> ({discord_id})"}: {entry.get('name', 'unknown')} ({entry.get('platform', DEFAULT_PLATFORM)})"
            )

    embed.description = "\n".join(lines)
    return embed

def _build_unlinked_message(guild: discord.Guild, data: dict) -> discord.Embed:
    server_data = data.get(str(guild.id))

    embed = discord.Embed(
        title="👥 Unlinked members",
        color=discord.Color.orange()
    )

    lines = []

    for member in guild.members:
        if member.bot:
            continue
        if str(member.id) not in server_data.keys():
            lines.append(f"{member}")

    if not lines:
        embed.description = "All members are linked!"
    else:
        embed.description = "\n".join(lines)
    return embed

# TODO: siin on bug, kui on interval 1 h siis failib displaymast
def _get_time_to_next_update(guild: discord.Guild):
    try:
        loop = running_loops.get(guild.id)
        if loop and loop.next_iteration:
            now = datetime.datetime.now(datetime.timezone.utc)
            time_left = loop.next_iteration - now

            total_seconds = int(time_left.total_seconds())
            if total_seconds < 0:
                return "Starting soon..."

            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours}h {minutes}m {seconds}s"

    except Exception as e:
        print(f"Error calculating next update time: {e}")
        return "❌ Needs /set-channel"

def _build_no_channel_warning_embed() -> discord.Embed:
    warning_embed = discord.Embed(
        title="⚠️ Report Channel Not Configured",
        description="No report channel has been set for this server!",
        color=discord.Color.red()
    )
    warning_embed.add_field(
        name="How to fix:",
        value=f"1. Go to your desired report channel\n2. Run: `{COMMAND_PREFIX}set-channel`",
        inline=False
    )
    return warning_embed

async def _warn_user_if_no_channel(interaction: discord.Interaction):
    """DMs the invoking user
    if this guild has no report channel configured yet. Called from send_interaction_message
    so it fires after every slash command without needing to touch each command."""
    if not interaction.guild:
        return

    if load_config().get(str(interaction.guild.id), {}).get('channel_id'):
        return

    try:
        # await interaction.user.send(embed=_build_no_channel_warning_embed())
        await interaction.followup.send(embed=_build_no_channel_warning_embed(), ephemeral=True)
    except Exception as e:
        log(interaction.guild, f"[WARNING] Failed to DM {interaction.user.display_name} about missing channel config: {e}")

async def send_interaction_message(interaction: discord.Interaction, content: str, *, ephemeral: bool = False, **kwargs):
    """Send a slash-command response safely, even after defer() or a prior response."""
    if isinstance(content, discord.Embed):
        kwargs['embed'] = content
        content = None

    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=ephemeral, **kwargs)
    else:
        await interaction.response.send_message(content, ephemeral=ephemeral, **kwargs)

    await _warn_user_if_no_channel(interaction)

def get_player_entry(data: dict, guild_id: int, discord_id: int):
    """
    Returns {"name": ..., "platform": ...} for a linked discord id, or None.
    Old entries were plain strings (just the EA name) - normalize those to
    the new dict shape so both formats keep working.
    """
    entry = data.get(str(guild_id)).get(str(discord_id))
    if entry is None:
        return None
    if isinstance(entry, str):
        return {"name": entry, "platform": DEFAULT_PLATFORM}
    return entry

_last_command_time = 0
REQUEST_INTERVAL_SECONDS = 2

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Catches errors from slash commands (on_command_error above only fires for prefix commands)."""

    if isinstance(error, app_commands.CheckFailure):
        await send_interaction_message(interaction, f"❌ You don't have permission to use this command. Requires **Administrator** or the `/show-authorised-role` role.", ephemeral=True)
        return

    log(interaction.guild, f"Unhandled error in command '{interaction.command.name if interaction.command else '?'}': {error}")
    await send_interaction_message(interaction, f"❌ An unexpected error occurred: {error}", ephemeral=True)

def is_admin_or_has_role():
    """Passes if the invoking user is a server administrator OR has the management role."""
    def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True

        if role_id := load_config().get(str(interaction.guild.id), {}).get('permissioned_role_id'):
            return discord.utils.get(interaction.user.roles, id=role_id) is not None

    return app_commands.check(predicate)
async def global_rate_limit(interaction: discord.Interaction):
    global _last_command_time
    now = time.monotonic() # lol wtf

    if now - _last_command_time < REQUEST_INTERVAL_SECONDS:
        # silently blocks the command from running
        return False

    _last_command_time = now
    return True

bot.tree.interaction_check = global_rate_limit

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}!")

    for guild in bot.guilds:
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        log(guild, f"Synced {len(synced)} commands to {guild.name} ({guild.id})")

        start_guild_update_loop(guild)

    # if not update_all_players.is_running():
    #     update_all_players.start()

@bot.event
async def on_command_error(ctx, error):
    """
    Catches errors from any command and prints a helpful usage message
    to the channel instead of letting the traceback go unseen in the console.
    """

    if isinstance(error, (commands.MissingPermissions, commands.MissingRole, commands.MissingAnyRole)):
        await ctx.send(f"❌ You don't have permission to use this command. Try again in {error.retry_after:.1f}s")
        return

    # arva ara kuidas muuta retry_after v22rtus
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Slow down! Try again in {error.retry_after:.1f}s.")
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            f"❌ Missing argument: `{error.param.name}`\n"
            f"Usage: `!{ctx.command.qualified_name} {ctx.command.signature}`"
        )
        return

    if isinstance(error, commands.BadArgument):
        await ctx.send(
            f"❌ Couldn't understand one of the arguments you gave.\n"
            f"Usage: `!{ctx.command.qualified_name} {ctx.command.signature}`"
        )
        return

    if isinstance(error, commands.CheckFailure):
        await ctx.send("⏳ Bot is busy, try again in a moment.")
        return

    log(ctx.guild, f"Unhandled error in command '{ctx.command}': {error}")
    await ctx.send(f"❌ An unexpected error occurred: {error}")

@bot.event
async def on_guild_join(guild):
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)

    config = load_config()
    server_key = str(guild.id)

    msg = f'[JOINED] bot into {guild.name} id: {guild.id}\n'

    if server_key not in config:
        config[server_key] = {
            "channel_id": guild._system_channel_id,
            "update_interval": AUTO_UPDATE_TIMER_HOURS
        }
        save_config(config)
        msg += f"Initialized default config configuration for server.\n"

    data = load_data()
    if server_key not in data:
        data[server_key] = {}
        save_data(data)
        msg += f"Initialized default data configuration for server."

    log(guild, msg)
    start_guild_update_loop(guild)

@bot.event
async def on_guild_remove(guild):
    config = load_config()
    server_key = str(guild.id)

    msg = f'[REMOVED] bot from {guild.name} id: {guild.id}\n'

    if server_key in config:
        delete_config_key(server_key)
        msg += f"Removed configuration for server.\n"

    data = load_data()
    if server_key in data:
        delete_data_key(server_key)
        msg += f"Removed saved data for server."

    log(guild, msg)

    existing = running_loops.pop(guild.id, None)
    if existing:
        existing.cancel()

@bot.event
async def on_member_remove(member: discord.Member):
    data = load_data()

    if str(member.guild.id) in data and str(member.id) in data[str(member.guild.id)]:
        del data[str(member.guild.id)][str(member.id)]
        save_data(data)
        log(member.guild, f"[LEFT] {member.display_name} ({str(member.id)}) left the guild - removed their link from data.")

async def fetch_player_stats(guild: discord.Guild, session: aiohttp.ClientSession, name: str, platform: str):
    """Hits the bf6 profile endpoint for a single player and returns the parsed JSON, or None.
    Retries transient failures up to API_MAX_RETRIES times. "Player not found" is treated as
    permanent (bad name/platform) and fails immediately without retrying."""

    last_error = None
    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
            API_URL = build_api_url(name, platform)
            async with session.get(API_URL) as response:
                if response.status != 200:
                    raise Exception(f'{response.status}')

                stats = await response.json()

                if isinstance(stats, dict) and "errors" in stats:
                    errors = stats["errors"]
                    if any("not found" in str(e).lower() for e in errors):
                        log(guild, f"❌ ({name}, {platform}) not found on gametools - check the linked name/platform.")
                        return None

                    raise Exception(f"{errors}")
                return stats

        except Exception as e:
            last_error = e
            if attempt < API_MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
            continue

    log(guild, f"ERROR! [Attempt {attempt}/{API_MAX_RETRIES}] ({name}, {platform}): {last_error}")
    return None

def get_level_and_rank(stats: dict):
    """
    Extracts rank/rankName from the bf6 profile response.

    The actual shape is:
    {
      "playerProfiles": [
        {
          "playerCard": {"rank": 254, ...},
          "rankName": "Major",
          ...
        }
      ]
    }
    So rank lives under playerProfiles[0]["playerCard"]["rank"], and
    rankName is on playerProfiles[0] directly - neither is top-level.
    """
    profiles = stats.get("playerProfiles") or []
    if not profiles:
        return None, None

    profile = profiles[0]
    rank = (profile.get("playerCard") or {}).get("rank")
    rank_name = profile.get("rankName")

    return rank, rank_name

async def get_role(guild: discord.Guild, rank_name: str):
    """Finds a role matching rank_name."""
    if not rank_name:
        log(guild, f"Failed to find rank_name: {rank_name}")
        return None

    if hasattr(rank_name, "name") and not isinstance(rank_name, str):
        return rank_name

    if isinstance(rank_name, int):
        return guild.get_role(rank_name)

    if isinstance(rank_name, str):
        role = discord.utils.get(guild.roles, name=rank_name)
    else:
        role = None

    if role is None:
        log(guild, 'Missing role!')
        # if channel:
        #     await channel.send(f"❌ Couldn't find a role based off rank name: {rank_name}. Search from !commands for role setup command.")
    return role

async def remove_rank_role(guild: discord.Guild, member: discord.Member, current_rank_name: str) -> dict:
    """Removes all obsolete rank roles from a member, keeping only their current rank role."""
    all_rank_names = get_role_dict().keys()

    # Identify obsolete roles the member currently holds
    roles_to_remove = [
        role for role in member.roles
        if role.name in all_rank_names and role.name != current_rank_name
    ]

    if not roles_to_remove:
        log(guild, msg := f"No obsolete rank roles to remove.")
        return {"success": True, "value": msg}

    try:
        await member.remove_roles(*roles_to_remove, reason="Rank sync - removing obsolete roles")
        removed_names = ", ".join(role.name for role in roles_to_remove)
        log(guild, msg := f"Removed roles: {removed_names}.")
        return {"success": True, "value": msg}

    except Exception as e:
        log(guild, return_msg := f"Remove rank error: {e}")
        return {"success": False, "value": return_msg}

async def assign_rank_role(guild: discord.Guild, member: discord.Member, rank_name: str) -> dict:
    """Ensures the role for rank_name exists, then gives it to member, removing other rank roles."""
    if not rank_name:
        log(guild, return_msg := 'Returning! rank_name is None.')
        return {"success": False, "value": return_msg}

    if not (role := await get_role(guild, rank_name)):
        log(guild, return_msg := 'Returning! Role is None.')
        return {"success": False, "value": return_msg}

    if role.position >= guild.me.top_role.position:
        log(guild, return_msg := f"Bot's role is too low to assign '{rank_name}' - move the bot's role higher.")
        return {"success": False, "value": return_msg}

    try:
        if role not in member.roles:
            await member.add_roles(role, reason="Rank sync - assign role")
            log(guild, return_msg := f"Assigned rank: {rank_name}.")
        else:
            log(guild, return_msg := f"Already has rank: {rank_name}.")

        return {"success": True, "value": return_msg}

    except Exception as e:
        log(guild, return_msg := f"Assign role error: {e}")
        return {"success": False, "value": return_msg}

async def _update_member(guild: discord.Guild, member: discord.Member, session: aiohttp.ClientSession):
    """
    Updates a single member's Discord rank roles based on their linked external game stats.

    Steps:
    1. Validates member eligibility (skips bots and unlinked accounts).
    2. Fetches external player stats and resolves their career rank name.
    3. Assigns the new rank role and strips obsolete rank roles in the guild.

    Returns:
        dict: A status map containing {'success': bool} along with 'value' (details),
              plus role update results on success.
    """
    await bot.wait_until_ready()

    return_msg = {'success': True}

    if member.bot:
        log(guild, fail_msg := f"❌ Trying to update a bot. What the helly.")
        return return_msg | {'success': False, 'value': fail_msg}

    if not (entry := get_player_entry(load_data(), guild.id, member.id)):
        log(guild, fail_msg := f"❌ discord: {member.display_name}. Not linked. Skipping.")
        return return_msg | {'success': False, 'value': fail_msg}

    name = entry["name"]
    platform = entry.get("platform", DEFAULT_PLATFORM)

    if not (stats := await fetch_player_stats(guild, session, name, platform)):
        log(guild, fail_msg := f"⚠️ Data fetch failed for discord: `{member.display_name}`. If link for member is correct, do not stress. API failure.")
        return return_msg | {'success': False, 'value': fail_msg}

    rankValue, _ = get_level_and_rank(stats)
    if rankValue is None:
        log(guild, fail_msg := f"[WARNING] Could not extract rank for discord: {member.display_name}, link: {name}, {platform}.")
        return return_msg | {'success': False, 'value': fail_msg}

    concise_rank_name = getRankNameFromCareerRank(rankValue)
    log(guild, success_msg := f"✅ discord: {member.display_name} (ea_name: {name}, platform: {platform}, level: {rankValue}, rank name: {concise_rank_name})")

    return_msg['assign_rank_role'] = await assign_rank_role(guild, member, concise_rank_name)
    if not return_msg['assign_rank_role']['success']:
        return return_msg | {'success': False, 'value': return_msg['assign_rank_role']['value'] }

    return_msg['remove_rank_role'] = await remove_rank_role(guild, member, concise_rank_name)
    if not return_msg['remove_rank_role']['success']:
        return return_msg | {'success': False, 'value': return_msg['remove_rank_role']['value'] }

    return return_msg | {'value': success_msg}

async def _run_guild_update(guild: discord.Guild, on_progress=None) -> dict:
    """Runs one full update pass over every member of a guild, assigning/removing rank roles.
    Resolves the guild's configured report channel itself, so callers just pass a guild.

    on_progress, if given, is an async callable(updated_count, total_linked) invoked after
    each successful member update - used for live progress reporting (e.g. editing a message).
    """
    check = check_guild_requirements(guild)
    if not check["ok"]:
        fail_msg = "[ERROR STARTING AUTOMATIC UPDATE]: " + " | ".join(check["issues"])
        log(guild, fail_msg)
        return {'success': False, 'value': fail_msg}

    log(guild, f"[START AUTOMATIC UPDATE]")

    failed_to_update: list = []
    success_to_update: list = []
    linked_member_ids = list(load_data().get(str(guild.id)).keys())
    async with aiohttp.ClientSession() as session:
        for idx, member_id in enumerate(linked_member_ids):
            member = guild.get_member(int(member_id))

            try:
                return_value: dict = await _update_member(guild, member, session)
                updated: bool = return_value['success']

                if on_progress:
                    await on_progress(len(success_to_update), len(linked_member_ids), idx == (len(linked_member_ids) - 1))

                if not updated:
                    raise Exception(return_value['value'])

                success_to_update.append(member.display_name)

            except Exception as e:
                failed_to_update.append(member.display_name)
                log(guild, f"❌ [ERROR] Automatic update failed for: {member.display_name}, error: {e}")

    log(guild,
        f"[FINISHED AUTOMATIC UPDATE] Updated {len(success_to_update)} member{'' if len(success_to_update) == 1 else 's'}.\
        Failed with {len(failed_to_update)}member{'' if len(failed_to_update) == 1 else 's'}"
    )

    if failed_to_update:
        return {'success': False, 'value': ', '.join(failed_to_update)}

    return {'success': True, 'value': ', '.join(success_to_update)}

def _make_guild_update_loop(guild_id: int, interval_hours: float) -> tasks.Loop:
    if not interval_hours:
        log(bot.get_guild(guild_id), f'{interval_hours} is not valid. Returning.')
        return

    if not guild_id:
        log(bot.get_guild(guild_id), f'{guild_id} is not valid. Returning.')
        return

    @tasks.loop(hours=interval_hours)
    async def _loop():
        await bot.wait_until_ready()

        guild = bot.get_guild(guild_id)
        if guild is None:
            log(guild, f"[ERROR] Guild {guild_id} no longer accessible, stopping its update loop.")
            _loop.cancel()
            return

        return_value = await _run_guild_update(guild)

        channel = bot.get_channel(load_config().get(str(guild.id), {}).get('channel_id'))
        if not channel:
            log(guild, 'Channel is not set.')
            return
        try:
            if return_value['success']:
                await channel.send(f"✅ Automatic update complete. {return_value['value']}")
            else:
                await channel.send(f"⚠️ Automatic update finished with errors: {return_value['value']}")
        except Exception as e:
            log(guild, f'Error at automatic loop: {e}')

    return _loop

def start_guild_update_loop(guild: discord.Guild):
    """Starts (or restarts) the automatic update loop for one guild, using its configured interval."""
    loop = _make_guild_update_loop(guild.id, load_config().get(str(guild.id)).get('update_interval'))
    running_loops[guild.id] = loop
    loop.start()

def restart_guild_update_loop(guild: discord.Guild):
    """Call this after update_interval changes in config, so the new interval takes effect."""
    existing = running_loops.get(guild.id)
    if existing:
        existing.cancel()
    start_guild_update_loop(guild)
