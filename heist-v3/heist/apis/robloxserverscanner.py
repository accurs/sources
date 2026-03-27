import aiohttp
import asyncio
import json
import time
import os
import sys
import ssl
import re
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from dotenv import load_dotenv
import uvicorn

load_dotenv("/root/heist-v3/heist/.env")

PROXY = f"http://{os.getenv('PROXY', '')}"

_original_path = sys.path.copy()
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append("/root/heist-v3")
from heist.framework.tools.robloxget import get_cookie
sys.path = _original_path

JOIN_CONCURRENCY = 15
GEO_CONCURRENCY = 24

class Client:
    def __init__(self, proxy):
        self.proxy = proxy
        self.session = None
        self.csrf_token = None

    async def sesh(self):
        if self.session is None or self.session.closed:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(limit=1500, ssl=ssl_ctx, keepalive_timeout=10)
            self.session = aiohttp.ClientSession(connector=connector)

    async def req(self, method, url, use_csrf=False, **kw):
        await self.sesh()
        base_headers = {
            "User-Agent": "BaszuckiLikesKids/5.0",
            "Cookie": f".ROBLOSECURITY={get_cookie()}"
        }
        if use_csrf and self.csrf_token:
            base_headers["x-csrf-token"] = self.csrf_token
        extra_headers = kw.pop("headers", None)
        if extra_headers:
            base_headers.update(extra_headers)
        for _ in range(10):
            try:
                async with self.session.request(method, url, proxy=self.proxy, timeout=20, headers=base_headers, **kw) as r:
                    if use_csrf and r.status == 403 and "x-csrf-token" in r.headers:
                        self.csrf_token = r.headers["x-csrf-token"]
                        base_headers["x-csrf-token"] = self.csrf_token
                        continue
                    try:
                        return await r.json()
                    except:
                        return None
            except:
                continue
        return None

client = Client(PROXY)
redis = Redis(host="localhost", port=6379, db=0, decode_responses=True)
app = FastAPI()

def estimate_creation_by_jobid(servers):
    servers_sorted = sorted(servers, key=lambda s: s["jobId"])

    now = int(time.time())
    interval = 90

    total = len(servers_sorted)
    for idx, s in enumerate(servers_sorted):
        s["created"] = now - ((total - idx) * interval)

    return servers_sorted

async def fetch_game_metadata(place_id: int):
    print("fetching game metadata")
    details_url = f"https://games.roblox.com/v1/games/multiget-place-details?placeIds={place_id}"
    icon_url = f"https://thumbnails.roblox.com/v1/places/gameicons?placeIds={place_id}&size=512x512&format=Png"
    details_task = client.req("GET", details_url)
    icon_task = client.req("GET", icon_url)
    details, icon = await asyncio.gather(details_task, icon_task)
    if not details or not isinstance(details, list) or not details:
        game_icon = None
        if icon and isinstance(icon.get("data"), list) and icon["data"]:
            game_icon = icon["data"][0].get("imageUrl")
        return {
            "gameName": "Unknown",
            "gameUrl": f"https://www.roblox.com/games/{place_id}",
            "gameIcon": game_icon,
            "universeId": None
        }
    d0 = details[0]
    name = d0.get("name") or d0.get("sourceName") or "Unknown"
    game_url = d0.get("url") or f"https://www.roblox.com/games/{place_id}"
    game_icon = None
    if icon and isinstance(icon.get("data"), list) and icon["data"]:
        game_icon = icon["data"][0].get("imageUrl")
    universe_id = d0.get("universeId")
    print("done")
    return {"gameName": name, "gameUrl": game_url, "gameIcon": game_icon, "universeId": universe_id}

async def fetch_real_ccu(universe_id):
    if not universe_id:
        return None
    key = f"universe_ccu:{universe_id}"
    cached = await redis.get(key)
    if cached is not None:
        try:
            return int(cached)
        except:
            pass
    url = f"https://games.roblox.com/v1/games?universeIds={universe_id}"
    data = await client.req("GET", url)
    if not data or "data" not in data or not data["data"]:
        await redis.set(key, "0", ex=30)
        return None
    playing = data["data"][0].get("playing")
    if playing is None:
        await redis.set(key, "0", ex=30)
        return None
    await redis.set(key, str(playing), ex=30)
    return playing

