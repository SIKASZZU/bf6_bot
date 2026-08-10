import json
import aiohttp
import time
from discord.ext import commands, tasks
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
        # TODO: figure out how to remove print?
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

def _build_commands_message():
    embed = discord.Embed(
        title="📋 All commands",
        color=discord.Color.blue()
    )

    admin_fields = []
    normal_fields = []

    seen_names = set()

    for cmd in list(bot.commands) + _get_tree_commands():
        if getattr(cmd, 'hidden', False):
            continue

        name = getattr(cmd, 'name', None)
        if not name or name in seen_names:
            continue
        seen_names.add(name)

        is_admin = any(
            getattr(check, '__qualname__', '').startswith('has_permissions')
            for check in getattr(cmd, 'checks', [])
        )

        prefix = COMMAND_PREFIX if isinstance(cmd, commands.Command) else '/'

        help_text = getattr(cmd, 'help', None) or getattr(cmd, 'description', None) or "No description."
        field_value = f"{prefix}{name} — {help_text}"

        if is_admin:
            admin_fields.append(field_value)
        else:
            normal_fields.append(field_value)

    if normal_fields:
        embed.add_field(name="User Commands", value="\n".join(normal_fields), inline=False)
    if admin_fields:
        embed.add_field(name="Administrator Commands", value="\n".join(admin_fields), inline=False)

    return embed

def _build_links_message(guild: discord.Guild, data: dict) -> discord.Embed:
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
        name = entry.get('name', 'unknown')
        platform = entry.get('platform', DEFAULT_PLATFORM)

        member = guild.get_member(int(discord_id))
        display = member.display_name if member else f"<left server> ({discord_id})"

        lines.append(f"{display}: {name} ({platform})")

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
    return "Unknown"

async def send_interaction_message(interaction: discord.Interaction, content: str, *, ephemeral: bool = False, **kwargs):
    """Send a slash-command response safely, even after defer() or a prior response."""
    if isinstance(content, discord.Embed):
        kwargs['embed'] = content
        content = None

    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=ephemeral, **kwargs)
    else:
        await interaction.response.send_message(content, ephemeral=ephemeral, **kwargs)

def get_player_entry(data: dict, guild_id: int, discord_id: int):
    """
    Returns {"name": ..., "platform": ...} for a linked discord id, or None.
    Old entries were plain strings (just the EA name) - normalize those to
    the new dict shape so both formats keep working.
    """
    entry = data.get(str(guild_id), {}).get(str(discord_id))
    if entry is None:
        return None
    if isinstance(entry, str):
        return {"name": entry, "platform": DEFAULT_PLATFORM}
    return entry

_last_command_time = 0
REQUEST_INTERVAL_SECONDS = 2

def is_admin_or_has_role(role_name: str = PERMISSIONED_ROLE):
    """Passes if the invoking user is a server administrator OR has the given role."""
    def predicate(ctx: commands.Context) -> bool:
        if ctx.author.guild_permissions.administrator:
            return True
        return discord.utils.get(ctx.author.roles, name=role_name) is not None

    return commands.check(predicate)

@bot.check
async def global_rate_limit(ctx):
    global _last_command_time
    now = time.monotonic() # lol wtf

    if now - _last_command_time < REQUEST_INTERVAL_SECONDS:
        # silently blocks the command from running
        return False

    _last_command_time = now
    return True

@bot.after_invoke
async def _check_and_send_warn_no_channel(ctx):
    """Sends a warning message when no report channel is configured."""

    if not load_config().get(str(ctx.guild.id), {}).get('channel_id'):
        warning_embed = discord.Embed(
            title="⚠️ Report Channel Not Configured",
            description=f"No report channel has been set for this server!",
            color=discord.Color.red()
        )
        warning_embed.add_field(
            name="How to fix:",
            value=f"1. Go to your desired report channel\n2. Run: `{COMMAND_PREFIX}set-channel`",
            inline=False
        )
        await ctx.send(embed=warning_embed)

@bot.event
async def on_ready():
    #TODO: fix print here maybbe
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
            "channel_id": None,
            "update_interval": 1
        }
        save_config(config)
        msg += f"Initialized default config configuration for server: {guild.name} ({server_key})\n"

    data = load_data()
    if server_key not in data:
        data[server_key] = {}
        save_data(data)
        msg += f"Initialized default data configuration for server: {guild.name} ({server_key})"

    log(guild, msg)

