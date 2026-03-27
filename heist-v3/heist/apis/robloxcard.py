import os
import ssl
import base64
import asyncio
import urllib3
from datetime import datetime
from io import BytesIO
import aiohttp
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
import uvicorn
import ujson as json
import sys

_original_path = sys.path.copy()
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append("/root/heist-v3")
from heist.framework.tools.robloxget import get_cookie
sys.path = _original_path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv("/root/heist-v3/heist/.env")

ROBLOXCLOUD_API_KEY = os.getenv("ROBLOXCLOUD_API_KEY", "")
PROXY = os.getenv("PROXY", "")
FONTS_DIR = "/root/heist-v3/heist/fonts"
PREMIUM_PATH = "/root/heist-v3/heist/assets/premium.png"
NAME_OFFSET = 15

app = FastAPI()
redis = Redis(host="localhost", port=6379, db=0)

rl_delay = 0.6
rl_retries = 4
last_req_time = 0.0
proxy_url = f"http://{PROXY}" if PROXY else None

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

connector = None
session = None

arial_cache = {}
niva_cache = {}

def format_number(n):
    try:
        n = int(n)
    except:
        return "0"
    if n >= 1000000000:
        return f"{n/1000000000:.1f}B"
    if n >= 1000000:
        return f"{n/1000000:.1f}M"
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return str(n)

def load_font(size, small=False):
    if small:
        names = ["NivaBook.ttf"]
    else:
        names = ["Generic.otf"]
    paths = []
    for name in names:
        paths.append(os.path.join(FONTS_DIR, name))
        paths.append(name)
        paths.append(os.path.join("C:/Windows/Fonts", name))
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except:
            continue
    return ImageFont.load_default()

def get_arial_font(size):
    key = size
    if key in arial_cache:
        return arial_cache[key]
    paths = [
        os.path.join(FONTS_DIR, "arial.ttf"),
        "arial.ttf",
        os.path.join("C:/Windows/Fonts", "arial.ttf"),
    ]
    for p in paths:
        try:
            f = ImageFont.truetype(p, size)
            arial_cache[key] = f
            return f
        except:
            continue
    f = ImageFont.load_default()
    arial_cache[key] = f
    return f

def get_niva_font(size):
    if size in niva_cache:
        return niva_cache[size]
    paths = [
        os.path.join(FONTS_DIR, "NivaBook.ttf"),
        "NivaBook.ttf",
        os.path.join("C:/Windows/Fonts", "NivaBook.ttf"),
    ]
    for p in paths:
        try:
            f = ImageFont.truetype(p, size)
            niva_cache[size] = f
            return f
        except:
            continue
    f = ImageFont.load_default()
    niva_cache[size] = f
    return f

def draw_text_fallback(draw, pos, text, main_font, fill):
    x, y = pos
    main_path = getattr(main_font, "path", "")
    for ch in text:
        use_font = main_font
        if ch == "_" and main_path.endswith("Generic.otf"):
            use_font = get_niva_font(main_font.size)
        elif ord(ch) > 127:
            use_font = get_arial_font(main_font.size)
        else:
            try:
                if draw.textlength(ch, font=main_font) == 0:
                    use_font = get_arial_font(main_font.size)
            except:
                use_font = get_arial_font(main_font.size)
        try:
            adv = draw.textlength(ch, font=use_font)
        except:
            adv = use_font.getsize(ch)[0]
        draw.text((x, y), ch, font=use_font, fill=fill)
        x += adv

def wrap(text, font, w, draw):
    out = []
    cur = ""
    for word in text.split():
        test = word if not cur else cur + " " + word
        try:
            tl = draw.textlength(test, font=font)
        except:
            tl = font.getsize(test)[0]
        if tl <= w:
            cur = test
        else:
            if cur:
                out.append(cur)
            cur = word
    if cur:
        out.append(cur)
    return out

async def roblox_rl():
    global last_req_time
    now = asyncio.get_event_loop().time()
    delta = now - last_req_time
    if delta < rl_delay:
        await asyncio.sleep(rl_delay - delta)
    last_req_time = asyncio.get_event_loop().time()

