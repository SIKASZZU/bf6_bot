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

class WrongChannelError(app_commands.CheckFailure):
    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        super().__init__(f"Command must be used in <#{channel_id}>")

def _get_tree_commands():
    tree_commands = getattr(bot.tree, 'get_commands', None)
    if callable(tree_commands):
        try:
            return list(tree_commands())
        except TypeError:
            return []
    return list(getattr(bot.tree, 'commands', []))

def _get_guild_role_status(guild: discord.Guild) -> list:
    missing_roles: bool = False
    position_below: bool = False

    bot_top_position = guild.me.top_role.position
    for rank_name in get_role_dict().keys():
        role = discord.utils.get(guild.roles, name=rank_name)
        if role is None:
            missing_roles = True
            continue

        if role.position >= bot_top_position:
            position_below = True

        if missing_roles and position_below:
            # all boxes are checked
            break

    return_v: list = []
    if missing_roles:
        return_v.append(f'Missing role(s), run /create-roles.')
    if position_below:
        return_v.append(f"Bot's role is positioned below some role(s) - move the bot's role higher.")
    return return_v

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
    issues.extend(_get_guild_role_status(guild))

    # 3. Report channel - configured and still resolvable (not deleted).
    channel_id = load_config().get(str(guild.id), {}).get('channel_id')
    if not channel_id:
        issues.append("No report channel configured - run /set-channel.")
    elif not bot.get_channel(channel_id):
        issues.append(f"Configured report channel ({channel_id}) no longer exists or bot can't see it.")

    return {"ok": not issues, "issues": issues}

def _add_chunked_field(embed: discord.Embed, name: str, items: list, *, max_len: int = 1024, suffix: str = ''):
    """Adds `items` (joined with ', ') to embed as one or more fields, splitting
    across multiple fields so no single field value exceeds Discord's 1024-char
    limit. `suffix` (e.g. a note appended after the last chunk) is appended to
    the final chunk only, and still respects the limit."""
    if not items:
        return

    chunks = []
    current = ''
    for item in items:
        piece = item if not current else f', {item}'
        if len(current) + len(piece) > max_len:
            chunks.append(current)
            current = item
        else:
            current += piece
    if current:
        chunks.append(current)

    if suffix:
        if len(chunks[-1]) + len(suffix) <= max_len:
            chunks[-1] += suffix
        else:
            chunks.append(suffix.lstrip('\n'))

    for i, chunk in enumerate(chunks):
        field_name = name if i == 0 else f'\u200b'
        embed.add_field(name=field_name, value=chunk, inline=False)

def _build_commands_message():
    embed = discord.Embed(
        title="📋 All commands",
        color=discord.Color.blue()
    )

    exempt_fields = []
    restricted_fields = []

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

        # if name in CHANNEL_CHECK_EXEMPT:
        #     exempt_fields.append(field_value)
        # else:
        restricted_fields.append(field_value)

    # if exempt_fields:
    #     embed.add_field(name="Available in every channel", value="\n".join(exempt_fields), inline=False)

    if restricted_fields:
        #Available in only set channel
        embed.add_field(name="", value="\n".join(restricted_fields), inline=False)

    return embed

def _build_linked_message(guild: discord.Guild, data: dict, member: discord.Member = None) -> discord.Embed:
    server_data = data.get(str(guild.id))

    resolved = guild.get_member(int(member.id)) if member else None
    member_name = resolved.name if resolved else (f"<left server> ({member.id})" if member else None)

    embed = discord.Embed(
        title="📊 Linked accounts" if not member else f"{member_name}'s linked account",
        color=discord.Color.blue()
    )

    lines = []

    for discord_id, entry in server_data.items():
        if member and discord_id == str(member.id):
            lines.append(
                f"{entry.get('name', 'unknown')}, level {entry.get('career_rank', 'Missing level')}, {entry.get('rank_name', 'Missing rank')}"
            )
            break

        elif not member:
            lines.append(
                f"{guild.get_member(int(discord_id)).mention if guild.get_member(int(discord_id)) else f"<left server> ({discord_id})"}: {entry.get('name', 'unknown')}, level {entry.get('career_rank', 'Missing level')}, {entry.get('rank_name', 'Missing rank')}"
            )

    if not server_data or not lines:
        embed.description = "No linked accounts found for this server in the database." if not member else f"No link"
        return embed

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
    if isinstance(error, WrongChannelError):
        await send_interaction_message(interaction, f"❌ This command can only be used in <#{error.channel_id}>.", ephemeral=True)
        return

    if isinstance(error, app_commands.CheckFailure):
        await send_interaction_message(interaction, f"❌ You don't have permission to use this command. Requires **Administrator** or the `/show-authorised-role` role.", ephemeral=True)
        return

    log(interaction.guild, f"Unhandled error in command '{interaction.command.name if interaction.command else '?'}': {error}")
    await send_interaction_message(interaction, f"❌ An unexpected error occurred: {error}", ephemeral=True)

