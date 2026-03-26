from __future__ import annotations

import io
import time
from datetime import datetime
from re import match
from typing import Any

import aiohttp
import discord
import edge_tts
import humanize
from discord import app_commands
from discord.ext import commands
from shazamio import Shazam

from bot.helpers.context import TormentContext, _color
from bot.helpers.converters.script.main import Script


class Miscellaneous(commands.Cog):
    __cog_name__ = "miscellaneous"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def storage(self):
        return self.bot.storage

    @commands.command(
        name="afk",
        help="Display your AFK message",
        extras={"parameters": "reason", "usage": "afk [reason]"},
    )
    async def afk(self, ctx: TormentContext, *, reason: str = "AFK") -> None:
        current_time = datetime.now()
        async with self.storage.pool.acquire() as conn:
            await conn.execute("DELETE FROM afk WHERE user_id = $1", ctx.author.id)
            await conn.execute(
                "INSERT INTO afk (user_id, guild_id, time, status) VALUES ($1, $2, $3, $4)",
                ctx.author.id,
                ctx.guild.id if ctx.guild else 0,
                current_time,
                reason,
            )
        await ctx.success(f"You have gone **AFK** with status: **{reason}**")

    @commands.Cog.listener("on_message")
    async def afk_listener(self, message: discord.Message) -> None:
        if message.author == self.bot.user or not message.guild:
            return

        db = await self.storage.pool.fetchrow(
            "SELECT prefix FROM prefix WHERE guild_id = $1", message.guild.id
        )
        prefix = db["prefix"] if db else ","

        if message.content.strip().startswith(prefix + "afk"):
            return

        afk_data = await self.storage.pool.fetchrow(
            "SELECT status, time FROM afk WHERE user_id = $1", message.author.id
        )
        if afk_data:
            status, start_time = afk_data["status"], afk_data["time"]
            if isinstance(start_time, int):
                start_time = datetime.fromtimestamp(start_time)
            now = datetime.now()
            time_away = humanize.naturaldelta(now - start_time)
            await self.storage.pool.execute(
                "DELETE FROM afk WHERE user_id = $1", message.author.id
            )
            embed = discord.Embed(
                description=f"👋 {message.author.mention}: Welcome back, you were away for **{time_away}**",
                color=_color("EMBED_INFO_COLOR"),
            )
            await message.channel.send(embed=embed)

        if message.mentions:
            for user in message.mentions:
                afk_data = await self.storage.pool.fetchrow(
                    "SELECT status, time FROM afk WHERE user_id = $1", user.id
                )
                if afk_data:
                    status, start_time = afk_data["status"], afk_data["time"]
                    if isinstance(start_time, int):
                        start_time = datetime.fromtimestamp(start_time)
                    now = datetime.now()
                    time_away = humanize.naturaldelta(now - start_time)
                    embed = discord.Embed(
                        description=f"💤 {user.mention}: is AFK: **{status}** - **{time_away}**",
                        color=_color("EMBED_INFO_COLOR"),
                    )
                    await message.channel.send(embed=embed)

    @commands.command(
        name="urban",
        aliases=["urbandictionary"],
        help="Lookup a word on urban dictionary",
        extras={"parameters": "word", "usage": "urban (word)"},
    )
    async def urban(self, ctx: TormentContext, *, word: str) -> None:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://api.urbandictionary.com/v0/define?term={word}"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    definitions = data.get("list", [])

                    if not definitions:
                        return await ctx.warn("No definitions found for that word.")

                    embeds = []
                    total_entries = len(definitions)

                    for definition in definitions:
                        embed = discord.Embed(
                            title=f"{word}",
                            description=definition.get("definition", "No definition found."),
                            color=_color("EMBED_INFO_COLOR"),
                        )
                        embed.add_field(
                            name="Example",
                            value=definition.get("example", "No example found."),
                            inline=False,
                        )
                        embed.set_footer(
                            text=f"👍 {definition.get('thumbs_up', 0)} • 👎 {definition.get('thumbs_down', 0)} • entries: {total_entries}"
                        )
                        embeds.append(embed)

                    await ctx.paginate(embeds)
                else:
                    await ctx.warn("Failed to retrieve data from Urban Dictionary.")

    @commands.hybrid_command(
        name="screenshot",
        aliases=["ss"],
        help="Screenshot a website",
        extras={"parameters": "url [delay]", "usage": "screenshot (url) [delay]"},
    )
    @app_commands.describe(
        url="The website URL to screenshot",
        delay="Delay in seconds before taking screenshot (0-10)"
    )
    async def screenshot(self, ctx: TormentContext, url: str, delay: int = 0) -> None:
        target_url = url
        delay_seconds = delay

        if not match(r"^(http://|https://)", target_url):
            target_url = f"https://{target_url}"

        if delay_seconds < 0 or delay_seconds > 10:
            return await ctx.warn("Delay must be between 0 and 10 seconds")

        start_time = time.time()
        await ctx.typing()

        try:
            params = {
                "access_key": "1bf7e81612b840028d27ef8f18319bef",
                "url": target_url,
                "format": "png",
                "width": 1920,
                "height": 1080,
                "full_page": "false",
                "fresh": "true",
                "quality": 100,
                "response_type": "image"
            }

            if delay_seconds > 0:
                params["delay"] = delay_seconds

            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.apiflash.com/v1/urltoimage", params=params) as response:
                    if response.status != 200:
                        return await ctx.warn(f"Failed to get screenshot: HTTP {response.status}")

                    screenshot_data = await response.read()

            screenshot_buffer = io.BytesIO(screenshot_data)
            screenshot_buffer.seek(0)

            exe_time = time.time() - start_time

            embed = discord.Embed(color=_color("EMBED_INFO_COLOR"))
            embed.set_image(url="attachment://screenshot.png")
            embed.set_footer(text=f"⏰ took {exe_time:.2f} seconds" + (f" (delay: {delay_seconds}s)" if delay_seconds > 0 else ""))
            embed.set_author(
                name=ctx.author.display_name,
                icon_url=ctx.author.display_avatar.url,
            )

            return await ctx.send(
                embed=embed,
                file=discord.File(screenshot_buffer, filename="screenshot.png"),
            )
        except Exception as e:
            await ctx.warn(f"Failed to get screenshot: `{e}`")

    @commands.command(
        name="shazam",
        help="Get a song from a video",
        extras={"parameters": "n/a", "usage": "shazam"},
    )
    async def shazam(self, ctx: TormentContext) -> None:
        if ctx.message.reference:
            ref_message = await ctx.channel.fetch_message(
                ctx.message.reference.message_id
            )
            if ref_message.attachments:
                attachment = ref_message.attachments[0]
            else:
                await ctx.warn(
                    "The replied-to message does not contain a video or audio file."
                )
                return
        elif ctx.message.attachments:
            attachment = ctx.message.attachments[0]
        else:
            await ctx.warn("Please provide a video or audio file.")
            return

        if not (
            attachment.content_type.startswith("audio/")
            or attachment.content_type.startswith("video/")
        ):
            await ctx.warn("The provided file is not an audio or video file.")
            return

        async with ctx.typing():
            audio_data = await attachment.read()
            shazam = Shazam()
            try:
                song = await shazam.recognize(audio_data)
                if "track" not in song or "share" not in song["track"]:
                    return await ctx.send("Could not recognize the track.")

                embed = discord.Embed(
                    description=f"🎵 {ctx.author.mention}: Found **[{song['track']['share']['text']}]({song['track']['share']['href']})**",
                    color=0x38A9E1,
                )
                return await ctx.send(embed=embed)
            except Exception as e:
                return await ctx.warn(f"An error occurred: **{e}**")

    @commands.command(
        name="createembed",
        aliases=["ce", "script"],
        help="Create an embed using script syntax",
        extras={"parameters": "script", "usage": "createembed (script)"},
    )
    @commands.has_permissions(manage_messages=True)
    async def createembed(self, ctx: TormentContext, *, script: Script = None) -> None:
        if script is None:
            return await ctx.warn("Enter embed script.")

        data = script.data
        return await ctx.send(
            content=data.get("content"),
            embeds=data.get("embeds", []),
            view=data.get("view"),
        )

    @commands.command(
        name="pin",
        help="Pin a message",
        extras={"parameters": "message", "usage": "pin [message]"},
    )
    @commands.has_permissions(manage_messages=True)
    async def pin(self, ctx: TormentContext, *, message: str = None) -> None:
        target_message = None
        if ctx.message.reference:
            target_message = await ctx.channel.fetch_message(
                ctx.message.reference.message_id
            )
        elif message:
            msg_match = match(
                r"https://discord.com/channels/(\d+)/(\d+)/(\d+)", message
            )
            if msg_match:
                guild_id, channel_id, message_id = map(int, msg_match.groups())
                if guild_id == ctx.guild.id:
                    channel = ctx.guild.get_channel(channel_id)
                    if channel:
                        target_message = await channel.fetch_message(message_id)

        if target_message:
            await target_message.pin()
            return await ctx.message.add_reaction("📌")

    @commands.command(
        name="unpin",
        help="Unpin a message",
        extras={"parameters": "message", "usage": "unpin [message]"},
    )
    @commands.has_permissions(manage_messages=True)
    async def unpin(self, ctx: TormentContext, *, message: str = None) -> None:
        target_message = None
        if ctx.message.reference:
            target_message = await ctx.channel.fetch_message(
                ctx.message.reference.message_id
            )
        elif message:
            msg_match = match(
                r"https://discord.com/channels/(\d+)/(\d+)/(\d+)", message
            )
            if msg_match:
                guild_id, channel_id, message_id = map(int, msg_match.groups())
                if guild_id == ctx.guild.id:
                    channel = ctx.guild.get_channel(channel_id)
                    if channel:
                        target_message = await channel.fetch_message(message_id)

        if target_message:
            await target_message.unpin()
            return await ctx.message.add_reaction("📌")

    @commands.group(
        name="tts",
        invoke_without_command=True,
        help="Convert text to speech and send as an mp3",
        extras={"parameters": "[voice] text", "usage": "tts [voice] (text)"},
    )
    async def tts(self, ctx: TormentContext, *, text: str) -> None:
        voices = await edge_tts.list_voices()
        voice_map = {v["ShortName"].lower(): v["ShortName"] for v in voices}
        friendly_map = {
            v["ShortName"].split("-")[-1].replace("Neural", "").lower(): v["ShortName"]
            for v in voices
        }

        selected_voice = "en-GB-RyanNeural"
        words = text.split(maxsplit=1)

        if len(words) >= 2:
            query = words[0].lower()
            if query in voice_map:
                selected_voice = voice_map[query]
                text = words[1].strip()
            elif query in friendly_map:
                selected_voice = friendly_map[query]
                text = words[1].strip()

        if not text:
            return await ctx.warn("Please provide some text to convert.")

        async with ctx.typing():
            try:
                buf = io.BytesIO()
                communicate = edge_tts.Communicate(text, selected_voice)
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        buf.write(chunk["data"])
                buf.seek(0)

                if buf.getbuffer().nbytes == 0:
                    return await ctx.warn("No audio was generated. Try a different voice or text.")

            except edge_tts.exceptions.NoAudioReceived:
                return await ctx.warn("No audio was received from the TTS service. Try again.")
            except Exception as e:
                return await ctx.warn(f"TTS failed: `{e}`")

        await ctx.send(file=discord.File(buf, filename="tts.mp3"))

    @tts.command(
        name="voices",
        help="List all available TTS voices",
        extras={"parameters": "n/a", "usage": "tts voices"},
    )
    async def tts_voices(self, ctx: TormentContext) -> None:
        voices = await edge_tts.list_voices()
        en_voices = [v["ShortName"] for v in voices if v["ShortName"].startswith("en-")]
        other_voices = [v["ShortName"] for v in voices if not v["ShortName"].startswith("en-")]

        embed = discord.Embed(title="Available TTS Voices", color=_color("EMBED_INFO_COLOR"))
        embed.add_field(
            name=f"English ({len(en_voices)})",
            value="\n".join(f"`{v}`" for v in en_voices[:20]) + (f"\n…and {len(en_voices) - 20} more" if len(en_voices) > 20 else ""),
            inline=True,
        )
        embed.add_field(
            name=f"Other ({len(other_voices)})",
            value="\n".join(f"`{v}`" for v in other_voices[:20]) + (f"\n…and {len(other_voices) - 20} more" if len(other_voices) > 20 else ""),
            inline=True,
        )
        embed.set_footer(text="Usage: tts [voice] (text) • Default: en-GB-RyanNeural")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Miscellaneous(bot))