async def fetch_all_servers(place_id: int):
    print("fetching servers")
    servers = []
    cursor = None
    while True:
        url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public?sortOrder=Desc&excludeFullGames=false&limit=100"
        if cursor:
            url += f"&cursor={cursor}"
        data = await client.req("GET", url)
        if not data:
            break
        sv = data.get("data", [])
        servers.extend(sv)
        cursor = data.get("nextPageCursor")
        if not cursor:
            break
    print("done")
    return servers

async def get_server_ip(place_id, job_id):
    print("getting server ips")
    key = f"serverip:{job_id}"
    cached = await redis.get(key)
    if cached is not None:
        return cached if cached != "None" else None

    await client.sesh()

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Roblox/WinInet",
        "Cookie": f".ROBLOSECURITY={get_cookie()}"
    }

    body = {"placeId": place_id, "gameId": job_id}

    for _ in range(10):
        try:
            async with client.session.post(
                "https://gamejoin.roblox.com/v1/join-game-instance",
                json=body,
                headers=headers,
                proxy=client.proxy,
                timeout=15
            ) as r:
                print('trying')
                if r.status == 429:
                    print(f"[JOIN 429] rate limited for job {job_id}")

                data = await r.json()

                if data.get("status") == 22:
                    print('22 status code received, likely server shutting down')
                    print(data)

                js = data.get("joinScript")
                if not js:
                    print(f"[JOIN NO JS] job={job_id} status={r.status} data={data}")
                    continue

                udmux = js.get("UdmuxEndpoints")
                if isinstance(udmux, list) and udmux:
                    addr = udmux[0].get("Address")
                    if addr:
                        await redis.set(key, addr, ex=600)
                        return addr

                addr = js.get("MachineAddress")
                if addr:
                    await redis.set(key, addr, ex=600)
                    return addr

        except Exception as e:
            print(f"[JOIN ERROR] {job_id} → {e}")
            continue

    await redis.set(key, "None", ex=120)
    print("got server ips")
    return None

async def geo_ip(ip: str):
    key = f"geo:{ip}"
    cached = await redis.get(key)
    if cached is not None:
        try:
            return json.loads(cached)
        except:
            return None
    await client.sesh()
    url = f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,regionName,city"
    for _ in range(5):
        try:
            async with client.session.get(url, proxy=client.proxy, timeout=10) as r:
                data = await r.json()
                if data.get("status") == "success":
                    await redis.set(key, json.dumps(data), ex=86400)
                    return data
        except:
            continue
    await redis.set(key, json.dumps(None), ex=3600)
    return None

