import os
import ssl
import asyncio
import aiohttp
import asyncpg
import discord
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from dotenv import load_dotenv
import ujson as json

load_dotenv("/root/heist-v3/heist/.env")

PROXY = os.getenv("PROXY", "")
BLOXLINK_KEY = os.getenv("BLOXLINK_API_KEY", "")
PG_DSN = os.getenv("DSN", os.getenv("DATABASE_URL", ""))
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

TOKEN = "MTQ0MTg4MzQyNTIxNTc0MjE1Mw.GTCM8W.IEWbED0re9JkondtSDDaJC9Y8m6_jFh-OUmJ5E"
GUILD_ID = 1441882278598021120
CHANNEL_ID = 1441882280019623968
COMMAND_ID = "977319353156526141"
COMMAND_VERSION = "1076786613092364290"
APPLICATION_ID = "298796807323123712"

app = FastAPI()
redis = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
client = discord.Client()

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

connector = None
session = None
pool = None

rl_delay = 0.6
rl_retries = 4
last_req_time = 0.0
proxy_url = f"http://{PROXY}" if PROXY else None

rover_pending_requests = {}
rover_request_queue = asyncio.Queue()
rover_queue_processor = None

async def roblox_rl():
    global last_req_time
    now = asyncio.get_event_loop().time()
    delta = now - last_req_time
    if delta < rl_delay:
        await asyncio.sleep(rl_delay - delta)
    last_req_time = asyncio.get_event_loop().time()

async def ensure_session():
    global session, connector
    if connector is None:
        connector = aiohttp.TCPConnector(ssl=ssl_context)
    if session is None or session.closed:
        session = aiohttp.ClientSession(connector=connector)

async def fetch_json(method, url, headers=None, data=None, use_proxy=True):
    await ensure_session()
    h = headers or {}
    for attempt in range(rl_retries):
        try:
            await roblox_rl()
            kwargs = {"headers": h, "timeout": 15}
            if data is not None:
                kwargs["json"] = data
            if use_proxy and proxy_url:
                kwargs["proxy"] = proxy_url
            async with session.request(method, url, **kwargs) as resp:
                if resp.status == 429:
                    retry_after = float(resp.headers.get("Retry-After", "1"))
                    await asyncio.sleep(retry_after)
                    continue
                if resp.status >= 500:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                if resp.status == 403:
                    token = resp.headers.get("X-CSRF-TOKEN")
                    if token:
                        h["X-CSRF-TOKEN"] = token
                        kwargs["headers"] = h
                        async with session.request(method, url, **kwargs) as r2:
                            try:
                                return await r2.json()
                            except:
                                return {}
                try:
                    return await resp.json()
                except:
                    return {}
        except:
            await asyncio.sleep(1 * (attempt + 1))
    return {}

async def d2r_push_redis(discord_id: str, roblox_id: int, roblox_name: str, source: str, last_updated: str):
    roblox_id = int(roblox_id)
    await redis.setex(
        f"d2r:{source}:{discord_id}",
        7776000,
        f"{roblox_id}:{roblox_name}:{last_updated}"
    )
    await redis.setex(
        f"d2r:{source}:{roblox_id}",
        7776000,
        f"{discord_id}:{roblox_name}:{last_updated}"
    )

async def d2r_hit_redis(identifier, source=None):
    if source:
        if isinstance(identifier, int):
            key = f"d2r:{source}:{identifier}"
        else:
            key = f"d2r:{source}:{identifier}"
    else:
        if isinstance(identifier, int):
            key_pattern = f"d2r:*:{identifier}"
        else:
            key_pattern = f"d2r:*:{identifier}"
        
        keys = await redis.keys(key_pattern)
        results = []
        for key in keys:
            if isinstance(key, bytes):
                key = key.decode('utf-8')
            cached_data = await redis.get(key)
            if cached_data:
                if isinstance(cached_data, bytes):
                    cached_data = cached_data.decode("utf-8", "ignore")
                parts = cached_data.split(":")
                source_name = key.split(":")[1]
                if isinstance(identifier, int):
                    results.append({
                        "source": source_name,
                        "discord_id": parts[0],
                        "roblox_name": parts[1],
                        "last_updated": ":".join(parts[2:])
                    })
                else:
                    results.append({
                        "source": source_name,
                        "roblox_id": int(parts[0]),
                        "roblox_name": parts[1],
                        "last_updated": ":".join(parts[2:])
                    })
        return results
    
    cached_data = await redis.get(key)
    if cached_data:
        if isinstance(cached_data, bytes):
            cached_data = cached_data.decode("utf-8", "ignore")
        parts = cached_data.split(":")
        return parts[0], parts[1], ":".join(parts[2:])
    return None, None, None