@bot.event
async def on_guild_remove(guild):
    config = load_config()
    server_key = str(guild.id)

    msg = f'[REMOVED] bot from {guild.name} id: {guild.id}\n'

    if server_key in config:
        delete_config_key(server_key)
        msg += f"Removed configuration for server: {guild.name} ({server_key})\n"

    data = load_data()
    if server_key in data:
        delete_data_key(server_key)
        msg += f"Removed saved data for server: {guild.name} ({server_key})"

    log(guild, msg)

    existing = running_loops.pop(guild.id, None)
    if existing:
        existing.cancel()

async def fetch_player_stats(guild: discord.Guild, session: aiohttp.ClientSession, name: str, platform: str, channel: discord.TextChannel):
    """Hits the bf6 profile endpoint for a single player and returns the parsed JSON, or None.
    Retries up to max_retries times for any failed request."""

    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
            API_URL = build_api_url(name, platform)
            async with session.get(API_URL) as response:
                if response.status != 200:
                    raise Exception(f'{response.status}')

                stats = await response.json()

                if isinstance(stats, dict) and "errors" in stats:
                    raise Exception(f"{stats['errors']}")
                return stats

        except Exception as e:
            log(guild, f"ERROR! [Attempt {attempt}/{API_MAX_RETRIES}] ({name}, {platform}): {e}")
            await asyncio.sleep(2 ** attempt)
            continue

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

async def get_role(guild: discord.Guild, rank_name: str, channel: discord.TextChannel = None):
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
        if channel:
            await channel.send(f"❌ Couldn't find a role based off rank name: {rank_name}. Search from !commands for role setup command.")
    return role

async def remove_rank_role(guild: discord.Guild, member: discord.Member, current_rank_name:str, channel: discord.TextChannel = None):
    current_role_names = {role.name for role in member.roles}
    for role_name in get_role_dict().keys():
        if role_name not in current_role_names:
            continue
        if role_name == current_rank_name:
            continue

        role_cls = await get_role(guild, role_name)
        if isinstance(role_cls, str):
            role_cls = discord.utils.get(guild.roles, name=role_cls)

        if role_cls is None or (not hasattr(role_cls, "name") and not isinstance(role_cls, str)):
            log(guild, f'Returning! role_cls is not a valid role object: {role_cls!r}')
            continue

        log(guild, f'Removing {role_name} from {member.display_name}, extra: {type(role_cls)}')

        await member.remove_roles(role_cls, reason='Rank sync - removing role')

        if channel:
            await channel.send(f"✅ Removed `{role_name}` from `{member.display_name}`")

async def assign_rank_role(guild: discord.Guild, member: discord.Member, rank_name: str, channel: discord.TextChannel = None):
    """Ensures the role for rank_name exists, then gives it to member, removing other rank roles."""
    if not rank_name:
        log(guild, 'Returning! rank_name is None.')
        return

    role = await get_role(guild, rank_name, channel)
    if role is None:
        log(guild, 'Returning! Role is None.')
        return

    if role.position >= guild.me.top_role.position:
        log(guild, f"Bot's top role is too low to assign '{rank_name}' - move the bot's role higher.")
        if channel:
            await channel.send(f"❌ Bot's top role is too low to assign '{rank_name}' - move the bot's role higher.")
        return

    try:
        if role not in member.roles:
            await member.add_roles(role, reason="Rank sync - assign role")
            log(guild, f"Assigned {rank_name} to {member.display_name}")
            if channel:
                await channel.send(f"✅ Assigned `{rank_name}` to `{member.display_name}`")
            return

    except discord.Forbidden:
        log(guild, f"Missing permissions to assign role '{rank_name}' to {member.display_name}")

    except discord.HTTPException as e:
        log(guild, f"Failed to assign role '{rank_name}' to {member.display_name}: {e}")

async def _update_member(guild: discord.Guild, member: discord.Member, session: aiohttp.ClientSession, channel: discord.TextChannel):
    """Update a single member's rank. """
    await bot.wait_until_ready()

    if member.bot: return False

    entry = get_player_entry(load_data(), guild.id, member.id)
    if not entry:
        log(guild, f"❌ discord: {member.display_name}. Not linked. Skipping.")
        return False

    name = entry["name"]
    platform = entry.get("platform", DEFAULT_PLATFORM)

    stats = await fetch_player_stats(guild, session, name, platform, channel)

    if stats is None:
        log(guild, f"❌ Data fetch failed for discord: {member.display_name}, link: {name}, {platform}. {API_MAX_RETRIES}x attempts.")
        return False

    # else:
        # log(guild, f"✅ Data fetch successful for discord: {member.display_name}, link: {name}, {platform}.")

    rankValue, _ = get_level_and_rank(stats)
    if rankValue is None:
        log(guild, f"[WARNING] Could not extract rank for discord: {member.display_name}, link: {name}, {platform}.")
        if channel:
            await channel.send(f"⚠️ Could not extract rank for discord: {member.display_name}, link: {name}, {platform}.")
        return False

    concise_rank_name = getRankNameFromCareerRank(rankValue)

    log(guild, f"✅ discord: {member.display_name} (ea_name: {name}, platform: {platform}, level: {rankValue}, rank name: {concise_rank_name})")

    await assign_rank_role(guild, member, concise_rank_name, channel)
    await remove_rank_role(guild, member, concise_rank_name, channel)

    return True

