import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import threading
import websockets
import json
from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.security.api_key import APIKeyHeader
import aiohttp
import uvicorn
from datetime import datetime, timedelta, UTC
import asyncpg
import sys, os
sys.path.append("/root/heist-v3")
from heist.plus.utils.db import Database, get_db_connection, redis_client as _redis_client_from_plus
from heist.plus.utils.compress import compress as sync_compress, decompress as sync_decompress
from functools import wraps
import time
from aiocache import caches, cached
from aiocache.serializers import JsonSerializer
from asyncpg.exceptions import PostgresError
import redis.asyncio as redis
import logging

logging.basicConfig(level=logging.INFO)
def handle_exception(loop, context):
    msg = context.get("exception", context["message"])
    logging.error(f"[UNHANDLED] {msg}", exc_info=True)

loop = asyncio.get_event_loop()
loop.set_exception_handler(handle_exception)

redis_client = redis.Redis(host='localhost', port=6379, db=0)
caches.set_config({'default': {'cache': "aiocache.SimpleMemoryCache", 'serializer': {'class': JsonSerializer}}})
app = FastAPI(docs_url=None)
request_counts = {}

with open('/root/heist-v3/heist/apis/self/config.json', 'r') as file:
    cfg_file = json.load(file)

tokens = cfg_file["tokens"]
RETENTION = 336
API_KEYS = ["GuestPhoenixBot4933"]
api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)
aiohttp_session = None

async def get_api_key(api_key: str = Depends(api_key_header), request: Request = None):
    if request and request.client.host in ["127.0.0.1", "localhost", "::1"]:
        return True
    if api_key in API_KEYS:
        return True
    raise HTTPException(status_code=403, detail="Invalid API Key")

XSuperProperties = {
    "os": "Windows",
    "browser": "Firefox",
    "device": "",
    "system_locale": "en-US",
    "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "browser_version": "123.0",
    "os_version": "10",
    "referrer": "https://www.google.com/search?q=discord",
    "referring_domain": "google.com",
    "referrer_current": "",
    "referring_domain_current": "",
    "release_channel": "stable",
    "client_build_number": 284422,
    "client_event_source": "null"
}

async def compress_async(data: str):
    return await sync_compress(data) if asyncio.iscoroutinefunction(sync_compress) else sync_compress(data)

async def decompress_async(data: bytes):
    return await sync_decompress(data) if asyncio.iscoroutinefunction(sync_decompress) else sync_decompress(data)

@app.middleware("http")
async def log_requests(request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    print(f"{request.method} {request.url.path} took {duration:.3f}s")
    return response

@app.on_event("startup")
async def startup_event():
    global aiohttp_session
    aiohttp_session = aiohttp.ClientSession()

@app.on_event("shutdown")
async def shutdown_event():
    global aiohttp_session
    if aiohttp_session:
        await aiohttp_session.close()

async def fetch_data(url, token):
    async with aiohttp_session.get(
        url,
        headers={
            "Accept": "*/*",
            "Accept-Language": "en-US",
            "Authorization": f"{token}",
            "X-Super-Properties": json.dumps(XSuperProperties),
            "X-Discord-Locale": "en",
            "Connection": "keep-alive",
            "Referer": "https://discord.com/channels/@me",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "TE": "trailers",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        },
        proxy="http://avxnhvsd-rotate:8oulnn82723ng@p.webshare.io:80",
    ) as response:
        return await response.json()

async def fetch_data_np(url, token):
    async with aiohttp_session.get(
        url,
        headers={
            "Accept": "*/*",
            "Accept-Language": "en-US",
            "Authorization": f"{token}",
            "X-Super-Properties": json.dumps(XSuperProperties),
            "X-Discord-Locale": "en",
            "Connection": "keep-alive",
            "Referer": "https://discord.com/channels/@me",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "TE": "trailers",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        },
    ) as response:
        return await response.json()

@cached(ttl=604800)
async def get_guild(id, token):
    try:
        url = f"https://discord.com/api/v9/guilds/{id}"
        return await fetch_data_np(url, token)
    except Exception as e:
        if isinstance(e, HTTPException) and e.status in [403, 429]:
            return await fetch_data(id, token)
        else:
            print(e)

@cached(ttl=86400)
async def get_channel_name(guild_id, channel_id, token):
    try:
        url = f"https://discord.com/api/v9/guilds/{guild_id}/channels"
        channels = await fetch_data_np(url, token)
        if channels:
            for channel in channels:
                if str(channel["id"]) == channel_id:
                    return channel.get("name", "Unknown Channel")
        return "Unknown Channel"
    except Exception:
        return "Unknown Channel"

@cached(ttl=3600)
async def get_user(id, token):
    try:
        url = f"https://discord.com/api/v9/users/{id}/profile"
        return await fetch_data_np(url, token)
    except Exception as e:
        if isinstance(e, HTTPException) and e.status in [403, 429]:
            return await fetch_data_np(id, token)
        else:
            print(e)

@cached(ttl=1200)
async def get_guilds(token):
    try:
        url = "https://discord.com/api/v9/users/@me/guilds"
        return await fetch_data_np(url, token)
    except Exception as e:
        print(e)

@app.get("/content/{user_id}/outbox")
@cached(ttl=15)
async def get_content_inventory(user_id: str, request: Request, api_key: bool = Depends(get_api_key)):
    try:
        tasks = [fetch_data(f"https://discord.com/api/v9/content-inventory/users/{user_id}/outbox", token) for token in tokens]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, dict) and "message" not in result:
                return result
        return {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users/{id}")
@cached(ttl=1200)
async def get_user_endpoint(id: int, request: Request, api_key: bool = Depends(get_api_key)):
    try:
        tasks = [get_user(id, token) for token in tokens]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, dict) and "message" not in result:
                return result
        return {}
    except Exception as e:
        print(e)