async def d2r_hit_db(identifier, source=None):
    if pool is None:
        return None
    
    if source:
        if isinstance(identifier, int):
            row = await pool.fetchrow(
                "SELECT discord_id, roblox_name, last_updated FROM d2r_sources WHERE roblox_id = $1 AND source = $2",
                identifier, source
            )
        else:
            row = await pool.fetchrow(
                "SELECT roblox_id, roblox_name, last_updated FROM d2r_sources WHERE discord_id = $1 AND source = $2",
                int(identifier), source
            )
    else:
        if isinstance(identifier, int):
            rows = await pool.fetch(
                "SELECT discord_id, roblox_name, source, last_updated FROM d2r_sources WHERE roblox_id = $1",
                identifier
            )
        else:
            rows = await pool.fetch(
                "SELECT roblox_id, roblox_name, source, last_updated FROM d2r_sources WHERE discord_id = $1",
                int(identifier)
            )
        
        results = []
        for row in rows:
            row_dict = dict(row)
            if isinstance(identifier, int):
                row_dict["discord_id"] = str(row_dict["discord_id"])
            else:
                row_dict["roblox_id"] = int(row_dict["roblox_id"])
            row_dict["last_updated"] = row_dict["last_updated"].isoformat()
            results.append(row_dict)
        return results
    
    if row:
        row = dict(row)
        if isinstance(identifier, int):
            row["discord_id"] = str(row["discord_id"])
        else:
            row["roblox_id"] = int(row["roblox_id"])
        row["last_updated"] = row["last_updated"].isoformat()
        return row
    
    return None

async def d2r_push_db(discord_id: str, roblox_id: int, roblox_name: str, source: str):
    if pool is None:
        return
    await pool.execute(
        """
        INSERT INTO d2r_sources (discord_id, roblox_id, roblox_name, source, last_updated)
        VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
        ON CONFLICT (discord_id, source)
        DO UPDATE SET roblox_id = $2, roblox_name = $3, last_updated = CURRENT_TIMESTAMP;
        """,
        int(discord_id), int(roblox_id), roblox_name, source 
    )
    now = datetime.now(timezone.utc).isoformat()
    await d2r_push_redis(discord_id, roblox_id, roblox_name, source, now)

async def resolve_username(username: str):
    search = await fetch_json(
        "POST",
        "https://users.roblox.com/v1/usernames/users",
        headers={"accept": "application/json", "Content-Type": "application/json"},
        data={"usernames": [username], "excludeBannedUsers": False},
        use_proxy=False
    )
    arr = search.get("data") or []
    if not arr:
        raise HTTPException(404, "User not found")
    d = arr[0]
    roblox_id = d.get("id")
    roblox_name = d.get("name") or username
    display_name = d.get("displayName")
    if not roblox_id:
        raise HTTPException(404, "User not found")
    return int(roblox_id), roblox_name, display_name

async def ropro_lookup(roblox_id: int):
    try:
        await ensure_session()
        async with session.get(f"https://api.ropro.io/getUserInfoTest.php?userid={roblox_id}", timeout=12) as r:
            if r.status == 200:
                j = await r.json()
                return j.get("discord")
    except:
        return None
    return None

async def bloxlink_lookup(discord_id: int):
    if not BLOXLINK_KEY:
        return None
    try:
        await ensure_session()
        headers = {"Authorization": BLOXLINK_KEY}
        async with session.get(
            f"https://api.blox.link/v4/public/discord-to-roblox/{discord_id}",
            headers=headers,
            timeout=12
        ) as r:
            j = await r.json()
            if r.status == 200 and "error" not in j:
                roblox_id = j.get("robloxID")
                roblox_data = (j.get("resolved") or {}).get("roblox") or {}
                roblox_name = roblox_data.get("name")
                if roblox_id and not roblox_name:
                    roblox_name = await get_roblox_username(int(roblox_id))
                return roblox_id, roblox_name
    except:
        return None
    return None

async def get_avatar(roblox_id: int):
    try:
        await ensure_session()
        url = (
            "https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds="
            + str(roblox_id)
            + "&size=420x420&format=Png&isCircular=false"
        )
        async with session.get(url, timeout=10) as r:
            if r.status == 200:
                j = await r.json()
                d = j.get("data")
                if d:
                    return d[0].get("imageUrl")
    except:
        return None
    return None

