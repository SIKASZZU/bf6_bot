import os
import sys

from dotenv import load_dotenv

load_dotenv('secrets.env')

from globals import bot, DEV_MODE
from commands import *


token = os.getenv("DISCORD_TOKEN") if not DEV_MODE else os.getenv("DISCORD_TOKEN_DEV")

if not token:
    raise RuntimeError("Set DISCORD_TOKEN or DISCORD_TOKEN_DEV as an environment variable before running.")

if __name__ == "__main__":
    print(f'Launching project DEV_MODE={DEV_MODE}')

    if not DEV_MODE and sys.stdin.isatty():
        x = input('WARNING! Are you sure, you want to run program in prod mode? Y/n: ')
        if x.lower() != 'y':
            print("Aborting.")
            sys.exit(0)

    bot.run(token)

