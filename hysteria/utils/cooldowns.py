import time
import redis.asyncio as aioredis
from functools import wraps
from discord import app_commands, Interaction, Embed, Color
import os
from dotenv import dotenv_values

config = dotenv_values(".env")
REDIS = config["REDIS_URL"]

class RedisCooldown:
    def __init__(self, redis_url: str, per_minute: int, per_hour: int, delay: int = 3):
        self.redis_url = redis_url
        self.per_minute = per_minute
        self.per_hour = per_hour
        self.delay = delay
        self.redis = None

    async def init(self):
        self.redis = await aioredis.from_url(self.redis_url, decode_responses=True)

    def __call__(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            interaction: Interaction = kwargs.get("interaction") or args[1]
            user_id = interaction.user.id
            now = int(time.time())

            minute_key = f"cd:minute:{user_id}"
            hour_key = f"cd:hour:{user_id}"
            last_key = f"cd:last:{user_id}"

            if not self.redis:
                await self.init()

            last_use = await self.redis.get(last_key)
            if last_use:
                last_use = int(last_use)
                if now - last_use < self.delay:
                    ts = last_use + self.delay
                    embed = Embed(description=f"ok chill out a little, u can use this again in <t:{ts}:R>", color=Color.yellow())
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

            minute_count = await self.redis.llen(minute_key)
            if minute_count >= self.per_minute:
                first = int(await self.redis.lindex(minute_key, 0))
                ts = first + 60
                embed = Embed(description=f"you can only use this **{self.per_minute} times/minute**, u can use it again in <t:{ts}:R>", color=Color.yellow())
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            hour_count = await self.redis.llen(hour_key)
            if hour_count >= self.per_hour:
                first = int(await self.redis.lindex(hour_key, 0))
                ts = first + 3600
                embed = Embed(description=f"you can only use this **{self.per_hour} times/hour**, u can use it again in <t:{ts}:R>", color=Color.yellow())
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            await self.redis.rpush(minute_key, now)
            await self.redis.rpush(hour_key, now)
            await self.redis.set(last_key, now)
            await self.redis.expire(minute_key, 60)
            await self.redis.expire(hour_key, 3600)
            await func(*args, **kwargs)

        return wrapper

def cooldown(redis_url: str = None):
    if redis_url is None:
        redis_url = REDIS
    return RedisCooldown(redis_url, per_minute=10, per_hour=150, delay=3)