async def ensure_session():
    global session, connector
    if session is None or session.closed:
        connector = aiohttp.TCPConnector(ssl=ssl_context)
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

async def get_cloud_meta(user_id):
    if not ROBLOXCLOUD_API_KEY:
        return {"country": "", "premium": False, "about": "", "createTime": ""}
    headers = {"x-api-key": ROBLOXCLOUD_API_KEY}
    data = await fetch_json("GET", f"https://apis.roblox.com/cloud/v2/users/{user_id}", headers=headers)
    loc = str(data.get("locale", "")).lower() if isinstance(data, dict) else ""
    country = ""
    if loc:
        if "_" in loc:
            country = loc.split("_")[1].upper()
        else:
            m = {"en": "US", "pt": "BR", "es": "ES", "fr": "FR", "de": "DE"}
            country = m.get(loc, "").upper()
    premium = bool(data.get("premium", False)) if isinstance(data, dict) else False
    about = data.get("about", "") if isinstance(data, dict) else ""
    create_time = data.get("createTime", "") if isinstance(data, dict) else ""
    return {"country": country, "premium": premium, "about": about, "createTime": create_time}

async def get_data(username):
    search = await fetch_json(
        "POST",
        "https://users.roblox.com/v1/usernames/users",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        data={"usernames": [username], "excludeBannedUsers": False},
    )
    arr = search.get("data") or []
    if not arr:
        raise HTTPException(404, "User not found")
    d = arr[0]
    user_id = d.get("id")
    if not user_id:
        raise HTTPException(404, "User not found")

    payload = {
        "profileType": "User",
        "profileId": str(user_id),
        "components": [{"component": "UserProfileHeader"}, {"component": "About"}, {"component": "Statistics"}],
    }
    headers = {
        "Content-Type": "application/json",
        "Cookie": f".ROBLOSECURITY={get_cookie()}",
    }

    p1 = fetch_json("POST", "https://apis.roblox.com/profile-platform-api/v1/profiles/get", headers=headers, data=payload)
    p2 = fetch_json("GET", f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=420x420&format=Png&isCircular=false")
    p3 = fetch_json("GET", f"https://api.rolimons.com/players/v1/playerinfo/{user_id}", use_proxy=False)
    p4 = get_cloud_meta(user_id)
    profile, av, rol, cloud = await asyncio.gather(p1, p2, p3, p4)

    avatar = ""
    try:
        avatar = av.get("data", [{}])[0].get("imageUrl", "")
    except:
        avatar = ""

    comp = profile.get("components", {}) if isinstance(profile, dict) else {}
    header = comp.get("UserProfileHeader") or {}
    about = comp.get("About") or {}
    stats = comp.get("Statistics") or {}
    counts = header.get("counts") or {}

    friends = counts.get("friendsCount", 0)
    followers = counts.get("followersCount", 0)
    following = counts.get("followingsCount", 0)
    rap = rol.get("rap", 0) if isinstance(rol, dict) else 0
    value = rol.get("value", 0) if isinstance(rol, dict) else 0

    raw_join = None
    if isinstance(about, dict):
        raw_join = about.get("joinDateTime")
    if not raw_join and isinstance(stats, dict):
        raw_join = stats.get("userJoinedDate")
    if not raw_join and isinstance(cloud, dict):
        raw_join = cloud.get("createTime")

    created = "-"
    if raw_join:
        try:
            t = datetime.fromisoformat(str(raw_join).replace("Z", "+00:00"))
            created = t.strftime("%b %d, %Y")
        except:
            created = "-"

    desc = ""
    if isinstance(about, dict):
        desc = about.get("description") or ""
    if not desc and isinstance(cloud, dict):
        desc = cloud.get("about") or ""

    names = header.get("names") or {}
    name = names.get("displayName") or names.get("primaryName") or d.get("displayName") or d.get("name") or username
    username_real = names.get("username") or d.get("name") or username

    country = cloud.get("country", "") if isinstance(cloud, dict) else ""
    premium = bool(cloud.get("premium", False)) if isinstance(cloud, dict) else False

    return {
        "user_id": user_id,
        "name": name,
        "username": username_real,
        "avatar": avatar,
        "friends": friends,
        "followers": followers,
        "following": following,
        "rap": rap,
        "value": value,
        "created": created,
        "desc": desc,
        "country": country,
        "premium": premium,
        "presence": 0,
    }

def parse_theme(color):
    if not color:
        return None
    c = color.strip().lstrip("#")
    if len(c) != 6:
        return None
    try:
        return int(c[:2], 16), int(c[2:4], 16), int(c[4:], 16)
    except:
        return None

def rgb_to_hex(rgb):
    r, g, b = rgb
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    return "#{:02x}{:02x}{:02x}".format(r, g, b)

def mix_with_black(rgb, f):
    r, g, b = rgb
    return int(r * f), int(g * f), int(b * f)

def draw_card(d, theme_rgb=None):
    W, H = 1200, 640
    if theme_rgb:
        base = theme_rgb
        outer = rgb_to_hex(mix_with_black(base, 0.35))
        inner = rgb_to_hex(mix_with_black(base, 0.22))
        accent = rgb_to_hex(base)
    else:
        outer = "#292d73"
        inner = "#12143b"
        accent = "#3e82ff"

    img = Image.new("RGBA", (W, H), outer)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((20, 20, W - 20, H - 20), 30, fill=inner)

    ax = 60
    ay = 35
    A = 190
    c = accent if theme_rgb else "#808080"

    try:
        import requests
        r = requests.get(d["avatar"], timeout=10)
        S = 4
        A_big = A * S
        avatar_big = Image.open(BytesIO(r.content)).convert("RGBA").resize((A_big, A_big), Image.LANCZOS)
        mask_big = Image.new("L", (A_big, A_big), 0)
        ImageDraw.Draw(mask_big).ellipse((0, 0, A_big, A_big), fill=255)
        circ_big = Image.new("RGBA", (A_big, A_big), (0, 0, 0, 0))
        circ_big.paste(avatar_big, (0, 0), mask_big)
        circ = circ_big.resize((A, A), Image.LANCZOS)
        img.paste(circ, (ax, ay), circ)
        ring_big = Image.new("RGBA", (A_big + 8 * S, A_big + 8 * S), (0, 0, 0, 0))
        rb = ImageDraw.Draw(ring_big)
        rb.ellipse((0, 0, A_big + 8 * S, A_big + 8 * S), outline=c, width=4 * S)
        ring = ring_big.resize((A + 8, A + 8), Image.LANCZOS)
        img.paste(ring, (ax - 4, ay - 4), ring)
    except:
        pass

    f_title = load_font(48)
    f_sub = load_font(24, small=True)
    f_big = load_font(42)
    f_small = load_font(22, small=True)

    nx = ax + A + 40
    ny = ay + 10 + NAME_OFFSET
    draw_text_fallback(draw, (nx, ny), d["name"], f_title, "white")

    if d["premium"] and os.path.exists(PREMIUM_PATH):
        try:
            prem = Image.open(PREMIUM_PATH).convert("RGBA")
            ph = 44
            pw = int(prem.width / prem.height * ph)
            prem = prem.resize((pw, ph))
            b = draw.textbbox((nx, ny), d["name"], font=f_title)
            img.paste(prem, (nx + (b[2] - b[0]) + 8, ny - 4), prem)
        except:
            pass

    hy = ny + 45
    handle = f"@{d['username']} (ID: {d['user_id']})"
    draw_text_fallback(draw, (nx, hy), handle, f_sub, "#a8b3cf")

    try:
        code = d["country"].lower()
        if code:
            import requests
            r = requests.get(f"https://flagcdn.com/w80/{code}.png", timeout=10)
            fg = Image.open(BytesIO(r.content)).convert("RGBA")
            fh = 54
            fw = int(fg.width / fg.height * fh)
            fg = fg.resize((fw, fh))
            flag_x = W - 40 - fw
            flag_y = 35
            img.paste(fg, (flag_x, flag_y), fg)
            f_lang = load_font(24, small=True)
            lang_text = "(Language)"
            tw = draw.textlength(lang_text, font=f_lang)
            lang_x = flag_x + (fw - tw) / 2
            lang_y = flag_y + fh + 6
            draw_text_fallback(draw, (lang_x, lang_y), lang_text, f_lang, "#a8b3cf")
    except:
        pass

    cols = [W * 0.18, W * 0.5, W * 0.82]
    topy = ay + A + 45
    labs = ["Friends", "Followers", "Following"]
    vals = [format_number(d["friends"]), format_number(d["followers"]), format_number(d["following"])]

    for cx, l, v in zip(cols, labs, vals):
        vb = draw.textbbox((0, 0), v, font=f_big)
        draw_text_fallback(draw, (cx - (vb[2] - vb[0]) / 2, topy), v, f_big, "white")
        lb = draw.textbbox((0, 0), l, font=f_small)
        draw_text_fallback(draw, (cx - lb[2] / 2, topy + 45), l, f_small, "#a8b3cf")

    by = topy + 100
    labs2 = ["Created", "RAP", "Value"]
    v2 = [
        d["created"],
        "-" if d["rap"] == 0 else format_number(d["rap"]),
        "-" if d["value"] == 0 else format_number(d["value"]),
    ]

    for cx, l, v in zip(cols, labs2, v2):
        vb = draw.textbbox((0, 0), v, font=f_big)
        draw_text_fallback(draw, (cx - (vb[2] - vb[0]) / 2, by), v, f_big, "white")
        lb = draw.textbbox((0, 0), l, font=f_small)
        draw_text_fallback(draw, (cx - lb[2] / 2, by + 45), l, f_small, "#a8b3cf")

    dx = 60
    dy = by + 130

    fdt = load_font(34)
    fdc = load_font(28, small=True)

    desc = (d.get("desc") or "").strip()
    if not desc:
        desc = "No description set."

    lines = wrap(desc, fdc, W - dx - 60, draw)
    if len(lines) > 3:
        lines = lines[:3]
        last = lines[-1]
        ell = "..."
        while draw.textlength(last + ell, font=fdc) > W - dx - 60 and last:
            last = last[:-1]
        lines[-1] = last + ell

    draw_text_fallback(draw, (dx, dy), "Description", fdt, "white")
    y = dy + 42
    for line in lines:
        draw_text_fallback(draw, (dx, y), line, fdc, "#a8b3cf")
        y += 32

    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()

@app.on_event("startup")
async def on_startup():
    global connector, session
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    session = aiohttp.ClientSession(connector=connector)
    await redis.ping()

@app.on_event("shutdown")
async def on_shutdown():
    global session
    if session and not session.closed:
        await session.close()
    await redis.close()

@app.get("/card")
async def card(username: str = Query(...), color: str | None = Query(None)):
    if not username:
        raise HTTPException(400, "username required")
    theme_rgb = parse_theme(color) if color else None
    cache_color = color.lower() if color else "default"
    key = f"heist:robloxcard:{username.lower()}:{cache_color}"
    cached = await redis.get(key)
    if cached:
        if isinstance(cached, bytes):
            cached = cached.decode("utf-8", "ignore")
        try:
            return JSONResponse(json.loads(cached))
        except:
            pass
    data = await get_data(username)
    img_bytes = await asyncio.to_thread(draw_card, data, theme_rgb)
    b64 = base64.b64encode(img_bytes).decode("ascii")
    payload = {
        "image": b64,
        "id": data.get("user_id"),
        "displayName": data.get("name"),
        "username": data.get("username"),
    }
    await redis.set(key, json.dumps(payload), ex=60)
    return JSONResponse(payload)

if __name__ == "__main__":
    uvicorn.run("robloxcard:app", host="0.0.0.0", port=7686)
