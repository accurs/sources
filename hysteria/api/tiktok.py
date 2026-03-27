import aiohttp
import asyncio
from fastapi import FastAPI, HTTPException, Request
from typing import Union, Dict, Any, Optional
from bs4 import BeautifulSoup
import json
from datetime import datetime
import uvicorn
import redis.asyncio as redis
import sqlite3
import os
import re

app = FastAPI()

DB_FILE = "whitelist.db"
if not os.path.exists(DB_FILE):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("CREATE TABLE api_keys (key TEXT PRIMARY KEY, owner TEXT, expires_at TEXT, ratelimit TEXT)")
    conn.commit()
    conn.close()

REGION_MAP = {"AF":"Afghanistan","AX":"Åland Islands","AL":"Albania","DZ":"Algeria","AS":"American Samoa","AD":"Andorra","AO":"Angola","AI":"Anguilla","AQ":"Antarctica","AG":"Antigua and Barbuda","AR":"Argentina","AM":"Armenia","AW":"Aruba","AU":"Australia","AT":"Austria","AZ":"Azerbaijan","BS":"Bahamas","BH":"Bahrain","BD":"Bangladesh","BB":"Barbados","BY":"Belarus","BE":"Belgium","BZ":"Belize","BJ":"Benin","BM":"Bermuda","BT":"Bhutan","BO":"Bolivia","BA":"Bosnia and Herzegovina","BW":"Botswana","BR":"Brazil","IO":"British Indian Ocean Territory","BN":"Brunei Darussalam","BG":"Bulgaria","BF":"Burkina Faso","BI":"Burundi","KH":"Cambodia","CM":"Cameroon","CA":"Canada","CV":"Cabo Verde","KY":"Cayman Islands","CF":"Central African Republic","TD":"Chad","CL":"Chile","CN":"China","CX":"Christmas Island","CC":"Cocos (Keeling) Islands","CO":"Colombia","KM":"Comoros","CG":"Congo","CD":"Congo (Democratic Republic)","CK":"Cook Islands","CR":"Costa Rica","CI":"Côte d'Ivoire","HR":"Croatia","CU":"Cuba","CW":"Curaçao","CY":"Cyprus","CZ":"Czechia","DK":"Denmark","DJ":"Djibouti","DM":"Dominica","DO":"Dominican Republic","EC":"Ecuador","EG":"Egypt","SV":"El Salvador","GQ":"Equatorial Guinea","ER":"Eritrea","EE":"Estonia","SZ":"Eswatini","ET":"Ethiopia","FK":"Falkland Islands (Malvinas)","FO":"Faroe Islands","FJ":"Fiji","FI":"Finland","FR":"France","GF":"French Guiana","PF":"French Polynesia","TF":"French Southern Territories","GA":"Gabon","GM":"Gambia","GE":"Georgia","DE":"Germany","GH":"Ghana","GI":"Gibraltar","GR":"Greece","GL":"Greenland","GD":"Grenada","GP":"Guadeloupe","GU":"Guam","GT":"Guatemala","GG":"Guernsey","GN":"Guinea","GW":"Guinea-Bissau","GY":"Guyana","HT":"Haiti","VA":"Holy See","HN":"Honduras","HK":"Hong Kong","HU":"Hungary","IS":"Iceland","IN":"India","ID":"Indonesia","IR":"Iran","IQ":"Iraq","IE":"Ireland","IM":"Isle of Man","IL":"Israel","IT":"Italy","JM":"Jamaica","JP":"Japan","JE":"Jersey","JO":"Jordan","KZ":"Kazakhstan","KE":"Kenya","KI":"Kiribati","KP":"Korea (Democratic People's Republic)","KR":"Korea (Republic)","KW":"Kuwait","KG":"Kyrgyzstan","LA":"Lao People's Democratic Republic","LV":"Latvia","LB":"Lebanon","LS":"Lesotho","LR":"Liberia","LY":"Libya","LI":"Liechtenstein","LT":"Lithuania","LU":"Luxembourg","MO":"Macao","MG":"Madagascar","MW":"Malawi","MY":"Malaysia","MV":"Maldives","ML":"Mali","MT":"Malta","MH":"Marshall Islands","MQ":"Martinique","MR":"Mauritania","MU":"Mauritius","YT":"Mayotte","MX":"Mexico","FM":"Micronesia (Federated States)","MD":"Moldova (Republic)","MC":"Monaco","MN":"Mongolia","ME":"Montenegro","MS":"Montserrat","MA":"Morocco","MZ":"Mozambique","MM":"Myanmar","NA":"Namibia","NR":"Nauru","NP":"Nepal","NL":"Netherlands","NC":"New Caledonia","NZ":"New Zealand","NI":"Nicaragua","NE":"Niger","NG":"Nigeria","NU":"Niue","NF":"Norfolk Island","MP":"Northern Mariana Islands","NO":"Norway","OM":"Oman","PK":"Pakistan","PW":"Palau","PS":"Palestine, State of","PA":"Panama","PG":"Papua New Guinea","PY":"Paraguay","PE":"Peru","PH":"Philippines","PN":"Pitcairn","PL":"Polany","PT":"Portugal","PR":"Puerto Rico","QA":"Qatar","MK":"Republic of North Macedonia","RO":"Romania","RU":"Russian Federation","RW":"Rwanda","RE":"Réunion","BL":"Saint Barthélemy","SH":"Saint Helena, Ascension and Tristan da Cunha","KN":"Saint Kitts and Nevis","LC":"Saint Lucia","MF":"Saint Martin (French part)","PM":"Saint Pierre and Miquelon","VC":"Saint Vincent and the Grenadines","WS":"Samoa","SM":"San Marino","ST":"Sao Tome and Principe","SA":"Saudi Arabia","SN":"Senegal","RS":"Serbia","SC":"Seychelles","SL":"Sierra Leone","SG":"Singapore","SX":"Sint Maarten (Dutch part)","SK":"Slovakia","SI":"Slovenia","SB":"Solomon Islands","SO":"Somalia","ZA":"South Africa","GS":"South Georgia and the South Sandwich Islands","SS":"South Sudan","ES":"Spain","LK":"Sri Lanka","SD":"Sudan","SR":"Suriname","SJ":"Svalbard and Jan Mayen","SE":"Sweden","CH":"Switzerland","SY":"Syrian Arab Republic","TW":"Taiwan","TJ":"Tajikistan","TZ":"Tanzania, United Republic of","TH":"Thailand","TL":"Timor-Leste","TG":"Togo","TK":"Tokelau","TO":"Tonga","TT":"Trinidad and Tobago","TN":"Tunisia","TR":"Turkey","TM":"Turkmenistan","TC":"Turks and Caicos Islands","TV":"Tuvalu","UG":"Uganda","UA":"Ukraine","AE":"United Arab Emirates","GB":"United Kingdom","UM":"United States Minor Outlying Islands","US":"United States","UY":"Uruguay","UZ":"Uzbekistan","VU":"Vanuatu","VE":"Venezuela","VN":"Viet Nam","VG":"Virgin Islands (British)","VI":"Virgin Islands (U.S.)","WF":"Wallis and Futuna","EH":"Western Sahara","YE":"Yemen","ZM":"Zambia","ZW":"Zimbabwe"}

