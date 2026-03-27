import aiohttp
import asyncpg
import base64
import os
import time
import asyncio
import logging
from aiofiles import open as aio_open
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from urllib.parse import urlparse
from datetime import datetime, timedelta
from dotenv import load_dotenv
import ssl

load_dotenv("/root/heist-v3/heist/.env")

app = FastAPI(docs_url=None)

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_SECRET") or os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT")
PG_DSN = os.getenv("PG_DSN") or os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

connector = None
session = None
pool = None
redis = None

class ExpiringCache:
    def __init__(self, ttl: int):
        self.ttl = ttl
        self._cache = {}

    def get(self, key):
        e = self._cache.get(key)
        if not e:
            return None
        if time.time() - e["time"] < self.ttl:
            return e["value"]
        self._cache.pop(key, None)
        return None

    def set(self, key, value):
        self._cache[key] = {"value": value, "time": time.time()}

    def delete(self, key):
        self._cache.pop(key, None)

app.cache = ExpiringCache(ttl=3600)
app.locks = {}

class SpotifySong(BaseModel):
    artist: str
    title: str
    image: str
    download_url: str

token_info = {"access_token": None, "expiration_time": 0}

@app.on_event("startup")
async def on_startup():
    global connector, session, pool, redis
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    session = aiohttp.ClientSession(connector=connector)
    if PG_DSN:
        pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=5)
    if REDIS_URL:
        try:
            import redis.asyncio as aioredis
            redis = aioredis.from_url(REDIS_URL, decode_responses=True)
            await redis.ping()
        except Exception:
            redis = None

@app.on_event("shutdown")
async def on_shutdown():
    global session, connector, pool, redis
    if session and not session.closed:
        await session.close()
    if connector:
        await connector.close()
    if pool:
        await pool.close()
    if redis:
        await redis.close()

async def delete_file_after_delay(file_path: str, delay_seconds: int):
    await asyncio.sleep(delay_seconds)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"Deleted file: {file_path}")
    except Exception as e:
        logging.error(f"Error deleting file {file_path}: {e}")

async def get_spotify_access_token() -> dict:
    global token_info
    if token_info["access_token"] and time.time() < token_info["expiration_time"] - 10:
        return token_info
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Spotify client not configured")
    auth_str = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    b64_auth_str = base64.b64encode(auth_str.encode()).decode()
    headers = {
        "Authorization": f"Basic {b64_auth_str}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials"}
    async with session.post("https://accounts.spotify.com/api/token", headers=headers, data=data) as response:
        rd = await response.json()
        if response.status != 200 or "access_token" not in rd:
            raise HTTPException(status_code=500, detail="Failed to obtain Spotify access token")
        token_info = {
            "access_token": rd["access_token"],
            "expiration_time": time.time() + int(rd.get("expires_in", 3600))
        }
        return token_info

async def search_spotify_track(access_token: str, track_name: str = None, artist_name: str = None, album_name: str = None, limit: int = 10, fuzzy: bool = False):
    headers = {"Authorization": f"Bearer {access_token}"}
    q_parts = []
    if fuzzy:
        if track_name:
            q_parts.append(f"track:{track_name}")
        if artist_name:
            q_parts.append(f"artist:{artist_name}")
        if album_name:
            q_parts.append(f"album:{album_name}")
    else:
        if track_name:
            q_parts.append(f'track:"{track_name}"')
        if artist_name:
            q_parts.append(f'artist:"{artist_name}"')
        if album_name:
            q_parts.append(f'album:"{album_name}"')
    q = " ".join(q_parts) if q_parts else ""
    params = {"q": q, "type": "track", "limit": str(limit)}
    async with session.get("https://api.spotify.com/v1/search", params=params, headers=headers) as response:
        if response.status != 200:
            return []
        data = await response.json()
        return data.get("tracks", {}).get("items", []) or []

async def search_spotify_album(access_token: str, album_name: str = None, artist_name: str = None, limit: int = 10):
    headers = {"Authorization": f"Bearer {access_token}"}
    q_parts = []
    if album_name:
        q_parts.append(f'album:"{album_name}"')
    if artist_name:
        q_parts.append(f'artist:"{artist_name}"')
    q = " ".join(q_parts) if q_parts else ""
    params = {"q": q, "type": "album", "limit": str(limit)}
    async with session.get("https://api.spotify.com/v1/search", params=params, headers=headers) as response:
        if response.status != 200:
            return []
        data = await response.json()
        return data.get("albums", {}).get("items", []) or []

def format_track_result(track: dict, request: Request) -> dict:
    images = (track.get("album") or {}).get("images") or []
    return {
        "type": "track",
        "id": track.get("id"),
        "title": track.get("name"),
        "artist": ", ".join(a.get("name") for a in track.get("artists", []) if a.get("name")),
        "album": (track.get("album") or {}).get("name"),
        "cover_art": images[0]["url"] if images else None,
        "preview_url": track.get("preview_url"),
        "spotify_url": (track.get("external_urls") or {}).get("spotify"),
        "download_url": str(request.url_for("spotify_downloads", id=track["id"])) if track.get("preview_url") else None,
        "duration_ms": track.get("duration_ms")
    }

