import discord
import time
import random
import aiohttp
import asyncio
import io
import os
from io import BytesIO
from discord import app_commands, File, Embed
from discord.ext import commands
from discord.ext.commands import Cog, hybrid_command
from typing import Optional, Tuple
import secrets
import datetime
from pilmoji import Pilmoji
import regex as re
import math, ast, operator, decimal
from decimal import Decimal
from functools import partial
import uwuify
import urllib.parse
import unicodedata
import pyfiglet
from urllib.parse import quote
from PIL import Image, ImageDraw, ImageFont, ImageColor
from lyricsgenius import Genius
from heist.framework.discord.decorators import donor_only, check_donor, check_owner
from heist.apis.musixmatch import Musixmatch, ENDPOINTS
import logging
import regex

GENIUS_KEY = os.getenv("GENIUS_ACCESS_KEY")

logger = logging.getLogger("lyrics")
logger.setLevel(logging.DEBUG)

fonts = [
    "3d-ascii", "3d_diagonal", "5lineoblique", "avatar", "braced", 
    "cards", "computer", "drpepper", "fun_face", "keyboard", "konto_slant"]

allowed_operators = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow
}

MAX_INPUT_LENGTH = 200
MAX_RECURSION_DEPTH = 20
MAX_EXECUTION_TIME = 2
MAX_NUMBER = Decimal('1e1000')

class SafeMathEvaluator:
    def __init__(self):
        self.start_time = None

    def evaluate_expression(self, expression):
        if len(expression) > MAX_INPUT_LENGTH:
            return "Error: Expression too long"

        expression = ''.join(c for c in expression if c.isprintable())
        expression = unicodedata.normalize("NFKC", expression)

        try:
            decimal.getcontext().prec = 50
            self.start_time = time.time()
            tree = ast.parse(expression, mode='eval')

            for node in ast.walk(tree):
                if isinstance(node, ast.Call) or isinstance(node, ast.Attribute):
                    raise ValueError("Function calls and attribute access are not allowed")
                if isinstance(node, ast.BinOp) and type(node.op) not in allowed_operators:
                    raise ValueError("Unsupported operator")

            result = self._eval_ast(tree.body, 0)
            return str(result)

        except Exception as e:
            return e

    def _eval_ast(self, node, depth):
        if depth > MAX_RECURSION_DEPTH:
            raise ValueError("Maximum recursion depth exceeded")

        if time.time() - self.start_time > MAX_EXECUTION_TIME:
            raise ValueError("Execution time limit exceeded")

        if isinstance(node, ast.Expression):
            return self._eval_ast(node.body, depth + 1)
        elif isinstance(node, ast.BinOp):
            left = self._eval_ast(node.left, depth + 1)
            right = self._eval_ast(node.right, depth + 1)
            op_func = allowed_operators[type(node.op)]

            if isinstance(node.op, ast.Div) and right == 0:
                raise ValueError("Division by zero")

            if isinstance(node.op, ast.Pow):
                if left == 0 and right < 0:
                    raise ValueError("Zero cannot be raised to a negative power")
                if abs(right) > 1000:
                    raise ValueError("Exponent too large")

            result = op_func(Decimal(str(left)), Decimal(str(right)))
            if abs(result) > MAX_NUMBER:
                raise ValueError("Result too large")
            return result

        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_ast(node.operand, depth + 1)
            if isinstance(node.op, ast.UAdd):
                return +operand
            elif isinstance(node.op, ast.USub):
                return -operand
            else:
                raise ValueError("Unsupported unary operator")
        elif isinstance(node, ast.Num):
            if abs(Decimal(str(node.n))) > MAX_NUMBER:
                raise ValueError("Number too large")
            return Decimal(str(node.n))
        else:
            raise ValueError("Unsupported AST node")