def load_tiktok_cookies():
    path = "/root/heist-v3/heist/framework/dataprocessing/tiktok/tiktok_cookies.txt"
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            cookies = json.load(f)
        jar = aiohttp.CookieJar()
        for c in cookies:
            jar.update_cookies({c["name"]: c["value"]}, response_url=f"https://{c['domain'].lstrip('.')}/")
        return jar
    except:
        return None

COOKIE_JAR = load_tiktok_cookies()

def check_api_key(key):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT expires_at FROM api_keys WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    if not row:
        return False
    expires_at = row[0]
    if expires_at:
        return datetime.fromisoformat(expires_at) > datetime.utcnow()
    return True

@app.on_event("startup")
async def startup_event():
    app.state.redis = await redis.from_url("redis://localhost", decode_responses=True)

@app.on_event("shutdown")
async def shutdown_event():
    await app.state.redis.close()

@app.on_event("startup")
async def cleanup_expired_keys_task():
    async def cleanup_loop():
        while True:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            now_iso = datetime.utcnow().isoformat()
            c.execute("DELETE FROM api_keys WHERE expires_at IS NOT NULL AND expires_at < ?", (now_iso,))
            conn.commit()
            conn.close()
            await asyncio.sleep(60)
    asyncio.create_task(cleanup_loop())