def extract_roblox_info_from_message(message):
    if message.components:
        for row in message.components:
            for button in row.children:
                if isinstance(button, discord.Button) and button.style == discord.ButtonStyle.link:
                    url = button.url
                    if "https://www.roblox.com/users/" in url and "/profile" in url:
                        user_id_start = url.find("users/") + len("users/")
                        user_id_end = url.find("/profile", user_id_start)
                        roblox_user_id = url[user_id_start:user_id_end]
                        return {
                            "roblox_profile_url": url,
                            "roblox_user_id": roblox_user_id,
                            "status": "verified"
                        }
    
    if message.embeds:
        embed = message.embeds[0]
        if embed.description and "not verified with RoVer" in embed.description.lower():
            return {
                "roblox_profile_url": None,
                "roblox_user_id": None,
                "status": "not_verified"
            }
        
        roblox_user_id = None
        for field in embed.fields:
            if field.name == "Roblox user ID":
                roblox_user_id = field.value
                break
        
        if roblox_user_id:
            roblox_url = f"https://www.roblox.com/users/{roblox_user_id}/profile"
            return {
                "roblox_profile_url": roblox_url,
                "roblox_user_id": roblox_user_id,
                "status": "verified"
            }
    
    return None

@client.event
async def on_ready():
    print(f"[Discord] Logged in as {client.user}")

@client.event
async def on_message(message):
    if message.channel.id != CHANNEL_ID or message.author.id != int(APPLICATION_ID):
        return

    if message.nonce:
        for user_id, future in rover_pending_requests.items():
            if not future.done():
                roblox_info = extract_roblox_info_from_message(message)
                if roblox_info is not None:
                    future.set_result({
                        "roblox_profile_url": roblox_info.get("roblox_profile_url"),
                        "roblox_user_id": roblox_info.get("roblox_user_id"),
                        "status": roblox_info.get("status", "unknown")
                    })
                    rover_pending_requests.pop(user_id, None)
                    break
                else:
                    future.set_result({
                        "roblox_profile_url": None,
                        "roblox_user_id": None,
                        "status": "not_found"
                    })
                    rover_pending_requests.pop(user_id, None)
                    break

async def rover_process_queue():
    while True:
        userid, future = await rover_request_queue.get()
        await rover_process_single_request(userid, future)
        rover_request_queue.task_done()

async def rover_process_single_request(userid: str, future: asyncio.Future):
    rover_pending_requests[userid] = future
    nonce = str(int(datetime.now().timestamp() * 1000))

    payload = {
        "type": 2,
        "application_id": APPLICATION_ID,
        "guild_id": str(GUILD_ID),
        "channel_id": str(CHANNEL_ID),
        "session_id": "selfbot-session",
        "data": {
            "version": COMMAND_VERSION,
            "id": COMMAND_ID,
            "name": "whois",
            "type": 1,
            "options": [
                {
                    "type": 1,
                    "name": "discord",
                    "options": [
                        {
                            "type": 6,
                            "name": "user", 
                            "value": userid
                        }
                    ]
                }
            ]
        },
        "nonce": nonce,
        "analytics_location": "slash_ui"
    }

    route = discord.http.Route("POST", "/interactions")

    try:
        await client.http.request(route, json=payload)
        result = await asyncio.wait_for(future, timeout=30.0)
        if not future.done():
            future.set_result(result)
    except asyncio.TimeoutError:
        if not future.done():
            future.set_result({"error": "Timeout waiting for bot response"})
        rover_pending_requests.pop(userid, None)
    except Exception as e:
        if not future.done():
            future.set_result({"error": f"Failed to send interaction: {str(e)}"})
        rover_pending_requests.pop(userid, None)

async def get_roblox_username(roblox_id: int):
    try:
        await ensure_session()
        async with session.get(f"https://users.roblox.com/v1/users/{roblox_id}", timeout=10) as r:
            if r.status == 200:
                j = await r.json()
                return j.get("name")
    except:
        return None
    return None

@app.on_event("startup")
async def on_startup():
    global connector, session, pool, rover_queue_processor
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    session = aiohttp.ClientSession(connector=connector)
    await redis.ping()
    if PG_DSN:
        pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=5)
    asyncio.create_task(client.start(TOKEN))
    rover_queue_processor = asyncio.create_task(rover_process_queue())

@app.on_event("shutdown")
async def on_shutdown():
    global session, pool
    if session and not session.closed:
        await session.close()
    if pool:
        await pool.close()
    await redis.close()
    if rover_queue_processor:
        rover_queue_processor.cancel()

