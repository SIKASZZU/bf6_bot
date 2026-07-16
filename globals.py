import discord
import os
import json
from discord.ext import commands


# Enable intents (Members intent is mandatory for role manipulation)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)


DB_FILE = 'player_data.json'
CONFIG_FILE = 'config.json'

VALID_PLATFORMS = {'EA'}
DEFAULT_PLATFORM = 'EA'

# falls back to the guild's system channel if never set.
UPDATE_CHANNEL_ID = None

# Channel the 24h loop posts results into.

AUTO_UPDATE_TIMER_HOURS : int = 24

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_config(config: dict):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)


_config = load_config()
UPDATE_CHANNEL_ID = _config.get('channel_id')