async def geo_ip_batch(ips: list[str]):
    print(f"[GEO] Incoming {len(ips)} IPs → batch resolving...")

    to_lookup = []
    results = {}

    for ip in ips:
        key = f"geo:{ip}"
        cached = await redis.get(key)

        if cached is not None:
            try:
                decoded = json.loads(cached)
                results[ip] = decoded
                print(f"[GEO] Cache HIT {ip} → {decoded}")
            except:
                results[ip] = None
                print(f"[GEO] Cache CORRUPT {ip} → forcing lookup")
        else:
            print(f"[GEO] Cache MISS {ip}")
            to_lookup.append(ip)

    if not to_lookup:
        print("[GEO] All IPs resolved from cache.")
        return results

    print(f"[GEO] Lookup required for {len(to_lookup)} IPs")

    await client.sesh()

    url = "http://ip-api.com/batch?fields=status,country,countryCode,regionName,city"

    chunks = [to_lookup[i:i+100] for i in range(0, len(to_lookup), 100)]
    print(f"[GEO] Split into {len(chunks)} chunk(s)")

    for idx, chunk in enumerate(chunks, start=1):
        print(f"[GEO] Sending batch {idx}/{len(chunks)} → {len(chunk)} IPs")

        try:
            async with client.session.post(url, json=chunk, proxy=client.proxy, timeout=15) as r:
                print(f"[GEO] HTTP STATUS: {r.status}")
                data = await r.json()

                print(f"[GEO] Batch response: {json.dumps(data, indent=2)[:500]} ...")

                for ip, info in zip(chunk, data):
                    key = f"geo:{ip}"

                    if info.get("status") == "success":
                        print(f"[GEO] SUCCESS {ip} → {info}")
                        await redis.set(key, json.dumps(info), ex=86400)
                        results[ip] = info
                    else:
                        print(f"[GEO] FAIL {ip} → {info}")
                        await redis.set(key, json.dumps(None), ex=3600)
                        results[ip] = None

        except Exception as e:
            print(f"[GEO] ERROR in batch {idx}: {e}")

            for ip in chunk:
                key = f"geo:{ip}"
                print(f"[GEO] MARK FAIL {ip} (exception)")
                await redis.set(key, json.dumps(None), ex=3600)
                results[ip] = None

    print(f"[GEO] Final result count: {len(results)}")

    return results

def parse_created(server):
    raw = server.get("created") or server.get("createdAt")
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1]
        dt_parts = raw.split(".")[0]
        from datetime import datetime
        dt = datetime.fromisoformat(dt_parts)
        return int(dt.timestamp())
    except:
        return None

def parse_version(server):
    name = server.get("name")
    if isinstance(name, str):
        m = re.search(r"(\d+)$", name)
        if m:
            try:
                return int(m.group(1))
            except:
                return None
    return None

