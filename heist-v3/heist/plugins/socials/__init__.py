import discord
from discord import app_commands, Embed, File
from discord import ui
from discord.ext import commands
from discord.ext.commands import Cog, hybrid_command, hybrid_group
import asyncio
import io
import random
import aiohttp
import re
import ujson as json
import base64
from typing import Optional, Union, Dict, Any
import urllib.parse
from urllib.parse import urlparse
import datetime
from datetime import datetime
from bs4 import BeautifulSoup
import ssl
import zipfile
import logging
import os
from urllib.parse import urlparse, urlencode
from PIL import Image
from heist.framework.discord.decorators import donor_only, check_donor, check_owner, disabled
from heist.framework.tools.separator import makeseparator
from heist.framework.tools.robloxget import get_cookie
import math
import hashlib
from heist.framework.pagination import Paginator
from heist.framework.discord import CommandCache
from pytubefix import YouTube
from pytube import Search
from heist.framework.youtube.getter import get_youtube
import websockets
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from heist.framework.discord.cv2 import cv2 as cpv2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("heist.log"),
    ],
)

logger = logging.getLogger("heist")

logging.getLogger("shazamio_core").setLevel(logging.ERROR)
logging.getLogger("symphonia_core.probe").setLevel(logging.ERROR)
logging.getLogger("symphonia_bundle_mp3.demuxer").setLevel(logging.ERROR)

TOKEN_FILE = "/root/heist-v3/heist/framework/youtube/youtubetoken.json"

async def get_cache_key(self, key_data):
    key_str = json.dumps(key_data, sort_keys=True)
    return f"roblox:{hashlib.md5(key_str.encode()).hexdigest()}"

async def get_cached_data(self, cache_key):
    try:
        cached = await self.bot.redis.get(cache_key)
        if cached:
            return await asyncio.get_event_loop().run_in_executor(None, json.loads, cached)
    except:
        pass
    return None

async def set_cached_data(self, cache_key, data):
    try:
        json_data = await asyncio.get_event_loop().run_in_executor(None, json.dumps, data)
        await self.bot.redis.setex(cache_key, 120, json_data)
    except:
        pass

BLOXLINK_KEY = os.getenv("BLOXLINK_API_KEY")
GUNSLOL_KEY = os.getenv("GUNSLOL_API_KEY")
ROBLOXCLOUD_API_KEY = os.getenv("ROBLOXCLOUD_API_KEY")
REDDIT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
OXAPAY_KEY = os.getenv('OXAPAY_API_KEY')
PROXY = os.getenv("PROXY")

