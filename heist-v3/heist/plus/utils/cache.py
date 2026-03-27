import asyncio
from heist.plus.utils.db import get_db_connection, redis_client

CACHE_EXPIRY_TIME = 300

async def set_embed_color(user_id: int, color: int):
    if isinstance(user_id, str):
        user_id = int(user_id)

    if isinstance(color, str):
        color = int(color, 16)

    if isinstance(color, int) and 0 <= color <= 0xFFFFFF:
        await redis_client.set(f"color:{user_id}", str(color), ex=CACHE_EXPIRY_TIME)
        async with get_db_connection() as conn:
            await conn.execute(
                """
                INSERT INTO preferences (user_id, color)
                VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET color = $2
                """,
                user_id, color
            )

async def get_embed_color(user_id) -> int:
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        raise ValueError("Invalid user_id type. Expected int or numeric string.")

    redis_key = f"color:{user_id}"
    cached = await redis_client.get(redis_key)
    if cached:
        return int(cached)

    async with get_db_connection() as conn:
        row = await conn.fetchrow("SELECT color FROM preferences WHERE user_id = $1", user_id)
        color_value = row['color'] if row and row['color'] is not None else 0xd3d6f1
        await redis_client.set(redis_key, str(color_value), ex=CACHE_EXPIRY_TIME)
        return color_value