def format_album_result(album: dict, request: Request) -> dict:
    images = album.get("images") or []
    return {
        "type": "album",
        "id": album.get("id"),
        "title": album.get("name"),
        "artist": ", ".join(a.get("name") for a in album.get("artists", []) if a.get("name")),
        "cover_art": images[0]["url"] if images else None,
        "spotify_url": (album.get("external_urls") or {}).get("spotify"),
        "download_url": str(request.url_for("spotify_album_cover", id=album["id"])) if album.get("id") else None
    }

def create_output_dictionary_album(lastfm_album, spotify_albums):
    images = spotify_albums[0].get("images") if spotify_albums else []
    return {
        "title": lastfm_album.get("name"),
        "artist": (lastfm_album.get("artist") or {}).get("#text"),
        "spotify_link": (spotify_albums[0].get("external_urls") or {}).get("spotify") if spotify_albums else None,
        "cover_art": images[0]["url"] if images else None
    }

def create_output_dictionary_track(lastfm_track, spotify_tracks):
    album = (spotify_tracks[0].get("album") or {}) if spotify_tracks else {}
    images = album.get("images") or []
    return {
        "title": lastfm_track.get("name"),
        "artist": (lastfm_track.get("artist") or {}).get("#text"),
        "spotify_link": (spotify_tracks[0].get("external_urls") or {}).get("spotify") if spotify_tracks else None,
        "cover_art": images[0]["url"] if images else None,
        "preview_url": spotify_tracks[0].get("preview_url") if spotify_tracks else None
    }

async def download_preview(preview_url: str, track_id: str):
    os.makedirs("./temp", exist_ok=True)
    download_path = os.path.join("./temp", f"{track_id}_p.mp3")
    async with session.get(preview_url) as response:
        if response.status == 200:
            b = await response.read()
            async with aio_open(download_path, "wb") as f:
                await f.write(b)
            return download_path
    return None

@app.get("/api/freesearch")
async def free_search(
    request: Request,
    background_tasks: BackgroundTasks,
    artist_name: str = None,
    track_name: str = None,
    album_name: str = None,
    search_type: str = "track",
    fuzzy: bool = False
):
    if not any([artist_name, track_name, album_name]):
        raise HTTPException(status_code=400, detail="At least one search parameter is required")
    ti = await get_spotify_access_token()
    access_token = ti["access_token"]
    if search_type == "track":
        items = await search_spotify_track(access_token, track_name=track_name, artist_name=artist_name, album_name=album_name, fuzzy=fuzzy)
        results = [format_track_result(t, request) for t in items]
        return JSONResponse(content={"results": results})
    if search_type == "album":
        items = await search_spotify_album(access_token, album_name=album_name, artist_name=artist_name)
        results = [format_album_result(a, request) for a in items]
        return JSONResponse(content={"results": results})
    raise HTTPException(status_code=400, detail="Invalid search_type. Must be 'track' or 'album'")

@app.get("/api/spotify/artist")
async def get_spotify_artist_cover(artist_name: str, request: Request) -> JSONResponse:
    ti = await get_spotify_access_token()
    headers = {"Authorization": f'Bearer {ti["access_token"]}'}
    params = {"q": f'artist:"{artist_name}"', "type": "artist", "limit": "1"}
    async with session.get("https://api.spotify.com/v1/search", params=params, headers=headers) as response:
        if response.status != 200:
            return JSONResponse(content={"error": "Failed to fetch artist data from Spotify"}, status_code=500)
        data = await response.json()
        artists = data.get("artists", {}).get("items", []) or []
        if not artists:
            return JSONResponse(content={"error": "No artists found"}, status_code=404)
        a = artists[0]
        images = a.get("images") or []
        cover_art = images[0]["url"] if images else None
        return JSONResponse(content={"cover_art": cover_art})

@app.get("/api/search")
async def search(lastfm_username: str, artist_name: str, background_tasks: BackgroundTasks, request: Request, album_name: str = None, track_name: str = None):
    ti = await get_spotify_access_token()
    access_token = ti["access_token"]
    if album_name and not track_name:
        spotify_albums = await search_spotify_album(access_token, album_name=album_name, artist_name=artist_name)
        output_dict = create_output_dictionary_album({"name": album_name, "artist": {"#text": artist_name}}, spotify_albums)
    else:
        spotify_tracks = await search_spotify_track(access_token, track_name=track_name, artist_name=artist_name)
        output_dict = create_output_dictionary_track({"name": track_name, "artist": {"#text": artist_name}}, spotify_tracks)
    if output_dict.get("spotify_link"):
        if album_name and not track_name:
            album_id = output_dict["spotify_link"].split("/")[-1].split("?")[0]
            output_dict["download_url"] = str(request.url_for("spotify_album_cover", id=album_id))
        else:
            track_id = output_dict["spotify_link"].split("/")[-1].split("?")[0]
            preview_url = output_dict.get("preview_url")
            if preview_url:
                preview_path = await download_preview(preview_url, track_id)
                if preview_path:
                    background_tasks.add_task(delete_file_after_delay, preview_path, 15)
            output_dict["download_url"] = str(request.url_for("spotify_downloads", id=track_id))
        return JSONResponse(content=output_dict)
    return JSONResponse(content={"error": "No Spotify content found"}, status_code=404)

