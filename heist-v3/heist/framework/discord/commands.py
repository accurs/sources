from typing import Dict, Optional, List, Any
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import time
import discord
import secrets
import aiohttp
import asyncio
from cashews import cache

bot_start_time = time.time()

RATE_LIMIT = 20
WINDOW = 10

LOCAL_IPS = {"127.0.0.1", "::1", "0.0.0.0", "localhost"}

class CommandCache:
    _commands: Dict[str, int] = {}
    _detailed_cache: List[Dict[str, Any]] = []
    
    @classmethod
    async def load_commands(cls, bot) -> None:
        commands = await bot.tree.fetch_commands()
        cls._commands = {}
        cls._detailed_cache = []
        
        def process_command(cmd, parent_name="", parent_id=None):
            full_name = f"{parent_name} {cmd.name}".strip()
            cmd_id = getattr(cmd, 'id', parent_id)
            
            if cmd_id:
                cls._commands[full_name] = cmd_id
                
                cmd_type = getattr(cmd, 'type', discord.AppCommandType.chat_input)
                if not parent_name and cmd_type != discord.AppCommandType.chat_input:
                    return
                
                is_hybrid = hasattr(bot.get_command(cmd.name.split()[-1]), 'callback') if bot.get_command(cmd.name.split()[-1]) else False
                
                cog_name = "Unknown"
                cmd_name_parts = full_name.split()
                base_cmd_name = cmd_name_parts[0] if cmd_name_parts else full_name
                
                for cog_name_key, cog in bot.cogs.items():
                    try:
                        for app_cmd in cog.get_app_commands():
                            if (hasattr(app_cmd, 'name') and app_cmd.name == base_cmd_name) or \
                               (hasattr(app_cmd, 'qualified_name') and base_cmd_name in app_cmd.qualified_name):
                                cog_name = cog.__class__.__name__
                                break
                        if cog_name != "Unknown":
                            break
                    except:
                        continue
                
                is_group = hasattr(cmd, 'options') and any(
                    option.type in [discord.AppCommandOptionType.subcommand, discord.AppCommandOptionType.subcommand_group]
                    for option in cmd.options
                )
                
                arguments = []
                if hasattr(cmd, 'options'):
                    for option in cmd.options:
                        if option.type not in [discord.AppCommandOptionType.subcommand, discord.AppCommandOptionType.subcommand_group]:
                            arg_data = {
                                "name": option.name,
                                "description": getattr(option, 'description', ''),
                                "type": option.type.name,
                                "required": getattr(option, 'required', True),
                                "choices": [choice.name for choice in getattr(option, 'choices', [])]
                            }
                            arguments.append(arg_data)
                
                cmd_data = {
                    "name": full_name,
                    "id": cmd_id,
                    "description": getattr(cmd, 'description', ''),
                    "type": cmd_type.name if hasattr(cmd_type, 'name') else 'chat_input',
                    "command_type": "ctx" if is_hybrid else "interaction",
                    "mention": f"</{full_name}:{cmd_id}>",
                    "is_hybrid": is_hybrid,
                    "is_group": is_group,
                    "cog": cog_name,
                    "arguments": arguments
                }
                cls._detailed_cache.append(cmd_data)
            
            if hasattr(cmd, 'options'):
                for option in cmd.options:
                    if option.type == discord.AppCommandOptionType.subcommand_group:
                        if hasattr(option, 'options'):
                            for sub_option in option.options:
                                process_command(sub_option, f"{full_name} {option.name}", cmd_id)
                    elif option.type == discord.AppCommandOptionType.subcommand:
                        process_command(option, full_name, cmd_id)
        
        for cmd in commands:
            process_command(cmd, "", getattr(cmd, 'id', None))
        
        await bot.redis.set("command_cache", cls._commands, ex=3600)
        await bot.redis.set("detailed_command_cache", cls._detailed_cache, ex=3600)
    
    @classmethod
    async def get_command_id(cls, bot, name: str) -> Optional[int]:
        if not cls._commands:
            cached = await bot.redis.get("command_cache")
            if cached:
                cls._commands = cached
            else:
                await cls.load_commands(bot)
        return cls._commands.get(name)
    
    @classmethod
    async def get_mention(cls, bot, name: str) -> str:
        command_id = await cls.get_command_id(bot, name)
        return f"</{name}:{command_id}>" if command_id else f"`/{name}`"
    
    @classmethod
    async def get_all_commands(cls, bot) -> List[Dict[str, Any]]:
        if not cls._detailed_cache:
            cached = await bot.redis.get("detailed_command_cache")
            if cached:
                cls._detailed_cache = cached
            else:
                await cls.load_commands(bot)
        return cls._detailed_cache

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class OAuthRequest(BaseModel):
    code: str
    redirect_uri: str

