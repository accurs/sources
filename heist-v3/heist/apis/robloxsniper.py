import aiohttp
import asyncio
import json
import io
import time
import os, sys
import ssl
from PIL import Image
import imagehash
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn
from dotenv import load_dotenv
import contextlib

CDN_ONLY = True

load_dotenv("/root/heist-v3/heist/.env")

PROXY = f"http://{os.getenv('PROXY', '')}"
LOOPS = 120
MAXPBATCH = 12
MAXHASH = 250

SNIPE_LIMIT = 2
snipe_semaphore = asyncio.Semaphore(SNIPE_LIMIT)
snipe_queue = []
active_users = set()

_original_path = sys.path.copy()
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append("/root/heist-v3")
from heist.framework.tools.robloxget import get_cookie
sys.path = _original_path

def dprint(*a):
    print("[DEBUG]", *a, flush=True)

class Client:
    def __init__(self, proxy):
        self.proxy = proxy
        self.session = None
        self.csrf_token = None

    async def sesh(self):
        if self.session is None or self.session.closed:
            dprint("create_session")
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(limit=3000, ssl=ssl_ctx, keepalive_timeout=10)
            self.session = aiohttp.ClientSession(connector=connector)

    async def req(self, method, url, use_csrf=False, **kw):
        await self.sesh()
        h = {
            "User-Agent": "BaszuckiLikesKids/5.0",
            "Cookie": f".ROBLOSECURITY={get_cookie()}"
        }
        if use_csrf and self.csrf_token:
            h["x-csrf-token"] = self.csrf_token
        extra = kw.pop("headers", None)
        if extra:
            h.update(extra)
        for attempt in range(10):
            try:
                dprint("REQ", method, url, "attempt", attempt + 1)
                async with self.session.request(method, url, proxy=self.proxy, timeout=20, headers=h, **kw) as r:
                    if use_csrf and r.status == 403 and "x-csrf-token" in r.headers:
                        dprint("csrf_refresh")
                        self.csrf_token = r.headers["x-csrf-token"]
                        h["x-csrf-token"] = self.csrf_token
                        continue
                    try:
                        js = await r.json()
                        dprint("resp_ok")
                        return js
                    except:
                        dprint("json_err")
                        return None
            except:
                dprint("req_err")
                continue
        dprint("req_fail")
        return None

client = Client(PROXY)
app = FastAPI()

async def get_uid(username):
    dprint("get_uid", username)
    r = await client.req("POST", "https://users.roblox.com/v1/usernames/users", json={"usernames": [username]})
    try:
        return r["data"][0]["id"]
    except:
        return None

