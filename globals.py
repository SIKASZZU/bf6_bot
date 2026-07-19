import discord
import json
import sqlite3
import os
from discord.ext import commands


# Enable intents (Members intent is mandatory for role manipulation)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

file_folder = os.getenv('DB_FOLDER', './data/')
os.makedirs(file_folder, exist_ok=True)

DEV_MODE = True

DB_PATH         = os.path.join(file_folder, 'main.db')
DB_DATA_FILE    = 'data'
DB_CONFIG_FILE  = 'config'

VALID_PLATFORMS = {'EA'}
DEFAULT_PLATFORM = 'EA'

AUTO_UPDATE_TIMER_HOURS : int = 1

def get_conn():

    conn = sqlite3.connect(DB_PATH)
    conn.execute(f'''
        CREATE TABLE IF NOT EXISTS {DB_CONFIG_FILE} (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    return conn

def load_config():
    conn = get_conn()
    rows = conn.execute(f'SELECT key, value FROM {DB_CONFIG_FILE}').fetchall()
    conn.close()
    return {key: json.loads(value) for key, value in rows}

def save_config(config: dict):
    if not config:
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
