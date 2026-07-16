import os

from dotenv import load_dotenv
from globals import bot
from commands import *

load_dotenv('secrets.env')

token = os.getenv("DISCORD_TOKEN")
if not token:
    raise RuntimeError("Set DISCORD_TOKEN as an environment variable before running.")

if __name__ == "__main__":
    bot.run(token)