async def resolve_short_url(url: str) -> str:
    try:
        headers = {
            "user-agent": "Mozilla/5.0",
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
        }
        async with aiohttp.ClientSession(cookie_jar=COOKIE_JAR) as session:
            async with session.get(url, headers=headers, allow_redirects=True) as response:
                return str(response.url)
    except:
        return url

def extract_video_id_from_url(url: str) -> Optional[int]:
    video_id_pattern = re.compile(r"https?://(?:www\.)?tiktok\.com/\S*/(?:video|photo)/(\d+)")
    shortened_url_pattern = re.compile(r"https?://(?:www\.)?(?:vm\.tiktok\.com|tiktok\.com/t/[a-zA-Z0-9]+|vt\.tiktok\.com/[a-zA-Z0-9]+)")
    if match := video_id_pattern.search(url):
        return int(match.group(1))
    elif shortened_url_pattern.search(url):
        return None
    return None

async def get_video_download_url(item_id: Union[str, int]) -> Dict[str, Any]:
    try:
        headers = {
            "user-agent": "Mozilla/5.0",
            "accept": "*/*",
        }
        async with aiohttp.ClientSession(cookie_jar=COOKIE_JAR) as session:
            async with session.get(f"https://www.tiktok.com/player/api/v1/items?item_ids={item_id}", headers=headers) as response:
                if not response.ok:
                    return {"error": f"API request failed with status {response.status}"}
                data = await response.json()
                if not data.get("items"):
                    return {"error": "No video data found"}
                item = data["items"][0]
                aweme_type = item.get("aweme_type")
                raw_id = item.get("id")
                try:
                    normalized_id = str(item_id)
                except:
                    normalized_id = str(raw_id)
                music_info = item.get("music_info", {})
                statistics_info = item.get("statistics_info", {})
                result = {
                    "id": normalized_id,
                    "desc": item.get("desc", ""),
                    "is_image_post": aweme_type == 150,
                    "region": item.get("region"),
                    "author": {
                        "uniqueId": item.get("author_info", {}).get("unique_id"),
                        "nickname": item.get("author_info", {}).get("nickname")
                    },
                    "music": {
                        "id": item.get("music", {}).get("id"),
                        "title": item.get("music", {}).get("title"),
                        "authorName": item.get("music", {}).get("authorName"),
                        "playUrl": item.get("music", {}).get("playUrl")
                    },
                    "music_info": {
                        "author": music_info.get("author"),
                        "id": music_info.get("id"),
                        "id_str": music_info.get("id_str"),
                        "title": music_info.get("title")
                    },
                    "stats": {
                        "likeCount": statistics_info.get("digg_count"),
                        "shareCount": statistics_info.get("share_count"),
                        "commentCount": statistics_info.get("comment_count"),
                        "playCount": item.get("stats", {}).get("playCount"),
                        "collectCount": item.get("stats", {}).get("collectCount", 0)
                    }
                }
                if "video_info" in item and item["video_info"].get("url_list"):
                    video_url = item["video_info"]["url_list"][0]
                    if aweme_type == 150:
                        result["audio_url"] = video_url
                    else:
                        result["video_url"] = video_url
                if "image_post_info" in item:
                    images = item["image_post_info"].get("images", [])
                    result["image_urls"] = []
                    for img in images:
                        if "display_image" in img and "url_list" in img["display_image"]:
                            if img["display_image"]["url_list"]:
                                result["image_urls"].append(img["display_image"]["url_list"][0])
                return result
    except Exception as e:
        return {"error": str(e)}

