from discord import Embed, Member, Message, User
from discord.ext import commands
from discord.ext.commands import Cog, BucketType, CheckFailure
from aiohttp import ClientSession, TCPConnector
from typing import Union
import asyncio
import io
import re
import copy
import base64
from urllib.parse import quote

import discord
from stare.core.tools.context import CustomContext as Context
from stare.core.config import Config

SUPPORT_GUILD_ID = 1473105346913505280
OWNER_IDS = (1460003194771083296, 1019668815728103526)
BOT_AVATAR = "https://images-ext-1.discordapp.net/external/3OMYi_SmczBA94QePvSFndjMroEVOTFFdjVGneWPCNw/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1472023540227117322/cb8d2c193818f84d6923bade5d0fd202.png?format=webp&quality=lossless"

BOOST_THANK_YOU_CONTENT = "# <a:253523boostgemsmonth6:1473168739766767708> Thank you for boosting [**stare**](https://server.link.here)!  \n> You now have **premium** perks, and a custom role in the support server. \n-# stare.lat • discord.gg/starebot\n"
BOOST_EXPIRED_CONTENT = "# <a:253523boostgemsmonth6:1473168739766767708> Your boost has expired\n> Your **premium** perks are now gone\n-# stare.lat • discord.gg/starebot\n"
PREMIUM_INFO_CONTENT = "# Premium  \nTo accquire premium, **boost** stare's [**Support Server**](https://discord.com/starebot) \nWe **will** add more payment methods **soon**"


def build_cv2_payload(content: str) -> dict:
    return {
        "content": "",
        "flags": 32768,
        "components": [
            {
                "type": 17,
                "components": [
                    {
                        "type": 9,
                        "components": [
                            {
                                "type": 10,
                                "content": content
                            }
                        ],
                        "accessory": {
                            "type": 11,
                            "media": {
                                "url": BOT_AVATAR
                            }
                        }
                    }
                ]
            }
        ]
    }


async def send_cv2(ctx: Context, content: str) -> None:
    token = ctx.bot.http.token
    async with ClientSession() as session:
        await session.post(
            f"https://discord.com/api/v10/channels/{ctx.channel.id}/messages",
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
            json=build_cv2_payload(content),
        )


async def send_cv2_dm(bot, user: Member, content: str) -> None:
    dm = user.dm_channel or await user.create_dm()
    token = bot.http.token
    async with ClientSession() as session:
        await session.post(
            f"https://discord.com/api/v10/channels/{dm.id}/messages",
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
            json=build_cv2_payload(content),
        )


def is_premium():
    async def predicate(ctx: Context) -> bool:
        cog = ctx.bot.get_cog("Premium")
        if cog and await cog.check_premium(ctx.author.id):
            return True
        raise CheckFailure("premium_required")
    return commands.check(predicate)


def is_owner():
    async def predicate(ctx: Context) -> bool:
        if ctx.author.id in OWNER_IDS:
            return True
        await ctx.deny("Developer only command!")
        raise CheckFailure("User is not an owner.")
    return commands.check(predicate)


