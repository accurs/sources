import datetime
import os
from typing import Any

import aiohttp
from discord.ext import commands
from pydantic import BaseModel
from tools.helpers import AkariContext


class Weather(BaseModel):
    """
    Model for weather api results
    """

    place: str
    country: str
    temp_c: float
    temp_f: float
    wind_mph: float
    wind_kph: float
    humidity: float
    condition: str
    condition_image: str
    condition: str
    time: Any


class WeatherLocation(commands.Converter):
    async def convert(self, ctx: AkariContext, argument: str) -> Weather:
        url = "http://api.weatherapi.com/v1/current.json"
        params = {"key": os.environ.get("weather"), "q": argument}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession(headers=headers) as cs:
            async with cs.get(url, params=params) as r:
                if r.status == 400:
                    raise commands.BadArgument("The location provided is not valid")

                data = await r.json()

                payload = {
                    "place": data["location"]["name"],
                    "country": data["location"]["country"],
                    "temp_c": data["current"]["temp_c"],
                    "temp_f": data["current"]["temp_f"],
                    "wind_mph": data["current"]["wind_mph"],
                    "wind_kph": data["current"]["wind_kph"],
                    "humidity": data["current"]["humidity"],
                    "condition": data["current"]["condition"]["text"],
                    "condition_image": f"http:{data['current']['condition']['icon']}",
                    "time": datetime.datetime.fromtimestamp(
                        int(data["current"]["last_updated_epoch"])
                    ),
                }

                return Weather(**payload)