class LoginResponse(BaseModel):
    success: bool
    message: str
    user_data: Optional[Dict] = None
    auth_token: Optional[str] = None
    is_famous: Optional[bool] = None
    is_donor: Optional[bool] = None

bot_instance = None

def get_bot():
    return bot_instance

async def api_register_user(bot, discord_id: int, username: str, displayname: str) -> None:
    redis_key = f"user:{discord_id}:exists"
    user_exists_in_cache = await bot.redis.get(redis_key)
    if not user_exists_in_cache:
        async with bot.pool.acquire() as conn:
            user_exists = await conn.fetchval("SELECT 1 FROM user_data WHERE user_id = $1", str(discord_id))
            if not user_exists:
                await conn.execute("""
                    INSERT INTO user_data (user_id, username, displayname)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id) DO NOTHING
                """, str(discord_id), username, displayname)
                await bot.redis.set(f"user:{discord_id}:limited", '', ex=7 * 24 * 60 * 60)
                await bot.redis.set(f"user:{discord_id}:untrusted", '', ex=60 * 24 * 60 * 60)
                await bot.redis.set(redis_key, '1', ex=600)

@cache(ttl="3h", key="blacklist:{object_id}:{object_type}")
async def api_check_blacklisted(bot, object_id: int, object_type: str = "user") -> bool:
    if object_type == "user":
        query = "SELECT 1 FROM blacklist WHERE user_id = $1"
        return bool(await bot.pool.fetchval(query, object_id))
    elif object_type == "guild":
        query = "SELECT 1 FROM guildblacklist WHERE guild_id = $1"
        return bool(await bot.pool.fetchval(query, object_id))
    else:
        query = "SELECT 1 FROM blacklists WHERE object_id = $1 AND object_type = $2"
        return bool(await bot.pool.fetchval(query, object_id, object_type))

async def api_check_famous(bot, user_id: int) -> bool:
    redis_key = f"famous:{user_id}"
    cached = await bot.redis.get(redis_key)
    if isinstance(cached, bytes):
        cached = cached.decode()
    if cached is not None:
        return cached == "True"
    async with bot.pool.acquire() as conn:
        result = await conn.fetchval("SELECT fame FROM user_data WHERE user_id = $1", str(user_id))
        is_famous = bool(result)
        await bot.redis.set(redis_key, str(is_famous), ex=300)
        return is_famous

async def api_check_donor(bot, user_id: int) -> bool:
    redis_key = f"donor:{user_id}"
    try:
        cached = await bot.redis.get(redis_key)
        if isinstance(cached, bytes):
            cached = cached.decode()
    except Exception:
        cached = None
    if cached is not None:
        return cached == "True"
    try:
        async with bot.pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1 FROM donors WHERE user_id = $1", str(user_id))
    except Exception:
        return False
    is_donor = bool(result)
    await bot.redis.set(redis_key, str(is_donor), ex=300)
    return is_donor

async def verify_auth_token(token: str, bot=Depends(get_bot)) -> Optional[int]:
    if not bot or not token:
        return None
    user_id = await bot.redis.get(f"auth_token:{token}")
    return int(user_id) if user_id else None

async def push_latency_point(bot):
    key = "status:latency_points"
    latency = round(bot.latency * 1000) if bot.latency else -1
    ts = time.strftime("%H:%M")
    point = {"time": ts, "latency": latency}
    await bot.redis.lpush(key, str(point))
    await bot.redis.ltrim(key, 0, 23)

