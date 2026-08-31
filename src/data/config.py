
import json
from src.data.connection import get_conn
from src.globals import DB_CONFIG_FILE


def load_config() -> dict:
    conn = get_conn()
    rows = conn.execute(f'SELECT key, value FROM {DB_CONFIG_FILE}').fetchall()
    conn.close()
    return {key: json.loads(value) for key, value in rows}

def save_config(config: dict):
    if not isinstance(config, dict):
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