async def get_avatar(uid):
    dprint("get_avatar", uid)
    r = await client.req("GET", f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={uid}&size=150x150&format=png")
    try:
        return r["data"][0]["imageUrl"]
    except:
        return None

async def get_universe_id(pid):
    dprint("get_universe_id", pid)
    r = await client.req("GET", f"https://apis.roblox.com/universes/v1/places/{pid}/universe")
    try:
        return r["universeId"]
    except:
        return None

async def get_game_info(universe_id):
    dprint("get_game_info", universe_id)
    r = await client.req("GET", f"https://games.roblox.com/v1/games?universeIds={universe_id}")
    try:
        return r["data"][0]["name"]
    except:
        return "Unknown"

async def get_game_thumbnail(universe_id):
    dprint("get_game_thumbnail", universe_id)
    r = await client.req("GET", f"https://thumbnails.roblox.com/v1/games/icons?universeIds={universe_id}&size=150x150&format=Png&isCircular=false")
    try:
        return r["data"][0]["imageUrl"]
    except:
        return None

async def fetch_page(pid, cursor=None):
    if cursor:
        url = f"https://games.roblox.com/v1/games/{pid}/servers/Public?cursor={cursor}"
    else:
        url = f"https://games.roblox.com/v1/games/{pid}/servers/Public"
    dprint("fetch_page", url)
    r = await client.req("GET", url)
    return r

async def download_image(url):
    dprint("download", url)
    for _ in range(10):
        try:
            await client.sesh()
            async with client.session.get(url, proxy=client.proxy, timeout=8) as r:
                raw = await r.read()
                return raw
        except Exception as e:
            dprint("download_err", e)
            await asyncio.sleep(0.02)
    return None

async def fast_hash_bytes(b):
    if CDN_ONLY:
        return None
    try:
        im = Image.open(io.BytesIO(b)).convert("RGB").resize((32, 32))
        h = imagehash.average_hash(im)
        dprint("fast_hash_ok", str(h))
        return h
    except Exception as e:
        dprint("fast_hash_fail", e)
        return None

async def full_hash_bytes(b):
    if CDN_ONLY:
        return None
    try:
        im = Image.open(io.BytesIO(b)).convert("RGB")
        h = imagehash.average_hash(im)
        dprint("full_hash_ok", str(h))
        return h
    except Exception as e:
        dprint("full_hash_fail", e)
        return None

async def batch(tokens):
    dprint("batch_tokens", len(tokens))
    chunks = []
    for i in range(0, len(tokens), 100):
        req = []
        for t in tokens[i:i+100]:
            req.append({
                "requestId": f"0:{t}:AvatarHeadshot:150x150:png:regular",
                "type": "AvatarHeadShot",
                "targetId": 0,
                "token": t,
                "format": "png",
                "size": "150x150"
            })
        chunks.append(req)
    sem = asyncio.Semaphore(MAXPBATCH)
    async def do(req):
        async with sem:
            for _ in range(10):
                r = await client.req("POST", "https://thumbnails.roblox.com/v1/batch", json=req)
                if r and "data" in r:
                    dprint("batch_ok")
                    return r["data"]
                r = await client.req("POST", "https://thumbnails.roproxy.com/v1/batch", json=req)
                if r and "data" in r:
                    dprint("batch_proxy_ok")
                    return r["data"]
            dprint("batch_fail")
            return []
    tasks = [asyncio.create_task(do(c)) for c in chunks]
    out = []
    for t in asyncio.as_completed(tasks):
        r = await t
        if r:
            out.extend(r)
    return out

async def scan_once(pid, target_fast, target_full, avatar_cdn=None):
    dprint("scan_once", pid)
    cursor = None
    servers = []
    while True:
        r = await fetch_page(pid, cursor)
        if not r:
            break
        d = r.get("data", [])
        if not d:
            break
        servers.extend(d)
        cursor = r.get("nextPageCursor")
        if not cursor:
            break
    dprint("servers", len(servers))
    token_map = {}
    all_tokens = []
    for s in servers:
        pts = s.get("playerTokens", [])
        for t in pts:
            all_tokens.append(t)
            if t not in token_map:
                token_map[t] = []
            token_map[t].append(s)
    dprint("total_tokens", len(all_tokens))
    if not all_tokens:
        return None
    thumbs = await batch(all_tokens)
    dprint("thumbs", len(thumbs))
    sem = asyncio.Semaphore(MAXHASH)
    async def process(ent):
        async with sem:
            u = ent.get("imageUrl")
            if not u:
                return None
            if CDN_ONLY:
                if u == avatar_cdn:
                    tok = ent["requestId"].split(":")[1]
                    sv = token_map.get(tok, [])
                    if sv:
                        dprint("cdn_match", tok)
                        return {"server": sv[0], "token": tok}
                return None
            b = await download_image(u)
            if not b:
                return None
            h1 = await fast_hash_bytes(b)
            if h1 is None:
                return None
            if target_fast - h1 <= 1:
                h2 = await full_hash_bytes(b)
                if h2 and target_full - h2 <= 2:
                    tok = ent["requestId"].split(":")[1]
                    sv = token_map.get(tok, [])
                    if sv:
                        dprint("match", tok)
                        return {"server": sv[0], "token": tok}
        return None
    tasks = [asyncio.create_task(process(ent)) for ent in thumbs]
    for t in asyncio.as_completed(tasks):
        r = await t
        if r:
            dprint("found_result")
            for other in tasks:
                if other is not t and not other.done():
                    other.cancel()
            return r
    dprint("no_match")
    return None

async def confirm_server(pid, token, server_id, websocket: WebSocket):
    dprint("confirm_server", server_id, token)
    cursor = None
    while True:
        with contextlib.suppress(Exception):
            await websocket.send_text(json.dumps({"status": "ping"}))
        r = await fetch_page(pid, cursor)
        if not r:
            return None
        sv = r.get("data", [])
        for s in sv:
            if s.get("id") == server_id:
                if token in s.get("playerTokens", []):
                    dprint("confirm_ok")
                    return s
                dprint("confirm_fail")
                return None
        cursor = r.get("nextPageCursor")
        if not cursor:
            return None

async def find_target(username, pid, loops, websocket: WebSocket):
    dprint("find_target", username, pid)
    uid = await get_uid(username)
    if not uid:
        await websocket.send_text(json.dumps({"status": "error", "message": "user_not_found"}))
        return
    avatar = await get_avatar(uid)
    if not avatar:
        await websocket.send_text(json.dumps({"status": "error", "message": "avatar_not_found"}))
        return
    universe_id = await get_universe_id(pid)
    if universe_id:
        game_data = await client.req("GET", f"https://games.roblox.com/v1/games?universeIds={universe_id}")
        try:
            playing = game_data["data"][0]["playing"]
        except:
            playing = 0
        if playing > 50000:
            await websocket.send_text(json.dumps({"status": "error", "message": "game_too_big"}))
            return
        game_name = game_data["data"][0]["name"]
        game_thumb = await get_game_thumbnail(universe_id)
    else:
        game_name = "Unknown"
        game_thumb = None
    dprint("avatar_url", avatar)
    target_fast = None
    target_full = None
    avatar_cdn = avatar
    if not CDN_ONLY:
        for _ in range(10):
            b = await download_image(avatar)
            if b:
                target_fast = await fast_hash_bytes(b)
                target_full = await full_hash_bytes(b)
                if target_fast and target_full:
                    break
        if target_fast is None or target_full is None:
            await websocket.send_text(json.dumps({"status": "error", "message": "hash_failed"}))
            return
    start = time.time()
    scans = 0
    for i in range(loops):
        scans = i + 1
        dprint("loop", scans)
        with contextlib.suppress(Exception):
            await websocket.send_text(json.dumps({"status": "ping"}))
        res = await scan_once(pid, target_fast, target_full, avatar_cdn)
        elapsed = round(time.time() - start, 3)
        if res:
            server = res["server"]
            token = res["token"]
            await websocket.send_text(json.dumps({
                "status": "found",
                "elapsed": elapsed,
                "scans": scans,
                "serverId": server["id"],
                "joinUrl": f"https://heist.lol/joiner?placeId={pid}&gameInstanceId={server['id']}",
                "gameName": game_name,
                "gameThumbnail": game_thumb,
                "gameUrl": f"https://www.roblox.com/games/{pid}/"
            }))
            return
    elapsed = round(time.time() - start, 3)
    await websocket.send_text(json.dumps({
        "status": "not_found",
        "elapsed": elapsed,
        "scans": scans,
        "gameName": game_name,
        "gameThumbnail": game_thumb,
        "gameUrl": f"https://www.roblox.com/games/{pid}/"
    }))

@app.on_event("shutdown")
async def shutdown_event():
    if client.session and not client.session.closed:
        await client.session.close()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    user_id = None
    try:
        raw = await websocket.receive_text()
        payload = json.loads(raw)
        username = payload.get("username")
        place_id = payload.get("placeId")
        loops = int(payload.get("loops", LOOPS))
        user_id = payload.get("userId")

        if user_id is not None:
            if user_id in active_users:
                await websocket.send_text(json.dumps({"status": "error", "message": "already_sniping"}))
                return
            active_users.add(user_id)

        snipe_queue.append(websocket)
        pos = len(snipe_queue)

        await websocket.send_text(json.dumps({
            "status": "queued",
            "position": pos
        }))

        while True:
            if snipe_queue and snipe_queue[0] is websocket:
                break
            await asyncio.sleep(0.3)

        async with snipe_semaphore:
            if websocket in snipe_queue:
                snipe_queue.remove(websocket)

            await websocket.send_text(json.dumps({"status": "starting"}))

            await find_target(username, int(place_id), loops, websocket)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        dprint("ws_error", e)
        with contextlib.suppress(Exception):
            await websocket.send_text(json.dumps({"status": "error", "message": "internal_error"}))
    finally:
        if user_id is not None and user_id in active_users:
            active_users.discard(user_id)
        with contextlib.suppress(Exception):
            if websocket in snipe_queue:
                snipe_queue.remove(websocket)
            await websocket.close()

if __name__ == "__main__":
    uvicorn.run("robloxsniper:app", host="0.0.0.0", port=8687, reload=False)