def get_shard_data(bot):
    if not hasattr(bot, "shards") or not bot.shards:
        total_servers = len(bot.guilds)
        total_users = sum(g.member_count for g in bot.guilds)
        latency = round(bot.latency * 1000) if bot.latency else -1
        return [{
            "id": 0,
            "name": "Main Shard",
            "status": "online",
            "servers": total_servers,
            "users": total_users,
            "latency": latency
        }]
    shards = []
    for shard_id, shard in bot.shards.items():
        servers = sum(1 for g in bot.guilds if g.shard_id == shard_id)
        users = sum(g.member_count for g in bot.guilds if g.shard_id == shard_id)
        latency = round(shard.latency * 1000) if shard.latency else -1
        shards.append({
            "id": shard_id,
            "name": f"Shard {shard_id}",
            "status": "online",
            "servers": servers,
            "users": users,
            "latency": latency
        })
    return shards

@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    client_ip = request.client.host

    if client_ip in LOCAL_IPS:
        return await call_next(request)

    key = f"ratelimit:{client_ip}"
    current = await bot_instance.redis.get(key)

    if current:
        current = int(current)
        if current >= RATE_LIMIT:
            return JSONResponse(
                status_code=429,
                content={"success": False, "message": "Rate limit exceeded"}
            )
        await bot_instance.redis.incr(key)
    else:
        await bot_instance.redis.set(key, 1, ex=WINDOW)

    return await call_next(request)

@app.get("/api/commands")
async def get_commands():
    return {"commands": CommandCache._detailed_cache}

@app.get("/api/commands/{command_name}")
async def get_command(command_name: str):
    for cmd in CommandCache._detailed_cache:
        if cmd["name"] == command_name:
            return cmd
    return {"error": "Command not found"}

@app.get("/api/commands/search/{query}")
async def search_commands(query: str):
    results = [cmd for cmd in CommandCache._detailed_cache if query.lower() in cmd["name"].lower()]
    return {"results": results}

@app.get("/api/oauth/url")
async def get_oauth_url():
    return {
        "url": "https://discord.com/api/oauth2/authorize?client_id=1391912800443564112&redirect_uri=http%3A%2F%2Flocalhost%3A4323%2Fapi%2Foauth%2Fcallback&response_type=code&scope=identify"
    }

@app.post("/api/oauth/login")
async def oauth_login(request: OAuthRequest, bot=Depends(get_bot)) -> LoginResponse:
    if not bot:
        raise HTTPException(status_code=500, detail="Bot not available")
    
    try:
        async with aiohttp.ClientSession() as session:
            token_data = {
                'client_id': '1391912800443564112',
                'client_secret': bot.Configuration.authentication.discord_secret,
                'grant_type': 'authorization_code',
                'code': request.code,
                'redirect_uri': request.redirect_uri
            }
            
            async with session.post('https://discord.com/api/oauth2/token', data=token_data) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    return LoginResponse(success=False, message=f"Discord API error: {error_text}")
                token_response = await resp.json()
            
            headers = {'Authorization': f'Bearer {token_response["access_token"]}'}
            async with session.get('https://discord.com/api/users/@me', headers=headers) as resp:
                if resp.status != 200:
                    return LoginResponse(success=False, message="Failed to fetch user data")
                discord_user = await resp.json()
        
        user_id = int(discord_user['id'])
        username = discord_user['username']
        display_name = discord_user.get('display_name', username)
        
        if await api_check_blacklisted(bot, user_id):
            return LoginResponse(success=False, message="Account is blacklisted")
        
        await api_register_user(bot, user_id, username, display_name)
        
        async with bot.pool.acquire() as conn:
            user_data = await conn.fetchrow("SELECT * FROM user_data WHERE user_id = $1", str(user_id))
            if not user_data:
                return LoginResponse(success=False, message="Failed to retrieve user data")
        
        is_famous = await api_check_famous(bot, user_id)
        is_donor = await api_check_donor(bot, user_id)
        
        auth_token = secrets.token_urlsafe(32)
        await bot.redis.set(f"auth_token:{auth_token}", str(user_id), ex=86400 * 7)
        
        return LoginResponse(
            success=True,
            message="Login successful",
            user_data=dict(user_data),
            auth_token=auth_token,
            is_famous=is_famous,
            is_donor=is_donor
        )
    
    except Exception as e:
        return LoginResponse(success=False, message=f"Login failed: {str(e)}")

