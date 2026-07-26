import json
import aiohttp
import time
from discord.ext import commands, tasks
import asyncio

from globals import *
from ranks import getRankNameFromCareerRank, get_role_dict

def load_data():
    conn = get_conn()
    rows = conn.execute(f'SELECT key, value FROM {DB_DATA_FILE}').fetchall()
    conn.close()
    return {key: json.loads(value) for key, value in rows}

def save_data(data):
    if not data:
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

    config = load_config()
    guild_config = config.get(str(ctx.guild.id), {})
    channel_id = guild_config.get('channel_id')

    if not channel_id:
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
    print(f"Logged in as {bot.user.name}!")

    for guild in bot.guilds:
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"Synced {len(synced)} commands to {guild.name} ({guild.id})")

    if not update_all_players.is_running():
        update_all_players.start()

@bot.event
async def on_command_error(ctx, error):
    """
    Catches errors from any command and prints a helpful usage message
    to the channel instead of letting the traceback go unseen in the console.
    """

    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
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

    print(f"Unhandled error in command '{ctx.command}': {error}")
    await ctx.send(f"❌ An unexpected error occurred: {error}")

@bot.event
async def on_guild_join(guild):
    config = load_config()
    server_key = str(guild.id)

    if server_key not in config:
        config[server_key] = {
            "channel_id": None,
            "update_interval": 1
        }
        save_config(config)
        print(f"Initialized default configuration for server: {guild.name} ({server_key})")

    data = load_data()
    if server_key not in config:
        data[server_key] = {}
        save_data(data)
        print(f"Initialized default configuration for server: {guild.name} ({server_key})")


@bot.event
async def on_guild_remove(guild):
    config = load_config()
    server_key = str(guild.id)

    if server_key in config:
        del config[server_key]
        save_config(config)
        print(f"Removed configuration for server: {guild.name} ({server_key})")

    data = load_data()
    if server_key in data:
        del data[server_key]
        save_data(data)
        print(f"Removed saved data for server: {guild.name} ({server_key})")

async def fetch_player_stats(session: aiohttp.ClientSession, name: str, platform: str = DEFAULT_PLATFORM, channel: discord.TextChannel = None):
    """Hits the bf6 profile endpoint for a single player and returns the parsed JSON, or None.
    Retries up to max_retries times for any failed request."""

    max_retries = API_MAX_RETRIES

    for attempt in range(1, max_retries + 1):
        try:
            API_URL = build_api_url(name, platform)
            async with session.get(API_URL) as response:
                if response.status != 200:
                    raise Exception(f'{response.status}')

                stats = await response.json()

                if isinstance(stats, dict) and "errors" in stats:
                    raise Exception(f"{stats['errors']}")

                print(f"✅ Data fetch successful for ({name}, {platform}). ({attempt}/{max_retries}) attempts.")
                return stats

        except Exception as e:
            print(f"ERROR! [Attempt {attempt}/{max_retries}] ({name}, {platform}): {e}")
            await asyncio.sleep(2 ** attempt)
            continue

    print(f"❌ Data fetch failed for ({name}, {platform}). ({attempt}/{max_retries}) attempts.")
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
        print(f"Failed to find rank_name: {rank_name}")
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
        print('Missing role!')
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
            print(f'Returning! role_cls is not a valid role object: {role_cls!r}')
            continue

        print(f'Removing {role_name} from {member.display_name}, extra: {type(role_cls)}')

        await member.remove_roles(role_cls, reason='Rank sync - removing role')

        if channel:
            await channel.send(f"✅ Removed `{role_name}` from `{member.display_name}`")

