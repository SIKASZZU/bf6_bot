import discord
import os
from discord.ext import commands, tasks


DEV_MODE = os.getenv('DEV_MODE', 'false').lower() == 'true'

# Enable intents (Members intent is mandatory for role manipulation)
intents = discord.Intents.default()
intents.members = True

# TODO: remove COMMAND_PREFIX, because all are slash commands now.
COMMAND_PREFIX = '/'
REQUEST_INTERVAL_SECONDS = 2

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)
bot.remove_command('help')

API_BASE_URL = 'https://api.gametools.network/bf6/profile/'
file_folder = '/data'

# gametools has 10requests per sec limit
API_MAX_RETRIES = 3 if DEV_MODE else 6

DB_DATA_FILE    = 'data'
DB_CONFIG_FILE  = 'config'
DB_NAME_FILE    = 'main'

VALID_PLATFORMS = {'EA'}
DEFAULT_PLATFORM = 'EA'

AUTO_UPDATE_TIMER_HOURS : int = 3

running_loops: dict[int, tasks.Loop] = {}