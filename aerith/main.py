from asyncio import run
from os import getenv
from dotenv import load_dotenv
from discord import ActivityType

from bot.aerith import Aerith
from bot.config import Status, Config

async def main():
    load_dotenv()

    config = Config(
        status=Status(
            type=ActivityType.streaming,
            name="🔗 aerith.lol",
            url="https://twitch.tv/aerith",
        )
    )

    async with Aerith(config) as aerith:
        if (token := getenv("token")) is not None:
            await aerith.start(token)
            

run(main())
