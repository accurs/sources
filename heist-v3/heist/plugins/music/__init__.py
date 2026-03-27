import discord, aiohttp, asyncpg, hashlib, os, json
from discord.ext import commands
from discord import ui, app_commands, ButtonStyle
from discord.ui import View, Select
from dotenv import load_dotenv
import secrets
from heist.framework.pagination import Paginator
from heist.framework.discord import CommandCache
from heist.framework.tools.audiopreviews import AudioPreviewHandler
from heist.framework.discord import cv2 as cpv2
from typing import Optional, Union
import asyncio
import urllib.parse
import io
from PIL import Image
import time
import math

load_dotenv()
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_API_SECRET = os.getenv("LASTFM_API_SECRET")
CALLBACK_URL = "https://api.cursi.ng/lastfm"

VALID_PERIODS = [
    app_commands.Choice(name="7 days", value="7day"),
    app_commands.Choice(name="1 month", value="1month"),
    app_commands.Choice(name="3 months", value="3month"),
    app_commands.Choice(name="6 months", value="6month"),
    app_commands.Choice(name="1 year", value="12month"),
    app_commands.Choice(name="lifetime", value="overall")
]
COLLAGE_PERIODS = {
    "7day": "7days",
    "1month": "1month",
    "3month": "3months",
    "6month": "6months",
    "12month": "12months",
    "overall": "overall"
}
PERIOD_DISPLAY = {
    "7day": "last 7 days",
    "1month": "last month",
    "3month": "last 3 months",
    "6month": "last 6 months",
    "12month": "last year",
    "overall": "lifetime"
}
PERIOD_MAP = {
    "lifetime": None,
    "7day": "7day",
    "1month": "1month",
    "3month": "3month",
    "6month": "6month",
    "12month": "12month"
}
periods_in_seconds = {
    "7day": 7 * 24 * 3600,
    "1month": 30 * 24 * 3600,
    "3month": 90 * 24 * 3600,
    "6month": 180 * 24 * 3600,
    "12month": 365 * 24 * 3600,
}

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.LASTFM_KEY = os.getenv("LASTFM_API_KEY")
        self.track_cache = {}
        self.cache_ttl = 120

    async def get_lastfm_user(self, user_id: int):
        async with self.bot.pool.acquire() as conn:
            data = await conn.fetchrow(
                "SELECT lastfm_username, hidden FROM lastfm_users WHERE discord_id = $1",
                user_id
            )
            if not data or not data["lastfm_username"]:
                return None
            return data["lastfm_username"], data["hidden"]

    async def get_dominant_color(self, image_bytes: bytes):
        def process():
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            image = image.resize((64, 64))
            pixels = list(image.getdata())
            r = sum(p[0] for p in pixels) // len(pixels)
            g = sum(p[1] for p in pixels) // len(pixels)
            b = sum(p[2] for p in pixels) // len(pixels)
            return (r << 16) + (g << 8) + b

        return await asyncio.to_thread(process)

    @commands.hybrid_group(name="lastfm", description="Last.fm integration commands", aliases=["lf"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def lastfm_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @lastfm_group.command(name="login", description="Link your Last.fm account")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def lastfm_login(self, ctx: commands.Context):
        state = secrets.token_urlsafe(16)
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO lastfm_auth_state (state, discord_id) VALUES ($1, $2) "
                "ON CONFLICT (state) DO UPDATE SET discord_id = $2, created_at = NOW();",
                state, ctx.author.id
            )

        login_url = f"https://www.last.fm/api/auth/?api_key={LASTFM_API_KEY}&cb={CALLBACK_URL}?state={state}"

        embed = discord.Embed(
            title="Connect your Last.fm to Heist",
            description="Click the button below to get your secure login link.",
            color=await self.bot.get_color(ctx.author.id)
        )
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar)
        embed.set_thumbnail(url="https://git.cursi.ng/heist.png")

        class LoginButtonView(View):
            def __init__(self, bot, author_id: int):
                super().__init__(timeout=300)
                self.bot = bot
                self.author_id = author_id
                self.add_item(LoginButton(bot))

            async def on_timeout(self):
                for child in self.children:
                    child.disabled = True
                try:
                    await message.edit(view=self)
                except Exception:
                    pass

        class LoginButton(discord.ui.Button):
            def __init__(self, bot):
                super().__init__(label="Connect Last.fm", emoji="<:lastfmv2:1426636679174815966>", style=discord.ButtonStyle.primary)
                self.bot = bot

            async def callback(self, interaction: discord.Interaction):
                if interaction.user.id != self.view.author_id:
                    await interaction.response.warn(
                        f"Only <@{self.view.author_id}> can use this.", ephemeral=True
                    )
                    return
                embed = discord.Embed(
                    description=f"-# [**Click here to link**]({login_url})",
                    color=await self.bot.get_color(interaction.user.id)
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

        view = LoginButtonView(self.bot, ctx.author.id)
        message = await ctx.send(embed=embed, view=view)

    async def complete_login(self, discord_id: int, token: str):
        sig_raw = f"api_key{LASTFM_API_KEY}methodauth.getSessiontoken{token}{LASTFM_API_SECRET}"
        api_sig = hashlib.md5(sig_raw.encode()).hexdigest()
        params = {
            "method": "auth.getSession",
            "api_key": LASTFM_API_KEY,
            "token": token,
            "api_sig": api_sig,
            "format": "json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get("https://ws.audioscrobbler.com/2.0/", params=params) as resp:
                data = await resp.json()

        if "session" not in data:
            return None

        username = data["session"]["name"]
        session_key = data["session"]["key"]

        async with self.bot.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO lastfm_users (discord_id, lastfm_username, session_key)
                VALUES ($1, $2, $3)
                ON CONFLICT (discord_id)
                DO UPDATE SET lastfm_username = $2, session_key = $3;
            """, discord_id, username, session_key)
        return username
        
    async def get_lastfm_v2(self, user_id: int):
        row = await self.bot.pool.fetchrow("SELECT lastfm_nowplaying_v2 FROM design_settings WHERE user_id=$1", user_id)
        if not row:
            return False
        return bool(row["lastfm_nowplaying_v2"])

    @lastfm_group.command(name="nowplaying", description="Get your current playing track on Last.fm", aliases=["np", "playing", "fm"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def lastfm_nowplaying(self, ctx: commands.Context, username: Optional[str] = None):

        async with ctx.typing():
            if username is None:
                user_row = await self.get_lastfm_user(ctx.author.id)
                if not user_row:
                    lastfmlogin = await CommandCache.get_mention(self.bot, "lastfm login")
                    return await ctx.warn(f"You haven't linked your Last.fm account yet. Use {lastfmlogin}.")
                lastfm_username, hidden = user_row
            else:
                lastfm_username = username
                hidden = False

            user_info_url = f"https://ws.audioscrobbler.com/2.0/?method=user.getinfo&user={lastfm_username}&api_key={self.LASTFM_KEY}&format=json"
            recent_tracks_url = f"https://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={lastfm_username}&api_key={self.LASTFM_KEY}&format=json&limit=1"

            user_response, tracks_response = await asyncio.gather(
                self.session.get(user_info_url),
                self.session.get(recent_tracks_url)
            )

            if user_response.status != 200 or tracks_response.status != 200:
                return await ctx.warn("Failed to fetch data from Last.fm.")

            user_data = await user_response.json()
            tracks_data = await tracks_response.json()

            if "error" in user_data or "error" in tracks_data:
                return await ctx.warn(f"Last.fm error: {user_data.get('message', tracks_data.get('message', 'Unknown error'))}")

            if "recenttracks" not in tracks_data or not tracks_data["recenttracks"].get("track"):
                return await ctx.warn(f"No recent tracks found for user `{lastfm_username}`.")

            track = tracks_data["recenttracks"]["track"][0]
            artist_name = track["artist"]["#text"]
            track_name = track["name"]
            album_name = track.get("album", {}).get("#text", "")
            artistenc = urllib.parse.quote(artist_name)
            trackenc = urllib.parse.quote(track_name)
            albumenc = urllib.parse.quote(album_name) if album_name else ""
            now_playing = "@attr" in track and track["@attr"].get("nowplaying") == "true"

            track_info_url = f"https://ws.audioscrobbler.com/2.0/?method=track.getInfo&api_key={self.LASTFM_KEY}&artist={artistenc}&track={trackenc}&username={lastfm_username}&format=json"
            album_info_url = f"https://ws.audioscrobbler.com/2.0/?method=album.getInfo&api_key={self.LASTFM_KEY}&artist={artistenc}&album={albumenc}&username={lastfm_username}&format=json" if album_name else None
            artist_info_url = f"https://ws.audioscrobbler.com/2.0/?method=artist.getInfo&api_key={self.LASTFM_KEY}&artist={artistenc}&username={lastfm_username}&format=json"

            track_info_response, album_info_response, artist_info_response = await asyncio.gather(
                self.session.get(track_info_url),
                self.session.get(album_info_url) if album_info_url else asyncio.sleep(0),
                self.session.get(artist_info_url)
            )

            track_scrobbles = 0
            album_scrobbles = 0
            artist_scrobbles = 0
            total_scrobbles = int(user_data["user"].get("playcount", 0)) if "user" in user_data else 0

            if isinstance(track_info_response, aiohttp.ClientResponse) and track_info_response.status == 200:
                track_data = await track_info_response.json()
                if "track" in track_data and "userplaycount" in track_data["track"]:
                    track_scrobbles = int(track_data["track"]["userplaycount"])

            if album_info_url and isinstance(album_info_response, aiohttp.ClientResponse) and album_info_response.status == 200:
                album_data = await album_info_response.json()
                if "album" in album_data and "userplaycount" in album_data["album"]:
                    album_scrobbles = int(album_data["album"]["userplaycount"])

            if isinstance(artist_info_response, aiohttp.ClientResponse) and artist_info_response.status == 200:
                artist_data = await artist_info_response.json()
                if "artist" in artist_data and "stats" in artist_data["artist"]:
                    artist_scrobbles = int(artist_data["artist"]["stats"].get("userplaycount", 0))

            cover_art_url = track.get("image", [])[-1].get("#text") if track.get("image") else None
            artist_url = f"https://www.last.fm/music/{artistenc}"
            album_url = f"https://www.last.fm/music/{artistenc}/{albumenc}" if album_name else None
            track_url = track.get("url", f"https://www.last.fm/music/{artistenc}/_/{trackenc}")

            spotify_track_url = None
            try:
                spotify_url = f"http://127.0.0.1:2053/api/search?lastfm_username={lastfm_username}&track_name={trackenc}&artist_name={artistenc}"
                spotify_response = await self.session.get(spotify_url)
                if spotify_response.status == 200:
                    spotify_data = await spotify_response.json()
                    spotify_track_url = spotify_data.get("spotify_link")
            except:
                pass

            preview_handler = AudioPreviewHandler(self.session)
            preview_url = await preview_handler.get_preview(track_name=track_name, artist_name=artist_name)

            use_v2 = await self.get_lastfm_v2(ctx.author.id)

            if use_v2:
                if not now_playing and "date" in track:
                    timestamp = int(track["date"]["uts"])
                    timestamp_txt = f"-# <t:{timestamp}:R>"
                else:
                    timestamp_txt = None

                color = await self.bot.get_color(ctx.author.id)
                if cover_art_url:
                    try:
                        cover_resp = await self.session.get(cover_art_url)
                        if cover_resp.status == 200:
                            image_data = await cover_resp.read()
                            color = await self.get_dominant_color(image_data)
                    except:
                        pass

                display_username = ctx.author.display_name if hidden else lastfm_username
                if hidden:
                    author_text = f"Now playing for **{display_username}**" if now_playing else f"Last track for **{display_username}**"
                else:
                    author_text = f"Now playing for [**{display_username}**](https://last.fm/user/{lastfm_username})" if now_playing else f"Last track for [**{display_username}**](https://lastfm/user/{lastfm_username})"
                if timestamp_txt:
                    author_text += f"\n{timestamp_txt}"

                line1 = f"[{artist_name}]({artist_url})"
                if album_name:
                    line1 += f" • [*{album_name}*]({album_url})"

                stats_lines = [
                    f"-# **{track_scrobbles}** track scrobbles",
                    f"-# **{album_scrobbles}** album scrobbles" if album_name else None,
                    f"-# **{artist_scrobbles}** artist scrobbles",
                    f"-# **{total_scrobbles}** total scrobbles"
                ]
                stats_txt = "\n".join([x for x in stats_lines if x])

                title_txt = f"### [{track_name}]({track_url})\n-# {author_text}"
                body_txt = f"{line1}\n{stats_txt}"

                if cover_art_url:
                    section = ui.Section(ui.TextDisplay(body_txt), accessory=ui.Thumbnail(cover_art_url))
                else:
                    section = ui.TextDisplay(body_txt)

                blocks = [
                    ui.TextDisplay(title_txt),
                    ui.Separator(),
                    section,
                    ui.Separator(),
                    ui.TextDisplay(f"-# [Open on <:lastfm:1275185763574874134>]({track_url})")
                ]

                btn_audio = discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    emoji=discord.PartialEmoji.from_str("<:audio:1345517095101923439>"),
                    custom_id="nowplayingaudio",
                    disabled=not bool(preview_url)
                )

                if spotify_track_url:
                    btn_spotify = discord.ui.Button(
                        style=discord.ButtonStyle.link,
                        url=spotify_track_url,
                        emoji=discord.PartialEmoji.from_str("<:spotify:1274904265114124308>")
                    )
                else:
                    btn_spotify = discord.ui.Button(
                        style=discord.ButtonStyle.link,
                        url="https://spotify.com",
                        emoji=discord.PartialEmoji.from_str("<:spotify:1274904265114124308>"),
                        disabled=True
                    )

                lock_key = None
                msg = None

                async def audio_preview_callback(interaction: discord.Interaction):
                    await interaction.response.defer(ephemeral=False)
                    if not preview_url or not lock_key:
                        return

                    acquired = await self.bot.redis.set(lock_key, "1", ex=10, nx=True)
                    if not acquired:
                        return

                    try:
                        await preview_handler.send_preview(interaction, preview_url, filename=f"{track_name}.mp3")
                    finally:
                        await self.bot.redis.delete(lock_key)
                        try:
                            real_audio_btn = view.bar.children[1]
                            real_audio_btn.disabled = True
                            await interaction.edit_original_response(view=view)
                        except:
                            pass

                btn_audio.callback = audio_preview_callback

                attrs = {}
                for idx, el in enumerate(blocks):
                    attrs[f"attr_{idx}"] = el
                Container = type("DynamicContainer", (ui.Container,), attrs)
                container = Container(accent_color=discord.Color(color))

                class NowPlayingView(ui.LayoutView):
                    timeout = 120
                    main = container
                    bar = ui.ActionRow(btn_spotify, btn_audio)
                    async def on_timeout(self):
                        real_btn = self.bar.children[1]
                        real_btn.disabled = True
                        try:
                            await msg.edit(view=self)
                        except:
                            pass

                view = NowPlayingView()
                msg = await ctx.send(view=view)
                lock_key = f"nowplaying:preview:{ctx.author.id}:{msg.id}"

            else:
                if "date" in track:
                    timestamp = int(track["date"]["uts"])
                    timestamp_str = f"<t:{timestamp}:R>"
                else:
                    timestamp_str = None

                color = await self.bot.get_color(ctx.author.id)
                if cover_art_url:
                    try:
                        cover_resp = await self.session.get(cover_art_url)
                        if cover_resp.status == 200:
                            image_data = await cover_resp.read()
                            color = await self.get_dominant_color(image_data)
                    except:
                        pass

                embed = discord.Embed(title=track_name, url=track_url, color=color)
                display_username = ctx.author.display_name if hidden else lastfm_username
                author_text = f"Now playing for {display_username}" if now_playing else f"Last track for {display_username}"
                author_url = None if hidden else f"https://last.fm/user/{lastfm_username}"
                embed.set_author(name=author_text, icon_url=ctx.author.display_avatar.url, url=author_url)
                
                now_playing_description = ""
                if timestamp_str:
                    now_playing_description += f"{timestamp_str}\n"
                now_playing_description += f"[{artist_name}]({artist_url})"
                if album_name:
                    now_playing_description += f" • [*{album_name}*]({album_url})"
                embed.description = now_playing_description
                
                scrobble_info = f"{track_scrobbles} track scrobbles"
                if album_name:
                    scrobble_info += f" · {album_scrobbles} album scrobbles\n"
                scrobble_info += f"{artist_scrobbles} artist scrobbles · {total_scrobbles} total scrobbles"
                if cover_art_url:
                    embed.set_thumbnail(url=cover_art_url)
                embed.set_footer(text=scrobble_info, icon_url="https://git.cursi.ng/lastfm_logo.png")

                pages = [embed]
                paginator = Paginator(ctx, pages, hide_nav=True, hide_footer=True)
                if spotify_track_url:
                    paginator.add_link_button(
                        url=spotify_track_url,
                        emoji=discord.PartialEmoji.from_str("<:spotify:1274904265114124308>"),
                        persist=True
                    )
                else:
                    paginator.add_link_button(
                        url="https://spotify.com",
                        emoji=discord.PartialEmoji.from_str("<:spotify:1274904265114124308>"),
                        persist=True,
                        disabled=True
                    )

                lock_var = {"value": None}

                async def audio_preview_callback(interaction, view):
                    await interaction.response.defer(ephemeral=False)

                    if lock_var["value"] is None:
                        return

                    acquired = await self.bot.redis.set(lock_var["value"], "1", ex=10, nx=True)
                    if not acquired:
                        return

                    try:
                        if preview_url:
                            await preview_handler.send_preview(
                                interaction,
                                preview_url,
                                filename=f"{track_name}.mp3"
                            )
                        else:
                            await interaction.followup.warn("No audio preview available.", ephemeral=True)
                    finally:
                        await self.bot.redis.delete(lock_var["value"])
                        for item in view.children:
                            if getattr(item, "custom_id", None) == "nowplayingaudio":
                                item.disabled = True
                        try:
                            await interaction.edit_original_response(view=view)
                        except:
                            pass

                paginator.add_custom_button(
                    callback=audio_preview_callback,
                    emoji=discord.PartialEmoji.from_str("<:audio:1345517095101923439>"),
                    style=discord.ButtonStyle.secondary,
                    disabled=not bool(preview_url),
                    custom_id="nowplayingaudio"
                )

                msg = await paginator.start()

                lock_var["value"] = f"nowplaying:preview:{ctx.author.id}:{msg.id}"

    @lastfm_group.command(name="spotify", description="Find your current playing Last.fm song on Spotify", aliases=["sptf"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def lastfm_spotify(self, ctx: commands.Context, username: Optional[str] = None):
        async with ctx.typing():
            async with self.bot.pool.acquire() as conn:
                if username is None:
                    row = await conn.fetchrow("SELECT lastfm_username FROM lastfm_users WHERE discord_id = $1", ctx.author.id)
                    if not row:
                        lastfmlogin = await CommandCache.get_mention(self.bot, "lastfm login")
                        return await ctx.warn(f"You haven’t linked your Last.fm account yet. Use {lastfmlogin}.")
                    lastfm_username = row["lastfm_username"]
                else:
                    lastfm_username = username

            url = f"https://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={lastfm_username}&api_key={self.LASTFM_KEY}&format=json&limit=1"
            async with self.session.get(url) as r:
                if r.status != 200:
                    return await ctx.warn("Failed to fetch data from Last.fm.")
                data = await r.json()

            if "error" in data:
                return await ctx.warn(data.get("message", "Unknown Last.fm error."))
            tracks = data.get("recenttracks", {}).get("track", [])
            if not tracks:
                return await ctx.warn(f"No recent tracks found for `{lastfm_username}`.")

            track = tracks[0]
            artist_name = track["artist"]["#text"]
            track_name = track["name"]
            spotify_url = f"http://127.0.0.1:2053/api/search?lastfm_username={lastfm_username}&track_name={urllib.parse.quote(track_name)}&artist_name={urllib.parse.quote(artist_name)}"
            async with self.session.get(spotify_url) as s:
                if s.status != 200:
                    return await ctx.warn("Could not reach Spotify API.")
                spotify_data = await s.json()
            link = spotify_data.get("spotify_link")
            if not link:
                return await ctx.warn(f"Couldn't find `{track_name}` by `{artist_name}` on Spotify.")
            embed = discord.Embed(
                title="Stream on Spotify",
                description=f"**{track_name}** by **{artist_name}**\n\n[Open in Spotify]({link})",
                color=await self.bot.get_color(ctx.author.id)
            )
            if spotify_data.get("cover_art"):
                embed.set_thumbnail(url=spotify_data["cover_art"])
            embed.set_footer(text=f"{lastfm_username} • Last.fm to Spotify", icon_url="https://git.cursi.ng/lastfm_logo.png")
            paginator = Paginator(ctx, [embed], hide_nav=True, hide_footer=True)
            paginator.add_link_button(
                url=link,
                emoji=discord.PartialEmoji.from_str("<:spotify:1274904265114124308>"),
                persist=True
            )
            await paginator.start()

    @lastfm_group.command(name="toptracks", description="Get your Last.fm top scrobbled tracks", aliases=["tt"])
    @app_commands.describe(username="Last.fm username (optional)", period="Select a time period")
    @app_commands.choices(period=VALID_PERIODS)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def lastfm_top_tracks(self, ctx: commands.Context, username: Optional[str] = None, period: Optional[str] = "7day"):
        collage = False
        await self._lastfm_top_command(ctx, "tracks", username, period, collage)

    @lastfm_group.command(name="topartists", description="Get your Last.fm top scrobbled artists", aliases=["tar"])
    @app_commands.describe(username="Last.fm username (optional)", period="Select a time period")
    @app_commands.choices(period=VALID_PERIODS)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def lastfm_top_artists(self, ctx: commands.Context, username: Optional[str] = None, period: Optional[str] = "7day"):
        collage = False
        await self._lastfm_top_command(ctx, "artists", username, period, collage)

    @lastfm_group.command(name="topalbums", description="Get your Last.fm top scrobbled albums", aliases=["ta"])
    @app_commands.describe(username="Last.fm username (optional)", period="Select a time period")
    @app_commands.choices(period=VALID_PERIODS)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def lastfm_top_albums(self, ctx: commands.Context, username: Optional[str] = None, period: Optional[str] = "7day"):
        collage = False
        await self._lastfm_top_command(ctx, "albums", username, period, collage)

    async def _lastfm_top_command(self, ctx: commands.Context, item_type: str, username: Optional[str], period: str, collage: bool):
        async with ctx.typing():
            async with self.bot.pool.acquire() as conn:
                if username is None:
                    row = await conn.fetchrow("SELECT lastfm_username, hidden FROM lastfm_users WHERE discord_id = $1", ctx.author.id)
                    if not row:
                        lastfmlogin = await CommandCache.get_mention(self.bot, "lastfm login")
                        return await ctx.warn(f"You haven’t linked your Last.fm account yet. Use {lastfmlogin}.")
                    real_username = row["lastfm_username"]
                    hidden = row.get("hidden", False)
                else:
                    real_username = username
                    hidden = False

            if collage:
                collage_period = COLLAGE_PERIODS.get(period, "7days")

                payload = {
                    "username": real_username,
                    "type": item_type,
                    "period": collage_period,
                    "rowNum": 4,
                    "colNum": 4,
                    "showName": True,
                    "hideMissing": False
                }

                headers = {
                    "Content-Type": "application/json;charset=UTF-8",
                    "Accept": "application/json, text/plain, */*",
                    "Origin": "https://lastcollage.io",
                    "Referer": "https://lastcollage.io/load"
                }

                async with self.session.post("https://lastcollage.io/api/collage", json=payload, headers=headers) as resp:
                    text = await resp.text()
                    print("COLLAGE RESPONSE:", resp.status, text, flush=True)

                    if resp.status == 200:
                        data = await resp.json()
                        if not data.get("path"):
                            return await ctx.warn("Failed to generate collage.")

                        image_url = f"https://lastcollage.io/{data['path']}"
                        async with self.session.get(image_url) as img:
                            if img.status == 200:
                                file = discord.File(io.BytesIO(await img.read()), filename="collage.png")

                                embed = discord.Embed(color=await self.bot.get_color(ctx.author.id))
                                embed.set_image(url="attachment://collage.png")
                                shown_name = ctx.author.display_name if hidden else real_username
                                embed.set_author(
                                    name=f"{shown_name}'s Top {item_type.capitalize()} ({PERIOD_DISPLAY.get(period, period)})",
                                    icon_url=ctx.author.display_avatar.url
                                )
                                return await ctx.send(embed=embed, file=file)

            user_info_url = f"https://ws.audioscrobbler.com/2.0/?method=user.getinfo&user={real_username}&api_key={self.LASTFM_KEY}&format=json"
            async with self.session.get(user_info_url) as r:
                user_data = await r.json()
            total_scrobbles = int(user_data.get("user", {}).get("playcount", 0))

            url = f"https://ws.audioscrobbler.com/2.0/?method=user.gettop{item_type}&user={real_username}&period={period}&api_key={self.LASTFM_KEY}&format=json&limit=50"
            async with self.session.get(url) as r:
                if r.status != 200:
                    return await ctx.warn("Failed to fetch data from Last.fm.")
                data = await r.json()

            key = f"top{item_type}"
            items = data.get(key, {}).get(item_type[:-1], [])
            if not items:
                return await ctx.warn(f"No {item_type} found for `{real_username}`.")

            per_page = 10
            embeds = []
            for i in range(0, len(items), per_page):
                chunk = items[i:i + per_page]
                desc = ""
                thumb = None

                for idx, item in enumerate(chunk, start=i + 1):
                    if item_type == "tracks":
                        name = item["name"]
                        artist = item["artist"]["name"]
                        plays = item["playcount"]
                        desc += (
                            f"{idx}. **[{name}](https://www.last.fm/music/{urllib.parse.quote(artist)}/_/"
                            f"{urllib.parse.quote(name)})** by "
                            f"[{artist}](https://www.last.fm/music/{urllib.parse.quote(artist)})"
                            f" - *{plays} plays*\n"
                        )

                        if thumb is None:
                            ti_url = (
                                "https://ws.audioscrobbler.com/2.0/?method=track.getInfo"
                                f"&api_key={self.LASTFM_KEY}"
                                f"&artist={urllib.parse.quote(artist)}"
                                f"&track={urllib.parse.quote(name)}"
                                f"&username={urllib.parse.quote(real_username)}"
                                "&format=json"
                            )
                            try:
                                async with self.session.get(ti_url) as tr:
                                    if tr.status == 200:
                                        trj = await tr.json()
                                        alb = trj.get("track", {}).get("album", {})
                                        imgs = alb.get("image", [])
                                        thumb = imgs[-1].get("#text") if imgs else None
                            except:
                                pass

                    elif item_type == "artists":
                        name = item["name"]
                        plays = item["playcount"]
                        desc += (
                            f"{idx}. **[{name}](https://www.last.fm/music/{urllib.parse.quote(name)})**"
                            f" - *{plays} plays*\n"
                        )

                        if thumb is None:
                            ai_url = (
                                "https://ws.audioscrobbler.com/2.0/?method=artist.getInfo"
                                f"&artist={urllib.parse.quote(name)}"
                                f"&api_key={self.LASTFM_KEY}"
                                "&format=json"
                            )
                            try:
                                async with self.session.get(ai_url) as ar:
                                    if ar.status == 200:
                                        arj = await ar.json()
                                        imgs = arj.get("artist", {}).get("image", [])
                                        thumb = imgs[-1].get("#text") if imgs else None
                            except:
                                pass

                    elif item_type == "albums":
                        name = item["name"]
                        artist = item["artist"]["name"]
                        plays = item["playcount"]
                        desc += (
                            f"{idx}. **[{name}](https://www.last.fm/music/{urllib.parse.quote(artist)}/"
                            f"{urllib.parse.quote(name)})** by "
                            f"[{artist}](https://www.last.fm/music/{urllib.parse.quote(artist)})"
                            f" - *{plays} plays*\n"
                        )

                        if thumb is None:
                            ai_url = (
                                "https://ws.audioscrobbler.com/2.0/?method=album.getInfo"
                                f"&artist={urllib.parse.quote(artist)}"
                                f"&album={urllib.parse.quote(name)}"
                                f"&api_key={self.LASTFM_KEY}"
                                "&format=json"
                            )
                            try:
                                async with self.session.get(ai_url) as ar:
                                    if ar.status == 200:
                                        arj = await ar.json()
                                        imgs = arj.get("album", {}).get("image", [])
                                        thumb = imgs[-1].get("#text") if imgs else None
                            except:
                                pass

                embed_color = await self.bot.get_color(ctx.author.id)
                if thumb:
                    try:
                        async with self.session.get(thumb) as resp:
                            if resp.status == 200:
                                embed_color = await self.get_dominant_color(await resp.read())
                    except:
                        pass

                shown_name = ctx.author.display_name if hidden else real_username
                author_url = None if hidden else f"https://last.fm/user/{real_username}"

                embed = discord.Embed(
                    description=desc.strip(),
                    color=embed_color,
                    url=author_url
                )

                embed.set_author(
                    name=f"{shown_name}'s Top {item_type.capitalize()} ({PERIOD_DISPLAY.get(period, period)})",
                    url=author_url,
                    icon_url=ctx.author.display_avatar.url
                )

                embed.set_footer(
                    text=f"Page {i // per_page + 1}/{(len(items) + per_page - 1) // per_page} • {shown_name} has {total_scrobbles:,} scrobbles",
                    icon_url="https://git.cursi.ng/lastfm_logo.png"
                )

                if thumb:
                    embed.set_thumbnail(url=thumb)

                embeds.append(embed)

            paginator = Paginator(ctx, embeds, hide_footer=True)
            await paginator.start()

    @lastfm_group.command(name="whoknows", description="See who in the server knows an artist", aliases=["wk", "whoknowsartist"])
    async def lastfm_whoknows(self, ctx: commands.Context, *, artist: Optional[str] = None):
        if not ctx.guild:
            return await ctx.warn("This command can only be used in servers.")
        async with ctx.typing():
            if not artist:
                me = await self.get_last_recent(ctx.author.id)
                if not me:
                    return await ctx.warn("Could not fetch your recent track.")
                artist_name = me["artist"]
            else:
                if " - " in artist:
                    artist_name = artist.split(" - ", 1)[0].strip()
                else:
                    artist_name = artist.strip()
                    try:
                        search_url = f"https://ws.audioscrobbler.com/2.0/?method=artist.search&artist={urllib.parse.quote(artist_name)}&api_key={self.LASTFM_KEY}&format=json&limit=1"
                        async with self.session.get(search_url) as r:
                            if r.status == 200:
                                jr = await r.json()
                                matches = jr.get("results", {}).get("artistmatches", {}).get("artist", [])
                                if isinstance(matches, list) and matches:
                                    artist_name = matches[0].get("name", artist_name)
                    except Exception:
                        pass
            result = await self._wk_aggregate(ctx, mode="artist", subject={"artist": artist_name})
            if isinstance(result, str):
                return await ctx.warn(result)
            subject = result["subject_meta"]
            listeners = result["listeners"]
            thumb_url = None
            if not listeners:
                return await ctx.warn(f"No one in this server has listened to **{subject.get('artist', artist_name)}**.")
            total_plays = sum(l["plays"] for l in listeners)
            listener_count = len(listeners)
            avg = total_plays // listener_count if listener_count else 0
            lines = []
            for i, l in enumerate(listeners[:15], 1):
                member = ctx.guild.get_member(l["discord_id"])
                display = member.display_name if member else l["username"]
                if l.get("hidden"):
                    lines.append(f"{i}. **{display}** - **{l['plays']:,}** plays")
                else:
                    lines.append(f"{i}. [**{l['username']}**](https://last.fm/user/{urllib.parse.quote(l['username'])}) - **{l['plays']:,}** plays")
            desc = "\n".join(lines)
            color = await self.bot.get_color(ctx.author.id)
            if not thumb_url:
                try:
                    api_url = f"http://127.0.0.1:2053/api/spotify/artist?artist_name={urllib.parse.quote(subject.get('artist',''))}"
                    async with self.session.get(api_url) as r:
                        if r.status == 200:
                            j = await r.json()
                            if j.get("cover_art"):
                                thumb_url = j.get("cover_art")
                except Exception:
                    pass
            if thumb_url:
                try:
                    async with self.session.get(thumb_url) as resp:
                        if resp.status == 200:
                            img = await resp.read()
                            color = await self.get_dominant_color(img)
                except Exception:
                    pass
            embed = discord.Embed(title=f"{subject.get('artist')} in {ctx.guild.name}", url=subject.get("url"), description=desc, color=color)
            if thumb_url:
                embed.set_thumbnail(url=thumb_url)
            embed.set_footer(text=f"Artist - {listener_count} listeners - {total_plays} plays - {avg} avg", icon_url="https://git.cursi.ng/lastfm_logo.png")
            await ctx.send(embed=embed)

    @lastfm_group.command(name="whoknowsalbum", description="See who in the server knows an album", aliases=["wka", "wkalbum"])
    async def lastfm_whoknows_album(self, ctx: commands.Context, *, album: Optional[str] = None):
        if not ctx.guild:
            return await ctx.warn("This command can only be used in servers.")
        async with ctx.typing():
            artist_name = None
            album_name = None
            if album:
                if " - " in album:
                    parts = album.split(" - ", 1)
                    artist_name = parts[0].strip()
                    album_name = parts[1].strip()
                else:
                    query = album.strip()
                    try:
                        search_url = f"https://ws.audioscrobbler.com/2.0/?method=album.search&album={urllib.parse.quote(query)}&api_key={self.LASTFM_KEY}&format=json&limit=1"
                        async with self.session.get(search_url) as r:
                            if r.status == 200:
                                jr = await r.json()
                                matches = jr.get("results", {}).get("albummatches", {}).get("album", [])
                                if isinstance(matches, list) and matches:
                                    album_name = matches[0].get("name")
                                    artist_name = matches[0].get("artist")
                    except Exception:
                        pass
                    if not album_name:
                        return await ctx.warn("Please provide album as `Artist - Album`, or use a term that can be found by Last.fm.")
            else:
                me = await self.get_last_recent(ctx.author.id)
                if not me or not me.get("album"):
                    return await ctx.warn("Could not determine your last played album.")
                artist_name = me["artist"]
                album_name = me["album"]
            result = await self._wk_aggregate(ctx, mode="album", subject={"artist": artist_name, "album": album_name})
            if isinstance(result, str):
                return await ctx.warn(result)
            subject = result["subject_meta"]
            listeners = result["listeners"]
            thumb_url = result.get("thumb")
            if not listeners:
                return await ctx.warn(f"No one in this server has listened to **{subject.get('album')}** by **{subject.get('artist')}**.")
            total_plays = sum(l["plays"] for l in listeners)
            listener_count = len(listeners)
            avg = total_plays // listener_count if listener_count else 0
            lines = []
            for i, l in enumerate(listeners[:15], 1):
                member = ctx.guild.get_member(l["discord_id"])
                display = member.display_name if member else l["username"]
                if l.get("hidden"):
                    lines.append(f"{i}. **{display}** - **{l['plays']:,}** plays")
                else:
                    lines.append(f"{i}. [**{l['username']}**](https://last.fm/user/{urllib.parse.quote(l['username'])}) - **{l['plays']:,}** plays")
            desc = "\n".join(lines)
            color = await self.bot.get_color(ctx.author.id)
            if not thumb_url:
                try:
                    api_url = f"http://127.0.0.1:2053/api/spotify/artist?artist_name={urllib.parse.quote(subject.get('artist',''))}"
                    async with self.session.get(api_url) as r:
                        if r.status == 200:
                            j = await r.json()
                            if j.get("cover_art"):
                                thumb_url = j.get("cover_art")
                except Exception:
                    pass
            if thumb_url:
                try:
                    async with self.session.get(thumb_url) as resp:
                        if resp.status == 200:
                            img = await resp.read()
                            color = await self.get_dominant_color(img)
                except Exception:
                    pass
            embed = discord.Embed(title=f"{subject.get('album')} by {subject.get('artist')} in {ctx.guild.name}", url=subject.get("url"), description=desc, color=color)
            if thumb_url:
                embed.set_thumbnail(url=thumb_url)
            embed.set_footer(text=f"Album - {listener_count} listeners - {total_plays} plays - {avg} avg", icon_url="https://git.cursi.ng/lastfm_logo.png")
            await ctx.send(embed=embed)

    @lastfm_group.command(name="whoknowstrack", description="See who in the server knows a track", aliases=["wkt", "wktrack"])
    async def lastfm_whoknows_track(self, ctx: commands.Context, *, track: Optional[str] = None):
        if not ctx.guild:
            return await ctx.warn("This command can only be used in servers.")
        async with ctx.typing():
            artist_name = None
            track_name = None
            if track:
                if " - " in track:
                    parts = track.split(" - ", 1)
                    artist_name = parts[0].strip()
                    track_name = parts[1].strip()
                else:
                    query = track.strip()
                    found = False
                    try:
                        search_url = f"https://ws.audioscrobbler.com/2.0/?method=track.search&track={urllib.parse.quote(query)}&api_key={self.LASTFM_KEY}&format=json&limit=1"
                        async with self.session.get(search_url) as r:
                            if r.status == 200:
                                jr = await r.json()
                                matches = jr.get("results", {}).get("trackmatches", {}).get("track", [])
                                if isinstance(matches, list) and matches:
                                    track_name = matches[0].get("name")
                                    artist_name = matches[0].get("artist")
                                    found = True
                    except Exception:
                        pass
                    if not found:
                        try:
                            search_url = f"https://ws.audioscrobbler.com/2.0/?method=album.search&album={urllib.parse.quote(query)}&api_key={self.LASTFM_KEY}&format=json&limit=1"
                            async with self.session.get(search_url) as r:
                                if r.status == 200:
                                    jr = await r.json()
                                    matches = jr.get("results", {}).get("albummatches", {}).get("album", [])
                                    if isinstance(matches, list) and matches:
                                        album_name = matches[0].get("name")
                                        artist_name = matches[0].get("artist")
                                        track_name = None
                                        found = True
                        except Exception:
                            pass
                    if not found:
                        return await ctx.warn("Could not find a matching track or album on Last.fm for your query.")
            else:
                me = await self.get_last_recent(ctx.author.id)
                if not me or not me.get("track"):
                    return await ctx.warn("Could not determine your last played track.")
                artist_name = me["artist"]
                track_name = me["track"]
            if not track_name and artist_name and 'album_name' in locals():
                return await ctx.warn("Please provide a track or use the album command for album-level lookups.")
            result = await self._wk_aggregate(ctx, mode="track", subject={"artist": artist_name, "track": track_name})
            if isinstance(result, str):
                return await ctx.warn(result)
            subject = result["subject_meta"]
            listeners = result["listeners"]
            thumb_url = result.get("thumb")
            if not listeners:
                return await ctx.warn(f"No one in this server has listened to **{subject.get('track')}** by **{subject.get('artist')}**.")
            total_plays = sum(l["plays"] for l in listeners)
            listener_count = len(listeners)
            avg = total_plays // listener_count if listener_count else 0
            lines = []
            for i, l in enumerate(listeners[:15], 1):
                member = ctx.guild.get_member(l["discord_id"])
                display = member.display_name if member else l["username"]
                if l.get("hidden"):
                    lines.append(f"{i}. **{display}** - **{l['plays']:,}** plays")
                else:
                    lines.append(f"{i}. [**{l['username']}**](https://last.fm/user/{urllib.parse.quote(l['username'])}) - **{l['plays']:,}** plays")
            desc = "\n".join(lines)
            color = await self.bot.get_color(ctx.author.id)
            if not thumb_url:
                try:
                    api_url = f"http://127.0.0.1:2053/api/spotify/artist?artist_name={urllib.parse.quote(subject.get('artist',''))}"
                    async with self.session.get(api_url) as r:
                        if r.status == 200:
                            j = await r.json()
                            if j.get("cover_art"):
                                thumb_url = j.get("cover_art")
                except Exception:
                    pass
            if thumb_url:
                try:
                    async with self.session.get(thumb_url) as resp:
                        if resp.status == 200:
                            img = await resp.read()
                            color = await self.get_dominant_color(img)
                except Exception:
                    pass
            album_url = None
            try:
                ti_url = f"https://ws.audioscrobbler.com/2.0/?method=track.getInfo&artist={urllib.parse.quote(subject.get('artist',''))}&track={urllib.parse.quote(subject.get('track',''))}&api_key={self.LASTFM_KEY}&format=json"
                async with self.session.get(ti_url) as r:
                    if r.status == 200:
                        ti = await r.json()
                        alb = ti.get("track", {}).get("album", {})
                        alb_name = alb.get("title")
                        if alb_name:
                            album_url = f"https://www.last.fm/music/{urllib.parse.quote(subject.get('artist',''))}/{urllib.parse.quote(alb_name)}"
            except Exception:
                pass
            embed = discord.Embed(title=f"{subject.get('track')} by {subject.get('artist')} in {ctx.guild.name}", url=album_url or subject.get("url"), description=desc, color=color)
            if thumb_url:
                embed.set_thumbnail(url=thumb_url)
            embed.set_footer(text=f"Track - {listener_count} listeners - {total_plays} plays - {avg} avg", icon_url="https://git.cursi.ng/lastfm_logo.png")
            await ctx.send(embed=embed)

    async def get_last_recent(self, discord_id: int):
        user = await self.get_lastfm_user(discord_id)
        if not user:
            return None
        username, _hidden = user
        url = f"https://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={urllib.parse.quote(username)}&api_key={self.LASTFM_KEY}&format=json&limit=1"
        async with self.session.get(url) as r:
            if r.status != 200:
                return None
            data = await r.json()
        tracks = data.get("recenttracks", {}).get("track", [])
        if not tracks:
            return None
        t = tracks[0]
        return {
            "artist": t["artist"]["#text"],
            "track": t["name"],
            "album": t.get("album", {}).get("#text") or None
        }

    async def _wk_aggregate(self, ctx: commands.Context, mode: str, subject: dict):
        cache_id = ""
        if mode == "artist":
            cache_id = subject["artist"].lower()
        elif mode == "album":
            cache_id = (subject["artist"] + " - " + subject["album"]).lower()
        else:
            cache_id = (subject["artist"] + " - " + subject["track"]).lower()
        cache_key = f"wk:{mode}:{ctx.guild.id}:{cache_id}"
        cached = await self.bot.redis.get(cache_key)
        if cached:
            try:
                payload = json.loads(cached.decode("utf-8") if isinstance(cached, bytes) else cached)
                return payload
            except Exception:
                pass
        if mode == "artist":
            info_url = f"https://ws.audioscrobbler.com/2.0/?method=artist.getInfo&artist={urllib.parse.quote(subject['artist'])}&api_key={self.LASTFM_KEY}&format=json"
        elif mode == "album":
            info_url = f"https://ws.audioscrobbler.com/2.0/?method=album.getInfo&artist={urllib.parse.quote(subject['artist'])}&album={urllib.parse.quote(subject['album'])}&api_key={self.LASTFM_KEY}&format=json"
        else:
            info_url = f"https://ws.audioscrobbler.com/2.0/?method=track.getInfo&artist={urllib.parse.quote(subject['artist'])}&track={urllib.parse.quote(subject['track'])}&api_key={self.LASTFM_KEY}&format=json"
        async with self.session.get(info_url) as r:
            if r.status != 200:
                return "This item does not exist on Last.fm or has 0 scrobbles."
            info = await r.json()
        subject_meta = None
        thumb = None
        if mode == "artist":
            if "artist" not in info:
                return "This item does not exist on Last.fm or has 0 scrobbles."
            name = info["artist"]["name"]
            url = info["artist"]["url"]
            images = info["artist"].get("image", [])
            if images:
                thumb = images[-1].get("#text") or None
            subject_meta = {"title": name, "url": url, "kind": "Artist", "artist": name}
        elif mode == "album":
            if "album" not in info:
                return "This item does not exist on Last.fm or has 0 scrobbles."
            name = info["album"]["name"]
            artist = info["album"]["artist"]
            url = info["album"]["url"]
            images = info["album"].get("image", [])
            if images:
                thumb = images[-1].get("#text") or None
            subject_meta = {"title": name, "url": url, "kind": "Album", "artist": artist, "album": name}
        else:
            if "track" not in info:
                return "This item does not exist on Last.fm or has 0 scrobbles."
            name = info["track"]["name"]
            artist = info["track"]["artist"]["name"] if isinstance(info["track"]["artist"], dict) else subject["artist"]
            url = info["track"]["url"]
            album = info["track"].get("album", {})
            images = album.get("image", []) if isinstance(album, dict) else []
            if images:
                thumb = images[-1].get("#text") or None
            subject_meta = {"title": name, "url": url, "kind": "Track", "artist": artist, "track": name}
        members = ctx.guild.members
        member_ids = [m.id for m in members]
        if not member_ids:
            return "No members found in this server."
        placeholders = ','.join(f'${i+1}' for i in range(len(member_ids)))
        query = f"SELECT discord_id, lastfm_username, COALESCE(hidden, false) AS hidden FROM lastfm_users WHERE discord_id IN ({placeholders})"
        guild_users = await self.bot.pool.fetch(query, *member_ids)
        if not guild_users:
            return "No one in this server has linked their Last.fm account."
        seen_usernames = set()
        unique_guild_users = []
        for user in guild_users:
            print(f"  - {user['lastfm_username']} (discord_id: {user['discord_id']})", flush=True)
            if user["lastfm_username"].lower() not in seen_usernames:
                seen_usernames.add(user["lastfm_username"].lower())
                unique_guild_users.append(user)
        guild_users = unique_guild_users
        sem = asyncio.Semaphore(8)
        listeners = []
        async def fetch_user(u):
            async with sem:
                uname = u["lastfm_username"]
                if mode == "artist":
                    url = f"https://ws.audioscrobbler.com/2.0/?method=artist.getInfo&artist={urllib.parse.quote(subject_meta['artist'])}&username={urllib.parse.quote(uname)}&api_key={self.LASTFM_KEY}&format=json"
                elif mode == "album":
                    url = f"https://ws.audioscrobbler.com/2.0/?method=album.getInfo&artist={urllib.parse.quote(subject_meta['artist'])}&album={urllib.parse.quote(subject_meta['album'])}&username={urllib.parse.quote(uname)}&api_key={self.LASTFM_KEY}&format=json"
                else:
                    url = f"https://ws.audioscrobbler.com/2.0/?method=track.getInfo&artist={urllib.parse.quote(subject_meta['artist'])}&track={urllib.parse.quote(subject_meta['track'])}&username={urllib.parse.quote(uname)}&api_key={self.LASTFM_KEY}&format=json"
                try:
                    async with self.session.get(url) as r:
                        if r.status != 200:
                            return
                        data = await r.json()
                        plays = 0
                        if mode == "artist" and "artist" in data:
                            plays = int(data["artist"].get("stats", {}).get("userplaycount", 0))
                        elif mode == "album" and "album" in data:
                            plays = int(data["album"].get("userplaycount", 0))
                        elif mode == "track" and "track" in data:
                            plays = int(data["track"].get("userplaycount", 0))
                        if plays > 0:
                            listeners.append({"discord_id": u["discord_id"], "username": uname, "plays": plays, "hidden": u["hidden"]})
                except Exception:
                    return
        await asyncio.gather(*(fetch_user(u) for u in guild_users))
        listeners.sort(key=lambda x: x["plays"], reverse=True)
        payload = {"subject_meta": subject_meta, "listeners": listeners, "thumb": thumb}
        await self.bot.redis.setex(cache_key, 1800, json.dumps(payload))
        return payload

    async def _wk_build_embed(self, ctx: commands.Context, mode: str, subject: dict, listeners: list, thumb_url: Optional[str]):
        if not listeners:
            return discord.Embed(title=f"Who knows {subject.get('title','this item')}?", description="No listeners found in this server.", color=await self.bot.get_color(ctx.author.id))
        total_plays = sum(l["plays"] for l in listeners)
        listener_count = len(listeners)
        avg = total_plays // listener_count if listener_count else 0
        lines = []
        for i, l in enumerate(listeners[:15], 1):
            member = ctx.guild.get_member(l["discord_id"])
            display = member.display_name if member else l["username"]
            if l["hidden"]:
                lines.append(f"{i}. **{display}** - **{l['plays']:,}** plays")
            else:
                lines.append(f"{i}. [**{l['username']}**](https://last.fm/user/{urllib.parse.quote(l['username'])}) - **{l['plays']:,}** plays")
        desc = "\n".join(lines)
        title = subject["title"]
        url = subject["url"]
        kind = subject["kind"]
        embed = discord.Embed(title=title, url=url, description=desc, color=await self.bot.get_color(ctx.author.id))
        if thumb_url:
            embed.set_thumbnail(url=thumb_url)
        footer = f"{kind} - {listener_count} listeners - {total_plays} plays - {avg} avg"
        embed.set_footer(text=footer, icon_url="https://git.cursi.ng/lastfm_logo.png")
        return embed

    @lastfm_group.command(name="latest", description="View your latest Last.fm scrobbles", aliases=["recent", "recenttracks", "rt"])
    @app_commands.describe(username="Last.fm username (optional)")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def lastfm_latest(self, ctx: commands.Context, username: Optional[str] = None):
        async with ctx.typing():
            async with self.bot.pool.acquire() as conn:
                if username is None:
                    row = await conn.fetchrow("SELECT lastfm_username, hidden FROM lastfm_users WHERE discord_id = $1", ctx.author.id)
                    if not row:
                        lastfmlogin = await CommandCache.get_mention(self.bot, "lastfm login")
                        return await ctx.warn(f"You haven’t linked your Last.fm account yet. Use {lastfmlogin}.")
                    real_username = row["lastfm_username"]
                    hidden = row["hidden"]
                else:
                    real_username = username
                    hidden = False

            url = f"https://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={urllib.parse.quote(real_username)}&api_key={self.LASTFM_KEY}&format=json&limit=50"
            async with self.session.get(url) as r:
                if r.status != 200:
                    return await ctx.warn("Failed to fetch data from Last.fm.")
                data = await r.json()

            if "error" in data:
                return await ctx.warn(data.get("message", "Last.fm error"))

            tracks = data.get("recenttracks", {}).get("track", [])
            if not tracks:
                return await ctx.warn(f"No recent tracks found for `{real_username}`.")

            total_scrobbles = int(data["recenttracks"]["@attr"].get("total", 0))

            embeds = []
            per_page = 5
            for i in range(0, len(tracks), per_page):
                chunk = tracks[i:i + per_page]
                desc = ""
                thumb = None

                for t in chunk:
                    name = t.get("name", "Unknown Track")
                    artist = t.get("artist", {}).get("#text", "Unknown Artist")
                    album = t.get("album", {}).get("#text") or None
                    url = t.get("url") or "#"

                    if not thumb:
                        images = t.get("image", [])
                        thumb = images[-1].get("#text") if images else None

                    uts = t.get("date", {}).get("uts")
                    ts = f"<t:{int(uts)}:R>" if uts else "🎶"

                    if album:
                        desc += f"**[{name}]({url})** by **{artist}**\n-# {ts} • *{album}*\n\n"
                    else:
                        desc += f"**[{name}]({url})** by **{artist}**\n-# {ts}\n\n"

                embed_color = await self.bot.get_color(ctx.author.id)
                if thumb:
                    try:
                        async with self.session.get(thumb) as resp:
                            if resp.status == 200:
                                embed_color = await self.get_dominant_color(await resp.read())
                    except:
                        pass

                shown_name = ctx.author.display_name if hidden else real_username
                author_url = None if hidden else f"https://last.fm/user/{real_username}"

                embed = discord.Embed(
                    description=desc.strip(),
                    color=embed_color,
                    url=author_url
                )

                embed.set_author(
                    name=f"Latest tracks for {shown_name}",
                    icon_url=ctx.author.display_avatar.url,
                    url=author_url
                )

                embed.set_footer(
                    text=f"Page {len(embeds)+1}/{(len(tracks)+per_page-1)//per_page} • {shown_name} has {total_scrobbles:,} scrobbles",
                    icon_url="https://git.cursi.ng/lastfm_logo.png"
                )

                if thumb:
                    embed.set_thumbnail(url=thumb)

                embeds.append(embed)

            paginator = Paginator(ctx, embeds, hide_footer=True)
            await paginator.start()


    @commands.hybrid_group(name="spotify", description="Spotify related commands", aliases=["spoti"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def spotify_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    async def statsfm_search_tracks(self, query: str, limit: int = 10):
        url = "https://api.stats.fm/api/v1/search/elastic"
        params = {"query": query, "type": "track", "limit": str(limit)}
        headers = {"User-Agent": "Heist Bot/3.0"}
        async with self.session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=6)) as r:
            if r.status != 200:
                return []
            data = await r.json()
        return data.get("items", {}).get("tracks", []) or []

    async def get_statsfm_preview(self, track_name: str, artist_name: str):
        url = "https://api.stats.fm/api/v1/search/elastic"
        params = {"query": track_name, "type": "track", "limit": "25"}
        headers = {"User-Agent": "Heist Bot/3.0"}
        async with self.session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=6)) as r:
            if r.status != 200:
                return None
            data = await r.json()
        tracks = data.get("items", {}).get("tracks", []) or []
        a_l = artist_name.lower()
        for t in tracks:
            for a in t.get("artists", []):
                if a.get("name", "").lower() == a_l:
                    return t.get("spotifyPreview") or t.get("appleMusicPreview")
        return None

    async def spotifypreview_auto(self, interaction, current):
        if not current or len(current) < 2:
            return []
        res = await self.statsfm_search_tracks(current, limit=10)
        out = []
        now = time.time()
        for t in res:
            tid = t.get("id")
            if not tid:
                continue
            name = t.get("name") or "Unknown"
            artists = t.get("artists") or []
            artist_txt = ", ".join(a.get("name") for a in artists)
            label = f"{name} — {artist_txt}"
            self.track_cache[str(tid)] = (t, now + self.cache_ttl)
            out.append(app_commands.Choice(name=label[:100], value=str(tid)))
        return out[:10]

    @spotify_group.command(name="preview", description="Get a track preview from Spotify")
    @app_commands.describe(track="Track name")
    @app_commands.autocomplete(track=spotifypreview_auto)
    async def spotifypreview(self, ctx: commands.Context, track: str):
        async with ctx.typing():
            cache = {}
            async def download_audio(url):
                now = time.time()
                c = cache.get(url)
                if c and c[1] > now:
                    return c[0]
                try:
                    async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                        if r.status != 200:
                            return None
                        b = await r.read()
                        cache[url] = (b, now + 60)
                        return b
                except:
                    return None

            tid = track.strip()
            now = time.time()
            local_td = None
            c = self.track_cache.get(tid)
            if c and c[1] > now:
                local_td = c[0]
            else:
                res = await self.statsfm_search_tracks(track, limit=1)
                if res:
                    local_td = res[0]

            if not local_td:
                await ctx.warn("No tracks found.")
                return

            tname = local_td.get("name") or "Unknown"
            artists = local_td.get("artists") or []
            aname = artists[0].get("name") if artists else "Unknown"
            cover = None
            albums = local_td.get("albums") or []
            if albums:
                cover = albums[0].get("image")

            purl = local_td.get("spotifyPreview") or local_td.get("appleMusicPreview")
            if not purl:
                purl = await self.get_statsfm_preview(tname, aname)

            audio_bytes = None
            if purl:
                audio_bytes = await download_audio(purl)

            if not audio_bytes:
                await ctx.warn("No preview available.")
                return

            col = discord.Color.blurple()
            try:
                base_c = await self.bot.get_color(ctx.author.id)
                if isinstance(base_c, int):
                    col = discord.Color(base_c)
            except:
                pass

            line1 = f"**Artist:** {aname}"
            album_name = albums[0].get("name") if albums else None
            if album_name:
                line1 += f"\n**Album:** {album_name}"
            dur = local_td.get("durationMs")
            if dur:
                s = max(0, int(dur // 1000))
                m, s = divmod(s, 60)
                h, m = divmod(m, 60)
                line1 += f"\n**Duration:** {f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'}"
            explicit_val = local_td.get("explicit")
            if explicit_val is not None:
                line1 += f"\n**Explicit:** {'Yes' if explicit_val else 'No'}"

            title_txt = f"### {tname}"

            if cover:
                section = ui.Section(ui.TextDisplay(line1), accessory=ui.Thumbnail(cover))
            else:
                section = ui.TextDisplay(line1)

            blocks = [
                ui.TextDisplay(title_txt),
                ui.Separator(),
                section
            ]

            attrs = {}
            for i, b in enumerate(blocks):
                attrs[f"attr_{i}"] = b
            Container = type("SpotifyPreviewContainer", (ui.Container,), attrs)
            container = Container(accent_color=col)

            class PreviewView(ui.LayoutView):
                timeout = 120
                main = container

            view = PreviewView()

            bio = io.BytesIO(audio_bytes)
            bio.seek(0)
            safe_name = "".join(ch for ch in tname if ch not in r'\/:*?"<>|')[:120] or "preview"
            f = discord.File(bio, filename=f"{safe_name}.mp3")
            await ctx.send(file=f)
            await ctx.send(view=view)

async def setup(bot):
    await bot.add_cog(Music(bot))