@app.get("/users/lastseen/{user_id}")
async def get_last_seen(user_id: str, request: Request, api_key: bool = Depends(get_api_key)):
    try:
        last_seen = await redis_client.get(f'last_seen_users:{user_id}')
        if not last_seen:
            return {}
        return json.loads(last_seen)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/users/vcstate/{user_id}")
async def get_voice_state(user_id: str, request: Request, api_key: bool = Depends(get_api_key)):
    try:
        vc_state = await redis_client.get(f'vc_state:{user_id}')
        if not vc_state:
            return {}
        return json.loads(vc_state)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")

@cached(ttl=1200)
@app.get("/mutualguilds/{user_id}")
async def get_mutual_guilds_endpoint(user_id: int, api_key: bool = Depends(get_api_key)):
    try:
        tasks = [get_mutual_guilds(user_id, token) for token in tokens]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        mutual_guilds = []
        for result in results:
            if isinstance(result, Exception):
                continue
            if isinstance(result, list):
                mutual_guilds.extend(result)
        unique_guilds = [dict(t) for t in {tuple(guild.items()) for guild in mutual_guilds}]
        return unique_guilds
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@cached(ttl=1200)
async def get_mutual_guilds(user_id, token):
    user_profile = await get_user(user_id, token)
    mutual_guilds = user_profile.get("mutual_guilds", [])
    tasks = [get_guild(guild["id"], token) for guild in mutual_guilds]
    guild_details = await asyncio.gather(*tasks)
    guild_details = [guild_info for guild_info in guild_details if isinstance(guild_info, dict) and 'id' in guild_info]
    guild_details = [{"id": guild_info["id"], "name": guild_info["name"], "vanity_url": guild_info.get("vanity_url_code", "")} for guild_info in guild_details]
    return guild_details

@app.get("/messages/exists/{user_id}")
@cached(ttl=10)
async def check_messages_exist(user_id: str, api_key: bool = Depends(get_api_key)):
    async with get_db_connection() as conn:
        exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM messages WHERE user_id = $1 LIMIT 1)", user_id)
        return {"exists": exists}

@app.get("/messages")
async def get_messages(user_id: str, limit: int = None, keyword: str = None, content_only: bool = False, attachments_only: bool = False, api_key: bool = Depends(get_api_key)):
    query = "SELECT content, is_compressed, guild_name, vanity_url, timestamp FROM messages WHERE user_id = $1"
    params = [user_id]
    if keyword:
        query += " AND content LIKE $2"
        params.append(f"%{keyword}%")
    query += " ORDER BY timestamp DESC"
    if limit is not None:
        query += " LIMIT $3"
        params.append(limit)
    async with get_db_connection() as conn:
        records = await conn.fetch(query, *params)
        messages = []
        for r in records:
            try:
                if r["is_compressed"]:
                    content = await decompress_async(r["content"])
                else:
                    content = r["content"].decode('utf-8')
                if attachments_only and "https://cdn.discordapp.com" not in content:
                    continue
                if content_only and "https://cdn.discordapp.com" in content:
                    continue
                messages.append({"content": content, "guild_name": r["guild_name"], "vanity_url": r["vanity_url"], "timestamp": r["timestamp"].isoformat()})
            except Exception as e:
                print(f"Error decoding message: {e}")
                continue
        return messages