async def analyze_place_servers(place_id: int):
    meta = await fetch_game_metadata(place_id)
    servers = await fetch_all_servers(place_id)
    universe_id = meta.get("universeId")
    if not servers:
        real_ccu = await fetch_real_ccu(universe_id)
        sample_ccu = 0
        return {
            "placeId": place_id,
            "gameName": meta["gameName"],
            "gameUrl": meta["gameUrl"],
            "gameIcon": meta["gameIcon"],
            "totalServers": 0,
            "fullServers": 0,
            "ccu": real_ccu or 0,
            "sampleCCU": sample_ccu,
            "realCCU": real_ccu,
            "regions": [],
            "topRegion": None,
            "servers": []
        }
    join_sem = asyncio.Semaphore(JOIN_CONCURRENCY)

    async def ip_task(s):
        job_id = s.get("id")
        if not job_id:
            return job_id, None
        async with join_sem:
            ip = await get_server_ip(place_id, job_id)
            return job_id, ip

    ip_tasks = [ip_task(s) for s in servers]
    ip_results = await asyncio.gather(*ip_tasks, return_exceptions=True)
    job_to_ip = {}
    for res in ip_results:
        if isinstance(res, Exception):
            continue
        job_id, ip = res
        if job_id and ip:
            job_to_ip[job_id] = ip
    unique_ips = sorted(set(job_to_ip.values()))

    ip_to_region_data = await geo_ip_batch(unique_ips)

    ip_to_region = {}

    for ip, info in ip_to_region_data.items():
        if not info:
            continue

        country = info.get("country") or ""
        country_code = info.get("countryCode") or ""
        region_name = info.get("regionName") or ""
        city = info.get("city") or ""

        if country_code and region_name:
            key = f"{country_code}, {region_name}"
        elif country_code and city:
            key = f"{country_code}, {city}"
        elif country and region_name:
            key = f"{country}, {region_name}"
        else:
            key = country or region_name or city or "Unknown"

        ip_to_region[ip] = {
            "key": key,
            "country": country,
            "countryCode": country_code,
            "regionName": region_name,
            "city": city,
            "ip": ip
        }
    annotated_servers = []
    for s in servers:
        job_id = s.get("id")
        ip = job_to_ip.get(job_id)
        region_info = ip_to_region.get(ip)
        max_players = s.get("maxPlayers") or 0
        playing = s.get("playing") or 0
        ping = s.get("ping")
        created = None
        version = parse_version(s)
        annotated_servers.append({
            "jobId": job_id,
            "maxPlayers": max_players,
            "playing": playing,
            "created": created,
            "version": version,
            "ping": ping,
            "ip": ip,
            "region": region_info
        })
    annotated_servers = estimate_creation_by_jobid(annotated_servers)
    total_servers = len(annotated_servers)
    full_servers = sum(1 for s in annotated_servers if s["maxPlayers"] and s["playing"] >= s["maxPlayers"])
    sample_ccu = sum(s["playing"] for s in annotated_servers)
    real_ccu = await fetch_real_ccu(universe_id)
    effective_ccu = real_ccu if real_ccu is not None else sample_ccu
    max_list = [s["maxPlayers"] for s in annotated_servers if s["maxPlayers"]]
    if max_list:
        avg_max_players = sum(max_list) / len(max_list)
        estimated_total_servers = int((effective_ccu / avg_max_players) + 0.9999)
        estimated_full_servers = int((full_servers / total_servers) * estimated_total_servers) if total_servers > 0 else 0
    else:
        estimated_total_servers = total_servers
        estimated_full_servers = full_servers
    region_agg = {}
    for s in annotated_servers:
        region = s["region"]
        if not region:
            continue
        key = region["key"]
        if key not in region_agg:
            region_agg[key] = {
                "key": key,
                "country": region["country"],
                "countryCode": region["countryCode"],
                "regionName": region["regionName"],
                "city": region["city"],
                "serverCount": 0,
                "ccu": 0
            }
        region_agg[key]["serverCount"] += 1
        region_agg[key]["ccu"] += s["playing"]
    regions_list = sorted(region_agg.values(), key=lambda x: x["ccu"], reverse=True)
    top_region = regions_list[0] if regions_list else None
    return {
        "placeId": place_id,
        "gameName": meta["gameName"],
        "gameUrl": meta["gameUrl"],
        "gameIcon": meta["gameIcon"],
        "totalServers": total_servers,
        "fullServers": full_servers,
        "estimatedTotalServers": estimated_total_servers,
        "ccu": effective_ccu,
        "sampleCCU": sample_ccu,
        "realCCU": real_ccu,
        "regions": regions_list,
        "topRegion": top_region,
        "servers": annotated_servers
    }

@app.get("/servers/info")
async def servers_info(placeId: int = Query(..., alias="placeId")):
    data = await analyze_place_servers(placeId)
    return JSONResponse(data)

@app.get("/servers/region")
async def servers_region(placeId: int = Query(..., alias="placeId"), regionKey: str = Query(..., alias="regionKey")):
    data = await analyze_place_servers(placeId)
    regions = data.get("regions") or []
    if not any(r["key"] == regionKey for r in regions):
        raise HTTPException(status_code=404, detail="region_not_found")
    servers = []
    idx = 1
    for s in data.get("servers", []):
        region = s.get("region")
        if not region:
            continue
        if region["key"] != regionKey:
            continue
        servers.append({
            "index": idx,
            "jobId": s["jobId"],
            "version": s["version"],
            "created": s["created"],
            "players": s["playing"],
            "maxPlayers": s["maxPlayers"],
            "ping": s["ping"],
            "joinUrl": f"https://heist.lol/joiner?placeId={placeId}&gameInstanceId={s['jobId']}"
        })
        idx += 1
    return JSONResponse({
        "placeId": placeId,
        "gameName": data["gameName"],
        "gameUrl": data["gameUrl"],
        "gameIcon": data["gameIcon"],
        "regionKey": regionKey,
        "servers": servers
    })

@app.on_event("shutdown")
async def shutdown_event():
    if client.session and not client.session.closed:
        await client.session.close()

if __name__ == "__main__":
    uvicorn.run("robloxserverscanner:app", host="0.0.0.0", port=8648, reload=False)
