from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from pathlib import Path

import discord
import discord_ios
from discord.ext import commands
from dotenv import load_dotenv

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.helpers.context import TormentContext
from bot.helpers.storage import Storage
from bot.helpers.api import Api


logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
LOGGER = logging.getLogger("torment")


class TormentBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.moderation = True
        intents.messages = True
        intents.message_content = True

        super().__init__(
            command_prefix=self.get_prefix,
            help_command=None,
            intents=intents,
            case_insensitive=True,
            strip_after_prefix=True,
            owner_ids={1285277569113133161, 1460003194771083296, 1476894501648863274, 1019668815728103526},
        )
        self.storage = Storage.from_env()
        self.default_prefix = self.require_env("BOT_PREFIX")
        self.spam_tracker: dict[int, list[float]] = {}
        self.spam_cooldowns: dict[int, float] = {}

    async def get_prefix(self, message: discord.Message):
        if not message.guild:
            return commands.when_mentioned_or(self.default_prefix)(self, message)
        
        config = await self.storage.get_config(message.guild.id)
        prefixes = config.get("prefixes") or [self.default_prefix]
        
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        
        return commands.when_mentioned_or(*prefixes)(self, message)

    @staticmethod
    def require_env(name: str) -> str:
        value = os.getenv(name)
        if value is None or not value.strip():
            raise RuntimeError(f"Missing required environment variable: {name}")
        return value.strip()

    async def setup_hook(self) -> None:
        await self.storage.initialize()
        await self.load_extension("jishaku")
        for extension in self.discover_extensions():
            await self.load_extension(extension)
            LOGGER.info("loaded extension %s", extension)
        
        try:
            synced = await self.tree.sync()
            LOGGER.info("synced %d slash commands", len(synced))
        except asyncio.CancelledError:
            LOGGER.warning("slash command sync was cancelled")
            raise
        except Exception as e:
            LOGGER.error("failed to sync slash commands: %s", e)

    async def get_context(self, origin, /, *, cls=TormentContext):
        return await super().get_context(origin, cls=cls)

    def discover_extensions(self) -> list[str]:
        modules_root = Path(__file__).resolve().parent / "modules"
        extensions: list[str] = []
        for path in sorted(modules_root.rglob("*.py")):
            if path.name == "__init__.py":
                continue
            source = path.read_text(encoding="utf-8")
            if not re.search(r"^async\s+def\s+setup\s*\(|^def\s+setup\s*\(", source, flags=re.MULTILINE):
                continue
            relative = path.relative_to(Path(__file__).resolve().parent.parent)
            dotted = ".".join(relative.with_suffix("").parts)
            extensions.append(dotted)
        return extensions

    async def on_ready(self) -> None:
        if self.user:
            LOGGER.info("ready as %s (%s)", self.user, self.user.id)
        
        if not hasattr(self, "start_time"):
            from discord.utils import utcnow
            self.start_time = utcnow()
        
        await self.change_presence(
            activity=discord.CustomActivity(
                name="🔗 torment.lat",
            )
        )

    # ── Private Logging ──────────────────────────────────────────────────────
    # Replace these with your actual webhook URLs and channel IDs.
    _LOG_JOIN_WEBHOOK    = "https://discord.com/api/webhooks/PLACEHOLDER_JOIN"
    _LOG_LEAVE_WEBHOOK   = "https://discord.com/api/webhooks/PLACEHOLDER_LEAVE"
    _LOG_COMMAND_WEBHOOK = "https://discord.com/api/webhooks/PLACEHOLDER_COMMAND"

    async def _send_log(self, webhook_url: str, embed: discord.Embed) -> None:
        if "PLACEHOLDER" in webhook_url:
            return
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                wh = discord.Webhook.from_url(webhook_url, session=session)
                await wh.send(embed=embed, username="torment logs", avatar_url=self.user.display_avatar.url if self.user else None)
        except Exception as e:
            LOGGER.warning("private log failed: %s", e)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        embed = discord.Embed(
            description=f"joined **{guild.name}** (`{guild.id}`)\n{guild.member_count} members",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await self._send_log(self._LOG_JOIN_WEBHOOK, embed)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        embed = discord.Embed(
            description=f"left **{guild.name}** (`{guild.id}`)\n{guild.member_count} members",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await self._send_log(self._LOG_LEAVE_WEBHOOK, embed)

    async def on_command(self, ctx: TormentContext) -> None:
        if not ctx.guild:
            return
        embed = discord.Embed(
            description=(
                f"`{ctx.command.qualified_name}` used by **{ctx.author}** (`{ctx.author.id}`)\n"
                f"**Server:** {ctx.guild.name} (`{ctx.guild.id}`)\n"
                f"**Channel:** {ctx.channel.mention}"
            ),
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        await self._send_log(self._LOG_COMMAND_WEBHOOK, embed)
    # ─────────────────────────────────────────────────────────────────────────

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        
        if message.guild and self.user and self.user in message.mentions:
            content = message.content.replace(f"<@{self.user.id}>", "").replace(f"<@!{self.user.id}>", "").strip()
            if not content and len(message.mentions) == 1 and not message.mention_everyone and not message.role_mentions:
                config = await self.storage.get_config(message.guild.id)
                prefixes = config.get("prefixes") or [self.default_prefix]
                if isinstance(prefixes, str):
                    prefixes = [prefixes]
                
                prefix_list = ", ".join(f"`{p}`" for p in prefixes)
                embed = discord.Embed(
                    description=f"The server's current prefix is: {prefix_list}",
                    color=discord.Color.from_str("#9FAB85")
                )
                await message.channel.send(embed=embed)
                return
        
        await self.process_commands(message)

    async def on_command_error(self, ctx: TormentContext, error: commands.CommandError) -> None:
        if hasattr(ctx.command, "on_error"):
            return

        original = getattr(error, "original", error)
        if isinstance(error, commands.CheckFailure):
            return
        if isinstance(error, (commands.MissingRequiredArgument, commands.MissingRequiredAttachment)):
            if ctx.command:
                await ctx.send_help_embed(ctx.command)
            return
        if isinstance(error, commands.TooManyArguments):
            if ctx.command:
                await ctx.send_help_embed(ctx.command)
            return
        if isinstance(error, commands.BadArgument):
            await ctx.warn(str(error))
            return
        if isinstance(error, commands.NoPrivateMessage):
            return
        if isinstance(error, commands.MissingPermissions):
            missing = ", ".join(permission.replace("_", " ") for permission in error.missing_permissions)
            await ctx.warn(f"You're **missing** permission(s): `{missing}`.")
            return
        if isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(permission.replace("_", " ") for permission in error.missing_permissions)
            await ctx.warn(f"I'm **missing** permission(s): `{missing}`.")
            return
        if isinstance(error, commands.CommandNotFound):
            return

        LOGGER.exception("command error: %s", original)
        await ctx.deny(f"Something went wrong: `{type(original).__name__}`")

    async def invoke(self, ctx: TormentContext) -> None:
        import time

        user_id = ctx.author.id
        current_time = time.time()

        cooldown_until = self.spam_cooldowns.get(user_id, 0)
        if current_time < cooldown_until:
            return

        if user_id not in self.spam_tracker:
            self.spam_tracker[user_id] = []

        self.spam_tracker[user_id] = [
            t for t in self.spam_tracker[user_id]
            if current_time - t < 5
        ]

        if len(self.spam_tracker[user_id]) >= 10:
            self.spam_tracker[user_id] = []
            self.spam_cooldowns[user_id] = current_time + 30
            await ctx.warn(
                f"{ctx.author.mention}: You're **spamming** commands. "
                f"You've been ignored for **30 seconds**."
            )
            return

        self.spam_tracker[user_id].append(current_time)
        await super().invoke(ctx)


async def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    token = TormentBot.require_env("DISCORD_TOKEN")

    os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
    os.environ["JISHAKU_NO_DM_TRACEBACK"] = "True"
    os.environ["JISHAKU_HIDE"] = "True"
    os.environ["JISHAKU_OWNER_IDS"] = os.getenv("JISHAKU_OWNER_IDS", "")

    bot = TormentBot()
    api = Api(bot)
    async with bot:
        await api.start()
        try:
            await bot.start(token)
        finally:
            await bot.storage.close()


if __name__ == "__main__":
    asyncio.run(main())