@app.get("/spotify/album_cover/{id}")
async def spotify_album_cover(id: str, request: Request):
    ti = await get_spotify_access_token()
    headers = {"Authorization": f'Bearer {ti["access_token"]}'}
    async with session.get(f"https://api.spotify.com/v1/albums/{id}", headers=headers) as response:
        if response.status != 200:
            return JSONResponse(content={"error": "Failed to fetch album data from Spotify"}, status_code=500)
        data = await response.json()
        images = data.get("images") or []
        if images:
            return JSONResponse(content={"cover_art": images[0]["url"]})
        return JSONResponse(content={"error": "No album cover found"}, status_code=404)

@app.get("/spotify/downloads/{id}")
async def spotify_downloads(id: str, request: Request, background_tasks: BackgroundTasks):
    os.makedirs("./temp", exist_ok=True)
    path = os.path.join("./temp", f"{id}.mp3")
    if os.path.exists(path):
        return FileResponse(path, media_type="audio/mpeg")
    cache = app.cache.get(f"spotify-{id}")
    if cache:
        url = cache.get("url")
        if url:
            async with session.get(url) as r:
                if r.status != 200:
                    return JSONResponse(content="Content Not Available", status_code=404)
                download_byte = await r.read()
            async with aio_open(path, "wb") as f:
                await f.write(download_byte)
            background_tasks.add_task(delete_file_after_delay, path, 15)
            return FileResponse(path, media_type="audio/mpeg")
    return JSONResponse(content="Content Not Available", status_code=404)

@app.get("/spotify/song", response_model=SpotifySong)
async def spotify_song(request: Request, url: str, background_tasks: BackgroundTasks) -> JSONResponse:
    parsed_url = urlparse(url)
    parts = parsed_url.path.split("/")
    if len(parts) > 2 and parts[-2] == "track":
        track_id = parts[-1]
    else:
        raise HTTPException(status_code=400, detail="Invalid Spotify URL.")
    clean_url = f"https://open.spotify.com/track/{track_id}"
    lock = app.locks.setdefault(request.client.host, asyncio.Lock())
    async with lock:
        cached = app.cache.get(f"spotify-{clean_url}")
        if cached:
            return JSONResponse(content=cached)
        ti = await get_spotify_access_token()
        headers = {
            "Authorization": f'Bearer {ti["access_token"]}',
            "User-Agent": "Heist Bot/3.0",
            "Content-Type": "application/json"
        }
        async with session.get(f"https://api.spotify.com/v1/tracks/{track_id}", headers=headers) as r:
            track_info = await r.json()
            if r.status != 200 or "artists" not in track_info:
                raise HTTPException(status_code=500, detail="Invalid response from Spotify API.")
            artist = (track_info["artists"][0] or {}).get("name") or "Unknown"
            title = track_info.get("name") or "Unknown"
            images = ((track_info.get("album") or {}).get("images") or [])
            image = images[0]["url"] if images else None
            payload = {
                "artist": artist,
                "title": title,
                "image": image,
                "download_url": str(request.url_for("spotify_downloads", id=track_id)),
            }
            if track_info.get("preview_url"):
                app.cache.set(f"spotify-{track_id}", {"url": track_info["preview_url"]})
            app.cache.set(f"spotify-{clean_url}", payload)
            background_tasks.add_task(delete_file_after_delay, os.path.join("./temp", f"{track_id}.mp3"), 15)
            return JSONResponse(content=payload)

@app.get("/spotify/callback")
async def spotify_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")
    if error:
        raise HTTPException(status_code=400, detail=f"Spotify authorization failed: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")
    if not pool:
        raise HTTPException(status_code=500, detail="Database not configured")
    async with pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT user_id FROM spotify_auth_states WHERE state = $1", state)
        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid state parameter")
        await conn.execute("DELETE FROM spotify_auth_states WHERE state = $1", state)
    auth_header = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {auth_header}"
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI
    }
    async with session.post("https://accounts.spotify.com/api/token", headers=headers, data=data) as response:
        jd = await response.json()
        if response.status != 200:
            raise HTTPException(status_code=400, detail=f"Spotify error: {jd.get('error_description', 'Unknown error')}")
        access_token = jd["access_token"]
        refresh_token = jd.get("refresh_token")
        expires_at = datetime.now() + timedelta(seconds=int(jd.get("expires_in", 3600)))
    async with session.get("https://api.spotify.com/v1/me", headers={"Authorization": f"Bearer {access_token}"}) as user_response:
        user_data = await user_response.json()
        if user_response.status != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch user data")
        if user_data.get("product") != "premium":
            raise HTTPException(status_code=400, detail="Spotify Premium required")
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO spotify_auth (user_id, access_token, refresh_token, expires_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE
            SET access_token = $2, refresh_token = $3, expires_at = $4
            """,
            user_id, access_token, refresh_token, expires_at
        )
    return RedirectResponse(url="https://discord.com/channels/@me")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=2053)
