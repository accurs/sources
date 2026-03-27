import aiohttp
import asyncio
import os
import json
import re
import ssl
import time
from dotenv import load_dotenv

load_dotenv("/root/heist-v3/heist/.env")
PROXY = os.getenv("PROXY")
PROXY = f"http://{PROXY}" if PROXY else None

COOKIE_PATH = "/root/heist-v3/heist/shared/rbxcookies.json"

session = None
connector = None

def load_cookies():
    print("[LOAD] loading cookies")
    try:
        with open(COOKIE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("cookies", [])
    except Exception as e:
        print("[LOAD] failed", e)
        return []
    upgraded = []
    changed = False
    for entry in raw:
        if isinstance(entry, str):
            print("[LOAD] upgrading old cookie entry")
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
        print("[LOAD] saving upgraded format")
        save_cookies(upgraded)
    print("[LOAD] total cookies", len(upgraded))
    return upgraded

def save_cookies(cookies):
    print("[SAVE] writing file")
    with open(COOKIE_PATH, "w", encoding="utf-8") as f:
        json.dump({"cookies": cookies}, f, indent=4)

async def ensure_session():
    global session, connector
    if connector is None:
        print("[SESSION] creating connector")
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
    if session is None or session.closed:
        print("[SESSION] creating session")
        session = aiohttp.ClientSession(connector=connector)

async def get_csrf(cookie):
    print("[CSRF] fetching token for cookie")
    await ensure_session()
    try:
        async with session.post(
            "https://auth.roblox.com/v2/logout",
            cookies={".ROBLOSECURITY": cookie},
            proxy=PROXY
        ) as r:
            token = r.headers.get("x-csrf-token")
            print("[CSRF] status", r.status, "token", token)
            return token
    except Exception as e:
        print("[CSRF] error", e)
        return None

async def generate_auth_ticket(cookie, csrf_token):
    print("[TICKET] requesting ticket")
    await ensure_session()
    headers = {
        "x-csrf-token": csrf_token,
        "referer": "https://www.roblox.com/",
        "Content-Type": "application/json",
        "Cookie": f".ROBLOSECURITY={cookie}"
    }
    try:
        async with session.post(
            "https://auth.roblox.com/v1/authentication-ticket",
            headers=headers,
            proxy=PROXY
        ) as r:
            ticket = r.headers.get("rbx-authentication-ticket")
            print("[TICKET] status", r.status, "ticket", ticket)
            return ticket
    except Exception as e:
        print("[TICKET] exception", e)
        return None

async def redeem_auth_ticket(ticket):
    print("[REDEEM] redeeming ticket", ticket)
    await ensure_session()
    headers = {
        "RBXAuthenticationNegotiation": "1",
        "Content-Type": "application/json",
        "Origin": "https://www.roblox.com",
        "Referer": "https://www.roblox.com/",
        "User-Agent": "Mozilla/5.0"
    }
    try:
        async with session.post(
            "https://auth.roblox.com/v1/authentication-ticket/redeem",
            json={"authenticationTicket": ticket},
            headers=headers,
            proxy=PROXY
        ) as r:
            cookies = r.headers.getall("set-cookie", [])
            combined = "\n".join(cookies)
            print("[REDEEM] status", r.status)
            print("[REDEEM] raw cookies\n", combined)
            return combined, r.status
    except Exception as e:
        print("[REDEEM] exception", e)
        return "", -1

async def refresh_cookie_single(old_cookie_obj):
    print("[REFRESH] starting refresh for cookie")
    old_cookie = old_cookie_obj["cookie"]

    csrf = await get_csrf(old_cookie)
    if not csrf:
        print("[REFRESH] csrf fail")
        return None, "csrf_failed"

    ticket = await generate_auth_ticket(old_cookie, csrf)
    if not ticket:
        print("[REFRESH] ticket fail")
        return None, "ticket_failed"

    raw, status = await redeem_auth_ticket(ticket)
    print("[REFRESH] parsing roblosecurity")
    m = re.search(r"ROBLOSECURITY=([^;]+)", raw)
    if not m:
        print("[REFRESH] parse fail")
        return None, "parse_failed"

    new_cookie = m.group(1)
    print("[REFRESH] success extracted cookie")
    return new_cookie, None

async def main():
    cookies = load_cookies()
    total = len(cookies)
    print("[MAIN] total cookies", total)
    if total <= 1:
        print("[MAIN] not enough cookies")
        return

    i = 1
    while i < total:
        print("")
        print("=========== COOKIE", i, "/", total - 1, "===========")
        new_cookie, err = await refresh_cookie_single(cookies[i])

        if err:
            print("[MAIN] refresh failed:", err)
            cookies[i]["fails"] += 1
            cookies[i]["health"] = max(0, cookies[i]["health"] - 20)
        else:
            print("[MAIN] refresh success, saving new cookie")
            cookies[i]["cookie"] = new_cookie
            cookies[i]["fails"] = 0
            cookies[i]["health"] = min(100, cookies[i]["health"] + 10)
            cookies[i]["last_refresh"] = int(time.time())

        save_cookies(cookies)

        choice = input("refresh next? (y/n/retry): ").strip().lower()
        if choice == "y":
            i += 1
        elif choice == "retry":
            continue
        else:
            break

    if session and not session.closed:
        await session.close()
    print("[MAIN] done")

asyncio.run(main())
