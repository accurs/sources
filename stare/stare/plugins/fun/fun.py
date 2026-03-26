import asyncio
from datetime import datetime
from io import BytesIO
from typing import Optional, Union, cast
from zoneinfo import ZoneInfo

import aiohttp
import discord
from aiohttp import ClientSession, TCPConnector
from asyncio import sleep
from discord import Embed, Member, Message, app_commands
from discord.ext import commands
from discord.ext.commands import BucketType, Cog, is_nsfw
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from uwuipy import uwuipy
from yarl import URL

from stare.core.config import Config
from stare.core.tools.context import CustomContext as Context

# ---------------------------------------------------------------------------
# Roleplay helpers
# ---------------------------------------------------------------------------

BASE_URL  = URL.build(scheme="https", host="nekos.best")
BASE_URL1 = URL.build(scheme="https", host="purrbot.site")
BASE_URL2 = URL.build(scheme="https", host="api.waifu.pics")

ACTIONS = {
    "bite": "bit",
    "cuddle": "cuddled",
    "feed": "fed",
    "hug": "hugged",
    "kiss": "kissed",
    "pat": "patted",
    "poke": "poked",
    "punch": "punched",
    "slap": "slapped",
    "smug": "smugged at",
    "tickle": "tickled",
    "neko": "showed a neko to",
    "waifu": "showed a waifu to",
    "husbando": "showed a husbando to",
    "kitsune": "showed a kitsune to",
    "lurk": "lurked at",
    "shoot": "shot",
    "sleep": "slept with",
    "shrug": "shrugged at",
    "stare": "stared at",
    "wave": "waved at",
    "smile": "smiled at",
    "peck": "pecked",
    "wink": "winked at",
    "blush": "blushed at",
    "yeet": "yeeted",
    "think": "thought about",
    "highfive": "high-fived",
    "bored": "got bored with",
    "nom": "nommed",
    "yawn": "yawned at",
    "facepalm": "facepalmed at",
    "happy": "got happy with",
    "baka": "called baka",
    "nod": "nodded at",
    "nope": "noped at",
    "dance": "danced with",
    "handshake": "shook hands with",
    "cry": "cried with",
    "pout": "pouted at",
    "handhold": "held hands with",
    "thumbsup": "gave a thumbs up to",
    "laugh": "laughed with",
    "anal": "fucked",
    "blowjob": "sucked off",
    "cum": "came on",
    "pussylick": "ate out",
    "threesome_ffm": "had a threesome with",
    "threesome_fmm": "had a threesome with",
    "threesome_fff": "had a threesome with",
    "lick": "licked",
    "bully": "bullied",
    "bonk": "bonked",
    "cringe": "cringed at",
    "awoo": "awooed at",
    "nutkick": "nutkicked",
    "fuck": "fucked",
    "spank": "spanked",
    "kill": "killed",
}


def ordinal(n: int) -> str:
    suffix = ("th", "st", "nd", "rd") + ("th",) * 10
    v = n % 100
    return f"{n}{suffix[v % 10] if v > 13 else suffix[v]}"


# ---------------------------------------------------------------------------
# Quote image constants & helpers
# ---------------------------------------------------------------------------

CANVAS_W      = 960
CANVAS_H      = 400
BG_COLOR      = (0, 0, 0)
QUOTE_COLOR   = (255, 255, 255)
DISP_COLOR    = (210, 210, 210)
USER_COLOR    = (120, 120, 120)
GUILD_COLOR   = (80, 80, 80)
MAX_MSG_LEN   = 300
MAX_USER_LEN  = 32
MAX_GUILD_LEN = 50
QUOTE_TIMEOUT = aiohttp.ClientTimeout(total=10)

# Text block starts at 54% across the canvas, matching the screenshot
TEXT_X_RATIO  = 0.54


def _load_font(path: str, size: int) -> Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