async def get_video_details_from_html(final_url: str) -> Dict[str, Any]:
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "accept": "text/html"
    }
    async with aiohttp.ClientSession(cookie_jar=COOKIE_JAR) as session:
        async with session.get(final_url, headers=headers) as r:
            if r.status != 200:
                return {"error": f"Failed to fetch video page: {r.status}"}
            text = await r.text()
    soup = BeautifulSoup(text, "html.parser")
    script_tag = None
    for script in soup.find_all("script"):
        if script.string and "__UNIVERSAL_DATA_FOR_REHYDRATION__" in script.attrs.get("id", ""):
            script_tag = script.string
            break
    if not script_tag:
        return {"error": "Video info not found in HTML"}
    try:
        data = json.loads(script_tag)
    except:
        return {"error": "Failed to parse video data"}
    video_detail = data.get("__DEFAULT_SCOPE__", {}).get("webapp.video-detail", {})
    item_info = video_detail.get("itemInfo", {})
    video_data = item_info.get("itemStruct", {})
    if not video_data:
        return {"error": "Video data not found"}
    create_time = None
    if "createTime" in video_data:
        try:
            create_time = datetime.utcfromtimestamp(int(video_data["createTime"])).isoformat() + ".000Z"
        except:
            create_time = video_data["createTime"]
    return {
        "id": video_data.get("id"),
        "description": video_data.get("desc"),
        "createTime": create_time,
        "locationCreated": video_data.get("locationCreated"),
        "fullLocation": REGION_MAP.get(video_data.get("locationCreated"), "Unknown") if video_data.get("locationCreated") else None,
        "author": {
            "uniqueId": video_data.get("author", {}).get("uniqueId"),
            "nickname": video_data.get("author", {}).get("nickname")
        },
        "music": {
            "id": video_data.get("music", {}).get("id"),
            "title": video_data.get("music", {}).get("title"),
            "authorName": video_data.get("music", {}).get("authorName"),
            "playUrl": video_data.get("music", {}).get("playUrl")
        },
        "stats": {
            "likeCount": video_data.get("stats", {}).get("diggCount"),
            "shareCount": video_data.get("stats", {}).get("shareCount"),
            "commentCount": video_data.get("stats", {}).get("commentCount"),
            "playCount": video_data.get("stats", {}).get("playCount"),
            "collectCount": video_data.get("stats", {}).get("collectCount", 0)
        },
        "video": {
            "duration": video_data.get("video", {}).get("duration"),
            "height": video_data.get("video", {}).get("height"),
            "width": video_data.get("video", {}).get("width"),
            "ratio": video_data.get("video", {}).get("ratio"),
            "coverUrl": video_data.get("video", {}).get("originCover")
        }
    }

