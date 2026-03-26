import asyncio
from stare.core.stare import bot
from stare.core.config import Config

def main():
    bot.run(Config.BOT_TOKEN)

if __name__ == "__main__":
    main()