import os
import json
import aiohttp
from discord.ext import commands, tasks

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

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}!")
    if not update_all_players.is_running():
        update_all_players.start()
    print("Background updater task has started.")

@bot.event
async def on_command_error(ctx, error):
    """
    Catches errors from any command and prints a helpful usage message
    to the channel instead of letting the traceback go unseen in the console.
    """

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


async def get_or_create_role(guild: discord.Guild, rank_name: str):
    """Finds a role matching rank_name. """
    if not rank_name:
        print(f"Failed to find rank_name: {rank_name}")
        return None

    role = discord.utils.get(guild.roles, name=rank_name)
    if role is None:
        try:
            role = await guild.create_role(name=rank_name, reason="Auto-created rank role")
            print(f"Created new role: {rank_name}")
        except discord.Forbidden:
            print(f"Missing permissions to create role: {rank_name}")
            return None
        except discord.HTTPException as e:
            print(f"Failed to create role {rank_name}: {e}")
            return None

    return role


async def assign_rank_role(member: discord.Member, rank_name: str):
    """Ensures the role for rank_name exists, then gives it to member, removing other rank roles."""
    if not rank_name:
        return

    guild = member.guild
    role = await get_or_create_role(guild, rank_name)
    if role is None:
        return

    if role.position >= guild.me.top_role.position:
        print(f"Bot's top role is too low to assign '{rank_name}' - move the bot's role higher.")
        return

    try:
        if role not in member.roles:
            await member.add_roles(role, reason="Rank sync")
            print(f"Assigned {rank_name} to {member.display_name}")
    except discord.Forbidden:
        print(f"Missing permissions to assign role '{rank_name}' to {member.display_name}")
    except discord.HTTPException as e:
        print(f"Failed to assign role '{rank_name}' to {member.display_name}: {e}")


@tasks.loop(hours=AUTO_UPDATE_TIMER)
async def update_all_players():
    """
    Runs every 24h (and once immediately on startup, since tasks.loop fires
    right away on .start()). Walks every member currently in the guild -
    linked or not - and only skips the ones who haven't run !link yet.
    This means a newly-linked member gets picked up on the very next pass,
    no restart needed.
    """
    await bot.wait_until_ready()

    guild = bot.guilds[0]  # single-server assumption; loop over bot.guilds for multi-server
    data = load_data()

    channel = None
    if UPDATE_CHANNEL_ID:
        channel = bot.get_channel(UPDATE_CHANNEL_ID)
    if channel is None:
        channel = guild.system_channel  # may be None if not configured

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

            rankValue, rank_name = get_level_and_rank(stats)
            concise_rank_name = getRankNameFromCareerRank(rankValue)

            print(f"--- {member.display_name} ({name} / {platform}) ---")
            print(f"Rank: {rankValue}")
            print(f"Rank name: {concise_rank_name}")
            print(f"Raw response: {json.dumps(stats)[:1000]}")  # trimmed, so you can spot other field names

            await assign_rank_role(member, concise_rank_name)

            if channel:
                await channel.send(
                    f"**{member.display_name}** (`{name}` / `{platform}`) — Rank: `{rankValue}` | Rank name: `{concise_rank_name}`"
                )