class Social(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.rolock = asyncio.Lock()
        self.ROBLOXCLOUD_API_KEY = ROBLOXCLOUD_API_KEY
        self.OXAPAY_KEY = os.getenv('OXAPAY_API_KEY')
        self.last_req_time = 0
        self.rl_retries = 4
        self.rl_delay = 0.6
        self.proxy_until = 0
        self.proxy_url = f"http://{PROXY}"
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self.omni_session = aiohttp.ClientSession(connector=connector)
        self.logger = logger
        self.ctx_discord2roblox2 = app_commands.ContextMenu(
            name='✨ Lookup Roblox',
            callback=self.discord2roblox2,
        )
        self.bot.tree.add_command(self.ctx_discord2roblox2)

    async def tiktok_rl(self):
        async with self.lock:
            now = asyncio.get_event_loop().time()
            wait_time = max(0, 1.05 - (now - self.last_request_time))
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self.last_request_time = asyncio.get_event_loop().time()

    async def roblox_rl(self):
        async with self.rolock:
            current_time = asyncio.get_event_loop().time()
            time_since_last = current_time - self.last_req_time
            if time_since_last < self.rl_delay:
                await asyncio.sleep(self.rl_delay - time_since_last)
            self.last_req_time = asyncio.get_event_loop().time()

    async def roblox_cloud_user(self, user_id):
        token = getattr(self, "ROBLOXCLOUD_API_KEY", None)
        if not token or not isinstance(token, str) or not token.strip():
            print("[cloud] Missing or invalid ROBLOXCLOUD_API_KEY", flush=True)
            return {}
        url = f"https://apis.roblox.com/cloud/v2/users/{user_id}"
        headers = {"x-api-key": f"{token}"}
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as s:
            for _ in range(self.rl_retries):
                await self.roblox_rl()
                async with s.get(url, headers=headers, proxy=self.proxy_url) as r:
                    if r.status == 429:
                        await asyncio.sleep(float(r.headers.get("Retry-After", 1)))
                        continue
                    if r.status >= 500:
                        await asyncio.sleep(1)
                        continue
                    try:
                        data = await r.json()
                    except Exception:
                        txt = await r.text()
                        return {}
                    if "locale" in data:
                        loc = data["locale"].split("_")[0]
                        langs = {
                            "en": "English","en_us": "English (US)","en_gb": "English (UK)",
                            "en_ca": "English (Canada)","en_au": "English (Australia)","en_nz": "English (New Zealand)",
                            "de": "German","fr": "French","es": "Spanish","es_mx": "Spanish (Mexico)","es_es": "Spanish (Spain)",
                            "es_ar": "Spanish (Argentina)","pt": "Portuguese","pt_br": "Portuguese (Brazil)","it": "Italian",
                            "ja": "Japanese","ko": "Korean","zh": "Chinese","zh_cn": "Chinese (Simplified)","zh_tw": "Chinese (Traditional)",
                            "zh_hk": "Chinese (Hong Kong)","nl": "Dutch","pl": "Polish","ru": "Russian","tr": "Turkish",
                            "sv": "Swedish","no": "Norwegian","da": "Danish","fi": "Finnish","cs": "Czech",
                            "sk": "Slovak","hu": "Hungarian","el": "Greek","ro": "Romanian","bg": "Bulgarian",
                            "uk": "Ukrainian","hr": "Croatian","sr": "Serbian","sl": "Slovenian","he": "Hebrew",
                            "ar": "Arabic","ar_sa": "Arabic (Saudi)","th": "Thai","vi": "Vietnamese","id": "Indonesian",
                            "ms": "Malay","hi": "Hindi","bn": "Bengali","ta": "Tamil","te": "Telugu","ur": "Urdu",
                            "fa": "Persian","et": "Estonian","lv": "Latvian","lt": "Lithuanian","is": "Icelandic",
                            "af": "Afrikaans","sw": "Swahili","fil": "Filipino","tl": "Tagalog","my": "Burmese",
                            "km": "Khmer","lo": "Lao","mn": "Mongolian","ne": "Nepali","si": "Sinhala",
                            "am": "Amharic","zu": "Zulu","xh": "Xhosa","st": "Sotho","ts": "Tsonga","tn": "Tswana",
                            "rw": "Kinyarwanda","ha": "Hausa","ig": "Igbo","yo": "Yoruba","kk": "Kazakh","uz": "Uzbek",
                            "az": "Azerbaijani","ka": "Georgian","be": "Belarusian","mk": "Macedonian","bs": "Bosnian",
                            "ga": "Irish","cy": "Welsh","mt": "Maltese","sq": "Albanian","hy": "Armenian",
                            "kmr": "Kurdish","tg": "Tajik","ky": "Kyrgyz","tk": "Turkmen","ps": "Pashto",
                            "sd": "Sindhi","gu": "Gujarati","kn": "Kannada","ml": "Malayalam","mr": "Marathi",
                            "pa": "Punjabi","si_lk": "Sinhala (Sri Lanka)"
                        }
                        lang = langs.get(data["locale"].lower(), langs.get(loc))
                        if lang:
                            data["language_display"] = f"{lang}"
                    return data
        return {}

    async def roblox_profile_user(self, user_id):
        url = "https://apis.roblox.com/profile-platform-api/v1/profiles/get"
        payload = {
            "profileType": "User",
            "profileId": str(user_id),
            "components": [
                {"component": "UserProfileHeader"},
                {"component": "About"},
                {"component": "CurrentlyWearing"},
                {"component": "FavoriteExperiences"},
                {"component": "Friends"},
                {"component": "Collections"},
                {"component": "Communities"},
                {"component": "RobloxBadges"},
                {"component": "PlayerBadges"},
                {"component": "Statistics"},
                {"component": "Actions"}
            ]
        }
        headers = {
            "Content-Type": "application/json",
            "Cookie": f".ROBLOSECURITY={get_cookie()}"
        }
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as s:
            for _ in range(self.rl_retries):
                await self.roblox_rl()
                async with s.post(url, headers=headers, json=payload, proxy=self.proxy_url) as r:
                    if r.status == 429:
                        await asyncio.sleep(float(r.headers.get("Retry-After", 1)))
                        continue
                    if r.status >= 500:
                        await asyncio.sleep(1)
                        continue
                    try:
                        return await r.json()
                    except Exception:
                        txt = await r.text()
                        return {}
        return {}

    async def roblox_request(self, method, url, **kwargs):
        if "cloud/v2/users" in url:
            return await self.roblox_cloud_user(url.split("/")[-1])
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 OPR/107.0.0.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        user_headers = kwargs.pop('headers', {})
        headers = {**default_headers, **user_headers}

        cookie_value = get_cookie()
        if cookie_value:
            headers['Cookie'] = f'.ROBLOSECURITY={cookie_value}'

        kwargs['headers'] = headers

        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)

        if not hasattr(self, 'rosession') or self.rosession.closed:
            self.rosession = aiohttp.ClientSession(connector=connector)

        for attempt in range(self.rl_retries):
            try:
                await self.roblox_rl()

                async with self.rosession.request(method, url, **kwargs, proxy=self.proxy_url) as response:
                    if response.status == 429:
                        retry_after = float(response.headers.get('Retry-After', 1))
                        await asyncio.sleep(retry_after)
                        continue
                    if response.status >= 500:
                        await asyncio.sleep(1 * (attempt + 1))
                        continue
                    if response.status == 403:
                        token = response.headers.get("X-CSRF-TOKEN")
                        if token:
                            kwargs['headers']['X-CSRF-TOKEN'] = token
                            async with self.rosession.request(method, url, **kwargs, proxy=self.proxy_url) as resp2:
                                await resp2.read()
                                print(resp2)
                                return resp2
                    await response.read()
                    return response

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                self.logger.warning(f"Request failed (attempt {attempt + 1}): {str(e)}")
                await asyncio.sleep(1 * (attempt + 1))

        raise aiohttp.ClientError("We are being ratelimited or disconnected. Try again later.")

    async def omni_search(self, query: str):
        query = (query or "").strip()
        if len(query) < 2:
            return []

        cache_key = f"heist:roblox:omni:{query.lower()}"
        try:
            cached = await self.bot.redis.get(cache_key)
            if cached:
                try:
                    return json.loads(cached)
                except:
                    pass
        except:
            pass

        params = {
            "verticalType": "user",
            "searchQuery": query,
            "pageToken": "",
            "globalSessionId": "diddy",
            "sessionId": "blud"
        }

        url = "https://apis.roblox.com/search-api/omni-search?" + urlencode(params)
        loop = asyncio.get_event_loop()
        use_proxy = self.proxy_url is not None and loop.time() < self.proxy_until
        proxy = self.proxy_url if use_proxy else None

        for attempt in range(self.rl_retries):
            try:
                await self.roblox_rl()

                async with self.omni_session.get(url, proxy=proxy) as r:
                    text = await r.text()
                    status = r.status

                    try:
                        data = json.loads(text)
                    except:
                        data = {}

                    is_rl = False
                    if status == 429:
                        is_rl = True
                    elif data.get("error") == 0:
                        is_rl = True

                    if is_rl:
                        if self.proxy_url:
                            self.proxy_until = loop.time() + 2
                            proxy = self.proxy_url
                            continue
                        await asyncio.sleep(0.5)
                        continue

                    if status != 200:
                        return []

                    sr = data.get("searchResults") or []
                    pairs = []

                    for group in sr:
                        contents = group.get("contents") or []
                        for c in contents:
                            u = c.get("username")
                            uid = c.get("contentId")
                            if u and uid:
                                pairs.append((u, uid))

                    seen = set()
                    result = []
                    for u, uid in pairs:
                        if u not in seen:
                            seen.add(u)
                            result.append((u, uid))
                    result = result[:10]

                    try:
                        if result:
                            await self.bot.redis.setex(cache_key, 10, json.dumps(result))
                    except:
                        pass

                    return result

            except Exception:
                await asyncio.sleep(0.2 * (attempt + 1))

        return []

    async def omni_search_games(self, query: str):
        query = (query or "").strip()
        if len(query) < 2:
            return []

        cache_key = f"heist:roblox:omni_games:{query.lower()}"
        try:
            cached = await self.bot.redis.get(cache_key)
            if cached:
                try:
                    return json.loads(cached)
                except:
                    pass
        except:
            pass

        params = {
            "searchQuery": query,
            "pageToken": "",
            "sessionId": "diddyblud",
            "pageType": "all"
        }

        url = "https://apis.roblox.com/search-api/omni-search?" + urlencode(params)
        loop = asyncio.get_event_loop()
        use_proxy = self.proxy_url is not None and loop.time() < self.proxy_until
        proxy = self.proxy_url if use_proxy else None

        for attempt in range(self.rl_retries):
            try:
                await self.roblox_rl()

                async with self.omni_session.get(url, proxy=proxy) as r:
                    text = await r.text()
                    status = r.status

                    try:
                        data = json.loads(text)
                    except:
                        data = {}

                    is_rl = False
                    if status == 429:
                        is_rl = True
                    elif data.get("error") == 0:
                        is_rl = True

                    if is_rl:
                        if self.proxy_url:
                            self.proxy_until = loop.time() + 2
                            proxy = self.proxy_url
                            continue
                        await asyncio.sleep(0.5)
                        continue

                    if status != 200:
                        return []

                    sr = data.get("searchResults") or []
                    result = []

                    for group in sr:
                        if group.get("contentGroupType") != "Game":
                            continue

                        contents = group.get("contents") or []
                        for c in contents:
                            name = c.get("name")
                            root = c.get("rootPlaceId")
                            creator = c.get("creatorName") or "Unknown"

                            if name and root:
                                result.append((name, root, creator))

                    out = []
                    seen = set()

                    for name, root, creator in result:
                        if root not in seen:
                            seen.add(root)
                            out.append((name, root, creator))

                    out = out[:10]

                    try:
                        if out:
                            await self.bot.redis.setex(cache_key, 10, json.dumps(out))
                    except:
                        pass

                    return out

            except Exception as e:
                await asyncio.sleep(0.2 * (attempt + 1))

        return []

    async def get_design_settings(self, user_id: int):
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT roblox_user_v2 FROM design_settings WHERE user_id=$1",
                user_id
            )
            return row or {"roblox_user_v2": False}

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def format_metric(self, value, use_millions=False):
        if use_millions and value >= 1000000:
            return f"{int(value/1000000)}M" if value % 1000000 == 0 else f"{value/1000000:.1f}M"
        elif value >= 1000:
            return f"{int(value/1000)}k" if value % 1000 == 0 else f"{value/1000:.1f}k"
        return str(value)

    async def process_description(self, description: str) -> str:
        return await asyncio.to_thread(
            lambda: re.sub(r"#(\S+)", r"[#\1](<https://tiktok.com/tag/\1>)", description)
            if description else ""
        )

    async def upload_to_catbox(self, file_data: io.BytesIO) -> str | None:
        try:
            data = aiohttp.FormData()
            data.add_field('reqtype', 'fileupload')
            data.add_field('fileToUpload', file_data, filename='heist.mp4')
            async with self.session.post('https://catbox.moe/user/api.php', data=data, proxy=self.proxy_url) as response:
                if response.status == 200:
                    return await response.text()
                return None
        except Exception:
            return None

    @hybrid_group(name="roblox", description="Roblox utilities", aliases=["rblx", "rbx"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def roblox(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @roblox.command(
        name="snipe",
        description="[UNAVAILABLE] Snipe a Roblox player in-game",
    )
    @app_commands.describe(
        username="Roblox username to snipe",
        place="Game ID to scan"
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def snipe(self, ctx: commands.Context, username: str, place: int):
        try:
            if ctx.author.id != 1150918662769881088:
                return await cpv2.warn(ctx, "Coming soon enough.")
            search_response = await self.roblox_request(
                "POST",
                "https://users.roblox.com/v1/usernames/users",
                headers={"accept": "application/json", "Content-Type": "application/json"},
                json={"usernames": [username], "excludeBannedUsers": True}
            )
            user_data = await search_response.json()

            if not user_data.get("data"):
                return await cpv2.warn(ctx, "No **Roblox user** found with that name.")

            def pluralize_scans(n: int):
                return "scan" if n == 1 else "scans"

            def pluralize_times(n: int):
                return "time" if n == 1 else "times"

            def format_elapsed(t: float):
                if t < 1:
                    return f"{round(t * 1000, 2)} ms"
                return f"{round(t, 2)} seconds"

            user_id = user_data["data"][0]["id"]
            roblox_username = user_data["data"][0]["name"]
            roblox_display_name = user_data["data"][0].get("displayName")
            profile_url = f"https://www.roblox.com/users/{user_id}/profile"
            author_name = f"{roblox_display_name} (@{roblox_username})" if roblox_display_name else roblox_username

            headshot_response = await self.roblox_request(
                "GET",
                f"https://thumbnails.roproxy.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Png"
            )
            headshot_data = await headshot_response.json()
            headshot_url = headshot_data["data"][0]["imageUrl"]

            color = await self.bot.get_color(ctx.author.id)

            msg = await cpv2.send(
                ctx,
                content=f"## 🔎 Preparing sniper..\nConnecting to scanner.. <a:dotsload:1423056880854499338>",
                media_url=headshot_url,
                color=color,
                title=f"[{author_name}]({profile_url})",
            )

            payload = {
                "username": roblox_username,
                "placeId": place,
                "userId": ctx.author.id
            }

            result = None
            async with websockets.connect("ws://127.0.0.1:8687/ws") as ws:
                await ws.send(json.dumps(payload))

                async for raw in ws:
                    data = json.loads(raw)
                    status = data.get("status")

                    if status == "already_sniping":
                        return await cpv2.edit_warn(
                            msg,
                            ctx,
                            "You already have an **active snipe running**.\nPlease wait for it to finish."
                        )

                    if status == "queued":
                        pos = data.get("position", "?")
                        await cpv2.edit(
                            msg,
                            ctx,
                            content=f"## 🕒 You are in the queue..\nPosition **#{pos}** <a:dotsload:1423056880854499338>",
                            media_url=headshot_url,
                            color=color,
                        )
                        continue

                    if status == "starting":
                        await cpv2.edit(
                            msg,
                            ctx,
                            content=f"## 🔎 Scanning servers..\nSearching for **`{roblox_username}`** in **{place}**.. <a:dotsload:1423056880854499338>",
                            media_url=headshot_url,
                            color=color,
                        )
                        continue

                    if status in ("found", "not_found", "error", "not_in_game"):
                        result = data
                        break

            if result is None:
                return await cpv2.edit_warn(msg, ctx, "No response received from sniper.")

            status = result.get("status")

            if status == "found":
                scans = result.get("scans")
                elapsed = format_elapsed(result.get("elapsed"))
                scan_word = pluralize_scans(scans)
                game_name = result.get("gameName")
                game_url = result.get("gameUrl")
                join_url = result.get("joinUrl")
                game_thumb = result.get("gameThumbnail")

                sections = [
                    ui.Section(
                        ui.TextDisplay(f"**Player:** [**`{author_name}`**]({profile_url})"),
                        accessory=ui.Thumbnail(headshot_url)
                    ),
                    ui.Separator(),
                    ui.TextDisplay(f"**Game:** [**`{game_name}`**]({game_url})"),
                    ui.MediaGallery(discord.MediaGalleryItem(game_thumb)),
                ]

                buttons = [
                    cpv2.link_button(f"Join {roblox_username}", join_url)
                ]

                return await cpv2.edit(
                    msg,
                    ctx,
                    title=f"**<:c_:1441253265151885343> Found the player!**",
                    content=f"-# Search completed: **{scans} {scan_word}** performed.\n-# Sniped in **{elapsed}**.",
                    sections=sections,
                    color=color,
                    buttons=buttons,
                )

            if status == "not_in_game":
                presence_status = result.get("presenceStatus") or "Unknown"

                sections = [
                    ui.Section(
                        ui.TextDisplay(f"User is not in any game."),
                        accessory=ui.Thumbnail(headshot_url)
                    )
                ]

                return await cpv2.edit(
                    msg,
                    ctx,
                    title=f"<:no:1423109075083989062> [User not in-game]({profile_url})",
                    content=f"**Current Status:**\n{presence_status}",
                    sections=sections,
                    color=discord.Color.red(),
                )

            if status == "error" and result.get("message") == "game_too_big":
                return await cpv2.edit_warn(
                    msg,
                    ctx,
                    "This game has **over 50,000 players**, scanning is disabled for performance reasons."
                )

            if status == "not_found":
                scans = result.get("scans")
                elapsed = format_elapsed(result.get("elapsed"))
                scan_word = pluralize_times(scans)
                game_name = result.get("gameName")
                game_url = result.get("gameUrl")
                game_thumb = result.get("gameThumbnail")

                sections = [
                    ui.Section(
                        ui.TextDisplay(f"**Player:** [**`{author_name}`**]({profile_url})"),
                        accessory=ui.Thumbnail(headshot_url)
                    ),
                    ui.Separator(),
                    ui.TextDisplay(f"**Game scanned:** [{game_name}]({game_url})"),
                    ui.MediaGallery(discord.MediaGalleryItem(game_thumb)),
                ]

                return await cpv2.edit(
                    msg,
                    ctx,
                    title=f"<:no:1423109075083989062> [User could not be found]({profile_url})",
                    content=f"Scanned **{scans} {scan_word}** but the user was **not found**.",
                    sections=sections,
                    color=discord.Color.red(),
                    footer=f"-# Scan took **{elapsed}**.",
                )

            return await cpv2.edit_warn(msg, ctx, f"Unexpected sniper error: `{result.get('message')}`")

        except Exception as e:
            return await cpv2.warn(ctx, str(e))

    @snipe.autocomplete("place")
    async def auto_snipe(self, interaction: discord.Interaction, current: str):
        try:
            results = await self.omni_search_games(current)
            return [
                app_commands.Choice(
                    name=f"{name} - {creator} [{root}]",
                    value=str(root)
                )
                for (name, root, creator) in results
            ]
        except:
            return []

    @roblox.command(name="group", description="Get Roblox group information", aliases=["g"])
    @app_commands.describe(id="The Roblox group ID to look up")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def roblox_group(self, ctx: commands.Context, id: str):
        match = re.search(r"(\d{3,})", id)
        if match:
            id = match.group(1)
            
        loading_embed = discord.Embed(
            description=f"-# <a:dotsload:1423056880854499338> {ctx.author.mention}: scanning group **`{id}`**..",
            color=await self.bot.get_color(ctx.author.id)
        )
        message = await ctx.send(embed=loading_embed)

        try:
            response = await self.roblox_request("GET", f"https://groups.roblox.com/v1/groups/{id}")
            if response.status != 200:
                await ctx.edit_warn("Invalid or private group.", message)
                return
            data = await response.json()

            name = data.get("name", "Unknown")
            bio = data.get("description", "")
            owner = data.get("owner")
            owner_text = "None"
            if owner:
                owner_text = f"[{owner['username']}](https://roblox.com/users/{owner['userId']}/profile)"

            shout = data.get("shout")
            shout_text = "None"
            shout_info = "None"
            if shout:
                poster = shout.get("poster")
                poster_text = f"[{poster['username']}](https://roblox.com/users/{poster['userId']}/profile)" if poster else "Unknown"
                created = shout.get("updated")
                ts = None
                if created:
                    try:
                        ts = int(datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp())
                    except:
                        ts = None
                shout_text = shout.get("body", "None")
                if ts:
                    shout_info = f"**Poster**: {poster_text}\n**Posted**: <t:{ts}:R>"
                else:
                    shout_info = f"**Poster**: {poster_text}"

            created_ts = None
            try:
                created_resp = await self.roblox_request("GET", f"https://groups.roblox.com/v2/groups?groupIds={id}")
                if created_resp.status == 200:
                    created_json = await created_resp.json()
                    groups_data = created_json.get("data", [])
                    if groups_data and "created" in groups_data[0]:
                        created_str = groups_data[0]["created"]
                        created_ts = int(datetime.fromisoformat(created_str.replace("Z", "+00:00")).timestamp())
            except:
                pass

            updated_ts = None
            updated = data.get("updated")
            if updated:
                try:
                    updated_ts = int(datetime.fromisoformat(updated.replace("Z", "+00:00")).timestamp())
                except:
                    pass

            member_count = data.get("memberCount", 0)
            is_public = data.get("publicEntryAllowed", False)

            thumb_resp = await self.roblox_request("GET", f"https://thumbnails.roblox.com/v1/groups/icons?groupIds={id}&size=420x420&format=Png&isCircular=false")
            if thumb_resp.status == 200:
                thumb_json = await thumb_resp.json()
                thumbnail = thumb_json.get("data", [{}])[0].get("imageUrl", "https://t0.rbxcdn.com/91d977e12525a5ed262cd4dc1c4fd52b?format=png")
            else:
                thumbnail = "https://t0.rbxcdn.com/91d977e12525a5ed262cd4dc1c4fd52b?format=png"

            embed = discord.Embed(
                title=name,
                url=f"https://roblox.com/groups/{id}",
                description=bio,
                color=await self.bot.get_color(ctx.author.id)
            )
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
            embed.set_thumbnail(url=thumbnail)
            embed.add_field(name="Owner", value=owner_text, inline=True)
            embed.add_field(name="Members", value=f"{member_count:,}", inline=True)
            if shout_text:
                shout_format = f"```{shout_text}```"
                embed.add_field(name="Shout", value=shout_format, inline=False)
            embed.add_field(name="ID", value=f"`{id}`", inline=True)
            embed.add_field(name="Public Entry", value=str(is_public), inline=True)
            embed.add_field(name="Created", value=f"<t:{created_ts}:R>" if created_ts else "Unknown", inline=True)
            embed.add_field(name="Shout Info", value=shout_info, inline=True)
            await message.edit(embed=embed)

        except Exception as e:
            await ctx.edit_warn(str(e), message)

    @roblox.group(name="render", description="Roblox rendering commands", aliases=["re"], invoke_without_command=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def render(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @roblox.group(name="history", description="Roblox history tracking commands", invoke_without_command=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def history(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    # @roblox.group(name="server", description="Roblox server info commands", invoke_without_command=True)
    # @app_commands.allowed_installs(guilds=True, users=True)
    # @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    # async def server(self, ctx: commands.Context):
    #     if ctx.invoked_subcommand is None:
    #         await ctx.send_help(ctx.command)

    @roblox.command(name="user", description="Get Roblox user information", aliases=["u", "profile"])
    @app_commands.describe(username="The Roblox username to look up", card="Generate profile card?")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def roblox_user(self, ctx: commands.Context, username: str, card: Optional[bool] = None):
        settings = await self.get_design_settings(ctx.author.id)
        auto_card = settings.get("roblox_user_v2", False)
        use_card = auto_card if card is None else card

        async def truncate_text(text: str, max_length: int = 500) -> str:
            cleaned_text = re.sub(r'\n{4,}', '\n\n\n', text)
            return cleaned_text[:max_length] + '...' if len(cleaned_text) > max_length else cleaned_text

        async def format_number(number):
            if number is None:
                return "0"
            if number >= 1_000_000_000:
                return f"{number/1_000_000_000:.1f}B"
            if number >= 1_000_000:
                return f"{number/1_000_000:.1f}M"
            if number >= 1_000:
                return f"{number/1_000:.1f}K"
            return str(number)

        async def fetch_rolimons(session, user_id):
            try:
                async with session.get(f'https://api.rolimons.com/players/v1/playerinfo/{user_id}') as response:
                    if response.status == 200:
                        return await response.json()
                    return {'value': 0, 'rap': 0, 'premium': False, 'stats_updated': None}
            except Exception:
                return {'value': 0, 'rap': 0, 'premium': False, 'stats_updated': None}

        async def get_thumbnail():
            try:
                response = await self.roblox_request('GET', f"https://thumbnails.roproxy.com/v1/users/avatar?userIds={user_id}&size=420x420&format=Png")
                return (await response.json())['data'][0]['imageUrl']
            except:
                return "https://t0.rbxcdn.com/91d977e12525a5ed262cd4dc1c4fd52b?format=png"

        async def get_ropro_info():
            async with self.session.get(f'https://api.ropro.io/getUserInfoTest.php?userid={user_id}') as ropro_response:
                if ropro_response.status == 200:
                    return (await ropro_response.json()).get('discord')
                return None

        async def check_verified_hat(user_id):
            try:
                r = await self.roblox_request(
                    "GET",
                    f"https://inventory.roblox.com/v1/users/{user_id}/items/Asset/102611803"
                )
                j = await r.json()
                return (len(j.get("data", [])) > 0, True)
            except aiohttp.ClientResponseError as e:
                if e.status == 403:
                    return (None, False)
                return (None, True)
            except:
                return (None, True)

        try:
            search_response = await self.roblox_request(
                'POST',
                'https://users.roblox.com/v1/usernames/users',
                headers={'accept': 'application/json', 'Content-Type': 'application/json'},
                json={'usernames': [username], 'excludeBannedUsers': False}
            )
            user_data = await search_response.json()
            if not user_data['data']:
                await ctx.warn("No **Roblox user** found with that name.")
                return
            user_id = user_data['data'][0]['id']

            try:
                if use_card:
                    async with aiohttp.ClientSession() as s:
                        color = await self.bot.get_color(ctx.author.id)
                        msg = await cpv2.send(
                            ctx,
                            content=f"-# <a:dotsload:1423056880854499338> Generating [{username}](https://roblox.com/users/{user_id}/profile)'s profile card..",
                            footer="Hang on tight, almost there!",
                            color=color
                        )
                        hexc = f"{color:06x}"
                        async with s.get(f"http://localhost:7686/card?username={username}&color={hexc}") as r:
                            if r.status != 200:
                                return await cpv2.edit_warn(msg, ctx, "Failed to generate card.")
                            data = await r.json()
                            b = base64.b64decode(data["image"])
                            file = discord.File(io.BytesIO(b), filename="card.png")
                            display_name = username
                            try:
                                j = data.get("meta", {})
                                display_name = j.get("displayName", username)
                                real_username = j.get("username", username)
                                user_id_local = data.get('id', user_id)
                            except:
                                real_username = username
                                user_id_local = user_id
                            profile_data = await self.roblox_profile_user(user_id_local)
                            about = profile_data.get("components", {}).get("About", {})
                            name_history = about.get("nameHistory", []) or []
                            if name_history:
                                shown = name_history[:20]
                                left = len(name_history) - 20
                                footer_text = "**Past Usernames:** " + ", ".join(f"`{n}`" for n in shown)
                                if left > 0:
                                    footer_text += f" (+{left} more)"
                            else:
                                footer_text = None
                            buttons = [
                                cpv2.link_button("Profile", f"https://roblox.com/users/{user_id_local}/profile", "<:Roblox:1263205555065983098>"),
                                cpv2.link_button("Rolimons", f"https://www.rolimons.com/player/{user_id_local}", "<:Rolimons:1263205684921499699>")
                            ]
                            await cpv2.edit(
                                msg,
                                ctx,
                                title=f"Viewing [{display_name} (@{real_username})](https://roblox.com/users/{user_id_local}/profile) - **{user_id_local}**",
                                media_url="attachment://card.png",
                                color=color,
                                files=[file],
                                buttons=buttons,
                                footer=footer_text if footer_text else None
                            )
                            return
            except Exception as e:
                return await cpv2.edit_warn(msg, ctx, str(e))

            loading_embed = discord.Embed(
                description=f"-# <a:dotsload:1423056880854499338> {ctx.author.mention}: scanning [**`{username}`**](https://roblox.com/users/{user_id}/profile)'s Roblox profile..",
                color=await self.bot.get_color(ctx.author.id)
            )
            message = await ctx.send(embed=loading_embed)

            async def get_profile_data():
                try:
                    return await self.roblox_profile_user(user_id)
                except:
                    return {}

            async def get_cloud_data():
                try:
                    return await self.roblox_cloud_user(user_id)
                except:
                    return {}

            profile_data, cloud_data, rolimons_data, ropro_discord, thumbnail_url, (has_hat, inventory_public) = await asyncio.gather(
                get_profile_data(),
                get_cloud_data(),
                fetch_rolimons(self.session, user_id),
                get_ropro_info(),
                get_thumbnail(),
                check_verified_hat(user_id)
            )

            components = profile_data.get("components", {})
            header = components.get("UserProfileHeader", {})
            about = components.get("About", {})
            roblox_badges = components.get("RobloxBadges", {})
            stats = components.get("Statistics", {})

            names = header.get("names", {})
            roblox_display_name = names.get("displayName") or names.get("primaryName") or username
            username_actual = names.get("username") or username
            counts = header.get("counts", {})
            friends_count = counts.get("friendsCount", 0)
            followers_count = counts.get("followersCount", 0)
            followings_count = counts.get("followingsCount", 0)
            
            is_verified = header.get("isVerified", False)

            created_unix = None
            joined = stats.get("userJoinedDate") or cloud_data.get("createTime")
            created_unix = None
            if joined:
                try:
                    created_unix = int(datetime.fromisoformat(joined.replace("Z", "+00:00")).timestamp())
                except:
                    created_unix = None

            visits = stats.get("numberOfVisits") or cloud_data.get("statistics", {}).get("visits") or 0
            lang_display = cloud_data.get("language_display", "")

            embed = discord.Embed(color=await self.bot.get_color(ctx.author.id))
            embed.set_author(name=f"{ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            embed.set_thumbnail(url=thumbnail_url)
            embed.title = f"{roblox_display_name} (@{username_actual})"
            profile_badges = [b.get("type", {}).get("value") for b in roblox_badges.get("robloxBadgeList", [])]

            is_premium = header.get("isPremium", False)
            is_admin = any(b == "Administrator" for b in profile_badges)

            if is_verified:
                embed.title += " <:roverified:1343047217899896885>"
            if is_premium:
                embed.title += " <:ropremium:1299803476506705920>"
            if is_admin:
                embed.title += " <:roadmin:1344495590834438195>"
            embed.url = f"https://roblox.com/users/{user_id}/profile"

            embed.description = (
                f"-# **{await format_number(friends_count)} Friends** | "
                f"**{await format_number(followers_count)} Followers** | "
                f"**{await format_number(followings_count)} Following**"
                + (f"\n-# <:language:1427375645733945424> {lang_display}" if lang_display else "")
            )

            embed.add_field(name="ID", value=f"`{user_id}`", inline=True)
            embed.add_field(name="Email Verified", value="Yes (Hat)" if has_hat else "No", inline=True)
            embed.add_field(name="Inventory", value="Public" if inventory_public else "Private", inline=True)

            stats_updated = rolimons_data.get('stats_updated')
            rap_val = rolimons_data.get('rap', 0)
            tot_val = rolimons_data.get('value', 0)

            embed.add_field(
                name="RAP",
                value=f"[{await format_number(rap_val)}](https://www.rolimons.com/player/{user_id})" + (f"\n-# <t:{stats_updated}:d>" if stats_updated else ""),
                inline=True
            )
            embed.add_field(
                name="Value",
                value=f"[{await format_number(tot_val)}](https://www.rolimons.com/player/{user_id})" + (f"\n-# <t:{stats_updated}:d>" if stats_updated else ""),
                inline=True
            )
            embed.add_field(name="Visits", value=f"{await format_number(visits)}", inline=True)

            if created_unix:
                embed.add_field(name="Created", value=f"<t:{created_unix}:F>", inline=True)
            else:
                embed.add_field(name="Created", value="Unknown", inline=True)

            badge_emojis = {
                "Homestead": "<:HomesteadBadge:1344516320523190273>",
                "Bricksmith": "<:BricksmithBadge:1344516271882113117>",
                "Combat Initiation": "<:CombatInitiationBadge:1344516287472074772>",
                "Veteran": "<:VeteranBadge:1344516347710799872>",
                "Warrior": "<:WarriorBadge:1344516351242534913>",
                "Friendship": "<:FriendshipBadge:1344516296380776530>",
                "Bloxxer": "<:BloxxerBadge:1344516227162443776>",
                "Inviter": "<:InviterBadge:1344516220594032670>",
                "Administrator": "<:AdministratorBadge:1344516214566686770>",
                "Official Model Maker": "<:OfficialModelMakerBadge:1344516334096220293>"
            }

            roblox_badge_list = roblox_badges.get("robloxBadges") or roblox_badges.get("robloxBadgeList") or []
            badge_names = []
            for b in roblox_badge_list:
                t = b.get("type", {})
                v = t.get("value")
                if v:
                    badge_names.append(v)

            badges_display = " ".join([badge_emojis.get(b, "") for b in badge_names])
            embed.add_field(name="Badges", value=badges_display if badges_display else "None", inline=True)

            about_text = about.get("description") or cloud_data.get("about") or ""
            if about_text:
                embed.add_field(name="Description", value=await truncate_text(about_text), inline=True)

            if ropro_discord:
                embed.description += f"\nDiscord (RoPro): `{ropro_discord}`"

            embed.set_footer(text="roblox.com", icon_url="https://git.cursi.ng/roblox_logo.png")

            view = discord.ui.View()
            view.add_item(discord.ui.Button(emoji="<:Roblox:1263205555065983098>", label="Profile", url=f"https://roblox.com/users/{user_id}/profile", style=discord.ButtonStyle.link))
            view.add_item(discord.ui.Button(emoji="<:Rolimons:1263205684921499699>", label="Rolimons", url=f"https://www.rolimons.com/player/{user_id}", style=discord.ButtonStyle.link))

            await message.edit(embed=embed, view=view)
        except Exception as e:
            await ctx.edit_warn(str(e), message)

    @roblox_user.autocomplete("username")
    async def autorobloxuser(self, interaction: discord.Interaction, current: str):
        try:
            results = await self.omni_search(current)
            return [
                app_commands.Choice(name=f"@{u} ({uid})", value=u)
                for (u, uid) in results
            ]
        except:
            return []

    @roblox.command(
        name="friends",
        description="View a Roblox user's friends list",
        aliases=["list"]
    )
    @app_commands.describe(username="The Roblox username to look up")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def friends(self, ctx: commands.Context, *, username: str):
        try:
            search_response = await self.roblox_request(
                "POST",
                "https://users.roblox.com/v1/usernames/users",
                headers={"accept": "application/json", "Content-Type": "application/json"},
                json={"usernames": [username], "excludeBannedUsers": True}
            )
            search_data = await search_response.json()
            if not search_data["data"]:
                await ctx.warn("No **Roblox user** found with that name.")
                return
            user_id = search_data["data"][0]["id"]
            loading = discord.Embed(
                description=f"-# <a:dotsload:1423056880854499338> {ctx.author.mention}: scanning [**`{username}`**](https://roblox.com/users/{user_id}/profile)'s friends list..",
                color=await self.bot.get_color(ctx.author.id)
            )
            msg = await ctx.send(embed=loading)
            profile = await self.roblox_profile_user(user_id)
            components = profile.get("components", {})
            header = components.get("UserProfileHeader", {})
            names = header.get("names", {}) or {}
            roblox_username = names.get("username") or username
            roblox_display = names.get("displayName") or roblox_username
            friends_ids = components.get("Friends", {}).get("friends", [])
            friends_ids = [str(x) for x in friends_ids]
            h1 = await self.roblox_request(
                "GET",
                f"https://thumbnails.roproxy.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Png"
            )
            headshot_url = (await h1.json())["data"][0]["imageUrl"]
            h2 = await self.roblox_request(
                "GET",
                f"https://thumbnails.roproxy.com/v1/users/avatar?userIds={user_id}&size=150x150&format=Png"
            )
            thumb_url = (await h2.json())["data"][0]["imageUrl"]
            display_author = f"{roblox_display} (@{roblox_username})"
            profile_url = f"https://roblox.com/users/{user_id}/profile"
            color = await self.bot.get_color(ctx.author.id)
            if not friends_ids:
                embed = discord.Embed(color=color)
                embed.set_author(name=display_author, url=profile_url, icon_url=headshot_url)
                embed.set_thumbnail(url=thumb_url)
                embed.description = "This user has no friends 😭"
                await msg.edit(embed=embed)
                return
            resolve = await self.roblox_request(
                "POST",
                "https://users.roblox.com/v1/users",
                headers={"accept": "application/json", "Content-Type": "application/json"},
                json={"userIds": friends_ids}
            )
            resolve_data = await resolve.json()
            flist = []
            for f in resolve_data.get("data", []):
                nm = f["name"]
                dn = f.get("displayName")
                fid = f["id"]
                s = f"[@{nm}](https://roblox.com/users/{fid})"
                if dn:
                    s += f" ({dn})"
                flist.append(s)
            pages = []
            buf = []
            for i, item in enumerate(flist, 1):
                buf.append(item)
                if i % 10 == 0 or i == len(flist):
                    pages.append("\n".join(buf))
                    buf = []
            embeds = []
            for p in pages:
                e = discord.Embed(color=color, description=p)
                e.set_author(name=display_author, url=profile_url, icon_url=headshot_url)
                e.set_thumbnail(url=thumb_url)
                e.set_footer(text=f"{len(flist)} friends", icon_url="https://git.cursi.ng/roblox_logo.png?v2")
                embeds.append(e)
            if len(embeds) == 1:
                await msg.edit(embed=embeds[0])
            else:
                from heist.framework.pagination import Paginator
                paginator = Paginator(ctx, embeds, embed=True, message=msg)
                await paginator.start()
        except Exception as e:
            await ctx.edit_warn(str(e), msg)

    @friends.autocomplete("username")
    async def friends_autocomplete(self, interaction: discord.Interaction, current: str):
        try:
            results = await self.omni_search(current)
            return [
                app_commands.Choice(name=f"@{u} ({uid})", value=u)
                for (u, uid) in results
            ]
        except:
            return []

    async def blendrobloxavatars(self, user_id1: int, user_id2: int) -> io.BytesIO:
        try:
            headshot1_response = await self.roblox_request(
                "GET",
                f"https://thumbnails.roproxy.com/v1/users/avatar-headshot?userIds={user_id1}&size=150x150&format=Png"
            )
            headshot1_data = await headshot1_response.json()
            headshot1_url = headshot1_data["data"][0]["imageUrl"]

            headshot2_response = await self.roblox_request(
                "GET",
                f"https://thumbnails.roproxy.com/v1/users/avatar-headshot?userIds={user_id2}&size=150x150&format=Png"
            )
            headshot2_data = await headshot2_response.json()
            headshot2_url = headshot2_data["data"][0]["imageUrl"]

            async with aiohttp.ClientSession() as s:
                async with s.get(headshot1_url) as r:
                    img1_bytes = await r.read()

                async with s.get(headshot2_url) as r:
                    img2_bytes = await r.read()

            def _render(b1: bytes, b2: bytes) -> bytes:
                img1 = Image.open(io.BytesIO(b1)).convert("RGBA")
                img2 = Image.open(io.BytesIO(b2)).convert("RGBA")
                img1 = img1.resize((150, 150))
                img2 = img2.resize((150, 150))
                canvas = Image.new("RGBA", (300, 150), (0, 0, 0, 0))
                canvas.paste(img1, (0, 0), img1)
                canvas.paste(img2, (150, 0), img2)
                buf = io.BytesIO()
                canvas.save(buf, format="PNG")
                return buf.getvalue()

            png_bytes = await asyncio.to_thread(_render, img1_bytes, img2_bytes)
            buf = io.BytesIO(png_bytes)
            buf.seek(0)
            return buf

        except Exception as e:
            return io.BytesIO()

    @roblox.command(
        name="blendavatars",
        description="Blend two Roblox avatar headshots side by side",
        aliases=["blendpfp", "blend", "combinepfp", "pfpblend"]
    )
    @app_commands.describe(
        username1="The first Roblox username",
        username2="The second Roblox username"
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def blendavatars(self, ctx: commands.Context, username1: str, username2: str):
        try:
            search1 = await self.roblox_request(
                "POST",
                "https://users.roblox.com/v1/usernames/users",
                headers={"accept":"application/json","Content-Type":"application/json"},
                json={"usernames":[username1],"excludeBannedUsers":True}
            )
            d1 = await search1.json()
            if not d1["data"]:
                await ctx.warn(f"No **Roblox user** found named `{username1}`.")
                return
            uid1 = d1["data"][0]["id"]
            u1 = d1["data"][0]["name"]

            search2 = await self.roblox_request(
                "POST",
                "https://users.roblox.com/v1/usernames/users",
                headers={"accept":"application/json","Content-Type":"application/json"},
                json={"usernames":[username2],"excludeBannedUsers":True}
            )
            d2 = await search2.json()
            if not d2["data"]:
                await ctx.warn(f"No **Roblox user** found named `{username2}`.")
                return
            uid2 = d2["data"][0]["id"]
            u2 = d2["data"][0]["name"]

            buf = await self.blendrobloxavatars(uid1, uid2)
            file = discord.File(buf, filename="blend.png")

            e = discord.Embed(
                color=await self.bot.get_color(ctx.author.id),
                description=f"[**{u1}**](https://roblox.com/users/{uid1}/profile) × [**{u2}**](https://roblox.com/users/{uid2}/profile)"
            )
            e.set_image(url="attachment://blend.png")

            await ctx.send(embed=e, file=file)
        except Exception as e:
            await ctx.edit_warn(str(e))

    @blendavatars.autocomplete("username1")
    async def blendavatars_autocomplete1(self, interaction: discord.Interaction, current: str):
        try:
            results = await self.omni_search(current)
            return [
                app_commands.Choice(name=f"@{u} ({uid})", value=u)
                for (u, uid) in results
            ]
        except:
            return []

    @blendavatars.autocomplete("username2")
    async def blendavatars_autocomplete2(self, interaction: discord.Interaction, current: str):
        try:
            results = await self.omni_search(current)
            return [
                app_commands.Choice(name=f"@{u} ({uid})", value=u)
                for (u, uid) in results
            ]
        except:
            return []

    @roblox.command(
        name="mutualfriends",
        description="View mutual friends between two Roblox users",
        aliases=["mutuals", "mutual"]
    )
    @app_commands.describe(
        username1="The first Roblox username",
        username2="The second Roblox username"
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def mutualfriends(self, ctx: commands.Context, username1: str, username2: str):
        try:
            search1 = await self.roblox_request(
                "POST",
                "https://users.roblox.com/v1/usernames/users",
                headers={"accept": "application/json", "Content-Type": "application/json"},
                json={"usernames": [username1], "excludeBannedUsers": True}
            )
            d1 = await search1.json()
            if not d1["data"]:
                await ctx.warn(f"No **Roblox user** found with the name `{username1}`.")
                return
            uid1 = d1["data"][0]["id"]
            u1 = d1["data"][0]["name"]
            d1n = d1["data"][0].get("displayName")

            search2 = await self.roblox_request(
                "POST",
                "https://users.roblox.com/v1/usernames/users",
                headers={"accept": "application/json", "Content-Type": "application/json"},
                json={"usernames": [username2], "excludeBannedUsers": True}
            )
            d2 = await search2.json()
            if not d2["data"]:
                await ctx.warn(f"No **Roblox user** found with the name `{username2}`.")
                return
            uid2 = d2["data"][0]["id"]
            u2 = d2["data"][0]["name"]
            d2n = d2["data"][0].get("displayName")

            color = await self.bot.get_color(ctx.author.id)

            link1 = f"[{u1}](https://roblox.com/users/{uid1}/profile)"
            link2 = f"[{u2}](https://roblox.com/users/{uid2}/profile)"

            topdesc = f"### {link1} × {link2}\n\n"

            loading = discord.Embed(
                description=f"-# <a:dotsload:1423056880854499338> {ctx.author.mention}: scanning mutual friends between [**`{u1}`**](https://roblox.com/users/{uid1}/profile) and [**`{u2}`**](https://roblox.com/users/{uid2}/profile)..",
                color=color
            )
            msg = await ctx.send(embed=loading)

            p1 = await self.roblox_profile_user(uid1)
            p2 = await self.roblox_profile_user(uid2)

            f1 = p1.get("components", {}).get("Friends", {}).get("friends", [])
            f2 = p2.get("components", {}).get("Friends", {}).get("friends", [])
            set2 = {int(x) for x in f2}
            mutual_ids = [int(x) for x in f1 if int(x) in set2]

            thumb = await self.roblox_request(
                "GET",
                f"https://thumbnails.roproxy.com/v1/users/avatar-headshot?userIds={uid1}&size=150x150&format=Png"
            )
            head = (await thumb.json())["data"][0]["imageUrl"]

            if not mutual_ids:
                buf = await self.blendrobloxavatars(uid1, uid2)
                file = discord.File(buf, filename="mutual.png")
                e = discord.Embed(description=topdesc + "These users have no mutual friends 😭", color=color)
                e.set_thumbnail(url="attachment://mutual.png")
                e.set_footer(text="0 mutual friends", icon_url="https://git.cursi.ng/roblox_logo.png?v2")
                await msg.edit(embed=e, attachments=[file])
                return

            resolve = await self.roblox_request(
                "POST",
                "https://users.roblox.com/v1/users",
                headers={"accept": "application/json", "Content-Type": "application/json"},
                json={"userIds": [str(x) for x in mutual_ids]}
            )
            rd = await resolve.json()

            out = []
            for f in rd.get("data", []):
                fid = f["id"]
                nm = f["name"]
                dn = f.get("displayName")
                s = f"[@{nm}](https://roblox.com/users/{fid}/profile)"
                if dn and dn != nm:
                    s += f" ({dn})"
                out.append(s)

            pages = []
            buf2 = []
            for i, x in enumerate(out, 1):
                buf2.append(x)
                if i % 10 == 0 or i == len(out):
                    pages.append("\n".join(buf2))
                    buf2 = []

            blend = await self.blendrobloxavatars(uid1, uid2)
            fblend = discord.File(blend, filename="mutual.png")

            embeds = []
            for p in pages:
                e = discord.Embed(color=color, description=topdesc + p)
                e.set_thumbnail(url="attachment://mutual.png")
                e.set_footer(text=f"{len(out)} mutual friends", icon_url="https://git.cursi.ng/roblox_logo.png?v2")
                embeds.append(e)

            if len(embeds) == 1:
                await msg.edit(embed=embeds[0], attachments=[fblend])
            else:
                await msg.edit(embed=embeds[0], attachments=[fblend])
                from heist.framework.pagination import Paginator
                paginator = Paginator(ctx, embeds, embed=True, message=msg)
                await paginator.start()
        except Exception as e:
            await ctx.edit_warn(str(e))

    @mutualfriends.autocomplete("username1")
    async def mutualfriends_autocomplete1(self, interaction: discord.Interaction, current: str):
        try:
            results = await self.omni_search(current)
            return [
                app_commands.Choice(name=f"@{u} ({uid})", value=u)
                for (u, uid) in results
            ]
        except:
            return []

    @mutualfriends.autocomplete("username2")
    async def mutualfriends_autocomplete2(self, interaction: discord.Interaction, current: str):
        try:
            results = await self.omni_search(current)
            return [
                app_commands.Choice(name=f"@{u} ({uid})", value=u)
                for (u, uid) in results
            ]
        except:
            return []

    @history.command(
        name="user",
        description="View a Roblox user's game history based on recent badges",
        aliases=["games", "played"]
    )
    @app_commands.describe(username="The Roblox username to look up")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def robloxuserhistory(self, ctx: commands.Context, *, username: str):
        async def get_game_details(places: list):
            try:
                roblox_games = {}
                for i in range(0, len(places), 30):
                    chunk = places[i:i + 30]
                    query = '&'.join(f'placeIds={pid}' for pid in chunk)
                    url = f"https://games.roproxy.com/v1/games/multiget-place-details?{query}"
                    response = await self.roblox_request('GET', url)
                    content_type = response.headers.get("Content-Type", "")
                    if "application/json" in content_type:
                        data = await response.json()
                        roblox_games.update({game['placeId']: game['name'] for game in data})
                    else:
                        text = await response.text()
                return roblox_games
            except Exception:
                return {}
                
        async def get_awarded_dates(user_id: int, badge_ids: list):
            try:
                response = await self.roblox_request(
                    'GET',
                    f"https://badges.roproxy.com/v1/users/{user_id}/badges/awarded-dates?badgeIds={','.join(map(str, badge_ids))}"
                )
                data = await response.json()
                return {item['badgeId']: item['awardedDate'] for item in data.get('data', [])}
            except:
                return {}

        try:
            search_response = await self.roblox_request(
                'POST',
                'https://users.roblox.com/v1/usernames/users',
                headers={'accept': 'application/json', 'Content-Type': 'application/json'},
                json={'usernames': [username], 'excludeBannedUsers': True}
            )
            user_data = await search_response.json()
            
            if not user_data['data']:
                await ctx.warn("No **Roblox user** found with that name.")
                return
            
            user_id = user_data['data'][0]['id']
            loading_embed = discord.Embed(
                description=f"-# <a:dotsload:1423056880854499338> {ctx.author.mention}: scanning [**`{username}`**](https://roblox.com/users/{user_id}/profile)'s game history..",
                color=await self.bot.get_color(ctx.author.id)
            )
            message = await ctx.send(embed=loading_embed)
            roblox_username = user_data['data'][0]['name']
            roblox_display_name = user_data['data'][0].get('displayName')
            profile_url = f"https://roblox.com/users/{user_id}/profile"

            thumbnail_response = await self.roblox_request(
                'GET',
                f"https://thumbnails.roproxy.com/v1/users/avatar?userIds={user_id}&size=150x150&format=Png"
            )
            thumbnail_data = await thumbnail_response.json()
            thumbnail_url = thumbnail_data['data'][0]['imageUrl']

            headshot_response = await self.roblox_request(
                'GET',
                f"https://thumbnails.roproxy.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Png"
            )
            headshot_data = await headshot_response.json()
            headshot_url = headshot_data['data'][0]['imageUrl']

            badges_response = await self.roblox_request(
                'GET',
                f'https://badges.roproxy.com/v1/users/{user_id}/badges?limit=100&sortOrder=Desc'
            )
            badges_data = await badges_response.json()
            
            author_name = f"{roblox_display_name} (@{roblox_username})" if roblox_display_name else roblox_username
            
            if not badges_data.get('data'):
                embed = discord.Embed()
                embed.set_author(name=author_name, url=profile_url, icon_url=headshot_url)
                embed.set_thumbnail(url=thumbnail_url)
                embed.description = "No recent game history found (based on badges)."
                await message.edit(embed=embed)
                return

            badge_ids = [badge['id'] for badge in badges_data['data']]
            awarded_dates = await get_awarded_dates(user_id, badge_ids)
            
            game_history = {}
            places = []

            for badge in badges_data['data']:
                badge_id = badge['id']
                game_id = badge['awarder']['id']
                
                if badge_id not in awarded_dates:
                    continue
                    
                awarded_date = awarded_dates[badge_id]
                awarded_timestamp = int(datetime.fromisoformat(awarded_date[:-1]).timestamp())
                
                if game_id not in game_history or awarded_timestamp > game_history[game_id]['timestamp']:
                    game_history[game_id] = {
                        'name': f"Game {game_id}",
                        'url': f"https://roblox.com/games/{game_id}",
                        'timestamp': awarded_timestamp
                    }
                    if game_id not in places:
                        places.append(game_id)

            if places:
                game_names = await get_game_details(places)
                for game_id in game_history:
                    if game_id in game_names:
                        game_history[game_id]['name'] = game_names[game_id]

            sorted_games = sorted(game_history.values(), key=lambda x: x['timestamp'], reverse=True)
            
            formatted_games = []
            for game in sorted_games:
                formatted_games.append(
                    f"• **[{game['name']}]({game['url']})**\n"
                    f"-# <t:{game['timestamp']}:d>, <t:{game['timestamp']}:T> (<t:{game['timestamp']}:R>)"
                )

            pages = []
            current_page = []
            for i, game in enumerate(formatted_games, 1):
                current_page.append(game)
                if i % 5 == 0 or i == len(formatted_games):
                    pages.append("\n\n".join(current_page))
                    current_page = []

            color = await self.bot.get_color(ctx.author.id)
            
            for i in range(len(pages)):
                pages[i] = (
                    "> *⚠️ **NOTE**: This list doesn't include all games. This information is based off the user's recent badges.*\n"
                    + pages[i]
                )

            embeds = []
            for i, page in enumerate(pages):
                embed = discord.Embed(
                    color=color,
                    description=page
                )
                embed.set_author(name=author_name, url=profile_url, icon_url=headshot_url)
                embed.set_thumbnail(url=thumbnail_url)
                embed.set_footer(text=f"{i + 1}/{len(pages)} • Total games: {len(sorted_games)}", icon_url="https://git.cursi.ng/roblox_logo.png?v2")
                embeds.append(embed)

            if len(embeds) == 1:
                await message.edit(embed=embeds[0])
            else:
                from heist.framework.pagination import Paginator
                paginator = Paginator(ctx, embeds, embed=True, message=message)
                await paginator.start()

        except Exception as e:
            await ctx.edit_warn(str(e), message)
            
    @robloxuserhistory.autocomplete("username")
    async def robloxuserhistory_autocomplete(self, interaction: discord.Interaction, current: str):
        try:
            results = await self.omni_search(current)
            return [
                app_commands.Choice(name=f"@{u} ({uid})", value=u)
                for (u, uid) in results
            ]
        except:
            return []

    @roblox.command(
        name="emotes",
        description="View a Roblox user's equipped emotes"
    )
    @app_commands.describe(username="The Roblox username to look up")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def emotes(self, ctx: commands.Context, *, username: str):
        try:
            search_response = await self.roblox_request(
                'POST',
                'https://users.roblox.com/v1/usernames/users',
                headers={'accept': 'application/json', 'Content-Type': 'application/json'},
                json={'usernames': [username], 'excludeBannedUsers': True}
            )
            user_data = await search_response.json()
            
            if not user_data['data']:
                await ctx.warn("No **Roblox user** found with that name.")
                return
            
            user_id = user_data['data'][0]['id']
            loading_embed = discord.Embed(
                description=f"-# <a:dotsload:1423056880854499338> {ctx.author.mention}: scanning [**`{username}`**](https://roblox.com/users/{user_id}/profile)'s equipped emotes..",
                color=await self.bot.get_color(ctx.author.id)
            )
            message = await ctx.send(embed=loading_embed)
            roblox_username = user_data['data'][0]['name']
            roblox_display_name = user_data['data'][0].get('displayName')
            profile_url = f"https://roblox.com/users/{user_id}/profile"

            thumbnail_response = await self.roblox_request(
                'GET',
                f"https://thumbnails.roproxy.com/v1/users/avatar?userIds={user_id}&size=150x150&format=Png"
            )
            thumbnail_data = await thumbnail_response.json()
            thumbnail_url = thumbnail_data['data'][0]['imageUrl']

            headshot_response = await self.roblox_request(
                'GET',
                f"https://thumbnails.roproxy.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Png"
            )
            headshot_data = await headshot_response.json()
            headshot_url = headshot_data['data'][0]['imageUrl']

            avatar_response = await self.roblox_request(
                'GET',
                f'https://avatar.roproxy.com/v1/users/{user_id}/avatar'
            )
            avatar_data = await avatar_response.json()
            
            author_name = f"{roblox_display_name} (@{roblox_username})" if roblox_display_name else roblox_username
            color = await self.bot.get_color(ctx.author.id)

            if not avatar_data.get('emotes'):
                embed = discord.Embed(color=color)
                embed.set_author(name=author_name, url=profile_url, icon_url=headshot_url)
                embed.set_thumbnail(url=thumbnail_url)
                embed.description = "This user has no equipped emotes."
                await message.edit(embed=embed)
                return

            emotes_list = []
            for emote in avatar_data['emotes']:
                emote_id = emote['assetId']
                emote_name = emote['assetName']
                position = emote['position']
                emotes_list.append(f"`#{position}`: [{emote_name}](https://www.roblox.com/catalog/{emote_id})")

            embeds = []
            chunks = [emotes_list[i:i + 10] for i in range(0, len(emotes_list), 10)]
            
            for i, chunk in enumerate(chunks, 1):
                embed = discord.Embed(
                    color=color,
                    title="Equipped Emotes",
                    description="\n".join(chunk)
                )
                embed.set_author(name=author_name, url=profile_url, icon_url=headshot_url)
                embed.set_thumbnail(url=thumbnail_url)
                embed.set_footer(icon_url="https://git.cursi.ng/roblox_logo.png?v2")
                embeds.append(embed)

            if len(embeds) == 1:
                embeds[0].set_footer(text=None)
                await message.edit(embed=embeds[0])
            else:
                from heist.framework.pagination import Paginator
                paginator = Paginator(ctx, embeds, embed=True, message=message)
                await paginator.start()

        except Exception as e:
            await ctx.edit_warn(str(e), message)

    @emotes.autocomplete("username")
    async def robloxemotes(self, interaction: discord.Interaction, current: str):
        try:
            results = await self.omni_search(current)
            return [
                app_commands.Choice(name=f"@{u} ({uid})", value=u)
                for (u, uid) in results
            ]
        except:
            return []

    @roblox.command(
        name="avataritems",
        description="View a Roblox user's currently worn items",
        aliases=["ai"]
    )
    @app_commands.describe(username="The Roblox username to look up")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def avataritems(self, ctx: commands.Context, *, username: str):
        try:
            search_response = await self.roblox_request(
                'POST',
                'https://users.roblox.com/v1/usernames/users',
                headers={'accept': 'application/json', 'Content-Type': 'application/json'},
                json={'usernames': [username], 'excludeBannedUsers': True}
            )
            user_data = await search_response.json()
            if not user_data['data']:
                await ctx.warn("No **Roblox user** found with that name.")
                return
            user_id = user_data['data'][0]['id']
            loading_embed = discord.Embed(
                description=f"-# <a:dotsload:1423056880854499338> {ctx.author.mention}: scanning [**`{username}`**](https://roblox.com/users/{user_id}/profile)'s worn items..",
                color=await self.bot.get_color(ctx.author.id)
            )
            message = await ctx.send(embed=loading_embed)
            roblox_username = user_data['data'][0]['name']
            roblox_display_name = user_data['data'][0].get('displayName')
            profile_url = f"https://roblox.com/users/{user_id}/profile"
            thumbnail_response = await self.roblox_request(
                'GET',
                f"https://thumbnails.roproxy.com/v1/users/avatar?userIds={user_id}&size=150x150&format=Png"
            )
            thumbnail_data = await thumbnail_response.json()
            thumbnail_url = thumbnail_data['data'][0]['imageUrl']
            headshot_response = await self.roblox_request(
                'GET',
                f"https://thumbnails.roproxy.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Png"
            )
            headshot_data = await headshot_response.json()
            headshot_url = headshot_data['data'][0]['imageUrl']
            avatar_response = await self.roblox_request(
                'GET',
                f'https://avatar.roproxy.com/v1/users/{user_id}/avatar'
            )
            avatar_data = await avatar_response.json()
            author_name = f"{roblox_display_name} (@{roblox_username})" if roblox_display_name else roblox_username
            color = await self.bot.get_color(ctx.author.id)
            if not avatar_data.get('assets'):
                embed = discord.Embed(color=color)
                embed.set_author(name=author_name, url=profile_url, icon_url=headshot_url)
                embed.set_thumbnail(url=thumbnail_url)
                embed.description = "This user has no visible worn items."
                await message.edit(embed=embed)
                return
            asset_ids = [str(item['id']) for item in avatar_data['assets']]
            details_response = await self.roblox_request(
                'POST',
                'https://catalog.roblox.com/v1/catalog/items/details',
                headers={'accept': 'application/json', 'Content-Type': 'application/json'},
                json={"items": [{"itemType": "Asset", "id": int(asset_id)} for asset_id in asset_ids]}
            )
            details_data = await details_response.json()
            asset_details = {str(item["id"]): item for item in details_data.get("data", [])}
            LIMITED_EMOJI = "<:star:1418003034306510919>"
            LIMITED_U_EMOJI = "(U)"
            UGC_EMOJI = "(UGC)"
            CHECKED_ITEMS = {"15093053680", "139607718"}
            CLASSIC_CLOTHING_TYPES = [11, 12, 13]
            ANIMATION_TYPES = [51, 52, 48, 54, 55, 53, 50]
            items_list = []
            for item in avatar_data['assets']:
                asset_id = str(item['id'])
                asset_name = item['name']
                detail = asset_details.get(asset_id, {})
                emojis = []
                restrictions = detail.get("itemRestrictions", [])
                if asset_id in CHECKED_ITEMS:
                    emojis.append("<:check:1344689360527949834>")
                if "LimitedUnique" in restrictions:
                    emojis.append(LIMITED_U_EMOJI)
                elif "Limited" in restrictions:
                    emojis.append(LIMITED_EMOJI)
                if detail.get("creatorType") == "User" and detail.get("creatorTargetId") != 1 and detail.get("assetType") not in CLASSIC_CLOTHING_TYPES + ANIMATION_TYPES:
                    emojis.append(UGC_EMOJI)
                elif detail.get("creatorType") == "Group" and detail.get("creatorTargetId") != 1 and detail.get("assetType") not in CLASSIC_CLOTHING_TYPES + ANIMATION_TYPES:
                    emojis.append(UGC_EMOJI)
                emoji_str = " ".join(emojis)
                items_list.append(f"[{asset_name}](https://www.roblox.com/catalog/{asset_id}) {emoji_str}" if emoji_str else f"[{asset_name}](https://www.roblox.com/catalog/{asset_id})")
            embeds = []
            chunks = [items_list[i:i + 10] for i in range(0, len(items_list), 10)]
            for i, chunk in enumerate(chunks, 1):
                embed = discord.Embed(
                    color=color,
                    title="Wearing Items",
                    description="\n".join(chunk)
                )
                embed.set_author(name=author_name, url=profile_url, icon_url=headshot_url)
                embed.set_thumbnail(url=thumbnail_url)
                embed.set_footer(icon_url="https://git.cursi.ng/roblox_logo.png?v2")
                embeds.append(embed)
            if len(embeds) == 1:
                embeds[0].set_footer(text=None)
                await message.edit(embed=embeds[0])
            else:
                from heist.framework.pagination import Paginator
                paginator = Paginator(ctx, embeds, embed=True, message=message)
                await paginator.start()
        except Exception as e:
            await ctx.edit_warn(str(e), message)

    @avataritems.autocomplete("username")
    async def avataritems(self, interaction: discord.Interaction, current: str):
        try:
            results = await self.omni_search(current)
            return [
                app_commands.Choice(name=f"@{u} ({uid})", value=u)
                for (u, uid) in results
            ]
        except:
            return []

    @roblox.command(
        name="necklaces",
        description="Search for initial necklaces in a user's inventory",
        aliases=["initials", "in"]
    )
    @app_commands.describe(username="The Roblox username to search")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def necklaces(self, ctx: commands.Context, *, username: str):
        try:
            search_response = await self.roblox_request(
                'POST',
                'https://users.roblox.com/v1/usernames/users',
                headers={'accept': 'application/json', 'Content-Type': 'application/json'},
                json={'usernames': [username], 'excludeBannedUsers': True}
            )
            user_data = await search_response.json()
            
            if not user_data['data']:
                await ctx.warn("No **Roblox user** found with that name.", message)
                return

            user_id = user_data['data'][0]['id']
            loading_embed = discord.Embed(
                description=f"-# <a:dotsload:1423056880854499338> {ctx.author.mention}: scanning [**`{username}`**](https://roblox.com/users/{user_id}/profile)'s Roblox profile..",
                color=await self.bot.get_color(ctx.author.id)
            )
            message = await ctx.send(embed=loading_embed)
            roblox_username = user_data['data'][0]['name']
            roblox_display_name = user_data['data'][0].get('displayName')
            profile_url = f"https://www.roblox.com/users/{user_id}/profile"

            thumbnail_response = await self.roblox_request(
                'GET',
                f"https://thumbnails.roproxy.com/v1/users/avatar?userIds={user_id}&size=150x150&format=Png"
            )
            thumbnail_data = await thumbnail_response.json()
            thumbnail_url = thumbnail_data['data'][0]['imageUrl']

            headshot_response = await self.roblox_request(
                'GET',
                f"https://thumbnails.roproxy.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Png"
            )
            headshot_data = await headshot_response.json()
            headshot_url = headshot_data['data'][0]['imageUrl']

            author_name = f"{roblox_display_name} (@{roblox_username})" if roblox_display_name else roblox_username

            inventory_response = await self.roblox_request(
                'GET',
                f'https://inventory.roproxy.com/v2/users/{user_id}/inventory/43?cursor=&limit=100'
            )
            inventory_data = await inventory_response.json()

            if 'errors' in inventory_data and any(e.get('code') == 4 for e in inventory_data['errors']):
                embed = discord.Embed(
                    title="Inventory Private",
                    description=f"**`{roblox_username}`**'s inventory is **private**.",
                    color=discord.Color.red()
                )
                embed.set_author(name=author_name, url=profile_url, icon_url=headshot_url)
                embed.set_thumbnail(url=thumbnail_url)
                await message.edit(embed=embed)
                return

            initial_necklaces = []
            for item in inventory_data.get('data', []):
                if not item.get('assetName'):
                    continue
                if "initial" in item['assetName'].lower() and ("necklace" in item['assetName'].lower() or "chain" in item['assetName'].lower()):
                    initial_necklaces.append(item)

            has_max_items = len(inventory_data.get('data', [])) == 100
            warning_text = "\n\n⚠ This search can only see up to **100** accessories, and the user has more than that." if has_max_items else ""

            if not initial_necklaces:
                embed = discord.Embed(
                    title="No Initial Necklaces Found",
                    description=f"No initial necklaces were found in `{roblox_username}`'s inventory.{warning_text}",
                    color=discord.Color.red()
                )
                embed.set_author(name=author_name, url=profile_url, icon_url=headshot_url)
                embed.set_thumbnail(url=thumbnail_url)
                await message.edit(embed=embed)
                return

            necklaces_list = []
            for i, necklace in enumerate(initial_necklaces, 1):
                necklaces_list.append(f"`#{i}`: [{necklace['assetName']}](https://www.roblox.com/catalog/{necklace['assetId']})")

            embeds = []
            chunks = [necklaces_list[i:i + 10] for i in range(0, len(necklaces_list), 10)]
            color = await self.bot.get_color(ctx.author.id)
            total_text = f"Total Necklaces: **`{len(initial_necklaces)}`**{warning_text}\n\n**Items**\n"
            
            for i, chunk in enumerate(chunks, 1):
                embed = discord.Embed(
                    title=f"{roblox_display_name}'s Initial Necklaces",
                    description=total_text + "\n".join(chunk),
                    color=color
                )
                embed.set_author(name=author_name, url=profile_url, icon_url=headshot_url)
                embed.set_thumbnail(url=thumbnail_url)
                embed.set_footer(icon_url="https://git.cursi.ng/roblox_logo.png?v2")
                embeds.append(embed)

            if len(embeds) == 1:
                embeds[0].set_footer(text=None)
                await message.edit(embed=embeds[0])
            else:
                from heist.framework.pagination import Paginator
                paginator = Paginator(ctx, embeds, embed=True, message=message)
                await paginator.start()

        except Exception as e:
            await ctx.edit_warn(str(e), message)

    @necklaces.autocomplete("username")
    async def robloxnecklaces(self, interaction: discord.Interaction, current: str):
        try:
            results = await self.omni_search(current)
            return [
                app_commands.Choice(name=f"@{u} ({uid})", value=u)
                for (u, uid) in results
            ]
        except:
            return []

    @roblox.command(
        name="avatars",
        description="View a Roblox user's saved avatars",
        aliases=["outfits", "avs"]
    )
    @app_commands.describe(username="The Roblox username to look up")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def avatars(self, ctx: commands.Context, *, username: str):
        try:
            user_response = await self.roblox_request(
                'POST',
                'https://users.roblox.com/v1/usernames/users',
                headers={'accept': 'application/json', 'Content-Type': 'application/json'},
                json={'usernames': [username], 'excludeBannedUsers': True}
            )
            user_data = await user_response.json()

            if not user_data['data']:
                await ctx.warn("No **Roblox user** found with that name.")
                return

            user_id = user_data['data'][0]['id']
            roblox_username = user_data['data'][0]['name']
            roblox_display_name = user_data['data'][0].get('displayName', roblox_username)
            profile_url = f"https://roblox.com/users/{user_id}/profile"

            retry_delays = [1, 2, 3]
            for attempt, delay in enumerate(retry_delays, start=1):
                try:
                    outfits_task = self.roblox_request('GET', f'https://avatar.roproxy.com/v1/users/{user_id}/outfits?page=1&itemsPerPage=25&isEditable=true')
                    thumbnail_task = self.roblox_request('GET', f"https://thumbnails.roproxy.com/v1/users/avatar?userIds={user_id}&size=420x420&format=Png&isCircular=false&thumbnailType=3d")
                    outfits_response, thumbnail_response = await asyncio.gather(outfits_task, thumbnail_task)
                    outfits_data = await outfits_response.json()
                    outfits = outfits_data.get('data', [])
                    break
                except:
                    if attempt == len(retry_delays):
                        raise
                    await asyncio.sleep(delay)

            if not outfits:
                await ctx.warn("This user has no saved avatars.")
                return

            thumbnail_data = await thumbnail_response.json()
            thumbnail_url = thumbnail_data['data'][0]['imageUrl']

            dropdown_data = []
            for i, outfit in enumerate(outfits):
                dropdown_data.append({
                    'label': outfit['name'][:100],
                    'description': f"Avatar #{i+1}",
                    'value': str(outfit['id'])
                })

            color = await self.bot.get_color(ctx.author.id)

            embed = discord.Embed(color=color)
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
            embed.title = f"{roblox_display_name} (@{roblox_username})"
            embed.url = profile_url
            embed.set_footer(text="showing current avatar - select a saved avatar below", icon_url="https://git.cursi.ng/roblox_logo.png?v2")
            embed.set_image(url=thumbnail_url)

            view = discord.ui.View(timeout=240)

            async def dropdown_callback(interaction: discord.Interaction):
                selected_value = interaction.data['values'][0]
                selected_index = next(i for i, o in enumerate(dropdown_data) if o['value'] == selected_value)
                outfit_id = dropdown_data[selected_index]['value']

                response = await self.roblox_request('GET', f"https://thumbnails.roproxy.com/v1/users/outfits?userOutfitIds={outfit_id}&size=420x420&format=Png")
                outfit_data = await response.json()
                outfit_url = outfit_data['data'][0]['imageUrl']

                new_embed = discord.Embed(color=color)
                new_embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)
                new_embed.title = f"{roblox_display_name} (@{roblox_username})"
                new_embed.url = profile_url
                new_embed.set_footer(
                    text=f"avatar {selected_index + 1} of {len(outfits)} ({dropdown_data[selected_index]['label']})",
                    icon_url="https://git.cursi.ng/roblox_logo.png?v2"
                )
                new_embed.set_image(url=outfit_url)

                await interaction.response.edit_message(embed=new_embed, view=view)

            dropdown = discord.ui.Select(
                placeholder="Select an avatar...",
                options=[discord.SelectOption(label=o['label'], description=o['description'], value=o['value']) for o in dropdown_data]
            )
            dropdown.callback = dropdown_callback
            view.add_item(dropdown)

            await ctx.send(embed=embed, view=view)

        except Exception as e:
            await ctx.warn(str(e))
            
    @avatars.autocomplete("username")
    async def robloxavatars(self, interaction: discord.Interaction, current: str):
        try:
            results = await self.omni_search(current)
            return [
                app_commands.Choice(name=f"@{u} ({uid})", value=u)
                for (u, uid) in results
            ]
        except:
            return []

    @roblox.command(
        name="devex",
        description="Calculate the USD value you'd get from Developer Exchange",
    )
    @app_commands.describe(amount="The amount of Robux, e.g., 100k, 1m, 10b")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def devex(self, ctx: commands.Context, *, amount: str):
        amount = amount.lower().replace(",", "").strip()
        match = re.match(r"^(\d+(?:\.\d+)?)([kmb]?)$", amount)

        if not match:
            await ctx.warn(
                "Invalid value entered. Please enter a valid amount like `100k`, `1m`, or `10b`.",
                ephemeral=True
            )
            return

        amount_value, suffix = match.groups()
        amount_value = float(amount_value)

        if suffix == 'k':
            amount_value *= 1_000
        elif suffix == 'm':
            amount_value *= 1_000_000
        elif suffix == 'b':
            amount_value *= 1_000_000_000

        usd_value = amount_value * 0.0037975
        usd_value_str = f"${usd_value:,.2f}"
        amount_value_str = f"{int(amount_value):,}"

        await ctx.send(
            f"**Amount**: **`{amount_value_str}`** <:robux:1296215059600642088>\n"
            f"**DevEx value**: **`{usd_value_str}`** 💵"
        )

    @roblox.command(
        name="calctax",
        description="Calculate Robux taxes",
        aliases=["tax"]
    )
    @app_commands.describe(amount="Amount of Robux")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def calctax(self, ctx: commands.Context, *, amount: str):
        amount = amount.lower().replace(",", "").strip()
        match = re.match(r"^(\d+(?:\.\d+)?)([kmb]?)$", amount)

        if not match:
            await ctx.warn(
                "Invalid value entered. Please enter a valid amount like `1k`, `10m`, etc.", 
                ephemeral=True
            )
            return

        amount_value, suffix = match.groups()
        amount_value = float(amount_value)

        if suffix == 'k':
            amount_value *= 1_000
        elif suffix == 'm':
            amount_value *= 1_000_000
        elif suffix == 'b':
            amount_value *= 1_000_000_000

        tax_rate = 0.7
        after_tax = math.ceil(amount_value * tax_rate)
        to_send_full = math.ceil(amount_value / tax_rate)

        amount_value_str = f"{int(amount_value):,}"
        after_tax_str = f"{after_tax:,}"
        to_send_full_str = f"{to_send_full:,}"

        await ctx.send(
            f"**Initial amount**: **`{amount_value_str}`** <:robux:1296215059600642088>\n"
            f"**After tax**: **`{after_tax_str}`** <:robux:1296215059600642088>\n"
            f"**Total cost for sending sum A/T**: **`{to_send_full_str}`** <:robux:1296215059600642088>"
    )

    @render.command(name="asset", description="Render a Roblox asset into a 3D model")
    @app_commands.describe(assetid="The ID or URL of the Roblox UGC item")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def render_asset(self, ctx: commands.Context, *, assetid: str):
        try:
            if assetid.isdigit():
                asset_id = assetid
            else:
                match = await asyncio.to_thread(lambda: re.search(r'/(\d+)(?:/|$)', assetid))
                if not match:
                    await ctx.warn("Invalid UGC URL or ID.")
                    return
                asset_id = match.group(1)

            async with self.session.get(f"https://thumbnails.roproxy.com/v1/assets-thumbnail-3d?assetId={asset_id}") as response:
                if response.status != 200:
                    await ctx.warn("Failed to fetch thumbnail metadata.")
                    return
                text = await response.text()
            jsond = await asyncio.to_thread(json.loads, text)

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 OPR/107.0.0.0',
                'Cookie': f'.ROBLOSECURITY={get_cookie()}'
            }

            image_url = jsond.get("imageUrl")
            if not image_url:
                await ctx.warn("No 3D thumbnail available for this asset.")
                return

            async with self.session.get(image_url, headers=headers) as meta_response:
                if meta_response.status != 200:
                    await ctx.warn("Failed to fetch asset metadata.")
                    return
                meta_text = await meta_response.text()
            metadata = await asyncio.to_thread(json.loads, meta_text)

            mtl_id = metadata["mtl"]
            obj_id = metadata["obj"]
            texture_ids = metadata.get("textures", [])

            async def try_fetch_file(fid):
                cdn_prefixes = [f"t{i}.rbxcdn.com" for i in range(8)]
                for cdn in cdn_prefixes:
                    url = f"https://{cdn}/{fid}"
                    try:
                        r = await self.session.get(url)
                        if r.status == 200:
                            data = await r.read()
                            await r.release()
                            return url, data
                        else:
                            await r.release()
                    except:
                        continue
                return None, None

            obj_url, obj_data = await try_fetch_file(obj_id)
            if obj_data is None:
                await ctx.warn("Failed to fetch .obj file.")
                return

            mtl_url, mtl_data = await try_fetch_file(mtl_id)
            if mtl_data is None:
                await ctx.warn("Failed to fetch .mtl file.")
                return

            textures = []
            for i, tex_id in enumerate(texture_ids):
                texture_data = None
                cdn_prefixes = [f"t{i}.rbxcdn.com" for i in range(8)]
                for cdn in cdn_prefixes:
                    url = f"https://{cdn}/{tex_id}"
                    try:
                        r = await self.session.get(url)
                        if r.status == 200:
                            texture_data = await r.read()
                            await r.release()
                            break
                        else:
                            await r.release()
                    except:
                        continue
                if texture_data is None:
                    await ctx.warn(f"Failed to fetch texture {i}.")
                    return
                textures.append((f"{asset_id}_{i}.png", texture_data))

            async def fix_mtl_texture_names(mtl_bytes, texture_name):
                lines = mtl_bytes.decode().splitlines()
                fixed_lines = []
                for line in lines:
                    if line.startswith("map_Ka") or line.startswith("map_Kd") or line.startswith("map_d"):
                        fixed_lines.append(f"{line.split()[0]} {texture_name}")
                    else:
                        fixed_lines.append(line)
                return "\n".join(fixed_lines).encode()

            async def create_zip(obj_data, mtl_data, textures, asset_id):
                fixed_mtl = await fix_mtl_texture_names(mtl_data, textures[0][0])
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w') as zipf:
                    zipf.writestr(f"{asset_id}.obj", obj_data)
                    zipf.writestr(f"{asset_id}.mtl", fixed_mtl)
                    for name, data in textures:
                        zipf.writestr(name, data)
                zip_buffer.seek(0)
                return zip_buffer

            zip_buffer = await create_zip(obj_data, mtl_data, textures, asset_id)

            await ctx.send(file=discord.File(zip_buffer, filename=f"asset_{asset_id}_heist.zip"))
        except Exception as e:
            await ctx.warn(str(e))

    @commands.hybrid_command(
        name="roblox2discord",
        description="✨ Find a Discord user's linked Roblox account",
        aliases=["r2d"],
    )
    @app_commands.describe(username="The Roblox username to look up")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @donor_only()
    async def roblox2discord(self, ctx, username: str):
        try:
            loading_embed = discord.Embed(
                description="-# <a:dotsload:1423056880854499338> " + ctx.author.mention +
                            ": looking up **`" + username + "`**'s Discord..",
                color=await self.bot.get_color(ctx.author.id)
            )
            message = await ctx.send(embed=loading_embed)

            async with self.session.get(
                "http://localhost:7690/roblox2discord",
                params={"username": username}
            ) as api:
                if api.status != 200:
                    return await ctx.edit_warn("Could not find a linked Discord for this Roblox user.", message)
                data = await api.json()

            roblox_id = data["roblox_id"]
            roblox_name = data["roblox_name"]
            roblox_display_name = data["roblox_display_name"]
            avatar = data["avatar"]
            results = data["results"]

            profile_url = f"https://roblox.com/users/{roblox_id}/profile"

            embed = discord.Embed(color=await self.bot.get_color(ctx.author.id))

            if roblox_display_name:
                embed.set_author(
                    name=f"{roblox_display_name} (@{roblox_name})",
                    url=profile_url,
                    icon_url=avatar
                )
            else:
                embed.set_author(
                    name=roblox_name,
                    url=profile_url,
                    icon_url=avatar
                )

            final_desc = ""

            for entry in results:
                did = entry["discord_id"]
                last = entry["last_updated"]
                src = entry["source"]

                if src == "bloxlink":
                    icon = "<:bloxlink:1441902218927276113>"
                elif src == "rover":
                    icon = "<:rover:1441902221481738442>"
                elif src == "ropro":
                    icon = "<:ropro:1441902316216692866>"
                else:
                    icon = "🔗"

                try:
                    du = await self.bot.fetch_user(int(did))
                    line = (
                        f"{icon} **Discord:** [{du}](discord://-/users/{did}) ({did})\n"
                        f"<:pointdrl:1318643571317801040> Updated: <t:{int(datetime.fromisoformat(last).timestamp())}:R>\n"
                    )
                except:
                    line = (
                        f"{icon} Discord: **{did}** (could not fetch)\n"
                        f"<:pointdrl:1318643571317801040> Updated: <t:{int(datetime.fromisoformat(last).timestamp())}:R>\n"
                    )

                final_desc += line + "\n"

            if not final_desc:
                final_desc = "No linked Discord accounts found."

            embed.description = final_desc
            embed.set_thumbnail(url=avatar)
            embed.set_footer(text="roblox.com", icon_url="https://git.cursi.ng/roblox_logo.png?v2")

            await message.edit(embed=embed)

        except Exception as e:
            await ctx.edit_warn(
                "An error occurred while searching for linked Discord.\n" + str(e),
                message
            )

    @roblox2discord.autocomplete("username")
    async def autoroblox2discord(self, interaction: discord.Interaction, current: str):
        try:
            results = await self.omni_search(current)
            return [
                app_commands.Choice(name=f"@{u} ({uid})", value=u)
                for (u, uid) in results
            ]
        except:
            return []

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @donor_only()
    async def discord2roblox2(self, interaction: discord.Interaction, user: discord.User):
        ctx = await self.bot.get_context(interaction)
        ctx.author = interaction.user
        ctx.message = interaction
        await self.discord2roblox(ctx, user)

    @commands.hybrid_command(
        name="discord2roblox",
        description="✨ Find a Discord user's linked Roblox account",
        aliases=["d2r"]
    )
    @app_commands.describe(user="The Discord user to look up")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @donor_only()
    async def discord2roblox(self, ctx: commands.Context, user: Optional[discord.User] = None):
        await self.d2r(ctx, user or ctx.author)
        
    async def d2r(self, ctx: commands.Context, user):
        msg = None
        try:
            author_obj = ctx.author
            target_user = user
            discord_id_int = int(target_user.id)
            discord_id_str = str(target_user.id)
            color = await self.bot.get_color(author_obj.id)

            msg = await cpv2.send(
                ctx,
                content="-# <a:dotsload:1423056880854499338> " + author_obj.mention +
                        ": looking up " + target_user.mention + "'s Roblox..",
                footer="Hang on tight, almost there!",
                color=color
            )

            main_results = []
            rover_result = None

            async with self.session.get(
                "http://localhost:7690/discord2roblox",
                params={"discord_id": discord_id_str}
            ) as api:
                if api.status == 200:
                    data = await api.json()
                    main_results = [data]

            async with self.session.get(
                "http://localhost:7690/roverdiscord2roblox",
                params={"discord_id": discord_id_str},
                timeout=aiohttp.ClientTimeout(total=6)
            ) as api:
                if api.status == 200:
                    rover_result = await api.json()

            if not main_results and not rover_result:
                return await cpv2.edit_warn(msg, ctx, "Could not find a linked Roblox account for this Discord user.")

            def normalize_redis_value(v):
                if v is None:
                    return None
                if isinstance(v, memoryview):
                    v = v.tobytes()
                if isinstance(v, (bytes, bytearray)):
                    v = v.decode("utf-8", "ignore")
                return str(v)

            async def cached_profile(roblox_id):
                key = f"rprofile:{roblox_id}"
                cached = await self.bot.redis.get(key)

                if cached is not None:
                    cached = normalize_redis_value(cached)
                    try:
                        return json.loads(cached)
                    except:
                        await self.bot.redis.delete(key)

                pd = await self.roblox_profile_user(roblox_id)
                await self.bot.redis.set(key, json.dumps(pd), ex=300)
                return pd

            async def cached_thumb(roblox_id):
                key = f"rthumb:{roblox_id}"
                cached = await self.bot.redis.get(key)

                if cached is not None:
                    cached = normalize_redis_value(cached)
                    if cached and cached.lower() != "none":
                        return cached

                default_url = "https://t0.rbxcdn.com/91d977e12525a5ed262cd4dc1c4fd52b?format=png"

                try:
                    async with self.session.get(
                        f"https://thumbnails.roproxy.com/v1/users/avatar-headshot?userIds={roblox_id}&size=420x420&format=Png&isCircular=false"
                    ) as r:
                        url = None
                        if r.status == 200:
                            j = await r.json()
                            d = j.get("data")
                            if d:
                                url = d[0].get("imageUrl")
                        if not url:
                            url = default_url
                except:
                    url = default_url

                url = str(url)
                await self.bot.redis.set(key, url, ex=300)
                return url

            async def build_profile_block(data, label=None, combined_sources=None):
                roblox_id = int(data["roblox_id"])
                roblox_name = data["roblox_name"]

                thumbnail_url = await cached_thumb(roblox_id)
                profile_data = await cached_profile(roblox_id)
                components = profile_data.get("components", {})

                header = components.get("UserProfileHeader", {}) or {}
                about = components.get("About", {}) or {}
                stats = components.get("Statistics", {}) or {}

                names = header.get("names", {}) or {}
                display_name = names.get("displayName") or names.get("primaryName") or roblox_name
                username_actual = names.get("username") or roblox_name

                counts = header.get("counts", {}) or {}
                friends_count = counts.get("friendsCount", 0)
                followers_count = counts.get("followersCount", 0)
                followings_count = counts.get("followingsCount", 0)

                joined = stats.get("userJoinedDate")
                created_ts = None
                if joined:
                    try:
                        dt_obj = datetime.fromisoformat(joined.replace("Z", "+00:00"))
                        created_ts = int(dt_obj.timestamp())
                    except:
                        created_ts = None

                description = about.get("description")

                if description is not None:
                    description = str(description)
                    if len(description) > 600:
                        description = description[:597] + "..."
                else:
                    description = ""

                if combined_sources:
                    title = "<:check:1344689360527949834> Found: [" + roblox_name + "](https://roblox.com/users/" + str(roblox_id) + "/profile) (" + str(roblox_id) + ")"
                else:
                    prefix = f"{label} " if label else ""
                    title = prefix + "Found: [" + roblox_name + "](https://roblox.com/users/" + str(roblox_id) + "/profile) (" + str(roblox_id) + ")"

                lines = []
                lines.append("**@" + username_actual + "** (" + display_name + ")")
                lines.append("<:pointdrl:1318643571317801040> **UserID:** " + str(roblox_id))
                lines.append("<:pointdrl:1318643571317801040> **Friends:** " + str(friends_count))
                lines.append("<:pointdrl:1318643571317801040> **Followers:** " + str(followers_count))
                lines.append("<:pointdrl:1318643571317801040> **Following:** " + str(followings_count))
                if created_ts:
                    lines.append("<:pointdrl:1318643571317801040> **Account Created:** <t:" + str(created_ts) + ":F>")
                if description:
                    lines.append("<:pointdrl:1318643571317801040> **Description:** " + description)

                content = "\n".join(lines)

                block = [
                    ui.TextDisplay(title),
                    ui.Separator(),
                    ui.Section(
                        ui.TextDisplay(content),
                        accessory=ui.Thumbnail(thumbnail_url)
                    )
                ]

                if combined_sources:
                    block.append(ui.Separator())
                    src_str = " & ".join([f":{s}:" for s in combined_sources])
                    block.append(ui.TextDisplay(f"-# **Verified** by {src_str}"))

                return block

            blocks = []

            blox = next((x for x in main_results if x["source"] == "bloxlink"), None)
            rover = rover_result

            if blox and rover and int(blox["roblox_id"]) == int(rover["roblox_id"]):
                combined = ["bloxlink", "rover"]
                block = await build_profile_block(blox, combined_sources=combined)
                blocks.append(block)
            elif blox and rover:
                blocks.append(await build_profile_block(blox, label="<:bloxlink:1441902218927276113>"))
                blocks.append(await build_profile_block(rover, label="<:rover:1441902221481738442>"))
            elif blox:
                blocks.append(await build_profile_block(blox, label="<:bloxlink:1441902218927276113>"))
            elif rover:
                blocks.append(await build_profile_block(rover, label="<:rover:1441902221481738442>"))

            await cpv2.edit(
                msg,
                ctx,
                advanced_sections=blocks,
                color=color
            )

        except Exception as e:
            if msg:
                await cpv2.edit_warn(msg, ctx, str(e))
            else:
                await cpv2.warn(ctx, str(e))
            
    @roblox.command(
        name="avatar",
        description="View a Roblox user's current avatar",
        aliases=["av"]
    )
    @app_commands.describe(username="The Roblox username to look up")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def avatar(self, ctx: commands.Context, *, username: str):
        await ctx.defer()
        try:
            search_response = await self.roblox_request(
                'POST',
                'https://users.roblox.com/v1/usernames/users',
                headers={'accept': 'application/json', 'Content-Type': 'application/json'},
                json={'usernames': [username], 'excludeBannedUsers': True}
            )
            user_data = await search_response.json()
            
            if not user_data['data']:
                await ctx.warn("No **Roblox user** found with that name.")
                return
            
            user_id = user_data['data'][0]['id']
            roblox_display_name = user_data['data'][0].get('displayName', username)

            thumbnail_response = await self.roblox_request(
                'GET',
                f"https://thumbnails.roproxy.com/v1/users/avatar?userIds={user_id}&size=720x720&format=Png&isCircular=false&thumbnailType=3d"
            )
            thumbnail_data = await thumbnail_response.json()
            thumbnail_url = thumbnail_data['data'][0]['imageUrl']
            
            async with self.session.get(thumbnail_url) as img_response:
                if img_response.status == 200:
                    image_data = await img_response.read()
                    file = discord.File(io.BytesIO(image_data), filename="avatar.png")
                else:
                    await ctx.warn("Failed to fetch avatar image.")
                    return

            color = await self.bot.get_color(ctx.author.id)
            embed = discord.Embed(color=color)
            embed.set_author(name=f"{ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            embed.title = f"{roblox_display_name} (@{user_data['data'][0]['name']})"
            embed.url = f"https://roblox.com/users/{user_id}/profile"
            embed.set_image(url="attachment://avatar.png")
            embed.set_footer(text="roblox.com", icon_url="https://git.cursi.ng/roblox_logo.png?v2")

            await ctx.send(file=file, embed=embed)
        except Exception as e:
            await ctx.warn(str(e))

    @avatar.autocomplete("username")
    async def robloxavatar(self, interaction: discord.Interaction, current: str):
        try:
            results = await self.omni_search(current)
            return [
                app_commands.Choice(name=f"@{u} ({uid})", value=u)
                for (u, uid) in results
            ]
        except:
            return []

    @render.command(name="avatar", description="Render a Roblox avatar into a 3D model", aliases=["av"])
    @app_commands.describe(username="Roblox username")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def render_avatar(self, ctx: commands.Context, username: str):
        await ctx.typing()
        try:
            search_response = await self.roblox_request(
                'POST',
                'https://users.roblox.com/v1/usernames/users',
                headers={
                    'accept': 'application/json',
                    'Content-Type': 'application/json'
                },
                json={'usernames': [username], 'excludeBannedUsers': False}
            )
            user_data = await search_response.json()
            if not user_data.get('data', []):
                await ctx.warn("No **Roblox user** found with that name.")
                return
            user_id = user_data['data'][0]['id']

            avatar_response = await self.roblox_request(
                'GET',
                f'https://avatar.roproxy.com/v1/users/{user_id}/avatar'
            )
            avatar_info = await avatar_response.json()

            COLOR_ID_TO_HEX = {
                1:"#F2F3F3", 2:"#A1A5A2", 3:"#F9E999", 5:"#D7C59A", 6:"#C2DAB8", 9:"#E8BAC8", 11:"#80BBDB", 12:"#CB8442",
                18:"#CC8E69", 21:"#C4281C", 22:"#C470A0", 23:"#0D69AC", 24:"#F5CD30", 25:"#624732", 26:"#1B2A35", 27:"#6D6E6C",
                28:"#287F47", 29:"#A1C48C", 36:"#F3CF9B", 37:"#4B974B", 38:"#A05F35", 39:"#C1CADE", 40:"#ECECEC", 41:"#CD544B",
                42:"#C1DFF0", 43:"#7BB6E8", 44:"#F7F18D", 45:"#B4D2E4", 47:"#D9856C", 48:"#84B68D", 49:"#F8F184", 50:"#ECE8DE",
                100:"#EEC4B6", 101:"#DA867A", 102:"#6E99CA", 103:"#C7C1B7", 104:"#6B327C", 105:"#E29B40", 106:"#DA8541", 107:"#008F9C",
                108:"#685C43", 110:"#435493", 111:"#BFB7B1", 112:"#6874AC", 113:"#E5ADC8", 115:"#C7D23C", 116:"#55A5AF", 118:"#B7D7D5",
                119:"#A4BD47", 120:"#D9E4A7", 121:"#E7AC58", 123:"#D36F4C", 124:"#923978", 125:"#EAB892", 126:"#A5A5CB", 127:"#DCBC81",
                128:"#AE7A59", 131:"#9CA3A8", 133:"#D5733D", 134:"#D8DD56", 135:"#74869D", 136:"#877C90", 137:"#E09864", 138:"#958A73",
                140:"#203A56", 141:"#27462D", 143:"#CFE2F7", 145:"#7988A1", 146:"#958EA3", 147:"#938767", 148:"#575857", 149:"#161D32",
                150:"#ABADAC", 151:"#788082", 153:"#957979", 154:"#7B2E2F", 157:"#FFF67B", 158:"#E1A4C2", 168:"#756C62", 176:"#97695B",
                178:"#B48455", 179:"#898788", 180:"#D7A94B", 190:"#F9D62E", 191:"#E8AB2D", 192:"#693C28", 193:"#CF6024", 194:"#A3A2A5",
                195:"#4667A4", 196:"#23478B", 198:"#8E4285", 199:"#635F62", 200:"#828A5D", 208:"#E5E4DF", 209:"#B08E44", 210:"#709578",
                211:"#79B5B5", 212:"#9FC3E9", 213:"#6C81B7", 216:"#904C2A", 217:"#7C5C46", 218:"#96709F", 219:"#6B629B", 220:"#A7A9CE",
                221:"#CD6298", 222:"#E4ADC8", 223:"#DC9095", 224:"#F0D5A0", 225:"#EBB87F", 226:"#FDEB8D", 232:"#7DBBDD", 268:"#342B75",
                301:"#506D54", 302:"#5B5D69", 303:"#0010B0", 304:"#2C651D", 305:"#527CAA", 306:"#335882", 307:"#102ADC", 308:"#3D1585",
                309:"#348E40", 310:"#5B9A4C", 311:"#9FA1AC", 312:"#592259", 313:"#1F801D", 314:"#9FACC0", 315:"#0989CF", 316:"#7B007B",
                317:"#7C9C6B", 318:"#8AAB85", 319:"#B9C4B1", 320:"#CACBD1", 321:"#A75E9B", 322:"#7B2F7B", 323:"#94BE81", 324:"#A8BD99",
                325:"#DFDFDE", 327:"#970000", 328:"#B1E5A6", 329:"#98C2DB", 330:"#FF98DC", 331:"#FF5959", 332:"#750000", 333:"#EFB838",
                334:"#F8D96D", 335:"#E7E7EC", 336:"#C7D4E4", 337:"#FF9494", 338:"#BE6862", 339:"#562424", 340:"#F1E7C7", 341:"#FEF3BB",
                342:"#E0B2D0", 343:"#D490BD", 344:"#965555", 345:"#8F4C2A", 346:"#D3BE96", 347:"#E2DCCC", 348:"#EDEAEA", 349:"#E9DADA",
                350:"#883E3E", 351:"#BC9B5D", 352:"#C7AC78", 353:"#CABFA3", 354:"#BBB3B2", 355:"#6C584B", 356:"#A0844F", 357:"#958988",
                358:"#ABA89E", 359:"#AF9483", 360:"#966766", 361:"#564236", 362:"#7E683F", 363:"#69665C", 364:"#5A4C42", 365:"#6A3909",
                1001:"#F8F8F8", 1002:"#CDCDCD", 1003:"#111111", 1004:"#FF0000", 1005:"#FFB000", 1006:"#B480FF", 1007:"#A34B4B", 1008:"#C1BE42",
                1009:"#FFFF00", 1010:"#0000FF", 1011:"#002060", 1012:"#2154B9", 1013:"#04AFEC", 1014:"#AA5500", 1015:"#AA00AA", 1016:"#FF66CC",
                1017:"#FFAF00", 1018:"#12EED4", 1019:"#00FFFF", 1020:"#00FF00", 1021:"#3A7D15", 1022:"#7F8E64", 1023:"#8C5B9F", 1024:"#AFDDFF",
                1025:"#FFC9C9", 1026:"#B1A7FF", 1027:"#9FF3E9", 1028:"#CCFFCC", 1029:"#FFFFCC", 1030:"#FFCC99", 1031:"#6225D1", 1032:"#FF00BF"
            }

            def id_to_hex(color_id):
                return COLOR_ID_TO_HEX.get(color_id, "#FFFFFF")

            payload = {
                "thumbnailConfig": {
                    "thumbnailId": 3,
                    "thumbnailType": "3d",
                    "size": "420x420"
                },
                "avatarDefinition": {
                    "assets": [
                        {
                            "id": asset["id"],
                            "meta": asset.get("meta")
                        }
                        for asset in avatar_info["assets"]
                    ],
                    "bodyColors": {
                        "headColor": id_to_hex(avatar_info["bodyColors"]["headColorId"]),
                        "torsoColor": id_to_hex(avatar_info["bodyColors"]["torsoColorId"]),
                        "rightArmColor": id_to_hex(avatar_info["bodyColors"]["rightArmColorId"]),
                        "leftArmColor": id_to_hex(avatar_info["bodyColors"]["leftArmColorId"]),
                        "rightLegColor": id_to_hex(avatar_info["bodyColors"]["rightLegColorId"]),
                        "leftLegColor": id_to_hex(avatar_info["bodyColors"]["leftLegColorId"])
                    },
                    "scales": {
                        "height": 1,
                        "width": 1,
                        "head": 1,
                        "depth": 1,
                        "proportion": 0,
                        "bodyType": 0
                    },
                    "playerAvatarType": {"playerAvatarType": "R15"}
                }
            }

            headers = {
                "Content-Type": "application/json",
                "Referer": "https://www.roblox.com",
                "User-Agent": "Mozilla/5.0",
                "Cookie": f".ROBLOSECURITY={get_cookie()}"
            }

            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)

            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post("https://avatar.roproxy.com/v1/avatar/render",
                                        json=payload,
                                        headers=headers) as resp:
                    if resp.status == 403 and resp.headers.get("x-csrf-token"):
                        headers["X-CSRF-TOKEN"] = resp.headers["x-csrf-token"]
                    else:
                        await ctx.warn("Failed to get CSRF token")
                        return

                render_data = None
                for _ in range(10):
                    async with session.post("https://avatar.roproxy.com/v1/avatar/render",
                                            json=payload,
                                            headers=headers) as resp:
                        render_data = await resp.json()
                        state = render_data.get("state")
                        if state == "Completed" or (state != "Pending" and state is not None):
                            break
                        await asyncio.sleep(1)

                if not render_data or render_data.get("state") != "Completed":
                    await ctx.warn("Render timed out, try again.")
                    return

                image_url = render_data.get("imageUrl")
                if not image_url:
                    await ctx.warn("Missing imageUrl in render data.")
                    return

                async with session.get(image_url) as model_response:
                    if model_response.status != 200:
                        await ctx.warn("Failed to get model JSON.")
                        return

                    text = await model_response.text()
                    model_data = await asyncio.to_thread(json.loads, text)

                obj_hash = model_data.get("obj")
                mtl_hash = model_data.get("mtl")
                textures = model_data.get("textures", [])

                if not obj_hash or not mtl_hash:
                    await ctx.warn("Missing model files in response.")
                    return

                async def try_fetch_file(fid):
                    cdn_prefixes = [f"t{i}.rbxcdn.com" for i in range(8)]
                    for cdn in cdn_prefixes:
                        url = f"https://{cdn}/{fid}"
                        try:
                            r = await session.get(url)
                            if r.status == 200:
                                data = await r.read()
                                await r.release()
                                return data
                            await r.release()
                        except:
                            continue
                    return None

                obj_data = await try_fetch_file(obj_hash)
                mtl_data = await try_fetch_file(mtl_hash)

                if not obj_data or not mtl_data:
                    await ctx.warn("Failed to download model files.")
                    return

                mtl_text = mtl_data.decode('utf-8')
                texture_files = {}
                for tex_hash in textures:
                    tex_data = await try_fetch_file(tex_hash)
                    if tex_data:
                        texture_files[f"{tex_hash}.png"] = tex_data
                        mtl_text = mtl_text.replace(tex_hash, f"{tex_hash}.png")

                def create_zip():
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, 'w') as zf:
                        zf.writestr("model.obj", obj_data)
                        zf.writestr("model.mtl", mtl_text)
                        for name, data in texture_files.items():
                            zf.writestr(name, data)
                    buf.seek(0)
                    return buf

                zip_buffer = await asyncio.to_thread(create_zip)

                await ctx.send(file=discord.File(zip_buffer, filename=f"{username}_avatar3d_heist.zip"))

        except Exception as e:
            await ctx.warn(str(e))

    # @server.command(
    #     name="region",
    #     description="View Roblox game servers by region"
    # )
    # @app_commands.describe(place="The Roblox game ID to scan")
    # @app_commands.allowed_installs(guilds=True, users=True)
    # @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    # async def robloxregion(self, ctx: commands.Context, place: int):
    #     try:
    #         color = await self.bot.get_color(ctx.author.id)
    #         loading = discord.Embed(
    #             description=f"-# <a:dotsload:1423056880854499338> {ctx.author.mention}: scanning **{place}**..",
    #             color=color
    #         )
    #         msg = await ctx.send(embed=loading)

    #         async with aiohttp.ClientSession() as s:
    #             async with s.get(f"http://127.0.0.1:8648/servers/info?placeId={place}") as r:
    #                 data = await r.json()

    #         game_name = data["gameName"]
    #         game_url = data["gameUrl"]
    #         game_icon = data.get("gameIcon")
    #         total = data["estimatedTotalServers"]
    #         ccu = data["ccu"]
    #         top = data["topRegion"]
    #         regions = data["regions"]
    #         servers_all = data["servers"]

    #         sepbyte = await makeseparator(self.bot, ctx.author.id)
    #         def make_sep():
    #             return discord.File(io.BytesIO(sepbyte), filename="separator.png")

    #         servers_by_region = {}

    #         for s in servers_all:
    #             region = s.get("region")
    #             if not region:
    #                 continue
    #             else:
    #                 label = region.get("country") or "Unknown"

    #             servers_by_region.setdefault(label, []).append(s)

    #         if not regions:
    #             embed = discord.Embed(color=color)
    #             embed.title = game_name
    #             embed.url = game_url
    #             embed.description = f"**Total Servers:** {total}\n**CCU:** {ccu}\n**Top CCU Region:** None"
    #             if game_icon:
    #                 embed.set_thumbnail(url=game_icon)
    #             embed.set_image(url="attachment://separator.png")
    #             await msg.edit(embed=embed, attachments=[make_sep()])
    #             return

    #         country_counts = {}

    #         for s in servers_all:
    #             region = s.get("region")
    #             country = region.get("country") if region else "Unknown"
    #             country_counts[country] = country_counts.get(country, 0) + 1

    #         dropdown_data = [{
    #             "label": country,
    #             "description": f"{count} servers",
    #             "value": country
    #         } for country, count in country_counts.items()]

    #         overview_embed = discord.Embed(color=color)
    #         overview_embed.title = game_name
    #         overview_embed.url = game_url
    #         overview_embed.description = (
    #             f"**Total Servers:** {total}\n"
    #             f"**CCU:** {ccu}\n"
    #             f"**Top CCU Region:** {top['key']} ({top['serverCount']} servers)"
    #         )
    #         overview_embed.set_image(url="attachment://separator.png")
    #         if game_icon:
    #             overview_embed.set_thumbnail(url=game_icon)

    #         view = discord.ui.View(timeout=240)

    #         async def dropdown_callback(interaction: discord.Interaction):
    #             if interaction.user.id != ctx.author.id:
    #                 embed_err = discord.Embed(description="You cannot interact with this **menu**.", color=self.bot.config.colors.information)
    #                 try:
    #                     await interaction.response.send_message(embed=embed_err, ephemeral=True)
    #                 except:
    #                     pass
    #                 return

    #             region_key = interaction.data["values"][0]
    #             servers = servers_by_region.get(region_key, [])
    #             pages = []
    #             buf = []

    #             for i, sv in enumerate(servers, 1):
    #                 created = f"<t:{sv['created']}:R>" if sv["created"] else "Unknown"
    #                 if sv.get("ping") is None:
    #                     ping_text = "Unknown"
    #                 else:
    #                     p = sv["ping"]
    #                     if p <= 80:
    #                         emoji = "🟢"
    #                     elif p <= 150:
    #                         emoji = "🟡"
    #                     else:
    #                         emoji = "🔴"
    #                     ping_text = f"{p}ms {emoji}"

    #                 buf.append(
    #                     f"**Server {i}**\n"
    #                     f"-# Ping: **{ping_text}**\n"
    #                     f"-# Players: **{sv['playing']}/{sv['maxPlayers']}**\n"
    #                     f"-# Created {created}\n"
    #                     f"[**Join**](https://heist.lol/joiner?placeId={place}&gameInstanceId={sv['jobId']})"
    #                 )

    #                 if i % 5 == 0 or i == len(servers):
    #                     pages.append("\n\n".join(buf))
    #                     buf = []

    #             embeds = []
    #             for p in pages:
    #                 e = discord.Embed(color=color, description=p)
    #                 e.title = f"{game_name} - {region_key}"
    #                 e.url = game_url
    #                 e.set_footer(text=f"{len(servers)} servers | 5 per page", icon_url="https://git.cursi.ng/roblox_logo.png?v2")
    #                 if game_icon:
    #                     e.set_thumbnail(url=game_icon)
    #                 e.set_image(url="attachment://separator.png")
    #                 embeds.append(e)

    #             if len(embeds) == 1:
    #                 back_view = discord.ui.View(timeout=240)
    #                 back_button = discord.ui.Button(label="Back", emoji="🗺️", style=discord.ButtonStyle.secondary)

    #                 async def back_callback(back_interaction: discord.Interaction):
    #                     if back_interaction.user.id != ctx.author.id:
    #                         embed_err2 = discord.Embed(description="You cannot interact with this **menu**.", color=self.bot.config.colors.information)
    #                         try:
    #                             await back_interaction.response.send_message(embed=embed_err2, ephemeral=True)
    #                         except:
    #                             pass
    #                         return
    #                     await back_interaction.response.edit_message(embed=overview_embed, view=view, attachments=[make_sep()])

    #                 back_button.callback = back_callback
    #                 back_view.add_item(back_button)
    #                 await interaction.response.edit_message(embed=embeds[0], view=back_view, attachments=[make_sep()])
    #             else:
    #                 from heist.framework.pagination import Paginator

    #                 async def back_button_callback(back_interaction: discord.Interaction, paginator):
    #                     if back_interaction.user.id != ctx.author.id:
    #                         try:
    #                             await back_interaction.response.warn("You cannot interact with this **menu**.", ephemeral=True)
    #                         except:
    #                             pass
    #                         return
    #                     await back_interaction.response.edit_message(embed=overview_embed, view=view, attachments=[make_sep()])
    #                     paginator.stop()

    #                 paginator = Paginator(ctx, embeds, embed=True, message=msg, disable_cancel_button=True)
    #                 paginator.add_custom_button(back_button_callback, emoji="🗺️", style=discord.ButtonStyle.secondary, custom_id="servers:back")
    #                 paginator.children[-1].label = "Back"
    #                 await interaction.response.defer()
    #                 await paginator.start(attachments=[make_sep()])

    #         dropdown = discord.ui.Select(
    #             placeholder="Select a region to browse servers..",
    #             options=[discord.SelectOption(label=o["label"], description=o["description"], value=o["value"]) for o in dropdown_data]
    #         )
    #         dropdown.callback = dropdown_callback
    #         view.add_item(dropdown)

    #         await msg.edit(embed=overview_embed, view=view, attachments=[make_sep()])
    #     except Exception as e:
    #         await ctx.edit_warn(str(e), msg)

    # @robloxregion.autocomplete("place")
    # async def auto_robloxregion(self, interaction: discord.Interaction, current: str):
    #     try:
    #         results = await self.omni_search_games(current)
    #         return [
    #             app_commands.Choice(
    #                 name=f"{name} - {creator} [{root}]",
    #                 value=str(root)
    #             )
    #             for (name, root, creator) in results
    #         ]
    #     except:
    #         return []

    @roblox.command(
        name="template",
        description="Grab the template for a classic Roblox shirt or pants",
        aliases=["grab", "steal", "cloth"]
    )
    @app_commands.describe(assetid="The ID/URL of the asset")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def template(self, ctx: commands.Context, *, assetid: str):
        await ctx.typing()
        try:
            if assetid.isdigit():
                clothing_id = assetid
            else:
                match = await asyncio.to_thread(lambda: re.search(r'/(\d+)(?:/|$)', assetid))
                if not match:
                    await ctx.warn("Invalid Roblox clothing URL or ID.")
                    return
                clothing_id = match.group(1)

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 OPR/107.0.0.0',
                'Cookie': f'.ROBLOSECURITY={get_cookie()}'
            }

            xml_url = f'https://assetdelivery.roproxy.com/v1/asset/?id={clothing_id}'
            async with self.session.get(xml_url, headers=headers) as response:
                if response.status != 200:
                    await ctx.warn("Unable to get the template.")
                    return
                xml_content = await response.text()

            match = await asyncio.to_thread(lambda: re.search(r'<url>.*\?id=(\d+)</url>', xml_content))
            if not match:
                await ctx.warn("Failed to extract new asset ID from the XML.")
                return

            new_id = match.group(1)
            img_url = f'https://assetdelivery.roproxy.com/v1/asset/?id={new_id}'

            async with self.session.get(img_url, headers=headers) as response:
                if response.status != 200:
                    await ctx.warn("Failed to download clothing image.")
                    return

                img_data = await response.read()
                img_byte_arr = await asyncio.to_thread(lambda: io.BytesIO(img_data))
                processed_img = await asyncio.to_thread(lambda: Image.open(img_byte_arr))
                output_buffer = io.BytesIO()
                await asyncio.to_thread(lambda: processed_img.save(output_buffer, format='PNG'))
                output_buffer.seek(0)
                await ctx.send(file=discord.File(output_buffer, filename="heist_template.png"))

        except (aiohttp.ContentTypeError, UnicodeDecodeError):
            await ctx.warn("This asset is not a shirt or pants.")
            return
        except Exception as e:
            await ctx.warn(str(e))

    async def dtr_push_db(self, discord_id: str, roblox_id: int, roblox_name: str):
        await self.bot.pool.execute(
            """
            INSERT INTO dtr_mappings (discord_id, roblox_id, roblox_name, last_updated)
            VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
            ON CONFLICT (discord_id, roblox_id) 
            DO UPDATE SET roblox_name = $3, last_updated = CURRENT_TIMESTAMP;
            """,
            discord_id, roblox_id, roblox_name
        )
        await self.dtr_push_redis(discord_id, roblox_id, roblox_name, datetime.now().isoformat())

    async def dtr_hit_db(self, identifier: Union[int, str]):
        if isinstance(identifier, int):
            row = await self.bot.pool.fetchrow(
                "SELECT discord_id, roblox_name, last_updated FROM dtr_mappings WHERE roblox_id = $1",
                identifier
            )
        else:
            row = await self.bot.pool.fetchrow(
                "SELECT roblox_id, roblox_name, last_updated FROM dtr_mappings WHERE discord_id = $1",
                identifier
            )
        
        if row:
            row = dict(row)
            if isinstance(identifier, int):
                row["discord_id"] = str(row["discord_id"])
            else:
                row["roblox_id"] = int(row["roblox_id"])
            row["last_updated"] = row["last_updated"].isoformat()
            return row
        return None

    async def dtr_push_redis(self, discord_id: str, roblox_id: int, roblox_name: str, last_updated: str):
        roblox_id = int(roblox_id)
        await self.bot.redis.setex(
            f"dtr:{roblox_id}",
            7776000,
            f"{discord_id}:{roblox_name}:{last_updated}"
        )
        await self.bot.redis.setex(
            f"r2d:{discord_id}",
            7776000,
            f"{roblox_id}:{roblox_name}:{last_updated}"
        )

    async def dtr_hit_redis(self, identifier: Union[int, str]):
        if isinstance(identifier, int):
            key = f"dtr:{identifier}"
        else:
            key = f"r2d:{identifier}"
        
        cached_data = await self.bot.redis.get(key)
        if cached_data:
            parts = cached_data.split(":")
            if isinstance(identifier, int):
                return parts[0], parts[1], ":".join(parts[2:])
            else:
                return parts[0], parts[1], ":".join(parts[2:])
        return None, None, None

    @hybrid_group(name="instagram", description="Instagram social commands", aliases=["insta", "ig"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def instagram(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @instagram.command(name="user", description="✨ Get Instagram user info", aliases=["u"])
    @app_commands.describe(username="Instagram username to lookup")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @donor_only()
    async def instauser(self, ctx: commands.Context, username: str):
        if not username:
            await ctx.warn("Please provide an Instagram username")
            return

        await ctx.typing()

        def format_number(number_str: str) -> str:
            try:
                number = float(number_str.replace(',', ''))
                if number >= 1_000_000:
                    return f"{number/1_000_000:.1f}m"
                elif number >= 1_000:
                    return f"{number/1_000:.1f}k"
                return str(int(number))
            except:
                return number_str

        try:
            data = await self.get_profile(username)

            title = f"@{data['username']}"
            if data.get('verified'):
                title += " <:verified_light_blue:1362170749271408911>"

            description = ""
            for link in data.get("bio_links", []):
                display_url = link['url'].replace("https://", "").replace("http://", "").split("/")[0]
                description += f"<:igurl:1388895771943899177> [{display_url}]({link['url']})\n"
            if data.get("bio"):
                description += data["bio"]

            color = await self.bot.get_color(ctx.author.id)

            embed = Embed(
                title=title,
                url=data["url"],
                description=description or None,
                color=color
            )
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
            if data.get("avatar_url"):
                embed.set_thumbnail(url=data["avatar_url"])

            embed.add_field(name="Followers", value=f"**`{format_number(data['followers'])}`**", inline=True)
            embed.add_field(name="Following", value=f"**`{format_number(data['following'])}`**", inline=True)
            embed.add_field(name="Posts", value=f"**`{format_number(data['posts'])}`**", inline=True)

            embed.set_footer(
                text="instagram.com",
                icon_url="https://git.cursi.ng/instagram_logo.png?e"
            )

            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.warn(str(e))

    async def get_profile(self, username: str) -> Dict[str, Any]:
        url = "https://trendhero.io/api/get_er_reports"
        params = {'username': username}
        headers = {
            'User-Agent': "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Mobile Safari/537.36",
            'Accept': "application/json, text/plain, */*",
            'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="132"',
            'sec-ch-ua-mobile': "?1",
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-site': "same-origin",
            'sec-fetch-mode': "cors",
            'sec-fetch-dest': "empty",
            'referer': "https://trendhero.io/instagram-follower-count/",
            'accept-language': "en-US,en;q=0.9",
        }
        
        async with self.session.get(url, params=params, headers=headers) as response:
            if response.status != 200:
                raise Exception(f"API request failed (Status: {response.status})")
            
            data = await response.json()
            
            if "error" in data:
                raise Exception(data["error"])
            
            user_info = data.get('preview', {}).get('user_info', {})
            print(user_info)
            
            bio_links = []
            if user_info.get('external_url'):
                bio_links.append({
                    'url': user_info['external_url']
                })
            
            return {
                'username': username,
                'full_name': user_info.get('full_name', username),
                'verified': user_info.get('is_verified', False),
                'bio': user_info.get('biography'),
                'bio_links': bio_links,
                'avatar_url': user_info.get('profile_pic_url'),
                'followers': str(user_info.get('follower_count', 0)),
                'following': str(user_info.get('following_count', 0)),
                'posts': str(user_info.get('media_count', 0)),
                'url': f"https://instagram.com/{username}"
            }

    @instagram.command(name="repost", description="✨ Repost an Instagram post/reel", aliases=["r"])
    @app_commands.describe(url="The Instagram post/reel URL to download")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @donor_only()
    async def repost(self, ctx: commands.Context, url: str):
        if not url:
            return await ctx.warn("Please provide an Instagram URL")

        if not any(x in url for x in ["instagram.com/reel/", "instagram.com/reels/", "instagram.com/p/", "instagram.com/tv/"]):
            return await ctx.warn("Please provide a valid Instagram post/reel URL")

        async with ctx.typing():
            try:
                data = await self.bot.cp_system.process_instagram(url)

                if "error" in data:
                    return await ctx.warn(f"Failed to fetch reel: {data['error']}")

                video_url = data.get("extra", {}).get("video_url")
                if not video_url:
                    return await ctx.warn("No video found in this post")

                username = data.get("user", {}).get("username", "unknown")
                profile_pic = data.get("user", {}).get("profile_pic_url", "")
                caption = data.get("caption", {}).get("text", "No caption")

                like_count = data.get("like_count", 0)
                comment_count = data.get("comment_count", 0)
                
                likes = await self.format_metric(like_count)
                comments = await self.format_metric(comment_count)
                stats = f"❤️ {likes} • 🗨️ {comments}"

                def process_caption(text):
                    if not text:
                        return ""
                    text = re.sub(r"#(\w+)", r"[#\1](https://instagram.com/explore/tags/\1)", text)
                    return text

                caption = await asyncio.to_thread(process_caption, caption)

                embed = discord.Embed(
                    description=caption,
                    color=await self.bot.get_color(ctx.author.id)
                )
                embed.set_author(
                    name=f"@{username}",
                    url=f"https://instagram.com/{username}",
                    icon_url=profile_pic
                )
                embed.set_footer(
                    text=stats,
                    icon_url="https://git.cursi.ng/instagram_logo.png?e"
                )

                try:
                    async with self.session.head(video_url) as response:
                        content_length = response.headers.get('content-length')
                        file_size = int(content_length) if content_length else 0

                    if file_size > 8 * 1024 * 1024:
                        await ctx.send(f"[Video URL]({video_url})\\n⚠️ File too large for Discord\\n`{stats}`")
                    else:
                        async with self.session.get(video_url) as resp:
                            if resp.status == 200:
                                video_data = await resp.read()
                                video_file = discord.File(io.BytesIO(video_data), "heist.mp4")
                                await ctx.send(file=video_file, embed=embed)
                            else:
                                await ctx.send(f"[Video URL]({video_url})", embed=embed)
                except:
                    await ctx.send(f"[Video URL]({video_url})", embed=embed)

            except Exception as e:
                await ctx.warn(f"Failed to process Instagram content: {str(e)}")

    @instagram.command(name="trending", description="✨ Get trending Instagram reel")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @donor_only()
    async def trending(self, ctx: commands.Context):
        async with ctx.typing():
            try:
                data = await self.bot.cp_system.process_instagram_trending()

                if "error" in data:
                    return await ctx.warn(f"Failed to fetch trending reel: {data['error']}")

                video_url = data.get("extra", {}).get("video_url")
                if not video_url:
                    return await ctx.warn("No trending video found")

                username = data.get("user", {}).get("username", "unknown")
                profile_pic = data.get("user", {}).get("profile_pic_url", "")
                caption = data.get("caption", {}).get("text", "Trending reel")

                like_count = data.get("like_count", 0)
                comment_count = data.get("comment_count", 0)
                
                likes = await self.format_metric(like_count)
                comments = await self.format_metric(comment_count)
                stats = f"❤️ {likes} • 🗨️ {comments} • 🔥 Trending"

                embed = discord.Embed(
                    description=caption,
                    color=await self.bot.get_color(ctx.author.id)
                )
                embed.set_author(
                    name=f"@{username}",
                    url=f"https://instagram.com/{username}",
                    icon_url=profile_pic
                )
                embed.set_footer(
                    text=stats,
                    icon_url="https://git.cursi.ng/instagram_logo.png?e"
                )

                try:
                    async with self.session.head(video_url) as response:
                        content_length = response.headers.get('content-length')
                        file_size = int(content_length) if content_length else 0

                    if file_size > 8 * 1024 * 1024:
                        await ctx.send(f"[Trending Video]({video_url})\n`{stats}`\n-# :warning: This video exceeds the limit of 8MB, hence the instagram cdn was used.")
                    else:
                        async with self.session.get(video_url) as resp:
                            if resp.status == 200:
                                video_data = await resp.read()
                                video_file = discord.File(io.BytesIO(video_data), "trending.mp4")
                                await ctx.send(file=video_file, embed=embed)
                            else:
                                await ctx.send(f"[Trending Video]({video_url})", embed=embed)
                except:
                    await ctx.send(f"[Trending Video]({video_url})", embed=embed)

            except Exception as e:
                await ctx.warn(f"Failed to fetch trending content: {str(e)}")

    @hybrid_group(
        name="medaltv",
        description="MedalTV related commands",
        aliases=["medal"]
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def medaltv(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @medaltv.command(name="repost", description="Repost a Medal TV clip", aliases=["r"])
    @app_commands.describe(url="The URL of the Medal clip")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def repost(self, ctx: commands.Context, url: str):
        await ctx.defer()

        async def upload_to_catbox(file_data: io.BytesIO) -> str | None:
            try:
                data = aiohttp.FormData()
                data.add_field('reqtype', 'fileupload')
                data.add_field('fileToUpload', file_data, filename='heist.mp4')

                async with self.session.post('https://catbox.moe/user/api.php', data=data) as response:
                    if response.status == 200:
                        return await response.text()
                    return None
            except:
                return None

        try:
            headers = {"Content-Type": "application/json"}
            payload = {"url": url}

            async with self.session.post("https://medalbypass.vercel.app/api/clip", headers=headers, json=payload) as response:
                if response.status != 200:
                    return await ctx.warn("Failed to fetch clip data.")

                data = await response.json()

                if not data.get("valid", False):
                    return await ctx.warn(f"Invalid clip. Reason: {data.get('reasoning', 'Unknown')}")

                video_url = data["src"]

                async with self.session.get(video_url) as video_response:
                    if video_response.status != 200:
                        return await ctx.warn("Failed to download the video.")

                    video_content = await video_response.read()
                    video_size = len(video_content)

                    if video_size > 10 * 1024 * 1024:
                        catbox_url = await upload_to_catbox(io.BytesIO(video_content))
                        if not catbox_url:
                            return await ctx.warn("Failed to upload the video to Catbox.")

                        return await ctx.send(
                            f"-# [**Medal.tv**](<{url}>) • [**Download**]({catbox_url})\n"
                            f"-# This video exceeds the limit of 10MB, hence it was uploaded to [catbox](<https://catbox.moe>)."
                        )

                    video_file = discord.File(io.BytesIO(video_content), filename="heist.mp4")
                    return await ctx.send(
                        content=f"[Original Clip](<{url}>)",
                        file=video_file
                    )

        except Exception as e:
            return await ctx.warn(str(e))

    @hybrid_group(name="tiktok", description="TikTok social commands", aliases=["tik", "tt"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def tiktok(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @tiktok.command(name="user", description="View TikTok user info", aliases=["u", "profile"])
    @app_commands.describe(username="The TikTok username to lookup")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def tiktokuser(self, ctx: commands.Context, username: str):
        if not username:
            return await ctx.warn("Please provide a TikTok username")

        def region2flag(region_code: str) -> str:
            if not region_code or len(region_code) != 2:
                return ""
            return chr(ord(region_code[0].upper()) + 127397) + chr(ord(region_code[1].upper()) + 127397)

        def format_number(number):
            if isinstance(number, str):
                try:
                    number = int(number)
                except:
                    return number
            if number >= 1_000_000_000:
                return f"{number / 1_000_000_000:.1f}b"
            elif number >= 1_000_000:
                return f"{number / 1_000_000:.1f}m"
            elif number >= 1_000:
                return f"{number / 1_000:.1f}k"
            return str(number)

        async with ctx.typing():
            try:
                user_data = await self.bot.cp_system.process_tiktok_user(username)
                if "error" in user_data:
                    return await ctx.warn("No **TikTok user** found with that name.")

                bio = user_data.get('signature', '') or "No bio available"
                bio = re.sub(r'@(\w+)', r'[@\1](https://www.tiktok.com/@\1)', bio)
                bio_lines = [bio]

                bio_url = user_data.get("bio_url")
                if bio_url:
                    bio_lines.append(f"<:igurl:1388895771943899177> [{bio_url}](https://{bio_url})")

                bio = "\n-# ".join(bio_lines)

                profile_pic = user_data.get('avatar_larger', None)
                followers = format_number(user_data.get('stats', {}).get('follower_count', 'N/A'))
                following = format_number(user_data.get('stats', {}).get('following_count', 'N/A'))
                likes = format_number(user_data.get('stats', {}).get('heart_count', 'N/A'))
                nickname = user_data.get('nickname', 'Unknown')
                unique_id = user_data.get('unique_id', '')
                verified = user_data.get('verified', False)
                region_code = user_data.get('region_code', "")
                region_name = user_data.get('region', "")
                flag = region2flag(region_code)
                if region_name:
                    desc = f"{flag} **`{region_name}`**"
                else:
                    desc = ""

                title = f"{nickname} (@{unique_id})"
                if verified:
                    title += " <:verified_light_blue:1362170749271408911>"

                embed = Embed(
                    title=title,
                    url=f"https://www.tiktok.com/@{unique_id}",
                    description=f"{desc}\n{bio}",
                    color=await self.bot.get_color(ctx.author.id)
                )

                embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
                embed.add_field(name='Followers', value=f"**`{followers}`**", inline=True)
                embed.add_field(name='Following', value=f"**`{following}`**", inline=True)
                embed.add_field(name='Likes', value=f"**`{likes}`**", inline=True)
                embed.set_footer(text="tiktok.com", icon_url="https://git.cursi.ng/tiktok_logo.png?2")

                if profile_pic:
                    embed.set_thumbnail(url=profile_pic)

                await ctx.send(embed=embed)

            except Exception as e:
                await ctx.warn(f"Failed to fetch TikTok profile: {str(e)}")

    @tiktok.command(name="repost", description="Repost a TikTok post", aliases=["r"])
    @app_commands.describe(url="The TikTok post URL to download")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def repost(self, ctx: commands.Context, url: str):
        if not url:
            return await ctx.warn("Please provide a TikTok URL")

        parsed = urlparse(url.strip())
        hostname = parsed.netloc.lower()

        if not (hostname == 'tiktok.com' or hostname.endswith('.tiktok.com')):
            return await ctx.warn("Please provide a valid TikTok URL")

        async with ctx.typing():
            try:
                data = await self.bot.cp_system.process_tiktok(url)

                if "error" in data:
                    return await ctx.warn(f"Failed to process TikTok: {data['error']}")

                username = data.get('author_info', {}).get('unique_id', 'unknown')
                nickname = data.get('author_info', {}).get('nickname', username)
                avatar_url = data.get('author_info', {}).get('avatar_url', '')
                description = data.get('desc', '')
                
                stats = data.get('statistics_info', {})
                likes = await self.format_metric(stats.get('digg_count', 0))
                comments = await self.format_metric(stats.get('comment_count', 0))
                shares = await self.format_metric(stats.get('share_count', 0))
                views = await self.format_metric(data.get('view_count', 0), use_millions=True)
                
                tiktokstats = f"❤️ {likes} • 👁️ {views} • 🗨️ {comments} • 🔄 {shares}"
                processed_desc = await self.process_description(description)

                embed = discord.Embed(
                    description=processed_desc,
                    color=await self.bot.get_color(ctx.author.id)
                )
                embed.set_author(
                    name=f"{nickname} (@{username})", 
                    url=f"https://www.tiktok.com/@{username}",
                    icon_url=avatar_url
                )
                embed.set_footer(
                    text=tiktokstats, 
                    icon_url="https://git.cursi.ng/tiktok_logo.png?2"
                )

                if data.get('is_image_post') and data.get('image_urls'):
                    files = []
                    for i, img_url in enumerate(data['image_urls'][:4]):
                        try:
                            async with self.session.get(img_url) as resp:
                                if resp.status == 200:
                                    img_data = await resp.read()
                                    files.append(discord.File(io.BytesIO(img_data), f"image_{i}.jpg"))
                        except:
                            continue
                    
                    if files:
                        await ctx.send(files=files, embed=embed)
                    else:
                        await ctx.warn("Failed to download images")
                
                elif data.get('video_url'):
                    try:
                        async with self.session.get(data['video_url']) as resp:
                            if resp.status == 200:
                                video_data = await resp.read()
                                video_size = len(video_data)
                                
                                if video_size <= 8 * 1024 * 1024:
                                    video_file = discord.File(io.BytesIO(video_data), "heist.mp4")
                                    await ctx.send(file=video_file, embed=embed)
                                elif video_size <= 50 * 1024 * 1024:
                                    catbox_url = await self.upload_to_catbox(io.BytesIO(video_data))
                                    if catbox_url:
                                        message = f"-# Uploaded by **`{nickname}`** [**`(@{username})`**](<https://www.tiktok.com/@{username}>)\\n"
                                        if description:
                                            message += f"-# {processed_desc}\\n"
                                        message += f"-# {tiktokstats}\\n\\n-# [**TikTok**](<{url}>) • [**Download**]({catbox_url})\\n-# This video exceeds the limit of 8MB, hence it was uploaded to [catbox](<https://catbox.moe>)."
                                        await ctx.send(message)
                                    else:
                                        await ctx.send(f"[Video URL]({data['video_url']})", embed=embed)
                                else:
                                    await ctx.send(f"Video is too large, [direct download]({data['video_url']}).", embed=embed)
                            else:
                                await ctx.send(f"[Video URL]({data['video_url']})", embed=embed)
                    except:
                        await ctx.send(f"[Video URL]({data['video_url']})", embed=embed)
                else:
                    await ctx.send(embed=embed)

            except Exception as e:
                await ctx.warn("Failed to process TikTok content")

    @commands.hybrid_command(
        name="telegram",
        description="Get Telegram user/channel information",
        aliases=["tele"]
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(handle="The Telegram username to look up")
    async def telegram(self, ctx: commands.Context, *, handle: str):
        async with ctx.typing():
            try:
                data = await self.bot.cp_system.process_telegram_user(handle)
                
                if not data or 'type' not in data:
                    err = data.get('error') if isinstance(data, dict) else None
                    return await ctx.warn(f"No **Telegram handle** found with that name.")

                if data['type'] == 'user':
                    display_name = f"{data['first_name']} {data['last_name']}" if data['first_name'] and data['last_name'] else data['first_name']
                    title = f"{display_name} (@{handle})" if display_name else f"@{handle}"
                    if data['is_premium']:
                        title += " <:teleprem:1345545700489953391>"
                    
                    description = ""
                    if data['last_seen']:
                        if data['last_seen'] == "now":
                            description += "-# Online now\n"
                        elif data['last_seen'] == "never":
                            description += "-# Never seen online\n"
                        elif data['last_seen'] == "recently":
                            description += "-# Seen recently\n"
                        elif isinstance(data['last_seen'], (int, float)):
                            description += f"-# Last seen <t:{int(data['last_seen'])}:R>\n"
                        else:
                            description += f"-# Last seen {data['last_seen']}\n"
                    else:
                        description += "-# Last seen *a long time ago*\n"
                    
                    if data['bio']:
                        bio = data['bio']
                        for word in bio.split():
                            if word.startswith("@"):
                                gyat = word[1:]
                                bio = bio.replace(word, f"[{word}](https://t.me/{gyat})")
                        description += bio
                else:
                    title = f"{data['title']} (@{handle})"
                    description = f"-# {data['members']} subscribers.  View in [Telegram](https://t.me/{handle}).\n"
                    if data['description']:
                        description += data['description']
                
                color = await self.bot.get_color(ctx.author.id)
                embed = discord.Embed(title=title, description=description, url=f"https://t.me/{handle}", color=color)
                embed.set_footer(text=f"t.me • {data['id']}", icon_url="https://git.cursi.ng/telegram_logo.png")
                embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
                
                view = discord.ui.View()
                view.add_item(discord.ui.Button(label="View", style=discord.ButtonStyle.link, url=f"https://t.me/{handle}"))
                
                if data['profile_photos'] and data['profile_photos'][0]:
                    photo_data = data['profile_photos'][0]
                    file_data = base64.b64decode(photo_data['data'])
                    file = io.BytesIO(file_data)
                    filename = f"profile{photo_data['extension']}"
                    embed.set_thumbnail(url=f"attachment://{filename}")
                    await ctx.send(embed=embed, file=discord.File(file, filename=filename), view=view)
                else:
                    await ctx.send(embed=embed, view=view)
                    
            except Exception as e:
                await ctx.warn(e)

    @commands.hybrid_group(name="x", description="X/Twitter utilities", aliases=["twitter"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def x(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @x.command(name="repost", description="Get information about a X.com (Twitter) post", aliases=["post"])
    @app_commands.describe(url="The URL of the X post")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def repost(self, interaction: commands.Context, url: str):
        ctx = await commands.Context.from_interaction(interaction) if isinstance(interaction, discord.Interaction) else interaction
        await ctx.typing()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            parsed_url = await asyncio.to_thread(urlparse, url)
            if parsed_url.netloc not in ["twitter.com", "x.com"]:
                await ctx.warn("The provided URL must be from X (formerly known as Twitter).")
                return
            match = re.search(r"(?:x\.com|twitter\.com)/([^/]+)/status/(\d+)", url)
            if not match:
                await ctx.warn("Invalid tweet URL format.")
                return
            username, tweet_id = match.groups()
            api_url = f"https://api.fxtwitter.com/{username}/status/{tweet_id}"
            async with self.session.get(api_url) as response:
                if response.status != 200:
                    await ctx.warn("Failed to fetch tweet data.")
                    return
                data = await response.json()
                tweet_data = data.get("tweet", data)
                created_at = tweet_data["created_at"]
                text = tweet_data["text"]
                text = re.sub(r"@(\w+)", r"[@\1](https://x.com/\1)", text)
                text = re.sub(r"#(\w+)", r"[#\1](https://x.com/hashtag/\1)", text)
                timestamp = datetime.strptime(created_at, "%a %b %d %H:%M:%S +0000 %Y")
                formatted_time = timestamp.strftime("%m/%d/%Y %I:%M %p")
                likes = f"{tweet_data['likes']/1000:.1f}k" if tweet_data["likes"] >= 1000 else tweet_data["likes"]
                replies = f"{tweet_data['replies']/1000:.1f}k" if tweet_data["replies"] >= 1000 else tweet_data["replies"]
                retweets = f"{tweet_data['retweets']/1000:.1f}k" if tweet_data["retweets"] >= 1000 else tweet_data["retweets"]
                embed = discord.Embed(
                    description=f"{text}\n\n",
                    color=await self.bot.get_color(ctx.author.id)
                )
                embed.set_author(
                    name=f"{tweet_data['author']['name']} (@{tweet_data['author']['screen_name']})",
                    url=url,
                    icon_url=tweet_data['author']['avatar_url']
                )
                embed.set_footer(text=f"{likes} ❤️ • {replies} 💬 • {retweets} 🔁 | {formatted_time}", icon_url="https://git.cursi.ng/x_logo.png")
                files = []
                has_media = False
                if tweet_data.get("media") and tweet_data["media"].get("all"):
                    has_media = True
                    for media in tweet_data["media"]["all"]:
                        mtype = media["type"]
                        if mtype == "photo":
                            async with self.session.get(media["url"]) as img_response:
                                if img_response.status == 200:
                                    img_data = await img_response.read()
                                    files.append(discord.File(io.BytesIO(img_data), f"heist_{len(files)}.png"))
                        elif mtype in ("video", "gif"):
                            highest_bitrate = 0
                            video_url = None
                            for variant in media.get("variants", []):
                                if variant.get("content_type") == "video/mp4" and variant.get("bitrate", 0) >= highest_bitrate:
                                    highest_bitrate = variant.get("bitrate", 0)
                                    video_url = variant["url"]
                            if video_url:
                                async with self.session.get(video_url) as vid_response:
                                    if vid_response.status == 200:
                                        vid_data = await vid_response.read()
                                        files.append(discord.File(io.BytesIO(vid_data), f"heist_{len(files)}.mp4"))
                perms = ctx.channel.permissions_for(ctx.guild.me if ctx.guild else ctx.bot.user)
                if has_media and not perms.attach_files:
                    await ctx.send("-# Missing the `Attach Files` permission, unable to show media.", embed=embed)
                    return
                if len(files) > 0:
                    await ctx.send(embed=embed, files=files)
                else:
                    await ctx.send(embed=embed)
        except Exception as e:
            await ctx.warn(str(e))

    @commands.hybrid_group(name="pinterest", description="Pinterest utilities")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def pinterest(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @pinterest.command(name="search", description="Search for images on Pinterest")
    @app_commands.describe(query="What to search for on Pinterest")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def search(self, ctx: commands.Context, *, query: str):
        async with ctx.typing():
            image_urls = await self.bot.cp_system.process_pinterest_search(query)
            
            if not image_urls:
                return await ctx.warn(f"No images found for **{query}**")

            async def fetch_image(url):
                async with self.session.get(url) as image_response:
                    if image_response.status == 200:
                        return await image_response.read()

            image_tasks = [fetch_image(url) for url in image_urls[:9]]
            images = await asyncio.gather(*image_tasks)
            images = [img for img in images if img is not None]
            
            if not images:
                return await ctx.warn(f"No images found for **{query}**")

            files = [discord.File(io.BytesIO(image), filename=f"heist_{i+1}.png") for i, image in enumerate(images)]
            await ctx.send(f"Successfully searched for **{query}**.", files=files)

    @pinterest.command(
        name="pin",
        description="View Pinterest pin info",
        aliases=["post", "repost", "r"]
    )
    @app_commands.describe(url="The Pinterest pin URL")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def pinterest_pin(self, ctx: commands.Context, url: str):
        async with ctx.typing():
            try:
                parsed = urlparse(url)
                if parsed.netloc.endswith("pinterest.com") and parsed.path.startswith("/pin/"):
                    pin_id = parsed.path.split('/')[2]
                    cleaned_url = f"https://www.pinterest.com/pin/{pin_id}"
                elif parsed.netloc.endswith("pin.it"):
                    pin_id = parsed.path.lstrip('/')
                    cleaned_url = f"https://www.pinterest.com/pin/{pin_id}"
                else:
                    return await ctx.warn("Please provide a valid Pinterest URL")

                pin_data = await self.bot.cp_system.process_pinterest_pin(cleaned_url)

                if "error" in pin_data:
                    return await ctx.warn(f"Failed to fetch pin: {pin_data['error']}")

                title = pin_data.get("title")
                description = pin_data.get("description")
                embed_url = pin_data.get("link")
                author_username = pin_data.get("fullName")
                author_avatar = pin_data.get("avatar")
                image_url = pin_data.get("image")
                username = pin_data.get("username")
                repin_count = pin_data.get("repinCount", 0)
                comments_count = pin_data.get("commentsCount", 0)
                reactions = pin_data.get("reactions", 0)
                created_at = pin_data.get("createdAt")
                alt_text = pin_data.get("altText")
                annotations = pin_data.get("annotations", [])

                created_at_dt = datetime.strptime(created_at, "%a, %d %b %Y %H:%M:%S %z")
                created_at_fmt = created_at_dt.strftime("%d/%m/%Y %I:%M %p")

                if alt_text != "N/A":
                    annotations_text = f"-# {alt_text}"
                else:
                    annotations_text = "-# " + ", ".join([annotation.get("label", "N/A") for annotation in annotations]) if annotations else ""

                async with self.session.get(image_url) as image_response:
                    if image_response.status == 200:
                        image_data = await image_response.read()
                        image_file = discord.File(io.BytesIO(image_data), filename="pin.jpg")

                        embed = discord.Embed(
                            title=title,
                            description=f"-# {description}\n{annotations_text}",
                            url=embed_url,
                            color=await self.bot.get_color(ctx.author.id)
                        )
                        embed.set_footer(
                            text=f"{repin_count} 📌 • {comments_count} 💬 • {reactions} ❤️ | {created_at_fmt}",
                            icon_url="https://git.cursi.ng/pinterest_logo.png"
                        )
                        embed.set_author(
                            name=f"{author_username} (@{username})",
                            icon_url=author_avatar,
                            url=f"https://www.pinterest.com/{username}/"
                        )
                        embed.set_image(url="attachment://pin.jpg")

                        await ctx.send(embed=embed, file=image_file)
                    else:
                        await ctx.warn("Failed to retrieve the image from Pinterest")

            except Exception as e:
                await ctx.warn(f"Failed to process Pinterest pin: {str(e)}")
    
    get = app_commands.Group(
        name="get", 
        description="Pfp generation commands",
        allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True),
        allowed_installs=app_commands.AppInstallationType(guild=True, user=True)
    )

    @get.command()
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(style="Choose a style for the profile picture")
    @app_commands.choices(style=[
        app_commands.Choice(name="Cat Pfp", value="cat pfp"),
        app_commands.Choice(name="Aesthetic Pfp", value="aesthetic pfp"),
        app_commands.Choice(name="Dark Pfp", value="dark pfp"),
        app_commands.Choice(name="Couple Pfp", value="couple pfp"),
        app_commands.Choice(name="Anime Pfp", value="anime pfp"),
        app_commands.Choice(name="Eboy Pfp", value="eboy pfp"),
        app_commands.Choice(name="Egirl Pfp", value="egirl pfp"),
        app_commands.Choice(name="Opiumcore Pfp", value="opiumcore pfp"),
        app_commands.Choice(name="Grunge Pfp", value="grunge pfp"),
        app_commands.Choice(name="Cartoon Pfp", value="cartoon pfp"),
        app_commands.Choice(name="Indie Pfp", value="indie pfp")
    ])
    async def pfp(self, interaction: discord.Interaction, style: app_commands.Choice[str]):
        ctx = await self.bot.get_context(interaction)
        try:            
            style_keywords = {
                "cat pfp": ["cat profile picture", "cute cat avatar", "cat aesthetic", "cat vibe", "kitten pfp", "cat icon", "kitty profile pic", "kitty pfp"],
                "aesthetic pfp": ["aesthetic profile picture", "minimalist avatar", "soft aesthetic", "aesthetic vibe", "pastel pfp", "vintage aesthetic", "aesthetic icon", "aesthetic profile pic"],
                "dark pfp": ["dark profile picture", "gothic avatar", "moody aesthetic", "dark vibe", "edgy pfp", "dark anime", "shadow pfp", "dark gothic", "emo pfp", "vampire aesthetic"],
                "couple pfp": ["couple profile picture", "matching avatars", "relationship aesthetic", "couple vibe", "love pfp", "romantic pfp", "couple icon", "couple type"],
                "anime pfp": ["anime profile picture", "anime avatar", "kawaii anime", "anime vibe", "anime girl pfp", "anime boy pfp", "anime icon", "anime type"],
                "egirl pfp": ["discord egirl profile picture", "discord egirl aesthetic", "discord pastel egirl", "discord egirl vibe", "discord egirl pfp", "discord egirl makeup", "discord egirl fashion", "discord egirl type"],
                "eboy pfp": ["discord eboy profile picture", "discord comboy", "discord eboy", "discord eboy vibe", "discord eboy pfp", "discord eboy fashion", "discord eboy profile pic", "discord eboy style"],
                "opiumcore pfp": ["opiumcore profile picture", "opiumcore aesthetic", "dark edgy avatar", "opiumcore vibe", "opiumcore icon", "opiumcore fashion", "opiumcore profile pic", "opiumcore mood"],
                "grunge pfp": ["grunge profile picture", "grunge aesthetic", "punk avatar", "grunge vibe", "grunge icon", "grunge fashion", "grunge profile pic", "grunge mood"],
                "cartoon pfp": ["cartoon profile picture", "cartoon avatar", "funny cartoon", "cartoon vibe", "cartoon icon", "cartoon type", "cartoon character", "cartoon style"],
                "indie pfp": ["indie profile picture", "indie aesthetic", "vintage avatar", "indie vibe", "indie icon", "indie type", "indie mood", "indie fashion"]
            }

            style_value = style.value
            keywords = style_keywords.get(style_value, [style_value])
            query = random.choice(keywords) + f" {random.randint(1, 100)}"

            image_urls = await self.bot.cp_system.process_pinterest_search(query)

            if not image_urls:
                await ctx.warn(f"No profile pictures found for **{style_value}**.")
                return

            async def fetch_image(url):
                try:
                    async with self.session.get(url) as image_response:
                        if image_response.status == 200:
                            image_data = await image_response.read()
                            return (url, image_data, len(image_data))
                except Exception:
                    return None

            image_tasks = [fetch_image(url) for url in image_urls[:12]]
            images = await asyncio.gather(*image_tasks)
            images = [img for img in images if img is not None]

            if not images:
                await ctx.warn(f"No profile pictures found for **{style_value}**.")
                return

            images.sort(key=lambda x: x[2])
            
            total_size = 0
            MAX_SIZE = 10 * 1024 * 1024
            cutoff_index = 0
            
            for i, (url, data, size) in enumerate(images):
                if total_size + size > MAX_SIZE:
                    break
                total_size += size
                cutoff_index = i + 1
            
            filtered_images = images[:cutoff_index]
            
            if not filtered_images:
                await ctx.warn("The profile pictures found are too large to send.")
                return

            files = [discord.File(io.BytesIO(data), filename=f"pfp_{i+1}.png") 
                    for i, (url, data, size) in enumerate(filtered_images)]
            
            await ctx.send(f"**{style_value}** (showing {len(files)} of {len(images)} images)", files=files)

        except Exception as e:
            await ctx.warn(str(e))

    @get.command()
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(style="Choose a style for the banner")
    @app_commands.choices(style=[
        app_commands.Choice(name="Cat Banner", value="cat banner"),
        app_commands.Choice(name="Aesthetic Banner", value="aesthetic banner"),
        app_commands.Choice(name="Dark Banner", value="dark banner"),
        app_commands.Choice(name="Couple Banner", value="couple banner"),
        app_commands.Choice(name="Anime Banner", value="anime banner"),
        app_commands.Choice(name="Eboy Banner", value="eboy banner"),
        app_commands.Choice(name="Egirl Banner", value="egirl banner"),
        app_commands.Choice(name="Opiumcore Banner", value="opiumcore banner"),
        app_commands.Choice(name="Grunge Banner", value="grunge banner"),
        app_commands.Choice(name="Cartoon Banner", value="cartoon banner"),
        app_commands.Choice(name="Indie Banner", value="indie banner")
    ])
    async def banner(self, interaction: discord.Interaction, style: app_commands.Choice[str]):
        ctx = await self.bot.get_context(interaction)
        try:
            style_keywords = {
                "cat banner": ["cat banner", "cute cat banner", "cat aesthetic banner", "cat vibe banner", "kitten banner", "cat illustration banner", "cat type banner"],
                "aesthetic banner": ["aesthetic banner", "minimalist banner", "soft aesthetic banner", "aesthetic vibe banner", "pastel banner", "vintage aesthetic banner", "aesthetic wallpaper banner"],
                "dark banner": ["dark banner", "gothic banner", "moody aesthetic banner", "dark vibe banner", "edgy banner", "dark anime banner", "shadow banner", "dark gothic banner", "emo banner", "vampire aesthetic banner"],
                "couple banner": ["couple banner", "matching banners", "relationship aesthetic banner", "couple vibe banner", "love banner", "romantic banner", "couple type banner"],
                "anime banner": ["anime banner", "anime vibe banner", "kawaii anime banner", "anime girl banner", "anime boy banner", "anime type banner"],
                "egirl banner": ["discord egirl banner", "discord egirl aesthetic banner", "discord pastel egirl banner", "discord egirl vibe banner", "discord egirl fashion banner", "discord egirl type banner"],
                "eboy banner": ["discord eboy banner", "discord eboy aesthetic banner", "discord dark eboy banner", "discord eboy vibe banner", "discord eboy fashion banner", "discord eboy type banner"],
                "opiumcore banner": ["opiumcore banner", "opiumcore aesthetic banner", "dark edgy banner", "opiumcore vibe banner", "opiumcore fashion banner", "opiumcore drawing banner"],
                "grunge banner": ["grunge banner", "grunge aesthetic banner", "punk banner", "grunge vibe banner", "grunge fashion banner", "grunge type banner"],
                "cartoon banner": ["cartoon banner", "funny cartoon banner", "cartoon vibe banner", "cartoon character banner", "cartoon style banner"],
                "indie banner": ["indie banner", "indie aesthetic banner", "vintage banner", "indie vibe banner", "indie type banner", "indie fashion banner"]
            }

            style_value = style.value
            keywords = style_keywords.get(style_value, [style_value])
            query = random.choice(keywords) + f" {random.randint(1, 100)}"

            image_urls = await self.bot.cp_system.process_pinterest_search(query)

            if not image_urls:
                await ctx.warn(f"No banners found for **{style_value}**.")
                return

            async def fetch_image(url):
                try:
                    async with self.session.get(url) as image_response:
                        if image_response.status == 200:
                            image_data = await image_response.read()
                            return (url, image_data, len(image_data))
                except Exception:
                    return None

            image_tasks = [fetch_image(url) for url in image_urls[:12]]
            images = await asyncio.gather(*image_tasks)
            images = [img for img in images if img is not None]

            if not images:
                await ctx.warn(f"No banners found for **{style_value}**.")
                return

            images.sort(key=lambda x: x[2])
            
            total_size = 0
            MAX_SIZE = 10 * 1024 * 1024
            cutoff_index = 0
            
            for i, (url, data, size) in enumerate(images):
                if total_size + size > MAX_SIZE:
                    break
                total_size += size
                cutoff_index = i + 1
            
            filtered_images = images[:cutoff_index]
            
            if not filtered_images:
                await ctx.warn("The banners found are too large to send.")
                return

            files = [discord.File(io.BytesIO(data), filename=f"banner_{i+1}.png") 
                    for i, (url, data, size) in enumerate(filtered_images)]
            
            await ctx.send(f"**{style_value}** (showing {len(files)} of {len(images)} images)", files=files)

        except Exception as e:
            await ctx.warn(str(e))


    @commands.hybrid_group(name="youtube", description="YouTube related commands", aliases=["yt"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def youtube(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    async def search_autocomplete(self, interaction: discord.Interaction, current: str):
        if not current:
            return []
        try:
            search_results = await asyncio.to_thread(lambda: Search(current).results[:5])
            return [
                app_commands.Choice(name=video.title[:100], value=video.watch_url)
                for video in search_results
            ]
        except Exception:
            return []
        
    @youtube.command(name="search", description="Search YouTube videos", aliases=["s"])
    @app_commands.describe(query="The query to search")
    @app_commands.autocomplete(query=search_autocomplete)
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def search(self, ctx: commands.Context, *, query: str):
        async with ctx.typing():
            try:
                search_results = await asyncio.to_thread(lambda: Search(query).results)
                if not search_results:
                    return await ctx.warn("No videos found")

                pages = []
                for i, video in enumerate(search_results, 1):
                    pages.append(f"{video.watch_url}")

                if len(pages) == 1:
                    await ctx.send(pages[0])
                else:
                    from heist.framework.pagination import Paginator
                    await Paginator(ctx, pages).start()
                                
            except Exception as e:
                await ctx.warn(str(e))

    @commands.hybrid_group(name="minecraft", description="Minecraft related commands", aliases=["mc"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def minecraft(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @minecraft.command(name="user", description="Get Minecraft user information", aliases=["u", "profile"])
    @app_commands.describe(username="The Minecraft username to look up")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def mcuser(self, ctx: commands.Context, username: str):
        if not username:
            return await ctx.warn("Please provide a Minecraft username")
        async with ctx.typing():
            search_url = f"https://laby.net/api/search/names/{username}"
            async with self.session.get(search_url) as resp:
                if resp.status != 200:
                    return await ctx.warn(f"Failed to fetch data for `{username}`")
                data = await resp.json()
                if not data['results']:
                    return await ctx.warn(f"No data found for `{username}`")
                player_info = data['results'][0]
                player_name = player_info['name']
            history_url = f"https://laby.net/api/search/get-previous-accounts/{username}"
            async with self.session.get(history_url) as resp:
                if resp.status != 200:
                    return await ctx.warn(f"Failed to fetch username history for `{username}`")
                history_data = await resp.json()
            if not history_data['users']:
                return await ctx.warn(f"No username history found for `{username}`")
            history = history_data['users'][0]['history']
            history_list = []
            if history:
                for entry in history:
                    name = entry['name']
                    changed_at = entry['changed_at']
                    formatted_change = f"**`{name}`**`({changed_at[:10] if changed_at else 'N/A'})`"
                    history_list.append(formatted_change)
            else:
                history_list.append("Not available")
            color = await self.bot.get_color(ctx.author.id)
            embed = Embed(title=player_name, url=f"https://laby.net/@{player_name}", color=color)
            embed.add_field(name="Username History", value=", ".join(history_list), inline=False)
            embed.set_thumbnail(url=f"https://mineskin.eu/avatar/{player_name}")
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
            embed.set_footer(text="heist.lol", icon_url="https://git.cursi.ng/minecraft_logo.png")
            await ctx.send(embed=embed)

    @minecraft.command(name="server", description="Get Minecraft server information", aliases=["s"])
    @app_commands.describe(address="The address of the Minecraft server")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def mcserver(self, ctx: commands.Context, address: str):
        if not address:
            return await ctx.warn("Please provide a server address")
        async with ctx.typing():
            url = f"https://api.mcstatus.io/v2/status/java/{address}?query=true"
            async with self.session.get(url) as response:
                if response.status != 200:
                    return await ctx.warn(f"Failed to fetch data for `{address}`")
                server_data = await response.json()
                if not server_data.get('online', False):
                    return await ctx.warn("Server not found or offline")
                host = server_data.get('host', 'Unknown')
                ip_address = server_data.get('ip_address', 'Unknown')
                players_online = server_data['players'].get('online', 0)
                max_players = server_data['players'].get('max', 0)
                motd = server_data['motd'].get('clean', 'Unknown')
                version = server_data['version'].get('name_clean', 'Unknown')
                icon = server_data.get('icon')
                color = await self.bot.get_color(ctx.author.id)
                embed = Embed(title=host, color=color)
                embed.add_field(name="Online", value="Yes", inline=True)
                embed.add_field(name="IP Address", value=ip_address, inline=True)
                embed.add_field(name="Players", value=f"{players_online}/{max_players}", inline=True)
                embed.add_field(name="MOTD", value=motd, inline=False)
                embed.add_field(name="Version", value=version, inline=True)
                embed.set_footer(text="heist.lol", icon_url="https://git.cursi.ng/minecraft_logo.png")
                embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
                if icon:
                    icon_data = icon.split(",")[1]
                    icon_bytes = io.BytesIO(base64.b64decode(icon_data))
                    file = discord.File(icon_bytes, filename="server_icon.png")
                    embed.set_thumbnail(url="attachment://server_icon.png")
                    await ctx.send(embed=embed, file=file)
                else:
                    await ctx.send(embed=embed)

    @minecraft.command(name="randomserver", description="Get a random Minecraft server", aliases=["rs", "random"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def mcrandomserver(self, ctx: commands.Context):
        async with ctx.typing():
            url = "https://minecraft-mp.com/servers/random/"
            headers = {'User-Agent': 'Mozilla/5.0'}
            try:
                async with self.session.get(url, headers=headers) as response:
                    if response.status != 200:
                        return await ctx.warn("Failed to fetch random server")
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    server_elements = soup.find_all(attrs={"data-clipboard-text": True})
                    server_ips = [elem['data-clipboard-text'] for elem in server_elements]
                    if not server_ips:
                        return await ctx.warn("No servers found")
                    random_ip = random.choice(server_ips)
                    status_url = f"https://api.mcstatus.io/v2/status/java/{random_ip}?query=true"
                    async with self.session.get(status_url) as status_response:
                        if status_response.status != 200:
                            return await ctx.warn("Failed to fetch server status")
                        server_data = await status_response.json()
                        if not server_data.get('online', False):
                            return await ctx.warn("Found server but it's offline")
                        host = server_data.get('host', 'Unknown')
                        players_online = server_data['players'].get('online', 0)
                        max_players = server_data['players'].get('max', 0)
                        motd = server_data['motd'].get('clean', 'Unknown')
                        version = server_data['version'].get('name_clean', 'Unknown')
                        icon = server_data.get('icon')
                        color = await self.bot.get_color(ctx.author.id)
                        embed = Embed(title="Random Minecraft Server", color=color)
                        embed.add_field(name="Server IP", value=f"`{random_ip}`", inline=False)
                        embed.add_field(name="Players", value=f"{players_online}/{max_players}", inline=True)
                        embed.add_field(name="Version", value=version, inline=True)
                        if motd != "Unknown":
                            embed.add_field(name="MOTD", value=motd, inline=False)
                        embed.set_footer(text="heist.lol", icon_url="https://git.cursi.ng/minecraft_logo.png")
                        embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
                        if icon:
                            icon_data = icon.split(",")[1]
                            icon_bytes = io.BytesIO(base64.b64decode(icon_data))
                            file = discord.File(icon_bytes, filename="server_icon.png")
                            embed.set_thumbnail(url="attachment://server_icon.png")
                            await ctx.send(embed=embed, file=file)
                        else:
                            await ctx.send(embed=embed)
            except Exception as e:
                await ctx.warn(e)

    # @youtube.command(name="getmp3", description="✨ Convert YouTube video to MP3", aliases=["yt2mp3", "ytmp3"])
    # @app_commands.describe(query="Search query or video URL")
    # @app_commands.autocomplete(query=search_autocomplete)
    # @app_commands.allowed_installs(users=True)
    # @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    # @disabled()
    # @donor_only()
    # async def youtube2mp3(self, ctx: commands.Context, *, query: str):
    #     try:
    #         async with ctx.typing():
    #             if "youtube.com/watch?v=" in query or "youtu.be/" in query:
    #                 video_id = query.split("v=")[-1].split("&")[0]
    #             else:
    #                 search_results = await asyncio.to_thread(lambda: Search(query).results)
    #                 if not search_results:
    #                     return await ctx.warn("No videos found")
    #                 video_id = search_results[0].watch_url.split("v=")[-1]
                
    #             video_info = await self.get_video_info(video_id)
    #             await ctx.approve(f"[download audio]({video_info['stream']})")
                
    #     except Exception as e:
    #         await ctx.warn(f"Error getting audio info: {str(e)}")

    # @youtube.command(name="getmp4", description="✨ Convert YouTube video to MP4", aliases=["yt2mp4", "ytmp4"])
    # @app_commands.describe(query="Search query or video URL")
    # @app_commands.autocomplete(query=search_autocomplete)
    # @app_commands.allowed_installs(users=True)
    # @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    # @disabled()
    # @donor_only()
    # async def youtube2mp4(self, ctx: commands.Context, *, query: str):
    #     async with ctx.typing():
    #         try:
    #             if "/shorts/" in query:
    #                 return await ctx.warn("Shorts not supported")
                    
    #             if "youtube.com/watch?v=" in query or "youtu.be/" in query:
    #                 video_id = query.split("v=")[-1].split("&")[0]
    #             else:
    #                 search_results = await asyncio.to_thread(lambda: Search(query).results)
    #                 if not search_results:
    #                     return await ctx.warn("No videos found")
    #                 video_id = search_results[0].watch_url.split("v=")[-1]
                
    #             video_info = await self.get_video_info(video_id)
    #             await ctx.approve(f"[download video]({video_info['stream']})")
                
    #         except Exception as e:
    #             await ctx.warn(f"Error getting video info: {str(e)}")

    @commands.hybrid_command(name="gunslol", description="Lookup a guns.lol user", aliases=["guns"])
    @app_commands.describe(username="The Guns.lol username.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def gunslol(self, ctx: commands.Context, username: str):
        try:
            await ctx.typing()
            url = "https://guns.lol/api/user/lookup?type=username"
            headers = {"Content-Type": "application/json"}
            data = {"username": username, "key": GUNSLOL_KEY}
            async with self.session.post(url, headers=headers, json=data) as response:
                if response.status != 200:
                    return await ctx.warn("User not found, check out [@cosmin](https://guns.lol/cosmin) tho.")
                user_data = await response.json()
                if user_data.get("error"):
                    return await ctx.warn(user_data["error"])
                title = user_data["username"]
                if "premium" in user_data["config"]["user_badges"]:
                    title += " <a:diamond:1282326797685624832>"
                color = await self.bot.get_color(ctx.author.id)
                embed = discord.Embed(
                    title=title,
                    url=f"https://guns.lol/{user_data['username']}",
                    description=user_data["config"]["description"],
                    color=color
                )
                embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
                avatar = user_data["config"].get("avatar")
                if avatar:
                    embed.set_thumbnail(url=avatar)
                background = user_data["config"].get("url")
                if background and background.lower().endswith((".jpg", ".jpeg", ".png", ".gif")):
                    embed.set_image(url=background)
                created_timestamp = user_data.get("account_created")
                if created_timestamp:
                    embed.add_field(name="Created", value=f"<t:{created_timestamp}:R>", inline=True)
                alias = user_data.get("alias")
                if alias:
                    embed.add_field(name="Alias", value=alias, inline=True)
                file_url = user_data.get("config", {}).get("url")
                if file_url:
                    if file_url.lower().endswith((".mp4", ".avi", ".mov")):
                        field_name = "Video"
                    elif file_url.lower().endswith((".jpg", ".jpeg", ".png")):
                        field_name = "Image"
                    elif file_url.lower().endswith(".gif"):
                        field_name = "GIF"
                    else:
                        field_name = "File"
                    embed.add_field(name=field_name, value=f"[Click here]({file_url})", inline=True)
                audio_list = user_data.get("config", {}).get("audio")
                if audio_list:
                    if isinstance(audio_list, list):
                        audio_field_lines = []
                        for i, a in enumerate(audio_list, start=1):
                            url = a.get("url")
                            if not url:
                                continue
                            title = a.get("title")
                            if not title or not title.strip():
                                filename = url.split("/")[-1]
                                if filename.endswith(".mp3"):
                                    filename = filename[:-4]
                                title = filename or f"Audio {i}"
                            audio_field_lines.append(f"[{title}]({url})")
                        audio_field = "\n".join(audio_field_lines)
                    elif isinstance(audio_list, str):
                        audio_field = f"[Click here]({audio_list.strip()})"
                    else:
                        audio_field = "Unknown audio format"
                    embed.add_field(name="Audio", value=audio_field, inline=True)
                cursor = user_data.get("config", {}).get("custom_cursor")
                if cursor:
                    embed.add_field(name="Cursor", value=f"[Click here]({cursor})", inline=True)
                embed.set_footer(
                    text=f"{user_data['config']['page_views']} views ● UID {user_data['uid']}",
                    icon_url="https://git.cursi.ng/guns_logo.png?v2"
                )
                await ctx.reply(embed=embed)
        except Exception as e:
            print(f"Got the following error in gunslol: {e}")
            pass

    @hybrid_group(name="fortnite", description="Fortnite utilities")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def fortnite(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @fortnite.command(name="shop", description="View today's Fortnite shop")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def shop(self, ctx):
        await ctx.defer()
        try:
            async with self.bot.session.get("http://127.0.0.1:8067/fortnite/getshop") as r:
                img = await r.read()
            file = discord.File(io.BytesIO(img), filename="fortniteshop.png")
            await ctx.send(file=file)
        except Exception as e:
            await ctx.warn(e)

async def setup(bot):
    await bot.add_cog(Social(bot))
