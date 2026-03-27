import io
import aiohttp
import asyncio
import discord
import time

class AudioPreviewHandler:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.search_timeout = aiohttp.ClientTimeout(total=5)
        self.download_timeout = aiohttp.ClientTimeout(total=20)
        self.cache = {}  # {preview_url: (audio_bytes, expires_at)}

    async def get_preview(self, track_data=None, track_name=None, artist_name=None):
        if track_data:
            preview_url = track_data.get("spotifyPreview") or track_data.get("appleMusicPreview")
            if preview_url:
                return preview_url
        if track_name and artist_name:
            headers = {"User-Agent": "Heist Bot/3.0"}
            try:
                async with self.session.get(
                    f"https://api.stats.fm/api/v1/search/elastic?query={track_name}&type=track&limit=10",
                    headers=headers,
                    timeout=self.search_timeout
                ) as response:
                    if response.status != 200:
                        return None
                    data = await response.json()
                    tracks = data.get("items", {}).get("tracks", [])
                    for track in tracks:
                        artists = [a['name'].lower() for a in track.get('artists', [])]
                        if artist_name.lower() in artists:
                            preview_url = track.get("spotifyPreview") or track.get("appleMusicPreview")
                            return preview_url
                    return None
            except Exception:
                return None
        return None

    async def send_preview(self, interaction, preview_url, filename="preview.mp3"):
        now = time.time()
        cached = self.cache.get(preview_url)
        if cached and cached[1] > now:
            audio_data = cached[0]
        else:
            try:
                async with self.session.get(preview_url, timeout=self.download_timeout) as resp:
                    if resp.status != 200:
                        return False
                    audio_data = await resp.read()
                    self.cache[preview_url] = (audio_data, now + 60)
            except Exception:
                return False

        mp3_io = io.BytesIO(audio_data)
        mp3_io.seek(0)
        audio_file = discord.File(mp3_io, filename=filename)
        await interaction.followup.send(file=audio_file, ephemeral=False)
        return True
