import os
import json
import aiohttp
from discord.ext import commands, tasks
import time

from globals import *
from ranks import getRankNameFromCareerRank


def load_data():
    """Loads the linked player database."""
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}


def save_data(data):
    """Saves the player database to a JSON file."""
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_player_entry(data: dict, discord_id: str):
    """
    Returns {"name": ..., "platform": ...} for a linked discord id, or None.
    Old entries were plain strings (just the EA name) - normalize those to
    the new dict shape so both formats keep working.
    """
    entry = data.get(discord_id)
    if entry is None:
        return None
    if isinstance(entry, str):
        return {"name": entry, "platform": DEFAULT_PLATFORM}
    return entry


_last_command_time = 0
REQUEST_INTERVAL_SECONDS = 5

@bot.check
async def global_rate_limit(ctx):
    global _last_command_time
    now = time.monotonic() # lol wtf

    if now - _last_command_time < REQUEST_INTERVAL_SECONDS:
        # silently blocks the command from running
        return False

    _last_command_time = now
    return True

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}!")

    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} command(s): {[c.name for c in synced]}")

    if not update_all_players.is_running():
        update_all_players.start()

@bot.event
async def on_command_error(ctx, error):
    """
    Catches errors from any command and prints a helpful usage message
    to the channel instead of letting the traceback go unseen in the console.
    """

    if isinstance(error, commands.CheckFailure):
        await ctx.send("⏳ Bot is busy, try again in a moment.")
        return

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

    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
        return

    if isinstance(error, commands.CommandNotFound):
        return  # unknown command, ignore silently

    print(f"Unhandled error in command '{ctx.command}': {error}")
    await ctx.send(f"❌ An unexpected error occurred: {error}")


async def fetch_player_stats(session: aiohttp.ClientSession, name: str, platform: str = DEFAULT_PLATFORM):
    """Hits the bf6 profile endpoint for a single player and returns the parsed JSON, or None."""
    api_url = f"https://api.gametools.network/bf6/profile/?name={name}&platform={platform}"

    print(f"api_url for {name} ({platform}): {api_url}")

    async with session.get(api_url) as response:
        if response.status == 404:
            print(f"[404] Player not found: {name} on platform {platform}")
            return None
        if response.status != 200:
            print(f"API Error for {name}: HTTP {response.status}")
            return None

        try:
            stats = await response.json()
        except Exception as e:
            print(f"Failed to parse JSON for {name}: {e}")
            return None

        if isinstance(stats, dict) and "errors" in stats:
            print(f"GameTools API Error for {name}: {stats['errors']}")
            return None

        return stats


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

    role = discord.utils.get(guild.roles, name=rank_name)
    if role is None:
        print('Missing role!')
        if channel:
            await channel.send(f"❌ Couldn't find a role based off rank name: {rank_name}")
    return role


async def assign_rank_role(member: discord.Member, rank_name: str, channel: discord.TextChannel = None):
    """Ensures the role for rank_name exists, then gives it to member, removing other rank roles."""
    if not rank_name:
        return

    guild = member.guild
    role = await get_role(guild, rank_name, channel)

    if role is None:
        return

    if role.position >= guild.me.top_role.position:
        print(f"Bot's top role is too low to assign '{rank_name}' - move the bot's role higher.")
        if channel:
            await channel.send(f"Bot's top role is too low to assign '{rank_name}' - move the bot's role higher.")
        return

    try:
        if role not in member.roles:
            await member.add_roles(role, reason="Rank sync")
            print(f"Assigned {rank_name} to {member.display_name}")
            if channel:
                await channel.send(f"✅Assigned `{rank_name}` to `{member.display_name}`")

    except discord.Forbidden:
        print(f"Missing permissions to assign role '{rank_name}' to {member.display_name}")

    except discord.HTTPException as e:
        print(f"Failed to assign role '{rank_name}' to {member.display_name}: {e}")

async def update_player(member: discord.Member, report_channel: discord.TextChannel = None):
    " Call update on player using their discord's name"
    await bot.wait_until_ready()

    data = load_data()

    # fix this
    channel = report_channel
    if channel is None and UPDATE_CHANNEL_ID:
        channel = bot.get_channel(UPDATE_CHANNEL_ID)

    async with aiohttp.ClientSession() as session:
        if member.bot:
            print(f"Skipping {member.display_name}: no game account linked (!link needed)")
            return

        entry = get_player_entry(data, str(member.id))
        if not entry:
            print(f"Skipping {member.display_name}: no game account linked (!link needed)")
            return

        name = entry["name"]
        platform = entry.get("platform", DEFAULT_PLATFORM)

        stats = await fetch_player_stats(session, name, platform)
        if stats is None:
            return

        rankValue, _ = get_level_and_rank(stats)
        concise_rank_name = getRankNameFromCareerRank(rankValue)

        print(f"--- {member.display_name} ({name} / {platform}) {rankValue} | {concise_rank_name} ---")
        await assign_rank_role(member, concise_rank_name, channel)

@tasks.loop(hours=AUTO_UPDATE_TIMER_HOURS)
async def update_all_players(report_channel: discord.TextChannel = None):
    """
    Runs every {AUTO_UPDATE_TIMER_HOURS}h automatically (falls back to
    UPDATE_CHANNEL_ID / guild system channel), or can be called manually
    with report_channel=ctx.channel to report back wherever it was triggered from.
    """
    await bot.wait_until_ready()

    guild = bot.guilds[0]
    data = load_data()

    # fix this
    channel = report_channel
    if channel is None and UPDATE_CHANNEL_ID:
        channel = bot.get_channel(UPDATE_CHANNEL_ID)

    if channel is None:
        channel = guild.system_channel  # still may be None — every .send below is guarded

    async with aiohttp.ClientSession() as session:
        for member in guild.members:
            if member.bot:
                continue

            entry = get_player_entry(data, str(member.id))
            if not entry:
                print(f"Skipping {member.display_name}: no game account linked (!link needed)")
                continue

            name = entry["name"]
            platform = entry.get("platform", DEFAULT_PLATFORM)

            stats = await fetch_player_stats(session, name, platform)
            if stats is None:
                continue

            rankValue, _ = get_level_and_rank(stats)
            concise_rank_name = getRankNameFromCareerRank(rankValue)

            print(f"--- {member.display_name} ({name} / {platform}) {rankValue} | {concise_rank_name} ---")
            await assign_rank_role(member, concise_rank_name, channel)