import json
from src.data.connection import get_conn
from src.globals import DB_DATA_FILE


def load_data() -> dict:
    conn = get_conn()
    rows = conn.execute(f'SELECT key, value FROM {DB_DATA_FILE}').fetchall()
    conn.close()
    return {key: json.loads(value) for key, value in rows}

def save_data(data: dict):
    if not isinstance(data, dict):
        print('Returning! No data provided for save_data.')
        return

    conn = get_conn()
    for key, value in data.items():
        conn.execute(
            f'INSERT OR REPLACE INTO {DB_DATA_FILE} (key, value) VALUES (?, ?)',
            (key, json.dumps(value))
        )
    conn.commit()
    conn.close()

def delete_data_key(server_key: str):
    conn = get_conn()
    conn.execute(f'DELETE FROM {DB_DATA_FILE} WHERE key = ?', (server_key,))
    conn.commit()
    conn.close()