# Quote: large regular weight | Attr: italic | Handle: small regular | Guild: tiny regular
QUOTE_FONT = _load_font("stare/fonts/Inter-VariableFont_opsz,wght.ttf", 38)
DISP_FONT  = _load_font("stare/fonts/Urbanist-Italic-VariableFont_wght.ttf", 22)
USER_FONT  = _load_font("stare/fonts/Inter-VariableFont_opsz,wght.ttf", 16)
GUILD_FONT = _load_font("stare/fonts/Inter-VariableFont_opsz,wght.ttf", 14)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    try:
        return draw.textlength(text, font=font)
    except Exception:
        return float(len(text) * 10)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list:
    words = text.split()
    lines: list = []
    current = ""

    for word in words:
        if _text_width(draw, word, font) > max_width:
            lo, hi = 1, len(word)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if _text_width(draw, word[:mid], font) <= max_width:
                    lo = mid
                else:
                    hi = mid - 1
            word = word[:max(1, lo)]

        test = f"{current} {word}".strip()
        if _text_width(draw, test, font) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines or [""]


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _build_avatar_layer(avatar_bytes: bytes, w: int, h: int) -> Optional[Image.Image]:
    """
    Render the avatar as a full-height layer with a hard right-edge fade
    that bleeds from solid on the left to fully transparent, matching the
    screenshot's vertical gradient dissolve.
    """
    try:
        av = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
        # Fill full canvas height, keep square aspect
        av = av.resize((h, h), Image.LANCZOS)

        # Build a per-column alpha mask:
        # - columns 0..fade_start  → fully opaque (alpha 255)
        # - columns fade_start..h  → linear fade to 0
        # The fade starts at ~55% of the avatar width, matching the screenshot
        # where the avatar bleeds to about x=420 on a 960px canvas.
        fade_start = int(h * 0.50)
        fade_end   = h

        mask = Image.new("L", (h, h), 255)
        mask_draw = ImageDraw.Draw(mask)

        for x in range(fade_start, fade_end):
            progress = (x - fade_start) / max(1, fade_end - fade_start)
            # Power curve makes it linger opaque longer then drop off fast, 
            # matching the soft-then-sharp dissolve visible in the screenshot
            alpha = int(255 * (1.0 - progress ** 1.6))
            mask_draw.line([(x, 0), (x, h)], fill=alpha)

        av.putalpha(mask)
        return av
    except Exception:
        return None


