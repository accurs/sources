import discord
import time
import random
import aiohttp
import asyncio
import aiofiles, aiofiles.os
import io
import os
from io import BytesIO
from discord import app_commands, File, Embed, Interaction
from discord.ui import Button, View, Modal, TextInput, Select
from discord.ext import commands
from discord.ext.commands import Cog, hybrid_command, hybrid_group
from typing import Literal, List, Union, Optional
import base64
import secrets
import datetime
from datetime import datetime, timedelta
import yt_dlp
from pilmoji import Pilmoji
import regex as re
import math, ast, operator, decimal
from decimal import Decimal
from functools import partial
import unicodedata
import pyfiglet
import urllib.parse
from urllib.parse import quote, urlparse
from PIL import Image, ImageDraw, ImageFont, ImageSequence
from shazamio import Shazam
import ssl
from heist.framework.discord.decorators import check_donor, check_famous, check_owner, check_blacklisted, donor_only
from heist.framework.tools.separator import makeseparator
from heist.framework.tools.titles import get_title
from heist.framework.pagination import Paginator
from heist.framework.discord import CommandCache
import ujson as json
from pyzbar.pyzbar import decode
import qrcode
import cv2
from pydub import AudioSegment
import numpy as np
from deep_translator import GoogleTranslator
from deep_translator.constants import GOOGLE_LANGUAGES_TO_CODES as GLC
from langdetect import detect
import pytz
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from heist.framework.discord.cv2 import cv2 as cpv2

NAVY_KEY = os.getenv("NAVY_API_KEY")
BYPASSVIP_KEY = os.getenv("BYPASSVIP_API_KEY")
ROBLOX_COOKIE = os.getenv("ROBLOX_COOKIE")
PROXY = os.getenv("PROXY")
PROXY_URL = f"http://{PROXY}"

def ListedFonts():
    fonts = []
    for file in os.listdir('heist/fonts/'):
        if (file.endswith('.ttf') or (file.endswith('.otf')) and 'futura' not in file.lower()):
            fonts.append(file)
    return fonts

class Buttons(discord.ui.View):
    EMOJIS = {
        "color": "<:color:1316896978931683408>",
        "contrast": "<:contrast:1316896854956314755>",
        "flip": "<:flip:1316896847096315954>",
        "gif": "<:gif:1325499192097116201>",
        "new": "<:new:1316896960917016607>",
        "blur": "<:blur:1316897646480461885>",
        "brightness": "<:brightness:1316897642114187324>",
        "pixelate": "<:pixel:1316897638620336148>",
        "solarize": "<:solarize:1316896942382387231>",
        "remove": "<:trash:1316896912372400201>"
    }

    def __init__(self, ctx, author):
        super().__init__(timeout=240)
        self.interaction = ctx
        self.author = author
        self.lock = asyncio.Lock()
        self.font = 'M PLUS Rounded 1c (mplus).ttf'
        self.is_gif = False
        self.color_active = False
        self.contrast_active = False
        self.flip_active = False
        self.new_active = False
        self.blur_active = False
        self.brightness_active = False
        self.pixelate_active = False
        self.solarize_active = False
        self._update_font_select()

    def _update_font_select(self):
        self.select_font.options = [
            discord.SelectOption(
                label=font,
                value=font,
                emoji="<:blarrow:1341204214273146902>" if font == self.font else None,
                default=font == self.font
            )
            for font in ListedFonts()
        ]

    async def authorCheck(self, interaction):
        if self.author != interaction.user:
            await interaction.response.send_message(f"Only {self.author.mention} can use this button.", ephemeral=True)
            return False
        return True

    async def UpdateImage(self, interaction):
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    'avatar_url': str(self.message.author.display_avatar.url),
                    'content': self.message.clean_content,
                    'display_name': self.message.author.display_name,
                    'username': self.message.author.name,
                    'font': self.font,
                    'color': 'white' if self.color_active else 'black',
                    'contrast': self.contrast_active,
                    'flip': self.flip_active,
                    'new': self.new_active,
                    'blur': self.blur_active,
                    'brightness': self.brightness_active,
                    'pixelate': self.pixelate_active,
                    'solarize': self.solarize_active,
                    'gif': self.is_gif
                }
                async with session.post('http://localhost:3636/quote', json=data) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()
                        filename = 'quote.gif' if self.is_gif else 'quote.png'
                        file = discord.File(io.BytesIO(image_data), filename=filename)
                        if interaction.response.is_done():
                            await interaction.edit_original_response(attachments=[file], view=self)
                        else:
                            await interaction.response.edit_message(attachments=[file], view=self)
                    else:
                        await interaction.followup.send("Failed to generate quote", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            await self.interaction.edit_original_response(view=self)
        except:
            pass

    @discord.ui.select(placeholder="Select a font...", options=[])
    async def select_font(self, interaction, select):
        if not await self.authorCheck(interaction):
            return
        self.font = select.values[0]
        self._update_font_select()
        await self.UpdateImage(interaction)

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji=EMOJIS["color"])
    async def color(self, interaction, button):
        if not await self.authorCheck(interaction):
            return
        self.color_active = not self.color_active
        button.style = discord.ButtonStyle.blurple if self.color_active else discord.ButtonStyle.grey
        await self.UpdateImage(interaction)

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji=EMOJIS["contrast"])
    async def contrast(self, interaction, button):
        if not await self.authorCheck(interaction):
            return
        self.contrast_active = not self.contrast_active
        button.style = discord.ButtonStyle.blurple if self.contrast_active else discord.ButtonStyle.grey
        await self.UpdateImage(interaction)

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji=EMOJIS["flip"])
    async def flip(self, interaction, button):
        if not await self.authorCheck(interaction):
            return
        self.flip_active = not self.flip_active
        button.style = discord.ButtonStyle.blurple if self.flip_active else discord.ButtonStyle.grey
        await self.UpdateImage(interaction)

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji=EMOJIS["gif"])
    async def gif(self, interaction, button):
        if not await self.authorCheck(interaction):
            return
        self.is_gif = not self.is_gif
        button.style = discord.ButtonStyle.blurple if self.is_gif else discord.ButtonStyle.grey
        await self.UpdateImage(interaction)

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji=EMOJIS["new"])
    async def new(self, interaction, button):
        if not await self.authorCheck(interaction):
            return
        self.new_active = not self.new_active
        button.style = discord.ButtonStyle.blurple if self.new_active else discord.ButtonStyle.grey
        await self.UpdateImage(interaction)

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji=EMOJIS["blur"])
    async def blur(self, interaction, button):
        if not await self.authorCheck(interaction):
            return
        self.blur_active = not self.blur_active
        button.style = discord.ButtonStyle.blurple if self.blur_active else discord.ButtonStyle.grey
        await self.UpdateImage(interaction)

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji=EMOJIS["brightness"])
    async def brightness(self, interaction, button):
        if not await self.authorCheck(interaction):
            return
        self.brightness_active = not self.brightness_active
        button.style = discord.ButtonStyle.blurple if self.brightness_active else discord.ButtonStyle.grey
        await self.UpdateImage(interaction)

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji=EMOJIS["pixelate"])
    async def pixelate(self, interaction, button):
        if not await self.authorCheck(interaction):
            return
        self.pixelate_active = not self.pixelate_active
        button.style = discord.ButtonStyle.blurple if self.pixelate_active else discord.ButtonStyle.grey
        await self.UpdateImage(interaction)

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji=EMOJIS["solarize"])
    async def solarize(self, interaction, button):
        if not await self.authorCheck(interaction):
            return
        self.solarize_active = not self.solarize_active
        button.style = discord.ButtonStyle.blurple if self.solarize_active else discord.ButtonStyle.grey
        await self.UpdateImage(interaction)

    @discord.ui.button(emoji=EMOJIS["remove"], style=discord.ButtonStyle.grey)
    async def remove_quote(self, interaction, button):
        if not await self.authorCheck(interaction):
            return
        async with self.lock:
            await interaction.response.defer()
            await interaction.delete_original_response()