async def global_interaction_check(interaction: discord.Interaction) -> bool:
    # 1. DM Guard
    if not interaction.guild:
        return True

    # 2. Rate-limiter / Cooldown check
    global _last_command_time
    now = time.monotonic()
    if now - _last_command_time < REQUEST_INTERVAL_SECONDS:
        raise app_commands.CheckFailure(f"{REQUEST_INTERVAL_SECONDS} cooldown after every command!")
    _last_command_time = now

    # Load full configuration safely
    full_config = load_config()
    guild_id_str = str(interaction.guild.id)
    guild_config = full_config.get(guild_id_str, {})

    # 3. Admin-or-role check
    if not interaction.user.guild_permissions.administrator:
        role_id = guild_config.get('permissioned_role_id')
        if not (role_id and discord.utils.get(interaction.user.roles, id=role_id)):
            role = interaction.guild.get_role(role_id) if role_id else None
            role_str = role.mention if role else "a required role"
            raise app_commands.CheckFailure(f"Missing {role_str} or Administrator permissions.")

    # 4. Report-channel restriction
    if (channel_id := guild_config.get('channel_id')):
        if interaction.guild.get_channel(channel_id) is None:
            # Channel deleted - reset setting safely across full config
            guild_config['channel_id'] = None
            full_config[guild_id_str] = guild_config
            save_config(full_config)
            return True

        if interaction.channel.id != channel_id:
            raise WrongChannelError(channel_id)

    return True

