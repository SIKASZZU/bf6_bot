import discord
from discord.ext import commands


# Enable intents (Members intent is mandatory for role manipulation)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


DB_FILE = "player_data.json"

# Confirmed accepted values from the /bf6/profile/ docs.
VALID_PLATFORMS = {"ea", "xbox", "psn", "steam", "epic", "pc", "xboxone", "ps4", "xboxseries", "ps5"}
DEFAULT_PLATFORM = "ea"

# falls back to the guild's system channel if never set.
UPDATE_CHANNEL_ID = None

# Channel the 24h loop posts results into.
AUTO_UPDATE_TIMER : int = 60 * 60 * 24