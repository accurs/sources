import ujson as json
import random

C = "/root/heist-v3/heist/shared/rbxcookies.json"

def get_cookie(index: int = None):
    with open(C, "r", encoding="utf-8") as f:
        data = json.load(f)

    cookies = data.get("cookies", [])

    if not cookies:
        return None

    if index is not None:
        if 0 <= index < len(cookies):
            return cookies[index].get("cookie")
        return None

    picked = random.choice(cookies)
    return picked.get("cookie")

def get_cookie_by_index(index: int):
    with open(C, "r", encoding="utf-8") as f:
        data = json.load(f)

    cookies = data.get("cookies", [])
    if not cookies:
        return None

    index = index % len(cookies)
    return cookies[index].get("cookie")