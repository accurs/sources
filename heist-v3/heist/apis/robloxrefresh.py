import aiohttp
import asyncio
import os
import json
import re
import ssl
import random
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import time

COOKIE_PATH = "/root/heist-v3/heist/shared/rbxcookies.json"

app = FastAPI()

session = None
connector = None

def load_cookies():
    try:
        with open(COOKIE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("cookies", [])
    except:
        return []
    upgraded = []
    changed = False
    for entry in raw:
        if isinstance(entry, str):
            upgraded.append({
                "cookie": entry,
                "health": 100,
                "last_refresh": 0,
                "fails": 0
            })
            changed = True
        else:
            entry.setdefault("health", 100)
            entry.setdefault("last_refresh", 0)
            entry.setdefault("fails", 0)
            upgraded.append(entry)
    if changed:
        save_cookies(upgraded)
    return upgraded

def save_cookies(cookies):
    with open(COOKIE_PATH, "w", encoding="utf-8") as f:
        json.dump({"cookies": cookies}, f, indent=4)

async def ensure_session():
    global session, connector
    if connector is None:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
    if session is None or session.closed:
        session = aiohttp.ClientSession(connector=connector)

async def get_csrf(cookie: str):
    await ensure_session()
    print("[CSRF] Fetching token")
    try:
        async with session.post("https://auth.roblox.com/v2/logout",
                                cookies={".ROBLOSECURITY": cookie}) as r:
            token = r.headers.get("x-csrf-token")
            print("[CSRF] Token:", token)
            return token
    except Exception as e:
        print("[CSRF] Error:", e)
        return None

async def generate_auth_ticket(cookie: str, csrf_token: str):
    await ensure_session()
    headers = {
        "x-csrf-token": csrf_token,
        "referer": "https://www.roblox.com/",
        "Content-Type": "application/json",
        "Cookie": f".ROBLOSECURITY={cookie}"
    }
    print("[TICKET] Requesting new ticket")
    async with session.post("https://auth.roblox.com/v1/authentication-ticket",
                            headers=headers) as r:
        ticket = r.headers.get("rbx-authentication-ticket")
        print("[TICKET] Ticket:", ticket)
        return ticket

async def redeem_auth_ticket(ticket: str):
    await ensure_session()
    headers = {
        "RBXAuthenticationNegotiation": "1",
        "Content-Type": "application/json",
        "Origin": "https://www.roblox.com",
        "Referer": "https://www.roblox.com/",
        "User-Agent": "Mozilla/5.0"
    }
    print("[REDEEM] Redeeming ticket")
    async with session.post("https://auth.roblox.com/v1/authentication-ticket/redeem",
                            json={"authenticationTicket": ticket},
                            headers=headers) as r:
        cookies = r.headers.getall("set-cookie", [])
        combined = "\n".join(cookies)
        print("[REDEEM] Status:", r.status)
        print("[REDEEM] Raw set-cookie:\n", combined)
        return combined, r.status

async def refresh_cookie_single(old_cookie_obj):
    print("[REFRESH] Starting single cookie refresh")
    old_cookie = old_cookie_obj["cookie"]

    csrf = await get_csrf(old_cookie)
    if not csrf:
        print("[REFRESH] CSRF failed")
        return None, "csrf_failed"

    ticket = await generate_auth_ticket(old_cookie, csrf)
    if not ticket:
        print("[REFRESH] Ticket failed")
        return None, "ticket_failed"

    raw, status = await redeem_auth_ticket(ticket)
    print("[REFRESH] Parsing cookie")
    m = re.search(r"ROBLOSECURITY=([^;]+)", raw)
    if not m:
        print("[REFRESH] Parse failed")
        return None, "parse_failed"

    print("[REFRESH] Extracted new cookie")
    return m.group(1), None

async def cookie_refresher_loop():
    idx = 0
    print("[LOOP] Cookie refresher started")
    while True:
        cookies = load_cookies()
        if not cookies:
            print("[LOOP] No cookies, waiting")
            await asyncio.sleep(60)
            continue

        if idx >= len(cookies):
            idx = 0

        print(f"[LOOP] Refreshing cookie {idx+1}/{len(cookies)}")
        c = cookies[idx]

        new_cookie, err = await refresh_cookie_single(c)
        now = int(time.time())

        if err:
            print("[LOOP] Refresh failed:", err)
            c["fails"] += 1
            c["health"] = max(0, c["health"] - 20)
        else:
            print("[LOOP] Refresh success")
            c["cookie"] = new_cookie
            c["last_refresh"] = now
            c["fails"] = 0
            c["health"] = min(100, c["health"] + 10)

        save_cookies(cookies)

        delay = 86400 / max(1, len(cookies))
        print("[LOOP] Delay:", delay, "seconds")

        idx += 1
        await asyncio.sleep(delay)

@app.post("/refresh")
async def refresh_cookie_api(body: dict):
    index = body.get("index")
    cookies = load_cookies()
    if index is None:
        raise HTTPException(400, "index missing")
    if not (0 <= index < len(cookies)):
        raise HTTPException(400, "invalid index")

    print("[API] Manual refresh for index", index)
    new_cookie, err = await refresh_cookie_single(cookies[index])
    if err:
        print("[API] Manual refresh failed:", err)
        raise HTTPException(400, err)

    cookies[index]["cookie"] = new_cookie
    cookies[index]["health"] = min(100, cookies[index]["health"] + 10)
    cookies[index]["fails"] = 0
    cookies[index]["last_refresh"] = int(time.time())
    save_cookies(cookies)

    print("[API] Manual refresh success")
    return {"success": True, "new_cookie": new_cookie}

@app.on_event("startup")
async def on_startup():
    print("[STARTUP] Starting refresher loop")
    asyncio.create_task(cookie_refresher_loop())

@app.on_event("shutdown")
async def on_shutdown():
    global session
    print("[SHUTDOWN] Closing session")
    if session and not session.closed:
        await session.close()

if __name__ == "__main__":
    uvicorn.run("robloxrefresh:app", host="0.0.0.0", port=8688)
