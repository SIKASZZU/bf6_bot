import discord
import json
import sqlite3
import os
import sys
from discord.ext import commands, tasks
from urllib.parse import urlencode

DEV_MODE = os.getenv('DEV_MODE', 'false').lower() == 'true'

# Enable intents (Members intent is mandatory for role manipulation)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

COMMAND_PREFIX = '/'

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)
bot.remove_command('help')

API_BASE_URL = 'https://api.gametools.network/bf6/profile/'
def build_api_url(name: str, platform: str) -> str:
    params = urlencode({'name': name, 'platform': platform})
    return f"{API_BASE_URL}?{params}"

file_folder = '/data'
def get_db_path():
    os.makedirs(file_folder, exist_ok=True)
    return os.path.join(file_folder, 'main.db')

# have more shots at api if productino mode
# may cause some limits but i dont know before not trying
API_MAX_RETRIES = 3 if DEV_MODE else 6

DB_DATA_FILE    = 'data'
DB_CONFIG_FILE  = 'config'

VALID_PLATFORMS = {'EA'}
DEFAULT_PLATFORM = 'EA'

AUTO_UPDATE_TIMER_HOURS : int = 3

# TODO: have it check by int somehow id // lol please fix this shit.
PERMISSIONED_ROLE: str = 'Admin'

running_loops: dict[int, tasks.Loop] = {}

def log(guild: discord.Guild, message: str):
    def get_caller() -> str:
        try: return sys._getframe(2).f_code.co_name
        except ValueError: return "Unknown"
    print(f'[server:{guild.name if guild else 'Unknown'}] (func:{get_caller()}) msg: {message}')

def get_conn():
    conn = sqlite3.connect(get_db_path())
    conn.execute(f'''
        CREATE TABLE IF NOT EXISTS {DB_DATA_FILE} (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.execute(f'''
        CREATE TABLE IF NOT EXISTS {DB_CONFIG_FILE} (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    return conn

def load_config() -> dict:
    conn = get_conn()
    rows = conn.execute(f'SELECT key, value FROM {DB_CONFIG_FILE}').fetchall()
    conn.close()
    return {key: json.loads(value) for key, value in rows}

def save_config(config: dict):
    if not isinstance(config, dict):
        # TODO: figure out how to remove print?
        print('Returning! No config provided for save_config.')
        return

    conn = get_conn()
    for key, value in config.items():
        conn.execute(
            f'INSERT OR REPLACE INTO {DB_CONFIG_FILE} (key, value) VALUES (?, ?)',
            (key, json.dumps(value))
        )
    conn.commit()
    conn.close()

def delete_config_key(server_key: str):
    conn = get_conn()
    conn.execute(f'DELETE FROM {DB_CONFIG_FILE} WHERE key = ?', (server_key,))
    conn.commit()
    conn.close()

def delete_data_key(server_key: str):
    conn = get_conn()
    conn.execute(f'DELETE FROM {DB_DATA_FILE} WHERE key = ?', (server_key,))
    conn.commit()
    conn.close()