async def get_tikwm_download_url(url: str) -> Optional[str]:
    tikwm_url = f"https://www.tikwm.com/api/?url={url}"
    headers = {"user-agent": "Mozilla/5.0"}
    start_time = asyncio.get_event_loop().time()
    retry_count = 0
    while asyncio.get_event_loop().time() - start_time < 10:
        try:
            async with aiohttp.ClientSession(cookie_jar=COOKIE_JAR) as session:
                async with session.get(tikwm_url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == 0:
                            return data.get("data", {}).get("play")
                        elif data.get("msg") == "Free Api Limit: 1 request/second.":
                            retry_count += 1
                            await asyncio.sleep(1.1)
                            continue
                        else:
                            return None
                    else:
                        return None
        except:
            return None
    return None

@app.get("/v1/search/tiktok/{username}")
async def search_tiktok(username: str, request: Request, key: str = None, api_key: str = None):
    if username.startswith("@"):
        username = username[1:]
    client_host = request.client.host
    header_key = request.headers.get("x-api-key")
    key_to_check = key or api_key or header_key
    if client_host not in ("127.0.0.1", "localhost"):
        if not key_to_check or not check_api_key(key_to_check):
            raise HTTPException(status_code=403, detail="Forbidden: invalid API key")
        redis_conn = app.state.redis
        limit_key_min = f"rate_min:{key_to_check}"
        limit_key_day = f"rate_day:{key_to_check}"
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT owner, ratelimit FROM api_keys WHERE key=?", (key_to_check,))
        row = c.fetchone()
        conn.close()
        owner, ratelimit = row if row else (None, "standard")
        if ratelimit == "standard" and owner != "cosmin":
            min_count = await redis_conn.get(limit_key_min)
            day_count = await redis_conn.get(limit_key_day)
            if min_count and int(min_count) >= 100:
                raise HTTPException(status_code=429, detail="Rate limit exceeded (per minute)")
            if day_count and int(day_count) >= 30000:
                raise HTTPException(status_code=429, detail="Rate limit exceeded (per day)")
            p = await redis_conn.pipeline()
            p.incr(limit_key_min, 1)
            p.expire(limit_key_min, 60)
            p.incr(limit_key_day, 1)
            p.expire(limit_key_day, 86400)
            await p.execute()
    redis_conn = app.state.redis
    cache_key = f"tiktok:{username}"
    cached = await redis_conn.get(cache_key)
    if cached:
        ttl = await redis_conn.ttl(cache_key)
        result = json.loads(cached)
        result["cache"] = {"cached": True, "ttl": ttl}
        return result
    headers = {"Host": "www.tiktok.com", "user-agent": "Mozilla/5.0 (Linux; Android 8.0.0; Plume L2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.88 Mobile Safari/537.36"}
    async with aiohttp.ClientSession(cookie_jar=COOKIE_JAR) as session:
        async with session.get(f"https://www.tiktok.com/@{username}", headers=headers) as r:
            if r.status != 200:
                raise HTTPException(status_code=r.status, detail="failed to fetch profile")
            text = await r.text()
    soup = BeautifulSoup(text, "html.parser")
    user_data_script = None
    for script in soup.find_all("script"):
        if script.string and "userInfo" in script.string:
            user_data_script = script.string
            break
    if not user_data_script:
        raise HTTPException(status_code=404, detail="user info not found")
    try:
        data = json.loads(user_data_script)
    except:
        raise HTTPException(status_code=500, detail="failed to parse user data")
    user_info = data.get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {}).get("userInfo", {})
    user = user_info.get("user", {})
    statsV2 = user_info.get("statsV2", {})
    create_unix = user.get("createTime", 0)
    create_time = datetime.utcfromtimestamp(create_unix).strftime("%Y-%m-%d %H:%M:%S") if create_unix else None
    avatar_larger = user.get("avatarLarger")
    avatar_medium = user.get("avatarMedium")
    avatar_thumb = user.get("avatarThumb")
    bio_link = user.get("bioLink", {}).get("link")
    result = {
        "user_id": user.get("id"),
        "username": username,
        "nickname": user.get("nickname"),
        "bio": user.get("signature"),
        "region": REGION_MAP.get(user.get("region"), "Unknown"),
        "region_code": user.get("region"),
        "language": user.get("language"),
        "verified": user.get("verified", False),
        "create_time": create_time,
        "nickNameModifyTime": user.get("nickNameModifyTime"),
        "uniqueIdModifyTime": user.get("uniqueIdModifyTime"),
        "followers": int(statsV2.get("followerCount", 0)),
        "following": int(statsV2.get("followingCount", 0)),
        "likes": int(statsV2.get("heartCount", 0)),
        "videos": int(statsV2.get("videoCount", 0)),
        "avatar": {"larger": avatar_larger, "medium": avatar_medium, "thumb": avatar_thumb},
        "bio_link": bio_link,
        "cache": {"cached": False}
    }
    if username.lower() == "csynholic":
        result["region"] = "Atlantis"
        result["region_code"] = "UN"
    await redis_conn.set(cache_key, json.dumps(result), ex=120)
    return result

