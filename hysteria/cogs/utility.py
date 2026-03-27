import discord, aiohttp, asyncio, base64, random, time, io
from discord import app_commands, File, Embed, Interaction
from discord.ext import commands
from typing import Optional, Union
import aiofiles, aiofiles.os
from datetime import datetime, timedelta
import yt_dlp
import os
import re
from utils.access import is_whitelisted
from utils.cooldowns import cooldown
from dotenv import dotenv_values
import json as jason
import pycountry
import asyncpg
from utils.paginator import MessagePaginatorView, GuildPaginatorView, format_messages_page, format_guilds_page
from urllib.parse import quote
import urllib

OWNER = [
    1150918662769881088
]

config = dotenv_values(".env")
HEISTDATABASE_URL = config["HEISTDATABASE_URL"]
NAVY_KEY = config["NAVY_API_KEY"]

BASE = "http://127.0.0.1:9038/v1/search"

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.aitts = 0
        self.ctx_discorduser = app_commands.ContextMenu(
            name='Lookup User',
            callback=self.discorduser_context,
        )
        self.ctx_discordmessages = app_commands.ContextMenu(
            name='Lookup Messages',
            callback=self.discordmessages_context,
        )
        self.ctx_discordguilds = app_commands.ContextMenu(
            name='Lookup Guilds',
            callback=self.discordguilds_context,
        )
        self.bot.tree.add_command(self.ctx_discorduser)
        self.bot.tree.add_command(self.ctx_discordmessages)
        self.bot.tree.add_command(self.ctx_discordguilds)

    user = app_commands.Group(
        name="user", 
        description="user utilities",
        allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True),
        allowed_installs=app_commands.AppInstallationType(guild=True, user=True)
   )

    lookup = app_commands.Group(
        name="lookup", 
        description="lookups",
        allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True),
        allowed_installs=app_commands.AppInstallationType(guild=True, user=True)
   )

    discordg = app_commands.Group(
        name="discord", 
        description="discord lookups",
        parent=lookup
   )

    async def make_r2d_embed(self, roblox_id: int, roblox_name: str, discord_id: Optional[int], ropro_discord: Optional[str]) -> discord.Embed:
        description = ""
        thumbnail_url = "https://t0.rbxcdn.com/91d977e12525a5ed262cd4dc1c4fd52b?format=png"
        if discord_id:
            try:
                discord_user = await self.bot.fetch_user(int(discord_id))
                description += f"**{roblox_name}** has been identified as [**{discord_user}**](discord://-/users/{discord_id})\n"
                description += f"userid: {discord_id}\n"
                thumbnail_url = discord_user.display_avatar.url
            except:
                description += f"oops could not fetch discord user {discord_id}\n"
        if ropro_discord:
            description += f"ropro also found: **{ropro_discord}**"
        embed = discord.Embed(color=self.bot.color, description=description)
        embed.set_thumbnail(url=thumbnail_url)
        return embed

    async def make_d2r_embed(self, discord_user: discord.User, roblox_id: int, roblox_name: str) -> discord.Embed:
        thumbnail_url = "https://t0.rbxcdn.com/91d977e12525a5ed262cd4dc1c4fd52b?format=png"
        async with self.session.get(f"https://thumbnails.roproxy.com/v1/users/avatar-headshot?userIds={roblox_id}&size=420x420&format=Png&isCircular=false") as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("data"):
                    thumbnail_url = data["data"][0].get("imageUrl") or thumbnail_url
        description = f"**{discord_user}** has been identified as [**{roblox_name}**](https://roblox.com/users/{roblox_id}/profile)\n"
        embed = discord.Embed(color=self.bot.color, description=description)
        embed.set_thumbnail(url=thumbnail_url)
        return embed

    @lookup.command(name="r2d", description="roblox 2 discord")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_whitelisted)
    async def roblox2discord(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer()

        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as insecure_session:
            async with insecure_session.post(
                "https://users.roproxy.com/v1/usernames/users",
                headers={"accept": "application/json", "Content-Type": "application/json"},
                json={"usernames": [username], "excludeBannedUsers": False}
            ) as response:
                data = await response.json()
                if not data.get("data"):
                    return await self.bot.send_followup(
                        interaction, content=f"oops could not find roblox user {username}"
                    )
                roblox_id = int(data["data"][0]["id"])
                roblox_name = data["data"][0]["name"]

        async with self.session.get(f"{BASE}/r2d", params={"roblox_id": roblox_id}) as resp:
            result = await resp.json()
            if resp.status != 200:
                return await self.bot.send_followup(
                    interaction, content=f"oops no linked discord found for {roblox_name}"
                )
            discord_id = result.get("discord")
            ropro_discord = result.get("ropro_discord")

        embed = await self.make_r2d_embed(roblox_id, roblox_name, discord_id, ropro_discord)
        await self.bot.send_followup(interaction, embed=embed)

    @lookup.command(name="d2r", description="discord 2 roblox")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_whitelisted)
    async def discord2roblox(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        await interaction.response.defer()
        target_user = user or interaction.user
        discord_id = str(target_user.id)
        async with self.session.get(f"{BASE}/d2r", params={"discord_id": discord_id}) as resp:
            result = await resp.json()
            if resp.status != 200:
                return await self.bot.send_followup(interaction, content=f"oops no linked roblox account found for {target_user}")
            roblox_id = result.get("roblox_id")
            roblox_name = result.get("roblox_name")
        embed = await self.make_d2r_embed(target_user, roblox_id, roblox_name)
        await self.bot.send_followup(interaction, embed=embed)

    @app_commands.command(name="tts", description="text 2 speech")
    @app_commands.choices(voice=[
        app_commands.Choice(name="Female", value="en_us_001"),
        app_commands.Choice(name="Male", value="en_us_006"),
        app_commands.Choice(name="Male 2", value="en_us_007"),
        app_commands.Choice(name="Ghostface (Char)", value="en_us_ghostface"),
        app_commands.Choice(name="Stormtrooper (Char)", value="en_us_stormtrooper"),
        app_commands.Choice(name="Rocket (Char)", value="en_us_rocket"),
        app_commands.Choice(name="Tenor (Singing)", value="en_male_m03_lobby"),
        app_commands.Choice(name="Sunshine Soon (Singing)", value="en_male_m03_sunshine_soon"),
        app_commands.Choice(name="Warmy Breeze (Singing)", value="en_female_f08_warmy_breeze"),
        app_commands.Choice(name="Glorious (Singing)", value="en_female_ht_f08_glorious"),
        app_commands.Choice(name="It Goes Up (Singing)", value="en_male_sing_funny_it_goes_up"),
        app_commands.Choice(name="Chipmunk (Singing)", value="en_male_m2_xhxs_m03_silly"),
        app_commands.Choice(name="Dramatic (Singing)", value="en_female_ht_f08_wonderful_world")
    ])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_whitelisted)
    async def tospeech(self, interaction: discord.Interaction, text: str, voice: Optional[str] = None):
        await interaction.response.defer()
        if not text:
            return await self.bot.send_followup(interaction, content=f"oops no text provided")
        invalid_chars = {'.', ',', '/', '\\'}
        if set(text) <= invalid_chars:
            return await self.bot.send_followup(interaction, content=f"oops no audio could be generated. invalid character")
        if len(text) > 300:
            return await self.bot.send_followup(interaction, content=f"text too long. max 300 chars")
        start_time = time.time()
        headers = {'Content-Type': 'application/json'}
        selected_voice = voice or 'en_us_001'
        json_data = {'text': text, 'voice': selected_voice}
        async with self.session.post(
            'https://tiktok-tts.weilnet.workers.dev/api/generation',
            headers=headers,
            json=json_data
        ) as response:
            data = await response.json()
            if 'data' not in data or data['data'] is None:
                return await self.bot.send_followup(interaction, content=f"oops api did not return anything")
            audio = base64.b64decode(data['data'])
            audio_buffer = io.BytesIO(audio)
            audio_buffer.seek(0)
            rnum = random.randint(100, 999)
            filename_mp3 = f"tts_{rnum}.mp3"
            audio_file = File(audio_buffer, filename_mp3)

            end_time = time.time()
            duration = end_time - start_time
            await self.bot.send_followup(interaction, file=audio_file)

    @user.command(name="avatar", description="get someones avatar")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_whitelisted)
    async def avatar(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        user = user or interaction.user
        avatar_url = user.avatar.url if user.avatar else user.default_avatar.url
        if not avatar_url:
            return await interaction.response.send_message(content=f"oops could not fetch avatar for {user}")
        await interaction.response.send_message(avatar_url)

    @user.command(name="banner", description="get someones banner")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_whitelisted)
    async def banner(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        user = user or interaction.user
        full_user = await self.bot.fetch_user(user.id)
        if not full_user.banner:
            return await interaction.response.send_message(content=f"oops **{user}** has no banner set")
        await interaction.response.send_message(full_user.banner.url)

    @app_commands.command(
        name="music",
        description="download a song"
    )
    @app_commands.describe(
        query="query",
        stats="fancy embed or no"
    )
    @app_commands.choices(stats=[
        app_commands.Choice(name="Yes", value="yes"),
        app_commands.Choice(name="No", value="no")
    ])
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_whitelisted)
    async def music(self, interaction: discord.Interaction, query: str, stats: str = "yes"):
        await interaction.response.defer()
        temp_file_path = None
        try:
            soundcloud_url_pattern = re.compile(r'^https?://(?:www\.|on\.|m\.)?soundcloud\.com/[\w-]+/[\w-]+(?:\?.*si=[\w-]+.*)?$|^https?://(?:www\.|on\.|m\.)?soundcloud\.com/.+$')
            
            if not soundcloud_url_pattern.match(query):
                try:
                    search_opts = {
                        'extractor_args': {'soundcloud': {'client_id': 'f1TFyuaI8LX1Ybd1zvQRX8GpsNYcQ3Y5'}},
                        'quiet': True,
                        'no_warnings': True,
                        'simulate': True,
                        'skip_download': True,
                        'extract_flat': True,
                        'default_search': 'scsearch',
                        'limit': 5
                    }
                    loop = asyncio.get_event_loop()
                    search_info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(search_opts).extract_info(f"scsearch1:{query}", download=False))
                    first_track = None
                    for entry in search_info.get('entries', []):
                        url = entry.get('webpage_url')
                        if url and not ('/sets/' in url or '?set=' in url):
                            first_track = entry
                            break
                    if not first_track:
                        return await self.bot.send_followup(interaction, content="oops no valid tracks found")
                    query = first_track['webpage_url']
                except Exception as e:
                    return await self.bot.send_followup(interaction, content=f"oops {e}")

            if '/sets/' in query or '?set=' in query:
                return await self.bot.send_followup(interaction, content="oops sets and playlists are not supported")

            url_match = re.search(r'(https?://(?:www\.|on\.|m\.)?soundcloud\.com/[\w-]+/[\w-]+)', query)
            if url_match:
                query = url_match.group(1)

            file_extension = "mp3"
            timestamp = int(datetime.now().timestamp() * 1000)
            temp_file_path = os.path.join("temp", f"track_{timestamp}.{file_extension}")

            ydl_opts = {
                "format": "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "extractor_args": {"soundcloud": {"client_id": "jHEka5S67uXVaQRAQZVR8fhxpQI2tcsq"}},
                "outtmpl": temp_file_path
            }

            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(query, download=True))

            title = info.get('title')
            artist = info.get('uploader')
            artist_url = info.get('uploader_url')
            track_cover = max(info.get('thumbnails', [{'url': None}]), key=lambda x: x.get('width', 0)).get('url')
            plays = info.get('view_count')
            likes = info.get('like_count')
            reposts = info.get('repost_count')
            upload_date = info.get('upload_date')
            duration = info.get('duration', 0)

            td = timedelta(seconds=duration)
            durationf = "{:02d}:{:02d}".format(td.seconds // 60, td.seconds % 60)

            fdate = ""
            if upload_date:
                try:
                    date_obj = datetime.strptime(upload_date, '%Y%m%d')
                    fdate = date_obj.strftime("%d/%m/%Y")
                except Exception:
                    fdate = upload_date

            sanitized_title = re.sub(r'[<>:"/\\|?*]', '', title)

            async with aiofiles.open(temp_file_path, "rb") as f:
                audio_data = await f.read()
                audio_buffer = io.BytesIO(audio_data)
                audio_buffer.seek(0)
                file = File(fp=audio_buffer, filename=f"{sanitized_title}.{file_extension}")

                if stats.lower() == "yes":
                    def format_number(num):
                        if num >= 1_000_000:
                            return f"{num/1_000_000:.1f}M"
                        elif num >= 1_000:
                            return f"{num/1_000:.1f}k"
                        return str(num)
                    desc = f"-# By [**{artist}**]({artist_url})\n-# Duration: **`{durationf}`**" if durationf else ""
                    track_url = info.get('webpage_url', query)
                    embed = Embed(title=title, description=desc, url=track_url, color=self.bot.color)
                    embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)
                    embed.set_footer(text=f"❤️ {format_number(likes)} • 👁️ {format_number(plays)} • 🔄 {format_number(reposts)} | {fdate}", icon_url="https://git.cursi.ng/soundcloud_logo.png?")
                    embed.set_thumbnail(url=track_cover)
                    await interaction.followup.send(file=file, embed=embed)
                else:
                    await interaction.followup.send(file=file)

        except Exception as e:
            await self.bot.send_followup(interaction, content=f"oops {e}")

        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    await aiofiles.os.remove(temp_file_path)
                except Exception:
                    pass

    @music.autocomplete("query")
    async def music_autocomplete(self, interaction: Interaction, current: str):
        if not current:
            return []

        try:
            ydl_opts = {
                'extractor_args': {'soundcloud': {'client_id': 'f1TFyuaI8LX1Ybd1zvQRX8GpsNYcQ3Y5'}},
                'quiet': True,
                'no_warnings': True,
                'simulate': True,
                'skip_download': True,
                'extract_flat': True,
                'limit': 5,
                'default_search': 'scsearch',
            }

            def search():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(f"scsearch5:{current}", download=False)

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, search)
            suggestions = []
            for entry in results.get('entries', []):
                if not entry or '/sets/' in entry.get('url', '') or '?set=' in entry.get('url', ''):
                    continue
                title = entry.get('title', 'Unknown Track')[:50]
                artist = entry.get('uploader', 'Unknown Artist')[:40]
                url = entry.get('webpage_url', '')[:100]
                if title and artist and url:
                    suggestions.append(app_commands.Choice(name=f"{title} - {artist}", value=url))
                if len(suggestions) >= 5:
                    break
            return suggestions
        except Exception:
            return []

    def country_name_to_flag(self, country_name: str) -> str:
        try:
            country = pycountry.countries.lookup(country_name)
            code = country.alpha_2.upper()
            return chr(ord(code[0]) + 127397) + chr(ord(code[1]) + 127397)
        except LookupError:
            return ""

    @lookup.command(name="tiktok2country", description="tiktok user 2 country")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_whitelisted)
    async def tiktok2country(self, interaction: Interaction, username: str):
        await interaction.response.defer()
        redis_key = f"tiktok2country:{username.lower()}"

        cached = await self.bot.redis.get(redis_key)
        if cached:
            cached_data = await asyncio.to_thread(jason.loads, cached)
            expire_ts = int(await self.bot.redis.ttl(redis_key)) or 0
            minutes, seconds = divmod(expire_ts, 60)
            timer_str = f"{minutes}m{seconds}s" if minutes else f"{seconds}s"
            flag_emoji = self.country_name_to_flag(cached_data['country'])
            language_name = cached_data.get('language', None)
            language = f"language: {language_name} • " if language_name else ""

            embed = Embed(
                description=f"[**{cached_data['username']}**]({cached_data['profile_url']})'s TikTok is in **{cached_data['country']} {flag_emoji}**",
                color=self.bot.color
            )
            embed.set_footer(text=f"{language}served from cache (expires in {timer_str})")
            return await self.bot.send_followup(interaction, embed=embed)

        async with self.session.get(f"http://127.0.0.1:8073/v1/search/tiktok/{username}") as resp:
            if resp.status != 200:
                return await self.bot.send_followup(interaction, content=f"oops could not fetch user {username}")

            try:
                data = await resp.json()
            except jason.JSONDecodeError:
                return await self.bot.send_followup(interaction, content=f"oops API returned invalid response for {username}")

            profile = {
                "Username": data.get("username"),
                "Country": data.get("region", "Unknown"),
                "Language": data.get("language", None)
            }

            country_name = profile.get('Country', 'Unknown')
            language_name = profile.get('Language', None)
            flag_emoji = self.country_name_to_flag(country_name)
            language = f"language: {language_name} • " if language_name else ""

            embed = Embed(
                description=f"[**{profile['Username']}**](https://www.tiktok.com/{profile['Username']})'s TikTok is in **{country_name} {flag_emoji}**",
                color=self.bot.color
            )

            await self.bot.redis.set(
                redis_key,
                jason.dumps({
                    "username": profile['Username'],
                    "profile_url": f"https://www.tiktok.com/{profile['Username']}",
                    "country": country_name,
                    "language": language_name
                }),
                ex=120
            )

            embed.set_footer(text=f"{language}cached for 2 mins")
            await self.bot.send_followup(interaction, embed=embed)

    async def dtr_hit_redis(self, identifier: Union[int, str]):
        if isinstance(identifier, int):
            key = f"dtr:{identifier}"
        else:
            key = f"r2d:{identifier}"
        
        cached_data = await self.bot.redis.get(key)
        if cached_data:
            cached_data = cached_data.decode()
            parts = cached_data.split(":")
            if isinstance(identifier, int):
                return parts[0], parts[1], ":".join(parts[2:])
            else:
                return parts[0], parts[1], ":".join(parts[2:])
        return None, None, None

    async def get_last_seen(self, user_id):
        try:
            key = f'last_seen_users:{user_id}'
            last_seen_str = await self.bot.redis.get(key)
            if last_seen_str:
                return await asyncio.to_thread(jason.loads, last_seen_str)
            return None
        except Exception as e:
            print(f"Error retrieving last seen for user {user_id}: {e}")
            return None

    async def get_last_seen_info(self, user):
        try:
            result_parts = []

            last_seen_data = await self.get_last_seen(user.id)
            if last_seen_data:
                guild_name = last_seen_data['guild_name']
                timestamp = int(last_seen_data['timestamp'])
                time_str = f"<t:{timestamp}:R>"
                result_parts.append(f"-# <:channel:1418734286370111568> Recently seen in **{guild_name}** {time_str}")

            vc_key = f'vc_state:{user.id}'
            vc_data_str = await self.bot.redis.get(vc_key)
            if vc_data_str:
                vc_data = await asyncio.to_thread(jason.loads, vc_data_str)
                guild_name = vc_data.get('guild_name', 'Unknown Guild')
                channel_name = vc_data.get('channel_name', 'Unknown Channel')
                guild_id = vc_data.get('guild_id')
                channel_id = vc_data.get('channel_id')

                if not channel_id:
                    await self.bot.redis.delete(vc_key)
                    return "\n".join(result_parts)

                voice_state_emojis = []
                if vc_data.get('mute'):
                    pass
                elif vc_data.get('self_mute'):
                    pass
                if vc_data.get('deaf'):
                    pass
                elif vc_data.get('self_deaf'):
                    pass

                if channel_name == "Unknown Channel":
                    result_parts.append(
                        f"-# {' '.join(voice_state_emojis)} Connected to [a VC](https://discord.com/channels/{guild_id}/{channel_id}) in **{guild_name}**"
                    )
                else:
                    result_parts.append(
                        f"-# {' '.join(voice_state_emojis)} Connected to [{channel_name}](https://discord.com/channels/{guild_id}/{channel_id}) in **{guild_name}**"
                    )

            return "\n".join(result_parts)

        except Exception as e:
            print(f"Error processing last seen info: {e}")
            return ""

    @discordg.command(name="user", description="get info about a discord user")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_whitelisted)
    async def discorduser(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        await interaction.response.defer()
        await self._lookup_user(interaction, user or interaction.user)

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_whitelisted)
    async def discorduser_context(self, interaction: discord.Interaction, target: discord.User):
        await self._lookup_user(interaction, target)

    async def _lookup_user(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer()
        
        in_db = await self.check_user_in_heist_db(user.id)
        in_db_emoji = "<:check:1418728100979671150>" if in_db else "<:x_:1418728109523337338>"

        has_message_logs = False
        try:
            async with self.session.get(f"http://127.0.0.1:8002/messages/exists/{user.id}", timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    has_message_logs = data.get("exists", False)
        except:
            pass
        message_logs_emoji = "<:check:1418728100979671150>" if has_message_logs else "<:x_:1418728109523337338>"

        user_bio = ""
        mutual_server_names = []
        try:
            async with self.session.get(f"http://127.0.0.1:8002/users/{user.id}", timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and "user" in data and "bio" in data["user"]:
                        user_bio = data["user"]["bio"].replace("`", "")
                    if "mutual_guilds" in data:
                        for guild in data["mutual_guilds"]:
                            guild_id = guild["id"]
                            nick = guild.get("nick")
                            try:
                                async with self.session.get(f"http://127.0.0.1:8002/guilds/{guild_id}", timeout=5) as g_resp:
                                    if g_resp.status == 200:
                                        g_data = await g_resp.json()
                                        name = g_data.get("name")
                                        vanity = g_data.get("vanity_url")
                                        if name and vanity:
                                            if nick:
                                                mutual_server_names.append(f"[**`{name}`**](https://discord.gg/{vanity}) (nick: **{nick}**)")
                                            else:
                                                mutual_server_names.append(f"[**`{name}`**](https://discord.gg/{vanity})")
                            except:
                                pass
        except:
            pass

        last_seen_info = await self.get_last_seen_info(user)

        roblox_info = ""
        try:
            roblox_id, roblox_name, _ = await self.dtr_hit_redis(str(user.id))
            if roblox_name and roblox_id:
                roblox_info = f"\n-# <:roblox:1418734448517840926> [**{roblox_name}**](https://roblox.com/users/{roblox_id}/profile)"
        except:
            pass

        embed = Embed(color=self.bot.color)
        embed.set_author(name=f"{user.display_name} (@{user.name})", icon_url=user.display_avatar.url)

        description = ""
        if user.id in OWNER: 
            description += "<:staff:1418736081175580803> [**`Hysteria Owner`**](https://discord.com/oauth2/authorize?client_id=1415512129867612375), [**`Heist Owner`**](https://discord.com/oauth2/authorize?client_id=1225070865935368265)\n"
        if last_seen_info:
            description += last_seen_info + "\n"
        if user_bio:
            description += f"{user_bio}\n"
        description += f"\n**Is in Heist database: {in_db_emoji}**\n"
        description += f"**Message logs: {message_logs_emoji}**"
        if roblox_info:
            description += roblox_info
        if mutual_server_names:
            server_list = " • ".join(f"{name}" for name in mutual_server_names)
            description += f"\n\n{server_list}\n-# Full list: </lookup discord guilds:1418669819275776153>"
        
        embed.description = description
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"{user.id}", icon_url="https://git.cursi.ng/discord_logo.png")

        await interaction.followup.send(embed=embed)

    async def check_user_in_heist_db(self, user_id: int) -> bool:
        try:
            conn = await asyncpg.connect(HEISTDATABASE_URL)
            result = await conn.fetchrow("SELECT 1 FROM user_data WHERE user_id = $1", str(user_id))
            await conn.close()
            return result is not None
        except Exception as e:
            print(f"Error checking user: {e}")
            return False

    @discordg.command(name="messages", description="messages of a discord user")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_whitelisted)
    async def discordmessages(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        await interaction.response.defer(thinking=True)
        await self._lookup_messages(interaction, user or interaction.user)

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_whitelisted)
    async def discordmessages_context(self, interaction: discord.Interaction, target: discord.User):
        await interaction.response.defer(thinking=True)
        await self._lookup_messages(interaction, target)

    async def _lookup_messages(self, interaction: discord.Interaction, user: discord.User):
        if user.id in OWNER:
            await interaction.followup.send("ummm actually that's a breach of cosmin's privacy and we should respect that.")
            return
        try:
            target_user = await interaction.client.fetch_user(user.id)
            messages_url = f"http://127.0.0.1:8002/messages?user_id={user.id}"
            async with self.session.get(messages_url) as resp:
                if resp.status != 200:
                    await interaction.followup.send("Failed to fetch messages.")
                    return

                messages = await resp.json()
                if not messages:
                    await interaction.followup.send("No messages found for this user.")
                    return

                paginator = MessagePaginatorView(
                    author_id=interaction.user.id,
                    messages=messages,
                    user=target_user,
                    embed_color=self.bot.color
                )
                paginator.format_callback = format_messages_page
                
                embed = paginator.create_embed()
                await interaction.followup.send(embed=embed, view=paginator)

        except Exception as e:
            print("error in discordmessages", e)
            await interaction.followup.send("An error occurred while fetching messages.")

    async def _lookup_guilds(self, interaction: discord.Interaction, user: discord.User):
        if user.id in OWNER:
            await interaction.response.send_message("ummm actually that's a breach of cosmin's privacy and we should respect that.")
            return
        
        await interaction.response.defer(thinking=True)
        
        try:
            target_user = await interaction.client.fetch_user(user.id)
            guilds_url = f"http://127.0.0.1:8002/mutualguilds/{user.id}"
            async with self.session.get(guilds_url) as resp:
                if resp.status == 200:
                    guilds_info = await resp.json()
                    if guilds_info:
                        paginator = GuildPaginatorView(
                            author_id=interaction.user.id,
                            guilds=guilds_info,
                            user=target_user,
                            embed_color=self.bot.color
                        )
                        paginator.format_callback = format_guilds_page
                        
                        embed = paginator.create_embed()
                        await interaction.followup.send(embed=embed, view=paginator)
                    else:
                        await interaction.followup.send("No guilds found for this user.")
                else:
                    await interaction.followup.send("Failed to fetch guilds.")
        except Exception as e:
            print("error in discordguilds", e)
            await interaction.followup.send("An error occurred while fetching guilds.")

    @discordg.command(name="guilds", description="guilds of a discord user")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_whitelisted)
    async def discordguilds(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        user = user or interaction.user
        await self._lookup_guilds(interaction, user)

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_whitelisted)
    async def discordguilds_context(self, interaction: discord.Interaction, target: discord.User):
        await self._lookup_guilds(interaction, target)

    async def try_navyai(self, prompt: str, model: str = "gpt-4o-search-preview"):
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {NAVY_KEY}"
            }
            data = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}]
            }
            async with self.session.post(
                "https://api.navy/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            ) as response:
                if response.status != 200:
                    return None
                result = await response.json()
                return result.get('choices', [{}])[0].get('message', {}).get('content')
        except:
            return None

    async def try_pollinations(self, prompt: str, model: str = "openai"):
        try:
            encoded_prompt = urllib.parse.quote(prompt)
            url = f"https://text.pollinations.ai/{encoded_prompt}?model={model}"
            async with self.session.get(url, timeout=30) as response:
                if response.status != 200:
                    return None
                return await response.text()
        except:
            return None

    @app_commands.command(name="chatgpt", description="talk 2 chatgpt")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_whitelisted)
    async def chatgpt(self, interaction: Interaction, prompt: str):
        await interaction.response.defer()
        try:
            ai_response = await self.try_navyai(prompt)
            if ai_response is None:
                ai_response = await self.try_pollinations(prompt)

            if ai_response is None:
                await interaction.followup.send("The AI model is **unresponsive** at the moment, please try using our other models.")
                return

            if len(prompt) > 40:
                tprompt = prompt[:40] + ".."
            else:
                tprompt = prompt

            full_message = f"{ai_response}"

            url_pattern = r"(https?://[^\s]+)"
            full_message = re.sub(url_pattern, r"<\1>", full_message)

            if len(full_message) > 4000:
                full_message = full_message[:3997] + "..."
        except Exception as e:
            print(e)

        await interaction.followup.send(full_message)

async def setup(bot):
    await bot.add_cog(Utility(bot))