@app.get("/guilds/{guild_id}")
async def get_guild_info_endpoint(guild_id: int, api_key: bool = Depends(get_api_key)):
    try:
        tasks = [get_guild(guild_id, token) for token in tokens]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, dict) and "name" in result:
                return {"id": result.get("id"), "name": result.get("name"), "vanity_url": result.get("vanity_url_code", None)}
        return {"error": "Guild not found or inaccessible"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def handle_last_seen(data, token):
    if data.get('author', {}).get('bot'):
        return
    try:
        user_id = str(data["author"]["id"])
        guild_id = str(data["guild_id"])
        channel_id = str(data["channel_id"])
        guild_info = await get_guild(guild_id, token)
        guild_name = guild_info.get("name", "Unknown Guild")
        channel_name = await get_channel_name(guild_id, channel_id, token)
        last_seen_data = {'guild_name': guild_name, 'channel_name': channel_name, 'timestamp': int(datetime.now(UTC).timestamp())}
        key = f'last_seen_users:{user_id}'
        await redis_client.setex(key, 24 * 60 * 60, json.dumps(last_seen_data))
        event_data = {"type": "message", "user_id": user_id, "guild_id": guild_id, "guild_name": guild_name, "channel_id": channel_id, "channel_name": channel_name}
        await redis_client.publish('user_activity', json.dumps(event_data))
    except Exception as e:
        print(f"Error updating last seen: {e}")

async def handle_voice_state(data, token):
    try:
        user_id = str(data["user_id"])
        channel_id = data.get("channel_id")
        vc_key = f'vc_state:{user_id}'
        prev_vc_data_str = await redis_client.get(vc_key)
        prev_vc_data = json.loads(prev_vc_data_str) if prev_vc_data_str else None
        prev_channel_id = prev_vc_data.get("channel_id") if prev_vc_data else None
        if channel_id:
            guild_info = await get_guild(data["guild_id"], token)
            guild_name = guild_info.get("name", "Unknown Guild")
            channel_name = await get_channel_name(data["guild_id"], channel_id, token)
            vc_data = {"channel_id": channel_id, "guild_id": data["guild_id"], "guild_name": guild_name, "channel_name": channel_name, "self_deaf": data.get("self_deaf", False), "self_mute": data.get("self_mute", False), "deaf": data.get("deaf", False), "mute": data.get("mute", False), "timestamp": int(datetime.now(UTC).timestamp())}
            await redis_client.setex(vc_key, 24 * 60 * 60, json.dumps(vc_data))
            if prev_channel_id and prev_channel_id != channel_id:
                prev_channel_name = await get_channel_name(data["guild_id"], prev_channel_id, token)
                event_data = {"type": "voice_switch", "user_id": user_id, "guild_name": guild_name, "old_channel_name": prev_channel_name, "channel_id": channel_id, "channel_name": channel_name}
            else:
                event_data = {"type": "voice_join", "user_id": user_id, "guild_name": guild_name, "channel_id": channel_id, "channel_name": channel_name}
        else:
            if prev_channel_id:
                guild_info = await get_guild(data["guild_id"], token)
                guild_name = guild_info.get("name", "Unknown Guild")
                prev_channel_name = await get_channel_name(data["guild_id"], prev_channel_id, token)
                event_data = {"type": "voice_leave", "user_id": user_id, "guild_name": guild_name, "channel_id": channel_id, "channel_name": prev_channel_name}
                await redis_client.delete(vc_key)
            else:
                return
        await redis_client.publish('user_activity', json.dumps(event_data))
    except Exception as e:
        print(f"Error updating voice state: {e}")

async def handle_message_create(data, token):
    if data.get('author', {}).get('bot'):
        return
    try:
        user_id = data["author"]["id"]
        guild_id = data["guild_id"]
        channel_id = data["channel_id"]
        raw_content = data["content"]
        if "attachments" in data and data["attachments"]:
            attachment_urls = "\n".join([attachment["url"] for attachment in data["attachments"]])
            raw_content = f"{raw_content}\n{attachment_urls}" if raw_content else attachment_urls
        content = raw_content[:500] + ("..." if len(raw_content) > 500 else "")
        timestamp = datetime.fromisoformat(data["timestamp"].rstrip('Z')).replace(tzinfo=None)
        guild_info = await get_guild(guild_id, token) if token else None
        guild_name = guild_info.get("name", "Unknown Guild") if guild_info else "Unknown Guild"
        vanity_url = guild_info.get("vanity_url_code", "") if guild_info else ""
        should_compress = len(content) > 200
        stored_content = await compress_async(content) if should_compress else content.encode('utf-8')
        async with get_db_connection() as conn:
            await conn.execute(
                '''
                INSERT INTO messages 
                (user_id, guild_id, guild_name, vanity_url, channel_id, content, is_compressed, timestamp) 
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (user_id, guild_id, content, timestamp) DO NOTHING
                ''',
                user_id, guild_id, guild_name, vanity_url, channel_id, stored_content, should_compress, timestamp
            )
    except Exception as e:
        print(f"Error handling message: {e}")

async def delete_old_messages():
    async with get_db_connection() as conn:
        try:
            cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=RETENTION)
            total_deleted = 0
            while True:
                result = await conn.execute(
                    '''
                    DELETE FROM messages
                    WHERE ctid IN (
                        SELECT ctid FROM messages
                        WHERE timestamp < $1
                        LIMIT 10000
                    )
                    ''',
                    cutoff
                )
                deleted_count = int(result.split()[-1])
                total_deleted += deleted_count
                if deleted_count < 10000:
                    break
                await asyncio.sleep(0)
            print(f"Deleted {total_deleted} old messages.")
        except PostgresError as e:
            print(f"Database error occurred while deleting old messages: {e}")