@app.get("/v1/search/tiktok/video/{full_url:path}")
async def search_tiktok_video(full_url: str, request: Request, key: str = None, api_key: str = None):
    client_host = request.client.host
    header_key = request.headers.get("x-api-key")
    key_to_check = key or api_key or header_key
    if client_host not in ("127.0.0.1", "localhost"):
        if not key_to_check or not check_api_key(key_to_check):
            raise HTTPException(status_code=403, detail="Forbidden: invalid API key")
        redis_conn = app.state.redis
        limit_key_min = f"rate_min:{key_to_check}"
        limit_key_day = f"rate_day:{key_to_check}"
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT owner, ratelimit FROM api_keys WHERE key=?", (key_to_check,))
        row = c.fetchone()
        conn.close()
        owner, ratelimit = row if row else (None, "standard")
        if ratelimit == "standard" and owner != "cosmin":
            min_count = await redis_conn.get(limit_key_min)
            day_count = await redis_conn.get(limit_key_day)
            if min_count and int(min_count) >= 100:
                raise HTTPException(status_code=429, detail="Rate limit exceeded (per minute)")
            if day_count and int(day_count) >= 30000:
                raise HTTPException(status_code=429, detail="Rate limit exceeded (per day)")
            p = await redis_conn.pipeline()
            p.incr(limit_key_min, 1)
            p.expire(limit_key_min, 60)
            p.incr(limit_key_day, 1)
            p.expire(limit_key_day, 86400)
            await p.execute()
    redis_conn = app.state.redis
    cache_key = f"tiktok:video:{full_url}"
    cached = await redis_conn.get(cache_key)
    if cached:
        ttl = await redis_conn.ttl(cache_key)
        result = json.loads(cached)
        result["cache"] = {"cached": True, "ttl": ttl}
        return result
    video_id = extract_video_id_from_url(full_url)
    if not video_id:
        resolved_url = await resolve_short_url(full_url)
        video_id = extract_video_id_from_url(resolved_url)
        if not video_id:
            raise HTTPException(status_code=400, detail="Could not extract video ID from URL")
    download_data = await get_video_download_url(video_id)
    if "error" in download_data:
        raise HTTPException(status_code=500, detail=download_data["error"])
    final_url_to_use = full_url
    if "vm.tiktok.com" in full_url or "vt.tiktok.com" in full_url or "/t/" in full_url:
        final_url_to_use = await resolve_short_url(full_url)
    html_data = await get_video_details_from_html(final_url_to_use)
    if download_data.get("is_image_post"):
        result = {
            "id": str(video_id),
            "description": download_data.get("desc"),
            "createTime": None,
            "locationCreated": download_data.get("region"),
            "fullLocation": REGION_MAP.get(download_data.get("region"), "Unknown") if download_data.get("region") else None,
            "author": download_data.get("author", {"uniqueId": None, "nickname": None}),
            "music": download_data.get("music", {"id": None, "title": None, "authorName": None, "playUrl": None}),
            "music_info": download_data.get("music_info", {"author": None, "id": None, "id_str": None, "title": None}),
            "stats": download_data.get("stats", {"likeCount": None, "shareCount": None, "commentCount": None, "playCount": None, "collectCount": None}),
            "video": {
                "duration": None,
                "height": None,
                "width": None,
                "ratio": None,
                "coverUrl": None,
                "audio_url": download_data.get("audio_url"),
                "is_image_post": True,
                "image_urls": download_data.get("image_urls", [])
            },
            "cache": {"cached": False}
        }
    else:
        if "error" in html_data:
            result = {
                "id": download_data.get("id"),
                "description": download_data.get("desc"),
                "createTime": None,
                "locationCreated": None,
                "fullLocation": None,
                "author": {"uniqueId": None, "nickname": None},
                "music": {"id": None, "title": None, "authorName": None, "playUrl": None},
                "music_info": download_data.get("music_info", {"author": None, "id": None, "id_str": None, "title": None}),
                "stats": {"likeCount": None, "shareCount": None, "commentCount": None, "playCount": None, "collectCount": None},
                "video": {
                    "duration": None,
                    "height": None,
                    "width": None,
                    "ratio": None,
                    "coverUrl": None,
                    "audio_url": None,
                    "is_image_post": False,
                    "image_urls": []
                },
                "cache": {"cached": False}
            }
        else:
            result = {
                "id": html_data.get("id") or download_data.get("id"),
                "description": html_data.get("description") or download_data.get("desc"),
                "createTime": html_data.get("createTime"),
                "locationCreated": html_data.get("locationCreated"),
                "fullLocation": REGION_MAP.get(html_data.get("locationCreated"), "Unknown") if html_data.get("locationCreated") else None,
                "author": html_data.get("author", {}),
                "music": html_data.get("music", {}),
                "music_info": download_data.get("music_info", {"author": None, "id": None, "id_str": None, "title": None}),
                "stats": html_data.get("stats", {}),
                "video": {
                    **html_data.get("video", {}),
                    "audio_url": None,
                    "is_image_post": False,
                    "image_urls": []
                },
                "cache": {"cached": False}
            }
    await redis_conn.set(cache_key, json.dumps(result), ex=120)
    return result

