import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import aiohttp
import json
import os

# Enable intents (Members intent is mandatory for role manipulation)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

DB_FILE = "player_data.json"

# Confirmed accepted values from the /bf6/profile/ docs.
VALID_PLATFORMS = {"ea", "xbox", "psn", "steam", "epic", "pc", "xboxone", "ps4", "xboxseries", "ps5"}
DEFAULT_PLATFORM = "ea"

# Channel the 24h loop posts results into. Set at runtime with !setchannel,
# falls back to the guild's system channel if never set.
UPDATE_CHANNEL_ID = None

load_dotenv('secrets.env')

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


@bot.command()
async def link(ctx, name: str, platform: str = DEFAULT_PLATFORM):
    """
    Links your Discord account to a game account.
    Usage: !link <name> [platform]
    platform defaults to 'ea'. Valid values: ea, xbox, psn, steam, epic, pc, xboxone, ps4, xboxseries, ps5
    Example for a Steam player: !link Sikzu steam
    """
    platform = platform.lower()
    if platform not in VALID_PLATFORMS:
        await ctx.send(f"❌ Unknown platform `{platform}`. Valid options: {', '.join(sorted(VALID_PLATFORMS))}")
        return

    data = load_data()
    data[str(ctx.author.id)] = {"name": name, "platform": platform}
    save_data(data)

    await ctx.send(f"Successfully linked your Discord account to **{name}** on platform `{platform}`! I will track your stats automatically.")


@bot.command(name="linkuser")
@commands.has_permissions(administrator=True)
async def link_user(ctx, member: discord.Member, name: str, platform: str = DEFAULT_PLATFORM):
    """
    Admin-only: link someone else's Discord account to a game account.
    Usage: !linkuser <@member> <name> [platform]
    Example: !linkuser @Oljake Oljake
    Example for Steam: !linkuser @Oljake Oljake steam
    """
    platform = platform.lower()
    if platform not in VALID_PLATFORMS:
        await ctx.send(f"❌ Unknown platform `{platform}`. Valid options: {', '.join(sorted(VALID_PLATFORMS))}")
        return

    data = load_data()
    data[str(member.id)] = {"name": name, "platform": platform}
    save_data(data)

    await ctx.send(f"Linked {member.mention} to **{name}** on platform `{platform}`!")


@bot.command(name="setchannel")
@commands.has_permissions(administrator=True)
async def set_channel(ctx):
    """Sets the current channel as the target for the 24h stats report."""
    global UPDATE_CHANNEL_ID
    UPDATE_CHANNEL_ID = ctx.channel.id
    await ctx.send(f"✅ This channel ({ctx.channel.mention}) will now receive the 24h stats updates.")


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
    """Finds a role matching rank_name, creating it if it doesn't exist."""
    if not rank_name:
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


@tasks.loop(hours=24)
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

            rank, rank_name = get_level_and_rank(stats)

            print(f"--- {member.display_name} ({name} / {platform}) ---")
            print(f"Rank: {rank}")
            print(f"Rank name: {rank_name}")
            print(f"Raw response: {json.dumps(stats)[:1000]}")  # trimmed, so you can spot other field names

            await assign_rank_role(member, rank_name)

            if channel:
                await channel.send(
                    f"**{member.display_name}** (`{name}` / `{platform}`) — Rank: `{rank}` | Rank name: `{rank_name}`"
                )


@bot.command(name="updateall")
@commands.has_permissions(administrator=True)
async def force_update_all(ctx):
    """Manually forces the background update logic to run immediately via chat."""
    await ctx.send("🔄 Manually initiating a global player stats update...")

    try:
        await update_all_players()
        await ctx.send("✅ Global player stats update completed successfully!")
    except Exception as e:
        await ctx.send(f"❌ An error occurred during the update: {e}")
        print(f"Manual update error: {e}")


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")

    if not token:
        raise RuntimeError("Set DISCORD_TOKEN as an environment variable before running.")

    bot.run(token)