def _generate_quote_image(
    avatar_bytes: Optional[bytes],
    message: str,
    display_name: str,
    username: str,
    guild_name: str,
) -> BytesIO:
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOR)

    if avatar_bytes:
        av_layer = _build_avatar_layer(avatar_bytes, CANVAS_W, CANVAS_H)
        if av_layer:
            # Centre vertically (avatar is square = CANVAS_H, so y=0)
            canvas.paste(av_layer, (0, 0), av_layer)

    draw       = ImageDraw.Draw(canvas)
    text_x     = int(CANVAS_W * TEXT_X_RATIO)
    text_max_w = CANVAS_W - text_x - 40

    # Layout measurements (all in px)
    q_line_h  = 48   # line height for quote text
    gap_q_d   = 16   # gap between last quote line and display name
    disp_h    = 26   # height of display name line
    gap_d_u   = 5    # gap between display name and @handle
    handle_h  = 20   # height of @handle line

    lines   = _wrap_text(draw, message, QUOTE_FONT, text_max_w)
    block_h = (len(lines) * q_line_h) + gap_q_d + disp_h + gap_d_u + handle_h
    text_y  = max(16, (CANVAS_H - block_h) // 2)

    # Bottom safety rail — leave room for attribution
    bottom = CANVAS_H - disp_h - handle_h - gap_q_d - gap_d_u - 8

    for line in lines:
        if text_y > bottom:
            break
        draw.text((text_x, text_y), line, font=QUOTE_FONT, fill=QUOTE_COLOR)
        text_y += q_line_h

    # Display name  e.g. "- coolman123"  in italic
    disp_y = min(text_y + gap_q_d, CANVAS_H - disp_h - handle_h - gap_d_u - 8)
    draw.text((text_x, disp_y), f"- {display_name}", font=DISP_FONT, fill=DISP_COLOR)

    # @handle  e.g. "@cooolman123"  smaller, dimmer
    handle_y = disp_y + disp_h + gap_d_u
    draw.text((text_x, handle_y), f"@{username}", font=USER_FONT, fill=USER_COLOR)

    # Guild name bottom-right, very small and dim
    if guild_name:
        gw = int(_text_width(draw, guild_name, GUILD_FONT))
        draw.text(
            (CANVAS_W - gw - 24, CANVAS_H - 26),
            guild_name,
            font=GUILD_FONT,
            fill=GUILD_COLOR,
        )

    buf = BytesIO()
    canvas.save(buf, "PNG")
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Fakemessage image constants & helpers
# ---------------------------------------------------------------------------

FM_BG          = (54, 57, 63)
FM_NAME_COLOR  = (255, 255, 255)
FM_TIME_COLOR  = (163, 166, 170)
FM_MSG_COLOR   = (220, 221, 222)
FM_AVATAR_SIZE = 40
FM_PAD_LEFT    = 16
FM_PAD_TOP     = 16
FM_PAD_BOTTOM  = 16
FM_AVATAR_GAP  = 16
FM_LINE_GAP    = 4
FM_MAX_WIDTH   = 700
FM_TIMEOUT     = aiohttp.ClientTimeout(total=10)

FM_NAME_FONT  = _load_font("stare/fonts/Inter-VariableFont_opsz,wght.ttf", 16)
FM_TIME_FONT  = _load_font("stare/fonts/Inter-VariableFont_opsz,wght.ttf", 12)
FM_MSG_FONT   = _load_font("stare/fonts/Inter-VariableFont_opsz,wght.ttf", 16)
FM_NAME_H     = 20
FM_MSG_LINE_H = 20


def _generate_fakemessage(
    avatar_bytes: Optional[bytes],
    display_name: str,
    timestamp: str,
    message: str,
) -> BytesIO:
    text_x   = FM_PAD_LEFT + FM_AVATAR_SIZE + FM_AVATAR_GAP
    canvas_w = text_x + FM_MAX_WIDTH + 40

    # Use the real canvas draw for both measuring and rendering — same as quote
    canvas = Image.new("RGB", (canvas_w, 1), FM_BG)
    draw   = ImageDraw.Draw(canvas)

    msg_lines    = _wrap_text(draw, message, FM_MSG_FONT, FM_MAX_WIDTH)
    msg_block_h  = len(msg_lines) * FM_MSG_LINE_H
    text_block_h = FM_NAME_H + FM_LINE_GAP + msg_block_h
    content_h    = max(text_block_h, FM_AVATAR_SIZE)
    canvas_h     = FM_PAD_TOP + content_h + FM_PAD_BOTTOM

    # Recreate at correct height now that we know it
    canvas = Image.new("RGB", (canvas_w, canvas_h), FM_BG)
    draw   = ImageDraw.Draw(canvas)

    av_y = FM_PAD_TOP + (content_h - FM_AVATAR_SIZE) // 2
    if avatar_bytes:
        try:
            av     = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
            av     = av.resize((FM_AVATAR_SIZE, FM_AVATAR_SIZE), Image.LANCZOS)
            mask   = Image.new("L", (FM_AVATAR_SIZE, FM_AVATAR_SIZE), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, FM_AVATAR_SIZE, FM_AVATAR_SIZE), fill=255)
            circle = Image.new("RGBA", (FM_AVATAR_SIZE, FM_AVATAR_SIZE), (0, 0, 0, 0))
            circle.paste(av, (0, 0), mask)
            canvas.paste(circle, (FM_PAD_LEFT, av_y), circle)
        except Exception:
            draw.ellipse(
                (FM_PAD_LEFT, av_y, FM_PAD_LEFT + FM_AVATAR_SIZE, av_y + FM_AVATAR_SIZE),
                fill=(100, 100, 100),
            )
    else:
        draw.ellipse(
            (FM_PAD_LEFT, av_y, FM_PAD_LEFT + FM_AVATAR_SIZE, av_y + FM_AVATAR_SIZE),
            fill=(100, 100, 100),
        )

    name_y = FM_PAD_TOP
    name_w = int(_text_width(draw, display_name, FM_NAME_FONT))
    draw.text((text_x, name_y), display_name, font=FM_NAME_FONT, fill=FM_NAME_COLOR)

    time_x = text_x + name_w + 8
    draw.text((time_x, name_y + 3), timestamp, font=FM_TIME_FONT, fill=FM_TIME_COLOR)

    msg_y = name_y + FM_NAME_H + FM_LINE_GAP
    for line in msg_lines:
        draw.text((text_x, msg_y), line, font=FM_MSG_FONT, fill=FM_MSG_COLOR)
        msg_y += FM_MSG_LINE_H

    buf = BytesIO()
    canvas.save(buf, "PNG")
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class Fun(Cog):
    """Fun commands"""

    def __init__(self, bot):
        self.bot = bot
        self.uwu = uwuipy()

    async def cog_load(self):
        if not self.bot.db_pool:
            return

        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS roleplay (
                user_id   BIGINT,
                target_id BIGINT,
                category  TEXT,
                amount    INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (user_id, target_id, category)
            )
        """)

        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS uwulock (
                guild_id BIGINT,
                user_id  BIGINT,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    async def _track(self, author_id: int, target_id: int, category: str) -> int:
        return cast(
            int,
            await self.bot.db_pool.fetchval(
                """
                INSERT INTO roleplay (user_id, target_id, category)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, target_id, category)
                DO UPDATE SET amount = roleplay.amount + 1
                RETURNING amount
                """,
                author_id, target_id, category,
            ),
        )

    def _action_embed(self, ctx: Context, member: Optional[Member], category: str, amount: int) -> Embed:
        embed = Embed(color=Config.COLORS.DEFAULT)
        if member:
            embed.description = (
                f"> {ctx.author.mention} has {ACTIONS[category]} {member.mention}"
                + (f" for the **{ordinal(amount)}** time" if member != ctx.author and amount else "")
            )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        return embed

    async def nekos_send(self, ctx: Context, member: Optional[Member], category: str) -> Message:
        url = BASE_URL.with_path(f"/api/v2/{category}")
        async with ctx.typing():
            async with ClientSession(connector=TCPConnector()) as session:
                async with session.get(url, proxy=None) as response:
                    try:
                        data = await response.json()
                        if not data.get("results"):
                            return await ctx.warn("Something went wrong, please try again later!")
                    except Exception:
                        return await ctx.warn("Something went wrong, please try again later!")

            amount = 0
            if member and member != ctx.author:
                amount = await self._track(ctx.author.id, member.id, category)

            embed = self._action_embed(ctx, member, category, amount)
            embed.set_image(url=data["results"][0]["url"])
            return await ctx.send(embed=embed)

    async def waifu_send(self, ctx: Context, member: Optional[Member], category: str) -> Message:
        url = BASE_URL2.with_path(f"/sfw/{category}")
        async with ctx.typing():
            async with ClientSession(connector=TCPConnector()) as session:
                async with session.get(url, proxy=None) as response:
                    try:
                        data = await response.json()
                        if not data.get("url"):
                            return await ctx.warn("Something went wrong, please try again later!")
                    except Exception:
                        return await ctx.warn("Something went wrong, please try again later!")

            amount = 0
            if member and member != ctx.author:
                amount = await self._track(ctx.author.id, member.id, category)

            embed = self._action_embed(ctx, member, category, amount)
            embed.set_image(url=data["url"])
            return await ctx.send(embed=embed)

    async def purrbot_send(self, ctx: Context, member: Optional[Member], category: str) -> Message:
        url = BASE_URL1.with_path(f"/api/img/nsfw/{category}/gif")
        async with ctx.typing():
            async with ClientSession(connector=TCPConnector()) as session:
                async with session.get(url, proxy=None) as response:
                    try:
                        data = await response.json()
                        if not data.get("link"):
                            return await ctx.warn("Something went wrong, please try again later!")
                    except Exception:
                        return await ctx.warn("Something went wrong, please try again later!")

            amount = 0
            if member and member != ctx.author:
                amount = await self._track(ctx.author.id, member.id, category)

            embed = self._action_embed(ctx, member, category, amount)
            embed.set_image(url=data["link"])
            return await ctx.send(embed=embed)

    async def threesome_send(self, ctx: Context, member: Member, member2: Member, category: str) -> Message:
        url = BASE_URL1.with_path(f"/api/img/nsfw/{category}/gif")
        async with ctx.typing():
            async with ClientSession(connector=TCPConnector()) as session:
                async with session.get(url, proxy=None) as response:
                    try:
                        data = await response.json()
                        if not data.get("link"):
                            return await ctx.warn("Something went wrong, please try again later!")
                    except Exception:
                        return await ctx.warn("Something went wrong, please try again later!")

            embed = Embed(
                color=Config.COLORS.DEFAULT,
                description=f"> {ctx.author.mention} has {ACTIONS[category]} {member.mention} and {member2.mention}",
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            embed.set_image(url=data["link"])
            return await ctx.send(embed=embed)

    async def _guild_embed_send(self, ctx: Context, user: Member, category: str, gif_url: str) -> None:
        amount = 0
        if user != ctx.author:
            amount = await self._track(ctx.author.id, user.id, category)

        embed = self._action_embed(ctx, user, category, amount)
        embed.set_image(url=gif_url)
        await ctx.send(embed=embed)

    # -----------------------------------------------------------------------
    # Quote
    # -----------------------------------------------------------------------

    @commands.command(name="quote")
    @commands.cooldown(1, 5, BucketType.user)
    @commands.guild_only()
    async def quote(self, ctx: Context):
        """Quote a message that a user sent"""
        ref = ctx.message.reference
        if not ref:
            return await ctx.warn("You need to reply to a message to quote it!")

        quoted_msg: Optional[discord.Message] = None
        if isinstance(ref.resolved, discord.Message):
            quoted_msg = ref.resolved
        elif ref.message_id:
            try:
                quoted_msg = await ctx.channel.fetch_message(ref.message_id)
            except (discord.NotFound, discord.HTTPException):
                return await ctx.warn("I couldn't find that message!")

        if quoted_msg is None:
            return await ctx.warn("I couldn't resolve that message!")

        content = quoted_msg.content.strip()
        if not content:
            return await ctx.warn("That message has no text content to quote!")

        content      = _truncate(content, MAX_MSG_LEN)
        display_name = _truncate(quoted_msg.author.display_name, MAX_USER_LEN)
        username     = _truncate(quoted_msg.author.name, MAX_USER_LEN)
        guild_name   = _truncate(ctx.guild.name, MAX_GUILD_LEN) if ctx.guild else ""

        async with ClientSession(connector=TCPConnector(), timeout=QUOTE_TIMEOUT) as session:
            try:
                async with session.get(str(quoted_msg.author.display_avatar.url)) as resp:
                    avatar_bytes = await resp.read() if resp.status == 200 else None
            except Exception:
                avatar_bytes = None

        buf = await asyncio.to_thread(
            _generate_quote_image,
            avatar_bytes,
            content,
            display_name,
            username,
            guild_name,
        )

        try:
            await ctx.reply(file=discord.File(buf, filename="quote.png"), mention_author=True)
        except discord.HTTPException:
            buf.seek(0)
            await ctx.send(file=discord.File(buf, filename="quote.png"))

    @quote.error
    async def quote_error(self, ctx: Context, error: commands.CommandError):
        unwrapped = getattr(error, "original", error)
        if isinstance(unwrapped, commands.CommandOnCooldown):
            await ctx.warn(f"You can use this command again in **{unwrapped.retry_after:.1f}s**!")

    # -----------------------------------------------------------------------
    # Fakemessage
    # -----------------------------------------------------------------------

    @commands.command(name="fakemessage")
    @commands.cooldown(1, 5, BucketType.user)
    @commands.guild_only()
    async def fakemessage(self, ctx: Context, user: discord.Member, *, message: str):
        """Create a fake Discord message from another user"""
        content      = _truncate(message.strip(), MAX_MSG_LEN)
        display_name = _truncate(user.display_name, MAX_USER_LEN)

        now       = datetime.now(ZoneInfo("America/Chicago"))
        hour      = str(now.hour % 12 or 12)
        timestamp = f"{hour}:{now.strftime('%M')} {'AM' if now.hour < 12 else 'PM'}"

        async with ClientSession(connector=TCPConnector(), timeout=FM_TIMEOUT) as session:
            try:
                async with session.get(str(user.display_avatar.url)) as resp:
                    avatar_bytes = await resp.read() if resp.status == 200 else None
            except Exception:
                avatar_bytes = None

        buf = await asyncio.to_thread(
            _generate_fakemessage,
            avatar_bytes,
            display_name,
            timestamp,
            content,
        )

        try:
            await ctx.reply(file=discord.File(buf, filename="fakemessage.png"), mention_author=True)
        except discord.HTTPException:
            buf.seek(0)
            await ctx.send(file=discord.File(buf, filename="fakemessage.png"))

    @fakemessage.error
    async def fakemessage_error(self, ctx: Context, error: commands.CommandError):
        unwrapped = getattr(error, "original", error)
        if isinstance(unwrapped, commands.CommandOnCooldown):
            await ctx.warn(f"You can use this command again in **{unwrapped.retry_after:.1f}s**!")

    # -----------------------------------------------------------------------
    # Uwulock
    # -----------------------------------------------------------------------

    @commands.hybrid_group(name="uwulock", aliases=["uwu"], invoke_without_command=True, description="Uwulock a user")
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(member="Who to uwulock")
    @commands.guild_only()
    async def uwulock(self, ctx: Context, member: discord.Member):
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            return await ctx.warn("You can't uwulock someone with a higher or equal role!")
        if member.id == ctx.guild.owner_id:
            return await ctx.warn("You can't uwulock the server owner!")
        if member.bot:
            return await ctx.warn("You can't uwulock bots!")

        record = await self.bot.db_pool.fetchrow(
            "SELECT 1 FROM uwulock WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id,
        )

        if record:
            await self.bot.db_pool.execute(
                "DELETE FROM uwulock WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id, member.id,
            )
            return await ctx.approve(f"I've removed {member.mention} from **uwulock**")

        await self.bot.db_pool.execute(
            "INSERT INTO uwulock (guild_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            ctx.guild.id, member.id,
        )
        return await ctx.approve(f"I've added {member.mention} to **uwulock**")

    @uwulock.command(name="list", description="Send a list of every uwulocked member")
    @commands.guild_only()
    async def uwulock_list(self, ctx: Context):
        records = await self.bot.db_pool.fetch(
            "SELECT user_id FROM uwulock WHERE guild_id = $1", ctx.guild.id
        )
        if not records:
            return await ctx.warn("No one in this server is uwulocked!")

        members = [
            f"{m.mention} - `{m.id}`"
            for r in records
            if (m := ctx.guild.get_member(r["user_id"]))
        ]
        if not members:
            return await ctx.warn("No one in this server is uwulocked!")

        per_page = 10
        pages = [members[i:i + per_page] for i in range(0, len(members), per_page)]
        embeds = [
            Embed(
                title="Uwulocked Members",
                description="\n".join(chunk),
                color=Config.COLORS.DEFAULT,
            ).set_footer(text=f"Page {i + 1}/{len(pages)} ({len(members)} members)")
            for i, chunk in enumerate(pages)
        ]

        if len(embeds) == 1:
            return await ctx.send(embed=embeds[0])

        from utils.paginator import Paginator
        paginator = Paginator(embeds, ctx.author)
        message = await ctx.send(embed=embeds[0], view=paginator)
        paginator.message = message

    @uwulock.command(name="reset", description="Reset the uwulock list")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def uwulock_reset(self, ctx: Context):
        data = await self.bot.db_pool.fetch(
            "SELECT 1 FROM uwulock WHERE guild_id = $1", ctx.guild.id
        )
        if not data:
            return await ctx.warn("No one in this server is uwulocked!")

        await self.bot.db_pool.execute(
            "DELETE FROM uwulock WHERE guild_id = $1", ctx.guild.id
        )
        return await ctx.approve("I've reset the **uwulock** list")

    @Cog.listener("on_message")
    async def uwulock_listener(self, message: discord.Message):
        if message.author.bot or message.guild is None or not message.content:
            return

        record = await self.bot.db_pool.fetchrow(
            "SELECT 1 FROM uwulock WHERE guild_id = $1 AND user_id = $2",
            message.guild.id, message.author.id,
        )
        if not record:
            return

        await sleep(0.5)

        uwuified = self.uwu.uwuify(message.content).strip()
        if not uwuified:
            return

        thread  = discord.utils.MISSING
        channel = message.channel

        if isinstance(channel, discord.Thread):
            thread  = channel
            channel = channel.parent

        if not hasattr(channel, "webhooks"):
            return

        try:
            webhooks = await channel.webhooks()
        except discord.Forbidden:
            return

        webhook = discord.utils.get(webhooks, name="Uwulock")
        if webhook is None:
            try:
                webhook = await channel.create_webhook(name="Uwulock")
            except discord.Forbidden:
                return

        try:
            await message.delete()
        except discord.Forbidden:
            pass

        try:
            await webhook.send(
                content=uwuified,
                username=message.author.display_name,
                avatar_url=message.author.display_avatar.url,
                allowed_mentions=discord.AllowedMentions.none(),
                thread=thread,
            )
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Roleplay / action commands
    # -----------------------------------------------------------------------

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @is_nsfw()
    @commands.guild_only()
    async def anal(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Fuck a member anally."""
        return await self.purrbot_send(ctx, member, "anal")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @is_nsfw()
    @commands.guild_only()
    async def blowjob(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Give a member a blowjob."""
        return await self.purrbot_send(ctx, member, "blowjob")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @is_nsfw()
    @commands.guild_only()
    async def cum(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Cum on a member."""
        return await self.purrbot_send(ctx, member, "cum")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @is_nsfw()
    @commands.guild_only()
    async def pussylick(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Lick a member's pussy."""
        return await self.purrbot_send(ctx, member, "pussylick")

    @commands.group(name="threesome", invoke_without_command=True)
    @is_nsfw()
    @commands.guild_only()
    async def threesome(self, ctx: Context):
        """Have a threesome with two other members."""
        await ctx.send_help(ctx.command)

    @threesome.command(name="ffm")
    @commands.cooldown(1, 3, BucketType.member)
    @is_nsfw()
    @commands.guild_only()
    async def threesome_ffm(self, ctx: Context, member1: Member, member2: Member):
        """Threesome with two girls and one boy."""
        return await self.threesome_send(ctx, member1, member2, "threesome_ffm")

    @threesome.command(name="fmm")
    @commands.cooldown(1, 3, BucketType.member)
    @is_nsfw()
    @commands.guild_only()
    async def threesome_fmm(self, ctx: Context, member1: Member, member2: Member):
        """Threesome with two boys and one girl."""
        return await self.threesome_send(ctx, member1, member2, "threesome_fmm")

    @threesome.command(name="fff")
    @commands.cooldown(1, 3, BucketType.member)
    @is_nsfw()
    @commands.guild_only()
    async def threesome_fff(self, ctx: Context, member1: Member, member2: Member):
        """Threesome with only girls."""
        return await self.threesome_send(ctx, member1, member2, "threesome_fff")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def cuddle(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Cuddle someone."""
        return await self.nekos_send(ctx, member, "cuddle")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def poke(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Poke someone."""
        return await self.nekos_send(ctx, member, "poke")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def kiss(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Kiss someone."""
        return await self.nekos_send(ctx, member, "kiss")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def hug(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Hug someone."""
        return await self.nekos_send(ctx, member, "hug")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def pat(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Pat someone."""
        return await self.nekos_send(ctx, member, "pat")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def tickle(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Tickle someone."""
        return await self.nekos_send(ctx, member, "tickle")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def lick(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Lick someone."""
        return await self.waifu_send(ctx, member, "lick")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def slap(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Slap someone."""
        return await self.nekos_send(ctx, member, "slap")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def feed(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Feed someone."""
        return await self.nekos_send(ctx, member, "feed")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def punch(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Punch someone."""
        return await self.nekos_send(ctx, member, "punch")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def highfive(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Highfive someone."""
        return await self.nekos_send(ctx, member, "highfive")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def bite(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Bite someone."""
        return await self.nekos_send(ctx, member, "bite")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def bully(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Bully someone."""
        return await self.waifu_send(ctx, member, "bully")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def bonk(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Bonk someone."""
        return await self.waifu_send(ctx, member, "bonk")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def cringe(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Cringe at someone."""
        return await self.waifu_send(ctx, member, "cringe")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def shoot(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Shoot someone."""
        return await self.nekos_send(ctx, member, "shoot")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def wave(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Wave to someone."""
        return await self.nekos_send(ctx, member, "wave")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def happy(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Be happy with someone."""
        return await self.nekos_send(ctx, member, "happy")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def peck(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Peck someone."""
        return await self.nekos_send(ctx, member, "peck")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def lurk(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Lurk at someone."""
        return await self.nekos_send(ctx, member, "lurk")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def sleep(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Sleep with someone."""
        return await self.nekos_send(ctx, member, "sleep")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def shrug(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Shrug at someone."""
        return await self.nekos_send(ctx, member, "shrug")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def wink(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Wink at someone."""
        return await self.nekos_send(ctx, member, "wink")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def dance(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Dance with someone."""
        return await self.nekos_send(ctx, member, "dance")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def yawn(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Yawn at someone."""
        return await self.nekos_send(ctx, member, "yawn")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def nom(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Nom someone."""
        return await self.nekos_send(ctx, member, "nom")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def awoo(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Awoo at someone."""
        return await self.waifu_send(ctx, member, "awoo")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def yeet(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Yeet someone."""
        return await self.nekos_send(ctx, member, "yeet")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def think(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Think about someone."""
        return await self.nekos_send(ctx, member, "think")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def bored(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Be bored with someone."""
        return await self.nekos_send(ctx, member, "bored")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def blush(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Blush at someone."""
        return await self.nekos_send(ctx, member, "blush")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def stare(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Stare at someone."""
        return await self.nekos_send(ctx, member, "stare")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def nod(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Nod at someone."""
        return await self.nekos_send(ctx, member, "nod")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def handhold(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Hold hands with someone."""
        return await self.nekos_send(ctx, member, "handhold")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def smug(self, ctx: Context, member: Optional[Member] = None) -> Message:
        """Smug at someone."""
        return await self.nekos_send(ctx, member, "smug")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def nutkick(self, ctx: Context, user: Member):
        """Nutkick someone."""
        async with ctx.typing():
            async with self.bot.session.get("https://nekos.best/api/v2/kick", proxy=None) as resp:
                data = await resp.json()
                gif_url = data["results"][0]["url"]
        await self._guild_embed_send(ctx, user, "nutkick", gif_url)

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def fuck(self, ctx: Context, user: Member):
        """Fuck someone."""
        return await self.purrbot_send(ctx, user, "fuck")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def spank(self, ctx: Context, user: Member):
        """Spank someone."""
        return await self.purrbot_send(ctx, user, "spank")

    @commands.command()
    @commands.cooldown(1, 3, BucketType.member)
    @commands.guild_only()
    async def kill(self, ctx: Context, user: Member):
        """Kill someone."""
        async with ctx.typing():
            async with self.bot.session.get("https://nekos.best/api/v2/shoot", proxy=None) as resp:
                data = await resp.json()
                gif_url = data["results"][0]["url"]
        await self._guild_embed_send(ctx, user, "kill", gif_url)


async def setup(bot):
    await bot.add_cog(Fun(bot))