async def periodic_cleanup(interval: int):
    while True:
        await delete_old_messages()
        await asyncio.sleep(interval)

async def connect_to_gateway(token):
    uri = "wss://gateway.discord.gg/?v=9&encoding=json"
    while True:
        try:
            async with websockets.connect(uri, ping_interval=30, ping_timeout=10, max_size=None) as websocket:
                await websocket.send(json.dumps({"op": 2, "d": {"token": token, "properties": {"$os": "Discord iOS", "$browser": "Discord iOS", "$device": "iOS"}}}))
                guilds = await get_guilds(token)
                for guild in guilds or []:
                    await websocket.send(json.dumps({"op": 14, "d": {"guild_id": guild["id"], "typing": True, "threads": True, "activities": False}}))
                async for event_data in websocket:
                    try:
                        event = json.loads(event_data)
                        if event["op"] == 10:
                            heartbeat_interval = event["d"]["heartbeat_interval"] / 1000
                            asyncio.create_task(send_heartbeat(websocket, heartbeat_interval))
                        elif event["op"] == 0:
                            if event["t"] == "MESSAGE_CREATE":
                                await handle_last_seen(event["d"], token)
                                await handle_message_create(event["d"], token)
                            elif event["t"] == "VOICE_STATE_UPDATE":
                                await handle_voice_state(event["d"], token)
                    except Exception as e:
                        print(f"Error processing event for token {token}: {e}")
        except websockets.exceptions.ConnectionClosed:
            await asyncio.sleep(5)
        except Exception as e:
            logging.error(f"Gateway error for token: {e}", exc_info=True)
            await asyncio.sleep(10)

async def send_heartbeat(websocket, interval):
    while True:
        try:
            await asyncio.sleep(interval)
            await websocket.send(json.dumps({"op": 1, "d": None}))
        except websockets.exceptions.ConnectionClosed:
            break

async def watchdog():
    while True:
        await asyncio.sleep(60)
        logging.info("watchdog %s", datetime.now(UTC).isoformat())

async def safe_task(func, *args):
    while True:
        try:
            await func(*args)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.error(f"[safe_task] {func.__name__} crashed: {e}", exc_info=True)
            await asyncio.sleep(5)

async def run_async():
    asyncio.create_task(periodic_cleanup(43200))
    asyncio.create_task(watchdog())
    tasks = [safe_task(connect_to_gateway, token) for token in tokens]
    await asyncio.gather(*tasks)

async def start_server():
    config = uvicorn.Config(app, host="0.0.0.0", port=8002, log_level="info")
    server = uvicorn.Server(config)
    asyncio.create_task(server.serve())
    await asyncio.sleep(1)

async def main():
    try:
        await start_server()
        await run_async()
    except Exception as e:
        logging.exception(f"[FATAL] Main crashed: {e}")

if __name__ == "__main__":
    asyncio.run(main())