@app.get("/api/auth/validate")
async def validate_token(token: str, bot=Depends(get_bot)):
    user_id = await verify_auth_token(token, bot)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    async with bot.pool.acquire() as conn:
        user_data = await conn.fetchrow("SELECT * FROM user_data WHERE user_id = $1", str(user_id))
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
    
    return {"valid": True, "user_id": user_id, "user_data": dict(user_data)}

@app.get("/api/oauth/callback")
async def oauth_callback(code: str, state: str = None, bot=Depends(get_bot)):
    if not bot:
        raise HTTPException(status_code=500, detail="Bot not available")
    
    try:
        async with aiohttp.ClientSession() as session:
            token_data = {
                'client_id': '1391912800443564112',
                'client_secret': bot.Configuration.authentication.discord_secret,
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': 'http://localhost:4323/api/oauth/callback'
            }
            
            async with session.post('https://discord.com/api/oauth2/token', data=token_data) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise HTTPException(status_code=400, detail=f"Discord API error: {error_text}")
                token_response = await resp.json()
            
            headers = {'Authorization': f'Bearer {token_response["access_token"]}'}
            async with session.get('https://discord.com/api/users/@me', headers=headers) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=400, detail="Failed to fetch user data")
                discord_user = await resp.json()
        
        user_id = int(discord_user['id'])
        username = discord_user['username']
        display_name = discord_user.get('display_name', username)
        
        if await api_check_blacklisted(bot, user_id):
            raise HTTPException(status_code=403, detail="Account is blacklisted")
        
        await api_register_user(bot, user_id, username, display_name)
        
        async with bot.pool.acquire() as conn:
            user_data = await conn.fetchrow("SELECT * FROM user_data WHERE user_id = $1", str(user_id))
        
        is_famous = await api_check_famous(bot, user_id)
        is_donor = await api_check_donor(bot, user_id)
        
        auth_token = secrets.token_urlsafe(32)
        await bot.redis.set(f"auth_token:{auth_token}", str(user_id), ex=86400 * 7)
        
        return {
            "success": True,
            "auth_token": auth_token,
            "user_data": dict(user_data) if user_data else None,
            "is_famous": is_famous,
            "is_donor": is_donor
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

async def latency_loop(bot):
    await bot.wait_until_ready()
    while not bot.is_closed():
        await push_latency_point(bot)
        await asyncio.sleep(3600)

@app.get("/api/status")
async def api_status():
    bot = bot_instance
    if not bot:
        raise HTTPException(status_code=503, detail="Bot unavailable")

    uptime = int(time.time() - bot_start_time)
    latency = round(bot.latency * 1000, 1) if bot.latency else -1
    total_servers = len(bot.guilds)
    total_users = sum(g.member_count for g in bot.guilds)

    shards = get_shard_data(bot)

    raw = await bot.redis.lrange("status:latency_points", 0, -1)
    chart = []
    for item in reversed(raw):
        if isinstance(item, bytes):
            item = item.decode()
        try:
            chart.append(eval(item))
        except:
            continue

    return {
        "status": "ok",
        "botId": str(bot.user.id),
        "overallStatus": "online",
        "uptime": uptime,
        "avgLatency": latency,
        "totalServers": total_servers,
        "totalUsers": total_users,
        "shards": shards,
        "chartData": chart,
        "lastUpdated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "startTime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(bot_start_time))
    }


async def start_api():
    import uvicorn
    config = uvicorn.Config(app, host="0.0.0.0", port=4323)
    server = uvicorn.Server(config)
    await server.serve()

def set_bot_instance(bot):
    global bot_instance
    bot_instance = bot

__all__ = ('CommandCache', 'app', 'start_api', 'set_bot_instance')