@tasks.loop(hours=AUTO_UPDATE_TIMER_HOURS)
async def update_all_players(report_channel: discord.TextChannel = None, guild: discord.Guild = None):
    await bot.wait_until_ready()

    if guild is not None:
        guilds_to_update = [guild]
    elif report_channel is not None:
        guild_context = getattr(report_channel, 'guild', None)
        guilds_to_update = [guild_context] if guild_context is not None else list(bot.guilds)
    else:
        guilds_to_update = list(bot.guilds)

    if not guilds_to_update:
        log(guild, '[ERROR] Automatic update skipped: no guilds to update.')
        return

    async with aiohttp.ClientSession() as session:
        log(guild, f"[DEBUG] guild_to_update {[getattr(guild, 'name', str(guild)) for guild in guilds_to_update]}")
        for target_guild in guilds_to_update:
            report_guild = getattr(report_channel, 'guild', None)
            channel = report_channel if (report_channel is not None and report_guild is not None and report_guild.id == target_guild.id) else None
            if channel is None and load_config().get(str(target_guild.id), {}).get('channel_id'):
                channel = bot.get_channel(int(load_config().get(str(target_guild.id), {})['channel_id']))

            log(guild, f"[START AUTOMATIC UPDATE] [{target_guild.name}] Interval: {load_config().get(str(target_guild.id), {}).get('update_interval', AUTO_UPDATE_TIMER_HOURS)} hours")

            updated_count = 0
            for member in target_guild.members:
                try:
                    if await _update_member(target_guild, member, session, channel):
                        updated_count += 1
                except Exception as e:
                    log(guild, f"[ERROR] Failed updating {member.display_name}: {e}")

            log(guild, f"[FINISHED AUTOMATIC UPDATE] [{target_guild.name}] Updated {updated_count} member{'' if updated_count == 1 else 's'}.")

running_loops: dict[int, tasks.Loop] = {}

def _make_guild_update_loop(guild_id: int, interval_hours: float) -> tasks.Loop:
    @tasks.loop(hours=interval_hours)
    async def _loop():
        await bot.wait_until_ready()

        guild = bot.get_guild(guild_id)
        if guild is None:
            log(guild, f"[ERROR] Guild {guild_id} no longer accessible, stopping its update loop.")
            _loop.cancel()
            return

        guild_config = load_config().get(str(guild_id), {})
        channel = None
        if guild_config.get('channel_id'):
            channel = bot.get_channel(int(guild_config['channel_id']))

        log(guild, f"[START AUTOMATIC UPDATE] [{guild.name}] Interval: {interval_hours}h")

        updated_count = 0
        async with aiohttp.ClientSession() as session:
            for member in guild.members:
                try:
                    if await _update_member(guild, member, session, channel):
                        updated_count += 1
                except Exception as e:
                    log(guild, f"[ERROR] Failed updating {member.display_name}: {e}")

        log(guild, f"[FINISHED AUTOMATIC UPDATE] [{guild.name}] Updated {updated_count} member{'' if updated_count == 1 else 's'}.")

    @_loop.error
    async def _loop_error(error):
        log(bot.get_guild(guild_id), f"[FATAL] Update loop crashed: {error}")
        if not _loop.is_running():
            _loop.restart()

    return _loop

def start_guild_update_loop(guild: discord.Guild):
    """Starts (or restarts) the automatic update loop for one guild, using its configured interval."""
    existing = running_loops.get(guild.id)
    if existing and existing.is_running():
        return

    interval = load_config().get(str(guild.id), {}).get('update_interval', AUTO_UPDATE_TIMER_HOURS)
    loop = _make_guild_update_loop(guild.id, interval)
    running_loops[guild.id] = loop
    loop.start()

def restart_guild_update_loop(guild: discord.Guild):
    """Call this after update_interval changes in config, so the new interval takes effect."""
    existing = running_loops.get(guild.id)
    if existing:
        existing.cancel()
    start_guild_update_loop(guild)
