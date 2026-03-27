import asyncio
import asyncpg
import redis.asyncio as redis
from contextlib import asynccontextmanager
from dotenv import dotenv_values
import os

env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
config = dotenv_values(env_path)

DATA_DB = config["DATA_DB"]

redis_pool = redis.ConnectionPool(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True,
    max_connections=250
)
redis_client = redis.Redis(connection_pool=redis_pool)

class Database:
    _pool = None
    _lock = asyncio.Lock()

    @classmethod
    async def init_pool(cls):
        if cls._pool is None:
            async with cls._lock:
                if cls._pool is None:
                    print("Initializing database pool...")
                    cls._pool = await asyncpg.create_pool(
                        dsn=DATA_DB,
                        min_size=5,
                        max_size=20,
                        max_inactive_connection_lifetime=300,
                        max_queries=10_000,
                    )
                    print("Database pool initialized successfully.")
        return cls._pool

    @classmethod
    @asynccontextmanager
    async def get_connection(cls):
        pool = await cls.init_pool()
        async with pool.acquire() as conn:
            yield conn

@asynccontextmanager
async def get_db_connection():
    async with Database.get_connection() as conn:
        yield conn

# --------------------------
#  Heist-compatible checks
# --------------------------

async def check_blacklisted(user_id: int) -> bool:
    key = f"blacklist:{user_id}"
    cached = await redis_client.get(key)
    if cached is not None:
        return cached == "True"

    async with Database.get_connection() as conn:
        result = await conn.fetchval("SELECT 1 FROM blacklist WHERE user_id = $1", str(user_id))
        is_blacklisted = bool(result)

    await redis_client.setex(key, 300, str(is_blacklisted))
    return is_blacklisted


async def check_donor(user_id: int) -> bool:
    key = f"donor:{user_id}"
    cached = await redis_client.get(key)
    if cached is not None:
        return cached == "True"

    async with Database.get_connection() as conn:
        result = await conn.fetchval("SELECT 1 FROM donors WHERE user_id = $1", str(user_id))
        is_donor = bool(result)

    await redis_client.setex(key, 300, str(is_donor))
    return is_donor


async def check_famous(user_id: int) -> bool:
    key = f"famous:{user_id}"
    cached = await redis_client.get(key)
    if cached is not None:
        return cached == "True"

    async with Database.get_connection() as conn:
        fame_status = await conn.fetchval("SELECT fame FROM user_data WHERE user_id = $1", str(user_id))
        is_famous = bool(fame_status)

    await redis_client.setex(key, 300, str(is_famous))
    return is_famous


async def check_owner(user_id: int) -> bool:
    key = f"owner:{user_id}"
    cached = await redis_client.get(key)
    if cached is not None:
        return cached == "True"

    async with Database.get_connection() as conn:
        result = await conn.fetchval("SELECT 1 FROM owners WHERE user_id = $1", str(user_id))
        is_owner = bool(result)

    await redis_client.setex(key, 300, str(is_owner))
    return is_owner


async def check_booster(user_id: int) -> bool:
    key = f"booster:{user_id}"
    cached = await redis_client.get(key)
    if cached is not None:
        return cached == "True"

    async with Database.get_connection() as conn:
        result = await conn.fetchval("SELECT booster FROM user_data WHERE user_id = $1", str(user_id))
        is_booster = bool(result)

    await redis_client.setex(key, 300, str(is_booster))
    return is_booster


async def reset_cache(user_id: int):
    keys = [
        f"blacklist:{user_id}",
        f"donor:{user_id}",
        f"famous:{user_id}",
        f"owner:{user_id}",
        f"booster:{user_id}",
    ]
    try:
        await redis_client.delete(*keys)
    except Exception:
        for key in keys:
            try:
                await redis_client.delete(key)
            except Exception:
                continue