class Premium(Cog):
    """Premium commands"""

    def __init__(self, bot):
        self.bot = bot
        self.session = ClientSession()
        self.github_token = "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"
        self.repo_owner = "4tsx"
        self.repo_name = "cdn"
        self.base_path = "media"

    async def cog_load(self):
        if not self.bot.db_pool:
            return
        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS premium_users (
                user_id BIGINT PRIMARY KEY
            )
        """)
        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS selfprefix (
                user_id BIGINT PRIMARY KEY,
                prefix TEXT NOT NULL
            )
        """)
        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS reskin (
                user_id BIGINT PRIMARY KEY,
                toggled BOOLEAN NOT NULL DEFAULT true,
                username TEXT,
                avatar TEXT
            )
        """)
        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS custom_colors (
                user_id BIGINT PRIMARY KEY,
                color INTEGER NOT NULL
            )
        """)

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def check_premium(self, user_id: int) -> bool:
        if not self.bot.db_pool:
            return False
        row = await self.bot.db_pool.fetchrow(
            "SELECT user_id FROM premium_users WHERE user_id = $1", user_id
        )
        if row:
            return True
        guild = self.bot.get_guild(SUPPORT_GUILD_ID)
        if guild is None:
            return False
        member = guild.get_member(user_id)
        if member is None:
            return False
        return member.premium_since is not None

    async def get_custom_color(self, user_id: int) -> int:
        if not self.bot.db_pool:
            return Config.COLORS.DEFAULT
        row = await self.bot.db_pool.fetchrow(
            "SELECT color FROM custom_colors WHERE user_id = $1", user_id
        )
        if row:
            return row['color']
        return Config.COLORS.DEFAULT

    @Cog.listener()
    async def on_command(self, ctx: Context):
        if await self.check_premium(ctx.author.id):
            if ctx.command and ctx.command._buckets:
                ctx.command.reset_cooldown(ctx)

    @Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        if not self.bot.db_pool:
            return

        row = await self.bot.db_pool.fetchrow(
            "SELECT prefix FROM selfprefix WHERE user_id = $1",
            message.author.id
        )
        if not row:
            return

        selfprefix = row["prefix"]
        if not message.content.startswith(selfprefix):
            return

        new_content = Config.PREFIX + message.content[len(selfprefix):]

        fake = copy.copy(message)
        fake._content = new_content

        ctx = await self.bot.get_context(fake)
        if ctx.valid:
            await self.bot.invoke(ctx)

    @Cog.listener()
    async def on_member_update(self, before: Member, after: Member):
        if before.guild.id != SUPPORT_GUILD_ID:
            return

        was_boosting = before.premium_since is not None
        is_boosting = after.premium_since is not None

        if not was_boosting and is_boosting:
            try:
                await send_cv2_dm(self.bot, after, BOOST_THANK_YOU_CONTENT)
            except Exception:
                pass

        elif was_boosting and not is_boosting:
            try:
                await send_cv2_dm(self.bot, after, BOOST_EXPIRED_CONTENT)
            except Exception:
                pass

    @commands.command(extras={'example': 'upload <attachment>'})
    @commands.is_owner()
    async def upload(self, ctx: Context, filename: str = None):
        """Upload a video or image to stare's CDN"""
        if not ctx.message.attachments:
            return await ctx.warn("I couldn't find an **attachment**.")

        attachment = ctx.message.attachments[0]
        file_name = filename or attachment.filename

        file_bytes = await attachment.read()
        encoded_content = base64.b64encode(file_bytes).decode()

        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents/{self.base_path}/{file_name}"

        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        data = {
            "message": f"Upload {file_name}",
            "content": encoded_content
        }

        async with ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    existing = await resp.json()
                    data["sha"] = existing["sha"]

            async with session.put(url, headers=headers, json=data) as resp:
                if resp.status in [200, 201]:
                    cdn_url = f"https://cdn.stare.lat/{self.base_path}/{file_name}"
                    await ctx.approve(f"**I've uploaded the file as**: {cdn_url}")
                else:
                    await ctx.deny(f"**I've failed to upload the file**: {resp.status}")

    @commands.group(invoke_without_command=True)
    @commands.cooldown(1, 5, BucketType.member)
    @commands.guild_only()
    async def premium(self, ctx: Context) -> None:
        """View all of the payment methods to buy premium."""
        await send_cv2(ctx, PREMIUM_INFO_CONTENT)

    @premium.command(name="add")
    @commands.cooldown(1, 5, BucketType.member)
    @commands.guild_only()
    @is_owner()
    async def premium_add(self, ctx: Context, user: Union[Member, User]) -> Message:
        """Add a person to premium."""
        await self.bot.db_pool.execute(
            """
            INSERT INTO premium_users (user_id)
            VALUES ($1)
            ON CONFLICT (user_id) DO NOTHING
            """,
            user.id,
        )
        return await ctx.approve(
            f"I've added **premium** to **{user.name}** (`{user.id}`)."
        )

    @premium.command(name="remove")
    @commands.cooldown(1, 5, BucketType.member)
    @commands.guild_only()
    @is_owner()
    async def premium_remove(self, ctx: Context, user: Union[Member, User]) -> Message:
        """Remove a person from premium."""
        result = await self.bot.db_pool.execute(
            "DELETE FROM premium_users WHERE user_id = $1", user.id
        )
        if result == "DELETE 0":
            return await ctx.deny(
                f"**{user.name}** (`{user.id}`) doesn't have premium!"
            )
        return await ctx.approve(
            f"I've removed **premium** from **{user.name}** (`{user.id}`)."
        )

    @premium.command(name="list")
    @commands.cooldown(1, 5, BucketType.member)
    @commands.guild_only()
    @is_owner()
    async def premium_list(self, ctx: Context) -> Message:
        """View the list of people who have premium."""
        rows = await self.bot.db_pool.fetch("SELECT user_id FROM premium_users")
        if not rows:
            return await ctx.warn("There are no premium users.")

        lines = []
        for i, row in enumerate(rows, start=1):
            user = ctx.bot.get_user(row["user_id"]) or await ctx.bot.fetch_user(row["user_id"])
            lines.append(f"`{i}.` **{user.name}** (**{user.id}**)")

        embed = Embed(
            color=Config.COLORS.DEFAULT,
            title="<:info:1475665966112309550> Premium List",
            description="\n".join(lines),
        )
        embed.set_thumbnail(
            url="https://cdn.discordapp.com/avatars/1472023540227117322/cb8d2c193818f84d6923bade5d0fd202.png?size=1024"
        )
        embed.set_footer(
            text="discord.gg/starebot",
            icon_url="https://cdn.discordapp.com/avatars/1472023540227117322/cb8d2c193818f84d6923bade5d0fd202.png?size=1024",
        )
        return await ctx.send(embed=embed)

    @commands.command(aliases=["ask", "gpt", "chatgpt"])
    @commands.cooldown(1, 5, BucketType.member)
    @commands.guild_only()
    @is_premium()
    async def ai(self, ctx: Context, *, prompt: str) -> Message:
        """Ask AI a question."""
        loading_embed = Embed(
            color=Config.COLORS.DEFAULT,
            description=f"<a:loading:1472264803882893538> {ctx.author.mention} **Generating** a response.."
        )
        loading_msg = await ctx.send(embed=loading_embed)

        try:
            connector = TCPConnector()
            async with ClientSession(connector=connector) as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": "Bearer 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",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 1024,
                    },
                ) as response:
                    data = await response.json()
                    if "error" in data:
                        await loading_msg.delete()
                        return await ctx.warn(f"API error: {data['error'].get('message', 'Unknown error')}")
                    if not data.get("choices"):
                        await loading_msg.delete()
                        return await ctx.warn("Something went wrong, please try again later!")
                    ai_response = data["choices"][0]["message"]["content"]
        except Exception as e:
            await loading_msg.delete()
            return await ctx.warn(f"Something went wrong: {e}")

        result_embed = Embed(
            color=Config.COLORS.DEFAULT,
            description=f"> *{prompt}*\n```ansi\n\u001b[2;36m\u001b[2;35m\u001b[2;34m{ai_response}\u001b[0m\u001b[2;35m\u001b[0m\u001b[2;36m\u001b[0m\n```",
        )
        result_embed.set_author(
            name=ctx.author.display_name,
            icon_url=ctx.author.display_avatar.url,
        )
        result_embed.set_footer(
            text="Llama 3.3 70B",
            icon_url="https://media.discordapp.net/attachments/1475563258139381881/1475628075436867684/meta-logo-300x300.png?ex=699e2d3d&is=699cdbbd&hm=3586195ec047ce1b664e48ccfe33d808dcdbb904697e6c1f4ebadf8dea652d2f&=&format=webp&quality=lossless",
        )

        await loading_msg.delete()
        return await ctx.send(embed=result_embed)

    @commands.command(aliases=["tts"])
    @commands.cooldown(1, 5, BucketType.member)
    @commands.guild_only()
    @is_premium()
    async def texttospeech(self, ctx: Context, voice: str, *, text: str) -> Message:
        """Generate text to speech."""
        import edge_tts

        voices = await edge_tts.list_voices()
        matched = next(
            (v for v in voices if v["ShortName"].lower() == f"en-us-{voice.lower()}neural"),
            None
        )

        if not matched:
            available = ", ".join(sorted({v["ShortName"].split("-")[2].replace("Neural", "").replace("Multilingual", "") for v in voices if "en-US" in v["ShortName"]}))
            return await ctx.warn(f"Voice **{voice}** not found. Available voices: `{available}`")

        async with ctx.typing():
            try:
                communicate = edge_tts.Communicate(text, matched["ShortName"])
                audio_buffer = io.BytesIO()
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_buffer.write(chunk["data"])
                audio_buffer.seek(0)
            except Exception as e:
                return await ctx.warn(f"Something went wrong: {e}")

        file = discord.File(audio_buffer, filename="tts.mp3")
        return await ctx.send(file=file)

    # ── Selfprefix ──────────────────────────────────────────────

    @commands.group(name="selfprefix", invoke_without_command=True)
    @commands.guild_only()
    async def selfprefix(self, ctx: Context) -> Message:
        """Manage your personal prefix"""
        await ctx.send_help(ctx.command)

    @selfprefix.command(name="set")
    @commands.cooldown(1, 5, BucketType.member)
    @is_premium()
    async def selfprefix_set(self, ctx: Context, prefix: str) -> Message:
        """Set your selfprefix"""
        if len(prefix) > 7:
            return await ctx.warn("**Selfprefix** is too long!")
        if not prefix:
            return await ctx.warn("**Selfprefix** is too short!")

        await self.bot.db_pool.execute(
            """
            INSERT INTO selfprefix (user_id, prefix)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET prefix = $2
            """,
            ctx.author.id, prefix
        )
        return await ctx.approve(f"I've set your **selfprefix** to `{prefix}`")

    @selfprefix.command(name="remove", aliases=["delete", "reset"])
    @commands.cooldown(1, 5, BucketType.member)
    @is_premium()
    async def selfprefix_remove(self, ctx: Context) -> Message:
        """Remove your selfprefix"""
        existing = await self.bot.db_pool.fetchrow(
            "SELECT prefix FROM selfprefix WHERE user_id = $1",
            ctx.author.id
        )
        if not existing:
            return await ctx.warn("You don't have a **selfprefix** set!")
        await self.bot.db_pool.execute(
            "DELETE FROM selfprefix WHERE user_id = $1",
            ctx.author.id
        )
        return await ctx.approve("Removed your **selfprefix**.")

    # ── Reskin ───────────────────────────────────────────────────

    @commands.group(name="reskin", invoke_without_command=True)
    @commands.guild_only()
    async def reskin(self, ctx: Context) -> Message:
        """Customize the outputs for stare's command outputs"""
        await ctx.send_help(ctx.command)

    @reskin.command(name="enable")
    @commands.cooldown(1, 5, BucketType.member)
    @is_premium()
    async def reskin_enable(self, ctx: Context) -> Message:
        """Enable reskin for command outputs"""
        existing = await self.bot.db_pool.fetchrow(
            "SELECT toggled FROM reskin WHERE user_id = $1",
            ctx.author.id
        )
        if existing and existing["toggled"]:
            return await ctx.warn("Reskin is already enabled!")
        if existing:
            await self.bot.db_pool.execute(
                "UPDATE reskin SET toggled = true WHERE user_id = $1",
                ctx.author.id
            )
        else:
            await self.bot.db_pool.execute(
                """
                INSERT INTO reskin (user_id, toggled, username, avatar)
                VALUES ($1, true, $2, $3)
                """,
                ctx.author.id,
                ctx.author.display_name,
                str(ctx.author.display_avatar.url)
            )
        return await ctx.approve("I've enabled **reskin**.")

    @reskin.command(name="disable")
    @commands.cooldown(1, 5, BucketType.member)
    @is_premium()
    async def reskin_disable(self, ctx: Context) -> Message:
        """Disable reskin for command outputs"""
        existing = await self.bot.db_pool.fetchrow(
            "SELECT toggled FROM reskin WHERE user_id = $1",
            ctx.author.id
        )
        if not existing:
            return await ctx.warn("**Reskin** is not enabled!")
        await self.bot.db_pool.execute(
            "DELETE FROM reskin WHERE user_id = $1",
            ctx.author.id
        )
        return await ctx.approve("I've **disabled** reskin.")

    @reskin.command(name="name")
    @commands.cooldown(1, 5, BucketType.member)
    @is_premium()
    async def reskin_name(self, ctx: Context, *, name: str) -> Message:
        """Edit stare's name for command outputs"""
        if len(name) > 32:
            return await ctx.warn("Reskin name cannot be longer than 32 characters!")
        existing = await self.bot.db_pool.fetchrow(
            "SELECT user_id FROM reskin WHERE user_id = $1",
            ctx.author.id
        )
        if not existing:
            return await ctx.warn("You need to **enable** reskin first with `;reskin enable`!")
        await self.bot.db_pool.execute(
            "UPDATE reskin SET username = $1 WHERE user_id = $2",
            name, ctx.author.id
        )
        return await ctx.approve(f"Updated your reskin name to **{name}**.")

    @reskin.command(name="avatar", aliases=["icon", "pfp", "av"])
    @commands.cooldown(1, 5, BucketType.member)
    @is_premium()
    async def reskin_avatar(self, ctx: Context, url: str = None) -> Message:
        """Edit stare's avatar for command outputs"""
        import re as _re
        if url is None and ctx.message.attachments:
            url = ctx.message.attachments[0].url
        if not url:
            return await ctx.send_help(ctx.command)

        regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»\u201c\u201d\u2018\u2019]))"
        if not _re.findall(regex, url):
            return await ctx.warn("The image you've provided is not a valid URL!")

        existing = await self.bot.db_pool.fetchrow(
            "SELECT user_id FROM reskin WHERE user_id = $1",
            ctx.author.id
        )
        if not existing:
            return await ctx.warn("You need to **enable** reskin first with `;reskin enable`!")

        await self.bot.db_pool.execute(
            "UPDATE reskin SET avatar = $1 WHERE user_id = $2",
            url, ctx.author.id
        )
        return await ctx.approve(f"I've updated your reskin's [**avatar**]({url}).")

    @reskin.command(name="reset", aliases=["delete", "remove"])
    @commands.cooldown(1, 5, BucketType.member)
    @is_premium()
    async def reskin_remove(self, ctx: Context) -> Message:
        """Reset your reskin customization"""
        existing = await self.bot.db_pool.fetchrow(
            "SELECT user_id FROM reskin WHERE user_id = $1",
            ctx.author.id
        )
        if not existing:
            return await ctx.warn("You don't have reskin configured!")
        await self.bot.db_pool.execute(
            "DELETE FROM reskin WHERE user_id = $1",
            ctx.author.id
        )
        return await ctx.approve("Reskin customization has been deleted.")

    @commands.group(name="color", aliases=["colour"], invoke_without_command=True)
    @commands.guild_only()
    async def color(self, ctx: Context) -> Message:
        """Customize embed colors for all bot responses"""
        await ctx.send_help(ctx.command)

    @color.command(name="set")
    @commands.cooldown(1, 5, BucketType.member)
    @is_premium()
    async def color_set(self, ctx: Context, color: str) -> Message:
        """Set your custom embed color (hex code like #FF5733 or color name)"""
        color = color.strip()

        if color.startswith('#'):
            color = color[1:]

        try:
            if len(color) == 6:
                color_int = int(color, 16)
            else:
                color_map = {
                    'red': 0xFF0000, 'blue': 0x0000FF, 'green': 0x00FF00,
                    'yellow': 0xFFFF00, 'purple': 0x800080, 'pink': 0xFFC0CB,
                    'orange': 0xFFA500, 'black': 0x000000, 'white': 0xFFFFFF,
                    'cyan': 0x00FFFF, 'magenta': 0xFF00FF, 'lime': 0x00FF00,
                    'navy': 0x000080, 'teal': 0x008080, 'silver': 0xC0C0C0,
                    'gold': 0xFFD700,
                }
                color_int = color_map.get(color.lower())
                if color_int is None:
                    return await ctx.warn("Invalid color! Use a hex code like `#FF5733` or a color name like `red`, `blue`, `purple`, etc.")
        except ValueError:
            return await ctx.warn("Invalid hex color! Use format like `#FF5733`")

        await self.bot.db_pool.execute(
            """
            INSERT INTO custom_colors (user_id, color)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET color = $2
            """,
            ctx.author.id, color_int
        )

        preview_embed = Embed(
            color=color_int,
            description=f"Your custom color has been set to `#{color_int:06X}`"
        )
        preview_embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        return await ctx.send(embed=preview_embed)

    @color.command(name="remove", aliases=["reset", "delete"])
    @commands.cooldown(1, 5, BucketType.member)
    @is_premium()
    async def color_remove(self, ctx: Context) -> Message:
        """Remove your custom embed color"""
        existing = await self.bot.db_pool.fetchrow(
            "SELECT color FROM custom_colors WHERE user_id = $1",
            ctx.author.id
        )
        if not existing:
            return await ctx.warn("You don't have a custom color set!")

        await self.bot.db_pool.execute(
            "DELETE FROM custom_colors WHERE user_id = $1",
            ctx.author.id
        )
        return await ctx.approve("Removed your custom color.")

    @color.command(name="view", aliases=["show"])
    @commands.cooldown(1, 5, BucketType.member)
    @is_premium()
    async def color_view(self, ctx: Context) -> Message:
        """View your current custom color"""
        existing = await self.bot.db_pool.fetchrow(
            "SELECT color FROM custom_colors WHERE user_id = $1",
            ctx.author.id
        )
        if not existing:
            return await ctx.warn("You don't have a custom color set!")

        color_int = existing['color']
        preview_embed = Embed(
            color=color_int,
            description=f"Your current custom color is `#{color_int:06X}`"
        )
        preview_embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        return await ctx.send(embed=preview_embed)


async def setup(bot):
    await bot.add_cog(Premium(bot))