class Fun(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.ctx_roast = app_commands.ContextMenu(
            name='Roast User',
            callback=self.userroast,
        )
        self.bot.tree.add_command(self.ctx_roast)

        self.ctx_rizz = app_commands.ContextMenu(
            name='Rizz User',
            callback=self.userrizz,
        )
        self.bot.tree.add_command(self.ctx_rizz)
        self.NAVY_KEY = os.getenv("NAVY_API_KEY")
        self.mxm = Musixmatch({
            'requestTimeoutMs': 10000,
            'cacheTTL': 300000,
            'maxCacheEntries': 100
        })

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    @app_commands.command()
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.describe(message="Message to say.", freaky="Make it 𝓯𝓻𝓮𝓪𝓴𝔂?", uwu="Make it UwU?", reverse="Reverse the message?")
    async def say(self, interaction: discord.Interaction, message: str, freaky: bool = False, uwu: bool = False, reverse: bool = False):
        """Make the bot say something"""
        try:
            if reverse:
                message = message[::-1].replace("@", "@\u200B").replace("&", "&\u200B")

            if uwu:
                flags = uwuify.STUTTER
                message = uwuify.uwu(message, flags=flags)

            if freaky:
                def to_freaky(text):
                    normal = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                    freaky = "𝓐𝓑𝓒𝓓𝓔𝓕𝓖𝓗𝓘𝓙𝓚𝓛𝓜𝓝𝓞𝓟𝓠𝓡𝓢𝓣𝓤𝓿𝓦𝓧𝓨𝓩𝓪𝓫𝓬𝓭𝓮𝓯𝓰𝓱𝓲𝓳𝓴𝓵𝓶𝓷𝓸𝓹𝓺𝓻𝓼𝓽𝓾𝓿𝔀𝔁𝔂𝔃"
                    translation_table = str.maketrans(normal, freaky)

                    translated_text = text.translate(translation_table)

                    wrapped_text = re.sub(r'[^𝓐-𝔃 *]+', lambda match: f"*{match.group(0)}*", translated_text)

                    return wrapped_text

                message = to_freaky(message)

            await interaction.response.send_message(message, allowed_mentions=discord.AllowedMentions.none())

        except discord.HTTPException as e:
            await interaction.warn("`Command 'say' was blocked by AutoMod.`")
        except Exception as e:
            await interaction.warn(e)

    @hybrid_command(name="coinflip", description="Flip a coin", aliases=["cf", "coinf"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def coinflip(self, ctx: commands.Context):
        result = "<:coinheads:1377329015886581922> Heads" if secrets.randbelow(2) == 0 else "<:cointails:1377328997767057499> Tails"
        await ctx.send(f"{result}.")

    @hybrid_command(name="8ball", description="Consult 8ball to receive an answer")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(question="The question you want answers to")
    async def eightball(self, ctx: commands.Context, *, question: str):
        ballresponse = [
            "Yes", "No", "Take a wild guess...", "Very doubtful",
            "Sure", "Without a doubt", "Most likely", 
            "Might be possible", "You'll be the judge",
            "no wtf", "no... baka", "yuh fosho", 
            "maybe man idk lol"
        ]

        answer = random.choice(ballresponse)
        await ctx.send(f"🎱 **Question:** {question}\n**Answer:** {answer}")

    @hybrid_command(name="hotcalc", description="Check how hot someone is")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(user="The user you want to check")
    async def hotcalc(self, ctx: commands.Context, user: discord.User = None):
        user = user or ctx.author
        r = random.randint(1, 100)
        hot = r / 1.17

        emoji = (
            "💞" if hot > 75 else
            "💖" if hot > 50 else
            "❤" if hot > 25 else
            "💔"
        )

        await ctx.send(f"**{user.name}** is **{hot:.2f}%** hot {emoji}")

    @hybrid_command(name="howgay", description="Check how gay someone is", aliases=["gayrate"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(user="The user you want to check the gayness of")
    async def howgay(self, ctx: commands.Context, user: Optional[discord.User] = None):
        user = user or ctx.author
        
        if user.id == 1363295564133040272:
            await ctx.send("cosmin is NOT gay 😭🙏🏿")
            return
    
        rgay = random.randint(1, 100)
        gay = rgay / 1.17

        emoji = (
            "🏳️🌈" if gay > 75 else
            "🤑" if gay > 50 else
            "🤫" if gay > 25 else
            "🔥"
        )

        await ctx.send(f"**{user.name}** is **{gay:.2f}%** gay {emoji}")

    @hybrid_command(name="howautistic", description="Check how autistic someone is", aliases=["autisticrate"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(user="The user you want to check the autism of.")
    async def howautistic(self, ctx: commands.Context, user: Optional[discord.User] = None):
        user = user or ctx.author

        if user.id == 1363295564133040272:
            await ctx.send("cosmin is NOT autistic 😭🙏🏿")
            return

        rautistic = random.randint(1, 100)
        autistic = rautistic / 1.17

        emoji = (
            "🧩" if autistic > 75 else
            "🧠" if autistic > 50 else
            "🤐" if autistic > 25 else
            "🔥"
        )

        await ctx.send(f"**{user.name}** is **{autistic:.2f}%** autistic {emoji}")

    @hybrid_command(name="ppsize", description="Check the size of someone's pp", aliases=["pp"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(user="The user you want to check the pp size of.")
    async def ppsize(self, ctx: commands.Context, user: Optional[discord.User] = None):
        user = user or ctx.author

        length = random.randint(1, 20)
        pp = "=" * length
        emoji = "D"
        
        await ctx.send(f"**{user.name}**'s pp:\\n**`8{pp}{emoji}`**")

    @hybrid_command(name="urban", description="Search Urban Dictionary")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(search="The term to search for")
    async def urban(self, ctx: commands.Context, *, search: str):
        await ctx.typing()

        try:
            async with self.session.get(f"https://api.urbandictionary.com/v0/define?term={search}") as r:
                if not r.ok:
                    return await ctx.warn("I think the API broke..")

                data = await r.json()
                if not data["list"]:
                    return await ctx.warn("Couldn't find your search in the dictionary...")

                definitions = sorted(data["list"], reverse=True, key=lambda g: int(g["thumbs_up"]))
                if not definitions:
                    return await ctx.warn("No definitions found.")

                color = await self.bot.get_color(ctx.author.id)
                pages_embeds = []
                
                for i, definition_data in enumerate(definitions):
                    definition = definition_data['definition']
                    word = definition_data['word']
                    url = definition_data['permalink']

                    if len(definition) >= 1000:
                        definition = definition[:1000].rsplit(" ", 1)[0] + "..."

                    embed = discord.Embed(
                        title=word,
                        url=url,
                        description=definition,
                        color=color
                    )

                    if definition_data['example']:
                        embed.add_field(name="Example", value=definition_data['example'], inline=False)

                    embed.set_author(
                        name=f"{ctx.author.name}", 
                        icon_url=ctx.author.display_avatar.url
                    )
                    embed.set_footer(
                        text=f"{definition_data['thumbs_up']} 👍 • {definition_data['thumbs_down']} 👎", 
                        icon_url="https://git.cursi.ng/heist.png?a"
                    )
                    pages_embeds.append(embed)

                from heist.framework.pagination import Paginator
                await Paginator(ctx, pages_embeds).start()

        except Exception as e:
            await ctx.warn(str(e))

    # @hybrid_command(name="lyrics", description="Search for song lyrics")
    # @app_commands.allowed_installs(guilds=True, users=True)
    # @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    # @app_commands.describe(song="The song to search lyrics for")
    # async def lyrics(self, ctx: commands.Context, *, song: str):
    #     await ctx.typing()
    #     try:
    #         loop = asyncio.get_running_loop()
    #         genius = Genius(GENIUS_KEY)
    #         genius.remove_section_headers = True
    #         genius.skip_non_songs = True
    #         genius.excluded_terms = ["(Remix)", "(Live)"]
    #         song_obj = await loop.run_in_executor(None, genius.search_song, song)
    #         if not song_obj or not song_obj.lyrics or not song_obj.lyrics.strip():
    #             return await ctx.warn("Lyrics not found.")
    #         lyrics = song_obj.lyrics
    #         if "Lyrics" in lyrics:
    #             lyrics_index = lyrics.find("Lyrics")
    #             lyrics = lyrics[lyrics_index + len("Lyrics"):].strip()
    #         def split_lyrics(lyrics: str):
    #             paragraphs = lyrics.split("\n\n")
    #             return [paragraph.strip() for paragraph in paragraphs if paragraph.strip()]
    #         pages_content = split_lyrics(lyrics)
    #         if not pages_content:
    #             return await ctx.warn("Lyrics not found.")
    #         color = await self.bot.get_color(ctx.author.id)
    #         pages_embeds = []
    #         for i, content in enumerate(pages_content):
    #             embed = discord.Embed(
    #                 title=f"{song_obj.title} - {song_obj.artist}",
    #                 description=f"```yaml\n{content}```",
    #                 url=song_obj.url,
    #                 color=color
    #             )
    #             embed.set_author(
    #                 name=ctx.author.name,
    #                 icon_url=ctx.author.display_avatar.url
    #             )
    #             embed.set_footer(
    #                 text=f"genius.com",
    #                 icon_url="https://git.cursi.ng/genius_logo.png"
    #             )
    #             embed.set_thumbnail(url=song_obj.song_art_image_url)
    #             pages_embeds.append(embed)
    #         from heist.framework.pagination import Paginator
    #         await Paginator(ctx, pages_embeds).start()
    #     except Exception as e:
    #         await ctx.warn(str(e))

    # @lyrics.autocomplete("song")
    # async def lyrics_autocomplete(
    #     self,
    #     interaction: discord.Interaction,
    #     current: str,
    # ) -> list[app_commands.Choice[str]]:
    #     if not current:
    #         default_songs = [
    #             "how u feel? - Destroy Lonely",
    #             "if looks could kill - Destroy Lonely",
    #             "JETLGGD - Destroy Lonely",
    #             "Foreign - Playboi Carti",
    #             "Freestyle 2 - Ken Carson",
    #             "overseas - Ken Carson",
    #             "NEVEREVER - Destroy Lonely",
    #             "Jennifer's Body - Ken Carson",
    #             "NOSTYLIST - Destroy Lonely",
    #             "ILoveUIHateU - Playboi Carti"
    #         ]
    #         return [app_commands.Choice(name=s, value=s) for s in default_songs]
    #     try:
    #         genius = Genius(GENIUS_KEY)
    #         genius.remove_section_headers = True
    #         genius.skip_non_songs = True
    #         genius.excluded_terms = ["(Remix)", "(Live)"]
    #         search_results = await asyncio.to_thread(genius.search_songs, current)
    #         choices = []
    #         for hit in search_results['hits'][:25]:
    #             song_title = hit['result']['title']
    #             artist_name = hit['result']['artist_names']
    #             choice_name = f"{song_title} - {artist_name}"
    #             if len(choice_name) > 100:
    #                 choice_name = choice_name[:97] + "..."
    #             choices.append(app_commands.Choice(name=choice_name, value=choice_name))
    #         return choices
    #     except Exception:
    #         return []

    @commands.hybrid_command(name="lyrics", description="Search for song lyrics")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(song="The song to search lyrics for")
    async def lyrics(self, ctx: commands.Context, *, song: str):
        loading_embed = discord.Embed(
            description=f"-# <a:dotsload:1423056880854499338> {ctx.author.mention}: fetching lyrics for: **{song}**\n-# **Trying with <:mxm:1433623990508716165>..**",
            color=await self.bot.get_color(ctx.author.id)
        )
        message = await ctx.send(embed=loading_embed)
        result = None

        try:
            result = await self.mxm.find_lyrics(song)
        except:
            result = None

        if not result or not result.get("text"):
            loading_embed.description = f"-# <a:dotsload:1423056880854499338> {ctx.author.mention}: fetching lyrics for: **{song}**\n-# Could not find. **Falling back to <:genius:1433623987958710272>..**"
            await message.edit(embed=loading_embed)
            try:
                loop = asyncio.get_running_loop()
                genius = Genius(GENIUS_KEY)
                genius.remove_section_headers = True
                genius.skip_non_songs = True
                genius.excluded_terms = ["(Remix)", "(Live)"]
                song_obj = await loop.run_in_executor(None, genius.search_song, song)
                if song_obj and song_obj.lyrics and song_obj.lyrics.strip():
                    lyrics_text = song_obj.lyrics
                    if "Lyrics" in lyrics_text:
                        lyrics_index = lyrics_text.find("Lyrics")
                        lyrics_text = lyrics_text[lyrics_index + len("Lyrics"):].strip()
                    lines = [line.strip() for line in lyrics_text.split("\n") if line.strip()]
                    lines_per_page = 15
                    pages_content = ["\n".join(lines[i:i+lines_per_page]) for i in range(0, len(lines), lines_per_page)]
                    track_info = {"title": song_obj.title, "author": song_obj.artist, "albumArt": song_obj.song_art_image_url}
                    result = {"text": lyrics_text, "track": track_info, "lines": pages_content, "source": "Genius"}
            except:
                await ctx.edit_warn("Lyrics not found.", message)
                return

        if not result or not result.get("text"):
            await ctx.edit_warn("Lyrics not found.", message)
            return

        lyrics_text = result["text"]
        lines = [line.strip() for line in lyrics_text.split("\n") if line.strip()]
        lines_per_page = 15
        pages_content = ["\n".join(lines[i:i+lines_per_page]) for i in range(0, len(lines), lines_per_page)]
        color = await self.bot.get_color(ctx.author.id)
        pages_embeds = []

        track_info = result.get("track", {})
        title = track_info.get("title", song)
        artist = track_info.get("author", "Unknown Artist")
        album_art = track_info.get("albumArt")
        source = result.get("source", "Musixmatch")

        for content in pages_content:
            embed = discord.Embed(
                title=f"{title} - {artist}",
                description=f"```yaml\n{content}```",
                color=color
            )
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
            embed.set_footer(
                text=source,
                icon_url="https://git.cursi.ng/mxm_logo.png" if source == "Musixmatch" else "https://git.cursi.ng/genius_logo.png"
            )
            if album_art:
                embed.set_thumbnail(url=album_art)
            pages_embeds.append(embed)

        from heist.framework.pagination import Paginator
        paginator = Paginator(ctx, pages_embeds, message=message)
        await paginator.start()

    @lyrics.autocomplete("song")
    async def lyrics_autocomplete(self, interaction: discord.Interaction, current: str):
        if not current:
            default_songs = [
                "how u feel? - Destroy Lonely",
                "if looks could kill - Destroy Lonely",
                "JETLGGD - Destroy Lonely",
                "Foreign - Playboi Carti",
                "Freestyle 2 - Ken Carson",
                "overseas - Ken Carson",
                "NEVEREVER - Destroy Lonely",
                "Jennifer's Body - Ken Carson",
                "NOSTYLIST - Destroy Lonely",
                "ILoveUIHateU - Playboi Carti"
            ]
            return [app_commands.Choice(name=s, value=s) for s in default_songs]

        try:
            loop = asyncio.get_running_loop()
            genius = Genius(GENIUS_KEY)
            genius.remove_section_headers = True
            genius.skip_non_songs = True
            genius.excluded_terms = ["(Remix)", "(Live)"]

            search_results = await loop.run_in_executor(None, genius.search_songs, current)
            hits = search_results.get("hits", [])[:25]

            choices = []
            for hit in hits:
                song_title = hit["result"]["title"]
                artist_name = hit["result"]["artist_names"]
                choice_name = f"{song_title} - {artist_name}"
                if len(choice_name) > 100:
                    choice_name = choice_name[:97] + "..."
                choices.append(app_commands.Choice(name=choice_name, value=choice_name))

            return choices
        except Exception:
            return []

    @hybrid_command(name="fakemessage", description="Create a fake Discord message", aliases=["fake", "fakemsg", "fmsg"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.choices(theme=[
        app_commands.Choice(name="Ash", value="ash"),
        app_commands.Choice(name="Dark", value="dark"),
    ])
    @app_commands.describe(
        user="The user to impersonate (leave empty to use yourself)",
        text="The message content"
    )
    async def fakemessage(self, ctx: commands.Context, user: Optional[discord.User] = None, *, text: str, theme: Optional[app_commands.Choice[str]] = None):
        if user is None:
            user = ctx.author

        if text is None:
            return await ctx.send_help(ctx.command)

        await ctx.typing()

        async def count_length(ctx, text):
            emoji_pattern = r'<a?:[a-zA-Z0-9_]+:\d+>'
            mention_pattern = r'<@!?(\d+)>'

            def replace_emoji(m):
                return '𝖾'

            async def replace_mention(m):
                user_id = int(m.group(1))
                try:
                    u = await self.bot.fetch_user(user_id)
                    return f"@{u.display_name or u.name}"
                except:
                    return "@unknown"

            text = re.sub(emoji_pattern, replace_emoji, text)
            mention_matches = list(re.finditer(mention_pattern, text))
            for match in mention_matches:
                mention_text = await replace_mention(match)
                text = text.replace(match.group(0), mention_text, 1)

            return len(text)

        theme_value = theme.value if theme else "ash"

        async def create_fake_discord_msg(display_name, pfp_data, message, decoration_data=None):
            def sync_create():
                font_username = ImageFont.truetype("heist/fonts/gg sans semibold.ttf", 16)
                font_timestamp = ImageFont.truetype("heist/fonts/gg sans medium.ttf", 12)
                font_message = ImageFont.truetype("heist/fonts/gg sans medium.ttf", 16)
                max_text_width = 500
                padding = 65

                wrapped_lines = []
                words = message.split(" ")
                line = ""
                for word in words:
                    test_line = line + word + " "
                    if font_message.getlength(test_line) <= max_text_width:
                        line = test_line
                    else:
                        if line.strip():
                            wrapped_lines.append(line.strip())
                        line = word + " "
                if line.strip():
                    wrapped_lines.append(line.strip())

                text_width = max(font_message.getlength(line) for line in wrapped_lines)
                width = min(800, max(400, int(text_width) + padding))
                height = 75 + (len(wrapped_lines) - 1) * 20

                bg_color = "#1a1b1e" if theme_value == "dark" else "#323339"
                image = Image.new("RGB", (width, height), bg_color)
                draw = ImageDraw.Draw(image, "RGBA")

                with Image.open(io.BytesIO(pfp_data)) as pfp_original:
                    pfp = pfp_original.convert("RGBA").resize((40, 40), Image.LANCZOS)
                large_mask = Image.new("L", (80, 80), 0)
                draw_large = ImageDraw.Draw(large_mask)
                draw_large.ellipse((0, 0, 80, 80), fill=255)
                mask = large_mask.resize((40, 40), Image.LANCZOS)
                pfp.putalpha(mask)
                image.paste(pfp, (13, 18), pfp)

                if decoration_data:
                    with Image.open(io.BytesIO(decoration_data)).convert("RGBA") as decor:
                        decor = decor.resize((50, 50), Image.LANCZOS)
                        image.paste(decor, (8, 13), decor)

                with Pilmoji(image) as pilmoji:
                    pilmoji.text((65, 15), display_name, (255, 255, 255), font=font_username, emoji_position_offset=(0, 3))

                timestamp_x = int(65 + font_username.getlength(display_name) + 7)
                hour = random.randint(1, 12)
                minute = random.randint(0, 59)
                ampm = random.choice(["AM", "PM"])
                timestamp_str = f"{hour}:{minute:02d} {ampm}"
                draw.text((timestamp_x, 18), timestamp_str, font=font_timestamp, fill=(163, 166, 170))

                with Pilmoji(image) as pilmoji:
                    extra_space = 2
                    y_offset = 36
                    for line in wrapped_lines:
                        x_offset = 65
                        words_in_line = line.split()
                        for word in words_in_line:
                            if re.fullmatch(r'@[\w]+', word):
                                mention_color = ImageColor.getrgb("#a5b5f9")
                                overlay_color = (41, 44, 80, 180)

                                mention_width = int(font_message.getlength(word + " "))
                                mention_height = font_message.size + 2
                                mention_y_offset = y_offset + 2

                                draw.rounded_rectangle(
                                    [x_offset - 2, mention_y_offset, x_offset + mention_width, mention_y_offset + mention_height],
                                    radius=4,
                                    fill=overlay_color
                                )

                                pilmoji.text(
                                    (x_offset, y_offset),
                                    word + " ",
                                    mention_color,
                                    font_message,
                                    emoji_position_offset=(0, 3)
                                )
                                x_offset += mention_width + extra_space
                            else:
                                pilmoji.text(
                                    (x_offset, y_offset),
                                    word + " ",
                                    ImageColor.getrgb("#e3e5e8"),
                                    font_message,
                                    emoji_position_offset=(0, 3)
                                )
                                x_offset += int(font_message.getlength(word + " "))
                        y_offset += 20

                return image

            return await asyncio.to_thread(sync_create)

        try:
            pfp_url = user.display_avatar.url
            async with self.session.get(pfp_url) as resp:
                if resp.status != 200:
                    return await ctx.warn("Couldn't fetch profile picture")
                pfp_bytes = await resp.read()

            decoration_bytes = None
            if hasattr(user, "avatar_decoration") and user.avatar_decoration:
                async with self.session.get(user.avatar_decoration.url) as resp:
                    if resp.status == 200:
                        decoration_bytes = await resp.read()

            mention_pattern = r'<@!?(\d+)>'
            mention_matches = list(re.finditer(mention_pattern, text))
            for match in mention_matches:
                user_id = int(match.group(1))
                try:
                    mentioned_user = await self.bot.fetch_user(user_id)
                    mention_text = f"@{mentioned_user.display_name or mentioned_user.name}"
                except:
                    mention_text = "@unknown"
                text = text.replace(match.group(0), mention_text, 1)

            img = await create_fake_discord_msg(user.display_name or user.name, pfp_bytes, text, decoration_bytes)

            with io.BytesIO() as image_binary:
                await asyncio.to_thread(img.save, image_binary, 'PNG')
                image_binary.seek(0)
                file = discord.File(fp=image_binary, filename='heist.png')
                await ctx.send(file=file)
                img.close()

        except Exception as e:
            await ctx.warn(e)

    @hybrid_command(name="math", description="Calculate mathematical expressions", aliases=["calc", "calculate"])
    @app_commands.describe(expression="The mathematical expression to evaluate")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def math(self, ctx: commands.Context, expression: str):
        evaluator = SafeMathEvaluator()
        result = evaluator.evaluate_expression(expression)
        await ctx.send(f"{result}")

    @hybrid_command(name="nitro", description="Why not send a little gift?")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def nitro(self, ctx: commands.Context):
        expiration_date = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        expiration_timestamp = int(expiration_date.timestamp())
        expiration_formatted = f"<t:{expiration_timestamp}:R>"
        
        embed = discord.Embed(
            title="You've been gifted a subscription!",
            description=f"You've been gifted Nitro for **1 month**!\nExpires **{expiration_formatted}**\n\n[**Disclaimer**](https://csyn.me/disclaimer)",
            color=0x7289DA
        )
        embed.set_thumbnail(url="https://git.cursi.ng/nitro_logo.jpeg")

        class NitroView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=240)

            @discord.ui.button(label="Claim", style=discord.ButtonStyle.blurple)
            async def claim_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                await button_interaction.response.send_message("https://git.cursi.ng/rickroll.gif", ephemeral=True)

            async def on_timeout(self):
                try:
                    await ctx.message.delete()
                except:
                    pass

        view = NitroView()
        await ctx.send(embed=embed, view=view)
        view.message = ctx.message

    @hybrid_command(name="rate", description="Rates what you desire")
    @app_commands.describe(thing="The thing you want to rate")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def rate(self, ctx: commands.Context, thing: str):
        if thing.lower() in ["csyn", "cosmin", "heist", "raluca", "hyqos"]:
            rating = 1000
        elif thing.lower() in ["mihaela", "mira", "yjwe"]:
            rating = -1000
        else:
            rating = random.uniform(0.0, 100.0)
        
        response = f"I'd rate `{thing}` a **{round(rating, 4)} / 100**"
        await ctx.send(response)

    @hybrid_command(name="button", description="Create a button")
    @app_commands.describe(
        title="Button title",
        text="Text sent when button is clicked",
        style="Button style",
        timeout="Time before disabling the button (default 60s)"
    )
    @app_commands.choices(
        style=[
            app_commands.Choice(name="blurple", value="blurple"),
            app_commands.Choice(name="green", value="green"),
            app_commands.Choice(name="grey", value="grey"),
            app_commands.Choice(name="red", value="red"),
            app_commands.Choice(name="link", value="link"),
        ]
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def button(self, ctx: commands.Context, title: str, text: str, style: str = "blurple", timeout: int = 60):
        if len(title) > 80:
            return await ctx.warn("Title cannot be longer than 80 characters.")
        if timeout > 240:
            return await ctx.warn("Timeout cannot be longer than 240 seconds.")

        style_map = {
            "blurple": discord.ButtonStyle.primary,
            "green": discord.ButtonStyle.success,
            "grey": discord.ButtonStyle.secondary,
            "red": discord.ButtonStyle.danger,
            "link": discord.ButtonStyle.link
        }

        btn_style = style_map.get(style)
        if btn_style is None:
            return await ctx.warn("Invalid style.")

        if btn_style == discord.ButtonStyle.link:
            view = discord.ui.View()
            try:
                view.add_item(discord.ui.Button(label=title, url=text))
                await ctx.send(view=view)
                return
            except discord.HTTPException:
                return await ctx.warn("Invalid URL for link button.")

        class ButtonView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=timeout)
                self.button = discord.ui.Button(label=title, style=btn_style)
                self.button.callback = self.button_callback
                self.add_item(self.button)

            async def button_callback(self, button_interaction: discord.Interaction):
                await button_interaction.response.send_message(text, ephemeral=True)

            async def on_timeout(self):
                self.button.disabled = True
                self.clear_items()
                self.add_item(self.button)
                if hasattr(self, "message"):
                    await self.message.edit(view=self)

        view = ButtonView()
        sent_message = await ctx.send(view=view)
        view.message = sent_message

    @hybrid_command(name="asciify", description="Convert text to ASCII art")
    @app_commands.describe(text="The text you want to convert to ASCII", font="The font you want to use for the ASCII")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def asciify(self, ctx: commands.Context, text: str, font: str = "3d-ascii"):
        if font not in fonts:
            return await ctx.warn(f"Invalid font. Available fonts are: {', '.join(fonts)}")

        try:
            ascii_art = await asyncio.to_thread(pyfiglet.figlet_format, text, font=font)
            await ctx.send(f"```fix\\n{ascii_art}\\n```")
        except Exception:
            await ctx.warn("Text is too long to display.")

    async def async_image_process(self, func, *args, **kwargs):
        return await self.bot.loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def create_circle_mask(self, size: Tuple[int, int]):
        return await self.async_image_process(self._create_circle_mask, size)

    def _create_circle_mask(self, size: Tuple[int, int]):
        mask = Image.new('L', size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + size, fill=255)
        return mask

    async def create_love_image(self, author_bytes: bytes, target_bytes: bytes, love_percent: int, bar_color: Tuple[int, int, int]) -> bytes:
        author_avatar = await self.async_image_process(Image.open, io.BytesIO(author_bytes))
        target_avatar = await self.async_image_process(Image.open, io.BytesIO(target_bytes))
        base = await self.async_image_process(Image.new, 'RGBA', (400, 200), (0, 0, 0, 0))
        draw = ImageDraw.Draw(base)
        avatar_size = (100, 100)
        if author_avatar.mode != 'RGBA':
            author_avatar = await self.async_image_process(author_avatar.convert, 'RGBA')
        if target_avatar.mode != 'RGBA':
            target_avatar = await self.async_image_process(target_avatar.convert, 'RGBA')
        author_avatar = await self.async_image_process(author_avatar.resize, avatar_size, Image.LANCZOS)
        target_avatar = await self.async_image_process(target_avatar.resize, avatar_size, Image.LANCZOS)
        circle_mask = await self.create_circle_mask(avatar_size)
        author_avatar.putalpha(circle_mask)
        target_avatar.putalpha(circle_mask)
        await self.async_image_process(base.paste, author_avatar, (50, 25), author_avatar)
        await self.async_image_process(base.paste, target_avatar, (250, 25), target_avatar)
        
        try:
            if love_percent >= 80:
                heart_symbol = await self.async_image_process(Image.open, "/root/heist-v3/heist/assets/growing_heart.png")
            elif love_percent >= 50:
                heart_symbol = await self.async_image_process(Image.open, "/root/heist-v3/heist/assets/smiling_hearts_face.png")
            elif love_percent >= 30:
                heart_symbol = await self.async_image_process(Image.open, "/root/heist-v3/heist/assets/broken_heart.png")
            elif love_percent >= 15:
                heart_symbol = await self.async_image_process(Image.open, "/root/heist-v3/heist/assets/crying_face.png")
            else:
                heart_symbol = await self.async_image_process(Image.open, "/root/heist-v3/heist/assets/skull_face.png")
            heart_symbol = await self.async_image_process(heart_symbol.resize, (100, 100), Image.LANCZOS)
            midpoint_x = (50 + 350) // 2
            heart_x = midpoint_x - 50
            await self.async_image_process(base.paste, heart_symbol, (heart_x, 30), heart_symbol)
        except Exception:
            try:
                font = ImageFont.truetype("DejaVuSans.ttf", 30)
            except:
                font = ImageFont.load_default()
            await self.async_image_process(draw.text, (175, 50), "<3" if love_percent >= 50 else "</3", font=font, fill=(255, 0, 0) if love_percent >= 50 else (0, 0, 0))
        
        bar_width, bar_height = 300, 20
        bar_x, bar_y = 50, 150
        await self.async_image_process(draw.rectangle, [(bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height)], fill=(169, 169, 169))
        progress_width = int(bar_width * (love_percent / 100))
        await self.async_image_process(draw.rectangle, [(bar_x, bar_y), (bar_x + progress_width, bar_y + bar_height)], fill=bar_color)
        percent_text = f"{love_percent}% love"
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 14)
        except:
            font = ImageFont.load_default()
        text_bbox = await self.async_image_process(font.getbbox, percent_text)
        text_width = text_bbox[2] - text_bbox[0]
        text_x = bar_x + (bar_width - text_width) // 2
        text_y = bar_y + (bar_height - 14) // 2
        brightness = (bar_color[0] * 0.299 + bar_color[1] * 0.587 + bar_color[2] * 0.114)
        text_color = (0, 0, 0) if brightness > 128 else (255, 255, 255)
        await self.async_image_process(draw.text, (text_x, text_y), percent_text, font=font, fill=text_color)
        image_binary = io.BytesIO()
        await self.async_image_process(base.save, image_binary, format='PNG')
        return image_binary.getvalue()

    @hybrid_command(name="ship", description="Ship two users together")
    @app_commands.describe(user1="First user to ship", user2="Second user to ship (defaults to you)")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def ship(self, ctx: commands.Context, user1: discord.User, user2: discord.User = None):
        await ctx.typing()
        love_percent = random.randint(0, 100)
        user2 = user2 or ctx.author
        
        try:
            user1_url = user1.display_avatar.with_size(512).url if user1.display_avatar else user1.default_avatar.url
            user2_url = user2.display_avatar.with_size(512).url if user2.display_avatar else user2.default_avatar.url
            async with self.session.get(user1_url) as resp:
                user1_bytes = await resp.read()
            async with self.session.get(user2_url) as resp:
                user2_bytes = await resp.read()
            
            user_color = await self.bot.get_color(ctx.author.id)
            color_tuple = ((user_color >> 16) & 255, (user_color >> 8) & 255, user_color & 255)
            image_bytes = await self.create_love_image(user1_bytes, user2_bytes, love_percent, color_tuple)
            combined_name = user1.name[:len(user1.name)//2] + user2.name[len(user2.name)//2:]
            combined_name = combined_name.lower()
            embed = discord.Embed(title=f"**{combined_name} 💕**", color=user_color)
            file = discord.File(fp=io.BytesIO(image_bytes), filename='love.png')
            embed.set_image(url="attachment://love.png")
            await ctx.send(file=file, embed=embed)
        except Exception as e:
            await ctx.warn(str(e))

    @hybrid_command(name="emojimix", description="Mix two emojis together", aliases=["mix"])
    @app_commands.describe(emojis="Two emojis to mix together")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def emojimix(self, ctx: commands.Context, *, emojis: str):
        await ctx.typing()

        emoji_match = regex.findall(r'\X', emojis)
        emoji_match = [e for e in emoji_match if regex.match(r'\p{Emoji}', e)]

        if len(emoji_match) < 2:
            return await ctx.warn("Please provide two valid emojis.")

        emoji1, emoji2 = emoji_match[:2]
        url = f"https://emojik.vercel.app/s/{quote(emoji1)}_{quote(emoji2)}?size=256"

        async with self.session.get(url) as response:
            if response.status == 200:
                data = await response.read()
                file = discord.File(io.BytesIO(data), filename="heist.png")
                await ctx.send(file=file)
            else:
                await ctx.warn("Failed to mix emojis.")

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def userroast(self, interaction: discord.Interaction, user: discord.User) -> None:
        ctx = await self.bot.get_context(interaction)
        ctx.author = interaction.user
        ctx.message = interaction
        await self.roast(ctx, user)

    @commands.hybrid_command(
        name="roast",
        description="Roast a user",
    )
    @app_commands.describe(user="The user to roast")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def roast_hybrid(self, ctx: commands.Context, user: discord.User):
        await self.roast(ctx, user)

    async def roast(self, ctx: commands.Context, user: discord.User):
        try:
            await ctx.defer()
            author_obj = getattr(ctx, "author", None) or getattr(ctx, "user", None)
            user_id = str(author_obj.id)

            if user.id == 1225070865935368265:
                await ctx.warn("real funny, buddy.")
                return

            is_donor = await check_donor(ctx.bot, user_id)
            is_owner = await check_owner(ctx.bot, user_id) 

            if not is_donor and not is_owner:
                cooldown_key = f"cooldown:roast:{user_id}"
                current_count = await self.bot.redis.get(cooldown_key)
                current_count = int(current_count) if current_count else 0

                if current_count >= 25:
                    ttl = await self.bot.redis.ttl(cooldown_key)
                    if ttl and ttl > 0:
                        drt = f"<t:{int(time.time()) + ttl}:R>"
                    else:
                        drt = "soon"

                    msg = (
                        "You are limited to **`25 uses per hour`** of this command.\n"
                        f"-# You can use this again **{drt}**.\n"
                        f"-# Roast more with **Premium**. </premium buy:{self.premiumbuy}>\n"
                    )
                    await ctx.warn(msg)
                    return

                await self.bot.redis.incr(cooldown_key)
                if current_count == 0:
                    await self.bot.redis.expire(cooldown_key, 3600)

            username = user.name
            alpha_chars = [char for char in username if char.isalpha()]
            is_3l = len(alpha_chars) == 3
            is_3c = len(username) == 3 and not is_3l
            is_4l = len(alpha_chars) == 4
            is_4c = len(username) == 4 and not is_4l

            if is_3c:
                lroast = "his username is 3 characters, so roast em extra hard for being basic af. like 'this ape really thinks his lame ahh 3c is og aint no way 💀.'"
            elif is_3l:
                lroast = "his username is 3 letters, so roast em extra hard for being basic af. like 'this ape really thinks his lame ahh 3l is og aint no way 💀.'"
            elif is_4c:
                lroast = "his username is 4 characters, so roast em extra hard for being basic af. like 'this ape really thinks his lame ahh 4c is og aint no way 💀.'"
            elif is_4l:
                lroast = "his username is 4 letters, so roast em extra hard for being basic af. like 'this ape really thinks his lame ahh 4l is og aint no way 💀.'"
            else:
                lroast = ""

            slang = ["wsg", "fr", "no cap", "man's finished", "violated", "ain't no way", "bro thinks he's", "certi clown"]
            insults = ["ur poor asf bruh get some funds", "come depo w me broke ass nga", "u look like u be begging for $5 on cashapp"]
            exaggerations = ["gay ass nga", "on god ur a fuck ass nga", "bitch ass nga"]
            emojis = ["🔥", "💀", "💯", "🧛‍♀️", "😭"]

            system_prompt = (
                f"yo, u gotta roast {user.name} based on their username. keep it raw af, "
                f"super casual, lowercase, and straight to the point. throw in slang like '{random.choice(slang)}' "
                f"come up with things like '{random.choice(insults)}' or '{random.choice(exaggerations)}' "
                f"use emojis like {random.choice(emojis)} and keep it under 600 chars. for stuff like nigga just say nga not nigga."
                f"{lroast} their username is {user.name}."
            )
            user_prompt = f"username: {user.name}, roast them."

            headers = {"Authorization": f"Bearer {self.NAVY_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "mistral-small-2506",
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                "max_tokens": 600,
                "temperature": 0.9
            }

            try:
                async with self.session.post("https://api.navy/v1/chat/completions", headers=headers, json=payload) as api_resp:
                    if api_resp.status == 200:
                        data = await api_resp.json()
                        roast_text = data.get("choices", [{}])[0].get("message", {}).get("content")
                        if roast_text and not any(x in roast_text.lower() for x in ["i can't", "cannot", "unable", "refuse", "fail"]):
                            await ctx.send(roast_text)
                            return
            except Exception as e:
                await ctx.warn(str(e))

            system_prompt_encoded = urllib.parse.quote(system_prompt)
            user_prompt_encoded = urllib.parse.quote(user_prompt)
            api_url = f"https://text.pollinations.ai/{user_prompt_encoded}?system={system_prompt_encoded}&model=llama&seed=12345"

            async with self.session.get(api_url) as response:
                if response.status == 200:
                    roast_text = await response.text()
                    await ctx.send(roast_text)
                else:
                    await ctx.warn("Failed to generate a roast. Try again later.")

        except Exception as e:
            await ctx.warn(e)

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def userrizz(self, interaction: discord.Interaction, user: discord.User) -> None:
        ctx = await self.bot.get_context(interaction)
        ctx.author = interaction.user
        ctx.message = interaction
        await self.rizz(ctx, user)

    @commands.hybrid_command(
        name="rizz",
        description="Rizz a user",
    )
    @app_commands.describe(user="The user to rizz")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def rizz_hybrid(self, ctx: commands.Context, user: discord.User):
        await self.rizz(ctx, user)

    async def rizz(self, ctx: commands.Context, user: discord.User):
        try:
            await ctx.defer()
            author_obj = getattr(ctx, "author", None) or getattr(ctx, "user", None)
            user_id = str(author_obj.id)
            is_donor = await check_donor(ctx.bot, user_id)
            is_owner = await check_owner(ctx.bot, user_id) 

            if not is_donor and not is_owner:
                cooldown_key = f"cooldown:rizz:{user_id}"
                current_count = await self.bot.redis.get(cooldown_key)
                current_count = int(current_count) if current_count else 0

                if current_count >= 25:
                    ttl = await self.bot.redis.ttl(cooldown_key)
                    if ttl and ttl > 0:
                        drt = f"<t:{int(time.time()) + ttl}:R>"
                    else:
                        drt = "soon"

                    msg = (
                        "You are limited to **`25 uses per hour`** of this command.\n"
                        f"-# You can use this again **{drt}**.\n"
                        f"-# Rizz more with **Premium**. </premium buy:{self.premiumbuy}>\n"
                    )
                    await ctx.warn(msg)
                    return

                await self.bot.redis.incr(cooldown_key)
                if current_count == 0:
                    await self.bot.redis.expire(cooldown_key, 3600)
            
            username = user.name
            alpha_chars = [char for char in username if char.isalpha()]
            is_3l = len(alpha_chars) == 3
            is_3c = len(username) == 3 and not is_3l
            is_4l = len(alpha_chars) == 4
            is_4c = len(username) == 4 and not is_4l

            if is_3c:
                lcontext = "his username only got 3 chars, so drop a smooth but cheeky line on him."
            elif is_3l:
                lcontext = "his username is 3 letters—make a flirty comment about how short and cute that is."
            elif is_4c:
                lcontext = "his username got 4 characters, so rizz em up properly."
            elif is_4l:
                lcontext = "his username is 4 letters—rizz em with something clean and confident."
            else:
                lcontext = ""

            slang = ["wsg", "wyd rn", "you up?", "no cap", "rizz god", "lowkey"]
            compliments = ["you fine af", "lemme take you out", "that pfp kinda got me staring", "you a whole 10"]
            emojis = ["😮‍💨", "😏", "🫶", "🔥", "👀", "💋"]

            system_prompt = (
                f"yo, try to rizz up {user.name} based on their username. keep it smooth, lowercase, modern slang. "
                f"use flirty energy like '{random.choice(slang)}' and say stuff like '{random.choice(compliments)}' "
                f"use emojis like {random.choice(emojis)} to make it hit. make sure it’s under 600 characters."
                f"{lcontext} their username is {user.name}."
            )
            user_prompt = f"username: {user.name}, rizz them up."

            headers = {"Authorization": f"Bearer {self.NAVY_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "mistral-small-2506",
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                "max_tokens": 600,
                "temperature": 0.9
            }

            try:
                async with self.session.post("https://api.navy/v1/chat/completions", headers=headers, json=payload) as api_resp:
                    if api_resp.status == 200:
                        data = await api_resp.json()
                        rizz_text = data.get("choices", [{}])[0].get("message", {}).get("content")
                        if rizz_text:
                            await ctx.send(rizz_text)
                            return
            except Exception as e:
                await ctx.warn(str(e))

            system_prompt_encoded = urllib.parse.quote(system_prompt)
            user_prompt_encoded = urllib.parse.quote(user_prompt)
            api_url = f"https://text.pollinations.ai/{user_prompt_encoded}?system={system_prompt_encoded}&model=llama&seed=12345"

            async with self.session.get(api_url) as response:
                if response.status == 200:
                    rizz_text = await response.text()
                    await ctx.send(rizz_text)
                else:
                    await ctx.warn("Failed to generate rizz. Try again later.")

        except Exception as e:
            print(e)

async def setup(bot):
    await bot.add_cog(Fun(bot))