@app.get("/v1/download/tiktok/video/{full_url:path}")
async def download_tiktok_video(full_url: str, request: Request, key: str = None, api_key: str = None):
    client_host = request.client.host
    header_key = request.headers.get("x-api-key")
    key_to_check = key or api_key or header_key
    if client_host not in ("127.0.0.1", "localhost"):
        if not key_to_check or not check_api_key(key_to_check):
            raise HTTPException(status_code=403, detail="Forbidden: invalid API key")
        redis_conn = app.state.redis
        limit_key_min = f"rate_min:{key_to_check}"
        limit_key_day = f"rate_day:{key_to_check}"
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT owner, ratelimit FROM api_keys WHERE key=?", (key_to_check,))
        row = c.fetchone()
        conn.close()
        owner, ratelimit = row if row else (None, "standard")
        if ratelimit == "standard" and owner != "cosmin":
            min_count = await redis_conn.get(limit_key_min)
            day_count = await redis_conn.get(limit_key_day)
            if min_count and int(min_count) >= 100:
                raise HTTPException(status_code=429, detail="Rate limit exceeded (per minute)")
            if day_count and int(day_count) >= 30000:
                raise HTTPException(status_code=429, detail="Rate limit exceeded (per day)")
            p = await redis_conn.pipeline()
            p.incr(limit_key_min, 1)
            p.expire(limit_key_min, 60)
            p.incr(limit_key_day, 1)
            p.expire(limit_key_day, 86400)
            await p.execute()
    redis_conn = app.state.redis
    cache_key = f"tiktok:download:{full_url}"
    cached = await redis_conn.get(cache_key)
    if cached:
        ttl = await redis_conn.ttl(cache_key)
        result = json.loads(cached)
        result["cache"] = {"cached": True, "ttl": ttl}
        return result
    video_id = extract_video_id_from_url(full_url)
    if not video_id:
        resolved_url = await resolve_short_url(full_url)
        video_id = extract_video_id_from_url(resolved_url)
        if not video_id:
            raise HTTPException(status_code=400, detail="Could not extract video ID from URL")
    download_data = await get_video_download_url(video_id)
    if "error" in download_data:
        raise HTTPException(status_code=500, detail=download_data["error"])
    if download_data.get("is_image_post"):
        raise HTTPException(status_code=400, detail="This endpoint is for videos only, not image posts")
    tikwm_download_url = await get_tikwm_download_url(full_url)
    result = {
        "success": True,
        "data": {
            "id": download_data.get("id"),
            "download_url": tikwm_download_url or download_data.get("video_url"),
            "cache": {"cached": False}
        }
    }
    await redis_conn.set(cache_key, json.dumps(result), ex=120)
    return result

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8073, log_level="info")
