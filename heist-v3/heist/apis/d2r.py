from fastapi import FastAPI, HTTPException, Depends, Request, Response
import aiohttp, asyncio, asyncpg, os
from datetime import datetime
import uvicorn
from redis.asyncio import Redis
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from dotenv import load_dotenv

load_dotenv("/root/heist-v3/heist/.env")

app = FastAPI()

REDIS_URL = "redis://localhost:6379"
DATABASE_URL = os.getenv("DSN")
API_KEY = "4x201lzopqsdAA"
BLOXLINK_KEY = os.getenv("BLOXLINK_API_KEY")

redis = None
db = None
session = None
queue = asyncio.Queue()
WORKERS = 3

async def worker():
    while True:
        func, args, fut = await queue.get()
        try:
            result = await func(*args)
            fut.set_result(result)
        except Exception as e:
            fut.set_exception(e)
        finally:
            queue.task_done()

async def enqueue(func, *args):
    fut = asyncio.get_event_loop().create_future()
    await queue.put((func, args, fut))
    return await fut

async def get_redis():
    global redis
    if not redis:
        redis = Redis.from_url(REDIS_URL, decode_responses=True)
    return redis

async def get_db():
    global db
    if not db:
        db = await asyncpg.create_pool(DATABASE_URL)
    return db

async def fetch_ropro(roblox_id: int):
    global session
    try:
        async with session.get(f'https://api.ropro.io/getUserInfoTest.php?userid={roblox_id}') as r:
            if r.status == 200:
                data = await r.json()
                return data.get("discord")
    except:
        return None

async def fetch_bloxlink(discord_id: str):
    global session
    import ssl
    url = f"https://api.blox.link/v4/public/discord-to-roblox/{discord_id}"
    headers = {"Authorization": BLOXLINK_KEY}
    try:
        async with session.get(url, headers=headers) as response:
            data = await response.json()
            if response.status == 200 and "error" not in data:
                roblox_id = data.get("robloxID")
                roblox_name = None
                resolved = data.get("resolved", {}).get("roblox")
                if resolved and isinstance(resolved, dict):
                    roblox_name = resolved.get("name")
                if roblox_id and not roblox_name:
                    connector = aiohttp.TCPConnector(ssl=False)
                    async with aiohttp.ClientSession(connector=connector) as insecure_session:
                        async with insecure_session.get(f"https://users.roproxy.com/v1/users/{roblox_id}") as r2:
                            if r2.status == 200:
                                udata = await r2.json()
                                roblox_name = udata.get("name")
                if roblox_id and roblox_name:
                    return int(roblox_id), roblox_name
    except:
        return None, None
    return None, None

async def hit_db_r2d(roblox_id: int):
    pool = await get_db()
    row = await pool.fetchrow("SELECT discord_id, roblox_name, last_updated FROM dtr_mappings WHERE roblox_id=$1", roblox_id)
    return dict(row) if row else None

async def hit_db_d2r(discord_id: str):
    pool = await get_db()
    row = await pool.fetchrow("SELECT roblox_id, roblox_name, last_updated FROM dtr_mappings WHERE discord_id=$1", discord_id)
    return dict(row) if row else None

async def hit_redis_r2d(roblox_id: int):
    r = await get_redis()
    cached = await r.get(f"dtr:{roblox_id}")
    if cached:
        parts = cached.split(":")
        return {"discord_id": parts[0], "roblox_name": parts[1], "last_updated": ":".join(parts[2:])}
    return None

async def hit_redis_d2r(discord_id: str):
    r = await get_redis()
    cached = await r.get(f"r2d:{discord_id}")
    if cached:
        parts = cached.split(":")
        return {"roblox_id": int(parts[0]), "roblox_name": parts[1], "last_updated": ":".join(parts[2:])}
    return None

async def push_redis_r2d(discord_id, roblox_id, roblox_name):
    r = await get_redis()
    now = datetime.now().isoformat()
    await r.setex(f"dtr:{roblox_id}", 7776000, f"{discord_id}:{roblox_name}:{now}")
    await r.setex(f"r2d:{discord_id}", 7776000, f"{roblox_id}:{roblox_name}:{now}")

def check_key(key: str):
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

def is_local(request: Request):
    return request.client.host in ("127.0.0.1", "localhost")

def conditional_rate_limiter(times: int, seconds: int):
    async def limiter(request: Request, response: Response):
        if request.client.host in ("127.0.0.1", "localhost"):
            return
        return await RateLimiter(times=times, seconds=seconds)(request, response)
    return Depends(limiter)

@app.get("/v1/search/r2d", dependencies=[conditional_rate_limiter(100, 60)])
async def search_r2d(roblox_id: int, key: str = None, request: Request = None):
    if not is_local(request):
        check_key(key)
    data = await hit_redis_r2d(roblox_id)
    if not data:
        data = await hit_db_r2d(roblox_id)
    discord = data.get("discord_id") if data else None
    roblox_name = data.get("roblox_name") if data else None
    ropro_discord = await enqueue(fetch_ropro, roblox_id)
    if not discord and not ropro_discord:
        raise HTTPException(status_code=404, detail="No linked Discord found")
    if discord and roblox_name:
        await push_redis_r2d(discord, roblox_id, roblox_name)
    return {
        "roblox_id": roblox_id,
        "roblox_name": roblox_name,
        "discord": discord,
        "ropro_discord": ropro_discord,
        "last_updated": data.get("last_updated") if data else None
    }

@app.get("/v1/search/d2r", dependencies=[conditional_rate_limiter(50, 60)])
async def search_d2r(discord_id: str, key: str = None, request: Request = None):
    if not is_local(request):
        check_key(key)
    data = await hit_redis_d2r(discord_id)
    if not data:
        data = await hit_db_d2r(discord_id)
    roblox_id = data.get("roblox_id") if data else None
    roblox_name = data.get("roblox_name") if data else None
    last_updated = data.get("last_updated") if data else None
    if not roblox_id or not roblox_name:
        roblox_id, roblox_name = await fetch_bloxlink(discord_id)
        if roblox_id and roblox_name:
            now = datetime.now().isoformat()
            await push_redis_r2d(discord_id, roblox_id, roblox_name)
            last_updated = now
    if not roblox_id or not roblox_name:
        raise HTTPException(status_code=404, detail="No linked Roblox account found")
    return {
        "discord_id": discord_id,
        "roblox_id": roblox_id,
        "roblox_name": roblox_name,
        "last_updated": last_updated
    }

@app.on_event("startup")
async def startup_event():
    global session
    session = aiohttp.ClientSession()
    r = await get_redis()
    await FastAPILimiter.init(r)
    for _ in range(WORKERS):
        asyncio.create_task(worker())

@app.on_event("shutdown")
async def shutdown_event():
    global session
    if session:
        await session.close()
    if redis:
        await redis.close()

if __name__ == "__main__":
    uvicorn.run("d2r:app", host="0.0.0.0", port=9038, reload=True)