bot.tree.interaction_check = global_interaction_check

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
async def on_guild_join(guild):
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)

    config = load_config()
    server_key = str(guild.id)

    msg = f'[JOINED] bot into {guild.name} id: {guild.id}\n'

    if server_key not in config:
        config[server_key] = {
            "channel_id": None,
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
        log(member.guild, f"[LEFT] {member.mention} ({str(member.id)}) left the guild - removed their link from data.")

async def fetch_player_stats(guild: discord.Guild, session: aiohttp.ClientSession, name: str):
    """Hits the bf6 profile endpoint for a single player and returns the parsed JSON, or None.
    Retries transient failures up to API_MAX_RETRIES times. "Player not found" is treated as
    permanent (bad name/platform) and fails immediately without retrying."""

    last_error = None
    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
            API_URL = build_api_url(name)
            async with session.get(API_URL) as response:
                if response.status != 200:
                    raise Exception(f'{response}')

                stats = await response.json()

                if isinstance(stats, dict) and "errors" in stats:
                    raise Exception(f"{stats['errors']}")

                return stats

        except Exception as e:
            last_error = e
            if attempt <= API_MAX_RETRIES:
                # max time is 126sec with 6 attempts. S = 2(2**6-1)/(2-1)
                await asyncio.sleep(2 ** attempt)
            continue

    log(guild, f"ERROR! [Attempt {attempt}/{API_MAX_RETRIES}] {name}: {last_error}")
    return None

def get_rank_value_from_data(stats: dict) -> int:
    """
    Extracts rank from the bf6 profile response.

    Public profile:
    {
      "playerProfiles": [
        {
          "playerCard": {"rank": 254, ...},
          "rankName": "Major",
          ...
        }
      ]
    }
    Private profile:
    {
    "other": [
        {
        "playerProfiles": [
            {
            "rank": 134,
            "badges": 81,
            "rankName": "Second Lieutenant IV",
            ...
            }
        ]
        }
    ]
    }
    """

    if not isinstance(stats, dict):
        return None

    profiles = stats.get("playerProfiles")
    if not profiles and isinstance(stats.get("other"), list) and stats["other"]:
        profiles = stats["other"][0].get("playerProfiles")

    if not isinstance(profiles, list) or not profiles:
        return None

    profile = profiles[0]

    player_card = profile.get("playerCard")
    if isinstance(player_card, dict) and "rank" in player_card:
        return player_card.get("rank")

    if "rank" in profile:
        return profile.get("rank")

    return None

async def remove_rank_role(guild: discord.Guild, member: discord.Member, current_rank_name: str) -> dict:
    """
    Removes all obsolete rank roles from a member, keeping only their current rank role.

    return_value = {
        "success": bool,
        "value": string
        "rank_removed": string|None
    }
    """
    all_rank_names = get_role_dict().keys()

    # Identify obsolete roles the member currently holds
    roles_to_remove = [
        role for role in member.roles
        if role.name in all_rank_names and role.name != current_rank_name
    ]

    if not roles_to_remove:
        # log(guild, msg := f"No obsolete rank roles to remove.")
        return {"success": True, "value": f"No obsolete rank roles to remove.", "rank_removed": None}

    try:
        await member.remove_roles(*roles_to_remove, reason="Rank sync - removing obsolete roles")
        removed_names = ", ".join(role.mention for role in roles_to_remove)
        # log(guild, msg := f"Removed roles: {removed_names}.")
        return {"success": True, "value": f"Removed roles: {removed_names}.", "rank_removed": removed_names}

    except Exception as e:
        # log(guild, return_msg := f"Remove rank error: {e}")
        return {"success": False, "value": f"Remove rank error: {e}"}

async def assign_rank_role(guild: discord.Guild, member: discord.Member, rank_name: str) -> dict:
    """
    Ensures the role for rank_name exists, then gives it to member, removing other rank roles.

    return_value = {
        "success": bool,
        "value": string|None
        "rank_added": string|None
    }
    """
    if not rank_name:
        log(guild, return_msg := 'Returning! rank_name is None.')
        return {"success": False, "value": return_msg}

    if not (role := discord.utils.get(guild.roles, name=rank_name)):
        log(guild, return_msg := 'Returning! Role is None.')
        return {"success": False, "value": return_msg}

    if role.position >= guild.me.top_role.position:
        log(guild, return_msg := f"Bot's role is too low to assign {role.mention} - move the bot's role higher.")
        return {"success": False, "value": return_msg}

    try:
        return_msg = None
        if role not in member.roles:
            await member.add_roles(role, reason="Rank sync - assign role")
            log(guild, return_msg := f"Assigned rank: {role.mention}.")

        return {"success": True, "value": return_msg or f'Already has rank: {role.mention}', "rank_added": rank_name if return_msg else None }

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

    return_value = {
        "success": bool,
        "value": string,
        "assign_rank_role": dict,
        "remove_rank_role": dict,
    }

    """
    await bot.wait_until_ready()

    return_msg = {'success': True}

    if member.bot:
        # log(guild, fail_msg := f"❌ Trying to update a bot. What the helly.")
        return return_msg | {'success': False, 'value': f"❌ Trying to update a bot. What the helly."}

    if not (entry := get_player_entry(load_data(), guild.id, member.id)):
        # log(guild, fail_msg := f"❌ Not linked. Skipping.")
        return return_msg | {'success': False, 'value': f"❌ Not linked. Skipping."}

    name = entry["name"]
    platform = entry.get("platform", DEFAULT_PLATFORM)

    if not (stats := await fetch_player_stats(guild, session, name)):
        # log(guild, fail_msg := f"⚠️ Data fetch failed. If link is correct, do not stress, API failure.")
        return return_msg | {'success': False, 'value': f"⚠️ Data fetch failed. If link is correct, do not stress, API failure."}

    rankValue = get_rank_value_from_data(stats)
    if rankValue is None:
        # log(guild, fail_msg := f"[WARNING] Could not extract rank.")
        return return_msg | {'success': False, 'value': f"[WARNING] Could not extract rank."}

    concise_rank_name = getRankNameFromCareerRank(rankValue)

    # lol
    data = load_data()
    data[str(guild.id)][str(member.id)].update({
        'rank_name': concise_rank_name,
        'career_rank': rankValue
    })
    save_data(data)

    return_msg['assign_rank_role'] = await assign_rank_role(guild, member, concise_rank_name)
    if not return_msg['assign_rank_role']['success']:
        # log(guild, msg := return_msg['assign_rank_role']['value'])
        return return_msg | {'success': False, 'value': f'{return_msg['assign_rank_role']['value']}'}

    return_msg['remove_rank_role'] = await remove_rank_role(guild, member, concise_rank_name)
    if not return_msg['remove_rank_role']['success']:
        # log(guild, msg := return_msg['remove_rank_role']['value'])
        return return_msg | {'success': False, 'value': f'{return_msg['remove_rank_role']['value']}'}

    # log(guild, success_msg := )
    return return_msg | {'value': f'✅ Update successful for {member.name}.'}

def _build_update_summary(return_value: dict) -> str:
    parts = [return_value['value']]

    assign = return_value.get('assign_rank_role') or {}
    if assign.get('rank_added'):
        parts.append(assign['value'])

    remove = return_value.get('remove_rank_role') or {}
    if remove.get('rank_removed'):
        parts.append(remove['value'])

    return ', '.join(parts)

def _has_rank_change(return_value: dict) -> bool:
    """True only if this member's update actually assigned or removed a rank
    role. Used to filter out no-op successes from the automatic update report."""
    assign = return_value.get('assign_rank_role') or {}
    remove = return_value.get('remove_rank_role') or {}
    return bool(assign.get('rank_added')) or bool(remove.get('rank_removed'))

async def _run_guild_update(guild: discord.Guild, on_progress=None, only_report_changes: bool = False) -> dict:
    """Runs one full update pass over every member of a guild, assigning/removing rank roles.
    Resolves the guild's configured report channel itself, so callers just pass a guild.

    on_progress, if given, is an async callable(updated_count, total_linked) invoked after
    each successful member update - used for live progress reporting (e.g. editing a message).

    only_report_changes, when True, drops successful-but-unchanged members from the returned
    summary so callers only see members whose rank role was actually assigned/removed. Failed
    updates are always included regardless of this flag. Used by the automatic loop.
    """
    check = check_guild_requirements(guild)
    if not check["ok"]:
        fail_msg = "❌ [ERROR STARTING AUTOMATIC UPDATE]: " + " | ".join(check["issues"])
        log(guild, fail_msg)
        return {'success': False, 'value': fail_msg}

    log(guild, f"[START AUTOMATIC UPDATE]")

    player_update_summary_list: list = []
    failed_player_updates_summary_list: list = []
    linked_member_ids = list(load_data().get(str(guild.id)).keys())
    async with aiohttp.ClientSession() as session:
        for idx, member_id in enumerate(linked_member_ids):
            member = guild.get_member(int(member_id))

            try:
                return_value: dict = await _update_member(guild, member, session)
                member_update_msg = _build_update_summary(return_value)

                if on_progress:
                    await on_progress(len(player_update_summary_list), len(linked_member_ids), idx == (len(linked_member_ids) - 1))

                if not return_value['success']:
                    raise Exception(f'❌ Update failed for {member.mention}: {return_value['value']}.')

                if not only_report_changes or _has_rank_change(return_value):
                    player_update_summary_list.append(f'\n{member_update_msg}')

            except Exception as e:
                log(guild, summary := f'{e}')
                player_update_summary_list.append(f'\n{summary}')
                failed_player_updates_summary_list.append(f'\n{summary}')

    log(guild, f"[FINISHED AUTOMATIC UPDATE] Updated {len(player_update_summary_list)} member{'' if len(player_update_summary_list) == 1 else 's'}.")
    return {'success': True, 'value': ', '.join(player_update_summary_list), 'failed_player_updates_summary_list': ', '.join(failed_player_updates_summary_list)}

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

        if not (channel := bot.get_channel(load_config().get(str(guild.id), {}).get('channel_id'))):
            log(guild, 'Channel is not set.')
            return _loop

        return_value = await _run_guild_update(guild, only_report_changes=True)

        if not return_value['value']:
            log(guild, 'No updated members.')
            return _loop

        try:
            # try because channel.send might raise error if channel not set or some permission missing. both cases should already be covered.
            if failed_msg := return_value.get('failed_player_updates_summary_list'):
                await channel.send(failed_msg)

            log(guild, channel_msg := f"{return_value['value']}")
            await channel.send(channel_msg)

        except Exception as e:
            log(guild, f'Error at automatic loop sending channel msg: {e}')

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
