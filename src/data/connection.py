
import os
import sqlite3
from src.globals import file_folder, DB_DATA_FILE, DB_CONFIG_FILE, DB_NAME_FILE

def get_db_path():
    os.makedirs(file_folder, exist_ok=True)
    return os.path.join(file_folder, f'{DB_NAME_FILE}.db')

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