@app.get("/roblox2discord")
async def api_roblox2discord(username: str = Query(...)):
    roblox_id, roblox_name, display_name = await resolve_username(username)

    avatar = await get_avatar(roblox_id)
    if not avatar:
        avatar = "https://t0.rbxcdn.com/91d977e12525a5ed262cd4dc1c4fd52b?format=png"

    results = []
    
    cached_results = await d2r_hit_redis(roblox_id)
    if cached_results:
        results.extend(cached_results)
    
    db_results = await d2r_hit_db(roblox_id)
    if db_results:
        for db_result in db_results:
            found_in_cache = False
            for cached_result in results:
                if cached_result["source"] == db_result["source"]:
                    found_in_cache = True
                    break
            if not found_in_cache:
                results.append(db_result)
                await d2r_push_redis(
                    db_result["discord_id"], 
                    roblox_id, 
                    db_result["roblox_name"], 
                    db_result["source"], 
                    db_result["last_updated"]
                )

    if not results:
        ropro_discord = await ropro_lookup(roblox_id)
        if ropro_discord:
            now = datetime.now(timezone.utc).isoformat()
            await d2r_push_db(str(ropro_discord), roblox_id, roblox_name, "ropro")
            results.append({
                "discord_id": str(ropro_discord),
                "roblox_name": roblox_name,
                "source": "ropro",
                "last_updated": now
            })

    if not results:
        raise HTTPException(404, "No linked Discord found for this Roblox user")

    return JSONResponse({
        "roblox_id": roblox_id,
        "roblox_name": roblox_name,
        "roblox_display_name": display_name,
        "avatar": avatar,
        "results": results
    })

@app.get("/discord2roblox")
async def api_discord2roblox(discord_id: str = Query(...)):
    try:
        discord_id_int = int(discord_id)
    except:
        raise HTTPException(400, "invalid discord_id")
        
    results = []
    
    cached_results = await d2r_hit_redis(discord_id)
    
    if cached_results:
        results.extend(cached_results)
    
    db_results = await d2r_hit_db(discord_id)
    
    if db_results:
        for db_result in db_results:
            found_in_cache = False
            for cached_result in results:
                if cached_result["source"] == db_result["source"]:
                    found_in_cache = True
                    break
            if not found_in_cache:
                results.append(db_result)
                await d2r_push_redis(
                    discord_id,
                    db_result["roblox_id"],
                    db_result["roblox_name"],
                    db_result["source"],
                    db_result["last_updated"]
                )
    
    bloxlink_found = any(result["source"] == "bloxlink" for result in results)
    
    if not bloxlink_found:
        ext = await bloxlink_lookup(discord_id_int)
        if ext:
            roblox_id, roblox_name = ext
            if roblox_id and roblox_name:
                now = datetime.now(timezone.utc).isoformat()
                await d2r_push_db(discord_id, int(roblox_id), roblox_name, "bloxlink")
                bloxlink_result = {
                    "roblox_id": int(roblox_id),
                    "roblox_name": roblox_name,
                    "source": "bloxlink",
                    "last_updated": now
                }
                results.append(bloxlink_result)    
    
    if not results:
        raise HTTPException(404, "No linked Roblox account found for this Discord user")
    
    bloxlink_result = next((r for r in results if r["source"] == "bloxlink"), None)
    if bloxlink_result:
        return JSONResponse(bloxlink_result)
    
    first_result = results[0]
    return JSONResponse(first_result)

@app.get("/roverdiscord2roblox")
async def api_roverdiscord2roblox(discord_id: str = Query(...)):
    try:
        discord_id_int = int(discord_id)
    except:
        raise HTTPException(400, "invalid discord_id")
    
    cached_roblox_id, cached_roblox_name, last_updated = await d2r_hit_redis(discord_id, "rover")
    if cached_roblox_id and cached_roblox_name:
        return JSONResponse({
            "discord_id": str(discord_id),
            "roblox_id": int(cached_roblox_id),
            "roblox_name": cached_roblox_name,
            "last_updated": last_updated,
            "source": "rover"
        })
    
    row = await d2r_hit_db(discord_id, "rover")
    if row:
        await d2r_push_redis(discord_id, row["roblox_id"], row["roblox_name"], "rover", row["last_updated"])
        return JSONResponse({
            "discord_id": str(discord_id),
            "roblox_id": row["roblox_id"],
            "roblox_name": row["roblox_name"],
            "last_updated": row["last_updated"],
            "source": "rover"
        })
    
    future = asyncio.get_event_loop().create_future()
    await rover_request_queue.put((discord_id, future))
    
    result = await future
    if "error" in result:
        raise HTTPException(500, result["error"])
    
    if result["status"] != "verified" or not result["roblox_user_id"]:
        raise HTTPException(404, "No linked Roblox account found via RoVer")
    
    roblox_id = int(result["roblox_user_id"])
    roblox_name = await get_roblox_username(roblox_id)
    if not roblox_name:
        roblox_name = f"User{roblox_id}"
    
    now = datetime.now(timezone.utc).isoformat()
    await d2r_push_db(discord_id, roblox_id, roblox_name, "rover")
    
    return JSONResponse({
        "discord_id": str(discord_id),
        "roblox_id": roblox_id,
        "roblox_name": roblox_name,
        "last_updated": now,
        "source": "rover"
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("d2r:app", host="0.0.0.0", port=7690)