class Utility(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.LASTFM_KEY = os.getenv('LASTFM_API_KEY')
        self.lock = asyncio.Lock()
        self.rolock = asyncio.Lock()
        self.ROBLOX_COOKIE = ROBLOX_COOKIE
        self.last_req_time = 0
        self.rl_retries = 4
        self.rl_delay = 0.6
        self.proxy_until = 0
        self.proxy_url = f"http://{PROXY}"
        self.badge_emojis = {
            "hypesquad_house_1": "<:hypesquad_bravery:1263855923806470144>",
            "hypesquad_house_2": "<:hypesquad_brilliance:1263855913480097822>",
            "hypesquad_house_3": "<:hypesquad_balance:1263855909420138616>",
            "premium": "<:nitro:1263855900846981232>",
            "premium_type_1": "<:bronzen:1293983425828753480>",
            "premium_type_2": "<:silvern:1293983951983083623>",
            "premium_type_3": "<:goldn:1293983938485686475>",
            "premium_type_4": "<:platinumn:1293983921469526137>",
            "premium_type_5": "<:diamondn:1293983900435091566>",
            "premium_type_6": "<:emeraldn:1293983816259731527>",
            "premium_type_7": "<:rubyn:1293983910342164655>",
            "premium_type_8": "<:firen:1293983849264582666>",
            "guild_booster_lvl1": "<:boosts1:1263857045027819560>",
            "guild_booster_lvl2": "<:boosts2:1263857025658388613>",
            "guild_booster_lvl3": "<:boosts:1263856979911245897>",
            "guild_booster_lvl4": "<:boosts4:1263856929835450469>",
            "guild_booster_lvl5": "<:boosts5:1263856884708937739>",
            "guild_booster_lvl6": "<:boosts6:1263856802638860370>",
            "guild_booster_lvl7": "<:boosts7:1263856551555502211>",
            "guild_booster_lvl8": "<:boosts8:1263856534216114298>",
            "guild_booster_lvl9": "<:boosts9:1263856512506400871>",
            "early_supporter": "<:early_supporter:1265425918843814010>",
            "verified_developer": "<:earlybotdev:1265426039509749851>",
            "active_developer": "<:activedeveloper:1265426222444183645>",
            "hypesquad": "<:hypesquad_events:1265426613605240863>",
            "bug_hunter_level_1": "<:bughunter_1:1265426779523252285>",
            "bug_hunter_level_2": "<:bughunter_2:1265426786607562893>",
            "staff": "<:staff:1265426958322241596>",
            "partner": "<:partner:1265426965511536792>",
            "bot_commands": "<:supports_commands:1265427168469712908>",
            "legacy_username": "<:pomelo:1265427449999659061>",
            "quest_completed": "<:quest:1265427335058948247>",
            "bot": "<:bot:1290389425850679388>",
            "heist": "<:heistlogo:1311093037539004557>"
        }
        self.ctx_discorduser = app_commands.ContextMenu(
            name='View Profile',
            callback=self.discorduser_context,
        )
        self.ctx_quote = app_commands.ContextMenu(
            name='Quote Message',
            callback=self.quotemessage_context,
        )
        self.ctx_toimage = app_commands.ContextMenu(
            name='Get Sticker/Emoji',
            callback=self.toimage,
        )
        self.ctx_shazam = app_commands.ContextMenu(
            name='Shazam This',
            callback=self.shazam_context,
        )
        self.ctx_transcribe = app_commands.ContextMenu(
            name='Transcribe VM',
            callback=self.transcribevm,
        )
        self.ctx_translate = app_commands.ContextMenu(
            name='Translate to English',
            callback=self.toenglish,
        )
        self.bot.tree.add_command(self.ctx_discorduser)
        self.bot.tree.add_command(self.ctx_shazam)
        self.bot.tree.add_command(self.ctx_quote)
        self.bot.tree.add_command(self.ctx_toimage)
        self.bot.tree.add_command(self.ctx_transcribe)
        self.bot.tree.add_command(self.ctx_translate)

    discordg = app_commands.Group(
        name="discord", 
        description="Discord related commands",
        allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True),
        allowed_installs=app_commands.AppInstallationType(guild=True, user=True)
   )

    tags = app_commands.Group(
        name="tags", 
        description="Tags related commands",
        allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True),
        allowed_installs=app_commands.AppInstallationType(guild=True, user=True)
    )

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def roblox_rl(self):
        async with self.rolock:
            current_time = asyncio.get_event_loop().time()
            time_since_last = current_time - self.last_req_time
            if time_since_last < self.rl_delay:
                await asyncio.sleep(self.rl_delay - time_since_last)
            self.last_req_time = asyncio.get_event_loop().time()

    async def roblox_request(self, method, url, **kwargs):
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 OPR/107.0.0.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        user_headers = kwargs.pop('headers', {})
        headers = {**default_headers, **user_headers}

        cookie_value = getattr(self, 'ROBLOX_COOKIE', None)
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

    async def get_last_seen(self, user_id):
        try:
            key = f'last_seen_users:{user_id}'
            last_seen_raw = await self.bot.redis.get(key)
            if not last_seen_raw:
                return None

            if isinstance(last_seen_raw, (bytes, bytearray, memoryview)):
                last_seen_raw = last_seen_raw.decode("utf-8")
            elif isinstance(last_seen_raw, dict):
                return last_seen_raw
            elif not isinstance(last_seen_raw, str):
                last_seen_raw = str(last_seen_raw)

            return await asyncio.to_thread(json.loads, last_seen_raw)

        except Exception as e:
            print(f"Error retrieving last seen for user {user_id}: {e}", flush=True)
            return None

    async def get_last_seen_info(self, user, limited):
        try:
            async with self.bot.pool.acquire() as conn:
                result = ""

                if limited:
                    return {}

                last_seen_data = await self.get_last_seen(user.id)
                print(last_seen_data)
                if last_seen_data:
                    guild_name = last_seen_data['guild_name']
                    channel_name = last_seen_data['channel_name']
                    timestamp = int(last_seen_data['timestamp'])
                    time_str = f"<t:{timestamp}:R>"

                    guild_activity_row = await conn.fetchrow(
                        "SELECT guild_activity FROM preferences WHERE user_id = $1",
                        user.id
                    )

                    if guild_activity_row is None:
                        guild_activity = True
                    else:
                        guild_activity = guild_activity_row['guild_activity']

                    if guild_activity:
                        result += f"\n-# <:channel:1319456081528885359> Recently seen in **{guild_name}** {time_str}"

                vc_key = f'vc_state:{user.id}'
                vc_data_str = await self.bot.redis.get(vc_key)
                if vc_data_str:
                    vc_data = await asyncio.to_thread(json.loads, vc_data_str)
                    guild_name = vc_data.get('guild_name', 'Unknown Guild')
                    channel_name = vc_data.get('channel_name', 'Unknown Channel')
                    guild_id = vc_data.get('guild_id', None)
                    channel_id = vc_data.get('channel_id', None)

                    if not channel_id:
                        await self.bot.redis.delete(vc_key)
                        return ""

                    voice_state_emojis = []
                    if vc_data.get('mute'):
                        voice_state_emojis.append("<:server_mute:1319357944332030043>")
                    elif vc_data.get('self_mute'):
                        voice_state_emojis.append("<:self_mute:1318966624816074782>")

                    if vc_data.get('deaf'):
                        voice_state_emojis.append("<:server_deaf:1319357938074128504>")
                    elif vc_data.get('self_deaf'):
                        voice_state_emojis.append("<:self_deafen:1318966630629511239>")

                    if channel_name == "Unknown Channel":
                        result += f"\n-# <:self_voice:1318730750685741076> {' '.join(voice_state_emojis)} Connected to [a VC](https://discord.com/channels/{guild_id}/{channel_id}) in **{guild_name}**"
                    else:
                        result += f"\n-# <:self_voice:1318730750685741076> {' '.join(voice_state_emojis)} Connected to [{channel_name}](https://discord.com/channels/{guild_id}/{channel_id}) in **{guild_name}**"

                return result

        except Exception as e:
            print(f"Error processing last seen info: {e}", flush=True)
            return ""

    @hybrid_group(name="ai", description="AI utilities")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def aitools(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    custom = app_commands.Group(
        name="custom",
        description="Custom stuff",
        allowed_installs=app_commands.AppInstallationType(guild=True, user=True),
        allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True)
    )

    customai = app_commands.Group(
        name="ai",
        description="Build a custom AI chat-bot",
        parent=custom 
    )

    @aitools.command(name="geolocate", description="Use AI to geolocate an image")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(image="The image to geolocate")
    async def geolocate(self, ctx: commands.Context, image: discord.Attachment):
        if not image.content_type.startswith('image/'):
            await ctx.warn("Only image files are allowed.")
            return

        loading_embed = discord.Embed(
            description=f"-# <a:dotsload:1423056880854499338> {ctx.author.mention}: thinking.. (10-15 seconds)",
            color=await self.bot.get_color(ctx.author.id)
        )
        message = await ctx.send(embed=loading_embed)

        try:
            async with self.session.get(image.url) as resp:
                if resp.status != 200:
                    await ctx.edit_warn("Failed to download image.", message)
                    return
                image_data = await resp.read()

            form_data = aiohttp.FormData()
            form_data.add_field('file', image_data, filename='image.png', content_type='image/png')
            async with self.session.post('http://127.0.0.1:8889/locate', data=form_data) as api_resp:
                if api_resp.status != 200:
                    await ctx.edit_warn("Could not locate image.", message)
                    return
                result = await api_resp.json()

            location = result.get("result", "Unknown location")
            confidence = result.get("confidence")

            if confidence:
                response_text = f"the image was taken in **{location}**. ({confidence} confidence)"
            else:
                response_text = f"the image was taken in **{location}**."
            response_text = response_text + "\n-# This feature is powered by AI and **may not** always be accurate."

            await message.edit(content=response_text, embed=None)

        except Exception as e:
            await ctx.edit_warn(str(e), message)

    @aitools.command(name="deepgeolocate", description="✨ Use AI to geolocate & deeply analyze an image")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(image="The image to geolocate")
    @donor_only()
    async def deepgeolocate(self, ctx: commands.Context, image: discord.Attachment):
        MAX_SIZE = 5 * 1024 * 1024
        if not image.content_type.startswith('image/'):
            await ctx.warn("Only image files are allowed.")
            return

        loading_embed = discord.Embed(
            description=f"-# <a:dotsload:1423056880854499338> {ctx.author.mention}: thinking.. (5-10 seconds)",
            color=await self.bot.get_color(ctx.author.id)
        )
        message = await ctx.send(embed=loading_embed)

        try:
            async with self.session.get(image.url) as resp:
                if resp.status != 200:
                    await ctx.edit_warn("Failed to download image.", message)
                    return
                image_data = await resp.read()

            if len(image_data) > MAX_SIZE:
                await ctx.edit_warn("Image size exceeds the **5 MB** limit. Please upload a smaller image.", message)
                return

            base64_image = await asyncio.to_thread(base64.b64encode, image_data)
            base64_image = base64_image.decode("utf-8")

            system_prompt = """Geolocate locations.
            format:
            {
            "possibleLocations": [
                {
                "location": "Primary location",
                "confidence": 85,
                "reasoning": "Brief explanation with maybe coordinates"
                },
                {
                "location": "Secondary location guess",
                "confidence": 45,
                "reasoning": "Alternative explanation"
                }
            ],
            "generalRegion": "Broader area"
            }"""

            headers = {
                "Authorization": f"Bearer {NAVY_KEY}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": "gemini-2.5-flash-thinking",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Analyze"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    }
                ],
                "max_tokens": 4096,
                "temperature": 0.2
            }

            async with self.session.post("https://api.navy/v1/chat/completions", headers=headers, json=payload) as api_resp:
                if api_resp.status == 413:
                    await ctx.edit_warn("Image size exceeds the **5 MB** limit. Please upload a smaller image.", message)
                    return
                if api_resp.status != 200:
                    try:
                        error_data = await api_resp.text()
                    except Exception:
                        error_data = "Failed to read error response"
                    await ctx.edit_warn("AI service failed to analyze the image.", message)
                    return
                result = await api_resp.json()

            raw_response = result["choices"][0]["message"]["content"]
            ai_response = raw_response.strip("` \n")

            if ai_response.lower().startswith("json"):
                ai_response = ai_response[ai_response.lower().index("{"):]

            try:
                parsed_data = await asyncio.to_thread(json.loads, ai_response)
            except:
                parsed_data = {
                    "possibleLocations": [{
                        "location": "Unknown",
                        "confidence": 0,
                        "reasoning": "Could not determine location"
                    }],
                    "generalRegion": "Unknown"
                }

            color = await self.bot.get_color(ctx.author.id)
            embed = discord.Embed(title="Image Geolocation Analysis", color=color)
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
            embed.set_thumbnail(url=image.url)

            region = parsed_data.get("generalRegion", "")
            description = f"**General region:** {region}" if region else ""
            description += "\n-# This feature is powered by AI and **may not** always be accurate."
            embed.description = description

            for idx, loc in enumerate(parsed_data.get("possibleLocations", [])[:3]):
                embed.add_field(
                    name=f"{idx + 1}. {loc.get('location', 'Unknown')} ({loc.get('confidence', 0)}% confidence)",
                    value=loc.get('reasoning', 'No reasoning provided'),
                    inline=False
                )

            await message.edit(embed=embed)

        except Exception as e:
            await ctx.edit_warn(str(e), message)

    @aitools.command(name="tts", description="✨ Convert text to audio using AI")
    @app_commands.choices(voice=[
        app_commands.Choice(name="Alloy", value="alloy"),
        app_commands.Choice(name="Echo", value="echo"),
        app_commands.Choice(name="Fable", value="fable"),
        app_commands.Choice(name="Onyx", value="onyx"),
        app_commands.Choice(name="Nova", value="nova"),
        app_commands.Choice(name="Shimmer", value="shimmer"),
    ])
    @app_commands.describe(
        text="Text to convert to speech",
        voice="Voice style to use",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @donor_only()
    async def aitts(self, ctx: commands.Context, *, text: str, voice: str = "alloy"):
        if not text:
            await ctx.warn("No text provided to convert to speech.")
            return

        if len(text) > 300:
            await ctx.warn("Text too long. Maximum 300 characters allowed.")
            return

        start_time = time.time()
        
        headers = {
            "Authorization": f"Bearer {NAVY_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "gpt-4o-mini-tts",
            "input": text,
            "voice": voice
        }
        
        try:
            async with self.session.post(
                "https://api.navy/v1/audio/speech",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    await ctx.warn("AI service failed to generate audio.")
                    return
                
                audio_data = await response.read()
                audio_buffer = BytesIO(audio_data)
                audio_buffer.seek(0)
                
                end_time = time.time()
                duration = end_time - start_time
                
                rnum = random.randint(100, 999)
                filename_mp3 = f"tts_{rnum}.mp3"
                filename_opus = f"tts_{rnum}.opus"
                
                embed = discord.Embed(
                    description=f"🔊 AI generated the audio in `{duration:.2f}s`.\n🗣️ Voice: **{voice}**",
                    color=await self.bot.get_color(ctx.author.id)
                )

                audio_buffer = io.BytesIO(audio_data)
                audio_buffer.seek(0)
                audio_file = discord.File(audio_buffer, filename_mp3)

                text_preview = (text[:297] + '...') if len(text) > 300 else text
                await ctx.send(f"Prompt: {text_preview}", file=audio_file, embed=embed)
                    
        except Exception as e:
            await ctx.warn(str(e))

    @aitools.command(name="llama", description="Ask LLaMA-3.1-8b-instant a question")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(prompt="The prompt for the AI")
    async def llama(self, ctx: commands.Context, *, prompt: str):
        loading_embed = discord.Embed(
            description=f"-# <a:dotsload:1423056880854499338> {ctx.author.mention}: thinking..",
            color=await self.bot.get_color(ctx.author.id)
        )
        message = await ctx.send(embed=loading_embed)

        for _ in range(3):
            try:
                headers = {
                    'Content-Type': 'application/json'
                }
                
                async with self.session.post(
                    'http://127.0.0.1:5094/chat',
                    json={'prompt': prompt, 'model': 'llama-3.1-8b-instant'},
                    headers=headers,
                    timeout=30
                ) as response:
                    if response.status != 200:
                        continue
                    
                    result = await response.json()
                    if result.get('status') == 'error':
                        continue
                        
                    ai_response = result['response']
                
                if len(prompt) > 40:
                    tprompt = prompt[:40] + ".."
                else:
                    tprompt = prompt

                prompt_message = f"* Prompt:\n```yaml\n{tprompt}```"
                full_message = f"{prompt_message}\n> **`Response ⬎`**\n{ai_response}"

                if len(full_message) > 4000:
                    full_message = full_message[:3997] + "..."
                
                embed = discord.Embed(description=f"{full_message}", color=await self.bot.get_color(ctx.author.id))
                embed.set_author(name="LLaMA Says", icon_url=ctx.author.display_avatar.url)
                embed.set_footer(text="heist.lol", icon_url="https://git.cursi.ng/heist.png?a")
                embed.set_thumbnail(url="https://git.cursi.ng/meta_logo.png")
                await message.edit(embed=embed)
                return
            except:
                continue
        
        await ctx.edit_warn("The AI model is **unresponsive** at the moment, please try using our other models.", message)

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

    @aitools.command(name="chatgpt", description="Ask ChatGPT a question (Internet access)")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(prompt="The prompt for the AI")
    async def chatgpt(self, ctx: commands.Context, *, prompt: str):
        loading_embed = discord.Embed(
            description=f"-# <a:dotsload:1423056880854499338> {ctx.author.mention}: thinking..",
            color=await self.bot.get_color(ctx.author.id)
        )
        message = await ctx.send(embed=loading_embed)
        try:
            ai_response = await self.try_navyai(prompt)
            if ai_response is None:
                ai_response = await self.try_pollinations(prompt)

            if ai_response is None:
                await ctx.edit_warn("The AI model is **unresponsive** at the moment, please try using our other models.", message)
                return

            if len(prompt) > 40:
                tprompt = prompt[:40] + ".."
            else:
                tprompt = prompt

            prompt_message = f"* Prompt:\n```yaml\n{tprompt}```"
            full_message = f"{prompt_message}\n> **`Response ⬎`**\n{ai_response}"

            if len(full_message) > 4000:
                full_message = full_message[:3997] + "..."
        except Exception as e:
            await ctx.edit_warn(str(e), message)
            return

        embed = discord.Embed(description=f"{full_message}", color=await self.bot.get_color(ctx.author.id))
        embed.set_author(name="ChatGPT Says", icon_url=ctx.author.display_avatar.url)
        embed.set_footer(text="heist.lol", icon_url="https://git.cursi.ng/heist.png?a")
        embed.set_thumbnail(url="https://git.cursi.ng/openai_logo.png")
        await message.edit(embed=embed)

    @aitools.command(name="imagine", description="✨ Generate an image based on the given prompt")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(prompt="The prompt to generate the image from", model="The model to use for image generation")
    @app_commands.choices(model=[
        app_commands.Choice(name="Flux (Quality)", value="flux"),
        app_commands.Choice(name="Turbo (Fastest)", value="turbo")
    ])
    @donor_only()
    async def imagine(self, ctx: commands.Context, *, prompt: str, model: str = "flux"):
        await ctx.defer()
        if not prompt.strip():
            await ctx.warn("Please provide a prompt to generate an image.")
            return
        start_time = time.time()

        try:
            image_data, footer = await self.flux_gen(prompt, model)

            buffer = io.BytesIO(image_data)
            
            end_time = time.time()
            duration = end_time - start_time
            embed = discord.Embed(description=f"**Prompt:**\n> {prompt}\n\nImage generated in `{duration:.2f}s`.", color=await self.bot.get_color(ctx.author.id))
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
            embed.set_footer(text="heist.lol", icon_url="https://git.cursi.ng/heist.png?a")

            await ctx.send(embed=embed, file=discord.File(buffer, filename="heist.jpg"))

        except Exception as e:
            await ctx.warn(str(e))

    async def flux_gen(self, prompt, model):
        api_url = f"https://image.pollinations.ai/prompt/{prompt}?model={model}&nologo=true"
        
        async def fetch_and_process_image(api_url, model):
            async with self.session.get(api_url) as resp:
                if resp.status == 200:
                    image_data = await resp.read()

                    def process_image(image_data, model):
                        with Image.open(io.BytesIO(image_data)) as img:
                            width, height = img.size

                            if model != "flux":
                                crop_amount = int(height * 0.03)
                                img = img.crop((0, 0, width, height - crop_amount))
                                offset = 40
                            else:
                                offset = 20

                            draw = ImageDraw.Draw(img)
                            font_path = "heist/fonts/futura.otf"
                            font = ImageFont.truetype(font_path, 30)
                            text = "heist.lol"

                            text_bbox = draw.textbbox((0, 0), text, font=font)
                            text_width = text_bbox[2] - text_bbox[0]
                            text_height = text_bbox[3] - text_bbox[1]

                            position = (width - text_width - 10, height - text_height - offset)
                            draw.text(position, text, font=font, fill=(255, 255, 255))

                            output_buffer = io.BytesIO()
                            img.save(output_buffer, format='JPEG')
                            output_buffer.seek(0)
                            return output_buffer.getvalue()

                    image_data = await asyncio.to_thread(process_image, image_data, model)
                    return image_data, f"heist.lol - {model.lower()}"
                else:
                    raise Exception(f"Please try again with another model or later.")
        
        try:
            return await fetch_and_process_image(api_url, model)
        except Exception as e:
            raise Exception(f"Failed to generate image: {e}")

    @customai.command()
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(prompt="The prompt for the AI")
    @donor_only()
    async def chat(self, interaction: discord.Interaction, prompt: str):
        """✨ Chat to your custom AI"""        
        try:
            await interaction.response.defer()
            settings = await self.get_ai_settings(interaction.user.id)
            if not settings:
                await interaction.followup.send(f"You need to build your AI first with </custom ai build:1402126672878112892>.", ephemeral=True)
                return

            model = settings['model']
            system_prompt = settings['system_prompt']
            thumbnail = settings.get('thumbnail')

            if not thumbnail:
                thumbnail = self.bot.user.display_avatar.url

            async def try_navyai():
                try:
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {NAVY_KEY}"
                    }
                    data = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ]
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

            ai_response = await try_navyai()
            if not ai_response:
                await interaction.followup.send("The AI model is **unresponsive** at the moment, please try again later.")
                return

            tprompt = prompt[:40] + ".." if len(prompt) > 40 else prompt
            prompt_message = f"* Prompt:\n```yaml\n{tprompt}```"
            full_message = f"{prompt_message}\n> **`Response ⬎`**\n{ai_response}"
            if len(full_message) > 4000:
                full_message = full_message[:3997] + "..."

            embed = discord.Embed(description=full_message, color=await self.bot.get_color(interaction.user.id))
            embed.set_author(name=f"{interaction.user.name}'s custom AI", icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else interaction.user.default_avatar.url)
            embed.set_footer(text=f"{model}", icon_url="https://git.cursi.ng/heist.png?a")
            embed.set_thumbnail(url=thumbnail)

            try:
                await interaction.followup.send(embed=embed)
            except discord.HTTPException as e:
                if e.code == 50035 and "embeds.0.thumbnail.url" in str(e):
                    default_thumb = self.bot.user.display_avatar.url
                    embed.set_thumbnail(url=default_thumb)
                    await interaction.followup.send(embed=embed)
                    async with self.bot.pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE ai_settings SET thumbnail = $2 WHERE user_id = $1",
                            interaction.user.id, None
                        )
                    await self.bot.redis.set(f"ai_settings:{interaction.user.id}", json.dumps({
                        "model": model,
                        "system_prompt": system_prompt,
                        "thumbnail": None
                    }))
                    await interaction.followup.send("Removed your thumbnail due to it being invalid.", ephemeral=True)
                else:
                    raise e
        except Exception as e:
            print(e, flush=True)

    @customai.command()
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @donor_only()
    async def build(self, interaction: discord.Interaction):
        """✨ Build your custom AI"""
        try:
            await interaction.response.defer(ephemeral=True)

            class ModelDropdown(discord.ui.Select):
                def __init__(self, parent_view, current_model):
                    self.parent_view = parent_view
                    options = [
                        discord.SelectOption(label="GPT-4o Search Preview", value="gpt-4o-search-preview", default=(current_model == "gpt-4o-search-preview")),
                        discord.SelectOption(label="GPT-4o Mini", value="gpt-4o-mini", default=(current_model == "gpt-4o-mini")),
                        discord.SelectOption(label="Deepseek R1", value="deepseek-r1-0528", default=(current_model == "deepseek-r1-0528")),
                        discord.SelectOption(label="Mistral Small 2506", value="mistral-small-2506", default=(current_model == "mistral-small-2506")),
                        discord.SelectOption(label="Devious (Uncensored)", value="devious-uncensored", default=(current_model == "devious-uncensored"))
                    ]
                    super().__init__(placeholder="Change model...", options=options)

                async def callback(self, interaction: discord.Interaction):
                    self.parent_view.model = self.values[0]
                    await self.parent_view.save_settings(interaction.user.id, self.parent_view.model, self.parent_view.system_prompt or "", self.parent_view.thumbnail)
                    for item in self.parent_view.children:
                        if isinstance(item, ModelDropdown):
                            self.parent_view.remove_item(item)
                            break
                    self.parent_view.add_item(ModelDropdown(self.parent_view, self.parent_view.model))
                    content = f"Model: **{self.parent_view.model}**"
                    if self.parent_view.system_prompt:
                        prompt = self.parent_view.system_prompt[:97] + "..." if len(self.parent_view.system_prompt) > 100 else self.parent_view.system_prompt
                        content += f"\nSystem prompt: **{prompt}**"
                    await interaction.response.edit_message(content=content, view=self.parent_view)

            class SetThumbnailButton(discord.ui.Button):
                def __init__(self, parent_view):
                    super().__init__(label="AI Thumbnail", style=discord.ButtonStyle.blurple)
                    self.parent_view = parent_view

                async def callback(self, interaction: discord.Interaction):
                    await interaction.response.send_modal(ThumbnailModal(self.parent_view))

            class RemoveThumbnailButton(discord.ui.Button):
                def __init__(self, parent_view):
                    super().__init__(label="Remove Thumbnail", style=discord.ButtonStyle.red)
                    self.parent_view = parent_view

                async def callback(self, interaction: discord.Interaction):
                    self.parent_view.thumbnail = None
                    await self.parent_view.save_settings(interaction.user.id, self.parent_view.model, self.parent_view.system_prompt, self.parent_view.thumbnail)
                    await self.parent_view.refresh(interaction)

            class ThumbnailModal(discord.ui.Modal):
                def __init__(self, view):
                    super().__init__(title="Set thumbnail image")
                    self.view = view
                    self.url = discord.ui.TextInput(label="Image URL", placeholder="https://...", required=True)
                    self.add_item(self.url)

                async def on_submit(self, interaction: discord.Interaction):
                    parsed = urlparse(self.url.value)
                    if parsed.scheme not in ("http", "https") or not parsed.netloc:
                        await interaction.followup.send("Invalid URL format. Must start with http/https.", ephemeral=True)
                        return
                    self.view.thumbnail = self.url.value
                    await self.view.save_settings(interaction.user.id, self.view.model, self.view.system_prompt, self.view.thumbnail)
                    await self.view.refresh(interaction)

            class SystemPromptModal(discord.ui.Modal):
                def __init__(self, view, prefill: str):
                    super().__init__(title="Set a system prompt")
                    self.view = view
                    self.prompt = discord.ui.TextInput(
                        label="System prompt (max 500 chars)",
                        placeholder="Act like you're a kitten..",
                        style=discord.TextStyle.long,
                        required=True,
                        max_length=500,
                        default=prefill
                    )
                    self.add_item(self.prompt)

                async def on_submit(self, interaction: discord.Interaction):
                    self.view.system_prompt = self.prompt.value
                    await self.view.save_settings(interaction.user.id, self.view.model, self.view.system_prompt, self.view.thumbnail)
                    prompt = self.prompt.value[:97] + "..." if len(self.prompt.value) > 100 else self.prompt.value
                    content = f"Model: **{self.view.model}**\nSystem prompt: **{prompt}**"
                    await interaction.response.edit_message(content=content, view=self.view)

            class ActionButtons(discord.ui.View):
                def __init__(self, bot, user_id, model=None, system_prompt=None, thumbnail=None):
                    super().__init__(timeout=300)
                    self.bot = bot
                    self.user_id = user_id
                    self.model = model
                    self.system_prompt = system_prompt
                    self.thumbnail = thumbnail
                    self.add_item(ModelDropdown(self, model))
                    self.update_thumbnail_button()

                def update_thumbnail_button(self):
                    for child in self.children[:]:
                        if isinstance(child, (SetThumbnailButton, RemoveThumbnailButton)):
                            self.remove_item(child)
                    if self.thumbnail:
                        self.add_item(RemoveThumbnailButton(self))
                    else:
                        self.add_item(SetThumbnailButton(self))

                async def refresh(self, interaction: discord.Interaction):
                    self.update_thumbnail_button()
                    content = "Model: **None**" if not self.model else f"Model: **{self.model}**"
                    if self.system_prompt:
                        prompt = self.system_prompt[:97] + "..." if len(self.system_prompt) > 100 else self.system_prompt
                        content += f"\nSystem prompt: **{prompt}**"
                    await interaction.response.edit_message(content=content, view=self)

                @discord.ui.button(label="System Prompt", style=discord.ButtonStyle.green)
                async def set_prompt(self, interaction: discord.Interaction, button: discord.ui.Button):
                    modal = SystemPromptModal(self, prefill=self.system_prompt or "")
                    await interaction.response.send_modal(modal)

                async def save_settings(self, user_id: int, model: str | None, system_prompt: str, thumbnail: str | None):
                    system_prompt = system_prompt or ""
                    async with self.bot.pool.acquire() as conn:
                        await conn.execute(
                            "INSERT INTO ai_settings (user_id, model, system_prompt, thumbnail) VALUES ($1, $2, $3, $4) "
                            "ON CONFLICT (user_id) DO UPDATE SET model = $2, system_prompt = $3, thumbnail = $4",
                            user_id, model, system_prompt, thumbnail
                        )
                    await self.bot.redis.set(f"ai_settings:{user_id}", json.dumps({
                        "model": model,
                        "system_prompt": system_prompt,
                        "thumbnail": thumbnail
                    }))

                async def on_timeout(self):
                    if hasattr(self, 'message'):
                        try:
                            await self.message.delete()
                        except:
                            pass

            settings = await self.get_ai_settings(interaction.user.id)
            initial_model = settings['model'] if settings and settings['model'] else None
            initial_prompt = settings['system_prompt'] if settings and settings['system_prompt'] else None
            thumbnail = settings['thumbnail'] if settings and settings.get('thumbnail') else None

            view = ActionButtons(self.bot, interaction.user.id, model=initial_model, system_prompt=initial_prompt, thumbnail=thumbnail)
            content = "Model: **None**" if not view.model else f"Model: **{view.model}**"
            if initial_prompt:
                prompt = initial_prompt[:97] + "..." if len(initial_prompt) > 100 else initial_prompt
                content += f"\nSystem prompt: **{prompt}**"
            message = await interaction.followup.send(content, view=view, ephemeral=True)
            view.message = message
        except Exception as e:
            print(f"Error in build command: {e}")

    async def get_ai_settings(self, user_id: int) -> Optional[dict]:
        try:
            cached = await self.bot.redis.get(f"ai_settings:{user_id}")

            if cached:
                if isinstance(cached, bytes):
                    decoded = cached.decode("utf-8")
                    return json.loads(decoded)
                elif isinstance(cached, str):
                    return json.loads(cached)
                elif isinstance(cached, dict):
                    return cached

            async with self.bot.pool.acquire() as conn:
                record = await conn.fetchrow(
                    "SELECT model, system_prompt, thumbnail FROM ai_settings WHERE user_id = $1",
                    user_id
                )

                if record:
                    settings = {
                        "model": record["model"],
                        "system_prompt": record["system_prompt"],
                        "thumbnail": record.get("thumbnail"),
                    }
                    await self.bot.redis.set(f"ai_settings:{user_id}", json.dumps(settings))
                    return settings

            return None
        except Exception as e:
            return None

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

    @commands.hybrid_command(
        name="tts",
        description="Convert text to audio",
        aliases=["texttospeech"]
    )
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
    async def tospeech(self, ctx, *, text: str, voice: Optional[str] = None):
        if not text:
            return await ctx.warn("No text provided to convert to speech.")
        invalid_chars = {'.', ',', '/', '\\'} 
        if set(text) <= invalid_chars:
            return await ctx.warn("No audio could be generated. Invalid character.")
        if len(text) > 300:
            return await ctx.warn(f"Text too long. Maximum 300 characters allowed.\nUse </ai tts:1402126672878112892> for raised limits (2.5k chars).")
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
                return await ctx.warn("API did not return anything.")
            audio = base64.b64decode(data['data'])
            audio_buffer = BytesIO(audio)
            audio_buffer.seek(0)
            rnum = random.randint(100, 999)
            filename_mp3 = f"tts_{rnum}.mp3"
            filename_opus = f"tts_{rnum}.opus"
            end_time = time.time()
            duration = end_time - start_time
            embed = Embed(
                description=f"🔊 Audio generated in `{duration:.2f}s`.", 
                color=await self.bot.get_color(ctx.author.id)
            )
            audio_buffer = io.BytesIO(audio)
            audio_buffer.seek(0)
            audio_file = File(audio_buffer, filename_mp3)

            if getattr(ctx.interaction, "app_permissions", discord.Permissions.all()).embed_links:
                await ctx.send(f"Prompt: {text}", embed=embed, file=audio_file)
            else:
                await ctx.send(f"Prompt: {text}", file=audio_file)

    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    async def quotemessage_context(self, interaction: Interaction, message: discord.Message):
        ctx = await self.bot.get_context(interaction)
        ctx.author = interaction.user
        ctx.message = interaction
        await self._process_quote(ctx, message)

    @commands.command(name="quotemessage", aliases=["qm", "quote"])
    async def quote_command(self, ctx, message: discord.Message = None):
        if not message and hasattr(ctx, 'message') and ctx.message.reference:
            message = ctx.message.reference.resolved
        if not message:
            await ctx.warn("Please reply to a message to quote it.")
            return
        await self._process_quote(ctx, message)

    async def _process_quote(self, ctx, message):
        try:
            if not message.content:
                await ctx.warn("You cannot quote this message (no text content).")
                return

            async with ctx.typing():
                pass

            view = Buttons(ctx, author=ctx.author)
            view.message = message

            async with aiohttp.ClientSession() as session:
                data = {
                    'avatar_url': str(message.author.display_avatar.url),
                    'content': message.clean_content,
                    'display_name': message.author.display_name,
                    'username': message.author.name,
                    'font': view.font
                }
                async with session.post('http://localhost:3636/quote', json=data) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()
                        file = discord.File(io.BytesIO(image_data), filename='quote.png')
                        await ctx.send(file=file, view=view)
                    else:
                        await ctx.warn("Failed to generate quote")
        except Exception as e:
            await ctx.warn(str(e))

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def toimage(self, interaction: discord.Interaction, message: discord.Message) -> None:
        ctx = await self.bot.get_context(interaction)
        ctx.author = interaction.user
        ctx.message = interaction

        async def fetch_image(url: str, session: aiohttp.ClientSession, retries: int = 3) -> bytes:
            for attempt in range(retries):
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            return await response.read()
                        elif response.status == 404 and 'cdn.discordapp.com' in url:
                            alt_url = url.replace("cdn.discordapp.com", "media.discordapp.net")
                            return await fetch_image(alt_url, session, retries - 1)
                        response.raise_for_status()
                except (aiohttp.ClientError, aiohttp.ClientResponseError):
                    if attempt == retries - 1:
                        raise
                    await asyncio.sleep(1 + attempt)
            raise Exception(f"Failed to fetch image after {retries} attempts")

        async def process_sticker(sticker: discord.Sticker) -> tuple[BytesIO, str]:
            is_animated = sticker.format in [
                discord.StickerFormatType.apng,
                discord.StickerFormatType.gif,
            ]
            filename = "sticker.gif" if is_animated else "sticker.png"

            async with aiohttp.ClientSession() as session:
                image_data = await fetch_image(sticker.url, session)
                image_io = BytesIO(image_data)

            if not is_animated:
                return image_io, filename

            def convert_sync():
                image_io.seek(0)
                with Image.open(image_io) as apng:
                    frames = []
                    durations = []
                    for frame in ImageSequence.Iterator(apng):
                        frames.append(frame.convert("RGBA"))
                        durations.append(frame.info.get("duration", 100))

                    output = BytesIO()
                    frames[0].save(
                        output,
                        format="GIF",
                        save_all=True,
                        append_images=frames[1:],
                        duration=durations,
                        loop=0,
                        disposal=1,
                    )
                    output.seek(0)
                    return output

            try:
                loop = asyncio.get_running_loop()
                output = await loop.run_in_executor(None, convert_sync)
                return output, filename
            except Exception:
                image_io.seek(0)
                return image_io, filename

        async def process_emojis(custom_emojis: list[tuple[str, str, str]]) -> None:
            emoji_urls = []
            for animated_flag, emoji_name, emoji_id in custom_emojis:
                is_animated = animated_flag == 'a'
                emoji_url = f'https://cdn.discordapp.com/emojis/{emoji_id}.{"gif" if is_animated else "png"}'
                if not is_animated:
                    emoji_url += "?size=600&quality=lossless"
                if emoji_url not in emoji_urls:
                    emoji_urls.append(emoji_url)

            if not emoji_urls:
                await ctx.warn("No valid custom emoji found in the message.")
                return

            if len(emoji_urls) > 1:
                from heist.framework.pagination import Paginator
                paginator = Paginator(ctx, emoji_urls, message=None)
                await paginator.start()
            else:
                await ctx.send(content=emoji_urls[0])

        try:
            await ctx.typing()

            if message.stickers:
                sticker = message.stickers[0]
                if sticker.format == discord.StickerFormatType.lottie:
                    await ctx.warn("Lottie format is not supported.")
                    return
                image_io, filename = await process_sticker(sticker)
                await ctx.send(file=File(image_io, filename=filename))
                return

            custom_emojis = []
            if message.content:
                custom_emojis.extend(re.findall(r'<(a?):(\w+):(\d+)>', message.content))

            if message.embeds:
                for embed in message.embeds:
                    for field in [
                        embed.description, embed.title,
                        embed.footer.text if embed.footer else None,
                        embed.author.name if embed.author else None
                    ]:
                        if field:
                            custom_emojis.extend(re.findall(r'<(a?):(\w+):(\d+)>', field))
                    if embed.fields:
                        for field in embed.fields:
                            custom_emojis.extend(re.findall(r'<(a?):(\w+):(\d+)>', field.value))

            if custom_emojis:
                await process_emojis(custom_emojis)
                return

            await ctx.warn("No sticker or emoji to convert.")

        except Exception as e:
            self.logger.error(f"Error in toimage command: {e}")
            await ctx.warn(str(e))

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def shazam_context(self, interaction: discord.Interaction, message: discord.Message) -> None:
        ctx = await self.bot.get_context(interaction)
        ctx.author = interaction.user
        ctx.message = interaction

        try:
            if not message.attachments:
                await ctx.warn("No attachment found in this message.")
                return

            attachment = message.attachments[0]
            SUPPORTED_EXTENSIONS = ['mp3', 'wav', 'ogg', 'm4a', 'flac', 'mp4', 'mov', 'avi', 'mkv', 'opus']
            file_extension = attachment.filename.split('.')[-1].lower()

            if file_extension not in SUPPORTED_EXTENSIONS:
                await ctx.warn("Unsupported file format for Shazam.")
                return

            await ctx.defer()

            async def convert_audio(data, ext):
                if ext in ['mp4', 'mov', 'avi', 'mkv']:
                    process = await asyncio.create_subprocess_exec(
                        'ffmpeg', '-i', 'pipe:0', '-f', 'mp3', '-vn', '-ac', '2', '-ar', '44100', '-b:a', '192k', 'pipe:1',
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate(input=data)
                    if process.returncode != 0:
                        raise Exception(f"FFmpeg error: {stderr.decode()}")
                    return stdout, 'mp3'
                elif ext in ['opus', 'ogg']:
                    process = await asyncio.create_subprocess_exec(
                        'ffmpeg', '-i', 'pipe:0', '-f', 'wav', '-ac', '2', '-ar', '44100', 'pipe:1',
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate(input=data)
                    if process.returncode != 0:
                        raise Exception(f"FFmpeg error: {stderr.decode()}")
                    return stdout, 'wav'
                return data, ext

            async with self.session.get(attachment.url) as response:
                audio_data = await response.read()

            converted_data, new_ext = await convert_audio(audio_data, file_extension)

            async with aiofiles.tempfile.NamedTemporaryFile(prefix='shazam_', suffix=f'.{new_ext}', delete=True) as temp_file:
                await temp_file.write(converted_data)
                await temp_file.flush()

                shazam = Shazam()
                result = await shazam.recognize(temp_file.name)

                if not result or 'track' not in result:
                    await ctx.warn("Could not recognize this song.")
                    return

                track = result['track']
                title = track.get('title', 'Unknown Title')
                artist = track.get('subtitle', 'Unknown Artist')

                apple_music_url = None
                spotify_url = None
                apple_music_image = None
                spotify_image = None

                if 'hub' in track and track['hub'].get('type') == 'APPLEMUSIC':
                    for action in track['hub'].get('actions', []):
                        if action.get('type') == 'applemusicplay':
                            apple_music_url = action.get('uri')
                        if action.get('type') == 'uri' and 'image' in action:
                            apple_music_image = action.get('image')

                if 'providers' in track:
                    for provider in track['providers']:
                        if provider.get('type') == 'SPOTIFY':
                            for action in provider.get('actions', []):
                                if action.get('type') == 'uri':
                                    spotify_url = action.get('uri')
                            if 'images' in provider:
                                spotify_image = provider['images'].get('default')

                shazam_image = track.get('images', {}).get('coverart', 'https://i.imgur.com/3sgezz7.png')
                thumbnail_url = apple_music_image or spotify_image or shazam_image

                description_parts = [f"Song: **{title}**\nArtist(s): **{artist}**"]
                if apple_music_url:
                    description_parts.append(f"[Listen on Apple Music]({apple_music_url})")
                if spotify_url:
                    description_parts.append(f"[Listen on Spotify]({spotify_url})")

                description = '\n'.join(description_parts)
                color = await self.bot.get_color(ctx.author.id)
                embed = discord.Embed(
                    title="<:check:1344689360527949834> Song recognised",
                    description=description or "No additional links available.",
                    color=color
                )

                if thumbnail_url:
                    embed.set_thumbnail(url=thumbnail_url)

                embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
                embed.set_footer(text="shazam.com", icon_url="https://git.cursi.ng/shazam_logo.png")

                await ctx.send(embed=embed)

        except Exception as e:
            await ctx.warn(f"Error recognizing song: {str(e)[:1500]}")

    @commands.hybrid_command(name="shazam", description="Recognize a song using Shazam")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(audio="Audio file to be recognized")
    async def shazam(self, ctx: commands.Context, audio: discord.Attachment):
        await ctx.typing()
        SUPPORTED_EXTENSIONS = ['mp3', 'wav', 'ogg', 'm4a', 'flac']

        try:
            file_extension = audio.filename.split('.')[-1].lower()
            if file_extension not in SUPPORTED_EXTENSIONS:
                return await ctx.warn("This file format is not supported.")

            async with aiofiles.tempfile.NamedTemporaryFile(prefix='shazam_', suffix=f'.{file_extension}', delete=True) as temp_file:
                await temp_file.write(await audio.read())
                await temp_file.flush()
                
                shazam = Shazam()
                result = await shazam.recognize(temp_file.name)

                if result and 'track' in result:
                    track = result['track']
                    title = track.get('title', 'Unknown Title')
                    artist = track.get('subtitle', 'Unknown Artist')

                    apple_music_url = None
                    spotify_url = None
                    apple_music_image = None
                    spotify_image = None

                    if 'hub' in track and track['hub'].get('type') == 'APPLEMUSIC':
                        for action in track['hub'].get('actions', []):
                            if action.get('type') == 'applemusicplay':
                                apple_music_url = action.get('uri')
                            if action.get('type') == 'uri' and 'image' in action:
                                apple_music_image = action.get('image')

                    if 'providers' in track:
                        for provider in track['providers']:
                            if provider.get('type') == 'SPOTIFY':
                                for action in provider.get('actions', []):
                                    if action.get('type') == 'uri':
                                        spotify_url = action.get('uri')
                                if 'images' in provider:
                                    spotify_image = provider['images'].get('default')

                    shazam_image = track.get('images', {}).get('coverart', 'https://i.imgur.com/3sgezz7.png')
                    thumbnail_url = apple_music_image or spotify_image or shazam_image

                    description_parts = [f"Song: **{title}**\nArtist(s): **{artist}**"]
                    if apple_music_url:
                        description_parts.append(f"[Listen on Apple Music]({apple_music_url})")
                    if spotify_url:
                        description_parts.append(f"[Listen on Spotify]({spotify_url})")

                    description = '\n'.join(description_parts)
                    embed = discord.Embed(
                        title="<:check:1344689360527949834> Song recognised",
                        description=description or "No additional links available.",
                        color=await self.bot.get_color(ctx.author.id)
                    )

                    if thumbnail_url:
                        embed.set_thumbnail(url=thumbnail_url)
                    
                    embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
                    embed.set_footer(text="shazam.com", icon_url="https://git.cursi.ng/shazam_logo.png")
                    
                    await ctx.send(embed=embed)

                else:
                    await ctx.warn("Could not recognize this song.", ephemeral=True)

        except Exception as e:
            await ctx.warn(f"Error recognizing song: {e}")

    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def transcribevm(self, ctx: Union[commands.Context, discord.Interaction], message: discord.Message):
        interaction = ctx if isinstance(ctx, discord.Interaction) else None
        ctx = await commands.Context.from_interaction(ctx) if interaction else ctx

        if not message.attachments or not message.attachments[0].filename.lower().endswith(('.wav', '.mp3', '.ogg', '.opus')):
            await ctx.warn("The message does not contain a supported voice message format.")
            return

        if interaction:
            await interaction.response.defer(thinking=True)
        else:
            await ctx.typing()

        attachment = message.attachments[0]
        user_id = str(ctx.author.id)
        is_donor = await check_donor(self.bot, ctx.author.id)
        is_owner = await check_owner(self.bot, ctx.author.id)
        daily_limit = 50 if is_donor else 30
        max_duration = 150000 if is_donor else 30000

        if not is_owner:
            cooldown_key = f"cooldown:transcribe:{user_id}"
            current_count = await self.bot.redis.get(cooldown_key)
            current_count = int(current_count) if current_count else 0
            if current_count >= daily_limit:
                await ctx.warn(f"You can only transcribe **`5`** VMs every day, but you can transcribe up to **`20`** VMs with **Premium**. </premium buy:{self.premiumbuy}>")
                return
            await self.bot.redis.incr(cooldown_key)
            if current_count == 0:
                await self.bot.redis.expire(cooldown_key, 86400)

        async with self.session.get(attachment.url) as response:
            audio_data = await response.read()

        async def convert_audio(data: bytes):
            process = await asyncio.create_subprocess_exec(
                'ffmpeg', '-i', 'pipe:0',
                '-f', 'wav', '-ac', '1', '-ar', '16000', 'pipe:1',
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate(input=data)
            if process.returncode != 0:
                raise Exception(f"FFmpeg error: {stderr.decode()}")
            return await asyncio.to_thread(lambda: AudioSegment.from_file(io.BytesIO(stdout), format='wav'))

        audio_segment = await convert_audio(audio_data)
        audio_duration = len(audio_segment)

        if audio_duration > max_duration:
            audio_segment = audio_segment[:max_duration]
            warning_message = f"-# You are limited to 30-second transcriptions per VM, in order to raise this limit check out **Premium**. </premium buy:{self.premiumbuy}>" if not is_donor else "-# You are limited to 150-second transcriptions per VM."
        else:
            warning_message = ""

        async def export_audio(segment):
            audio_wav = io.BytesIO()
            def _export():
                segment.export(audio_wav, format='wav', parameters=["-ac", "1", "-ar", "16000"])
                audio_wav.seek(0)
                return audio_wav
            return await asyncio.to_thread(_export)

        audio_wav = await export_audio(audio_segment)
        data = aiohttp.FormData()
        data.add_field('file', audio_wav, filename='audio.wav', content_type='audio/wav')

        async with self.session.post("http://localhost:5094/transcribe", data=data) as response:
            if response.status != 200:
                await ctx.warn("Failed to transcribe audio.")
                return
            data = await response.json()

        transcript = data.get('text', 'No transcription result available.')
        if len(transcript) > 2000:
            transcript = transcript[:1856] + "..." if warning_message else transcript[:1997] + "..."

        await ctx.send(f"{transcript}\n{warning_message}", ephemeral=True if interaction else False)

    @commands.hybrid_group(name="convert", description="Conversion utilities", aliases=["conv"])
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def convert(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @convert.command(name="discorduser2id", description="Get the Discord ID of a user", aliases=["d2i", "d2id", "discord2id"])
    @app_commands.describe(user="The user to get ID of (empty=self)")
    async def discorduser2id(self, ctx: commands.Context, user: discord.User = None):
        user = user or ctx.author
        await ctx.send(str(user.id))

    @convert.command(
        name="robloxuser2id",
        description="Get the Roblox user ID from username",
        aliases=["r2i", "rbx2id", "roblox2id"]
    )
    @app_commands.describe(username="The Roblox username to get the ID of")
    async def robloxuser2id(self, ctx: commands.Context, username: str):
        url = "https://users.roblox.com/v1/usernames/users"
        payload = {"usernames": [username], "excludeBannedUsers": False}
        try:
            response = await self.roblox_request("POST", url, json=payload)
            data = await response.json()

            if "data" in data and data["data"]:
                user_id = data["data"][0].get("id")
                if user_id:
                    await ctx.send(str(user_id))
                    return
            await ctx.warn(f"Could not find a Roblox user with the username **`{username}`**.")
        except Exception as e:
            await ctx.warn(e)

    @convert.command(name="discordid2user", description="Get the Discord user from an ID", aliases=["i2d", "id2d", "id2discord"])
    @app_commands.describe(user_id="The Discord user ID to convert")
    async def discordid2user(self, ctx: commands.Context, user_id: str):
        try:
            user = await self.bot.fetch_user(int(user_id))
            if user:
                await ctx.send(f"{user} (`{user.id}`)")
            else:
                await ctx.warn(f"User with ID `{user_id}` not found.")
        except Exception:
            await ctx.warn("Invalid or unknown Discord user ID.")

    @convert.command(
        name="robloxid2user",
        description="Get the Roblox username from user ID",
        aliases=["i2r", "id2r", "id2roblox"]
    )
    @app_commands.describe(user_id="The Roblox user ID to convert")
    async def robloxid2user(self, ctx: commands.Context, user_id: str):
        url = f"https://users.roblox.com/v1/users/{user_id}"
        try:
            response = await self.roblox_request("GET", url)
            data = await response.json()

            if data.get("name"):
                username = data["name"]
                display_name = data.get("displayName", username)
                await ctx.send(f"**{display_name}** (`{username}`) → `{user_id}`")
                return
            await ctx.warn(f"Could not find a Roblox user with the ID **`{user_id}`**.")
        except Exception as e:
            await ctx.warn(e)

    async def check_user_in_heist_db(self, user_id: str) -> bool:
        query = "SELECT 1 FROM user_data WHERE user_id = $1 LIMIT 1"
        user_id = str(user_id)
        try:
            async with self.bot.pool.acquire() as conn:
                async with conn.transaction():
                    result = await conn.fetchval(query, user_id)
                    return result is not None
        except Exception as e:
            print(f"Database query error: {e}")
            return False

    async def dtr_hit_redis(self, identifier: Union[int, str]):
        identifier = str(identifier)

        pattern = f"d2r:*:{identifier}"
        keys = await self.bot.redis.keys(pattern)

        results = []

        for key in keys:
            if isinstance(key, bytes):
                key = key.decode("utf-8")

            cached_data = await self.bot.redis.get(key)
            if not cached_data:
                continue

            if isinstance(cached_data, bytes):
                cached_data = cached_data.decode("utf-8")

            parts = cached_data.split(":")
            if len(parts) < 3:
                continue

            source = key.split(":")[1]

            roblox_id = int(parts[0])
            roblox_name = parts[1]
            last_updated = ":".join(parts[2:])

            results.append({
                "source": source,
                "roblox_id": roblox_id,
                "roblox_name": roblox_name,
                "last_updated": last_updated
            })

        return results

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def discorduser_context(self, interaction: discord.Interaction, user: discord.User) -> None:
        ctx = await self.bot.get_context(interaction)
        ctx.author = interaction.user
        ctx.message = interaction
        await self._process_user(ctx, user)

    @discordg.command()
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(user="The user to view the profile of")
    async def user(self, interaction: discord.Interaction, user: discord.User = None):
        """View a Discord user's profile"""
        ctx = await self.bot.get_context(interaction)
        ctx.author = interaction.user
        ctx.message = interaction
        await self._process_user(ctx, user or ctx.author)

    async def _process_user(self, ctx, user: discord.User):
        user = user or ctx.author
        is_blacklisted = await check_blacklisted(ctx.bot, user.id)
        donor_only = await check_donor(ctx.bot, user.id)
        donor_only_self = await check_donor(ctx.bot, ctx.author.id)
        is_owner = await check_owner(ctx.bot, user.id)
        is_owner_self = await check_owner(ctx.bot, ctx.author.id)
        user_in_db = await self.check_user_in_heist_db(user.id)
        embed_color = await self.bot.get_color(user.id)
        embed_color_self = await self.bot.get_color(ctx.author.id)

        badges = []
        badge_names = []
        full_user = await self.bot.fetch_user(user.id)
        use_discord_method = True
        user_data = None

        try:
            url = f"http://127.0.0.1:8002/users/{user.id}"
            timeout = aiohttp.ClientTimeout(total=5)
            async with self.session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and 'user' in data and 'id' in data['user']:
                        use_discord_method = False
                        user_data = data.get('user', {})
                        if 'badges' in data and data['badges']:
                            if not user.bot and "premium_since" in data:
                                premium_since = datetime.fromisoformat(data["premium_since"].replace("Z", "+00:00"))
                                now = datetime.now(premium_since.tzinfo)
                                months_subscribed = (now - premium_since).days / 30.44
                                
                                if months_subscribed >= 72:
                                    badges.append(self.badge_emojis.get("premium_type_8"))
                                    badge_names.append("premium_type_8")
                                elif months_subscribed >= 60:
                                    badges.append(self.badge_emojis.get("premium_type_7"))
                                    badge_names.append("premium_type_7")
                                elif months_subscribed >= 36:
                                    badges.append(self.badge_emojis.get("premium_type_6"))
                                    badge_names.append("premium_type_6")
                                elif months_subscribed >= 24:
                                    badges.append(self.badge_emojis.get("premium_type_5"))
                                    badge_names.append("premium_type_5")
                                elif months_subscribed >= 12:
                                    badges.append(self.badge_emojis.get("premium_type_4"))
                                    badge_names.append("premium_type_4")
                                elif months_subscribed >= 6:
                                    badges.append(self.badge_emojis.get("premium_type_3"))
                                    badge_names.append("premium_type_3")
                                elif months_subscribed >= 3:
                                    badges.append(self.badge_emojis.get("premium_type_2"))
                                    badge_names.append("premium_type_2")
                                elif months_subscribed >= 1:
                                    badges.append(self.badge_emojis.get("premium_type_1"))
                                    badge_names.append("premium_type_1")
                                else:
                                    badges.append(self.badge_emojis.get("premium"))
                                    badge_names.append("premium")

                            for badge in data['badges']:
                                badge_id = badge['id']
                                if badge_id == "premium" and any(b.startswith("premium_type_") for b in badge_names):
                                    continue
                                    
                                badge_emoji = self.badge_emojis.get(badge_id)
                                if badge_emoji and badge_id not in badge_names:
                                    badges.append(badge_emoji)
                                    badge_names.append(badge_id)
        except Exception:
            use_discord_method = True
        
        if use_discord_method and not user.bot:
            user_flags = user.public_flags.all()
            for flag in user_flags:
                badge_emoji = self.badge_emojis.get(flag.name)
                if badge_emoji:
                    badges.append(badge_emoji)
                    badge_names.append(flag.name)

            if full_user.avatar and full_user.avatar.key.startswith('a_') or full_user.banner:
                nitro_emoji = self.badge_emojis.get("premium", "")
                if nitro_emoji:
                    insert_index = 0
                    for name in badge_names:
                        if name > "premium":
                            break
                        insert_index += 1
                    badges.insert(insert_index, nitro_emoji)
                    badge_names.insert(insert_index, "premium")
        elif user.bot:
            badges.append(self.badge_emojis.get("bot", ""))

        badge_string = f"### {' '.join(badges)}" if badges else ""

        async with self.bot.pool.acquire() as conn:
            fame_status = await check_famous(ctx.bot, user.id)

            heist_titles = []
            custom_title = await get_title(user.id)
            if custom_title:
                heist_titles.append(custom_title)
            if user_in_db and not user.bot:
                if not is_blacklisted:
                    if is_owner:
                        heist_titles.append("<a:heistowner:1343768654357205105> **`Heist Owner`**")
                    if fame_status:
                        heist_titles.append("<:famous:1311067416251596870> **`Famous`**")
                    if donor_only:
                        heist_titles.append("<:premium:1311062205650833509> **`Premium`**")
                    if not donor_only:
                        heist_titles.append("<:heist:1391969039361904794> **`Standard`**")
                else:
                    heist_titles.append("❌ **`Blacklisted`** (lol)")

            heist_titles_string = ", ".join(heist_titles)

            description = badge_string
            if heist_titles_string:
                description += f"\n{heist_titles_string}"
                
            user_id_str = str(user.id)
            result = await conn.fetchrow("SELECT lastfm_username FROM lastfm_users WHERE discord_id = $1", user.id)
            lastfm_username = result['lastfm_username'] if result else None

            has_audio = False
            song_name = None
            artist_name = None
            if lastfm_username:
                try:
                    api_key = self.LASTFM_KEY
                    recent_tracks_url = f"http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={lastfm_username}&api_key={api_key}&format=json"

                    async with self.session.get(recent_tracks_url) as recent_tracks_response:
                        if recent_tracks_response.status == 200:
                            tracks = (await recent_tracks_response.json())['recenttracks'].get('track', [])

                            if tracks:
                                now_playing = None
                                for track in tracks:
                                    if '@attr' in track and 'nowplaying' in track['@attr'] and track['@attr']['nowplaying'] == 'true':
                                        now_playing = track
                                        break

                                if now_playing:
                                    artist_name = now_playing['artist']['#text']
                                    song_name = now_playing['name']

                                    trackenc = urllib.parse.quote_plus(song_name)
                                    artistenc = urllib.parse.quote_plus(artist_name)
                                    artist_url = f"https://www.last.fm/music/{artistenc}"
                                    api_url = f"http://127.0.0.1:2053/api/search?lastfm_username={lastfm_username}&track_name={trackenc}&artist_name={artistenc}"
                                    
                                    async with self.session.get(api_url) as spotify_response:
                                        if spotify_response.status == 200:
                                            spotify_data = await spotify_response.json()
                                            song_url = spotify_data.get('spotify_link')
                                            description += f"\n-# <:lastfm:1275185763574874134> [**{song_name}**]({song_url}) by [{artist_name}]({artist_url})"
                                        else:
                                            description += f"\n-# <:lastfm:1275185763574874134> **{song_name}** by {artist_name}"
                                else:
                                    last_played = tracks[-1] if isinstance(tracks, list) else tracks
                                    artist_name = last_played['artist']['#text']
                                    song_name = last_played['name']

                                    trackenc = urllib.parse.quote_plus(song_name)
                                    artistenc = urllib.parse.quote_plus(artist_name)
                                    artist_url = f"https://www.last.fm/music/{artistenc}"
                                    api_url = f"http://127.0.0.1:2053/api/search?lastfm_username={lastfm_username}&track_name={trackenc}&artist_name={artistenc}"

                                    async with self.session.get(api_url) as spotify_response:
                                        if spotify_response.status == 200:
                                            spotify_data = await spotify_response.json()
                                            song_url = spotify_data.get('spotify_link')
                                            description += f"\n-# <:lastfm:1275185763574874134> Last listened to [**{song_name}**]({song_url}) by [{artist_name}]({artist_url})"
                                        else:
                                            description += f"\n-# <:lastfm:1275185763574874134> Last listened to **{song_name}** by {artist_name}"

                                if song_name and artist_name:
                                    query = f"{song_name}"
                                    headers = {
                                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                                    }
                                    async with self.session.get(f"https://api.stats.fm/api/v1/search/elastic?query={query}&type=track&limit=1", headers=headers) as response:
                                        if response.status == 200:
                                            data = await response.json()
                                            tracks_search = data.get("items", {}).get("tracks", [])
                                            if tracks_search:
                                                genius_title = song_name.lower().strip()
                                                genius_artist = artist_name.lower().strip()
                                                for track in tracks_search:
                                                    track_title = track.get("name", "").lower().strip()
                                                    track_artists = [artist.get("name", "").lower().strip() for artist in track.get("artists", [])]
                                                    spotify_preview = track.get("spotifyPreview")
                                                    apple_preview = track.get("appleMusicPreview")

                                                    title_match = genius_title in track_title or track_title in genius_title
                                                    artist_match = any(
                                                        genius_artist in track_artist or track_artist in genius_artist 
                                                        for track_artist in track_artists
                                                    )

                                                    if title_match and artist_match:
                                                        if spotify_preview or apple_preview:
                                                            has_audio = True
                                                            break

                except Exception:
                    pass

            limited_key = f"user:{ctx.author.id}:limited"
            untrusted_key = f"user:{ctx.author.id}:untrusted"
            limited = await self.bot.redis.exists(limited_key)
            untrusted = await self.bot.redis.exists(untrusted_key)

            if not untrusted:
                last_seen_info = await self.get_last_seen_info(user, limited)
                if last_seen_info:
                    description += last_seen_info

            if not limited and user_data and "bio" in user_data and user_data["bio"]:
                description += f"\n{user_data['bio']}"
                
            cached = await self.dtr_hit_redis(str(user.id))

            if cached:
                if donor_only_self:
                    dedup = {}
                    for entry in cached:
                        rid = entry["roblox_id"]
                        if rid not in dedup:
                            dedup[rid] = entry
                        else:
                            dedup[rid]["source"] = "same"

                    entries = list(dedup.values())

                    def format_entry(entry):
                        src = entry["source"]
                        rid = entry["roblox_id"]
                        rname = entry["roblox_name"]
                        if src == "same":
                            icon = "<:roblox:1337106773886369822>"
                        elif src == "bloxlink":
                            icon = "<:bloxlink:1441902218927276113> <:roblox:1337106773886369822>"
                        elif src == "rover":
                            icon = "<:rover:1441902221481738442> <:roblox:1337106773886369822>"
                        else:
                            icon = "<:roblox:1337106773886369822>"
                        return f"{icon} [**{rname}**](https://roblox.com/users/{rid}/profile)"

                    if len(entries) == 1:
                        description += "\n\n-# Also found: " + format_entry(entries[0])
                    else:
                        description += "\n\n-# Also found:\n"
                        for e in entries:
                            description += format_entry(e) + "\n"
                else:
                    description += "\n\n-# Also found: <:roblox:1337106773886369822> (**View with Premium**)"

            description = description.rstrip() + "\n"
            description += f"\n-# **Created on** <t:{int(user.created_at.timestamp())}:f> (<t:{int(user.created_at.timestamp())}:R>)"

            embed = Embed(
                description=description,
                color=embed_color
            )

            if user_data and 'clan' in user_data and user_data.get('clan') and isinstance(user_data['clan'], dict):
                clan = user_data['clan']
                clan_tag = clan.get('tag')
                clan_badge = clan.get('badge')
                identity_guild_id = clan.get('identity_guild_id')
                if clan_tag and clan_badge and identity_guild_id:
                    clan_badge_url = f"https://cdn.discordapp.com/clan-badges/{identity_guild_id}/{clan_badge}.png?size=16"
                    embed.set_author(name=f"{clan_tag}", icon_url=clan_badge_url)
                    embed.description = f"**{user.display_name} (@{user.name})**\n{description}"
                else:
                    embed.set_author(name=f"{user.display_name} (@{user.name})", icon_url=user.display_avatar.url)
                    embed.description = description
            else:
                embed.set_author(name=f"{user.display_name} (@{user.name})", icon_url=user.display_avatar.url)
                embed.description = description

            embed.set_thumbnail(url=user.display_avatar.url)

            sep = None
            burl = full_user.banner.url if full_user.banner else None
            if burl:
                embed.set_image(url=burl)
            else:
                sepbyte = await makeseparator(self.bot, user.id)
                sep = discord.File(io.BytesIO(sepbyte), filename="separator.png")

                embed.set_image(url="attachment://separator.png")
            
            embed.set_footer(text=f"heist.lol • {user.id}", icon_url="https://git.cursi.ng/discord_logo.png") 

            view = View(timeout=300)

            async def on_timeout():
                for item in view.children:
                    if isinstance(item, discord.ui.Button) and item.style != discord.ButtonStyle.link:
                        item.disabled = True
                try:
                    await ctx.message.edit_original_response(view=view)
                except discord.NotFound:
                    pass

            view.on_timeout = on_timeout

            try:
                profile_button = discord.ui.Button(label="View Profile", emoji=discord.PartialEmoji.from_str("<:person:1295440206706511995>"), style=discord.ButtonStyle.link, url=f"discord://-/users/{user.id}")
                view.add_item(profile_button)
            except Exception:
                pass

            if has_audio and song_name and artist_name:
                audio_button = discord.ui.Button(
                    emoji=discord.PartialEmoji.from_str("<:audio:1345517095101923439>"),
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"audio_{user.id}_{ctx.author.id}"
                )

                async def audio_button_callback(button_interaction: discord.Interaction):
                    try:
                        await button_interaction.response.defer(ephemeral=True)
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                        }
                        query = f"{song_name}"
                        async with self.session.get(f"https://api.stats.fm/api/v1/search/elastic?query={query}&type=track&limit=1", headers=headers) as response:
                            if response.status != 200:
                                await button_interaction.followup.send("Failed to fetch track data.", ephemeral=True)
                                return
                            data = await response.json()
                            tracks = data.get("items", {}).get("tracks", [])
                            if not tracks:
                                await button_interaction.followup.send("No tracks found.", ephemeral=True)
                                return
                            genius_title = song_name.lower().strip()
                            genius_artist = artist_name.lower().strip()
                            best_match = None
                            for track in tracks:
                                track_title = track.get("name", "").lower().strip()
                                track_artists = [artist.get("name", "").lower().strip() for artist in track.get("artists", [])]
                                spotify_preview = track.get("spotifyPreview")
                                apple_preview = track.get("appleMusicPreview")
                                title_match = genius_title in track_title or track_title in genius_title
                                artist_match = any(genius_artist in a or a in genius_artist for a in track_artists)
                                if title_match and artist_match:
                                    if spotify_preview or apple_preview:
                                        best_match = track
                                        break
                                    else:
                                        best_match = best_match or track
                            if not best_match:
                                await button_interaction.followup.send("No matching track found.", ephemeral=True)
                                return
                            preview_url = best_match.get("spotifyPreview") or best_match.get("appleMusicPreview")
                            if preview_url:
                                async with self.session.get(preview_url) as audio_response:
                                    if audio_response.status == 200:
                                        mp3_data = await audio_response.read()
                                        audio_file = discord.File(io.BytesIO(mp3_data), filename="audio.mp3")
                                        await button_interaction.followup.send(file=audio_file, ephemeral=True)
                                    else:
                                        await button_interaction.followup.send("Failed to fetch audio preview.", ephemeral=True)
                            else:
                                await button_interaction.followup.send("No audio preview available.", ephemeral=True)
                    except Exception:
                        pass

                audio_button.callback = audio_button_callback
                view.add_item(audio_button)

                guilds_button = None
                messages_button = None
                
            if is_owner_self:
                guilds_button = discord.ui.Button(
                    label="Guilds",
                    emoji=discord.PartialEmoji.from_str("<:group:1343755056536621066>"),
                    style=discord.ButtonStyle.green,
                    custom_id=f"guilds_{user.id}_{ctx.author.id}"
                )
                view.add_item(guilds_button)
                
                try:
                    async with self.session.get(
                        f"http://127.0.0.1:8002/messages/exists/{user.id}",
                        timeout=5
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("exists"):
                                messages_button = discord.ui.Button(
                                    label="Messages",
                                    emoji=discord.PartialEmoji.from_str("<:mail:1397689655306223748>"),
                                    style=discord.ButtonStyle.blurple,
                                    custom_id=f"messages_{user.id}_{ctx.author.id}"
                                )
                                view.add_item(messages_button)
                except Exception as e:
                    print(e)
                    pass

        if sep:
            await ctx.send(embed=embed, view=view, file=sep)
        else:
            await ctx.send(embed=embed, view=view)

        if guilds_button:
            async def guilds_button_callback(button_interaction: discord.Interaction):
                is_owner_self = await check_owner(button_interaction.client, button_interaction.user.id)
                if not is_owner_self:
                    embed = discord.Embed(
                        description=f"<:warning:1350239604925530192> {button_interaction.user.mention}: You are not Heist staff.",
                        color=embed_color_self
                    )
                    await button_interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                await button_interaction.response.defer(thinking=True, ephemeral=True)
                target_user = await ctx.bot.fetch_user(user.id)
                processing_embed = discord.Embed(description=f"<a:loading:1392217668383408148> {ctx.author.mention}: processing..", color=embed_color_self)
                processing = await button_interaction.followup.send(embed=processing_embed)
                guilds_info = []
                guild_ids = set()
                retries = 0
                max_retries = 5
                backoff_factor = 2
                timeout = aiohttp.ClientTimeout(total=2)
                while retries < max_retries:
                    try:
                        async with self.session.get(f"http://127.0.0.1:8002/mutualguilds/{user.id}", timeout=timeout) as resp:
                            if resp.status == 200:
                                guilds_data = await resp.json()
                                for guild_data in guilds_data:
                                    guild_id = guild_data.get("id")
                                    if guild_id not in guild_ids:
                                        guild_ids.add(guild_id)
                                        guilds_info.append(guild_data)
                                if len(guilds_info) == 0:
                                    embed = discord.Embed(
                                        title=f"{target_user.name}'s guilds shared with Heist (0)",
                                        description="-# No guilds shared with user.",
                                        color=embed_color
                                    )
                                    embed.set_footer(text="heist.lol", icon_url="https://git.cursi.ng/heist.png?a")
                                    embed.set_thumbnail(url=target_user.avatar.url if target_user.avatar else target_user.default_avatar.url)
                                    await processing.edit(embed=embed)
                                    return
                                total_pages = (len(guilds_info) + 4) // 5
                                current_page = 0
                                embed = discord.Embed(
                                    title=f"{target_user.name}'s guilds shared with Heist ({len(guilds_info)})",
                                    url=f"https://discord.com/users/{target_user.id}",
                                    color=embed_color
                                )
                                embed.description = ""
                                start_idx = current_page * 5
                                end_idx = min(start_idx + 5, len(guilds_info))
                                for guild in guilds_info[start_idx:end_idx]:
                                    guild_name = guild.get("name", "Unknown Guild")
                                    vanity = guild.get("vanity_url")
                                    vanity_text = f"`discord.gg/{vanity}`" if vanity else "`no vanity found`"
                                    embed.description += f"**{guild_name}**\n-# {vanity_text}\n\n"
                                embed.set_author(
                                    name=f"{target_user.name}",
                                    icon_url=target_user.avatar.url if target_user.avatar else target_user.default_avatar.url
                                )
                                embed.set_thumbnail(url=target_user.avatar.url if target_user.avatar else target_user.default_avatar.url)
                                embed.set_footer(text=f"Page {current_page + 1}/{total_pages} • heist.lol", icon_url="https://git.cursi.ng/heist.png?a")
                                view = discord.ui.View()
                                previous_button = discord.ui.Button(
                                    emoji=discord.PartialEmoji.from_str("<:left:1265476224742850633>"), 
                                    style=discord.ButtonStyle.primary, 
                                    disabled=True,
                                    custom_id="previous"
                                )
                                view.add_item(previous_button)
                                next_button = discord.ui.Button(
                                    emoji=discord.PartialEmoji.from_str("<:right:1265476229876678768>"), 
                                    style=discord.ButtonStyle.primary, 
                                    disabled=total_pages <= 1,
                                    custom_id="next"
                                )
                                view.add_item(next_button)
                                skip_button = discord.ui.Button(
                                    emoji=discord.PartialEmoji.from_str("<:sort:1317260205381386360>"),
                                    style=discord.ButtonStyle.secondary,
                                    custom_id="skip"
                                )
                                view.add_item(skip_button)
                                json_button = discord.ui.Button(
                                    emoji=discord.PartialEmoji.from_str("<:json:1292867766755524689>"),
                                    style=discord.ButtonStyle.secondary,
                                    custom_id="json"
                                )
                                view.add_item(json_button)
                                delete_button = discord.ui.Button(
                                    emoji=discord.PartialEmoji.from_str("<:bin:1317214464231079989>"),
                                    style=discord.ButtonStyle.danger,
                                    custom_id="delete"
                                )
                                view.add_item(delete_button)
                                async def button_callback(button_interaction: discord.Interaction):
                                    nonlocal current_page
                                    if button_interaction.user.id != ctx.author.id:
                                        await button_interaction.response.send_message("You cannot use these buttons.", ephemeral=True)
                                        return
                                    if button_interaction.data["custom_id"] == "delete":
                                        await button_interaction.response.defer()
                                        await button_interaction.delete_original_response()
                                        return
                                    if button_interaction.data["custom_id"] == "skip":
                                        class GoToPageModal(discord.ui.Modal, title="Go to Page"):
                                            page_number = discord.ui.TextInput(label="Navigate to page", placeholder=f"Enter a page number (1-{total_pages})", min_length=1, max_length=len(str(total_pages)))
                                            async def on_submit(self, interaction: discord.Interaction):
                                                try:
                                                    page = int(self.page_number.value) - 1
                                                    if page < 0 or page >= total_pages:
                                                        raise ValueError
                                                    nonlocal current_page
                                                    current_page = page
                                                    await update_message()
                                                    await interaction.response.defer()
                                                except ValueError:
                                                    await interaction.response.send_message("Invalid choice, cancelled.", ephemeral=True)
                                        modal = GoToPageModal()
                                        await button_interaction.response.send_modal(modal)
                                        return
                                    if button_interaction.data["custom_id"] == "previous":
                                        current_page = max(0, current_page - 1)
                                    elif button_interaction.data["custom_id"] == "next":
                                        current_page = min(total_pages - 1, current_page + 1)
                                    await button_interaction.response.defer()
                                    await update_message()
                                async def update_message():
                                    embed.description = ""
                                    start_idx = current_page * 5
                                    end_idx = min(start_idx + 5, len(guilds_info))
                                    for guild in guilds_info[start_idx:end_idx]:
                                        guild_name = guild.get("name", "Unknown Guild")
                                        vanity = guild.get("vanity_url")
                                        vanity_text = f"`discord.gg/{vanity}`" if vanity else "`no vanity found`"
                                        embed.description += f"**{guild_name}**\n-# {vanity_text}\n\n"
                                    embed.set_footer(text=f"Page {current_page + 1}/{total_pages} • heist.lol", icon_url="https://git.cursi.ng/heist.png?a")
                                    view.children[0].disabled = current_page == 0
                                    view.children[1].disabled = current_page == total_pages - 1
                                    await processing.edit(embed=embed, view=view)
                                async def json_button_callback(button_interaction: discord.Interaction):
                                    formatjson = json.dumps(guilds_info, indent=4)
                                    file = io.BytesIO(formatjson.encode())
                                    await button_interaction.response.send_message(file=discord.File(file, filename="guilds.json"), ephemeral=True)
                                for button in view.children[:-2]:
                                    button.callback = button_callback
                                json_button.callback = json_button_callback
                                delete_button.callback = button_callback
                                await processing.edit(embed=embed, view=view)
                                break
                    except Exception:
                        retries += 1
                        await asyncio.sleep(backoff_factor * retries)
                else:
                    await button_interaction.followup.send("An error occurred while fetching guilds after multiple attempts.", ephemeral=True)
            guilds_button.callback = guilds_button_callback

        if messages_button:
            async def messages_button_callback(button_interaction: discord.Interaction):
                try:
                    is_owner_self = await check_owner(button_interaction.client, button_interaction.user.id)
                    if not is_owner_self:
                        embed = discord.Embed(
                            description=f"<:warning:1350239604925530192> {button_interaction.user.mention}: You are not Heist staff.",
                            color=embed_color_self
                        )
                        await button_interaction.response.send_message(embed=embed, ephemeral=True)
                        return
                    await button_interaction.response.defer(thinking=True, ephemeral=True)
                    target_user = await ctx.bot.fetch_user(user.id)
                    processing_embed = discord.Embed(description=f"<a:loading:1392217668383408148> {ctx.author.mention}: processing..", color=embed_color_self)
                    processing = await button_interaction.followup.send(embed=processing_embed)
                    messages_url = f"http://127.0.0.1:8002/messages?user_id={user.id}"
                    async with self.session.get(messages_url) as resp:
                        if resp.status == 200:
                            messages = await resp.json()
                            if messages:
                                total_pages = (len(messages) + 4) // 5
                                current_page = 0
                                embed = discord.Embed(
                                    title=f"{target_user.name}'s Recent Messages ({len(messages)})",
                                    url=f"https://discord.com/users/{target_user.id}",
                                    color=embed_color
                                )
                                import re
                                embed.description = ""

                                def get_name(url):
                                    parts = url.split('/')
                                    if parts:
                                        last_part = parts[-1]
                                        if '?' in last_part:
                                            last_part = last_part.split('?')[0]
                                        if last_part:
                                            return last_part
                                    return None

                                pattern = r"(https://cdn\.discordapp\.com/attachments/[^\s]+)"

                                def format_content(content: str) -> str:
                                    parts = re.split(pattern, content)
                                    formatted_parts = []
                                    for part in parts:
                                        if re.match(pattern, part):
                                            name = get_name(part)
                                            if not name:
                                                name = "attachment"
                                            formatted_parts.append(f"[**`{name}`**]({part})")
                                        else:
                                            safe_part = part.replace("`", "ˋ").replace("\n", " ⏎ ")
                                            if safe_part.strip() != "":
                                                formatted_parts.append(f"`{safe_part}`")
                                            else:
                                                formatted_parts.append(safe_part)
                                    return "".join(formatted_parts)

                                start_idx = current_page * 5
                                end_idx = min(start_idx + 5, len(messages))
                                for msg in messages[start_idx:end_idx]:
                                    timestamp = datetime.fromisoformat(msg['timestamp'].rstrip('Z')).timestamp()
                                    guild_name = msg.get('guild_name', 'Unknown Guild')
                                    if msg.get('vanity_url'):
                                        guild_line = f"**[{guild_name}](https://discord.gg/{msg['vanity_url']})**\n"
                                    else:
                                        guild_line = f"**{guild_name}**\n"
                                    content = msg['content']
                                    content = await asyncio.get_event_loop().run_in_executor(None, format_content, content)
                                    embed.description += f"{guild_line}-# {content}\n-# <t:{int(timestamp)}:R>\n\n"
                                embed.set_author(
                                    name=f"{target_user.name}",
                                    icon_url=target_user.avatar.url if target_user.avatar else target_user.default_avatar.url
                                )
                                embed.set_thumbnail(url=target_user.avatar.url if target_user.avatar else target_user.default_avatar.url)
                                embed.set_footer(text=f"Page {current_page + 1}/{total_pages} • heist.lol", icon_url="https://git.cursi.ng/heist.png?a")
                                view = discord.ui.View()
                                previous_button = discord.ui.Button(
                                    emoji=discord.PartialEmoji.from_str("<:left:1265476224742850633>"), 
                                    style=discord.ButtonStyle.primary, 
                                    disabled=True,
                                    custom_id="previous"
                                )
                                view.add_item(previous_button)
                                next_button = discord.ui.Button(
                                    emoji=discord.PartialEmoji.from_str("<:right:1265476229876678768>"), 
                                    style=discord.ButtonStyle.primary, 
                                    disabled=total_pages <= 1,
                                    custom_id="next"
                                )
                                view.add_item(next_button)
                                skip_button = discord.ui.Button(
                                    emoji=discord.PartialEmoji.from_str("<:sort:1317260205381386360>"),
                                    style=discord.ButtonStyle.secondary,
                                    custom_id="skip"
                                )
                                view.add_item(skip_button)
                                json_button = discord.ui.Button(
                                    emoji=discord.PartialEmoji.from_str("<:json:1292867766755524689>"),
                                    style=discord.ButtonStyle.secondary,
                                    custom_id="json"
                                )
                                view.add_item(json_button)
                                delete_button = discord.ui.Button(
                                    emoji=discord.PartialEmoji.from_str("<:bin:1317214464231079989>"),
                                    style=discord.ButtonStyle.danger,
                                    custom_id="delete"
                                )
                                view.add_item(delete_button)

                                async def update_message():
                                    embed.description = ""
                                    start_idx = current_page * 5
                                    end_idx = min(start_idx + 5, len(messages))
                                    for msg in messages[start_idx:end_idx]:
                                        timestamp = datetime.fromisoformat(msg['timestamp'].rstrip('Z')).timestamp()
                                        guild_name = msg.get('guild_name', 'Unknown Guild')
                                        if msg.get('vanity_url'):
                                            guild_line = f"**[{guild_name}](https://discord.gg/{msg['vanity_url']})**\n"
                                        else:
                                            guild_line = f"**{guild_name}**\n"
                                        content = msg['content']
                                        content = await asyncio.get_event_loop().run_in_executor(None, format_content, content)
                                        embed.description += f"{guild_line}-# {content}\n-# <t:{int(timestamp)}:R>\n\n"
                                    embed.set_footer(text=f"Page {current_page + 1}/{total_pages} • heist.lol", icon_url="https://git.cursi.ng/heist.png?a")
                                    view.children[0].disabled = current_page == 0
                                    view.children[1].disabled = current_page == total_pages - 1
                                    await processing.edit(embed=embed, view=view)

                                async def button_callback(button_interaction: discord.Interaction):
                                    nonlocal current_page
                                    if button_interaction.data["custom_id"] == "delete":
                                        await button_interaction.response.defer()
                                        await button_interaction.delete_original_response()
                                        return
                                    if button_interaction.data["custom_id"] == "skip":
                                        class GoToPageModal(discord.ui.Modal, title="Go to Page"):
                                            page_number = discord.ui.TextInput(label="Navigate to page", placeholder=f"Enter a page number (1-{total_pages})", min_length=1, max_length=len(str(total_pages)))
                                            async def on_submit(self, interaction: discord.Interaction):
                                                try:
                                                    page = int(self.page_number.value) - 1
                                                    if page < 0 or page >= total_pages:
                                                        raise ValueError
                                                    nonlocal current_page
                                                    current_page = page
                                                    await update_message()
                                                    await interaction.response.defer()
                                                except ValueError:
                                                    await interaction.response.send_message("Invalid choice, cancelled.", ephemeral=True)
                                        modal = GoToPageModal()
                                        await button_interaction.response.send_modal(modal)
                                        return
                                    if button_interaction.data["custom_id"] == "previous":
                                        current_page = max(0, current_page - 1)
                                    elif button_interaction.data["custom_id"] == "next":
                                        current_page = min(total_pages - 1, current_page + 1)
                                    await button_interaction.response.defer()
                                    await update_message()

                                async def json_button_callback(button_interaction: discord.Interaction):
                                    formatjson = json.dumps(messages, indent=4)
                                    file = io.BytesIO(formatjson.encode())
                                    await button_interaction.response.send_message(file=discord.File(file, filename="messages.json"), ephemeral=True)

                                for button in view.children[:-2]:
                                    button.callback = button_callback
                                json_button.callback = json_button_callback
                                delete_button.callback = button_callback
                                await processing.edit(embed=embed, view=view)
                            else:
                                await button_interaction.followup.send("No messages found for this user.", ephemeral=True)
                        else:
                            await button_interaction.followup.send("Failed to fetch messages.", ephemeral=True)
                except Exception as gyat:
                    print("error in messages butt", gyat, flush=True)
            messages_button.callback = messages_button_callback

    @commands.hybrid_group(name="crypto", description="Cryptocurrency related commands")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def crypto(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @crypto.command(name="track", description="✨ Track a crypto transaction", invoke_without_command=True)
    @app_commands.describe(coin="Select a cryptocurrency", txid="Transaction ID to track", confirmations="✨ Number of confirmations to wait for")
    @app_commands.choices(coin=[
        app_commands.Choice(name="Bitcoin", value="btc"),
        app_commands.Choice(name="Litecoin", value="ltc"),
        app_commands.Choice(name="Ethereum", value="eth")
    ])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @donor_only()
    async def track(self, ctx: Union[commands.Context, discord.Interaction], coin: str = None, txid: str = None, confirmations: int = None):
        try:
            interaction = ctx if isinstance(ctx, discord.Interaction) else None
            ctx = await commands.Context.from_interaction(ctx) if interaction else ctx
            await ctx.typing()
            is_donor = await check_donor(self.bot, ctx.author.id)
            max_tx = 5 if is_donor else 2
            if not is_donor:
                confirmations = 1
            else:
                if confirmations is None or confirmations < 1:
                    confirmations = 1
                elif confirmations > 8:
                    confirmations = 8

            user_key = f"activetxids:{ctx.author.id}"
            active_txs = await self.bot.redis.lrange(user_key, 0, -1)
            if len(active_txs) >= max_tx:
                premiumbuy = await CommandCache.get_mention(self.bot, "premium buy")
                limit_msg = f"You have reached your maximum transaction limit (**`{max_tx}`**). Upgrade to Premium for up to **`5`** transactions. {premiumbuy}" if not is_donor else f"You have reached your maximum transaction limit ({max_tx})."
                await ctx.warn(limit_msg)
                return

            coin_value = coin
            txid_clean = txid.split("/")[-1] if "/" in txid else txid
            entry = f"{coin_value}:{txid_clean}"
            await self.bot.redis.rpush(user_key, entry)
            await self.bot.redis.expire(user_key, 3600)

            url_map = {
                "btc": f"https://api.blockcypher.com/v1/btc/main/txs/{txid_clean}",
                "ltc": f"https://api.blockcypher.com/v1/ltc/main/txs/{txid_clean}",
                "eth": f"https://api.blockcypher.com/v1/eth/main/txs/{txid_clean}"
            }
            thumb_unconfirmed_map = {
                "btc": "https://git.cursi.ng/unconfirmedbtc.png",
                "ltc": "https://git.cursi.ng/unconfirmedltc.png",
                "eth": "https://git.cursi.ng/unconfirmedeth.png"
            }
            thumb_confirmed_map = {
                "btc": "https://git.cursi.ng/confirmedbtc.png?v",
                "ltc": "https://git.cursi.ng/confirmedltc.png",
                "eth": "https://git.cursi.ng/confirmedeth.png"
            }
            explorer_map = {
                "btc": f"https://blockchair.com/bitcoin/transaction/{txid_clean}",
                "ltc": f"https://blockchair.com/litecoin/transaction/{txid_clean}",
                "eth": f"https://blockchair.com/ethereum/transaction/{txid_clean}"
            }
            color_map = {"btc": 0xef8f19, "ltc": 0xb8b9b8, "eth": 0x3c3cff}

            url = url_map[coin_value]
            thumb_unconfirmed = thumb_unconfirmed_map[coin_value]
            thumb_confirmed = thumb_confirmed_map[coin_value]
            explorer = explorer_map[coin_value]
            color = color_map[coin_value]

            short_txid = f"{txid_clean[:6]}...{txid_clean[-6:]}"
            waiting_desc = f"Waiting for **{confirmations}** confirmation(s). Progress: `0/{confirmations}`"
            embed = discord.Embed(title=f"Waiting for {confirmations} confirmation(s)...", description=waiting_desc, color=color)
            embed.add_field(name="Transaction ID", value=f"`{short_txid}` [View on Blockchain]({explorer})", inline=False)
            embed.set_thumbnail(url=thumb_unconfirmed)
            msg = await ctx.send(embed=embed) if not interaction else await ctx.followup.send(embed=embed)

            if not hasattr(self, "txid_messages"):
                self.txid_messages = {}
            if ctx.author.id not in self.txid_messages:
                self.txid_messages[ctx.author.id] = []
            self.txid_messages[ctx.author.id].append(msg)

            cancel_button = discord.ui.Button(style=discord.ButtonStyle.danger, label="Cancel", emoji=self.bot.config.emojis.context.deny)
            view = discord.ui.View()
            view.add_item(cancel_button)
            await msg.edit(view=view)
            cancelled = False

            async def cancel_callback(interaction_):
                nonlocal cancelled
                if interaction_.user.id != ctx.author.id:
                    await interaction_.response.send_message("You can’t cancel someone else’s tracking.", ephemeral=True)
                    return
                cancelled = True
                try:
                    embed.title = "<:warning:1350239604925530192> Transaction Cancelled"
                    embed.description = "This transaction tracking has been cancelled."
                    embed.set_thumbnail(url="https://git.cursi.ng/redx.png")
                    embed.color = 0xfe0000
                    await msg.edit(embed=embed, view=None)
                except:
                    pass
                try:
                    all_keys = await self.bot.redis.keys("activetxids:*")
                    for k in all_keys:
                        tx_list = await self.bot.redis.lrange(k, 0, -1)
                        for tx_entry in tx_list:
                            tx_entry_str = tx_entry.decode() if isinstance(tx_entry, bytes) else tx_entry
                            if txid_clean in tx_entry_str:
                                await self.bot.redis.lrem(k, 0, tx_entry)
                except:
                    pass
                if getattr(self, "txid_messages", None) and ctx.author.id in self.txid_messages:
                    try:
                        self.txid_messages[ctx.author.id].remove(msg)
                        if not self.txid_messages[ctx.author.id]:
                            del self.txid_messages[ctx.author.id]
                    except:
                        pass

            cancel_button.callback = cancel_callback

            async def fetch_tx(proxies_cycle=[None, self.proxy_url], delay_cycle=[3, 10]):
                for delay in delay_cycle:
                    for proxy in proxies_cycle:
                        try:
                            async with self.session.get(url, proxy=proxy) as r:
                                data = await r.json()
                            if r.status == 429:
                                continue
                            return data
                        except:
                            await asyncio.sleep(delay)
                return None

            data = await fetch_tx()
            if not data or "error" in data:
                embed.title = "<:warning:1350239604925530192> Transaction Not Found"
                embed.description = f"Transaction `{short_txid}` not found."
                embed.set_thumbnail(url="https://git.cursi.ng/redx.png")
                embed.color = 0xfe0000
                await msg.edit(embed=embed, view=None)
                await self.bot.redis.lrem(user_key, 0, entry)
                if getattr(self, "txid_messages", None) and ctx.author.id in self.txid_messages:
                    self.txid_messages[ctx.author.id].remove(msg)
                return

            while True:
                if cancelled or ctx.author.id not in getattr(self, "txid_messages", {}):
                    await self.bot.redis.lrem(user_key, 0, entry)
                    return
                data = await fetch_tx()
                current_confirmations = data.get("confirmations", 0) if data else 0
                if current_confirmations < confirmations:
                    embed.description = f"Waiting for **{confirmations}** confirmation(s). Progress: `{current_confirmations}/{confirmations}`"
                    await msg.edit(embed=embed)
                    await asyncio.sleep(30)
                else:
                    break

            if cancelled or ctx.author.id not in getattr(self, "txid_messages", {}):
                await self.bot.redis.lrem(user_key, 0, entry)
                return

            embed.title = "🤑 Transaction Confirmed!"
            embed.description = f"It was successfully confirmed on the blockchain with **{confirmations}** confirmation(s)!"
            embed.set_thumbnail(url=thumb_confirmed)
            embed.color = 0x54e135
            await msg.edit(embed=embed, view=None)
            await ctx.send(f"{ctx.author.mention}, your transaction confirmed!")
            await self.bot.redis.lrem(user_key, 0, entry)
            if getattr(self, "txid_messages", None) and ctx.author.id in self.txid_messages:
                try:
                    self.txid_messages[ctx.author.id].remove(msg)
                    if not self.txid_messages[ctx.author.id]:
                        del self.txid_messages[ctx.author.id]
                except:
                    pass
        except Exception:
            pass

    @crypto.command(name="stoptrack", description="Cancel all active transaction trackers")
    async def stoptrack(self, ctx: Union[commands.Context, discord.Interaction]):
        interaction = ctx if isinstance(ctx, discord.Interaction) else None
        ctx = await commands.Context.from_interaction(ctx) if interaction else ctx
        user_key = f"activetxids:{ctx.author.id}"
        active_txs = await self.bot.redis.lrange(user_key, 0, -1)
        active_txs = [tx.decode() if isinstance(tx, bytes) else tx for tx in active_txs]
        if not active_txs:
            await ctx.warn("You have no active transactions to cancel.")
            return
        for tx_entry in active_txs:
            try:
                txid_clean = tx_entry.split(":")[1]
                all_keys = await self.bot.redis.keys("activetxids:*")
                for k in all_keys:
                    tx_list = await self.bot.redis.lrange(k, 0, -1)
                    tx_list = [t.decode() if isinstance(t, bytes) else t for t in tx_list]
                    for entry in tx_list:
                        if txid_clean in entry:
                            await self.bot.redis.lrem(k, 0, entry)
            except:
                pass
        try:
            all_msgs = getattr(self, "txid_messages", {})
            user_msgs = all_msgs.get(ctx.author.id, [])
            for msg in user_msgs:
                try:
                    embed = msg.embeds[0]
                    embed.title = "<:warning:1350239604925530192> Transaction Cancelled"
                    embed.description = "This transaction tracking has been cancelled."
                    embed.set_thumbnail(url="https://git.cursi.ng/redx.png")
                    embed.color = 0xfe0000
                    await msg.edit(embed=embed, view=None)
                except:
                    pass
            if ctx.author.id in all_msgs:
                del all_msgs[ctx.author.id]
        except:
            pass
        await ctx.approve(f"All your active transactions have been cancelled.")

    @crypto.group(name="bitcoin", description="Bitcoin related commands", aliases=["btc"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def bitcoin(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @bitcoin.command(name="address", description="Lookup a Bitcoin address", aliases=["addr", "wallet", "addy"])
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(address="Bitcoin address")
    async def bitcoin_address(self, ctx: Union[commands.Context, discord.Interaction], address: str):
        interaction = ctx if isinstance(ctx, discord.Interaction) else None
        ctx = await commands.Context.from_interaction(ctx) if interaction else ctx
        await ctx.typing()
        def btc_validity(a: str): return bool(re.match(r'^(1|3|bc1)[a-zA-Z0-9]{25,40}$', a))
        if not btc_validity(address):
            await ctx.warn("Invalid Bitcoin address format.")
            return
        async with self.session.get(f"https://blockchain.info/rawaddr/{address}?cors=true") as r:
            if r.status == 429:
                async with self.session.get(
                    f"https://blockchain.info/rawaddr/{address}?cors=true",
                    proxy=PROXY_URL
                ) as pr:
                    if pr.status != 200:
                        await ctx.warn("Failed to fetch address data.")
                        return
                    data = await pr.json()
            elif r.status != 200:
                await ctx.warn("Failed to fetch address data.")
                return
            else:
                data = await r.json()
        async with self.session.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd") as p:
            price_data = await p.json()
        btc_usd = price_data.get("bitcoin", {}).get("usd", 0)
        btc_usd_fmt = f"{btc_usd:,.2f}".rstrip("0").rstrip(".")
        balance = data.get("final_balance", 0) / 1e8
        received = data.get("total_received", 0) / 1e8
        sent = data.get("total_sent", 0) / 1e8
        usd_balance = balance * btc_usd
        usd_received = received * btc_usd
        usd_sent = sent * btc_usd
        if data.get("txs"):
            first_seen_unix = min(tx["time"] for tx in data["txs"])
            first_seen_dt = datetime.utcfromtimestamp(first_seen_unix)
            first_seen_str = first_seen_dt.strftime("first seen %d %B %Y").replace(" 0", " ").lower()
        else:
            first_seen_str = "never seen"
        transactions = str(data.get("n_tx", 0))
        color = await self.bot.get_color(ctx.author.id)
        embed = discord.Embed(
            title="Bitcoin Address <:btc:1317320391672332411>",
            url=f"https://www.blockchain.com/explorer/addresses/btc/{address}",
            description=address,
            color=color
        )
        embed.set_author(
            name=ctx.user.name if interaction else ctx.author.name,
            icon_url=ctx.user.display_avatar.url if interaction else ctx.author.display_avatar.url
        )
        embed.add_field(
            name="Funds",
            value=(
                f"* Balance: **`{balance:.8f}`** BTC (**{usd_balance:,.2f} USD**)\n"
                f"* Received: **`{received:.8f}`** BTC (**{usd_received:,.2f} USD**)\n"
                f"* Sent: **`{sent:.8f}`** BTC (**{usd_sent:,.2f} USD**)"
            ),
            inline=False
        )
        embed.set_footer(text=f"{first_seen_str} • {transactions} transactions • 1 btc = {btc_usd_fmt.lower()} usd")
        embed.set_thumbnail(url="https://git.cursi.ng/bitcoin.png?")
        await ctx.send(embed=embed)

    @bitcoin.command(name="price", description="Get the current price of Bitcoin", aliases=["p", "value"])
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def bitcoin_price(self, ctx: Union[commands.Context, discord.Interaction]):
        interaction = ctx if isinstance(ctx, discord.Interaction) else None
        ctx = await commands.Context.from_interaction(ctx) if interaction else ctx
        async with self.session.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd") as r:
            if r.status != 200:
                await ctx.warn("Failed to fetch price data.")
                return
            data = await r.json()
        btc = data["bitcoin"]["usd"]
        btcf = f"{btc:,.2f}".rstrip("0").rstrip(".")
        await ctx.send(f"<:btc:1317320391672332411> is currently valued at **`{btcf}`** USD")

    @bitcoin.command(name="chart", description="Generate a Bitcoin price chart")
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def bitcoin_chart(self, ctx):
        url = "http://127.0.0.1:7685/btc"
        async with self.bot.session.get(url) as r:
            data = await r.json()
        stats = data["stats"]
        img = bytes.fromhex(data["image"])
        file = discord.File(io.BytesIO(img), filename="btc.png")
        color = await self.bot.get_color(ctx.author.id)
        await cpv2.send(ctx,
                        title="<:btc:1317320391672332411> [Bitcoin (BTC)](https://www.tradingview.com/symbols/BTCUSD)",
                        media_url="attachment://btc.png",
                        footer=f"-# {stats['formatted']}",
                        color=color,
                        files=[file])

    @crypto.group(name="litecoin", description="Litecoin related commands", aliases=["ltc"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def litecoin(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @litecoin.command(name="address", description="Lookup a Litecoin address", aliases=["addr", "wallet", "addy"])
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(address="Litecoin address")
    async def litecoin_address(self, ctx: Union[commands.Context, discord.Interaction], address: str):
        interaction = ctx if isinstance(ctx, discord.Interaction) else None
        ctx = await commands.Context.from_interaction(ctx) if interaction else ctx
        await ctx.typing()
        def ltc_validity(a: str): return bool(re.match(r'^(L|M|ltc1)[a-zA-Z0-9]{25,40}$', a))
        if not ltc_validity(address):
            await ctx.warn("Invalid Litecoin address format.")
            return

        async with self.session.get(f"https://api.blockcypher.com/v1/ltc/main/addrs/{address}/balance") as r:
            if r.status != 200:
                await ctx.warn("Failed to fetch address data.")
                return
            data = await r.json()

        async with self.session.get(f"https://api.blockcypher.com/v1/ltc/main/addrs/{address}/full?limit=50") as full_r:
            first_seen_str = "never seen"
            if full_r.status == 200:
                full_data = await full_r.json()
                if "txs" in full_data and full_data["txs"]:
                    txs = full_data["txs"]
                    earliest = min(tx.get("confirmed") for tx in txs if tx.get("confirmed"))
                    if earliest:
                        dt = datetime.strptime(earliest, "%Y-%m-%dT%H:%M:%SZ")
                        first_seen_str = dt.strftime("first seen %d %B %Y").replace(" 0", " ").lower()

        async with self.session.get("https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd") as p:
            price_data = await p.json()
        ltc_usd = price_data.get("litecoin", {}).get("usd", 0)
        ltc_usd_fmt = f"{ltc_usd:,.2f}".rstrip("0").rstrip(".")
        balance = data.get("balance", 0) / 1e8
        received = data.get("total_received", 0) / 1e8
        sent = data.get("total_sent", 0) / 1e8
        usd_balance = balance * ltc_usd
        usd_received = received * ltc_usd
        usd_sent = sent * ltc_usd
        transactions = str(data.get("n_tx", 0))

        color = await self.bot.get_color(ctx.author.id)
        embed = discord.Embed(
            title="Litecoin Address <:ltc:1317315167671025684>",
            url=f"https://blockchair.com/litecoin/address/{address}",
            description=address,
            color=color
        )
        embed.set_author(name=ctx.user.name if interaction else ctx.author.name,
                        icon_url=ctx.user.display_avatar.url if interaction else ctx.author.display_avatar.url)
        embed.add_field(name="Funds", value=(
            f"* Balance: **`{balance:.8f}`** LTC (**{usd_balance:,.2f} USD**)\n"
            f"* Received: **`{received:.8f}`** LTC (**{usd_received:,.2f} USD**)\n"
            f"* Sent: **`{sent:.8f}`** LTC (**{usd_sent:,.2f} USD**)"
        ), inline=False)
        embed.set_footer(text=f"{first_seen_str} • {transactions} transactions • 1 ltc = {ltc_usd_fmt.lower()} usd")
        embed.set_thumbnail(url="https://git.cursi.ng/litecoin.png?")
        await ctx.send(embed=embed)

    @litecoin.command(name="price", description="Get the current price of Litecoin", aliases=["p", "value"])
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def litecoin_price(self, ctx: Union[commands.Context, discord.Interaction]):
        interaction = ctx if isinstance(ctx, discord.Interaction) else None
        ctx = await commands.Context.from_interaction(ctx) if interaction else ctx
        async with self.session.get("https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd") as r:
            if r.status != 200:
                await ctx.warn("Failed to fetch price data.")
                return
            data = await r.json()
        ltc = data["litecoin"]["usd"]
        ltcf = f"{ltc:,.2f}".rstrip("0").rstrip(".")
        await ctx.send(f"<:ltc:1317315167671025684> is currently valued at **`{ltcf}`** USD")

    @litecoin.command(name="chart", description="Generate a Litecoin price chart")
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def litecoin_chart(self, ctx):
        url = "http://127.0.0.1:7685/ltc"
        async with self.bot.session.get(url) as r:
            data = await r.json()
        stats = data["stats"]
        img = bytes.fromhex(data["image"])
        file = discord.File(io.BytesIO(img), filename="ltc.png")
        color = await self.bot.get_color(ctx.author.id)
        await cpv2.send(ctx,
                        title="<:ltc:1317315167671025684> [Litecoin (LTC)](https://www.tradingview.com/symbols/LTCUSD)",
                        media_url="attachment://ltc.png",
                        footer=f"-# {stats['formatted']}",
                        color=color,
                        files=[file])

    @crypto.group(name="ethereum", description="Ethereum related commands", aliases=["eth"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def ethereum(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @ethereum.command(name="address", description="Lookup an Ethereum address", aliases=["addr", "wallet", "addy"])
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(address="Ethereum address")
    async def ethereum_address(self, ctx: Union[commands.Context, discord.Interaction], address: str):
        interaction = ctx if isinstance(ctx, discord.Interaction) else None
        ctx = await commands.Context.from_interaction(ctx) if interaction else ctx
        await ctx.typing()
        def eth_validity(a: str): return bool(re.match(r"^(0x)?[0-9a-fA-F]{40}$", a))
        if not eth_validity(address):
            await ctx.warn("Invalid Ethereum address format.")
            return
        async with self.session.get(f"https://eth.blockscout.com/api/v2/addresses/{address}") as r:
            if r.status != 200:
                await ctx.warn("Failed to fetch address data.")
                return
            data = await r.json()
        coin_balance = int(data.get("coin_balance", 0))
        balance_eth = coin_balance / 1e18
        price_usd = float(data.get("exchange_rate", 0))
        usd_balance = balance_eth * price_usd
        is_contract = data.get("is_contract", False)
        creation_tx = data.get("creation_transaction_hash")
        first_seen_str = "first seen unknown"
        if creation_tx:
            first_seen_str = f"first seen via [creation tx](https://eth.blockscout.com/tx/{creation_tx})"
        async with self.session.get("https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd") as p:
            cg_price = await p.json()
        cg_usd = cg_price.get("ethereum", {}).get("usd", price_usd or 0)
        cg_usd_fmt = f"{cg_usd:,.2f}".rstrip("0").rstrip(".")
        color = await self.bot.get_color(ctx.author.id)
        embed = discord.Embed(
            title="Ethereum Address <:eth:1317321708318752790>",
            url=f"https://eth.blockscout.com/address/{address}",
            description=address,
            color=color
        )
        embed.set_author(
            name=ctx.user.name if interaction else ctx.author.name,
            icon_url=ctx.user.display_avatar.url if interaction else ctx.author.display_avatar.url
        )
        embed.add_field(
            name="Funds",
            value=(f"* Balance: **`{balance_eth:.8f}`** ETH (**{usd_balance:,.2f} USD**)"),
            inline=False
        )
        embed.add_field(
            name="Type",
            value="Smart Contract" if is_contract else "Externally Owned Account (EOA)",
            inline=False
        )
        embed.set_footer(text=f"{first_seen_str} • 1 eth = {cg_usd_fmt.lower()} usd")
        embed.set_thumbnail(url="https://git.cursi.ng/ethereum.png?")
        await ctx.send(embed=embed)

    @ethereum.command(name="price", description="Get the current price of Ethereum", aliases=["p", "value"])
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def ethereum_price(self, ctx: Union[commands.Context, discord.Interaction]):
        interaction = ctx if isinstance(ctx, discord.Interaction) else None
        ctx = await commands.Context.from_interaction(ctx) if interaction else ctx
        async with self.session.get("https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd") as r:
            if r.status != 200:
                await ctx.warn("Failed to fetch price data.")
                return
            data = await r.json()
        eth = data["ethereum"]["usd"]
        ethf = f"{eth:,.2f}".rstrip("0").rstrip(".")
        await ctx.send(f"<:eth:1317321708318752790> is currently valued at **`{ethf}`** USD")

    @ethereum.command(name="chart", description="Generate an Ethereum price chart")
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def ethereum_chart(self, ctx):
        url = "http://127.0.0.1:7685/eth"
        async with self.bot.session.get(url) as r:
            data = await r.json()

        stats = data["stats"]
        img_bytes = bytes.fromhex(data["image"])
        file = discord.File(io.BytesIO(img_bytes), filename="eth.png")
        color = await self.bot.get_color(ctx.author.id)

        await cpv2.send(
            ctx,
            title="<:eth:1317321708318752790> [Ethereum (ETH)](https://www.tradingview.com/symbols/ETHUSD)",
            media_url="attachment://eth.png",
            footer=f"-# {stats['formatted']}",
            color=color,
            files=[file]
        )

    @crypto.group(name="usdt", description="USDT related commands", aliases=["tether"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def usdt(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @usdt.command(name="price", description="Get the current price of USDT", aliases=["p", "value"])
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def usdt_price(self, ctx: Union[commands.Context, discord.Interaction]):
        interaction = ctx if isinstance(ctx, discord.Interaction) else None
        ctx = await commands.Context.from_interaction(ctx) if interaction else ctx
        await ctx.send("https://git.cursi.ng/1dollar.png?meow")

    @commands.hybrid_group(name="qr", description="QR code utilities")
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def qr(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @qr.command(name="generate", description="Generate a QR code", aliases=["create", "make"])
    @app_commands.describe(text="Text to encode in QR")
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def generate_qr(self, ctx: Union[commands.Context, discord.Interaction], *, text: str):
        interaction = ctx if isinstance(ctx, discord.Interaction) else None
        ctx = await commands.Context.from_interaction(ctx) if interaction else ctx
        async with ctx.typing():
            try:
                def make_qr():
                    qr = qrcode.QRCode(
                        version=1,
                        error_correction=qrcode.constants.ERROR_CORRECT_L,
                        box_size=10,
                        border=4,
                    )
                    qr.add_data(text)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="#d3d6f1", back_color="white").convert("RGB")
                    draw = ImageDraw.Draw(img)
                    try:
                        font = ImageFont.truetype("fonts/gg sans semibold.ttf", 20)
                    except:
                        font = ImageFont.load_default()
                    text_width = draw.textlength("HEIST", font=font)
                    position = (img.size[0] - text_width - 20, img.size[1] - 40)
                    draw.text(position, "HEIST", fill="#bec2c4", font=font, stroke_width=2, stroke_fill="#d3d6f1")
                    buffer = io.BytesIO()
                    img.save(buffer, format="PNG")
                    buffer.seek(0)
                    return buffer
                buffer = await asyncio.to_thread(make_qr)
                file = discord.File(buffer, filename="heist.png")
                await ctx.send(file=file)
            except Exception as e:
                await ctx.warn(str(e))

    @qr.command(name="scan", description="Scan a QR code from an image", aliases=["read", "decode"])
    @app_commands.describe(image="Image containing QR code to scan")
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def scan_qr(self, ctx: Union[commands.Context, discord.Interaction], image: discord.Attachment):
        interaction = ctx if isinstance(ctx, discord.Interaction) else None
        ctx = await commands.Context.from_interaction(ctx) if interaction else ctx
        async with ctx.typing():
            try:
                if not image.content_type or not image.content_type.startswith("image/"):
                    await ctx.warn("Please provide a valid image file.")
                    return
                img_data = await image.read()
                def decode_qr(img_bytes):
                    nparr = np.frombuffer(img_bytes, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    decoded_objects = decode(img)
                    if not decoded_objects:
                        return None
                    return decoded_objects[0].data.decode("utf-8")
                result = await asyncio.to_thread(decode_qr, img_data)
                if not result:
                    await ctx.warn("No QR code found in the image.")
                    return
                if len(result) > 1900:
                    with io.StringIO(result) as f:
                        file = discord.File(f, filename="heist_qr.txt")
                        await ctx.send("QR content is too long, sending as file:", file=file)
                        return
                embed = discord.Embed(
                    title="QR Code Content",
                    description=f"```\n{result}\n```",
                    color=await self.bot.get_color(ctx.author.id)
                )
                await ctx.send(embed=embed)
            except Exception as e:
                await ctx.warn(str(e))

    @commands.hybrid_group(name="base64", description="Base64 encoding/decoding utilities")
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def base64(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @base64.command(name="encode", description="Encode a string to Base64", aliases=["en"])
    @app_commands.describe(string="The string to encode")
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def encode(self, ctx: Union[commands.Context, discord.Interaction], *, string: str):
        interaction = ctx if isinstance(ctx, discord.Interaction) else None
        ctx = await commands.Context.from_interaction(ctx) if interaction else ctx
        try:
            encoded_bytes = await asyncio.to_thread(base64.b64encode, string.encode("utf-8"))
            encoded_string = encoded_bytes.decode("utf-8")
            await ctx.send(f"```\n{encoded_string}\n```")
        except Exception as e:
            await ctx.warn(str(e))

    @base64.command(name="decode", description="Decode a Base64 string", aliases=["de"])
    @app_commands.describe(string="The Base64 string to decode")
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def decode(self, ctx: Union[commands.Context, discord.Interaction], *, string: str):
        interaction = ctx if isinstance(ctx, discord.Interaction) else None
        ctx = await commands.Context.from_interaction(ctx) if interaction else ctx
        try:
            missing_padding = len(string) % 4
            if missing_padding:
                string += "=" * (4 - missing_padding)
            decoded_bytes = await asyncio.to_thread(base64.b64decode, string.encode("utf-8"))
            decoded_string = decoded_bytes.decode("utf-8")
            await ctx.send(f"```\n{decoded_string}\n```")
        except base64.binascii.Error:
            await ctx.warn("Invalid Base64 input. Please check the string and try again.")
        except Exception as e:
            await ctx.warn(str(e))

    @commands.hybrid_group(name="soundcloud", description="SoundCloud commands", aliases=["scl"])
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def soundcloud(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @soundcloud.command(name="track", description="Get information about a SoundCloud track", aliases=["t"])
    @app_commands.describe(query="Search query or track URL", stats="Show track statistics?")
    @app_commands.choices(stats=[
        app_commands.Choice(name="Yes", value="yes"),
        app_commands.Choice(name="No", value="no")
    ])
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def track(self, ctx: Union[commands.Context, discord.Interaction], *, query: str, stats: str = "yes"):
        interaction = ctx if isinstance(ctx, discord.Interaction) else None
        ctx = await commands.Context.from_interaction(ctx) if interaction else ctx
        await ctx.typing()
        soundcloud_url_pattern = re.compile(r'^https?://(?:www\.|on\.|m\.)?soundcloud\.com/[\w-]+/[\w-]+(?:\?.*si=[\w-]+.*)?$|^https?://(?:www\.|on\.|m\.)?soundcloud\.com/.+$')
        if not soundcloud_url_pattern.match(query):
            try:
                search_opts = {
                    'extractor_args': {'soundcloud': {'client_id': 'f1TFyuaI8LX1Ybd1zvQRX8GpsNYcQ3Y5'}},
                    'quiet': True,
                    'no_warnings': True,
                    "noprogress": True,
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
                    await ctx.warn("No valid tracks found.")
                    return
                query = first_track['webpage_url']
            except Exception as e:
                await ctx.warn(str(e))
                return
        if '/sets/' in query or '?set=' in query:
            await ctx.warn("Sets and playlists are not supported.")
            return
        url_match = re.search(r'(https?://(?:www\.|on\.|m\.)?soundcloud\.com/[\w-]+/[\w-]+)', query)
        if url_match:
            query = url_match.group(1)
        try:
            file_extension = "mp3"
            timestamp = int(datetime.now().timestamp() * 1000)
            temp_file_path = os.path.join("temp", f"track_{timestamp}.{file_extension}")
            ydl_opts = {
                "format": "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "noprogress": True,
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
                file = discord.File(fp=audio_buffer, filename=f"{sanitized_title}.{file_extension}")
                if stats.lower() == "yes":
                    def format_number(num):
                        if num >= 1_000_000:
                            return f"{num/1_000_000:.1f}M"
                        elif num >= 1_000:
                            return f"{num/1_000:.1f}k"
                        return str(num)
                    desc = f"-# By [**{artist}**]({artist_url})\n-# Duration: **`{durationf}`**" if durationf else ""
                    track_url = info.get('webpage_url', query)
                    embed = discord.Embed(title=title, description=desc, url=track_url, color=await self.bot.get_color(ctx.author.id))
                    embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
                    embed.set_footer(text=f"❤️ {format_number(likes)} • 👁️ {format_number(plays)} • 🔄 {format_number(reposts)} | {fdate}", icon_url="https://git.cursi.ng/soundcloud_logo.png?")
                    embed.set_thumbnail(url=track_cover)
                    await ctx.send(file=file, embed=embed)
                else:
                    await ctx.send(file=file)
            await aiofiles.os.remove(temp_file_path)
        except Exception as e:
            await ctx.warn(str(e))

    @track.autocomplete("query")
    async def track_autocomplete(self, interaction: discord.Interaction, current: str):
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

    @commands.hybrid_command(name="translate", description="Translate text with Google")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(to="Language to translate to (e.g. 'English', 'fr', 'ro')", text="Text to translate")
    async def translate(self, ctx: Union[commands.Context, discord.Interaction], to: str = None, *, text: str = None):
        interaction = ctx if isinstance(ctx, discord.Interaction) else None
        ctx = await commands.Context.from_interaction(ctx) if interaction else ctx

        if interaction:
            await interaction.response.defer(thinking=True)
        else:
            await ctx.typing()

        try:
            if not to and not text and not (ctx.message.reference if not interaction else None):
                await ctx.warn("You must either provide text or reply to a message.")
                return

            if ctx.message.reference and (to is None and text is None):
                referenced_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                text_to_translate = referenced_msg.content or ""
                target_lang_input = "en"
            else:
                if text is None:
                    text_to_translate = to or ""
                    target_lang_input = "en"
                else:
                    text_to_translate = text or ""
                    target_lang_input = (to or "en")

            def normalize_lang(lang: str) -> str | None:
                if not lang:
                    return None
                s = lang.strip().lower()
                if s in GLC.values():
                    return s
                if s in GLC:
                    return GLC[s]
                for name, code in GLC.items():
                    if name.lower() == s:
                        return code
                return None

            target_lang = normalize_lang(target_lang_input)
            if not target_lang:
                await ctx.warn("That language is not supported by Google Translate.")
                return
            if not text_to_translate.strip():
                await ctx.warn("There is no text to translate.")
                return

            async def detect_language(txt: str):
                url = "https://translate.googleapis.com/translate_a/single"
                params = {"client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": txt}
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params) as resp:
                        if resp.status != 200:
                            return "auto"
                        data = await resp.json()
                        return data[2] if len(data) > 2 else "auto"

            detected_code = await detect_language(text_to_translate)

            def do_translate(tgt: str, txt: str):
                translator = GoogleTranslator(source="auto", target=tgt)
                return translator.translate(txt)

            translated_text = await asyncio.to_thread(do_translate, target_lang, text_to_translate)

            if not translated_text:
                await ctx.warn("No translation result available.")
                return

            if len(translated_text) > 2000:
                translated_text = translated_text[:1997] + "..."

            code_to_name = {v: k for k, v in GLC.items()}
            target_name = code_to_name.get(target_lang.lower(), target_lang.upper()).capitalize()
            detected_name = code_to_name.get(detected_code.lower(), "Auto-detected").capitalize()

            embed = discord.Embed(
                title=f"{detected_name} ➜ {target_name}",
                description=translated_text,
                color=await self.bot.get_color(ctx.author.id)
            )
            author = interaction.user if interaction else ctx.author
            embed.set_author(name=author.name, icon_url=author.display_avatar.url)
            embed.set_footer(
                text="translate.google.com",
                icon_url="https://git.cursi.ng/translate_logo.png"
            )
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.warn(str(e))

    @translate.autocomplete("to")
    async def translate_autocomplete(self, interaction: discord.Interaction, current: str):
        current_lower = current.lower() if current else ""
        results = []
        for lang_name, code in GLC.items():
            if current_lower in lang_name.lower() or current_lower in code.lower():
                results.append(app_commands.Choice(name=f"{lang_name.capitalize()} ({code})", value=lang_name))
            if len(results) >= 25:
                break
        return results or [
            app_commands.Choice(name="English (en)", value="English"),
            app_commands.Choice(name="Spanish (es)", value="Spanish"),
            app_commands.Choice(name="Romanian (ro)", value="Romanian"),
            app_commands.Choice(name="French (fr)", value="French"),
            app_commands.Choice(name="German (de)", value="German"),
        ]

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def toenglish(self, ctx: Union[commands.Context, discord.Interaction], message: discord.Message):
        interaction = ctx if isinstance(ctx, discord.Interaction) else None
        ctx = await commands.Context.from_interaction(ctx) if interaction else ctx

        if interaction:
            await interaction.response.defer(thinking=True)
        else:
            await ctx.typing()

        try:
            if message.content:
                text_to_translate = message.content
            elif message.embeds:
                embed = message.embeds[0]
                text_to_translate = (embed.title or "") + " " + (embed.description or "")
            elif message.attachments:
                await ctx.warn("You cannot use this on a message containing images/files.")
                return
            elif message.stickers:
                await ctx.warn("You cannot use this on a message containing stickers.")
                return
            else:
                await ctx.warn("No text available to translate.")
                return

            async def detect_language(txt: str):
                url = "https://translate.googleapis.com/translate_a/single"
                params = {"client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": txt}
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params) as resp:
                        if resp.status != 200:
                            return "auto"
                        data = await resp.json()
                        return data[2] if len(data) > 2 else "auto"

            detected_code = await detect_language(text_to_translate)

            def do_translate(txt: str):
                translator = GoogleTranslator(source="auto", target="en")
                return translator.translate(txt)

            translated_text = await asyncio.to_thread(do_translate, text_to_translate)

            if len(translated_text) > 2000:
                translated_text = translated_text[:1997] + "..."

            code_to_name = {v: k for k, v in GLC.items()}
            detected_name = code_to_name.get(detected_code.lower(), "Auto-detected").capitalize()

            embed = discord.Embed(
                title=f"{detected_name} ➜ English",
                description=translated_text,
                color=await self.bot.get_color(ctx.author.id)
            )
            embed.set_footer(text="translate.google.com", icon_url="https://git.cursi.ng/translate_logo.png")
            embed.set_author(name=message.author, icon_url=message.author.display_avatar.url)
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.warn(str(e))

    async def tag_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        user_id = interaction.user.id
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT tag_name FROM user_tags WHERE user_id = $1 AND tag_name ILIKE $2 LIMIT 25",
                user_id, f"%{current}%"
            )
        return [app_commands.Choice(name=row["tag_name"], value=row["tag_name"]) for row in rows]

    @tags.command(name="create", description="Create a tag")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(tag="The name of the tag", text="The text to display on the tag")
    async def create(self, interaction: discord.Interaction, tag: str, *, text: str):
        ctx = await self.bot.get_context(interaction)
        async with ctx.typing():
            try:
                if len(tag) > 50 or len(text) > 2000:
                    await ctx.warn("Tag name or text is too long. (Max: 50 chars for name, 2000 chars for text)")
                    return
                
                text = text.replace(r'\n', '\n')

                user_id = ctx.author.id
                is_donor = await check_donor(self.bot, ctx.author.id)
                max_tags = 20 if is_donor else 5
                
                async with self.bot.pool.acquire() as conn:
                    tag_count = await conn.fetchval("SELECT COUNT(*) FROM user_tags WHERE user_id = $1", user_id)
                    
                    if tag_count >= max_tags:
                        premiumbuy = await CommandCache.get_mention(self.bot, "premium buy")
                        limit_msg = f"You have reached your tag limit (**`{max_tags}`**).\nUpgrade to Premium for up to **`20`** tags. {premiumbuy}" if not is_donor else f"You have reached your maximum tag limit ({max_tags})."
                        await ctx.warn(limit_msg)
                        return
                        
                    cache_key = f"tags:{user_id}:{tag}"
                    cached_tag = await self.bot.redis.get(cache_key)
                    
                    if cached_tag:
                        await ctx.warn(f"Tag **{tag}** already exists.")
                        return

                    try:
                        await conn.execute("INSERT INTO user_tags (user_id, tag_name, tag_text) VALUES ($1, $2, $3)", user_id, tag, text)
                        await self.bot.redis.setex(cache_key, 604800, text)
                        await ctx.approve(f"Tag **{tag}** created successfully.")
                    except Exception as e:
                        await ctx.warn(f"Tag **{tag}** already exists.")
            except Exception as e:
                await ctx.warn(str(e))

    @tags.command()
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(tag="The name of the tag to send")
    @app_commands.autocomplete(tag=tag_autocomplete)
    async def send(self, interaction: discord.Interaction, tag: str):
        """Send a tag"""
        ctx = await self.bot.get_context(interaction)
        async with ctx.typing():
            try:
                user_id = ctx.author.id
                cache_key = f"tags:{user_id}:{tag}"

                cached_text = await self.bot.redis.get(cache_key)
                if cached_text:
                    await ctx.send(cached_text)
                    return

                async with self.bot.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT tag_text FROM user_tags WHERE user_id = $1 AND tag_name = $2",
                        user_id, tag
                    )
                    if not row:
                        await ctx.warn(f"Tag **{tag}** does not exist.")
                        return

                    tag_text = row["tag_text"]
                    await self.bot.redis.setex(cache_key, 604800, tag_text)
                    await ctx.send(tag_text)
            except Exception as e:
                await ctx.warn(str(e))

    @tags.command(name="delete", description="Delete a tag")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(tag="The name of the tag to delete")
    @app_commands.autocomplete(tag=tag_autocomplete)
    async def delete(self, interaction: discord.Interaction, tag: str):
        """Delete a tag"""
        ctx = await self.bot.get_context(interaction)
        async with ctx.typing():
            try:
                user_id = ctx.author.id
                cache_key = f"tags:{user_id}:{tag}"
                
                async with self.bot.pool.acquire() as conn:
                    result = await conn.execute(
                        "DELETE FROM user_tags WHERE user_id = $1 AND tag_name = $2",
                        user_id, tag
                    )
                    if result == "DELETE 0":
                        await ctx.warn(f"Tag **{tag}** does not exist.")
                        return

                    await self.bot.redis.delete(cache_key)
                    await ctx.approve(f"Tag **{tag}** deleted successfully.")
            except Exception as e:
                await ctx.warn(str(e))

    @tags.command(name="edit", description="Edit a tag")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(tag="The name of the tag to edit")
    @app_commands.autocomplete(tag=tag_autocomplete)
    async def edit(self, interaction: discord.Interaction, tag: str):
        """Edit a tag"""
        ctx = await self.bot.get_context(interaction)
        try:
            class TagEditModal(discord.ui.Modal):
                def __init__(self, bot: commands.Bot, tag_name: str, tag_text: str):
                    super().__init__(title=f"Edit Tag: {tag_name}")
                    self.bot = bot
                    self.tag_name = tag_name

                    self.text_input = discord.ui.TextInput(
                        label="Edit your tag text",
                        default=tag_text,
                        required=True,
                        max_length=2000,
                        style=discord.TextStyle.paragraph,
                    )
                    self.add_item(self.text_input)

                async def on_submit(self, interaction: Interaction):
                    tag_text = self.text_input.value
                    user_id = interaction.user.id
                    cache_key = f"tags:{user_id}:{self.tag_name}"

                    async with self.bot.pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE user_tags SET tag_text = $1 WHERE user_id = $2 AND tag_name = $3",
                            tag_text, user_id, self.tag_name
                        )
                        await self.bot.redis.setex(cache_key, 604800, tag_text)

                    await interaction.response.send_message(f"Tag **{self.tag_name}** updated successfully!", ephemeral=True)

            user_id = ctx.author.id

            async with self.bot.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT tag_text FROM user_tags WHERE user_id = $1 AND tag_name = $2",
                    user_id, tag
                )
                if not row:
                    await ctx.warn(f"Tag **{tag}** does not exist.")
                    return

                tag_text = row["tag_text"]

            modal = TagEditModal(bot=self.bot, tag_name=tag, tag_text=tag_text)
            await ctx.interaction.response.send_modal(modal)
        except Exception as e:
            await ctx.warn(str(e))

    @tags.command(name="list", description="List all your tags")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def list(self, interaction: discord.Interaction):
        """List all your tags"""
        ctx = await self.bot.get_context(interaction)
        async with ctx.typing():
            try:
                user_id = ctx.author.id
                
                async with self.bot.pool.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT tag_name, tag_text FROM user_tags WHERE user_id = $1 ORDER BY tag_name",
                        user_id
                    )
                    
                    if not rows:
                        await ctx.warn("You don't have any tags.")
                        return
                    
                    is_donor = await check_donor(self.bot, ctx.author.id)
                    max_tags = 20 if is_donor else 5
                    
                    description = ""
                    for row in rows:
                        tag_name = row["tag_name"]
                        tag_text = row["tag_text"]
                        
                        if len(tag_text) > 20:
                            tag_text = tag_text[:20] + "..."
                        
                        description += f"**{tag_name}** - {tag_text}\n"
                    
                    embed = discord.Embed(
                        description=description,
                        color=await self.bot.get_color(ctx.author.id)
                    )
                    
                    embed.set_author(
                        name=f"{ctx.author.display_name}'s tags",
                        icon_url=ctx.author.display_avatar.url
                    )
                    
                    embed.set_footer(text=f"Using {len(rows)}/{max_tags} tags" + (" (premium)" if is_donor else ""))
                    
                    await ctx.send(embed=embed)
            except Exception as e:
                await ctx.warn(str(e))
    async def timezone_autocomplete(self, interaction: discord.Interaction, current: str):
        popular_timezones = [
            "Europe/Berlin",
            "Europe/Madrid",
            "Europe/Warsaw",
            "Europe/Bucharest",
            "Europe/Paris",
            "Europe/London",
            "Europe/Rome",
            "America/New_York",
            "America/Los_Angeles",
            "America/Chicago",
            "Asia/Shanghai",
            "Asia/Tokyo",
            "Asia/Dubai",
        ]

        country2capital = {
            "Afghanistan": "Asia/Kabul", "Albania": "Europe/Tirane", "Algeria": "Africa/Algiers", "Andorra": "Europe/Andorra",
            "Angola": "Africa/Luanda", "Antigua and Barbuda": "America/Antigua", "Argentina": "America/Argentina/Buenos_Aires",
            "Armenia": "Asia/Yerevan", "Australia": "Australia/Sydney", "Austria": "Europe/Vienna", "Azerbaijan": "Asia/Baku",
            "Bahamas": "America/Nassau", "Bahrain": "Asia/Bahrain", "Bangladesh": "Asia/Dhaka", "Barbados": "America/Barbados",
            "Belarus": "Europe/Minsk", "Belgium": "Europe/Brussels", "Belize": "America/Belize", "Benin": "Africa/Porto-Novo",
            "Bhutan": "Asia/Thimphu", "Bolivia": "America/La_Paz", "Bosnia and Herzegovina": "Europe/Sarajevo",
            "Botswana": "Africa/Gaborone", "Brazil": "America/Sao_Paulo", "Brunei": "Asia/Brunei", "Bulgaria": "Europe/Sofia",
            "Burkina Faso": "Africa/Ouagadougou", "Burundi": "Africa/Bujumbura", "Cabo Verde": "Atlantic/Cape_Verde",
            "Cambodia": "Asia/Phnom_Penh", "Cameroon": "Africa/Douala", "Canada": "America/Toronto",
            "Central African Republic": "Africa/Bangui", "Chad": "Africa/Ndjamena", "Chile": "America/Santiago",
            "China": "Asia/Shanghai", "Colombia": "America/Bogota", "Comoros": "Indian/Comoro", "Congo": "Africa/Brazzaville",
            "Costa Rica": "America/Costa_Rica", "Croatia": "Europe/Zagreb", "Cuba": "America/Havana", "Cyprus": "Asia/Nicosia",
            "Czech Republic": "Europe/Prague", "Denmark": "Europe/Copenhagen", "Djibouti": "Africa/Djibouti",
            "Dominica": "America/Dominica", "Dominican Republic": "America/Santo_Domingo", "Ecuador": "America/Guayaquil",
            "Egypt": "Africa/Cairo", "El Salvador": "America/El_Salvador", "Equatorial Guinea": "Africa/Malabo",
            "Eritrea": "Africa/Asmara", "Estonia": "Europe/Tallinn", "Eswatini": "Africa/Mbabane", "Ethiopia": "Africa/Addis_Ababa",
            "Fiji": "Pacific/Fiji", "Finland": "Europe/Helsinki", "France": "Europe/Paris", "Gabon": "Africa/Libreville",
            "Gambia": "Africa/Banjul", "Georgia": "Asia/Tbilisi", "Germany": "Europe/Berlin", "Ghana": "Africa/Accra",
            "Greece": "Europe/Athens", "Grenada": "America/Grenada", "Guatemala": "America/Guatemala", "Guinea": "Africa/Conakry",
            "Guinea-Bissau": "Africa/Bissau", "Guyana": "America/Guyana", "Haiti": "America/Port-au-Prince",
            "Honduras": "America/Tegucigalpa", "Hungary": "Europe/Budapest", "Iceland": "Atlantic/Reykjavik",
            "India": "Asia/Kolkata", "Indonesia": "Asia/Jakarta", "Iran": "Asia/Tehran", "Iraq": "Asia/Baghdad",
            "Ireland": "Europe/Dublin", "Israel": "Asia/Jerusalem", "Italy": "Europe/Rome", "Jamaica": "America/Jamaica",
            "Japan": "Asia/Tokyo", "Jordan": "Asia/Amman", "Kazakhstan": "Asia/Almaty", "Kenya": "Africa/Nairobi",
            "Kiribati": "Pacific/Tarawa", "Korea, North": "Asia/Pyongyang", "Korea, South": "Asia/Seoul", "Kosovo": "Europe/Belgrade",
            "Kuwait": "Asia/Kuwait", "Kyrgyzstan": "Asia/Bishkek", "Laos": "Asia/Vientiane", "Latvia": "Europe/Riga",
            "Lebanon": "Asia/Beirut", "Lesotho": "Africa/Maseru", "Liberia": "Africa/Monrovia", "Libya": "Africa/Tripoli",
            "Liechtenstein": "Europe/Vaduz", "Lithuania": "Europe/Vilnius", "Luxembourg": "Europe/Luxembourg",
            "Madagascar": "Indian/Antananarivo", "Malawi": "Africa/Blantyre", "Malaysia": "Asia/Kuala_Lumpur",
            "Maldives": "Indian/Maldives", "Mali": "Africa/Bamako", "Malta": "Europe/Malta", "Marshall Islands": "Pacific/Majuro",
            "Mauritania": "Africa/Nouakchott", "Mauritius": "Indian/Mauritius", "Mexico": "America/Mexico_City",
            "Micronesia": "Pacific/Pohnpei", "Moldova": "Europe/Chisinau", "Monaco": "Europe/Monaco", "Mongolia": "Asia/Ulaanbaatar",
            "Montenegro": "Europe/Podgorica", "Morocco": "Africa/Casablanca", "Mozambique": "Africa/Maputo", "Myanmar": "Asia/Yangon",
            "Namibia": "Africa/Windhoek", "Nauru": "Pacific/Nauru", "Nepal": "Asia/Kathmandu", "Netherlands": "Europe/Amsterdam",
            "New Zealand": "Pacific/Auckland", "Nicaragua": "America/Managua", "Niger": "Africa/Niamey", "Nigeria": "Africa/Lagos",
            "North Macedonia": "Europe/Skopje", "Norway": "Europe/Oslo", "Oman": "Asia/Muscat", "Pakistan": "Asia/Karachi",
            "Palau": "Pacific/Palau", "Panama": "America/Panama", "Papua New Guinea": "Pacific/Port_Moresby", "Paraguay": "America/Asuncion",
            "Peru": "America/Lima", "Philippines": "Asia/Manila", "Poland": "Europe/Warsaw", "Portugal": "Europe/Lisbon",
            "Qatar": "Asia/Qatar", "Romania": "Europe/Bucharest", "Russia": "Europe/Moscow", "Rwanda": "Africa/Kigali",
            "Saint Kitts and Nevis": "America/St_Kitts", "Saint Lucia": "America/St_Lucia", "Saint Vincent and the Grenadines": "America/St_Vincent",
            "Samoa": "Pacific/Apia", "San Marino": "Europe/San_Marino", "Sao Tome and Principe": "Africa/Sao_Tome", "Saudi Arabia": "Asia/Riyadh",
            "Senegal": "Africa/Dakar", "Serbia": "Europe/Belgrade", "Seychelles": "Indian/Mahe", "Sierra Leone": "Africa/Freetown",
            "Singapore": "Asia/Singapore", "Slovakia": "Europe/Bratislava", "Slovenia": "Europe/Ljubljana", "Solomon Islands": "Pacific/Guadalcanal",
            "Somalia": "Africa/Mogadishu", "South Africa": "Africa/Johannesburg", "South Sudan": "Africa/Juba", "Spain": "Europe/Madrid",
            "Sri Lanka": "Asia/Colombo", "Sudan": "Africa/Khartoum", "Suriname": "America/Paramaribo", "Sweden": "Europe/Stockholm",
            "Switzerland": "Europe/Zurich", "Syria": "Asia/Damascus", "Taiwan": "Asia/Taipei", "Tajikistan": "Asia/Dushanbe",
            "Tanzania": "Africa/Dar_es_Salaam", "Thailand": "Asia/Bangkok", "Timor-Leste": "Asia/Dili", "Togo": "Africa/Lome",
            "Tonga": "Pacific/Tongatapu", "Trinidad and Tobago": "America/Port_of_Spain", "Tunisia": "Africa/Tunis", "Turkey": "Europe/Istanbul",
            "Turkmenistan": "Asia/Ashgabat", "Tuvalu": "Pacific/Funafuti", "Uganda": "Africa/Kampala", "Ukraine": "Europe/Kiev",
            "United Arab Emirates": "Asia/Dubai", "United Kingdom": "Europe/London", "United States": "America/New_York", "Uruguay": "America/Montevideo",
            "Uzbekistan": "Asia/Tashkent", "Vanuatu": "Pacific/Efate", "Vatican City": "Europe/Vatican", "Venezuela": "America/Caracas",
            "Vietnam": "Asia/Ho_Chi_Minh", "Yemen": "Asia/Aden", "Zambia": "Africa/Lusaka", "Zimbabwe": "Africa/Harare"
        }

        if not current:
            return [app_commands.Choice(name=tz, value=tz) for tz in sorted(popular_timezones)]
        all_timezones = pytz.all_timezones
        filtered_timezones = [tz for tz in all_timezones if current.lower() in tz.lower()]
        return [app_commands.Choice(name=tz, value=tz) for tz in sorted(filtered_timezones)[:25]]

    @commands.hybrid_group(name="timezone", description="Timezone related commands")
    @app_commands.allowed_installs(users=True, guilds=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def timezone(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @timezone.command(name="view", description="View the current time for a timezone or user")
    @app_commands.describe(timezone="The timezone to get the current time for", user="The user to check the timezone for")
    @app_commands.autocomplete(timezone=timezone_autocomplete)
    @app_commands.allowed_installs(users=True, guilds=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def view(self, ctx: commands.Context, timezone: str = None, user: discord.User = None):
        if timezone and user:
            await ctx.warn("You cannot specify both a timezone and a user at the same time.")
            return
        if timezone:
            try:
                tz = pytz.timezone(timezone)
                current_time = datetime.now(tz)
                formatted_time = current_time.strftime("%I:%M %p")
                formatted_date = current_time.strftime("%d %B, %Y")
                color = await self.bot.get_color(ctx.author.id)
                embed = discord.Embed(description=f"⌚ **{timezone}**: {formatted_time} ({formatted_date})", color=color)
                await ctx.send(embed=embed)
            except pytz.UnknownTimeZoneError:
                await ctx.warn("Invalid timezone! Use format like `America/New_York`, `Europe/London`, `Asia/Tokyo`\n\nFind your timezone: <https://en.wikipedia.org/wiki/List_of_tz_database_time_zones>")
            except Exception as e:
                await ctx.warn(str(e))
        else:
            target_user_id = user.id if user else ctx.author.id
            try:
                result = await self.bot.pool.fetchrow("SELECT timezone FROM timezones WHERE user_id = $1", target_user_id)
                if result and result['timezone']:
                    timezone = result['timezone']
                    tz = pytz.timezone(timezone)
                    current_time = datetime.now(tz)
                    formatted_time = current_time.strftime("%I:%M %p")
                    formatted_date = current_time.strftime("%d %B, %Y")
                    color = await self.bot.get_color(ctx.author.id)
                    embed = discord.Embed(description=f"⌚ **{timezone}**: {formatted_time} ({formatted_date})", color=color)
                    await ctx.send(embed=embed)
                else:
                    username = user.display_name if user else ctx.author.display_name
                    await ctx.warn(f"{username} doesn't have their timezone set.")
            except Exception as e:
                await ctx.warn(str(e))

    @timezone.command(name="set", description="Set your timezone")
    @app_commands.describe(timezone="The timezone to set for your profile")
    @app_commands.autocomplete(timezone=timezone_autocomplete)
    @app_commands.allowed_installs(users=True, guilds=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def set(self, ctx: commands.Context, timezone: str):
        try:
            tz = pytz.timezone(timezone)
            user_id = ctx.author.id
            await self.bot.pool.execute("""
                INSERT INTO timezones (user_id, timezone)
                VALUES ($1, $2)
                ON CONFLICT (user_id)
                DO UPDATE SET timezone = EXCLUDED.timezone
            """, user_id, timezone)
            await ctx.approve(f"Your timezone has been set to **{timezone}**.", ephemeral=True)
        except pytz.UnknownTimeZoneError:
            await ctx.warn("Invalid timezone! Use format like `America/New_York`, `Europe/London`, `Asia/Tokyo`\n\nFind your timezone: <https://en.wikipedia.org/wiki/List_of_tz_database_time_zones>")
        except Exception as e:
            await ctx.warn(str(e))

    @commands.hybrid_command(name="screenshot", description="✨ Take a screenshot of a website")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(url="The URL you want to take a screenshot from", delay="Seconds to allocate for loading the website")
    async def screenshot(self, ctx: commands.Context, url: str, delay: str = "0"):
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"

        try:
            delay = int(delay)
            if delay > 15:
                await ctx.warn("Delay cannot be more than 15 seconds.")
                return
        except ValueError:
            await ctx.warn("Invalid delay input. Please enter a valid number up to 15.")
            return

        dtext = f" (+{delay} seconds delay)" if delay > 0 else ""
        loading_embed = discord.Embed(
            description=f"-# <a:dotsload:1423056880854499338> {ctx.author.mention}: rendering website..{dtext}",
            color=await self.bot.get_color(ctx.author.id)
        )

        message = await ctx.send(embed=loading_embed)
        screen = f"http://127.0.0.1:5008/screenshot?url={url}&delay={delay}"

        try:
            async with self.session.get(screen) as response:
                if response.status == 200:
                    screenshot_bytes = await response.read()
                    screenshot_file = discord.File(BytesIO(screenshot_bytes), filename="screenshot.png")
                    await message.edit(content=None, embed=None, attachments=[screenshot_file])
                else:
                    await ctx.edit_warn(f"Failed to fetch screenshot: {response.status} - {response.reason}", message)
        except Exception as e:
            await ctx.edit_warn(str(e), message)

    @commands.hybrid_command(name="bypass", description="Bypass a URL")
    @app_commands.describe(url="The URL you want to bypass")
    @app_commands.allowed_installs(users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def bypass(self, ctx: commands.Context, url: str):
        await ctx.typing()

        try:
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url

            lower = url.lower()

            if "flux.li" in lower or "fluxus" in lower:
                api = f"http://localhost:1117/api/fluxus?link={urllib.parse.quote(url)}"

                async with self.session.get(api) as resp:
                    data = await resp.json()

                if data.get("status") == "success":
                    return await ctx.approve(data.get("key"))

                return await ctx.warn("Failed to bypass Fluxus.")

            api_url = f"https://api.bypass.vip/premium/bypass?url={urllib.parse.quote(url)}"
            headers = {"x-api-key": BYPASSVIP_KEY}

            async with self.session.get(api_url, headers=headers) as resp:
                data = await resp.json()

            if data.get("status") == "success":
                return await ctx.approve(data.get("result"))

            await ctx.warn("Failed to bypass URL.")

        except Exception as e:
            await ctx.warn(str(e))

    @commands.hybrid_group(name="ip", description="IP info related commands")
    @app_commands.allowed_installs(users=True, guilds=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def ip(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @ip.command(name="ping", description="Ping a host from global locations")
    @app_commands.describe(host="IP address or domain to ping")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def ping(self, ctx: commands.Context, host: str):
        try:
            import re

            raw_host = host.strip()

            if raw_host.startswith("http://"):
                query_host = raw_host[7:].split("/")[0]
            elif raw_host.startswith("https://"):
                query_host = raw_host[8:].split("/")[0]
            else:
                query_host = raw_host

            ipv4_pattern = r"^\d{1,3}(?:\.\d{1,3}){3}$"
            if raw_host.startswith("http://") or raw_host.startswith("https://") or re.match(ipv4_pattern, query_host):
                title_host = raw_host
            else:
                title_host = f"https://{query_host}"

            color = await self.bot.get_color(ctx.author.id)

            msg = await cpv2.send(
                ctx,
                content=f"## 🌐 Scanning host..\nPinging **{title_host}** <a:dotsload:1423056880854499338>",
                color=color
            )

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://check-host.net/check-ping",
                    params={"host": query_host},
                    headers={"Accept": "application/json"}
                ) as r:
                    if r.status != 200:
                        return await cpv2.edit_warn(msg, ctx, f"Ping request failed with status `{r.status}`.")
                    data = await r.json()

                request_id = data.get("request_id")
                nodes_meta = data.get("nodes") or {}

                if not request_id or not nodes_meta:
                    return await cpv2.edit_warn(msg, ctx, "Unable to start ping check for that host.")

                await asyncio.sleep(1)

                results = None
                for _ in range(3):
                    async with session.get(
                        f"https://check-host.net/check-result/{request_id}",
                        headers={"Accept": "application/json"}
                    ) as r:
                        if r.status != 200:
                            break
                        results = await r.json()

                    if isinstance(results, dict):
                        all_ready = True
                        for node_id in nodes_meta:
                            val = results.get(node_id)
                            if val is None:
                                all_ready = False
                                break
                            if isinstance(val, list) and len(val) > 0:
                                if all(x is None for x in val):
                                    all_ready = False
                                    break
                        if all_ready:
                            break

                    await asyncio.sleep(0.7)

            if not isinstance(results, dict) or not results:
                return await cpv2.edit_warn(msg, ctx, "No ping results were returned.")

            lines = []
            success_count = 0
            fail_count = 0
            total_nodes = 0

            for node_id, meta in nodes_meta.items():
                total_nodes += 1
                country_code = (meta[0] or "").lower()
                country_name = meta[1] or "Unknown"
                city = meta[2] or "Unknown"
                flag = f":flag_{country_code}:" if country_code else "🌐"

                node_result = results.get(node_id)

                times = []

                if isinstance(node_result, list):
                    for group in node_result:
                        if not isinstance(group, list):
                            continue
                        for ping in group:
                            if not isinstance(ping, list) or len(ping) < 2:
                                continue
                            status = ping[0]
                            latency = ping[1]
                            if status == "OK":
                                try:
                                    times.append(float(latency))
                                except:
                                    pass

                if times:
                    avg_ms = (sum(times) / len(times)) * 1000.0
                    success_count += 1
                    latency_str = f"{avg_ms:.2f}ms"
                    line = f"{flag} **{city} - {country_name}**: <:c_:1441253265151885343> `{latency_str}`"
                else:
                    fail_count += 1
                    line = f"{flag} **{city} - {country_name}**: <:no:1423109075083989062>"

                lines.append(line)

            if not lines:
                return await cpv2.edit_warn(msg, ctx, "No ping data was available from any node.")

            content = "\n".join(lines)

            while len(content) > 3800 and lines:
                lines.pop()
                content = "\n".join(lines)

            footer = (
                f"**Summary:** {success_count} successful, {fail_count} failed\n"
                f"-# Results from {total_nodes} global locations | "
                f"[Check Report](https://check-host.net/check-report/{request_id})"
            )

            await cpv2.edit(
                msg,
                ctx,
                title=f"**Ping Results for {title_host}**",
                content=content,
                color=color,
                footer=footer,
            )

        except Exception as e:
            await cpv2.edit_warn(msg, ctx, str(e))

    @ip.command(name="lookup", description="Lookup an IP address (IPv4)", aliases=["ipv4", "ipinfo"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(ip="The IP address to look up")
    async def lookup(self, ctx: commands.Context, ip: str):
        await ctx.typing()

        if ip in {".", "localhost", "127.0.0.1"}:
            await ctx.warn("nuh uh.")
            return

        IP = re.compile(
            r"^(?!0)(?!.*\.$)(?!.*\.\.)(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
        )

        if not IP.match(ip):
            await ctx.warn("The IP address is not valid. Please enter a valid IPv4 address.")
            return

        try:
            url = f"http://ip-api.com/json/{ip}?fields=status,message,continent,continentCode,country,countryCode,region,regionName,city,zip,lat,lon,timezone,isp,org,as,mobile,proxy"
            async with self.session.get(url) as response:
                data = await response.json()

                if data.get("status") != "success":
                    return await ctx.warn("You cannot do this because: " + data.get("message", "Unknown error occurred"))

                continent = f"{data['continent']} ({data['continentCode']})"
                country = f"{data['country']} ({data['countryCode']})"
                region = f"{data['regionName']} ({data['region']})"
                city = data['city']
                zip_code = data['zip']
                latitude = data['lat']
                longitude = data['lon']
                timezone = data['timezone']
                isp = data['isp']
                organization = data['org']
                as_number = data['as']
                mobile = "Yes" if data['mobile'] else "No"
                proxy = "Yes" if data['proxy'] else "No"
                embed = discord.Embed(title=f"IP Lookup: {ip}", color=await self.bot.get_color(ctx.author.id))
                embed.add_field(name="Continent", value=continent, inline=True)
                embed.add_field(name="Country", value=country, inline=True)
                embed.add_field(name="Region", value=region, inline=True)
                embed.add_field(name="City", value=city, inline=True)
                embed.add_field(name="Zip Code", value=zip_code, inline=True)
                embed.add_field(name="Latitude", value=latitude, inline=True)
                embed.add_field(name="Longitude", value=longitude, inline=True)
                embed.add_field(name="Timezone", value=timezone, inline=True)
                embed.add_field(name="ISP", value=isp, inline=True)
                embed.add_field(name="Organization", value=organization, inline=True)
                embed.add_field(name="AS Number", value=as_number, inline=True)
                embed.add_field(name="Proxy", value=proxy, inline=True)
                embed.set_author(name=f"{ctx.author.name}", icon_url=ctx.author.display_avatar.url)

                await ctx.send(embed=embed)

        except Exception as e:
            await ctx.warn(e)

async def setup(bot):
    await bot.add_cog(Utility(bot))