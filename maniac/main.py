import asyncio 
import discord_ios
from maniac.core.maniac import bot
from maniac.core.config import Config

def main():
    bot.run(Config.BOT_TOKEN)

if __name__ == "__main__":
    main()



