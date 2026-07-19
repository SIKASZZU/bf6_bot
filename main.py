import os

from dotenv import load_dotenv
from globals import bot
from commands import *

load_dotenv('secrets.env')

token = os.getenv("DISCORD_TOKEN") if not DEV_MODE else os.getenv("DISCORD_TOKEN_DEV")
if not token:
    raise RuntimeError("Set DISCORD_TOKEN or DISCORD_TOKEN_DEV as an environment variable before running.")

if __name__ == "__main__":
    LAUNCH_CONFIRMED: bool = True
    print(f'Launching project DEV_MODE={DEV_MODE}')

    if not DEV_MODE:
        x = input('Are you sure, you want to run program in prod mode? Y/n')
        if (x != 'Y'):
            LAUNCH_CONFIRMED = False


    if (LAUNCH_CONFIRMED):
        bot.run(token)

    else:
        print('Shutting down.')