async def assign_rank_role(member: discord.Member, rank_name: str, channel: discord.TextChannel = None):
    """Ensures the role for rank_name exists, then gives it to member, removing other rank roles."""
    if not rank_name:
        print('Returning! rank_name is None.')
        return

    guild = member.guild

    role = await get_role(guild, rank_name, channel)
    if role is None:
        print('Returning! Role is None.')
        return

    if role.position >= guild.me.top_role.position:
        print(f"Bot's top role is too low to assign '{rank_name}' - move the bot's role higher.")
        if channel:
            await channel.send(f"❌ Bot's top role is too low to assign '{rank_name}' - move the bot's role higher.")
        return

    try:
        if role not in member.roles:
            await member.add_roles(role, reason="Rank sync - assign role")
            print(f"Assigned {rank_name} to {member.display_name}")
            if channel:
                await channel.send(f"✅ Assigned `{rank_name}` to `{member.display_name}`")
            return

    except discord.Forbidden:
        print(f"Missing permissions to assign role '{rank_name}' to {member.display_name}")

    except discord.HTTPException as e:
        print(f"Failed to assign role '{rank_name}' to {member.display_name}: {e}")


async def _update_member(guild: discord.Guild, member: discord.Member, session, channel, show_success: bool = True):
    """Update a single member's rank. Only shows success messages if show_success is True."""
    await bot.wait_until_ready()

    if member.bot:
        return False

    entry = get_player_entry(load_data(), guild.id, member.id)
    if not entry:
        print(f"Skipping {member.display_name}: no game account linked (!link needed)")
        return False

    name = entry["name"]
    platform = entry.get("platform", DEFAULT_PLATFORM)

    stats = await fetch_player_stats(session, name, platform, channel if show_success else None)
    if stats is None:
        if show_success and channel:
            await channel.send(f"❌ Failed to fetch stats for {member.mention} ({name}). API may be down.")
        return False

    rankValue, _ = get_level_and_rank(stats)
    if rankValue is None:
        print(f"[WARNING] Could not extract rank for {member.display_name} ({name})")
        if show_success and channel:
            await channel.send(f"⚠️ Could not extract rank for {member.mention} ({name})")
        return False

    concise_rank_name = getRankNameFromCareerRank(rankValue)

    print(f"--- {member.display_name} ({name} / {platform}) {rankValue} | {concise_rank_name} ---")

    await assign_rank_role(member, concise_rank_name, channel if show_success else None)
    await remove_rank_role(guild, member, concise_rank_name, channel if show_success else None)
    return True

async def _update_guild_members(guild: discord.Guild, session: aiohttp.ClientSession, channel: discord.TextChannel):
    print(f"Automatic update in progress for {guild.name} ({guild.id})... Interval: {load_config().get(str(guild.id), {}).get('update_interval', AUTO_UPDATE_TIMER_HOURS)} hours")

    if channel is None and load_config().get(str(guild.id), {}).get('channel_id'):
        channel = bot.get_channel(load_config().get(str(guild.id), {}).get('channel_id'))

    if channel:
        await channel.send(f"🔄 Automatic update in progress for {guild.name}...")
    else:
        # set_config_guild_channel(bot.get_channel(channel_id))
        print('#9w8dbufg - channel is none and nothing will be done! ')
        ...

    updated_count = 0
    for member in guild.members:
        if await _update_member(guild, member, session, channel, show_success=False):
            updated_count += 1

    if channel:
        await channel.send(f"✅ Automatic update complete! Updated {updated_count} member{'' if (updated_count == 0 or updated_count == 1) else 's'}.")

    print(f"Automatic update complete for {guild.name}! Updated {updated_count} member{'' if (updated_count == 0 or updated_count == 1) else 's'}.")


@tasks.loop(hours=AUTO_UPDATE_TIMER_HOURS)
async def update_all_players(report_channel: discord.TextChannel = None, guild: discord.Guild = None):
    await bot.wait_until_ready()

    if guild is not None:
        guilds_to_update = [guild]
    elif report_channel is not None:
        guild_context = getattr(report_channel, 'guild', None)
        guilds_to_update = [guild_context] if guild_context is not None else []
    else:
        guilds_to_update = list(bot.guilds)

    if not guilds_to_update:
        print('Error! Automatic update skipped: no specific guild context provided.')
        return

    async with aiohttp.ClientSession() as session:
        for target_guild in guilds_to_update:
            await _update_guild_members(target_guild, session, channel=report_channel)