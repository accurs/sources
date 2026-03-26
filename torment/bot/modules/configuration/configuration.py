from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Literal, Optional, Union

import asyncpg
import discord
from discord import RateLimited, app_commands
from discord.ext import commands, tasks
from discord.utils import utcnow
from dotenv import load_dotenv
from humanfriendly import format_timespan

from bot.helpers.context import TormentContext, _color
from bot.helpers.converters import Script
from bot.helpers.paginator import Paginator
from .helpers import ProfileManager

load_dotenv()
DB_DSN = os.getenv("DATABASE_URL")


def build_board_embed(message: discord.Message, emoji: str, count: int) -> tuple[str, discord.Embed, discord.ui.View]:
    embed = discord.Embed(color=_color("EMBED_INFO_COLOR"))
    embed.set_author(
        name=message.author.display_name,
        icon_url=message.author.display_avatar.url,
    )
    embed.set_footer(text=_fmt_time(message.created_at))

    if message.reference and isinstance(message.reference.resolved, discord.Message):
        ref = message.reference.resolved
        embed.description = (
            f"*{ref.author.mention}*: {ref.content or '*[No text]*'}\n"
            f"<:reply:1479995468095422596> **{message.content or '*No text.*'}**"
        )
    else:
        embed.description = message.content or ""

    for attachment in message.attachments:
        if attachment.content_type and attachment.content_type.startswith("image/"):
            embed.set_image(url=attachment.url)
            break

    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        style=discord.ButtonStyle.link,
        label="Jump to Message",
        url=message.jump_url,
    ))

    return f"{emoji} **#{count}**", embed, view


def _parse_interval(value: str) -> int:
    match = re.fullmatch(r"(\d+)\s*([smhdw])", value.strip().lower())
    if not match:
        raise ValueError(f"Invalid interval `{value}`. Use `s`, `m`, `h`, `d`, or `w` — e.g. `30m`, `2h`, `1d`.")
    amount, unit = int(match.group(1)), match.group(2)
    seconds = amount * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]
    if seconds < 60:
        raise ValueError("Interval must be at least 1 minute.")
    return seconds


def _fmt_interval(seconds: int) -> str:
    units = [("week", 604800), ("day", 86400), ("hour", 3600), ("minute", 60), ("second", 1)]
    for name, size in units:
        if seconds >= size:
            val = seconds // size
            return f"{val} {name}{'s' if val != 1 else ''}"
    return f"{seconds} seconds"


def _fmt_time(dt: datetime) -> str:
    hour = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.month}/{dt.day}/{str(dt.year)[2:]} • {hour}:{dt.strftime('%M')} {ampm}"


class CommandConverter(commands.Converter):
    async def convert(self, ctx: TormentContext, argument: str):
        command = ctx.bot.get_command(argument)
        if not command or command.hidden:
            raise commands.BadArgument(f"Command `{argument}` not found")
        elif command.qualified_name.startswith("command"):
            raise commands.BadArgument("Cannot manage the command management commands")
        return command


class Configuration(commands.Cog):
    __cog_name__ = "configuration"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.pool: asyncpg.Pool = None
        self.board_posts: dict[str, dict[str, int]] = {}
        self._config_cache: dict[int, asyncpg.Record | None] = {}

    async def cog_load(self) -> None:
        self.pool = await asyncpg.create_pool(dsn=DB_DSN)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS board_config (
                guild_id   BIGINT PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                emoji      TEXT NOT NULL,
                threshold  INTEGER NOT NULL DEFAULT 3,
                enabled    BOOLEAN NOT NULL DEFAULT TRUE
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS board_posts (
                guild_id     BIGINT NOT NULL,
                message_id   BIGINT NOT NULL,
                board_msg_id BIGINT NOT NULL,
                PRIMARY KEY (guild_id, message_id)
            )
        """)
        records = await self.pool.fetch("SELECT * FROM board_posts")
        for record in records:
            guild_posts = self.board_posts.setdefault(str(record["guild_id"]), {})
            guild_posts[str(record["message_id"])] = record["board_msg_id"]

        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS reaction_roles (
                guild_id   BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                emoji      TEXT NOT NULL,
                role_id    BIGINT NOT NULL,
                PRIMARY KEY (guild_id, message_id, emoji)
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS pingonjoin (
                guild_id   BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message    TEXT,
                PRIMARY KEY (guild_id, channel_id)
            )
        """)
        await self.pool.execute("""
            ALTER TABLE pingonjoin ADD COLUMN IF NOT EXISTS message TEXT
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS aliases (
                guild_id BIGINT NOT NULL,
                alias    TEXT NOT NULL,
                command  TEXT NOT NULL,
                PRIMARY KEY (guild_id, alias)
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS counter (
                guild_id          BIGINT NOT NULL,
                channel_id        BIGINT NOT NULL,
                option            TEXT NOT NULL,
                last_update       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                rate_limited_until TIMESTAMPTZ,
                PRIMARY KEY (guild_id, channel_id)
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS button_roles (
                guild_id   BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                role_id    BIGINT NOT NULL,
                style      TEXT NOT NULL DEFAULT 'blurple',
                emoji      TEXT,
                label      TEXT,
                PRIMARY KEY (message_id, role_id)
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS vanity_config (
                guild_id   BIGINT PRIMARY KEY,
                substring  TEXT,
                channel_id BIGINT,
                message    TEXT
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS vanity_roles (
                guild_id BIGINT NOT NULL,
                role_id  BIGINT NOT NULL,
                PRIMARY KEY (guild_id, role_id)
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS vanity_members (
                guild_id BIGINT NOT NULL,
                user_id  BIGINT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS timers (
                guild_id   BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                interval   INTERVAL NOT NULL,
                message    TEXT NOT NULL,
                next_send  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, channel_id)
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS reaction_triggers (
                guild_id BIGINT NOT NULL,
                emoji    TEXT NOT NULL,
                PRIMARY KEY (guild_id, emoji)
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS reaction_trigger_words (
                guild_id BIGINT NOT NULL,
                emoji    TEXT NOT NULL,
                trigger  TEXT NOT NULL,
                PRIMARY KEY (guild_id, emoji, trigger)
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS reaction_message_channels (
                guild_id   BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                emoji      TEXT NOT NULL,
                PRIMARY KEY (guild_id, channel_id, emoji)
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS booster_roles (
                guild_id BIGINT NOT NULL,
                user_id  BIGINT NOT NULL,
                role_id  BIGINT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS booster_role_config (
                guild_id     BIGINT PRIMARY KEY,
                base_role_id BIGINT,
                enabled      BOOLEAN NOT NULL DEFAULT FALSE
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS booster_role_include (
                guild_id BIGINT NOT NULL,
                role_id  BIGINT NOT NULL,
                PRIMARY KEY (guild_id, role_id)
            )
        """)
        rows = await self.pool.fetch("SELECT DISTINCT message_id FROM button_roles")
        for row in rows:
            view = ButtonRoleView(self.pool, row["message_id"])
            await view.rebuild(self.bot)
            self.bot.add_view(view, message_id=row["message_id"])
        
        self.bot.add_check(self.command_check)
        self.update_statistics.start()
        self._timer_task.start()

    async def cog_unload(self) -> None:
        if self.pool:
            await self.pool.close()
        self.update_statistics.cancel()
        self._timer_task.cancel()
        self.bot.remove_check(self.command_check)

    async def command_check(self, ctx: TormentContext) -> bool:
        if not ctx.guild or not ctx.command:
            return True
        
        if ctx.author.guild_permissions.administrator:
            return True
        
        command_name = ctx.command.qualified_name
        parent_name = ctx.command.full_parent_name if ctx.command.parent else ""
        
        if isinstance(ctx.channel, discord.TextChannel):
            query = """
                SELECT 1 FROM command_disabled
                WHERE channel_id = $1 AND (command = $2 OR command = $3)
            """
            disabled = await self.pool.fetchval(
                query, ctx.channel.id, command_name, parent_name
            )
            if disabled:
                await ctx.warn(f"The `{command_name}` command is disabled in this channel")
                return False
        
        query = """
            SELECT 1 FROM command_restricted
            WHERE guild_id = $1
            AND NOT role_id = ANY($2::BIGINT[])
            AND (command = $3 OR command = $4)
        """
        role_ids = [role.id for role in ctx.author.roles]
        restricted = await self.pool.fetchval(
            query, ctx.guild.id, role_ids, command_name, parent_name
        )
        
        if restricted:
            await ctx.warn(f"You don't have access to use the `{command_name}` command")
            return False
        
        return True

    async def get_board_config(self, guild_id: int) -> asyncpg.Record | None:
        if guild_id not in self._config_cache:
            self._config_cache[guild_id] = await self.pool.fetchrow(
                "SELECT * FROM board_config WHERE guild_id = $1", guild_id
            )
        return self._config_cache[guild_id]

    def _invalidate_config(self, guild_id: int) -> None:
        self._config_cache.pop(guild_id, None)

    async def get_reaction_count(self, message: discord.Message, emoji: str) -> int:
        for reaction in message.reactions:
            if str(reaction.emoji) == emoji:
                return reaction.count
        return 0

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        config = await self.get_board_config(payload.guild_id)
        if not config or not config["enabled"] or not config["channel_id"] or not config["emoji"]:
            return
        if str(payload.emoji) != config["emoji"]:
            return

        guild = self.bot.get_guild(payload.guild_id)
        channel = guild and guild.get_channel(payload.channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.HTTPException):
            return

        count = await self.get_reaction_count(message, config["emoji"])
        if count < config["threshold"]:
            return

        board_channel = guild.get_channel(config["channel_id"])
        if not board_channel:
            return

        guild_posts = self.board_posts.setdefault(str(payload.guild_id), {})
        msg_key = str(message.id)
        content, embed, view = build_board_embed(message, config["emoji"], count)

        if msg_key in guild_posts:
            try:
                board_msg = await board_channel.fetch_message(guild_posts[msg_key])
                await board_msg.edit(content=content, embed=embed)
            except discord.NotFound:
                del guild_posts[msg_key]
                await self.pool.execute(
                    "DELETE FROM board_posts WHERE guild_id = $1 AND message_id = $2",
                    payload.guild_id, message.id,
                )
                board_msg = await board_channel.send(content=content, embed=embed, view=view)
                guild_posts[msg_key] = board_msg.id
                await self.pool.execute(
                    "INSERT INTO board_posts (guild_id, message_id, board_msg_id) VALUES ($1, $2, $3)",
                    payload.guild_id, message.id, board_msg.id,
                )
            return

        board_msg = await board_channel.send(content=content, embed=embed, view=view)
        guild_posts[msg_key] = board_msg.id
        await self.pool.execute(
            "INSERT INTO board_posts (guild_id, message_id, board_msg_id) VALUES ($1, $2, $3)",
            payload.guild_id, message.id, board_msg.id,
        )

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        config = await self.get_board_config(payload.guild_id)
        if not config or not config["enabled"] or not config["channel_id"] or not config["emoji"]:
            return
        if str(payload.emoji) != config["emoji"]:
            return

        guild = self.bot.get_guild(payload.guild_id)
        channel = guild and guild.get_channel(payload.channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.HTTPException):
            return

        count = await self.get_reaction_count(message, config["emoji"])
        board_channel = guild.get_channel(config["channel_id"])
        guild_posts = self.board_posts.get(str(payload.guild_id), {})
        msg_key = str(message.id)

        if msg_key in guild_posts and board_channel:
            try:
                board_msg = await board_channel.fetch_message(guild_posts[msg_key])
                content, embed, view = build_board_embed(message, config["emoji"], count)
                await board_msg.edit(content=content, embed=embed)
            except discord.NotFound:
                guild_posts.pop(msg_key, None)
                await self.pool.execute(
                    "DELETE FROM board_posts WHERE guild_id = $1 AND message_id = $2",
                    payload.guild_id, message.id,
                )

    @commands.hybrid_group(
        name="customize",
        aliases=["customise", "custom"],
        invoke_without_command=True,
        help="Customize the bot's appearance and profile in your server",
        extras={"parameters": "n/a", "usage": "customize"},
    )
    async def customize(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @customize.group(
        name="avatar",
        aliases=["pfp"],
        invoke_without_command=True,
        help="Set a custom server profile picture for the bot",
        extras={"parameters": "url|attachment", "usage": "customize avatar [url|attachment]"},
    )
    @commands.has_permissions(administrator=True)
    @app_commands.describe(url="The URL of the avatar image (or attach an image)")
    async def customize_avatar(self, ctx: TormentContext, url: str = None) -> None:
        try:
            if url is None and ctx.message.attachments:
                attachment = ctx.message.attachments[0]
                await ProfileManager(self.bot).update_profile(ctx.guild.id, avatar=attachment)
            elif url:
                await ProfileManager(self.bot).update_profile(ctx.guild.id, avatar=url)
            else:
                return await ctx.warn("Please provide a URL or attach an image!")
            await ctx.success("Updated the bot's profile picture for this server")
        except Exception as e:
            await ctx.warn(f"Failed to update profile picture: {str(e)}")

    @customize_avatar.command(
        name="remove",
        aliases=["reset"],
        help="Remove the bot's custom server profile picture",
        extras={"parameters": "n/a", "usage": "customize avatar remove"},
    )
    @commands.has_permissions(administrator=True)
    async def customize_avatar_remove(self, ctx: TormentContext) -> None:
        try:
            profile = await ProfileManager(self.bot).get_profile(ctx.guild.id, ctx.guild.me.id)
            if not profile.guild_avatar:
                return await ctx.warn("There is no custom profile picture set for this server!")
            await ProfileManager(self.bot).update_profile(ctx.guild.id, avatar=None)
            await ctx.success("Successfully removed the bot's custom profile picture")
        except Exception as e:
            await ctx.warn(f"Failed to reset profile picture: {str(e)}")

    @customize.group(
        name="banner",
        invoke_without_command=True,
        help="Set a custom server banner for the bot's profile",
        extras={"parameters": "url|attachment", "usage": "customize banner [url|attachment]"},
    )
    @commands.has_permissions(administrator=True)
    @app_commands.describe(url="The URL of the banner image (or attach an image)")
    async def customize_banner(self, ctx: TormentContext, url: str = None) -> None:
        try:
            if url is None and ctx.message.attachments:
                attachment = ctx.message.attachments[0]
                await ProfileManager(self.bot).update_profile(ctx.guild.id, banner=attachment)
            elif url:
                await ProfileManager(self.bot).update_profile(ctx.guild.id, banner=url)
            else:
                return await ctx.warn("Please provide a URL or attach an image!")
            await ctx.success("Successfully updated the bot's banner for this server")
        except Exception as e:
            await ctx.warn(f"Failed to update banner: {str(e)}")

    @customize_banner.command(
        name="remove",
        aliases=["reset"],
        help="Remove the bot's custom server banner",
        extras={"parameters": "n/a", "usage": "customize banner remove"},
    )
    @commands.has_permissions(administrator=True)
    async def customize_banner_remove(self, ctx: TormentContext) -> None:
        try:
            profile = await ProfileManager(self.bot).get_profile(ctx.guild.id, ctx.guild.me.id)
            if not profile.guild_banner:
                return await ctx.warn("There is no custom banner set for this server!")
            await ProfileManager(self.bot).update_profile(ctx.guild.id, banner=None)
            await ctx.success("Successfully removed the bot's custom banner")
        except Exception as e:
            await ctx.warn(f"Failed to reset banner: {str(e)}")

    @customize.group(
        name="bio",
        invoke_without_command=True,
        help="Set a custom bio for the bot's server profile",
        extras={"parameters": "bio", "usage": "customize bio (bio)"},
    )
    @commands.has_permissions(administrator=True)
    @app_commands.describe(bio="The bio text to set for the bot")
    async def customize_bio(self, ctx: TormentContext, *, bio: str = None) -> None:
        try:
            if bio is None:
                return await ctx.warn("Please provide a bio to set!")
            await ProfileManager(self.bot).update_profile(ctx.guild.id, bio=bio)
            await ctx.success("Successfully updated the bot's bio for this server")
        except Exception as e:
            await ctx.warn(f"Failed to update bio: {str(e)}")

    @customize_bio.command(
        name="remove",
        aliases=["reset"],
        help="Remove the bot's custom server bio",
        extras={"parameters": "n/a", "usage": "customize bio remove"},
    )
    @commands.has_permissions(administrator=True)
    async def customize_bio_remove(self, ctx: TormentContext) -> None:
        try:
            profile = await ProfileManager(self.bot).get_profile(ctx.guild.id, ctx.guild.me.id)
            if not profile.bio:
                return await ctx.warn("There is no custom bio set for this server!")
            await ProfileManager(self.bot).update_profile(ctx.guild.id, bio=None)
            await ctx.success("Successfully removed the bot's custom bio")
        except Exception as e:
            await ctx.warn(f"Failed to reset bio: {str(e)}")

    @customize.group(
        name="name",
        invoke_without_command=True,
        help="Set a custom nickname for the bot in your server",
        extras={"parameters": "name", "usage": "customize name (name)"},
    )
    @commands.has_permissions(administrator=True)
    @app_commands.describe(name="The nickname to set for the bot")
    async def customize_name(self, ctx: TormentContext, *, name: str = None) -> None:
        if name is None:
            return await ctx.warn("Please provide a name to set!")
        await ctx.guild.me.edit(nick=name)
        await ctx.success("Successfully updated the bot's nickname for this server")

    @customize_name.command(
        name="remove",
        aliases=["reset"],
        help="Remove the bot's custom server nickname",
        extras={"parameters": "n/a", "usage": "customize name remove"},
    )
    @commands.has_permissions(administrator=True)
    async def customize_name_remove(self, ctx: TormentContext) -> None:
        if not ctx.guild.me.nick:
            return await ctx.warn("The bot's name is already set to default!")
        await ctx.guild.me.edit(nick=None)
        await ctx.success("Successfully removed the bot's custom nickname")

    @customize.command(
        name="view",
        help="View the bot's current customization settings in your server",
        extras={"parameters": "n/a", "usage": "customize view"},
    )
    @commands.has_permissions(administrator=True)
    async def customize_view(self, ctx: TormentContext) -> None:
        manager = ProfileManager(self.bot)
        profile = await manager.get_profile(ctx.guild.id, ctx.guild.me.id)
        embed = await manager.create_profile_embed(ctx, profile)
        if embed:
            await ctx.reply(embed=embed)

    @customize.command(
        name="reset",
        aliases=["remove"],
        help="Reset all of the bot's customization settings in your server",
        extras={"parameters": "n/a", "usage": "customize reset"},
    )
    @commands.has_permissions(administrator=True)
    async def customize_remove(self, ctx: TormentContext) -> None:
        profile = await ProfileManager(self.bot).get_profile(ctx.guild.id, ctx.guild.me.id)
        if not profile.guild_avatar and not profile.guild_banner and not profile.bio and not ctx.guild.me.nick:
            return await ctx.warn("No customizations are currently set for this server!")

        if not await ctx.confirm("Are you sure you want to reset the bot's profile customization?"):
            return

        try:
            await ctx.guild.me.edit(nick=None)
            await ProfileManager(self.bot).reset_profile(ctx.guild.id)
            await ctx.success("Successfully reset all profile customization settings")
        except Exception as e:
            await ctx.warn(f"Failed to reset profile: {str(e)}")

    @commands.hybrid_group(
        name="prefix",
        aliases=["prefixes"],
        invoke_without_command=True,
        help="View or manage the bot's custom prefixes for your server",
        extras={"parameters": "n/a", "usage": "prefix"},
    )
    async def prefix(self, ctx: TormentContext) -> None:
        if not ctx.guild:
            return await ctx.warn("This command can only be used in a server!")

        config = await self.bot.storage.get_config(ctx.guild.id)
        prefixes = config.get("prefixes") or [self.bot.command_prefix]

        if isinstance(prefixes, str):
            prefixes = [prefixes]

        prefix_list = ", ".join([f"`{p}`" for p in prefixes])

        if len(prefixes) > 1:
            await ctx.info(f"The prefixes for this server are {prefix_list}")
        else:
            await ctx.info(f"The prefix for this server is {prefix_list}")

    @prefix.command(
        name="set",
        help="Set a single custom prefix for the server",
        extras={"parameters": "prefix", "usage": "prefix set (prefix)"},
    )
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(prefix="The new prefix to set for the server")
    async def prefix_set(self, ctx: TormentContext, prefix: str) -> None:
        if not ctx.guild:
            return

        if not prefix:
            return await ctx.warn("You must provide a prefix to set!")

        if len(prefix) > 10:
            return await ctx.warn("Prefix cannot be longer than 10 characters!")

        config = await self.bot.storage.get_config(ctx.guild.id)
        current_prefixes = config.get("prefixes")

        if current_prefixes and len(current_prefixes) > 0:
            if not await ctx.confirm(
                f"Are you sure you want to set the server's prefix to `{prefix}`? "
                f"This will override the {len(current_prefixes)} existing prefix{'es' if len(current_prefixes) > 1 else ''}"
            ):
                return

        await self.bot.storage.set_prefixes(ctx.guild.id, [prefix])
        await ctx.success(f"Successfully set the server's prefix to `{prefix}`")

    @prefix.command(
        name="add",
        help="Add an additional prefix to the server",
        extras={"parameters": "prefix", "usage": "prefix add (prefix)"},
    )
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(prefix="The prefix to add to the server")
    async def prefix_add(self, ctx: TormentContext, prefix: str) -> None:
        if not ctx.guild:
            return

        if not prefix:
            return await ctx.warn("You must provide a prefix to add!")

        if len(prefix) > 5:
            return await ctx.warn("Prefix cannot be longer than 5 characters!")

        config = await self.bot.storage.get_config(ctx.guild.id)
        prefixes = config.get("prefixes") or [self.bot.command_prefix]

        if isinstance(prefixes, str):
            prefixes = [prefixes]

        if prefix in prefixes:
            return await ctx.warn(f"The prefix `{prefix}` is already in the server's prefixes!")

        prefixes.append(prefix)
        await self.bot.storage.set_prefixes(ctx.guild.id, prefixes)
        await ctx.success(f"Successfully added the prefix `{prefix}`")

    @prefix.command(
        name="remove",
        aliases=["delete", "del", "rm"],
        help="Remove a prefix from the server",
        extras={"parameters": "prefix", "usage": "prefix remove (prefix)"},
    )
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(prefix="The prefix to remove from the server")
    async def prefix_remove(self, ctx: TormentContext, prefix: str) -> None:
        if not ctx.guild:
            return

        if not prefix:
            return await ctx.warn("You must provide a prefix to remove!")

        config = await self.bot.storage.get_config(ctx.guild.id)
        prefixes = config.get("prefixes") or [self.bot.command_prefix]

        if isinstance(prefixes, str):
            prefixes = [prefixes]

        if prefix not in prefixes:
            return await ctx.warn(f"The prefix `{prefix}` is not in the server's prefixes!")

        if len(prefixes) == 1:
            return await ctx.warn("You cannot remove the last prefix! Use `prefix reset` to reset to default.")

        prefixes.remove(prefix)
        await self.bot.storage.set_prefixes(ctx.guild.id, prefixes)
        await ctx.success(f"Successfully removed the prefix `{prefix}`")

    @prefix.command(
        name="reset",
        help="Reset the server's prefixes to the default",
        extras={"parameters": "n/a", "usage": "prefix reset"},
    )
    @commands.has_permissions(manage_guild=True)
    async def prefix_reset(self, ctx: TormentContext) -> None:
        if not ctx.guild:
            return

        await self.bot.storage.set_prefixes(ctx.guild.id, None)
        await ctx.success("Successfully reset the server's prefixes to the default")

    @commands.group(
        name="board",
        aliases=["skullboard", "starboard", "sb"],
        invoke_without_command=True,
        help="Manage the server board",
        extras={"parameters": "n/a", "usage": "board"},
    )
    async def board_group(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @board_group.command(
        name="add",
        aliases=["setup"],
        help="Set up the board system in a channel",
        extras={"parameters": "channel, emoji, threshold", "usage": "board add (channel) (emoji) (threshold)"},
    )
    @commands.has_permissions(manage_channels=True)
    async def board_add(self, ctx: TormentContext, channel: discord.TextChannel, emoji: str, threshold: int) -> None:
        config = await self.get_board_config(ctx.guild.id)
        if not config or not config["enabled"]:
            prefix = ctx.prefix or ",,"
            await ctx.warn(f"The board isn't **toggled**. Use `{prefix}board toggle` to toggle it.")
            return

        await self.pool.execute("""
            INSERT INTO board_config (guild_id, channel_id, emoji, threshold, enabled)
            VALUES ($1, $2, $3, $4, TRUE)
            ON CONFLICT (guild_id) DO UPDATE
            SET channel_id = $2, emoji = $3, threshold = $4
        """, ctx.guild.id, channel.id, emoji, threshold)
        self._invalidate_config(ctx.guild.id)
        await ctx.success(f"board set up in {channel.mention}.")

    @board_group.command(
        name="configuration",
        aliases=["config"],
        help="View the current board configuration",
        extras={"parameters": "n/a", "usage": "board config"},
    )
    @commands.has_permissions(manage_channels=True)
    async def board_config(self, ctx: TormentContext) -> None:
        config = await self.get_board_config(ctx.guild.id)
        if not config:
            await ctx.warn("No **board** data found for this server.")
            return

        embed = discord.Embed(
            title="Board Configuration",
            color=_color("EMBED_INFO_COLOR"),
            description="\n".join([
                f"**Channel:** <#{config['channel_id']}>",
                f"**Emoji:** {config['emoji']}",
                f"**Threshold:** `{config['threshold']}`",
                f"**Toggled:** `{'On' if config['enabled'] else 'Off'}`",
            ]),
        )
        if ctx.guild.icon:
            embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url)
        else:
            embed.set_author(name=ctx.guild.name)
        await ctx.send(embed=embed)

    @board_group.command(
        name="reset",
        aliases=["remove", "disable"],
        help="Reset the board configuration for a channel",
        extras={"parameters": "channel", "usage": "board reset (channel)"},
    )
    @commands.has_permissions(manage_channels=True)
    async def board_reset(self, ctx: TormentContext, channel: discord.TextChannel) -> None:
        config = await self.get_board_config(ctx.guild.id)
        if not config:
            await ctx.warn("No **board** data found for this server.")
            return
        if config["channel_id"] != channel.id:
            await ctx.warn("That channel doesn't have the **board** configured.")
            return

        await self.pool.execute("DELETE FROM board_config WHERE guild_id = $1", ctx.guild.id)
        await self.pool.execute("DELETE FROM board_posts WHERE guild_id = $1", ctx.guild.id)
        self.board_posts.pop(str(ctx.guild.id), None)
        self._invalidate_config(ctx.guild.id)
        await ctx.success(f"reset the **board** in {channel.mention}.")

    @board_group.command(
        name="toggle",
        help="Toggle the board on or off",
        extras={"parameters": "n/a", "usage": "board toggle"},
    )
    @commands.has_permissions(manage_channels=True)
    async def board_toggle(self, ctx: TormentContext) -> None:
        config = await self.get_board_config(ctx.guild.id)

        if not config:
            await self.pool.execute("""
                INSERT INTO board_config (guild_id, channel_id, emoji, threshold, enabled)
                VALUES ($1, 0, '', 3, TRUE)
                ON CONFLICT DO NOTHING
            """, ctx.guild.id)
            self._invalidate_config(ctx.guild.id)
            await ctx.success("toggled the **board** on.")
            return

        new_state = not config["enabled"]
        await self.pool.execute(
            "UPDATE board_config SET enabled = $1 WHERE guild_id = $2",
            new_state, ctx.guild.id,
        )
        self._invalidate_config(ctx.guild.id)
        state_str = "on" if new_state else "off"
        await ctx.success(f"toggled the **board** {state_str}.")

    @commands.group(
        name="welcome",
        aliases=["welc"],
        invoke_without_command=True,
        help="Configure welcome messages for new members",
        extras={"parameters": "n/a", "usage": "welcome"},
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @welcome.command(
        name="add",
        aliases=["create", "set"],
        help="Add a welcome message to a channel with embed scripting support",
        extras={"parameters": "channel, script", "usage": "welcome add (channel) (script)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_add(
        self, ctx: TormentContext, channel: discord.TextChannel, *, message: str
    ) -> None:
        if not ctx.guild:
            return

        try:
            await self.bot.storage.add_welcome_message(ctx.guild.id, channel.id, message)
            await ctx.success(f"set welcome message for {channel.mention}")
        except Exception as e:
            await ctx.warn(f"Failed to add welcome message: {str(e)}")

    @welcome.command(
        name="remove",
        aliases=["delete", "del", "rm"],
        help="Remove a welcome message from a channel",
        extras={"parameters": "channel", "usage": "welcome remove (channel)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_remove(
        self, ctx: TormentContext, channel: discord.TextChannel
    ) -> None:
        if not ctx.guild:
            return

        try:
            removed = await self.bot.storage.remove_welcome_message(
                ctx.guild.id, channel.id
            )
            if removed:
                await ctx.success(f"removed welcome message from {channel.mention}")
            else:
                await ctx.warn(f"No welcome message found for {channel.mention}")
        except Exception as e:
            await ctx.warn(f"Failed to remove welcome message: {str(e)}")

    @welcome.command(
        name="list",
        help="View all configured welcome messages",
        extras={"parameters": "n/a", "usage": "welcome list"},
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_list(self, ctx: TormentContext) -> None:
        if not ctx.guild:
            return

        try:
            messages = await self.bot.storage.get_welcome_messages(ctx.guild.id)

            if not messages:
                return await ctx.warn("No welcome messages configured!")

            channels = []
            for msg in messages:
                channel = ctx.guild.get_channel(msg["channel_id"])
                if channel:
                    channels.append(f"{channel.mention} - `{msg['message'][:50]}...`")

            embed = discord.Embed(
                title="Welcome Messages", color=_color("EMBED_INFO_COLOR")
            )
            paginator = Paginator(ctx, channels, embed)
            await paginator.start()
        except Exception as e:
            await ctx.warn(f"Failed to list welcome messages: {str(e)}")

    @welcome.command(
        name="clear",
        aliases=["reset"],
        help="Remove all welcome messages",
        extras={"parameters": "n/a", "usage": "welcome clear"},
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_clear(self, ctx: TormentContext) -> None:
        if not ctx.guild:
            return

        if not await ctx.confirm("Are you sure you want to remove all welcome messages?"):
            return

        try:
            count = await self.bot.storage.clear_welcome_messages(ctx.guild.id)
            if count > 0:
                await ctx.success(f"removed {count} welcome message{'s' if count != 1 else ''}")
            else:
                await ctx.warn("No welcome messages to clear!")
        except Exception as e:
            await ctx.warn(f"Failed to clear welcome messages: {str(e)}")

    @welcome.command(
        name="test",
        aliases=["preview"],
        help="Test a welcome message with the current user",
        extras={"parameters": "channel", "usage": "welcome test (channel)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_test(
        self, ctx: TormentContext, channel: discord.TextChannel
    ) -> None:
        if not ctx.guild:
            return

        try:
            messages = await self.bot.storage.get_welcome_messages(ctx.guild.id)
            welcome_msg = next(
                (msg for msg in messages if msg["channel_id"] == channel.id), None
            )

            if not welcome_msg:
                return await ctx.warn(f"No welcome message found for {channel.mention}")

            script = Script(welcome_msg["message"], [ctx.guild, channel, ctx.author])
            await script.send(ctx.channel)
        except Exception as e:
            await ctx.warn(f"Failed to test welcome message: {str(e)}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        try:
            messages = await self.bot.storage.get_welcome_messages(member.guild.id)
            if messages:
                for msg in messages:
                    channel = member.guild.get_channel(msg["channel_id"])
                    if not isinstance(channel, discord.TextChannel):
                        continue
                    script = Script(msg["message"], [member.guild, channel, member])
                    try:
                        await script.send(channel)
                    except discord.HTTPException:
                        pass
        except Exception:
            pass

        if not member.bot:
            try:
                rows = await self.pool.fetch(
                    "SELECT role_id FROM autoroles WHERE guild_id = $1", member.guild.id
                )
                if rows:
                    roles = [member.guild.get_role(r["role_id"]) for r in rows]
                    roles = [r for r in roles if r and r < member.guild.me.top_role]
                    if roles:
                        await member.add_roles(*roles, reason="autorole")
            except discord.HTTPException:
                pass

    @commands.group(
        name="goodbye",
        invoke_without_command=True,
        help="Configure goodbye messages for members who leave",
        extras={"parameters": "n/a", "usage": "goodbye"},
    )
    @commands.has_permissions(manage_guild=True)
    async def goodbye(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @goodbye.command(
        name="add",
        aliases=["create", "set"],
        help="Add a goodbye message to a channel with embed scripting support",
        extras={"parameters": "channel, script", "usage": "goodbye add (channel) (script)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def goodbye_add(
        self, ctx: TormentContext, channel: discord.TextChannel, *, message: str
    ) -> None:
        if not ctx.guild:
            return

        try:
            await self.bot.storage.add_goodbye_message(ctx.guild.id, channel.id, message)
            await ctx.success(f"set goodbye message for {channel.mention}")
        except Exception as e:
            await ctx.warn(f"Failed to add goodbye message: {str(e)}")

    @goodbye.command(
        name="remove",
        aliases=["delete", "del", "rm"],
        help="Remove a goodbye message from a channel",
        extras={"parameters": "channel", "usage": "goodbye remove (channel)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def goodbye_remove(
        self, ctx: TormentContext, channel: discord.TextChannel
    ) -> None:
        if not ctx.guild:
            return

        try:
            removed = await self.bot.storage.remove_goodbye_message(
                ctx.guild.id, channel.id
            )
            if removed:
                await ctx.success(f"removed goodbye message from {channel.mention}")
            else:
                await ctx.warn(f"No goodbye message found for {channel.mention}")
        except Exception as e:
            await ctx.warn(f"Failed to remove goodbye message: {str(e)}")

    @goodbye.command(
        name="list",
        help="View all configured goodbye messages",
        extras={"parameters": "n/a", "usage": "goodbye list"},
    )
    @commands.has_permissions(manage_guild=True)
    async def goodbye_list(self, ctx: TormentContext) -> None:
        if not ctx.guild:
            return

        try:
            messages = await self.bot.storage.get_goodbye_messages(ctx.guild.id)

            if not messages:
                return await ctx.warn("No goodbye messages configured!")

            channels = []
            for msg in messages:
                channel = ctx.guild.get_channel(msg["channel_id"])
                if channel:
                    channels.append(f"{channel.mention} - `{msg['message'][:50]}...`")

            embed = discord.Embed(
                title="Goodbye Messages", color=_color("EMBED_INFO_COLOR")
            )
            paginator = Paginator(ctx, channels, embed)
            await paginator.start()
        except Exception as e:
            await ctx.warn(f"Failed to list goodbye messages: {str(e)}")

    @goodbye.command(
        name="test",
        aliases=["preview"],
        help="Test a goodbye message with the current user",
        extras={"parameters": "channel", "usage": "goodbye test (channel)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def goodbye_test(
        self, ctx: TormentContext, channel: discord.TextChannel
    ) -> None:
        if not ctx.guild:
            return

        try:
            messages = await self.bot.storage.get_goodbye_messages(ctx.guild.id)
            goodbye_msg = next(
                (msg for msg in messages if msg["channel_id"] == channel.id), None
            )

            if not goodbye_msg:
                return await ctx.warn(f"No goodbye message found for {channel.mention}")

            script = Script(goodbye_msg["message"], [ctx.guild, channel, ctx.author])
            await script.send(ctx.channel)
        except Exception as e:
            await ctx.warn(f"Failed to test goodbye message: {str(e)}")

    @goodbye.command(
        name="clear",
        aliases=["reset"],
        help="Remove all goodbye messages",
        extras={"parameters": "n/a", "usage": "goodbye clear"},
    )
    @commands.has_permissions(manage_guild=True)
    async def goodbye_clear(self, ctx: TormentContext) -> None:
        if not ctx.guild:
            return

        if not await ctx.confirm("Are you sure you want to remove all goodbye messages?"):
            return

        try:
            count = await self.bot.storage.clear_goodbye_messages(ctx.guild.id)
            if count > 0:
                await ctx.success(f"removed {count} goodbye message{'s' if count != 1 else ''}")
            else:
                await ctx.warn("No goodbye messages to clear!")
        except Exception as e:
            await ctx.warn(f"Failed to clear goodbye messages: {str(e)}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        try:
            messages = await self.bot.storage.get_goodbye_messages(member.guild.id)

            if not messages:
                return

            for msg in messages:
                channel = member.guild.get_channel(msg["channel_id"])
                if not isinstance(channel, discord.TextChannel):
                    continue

                script = Script(msg["message"], [member.guild, channel, member])
                try:
                    await script.send(channel)
                except discord.HTTPException:
                    pass
        except Exception:
            pass

    @commands.group(
        name="boost",
        aliases=["booster"],
        invoke_without_command=True,
        help="Configure boost messages for server boosters",
        extras={"parameters": "n/a", "usage": "boost"},
    )
    @commands.has_permissions(manage_guild=True)
    async def boost(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @boost.command(
        name="add",
        aliases=["create", "set"],
        help="Add a boost message to a channel with embed scripting support",
        extras={"parameters": "channel, script", "usage": "boost add (channel) (script)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def boost_add(
        self, ctx: TormentContext, channel: discord.TextChannel, *, message: str
    ) -> None:
        if not ctx.guild:
            return

        try:
            await self.bot.storage.add_boost_message(ctx.guild.id, channel.id, message)
            await ctx.success(f"set boost message for {channel.mention}")
        except Exception as e:
            await ctx.warn(f"Failed to add boost message: {str(e)}")

    @boost.command(
        name="remove",
        aliases=["delete", "del", "rm"],
        help="Remove a boost message from a channel",
        extras={"parameters": "channel", "usage": "boost remove (channel)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def boost_remove(
        self, ctx: TormentContext, channel: discord.TextChannel
    ) -> None:
        if not ctx.guild:
            return

        try:
            removed = await self.bot.storage.remove_boost_message(
                ctx.guild.id, channel.id
            )
            if removed:
                await ctx.success(f"removed boost message from {channel.mention}")
            else:
                await ctx.warn(f"No boost message found for {channel.mention}")
        except Exception as e:
            await ctx.warn(f"Failed to remove boost message: {str(e)}")

    @boost.command(
        name="list",
        help="View all configured boost messages",
        extras={"parameters": "n/a", "usage": "boost list"},
    )
    @commands.has_permissions(manage_guild=True)
    async def boost_list(self, ctx: TormentContext) -> None:
        if not ctx.guild:
            return

        try:
            messages = await self.bot.storage.get_boost_messages(ctx.guild.id)

            if not messages:
                return await ctx.warn("No boost messages configured!")

            channels = []
            for msg in messages:
                channel = ctx.guild.get_channel(msg["channel_id"])
                if channel:
                    channels.append(f"{channel.mention} - `{msg['message'][:50]}...`")

            embed = discord.Embed(
                title="Boost Messages", color=_color("EMBED_INFO_COLOR")
            )
            paginator = Paginator(ctx, channels, embed)
            await paginator.start()
        except Exception as e:
            await ctx.warn(f"Failed to list boost messages: {str(e)}")

    @boost.command(
        name="test",
        aliases=["preview"],
        help="Test a boost message with the current user",
        extras={"parameters": "channel", "usage": "boost test (channel)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def boost_test(
        self, ctx: TormentContext, channel: discord.TextChannel
    ) -> None:
        if not ctx.guild:
            return

        try:
            messages = await self.bot.storage.get_boost_messages(ctx.guild.id)
            boost_msg = next(
                (msg for msg in messages if msg["channel_id"] == channel.id), None
            )

            if not boost_msg:
                return await ctx.warn(f"No boost message found for {channel.mention}")

            script = Script(boost_msg["message"], [ctx.guild, channel, ctx.author])
            await script.send(ctx.channel)
        except Exception as e:
            await ctx.warn(f"Failed to test boost message: {str(e)}")

    @boost.command(
        name="clear",
        aliases=["reset"],
        help="Remove all boost messages",
        extras={"parameters": "n/a", "usage": "boost clear"},
    )
    @commands.has_permissions(manage_guild=True)
    async def boost_clear(self, ctx: TormentContext) -> None:
        if not ctx.guild:
            return

        if not await ctx.confirm("Are you sure you want to remove all boost messages?"):
            return

        try:
            count = await self.bot.storage.clear_boost_messages(ctx.guild.id)
            if count > 0:
                await ctx.success(f"removed {count} boost message{'s' if count != 1 else ''}")
            else:
                await ctx.warn("No boost messages to clear!")
        except Exception as e:
            await ctx.warn(f"Failed to clear boost messages: {str(e)}")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.premium_since is None and after.premium_since is not None:
            try:
                messages = await self.bot.storage.get_boost_messages(after.guild.id)

                if not messages:
                    return

                for msg in messages:
                    channel = after.guild.get_channel(msg["channel_id"])
                    if not isinstance(channel, discord.TextChannel):
                        continue

                    script = Script(msg["message"], [after.guild, channel, after])
                    try:
                        await script.send(channel)
                    except discord.HTTPException:
                        pass
            except Exception:
                pass

    @commands.group(
        name="command",
        aliases=["cmd"],
        invoke_without_command=True,
        help="Manage command restrictions and permissions",
        extras={"parameters": "n/a", "usage": "command"},
    )
    @commands.has_permissions(administrator=True)
    async def command_group(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @command_group.group(
        name="disable",
        aliases=["off"],
        invoke_without_command=True,
        help="Disable a command in a channel or all channels",
        extras={"parameters": "channel, command", "usage": "command disable [channel] (command)"},
    )
    @commands.has_permissions(administrator=True)
    async def command_disable(
        self,
        ctx: TormentContext,
        channel: discord.TextChannel = None,
        *,
        command: CommandConverter,
    ) -> None:
        if not ctx.guild:
            return

        query = """
            SELECT channel_id
            FROM command_disabled
            WHERE guild_id = $1 AND command = $2
        """
        records = await self.pool.fetch(query, ctx.guild.id, command.qualified_name)
        channel_ids = [r["channel_id"] for r in records]

        if channel and channel.id in channel_ids:
            return await ctx.warn(
                f"The `{command.qualified_name}` command is already disabled in {channel.mention}"
            )
        elif not channel and all(
            ch.id in channel_ids for ch in ctx.guild.text_channels
        ):
            return await ctx.warn(
                f"The `{command.qualified_name}` command is already disabled in all channels"
            )

        channels_to_disable = [channel] if channel else ctx.guild.text_channels

        for ch in channels_to_disable:
            await self.pool.execute(
                """
                INSERT INTO command_disabled (guild_id, channel_id, command)
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id, channel_id, command) DO NOTHING
                """,
                ctx.guild.id,
                ch.id,
                command.qualified_name,
            )

        if channel:
            return await ctx.success(
                f"Disabled the `{command.qualified_name}` command in {channel.mention}"
            )
        return await ctx.success(
            f"Disabled the `{command.qualified_name}` command in {len(channels_to_disable)} channels"
        )

    @command_disable.command(
        name="view",
        aliases=["channels"],
        help="View all channels a command is disabled in",
        extras={"parameters": "command", "usage": "command disable view (command)"},
    )
    @commands.has_permissions(administrator=True)
    async def command_disable_view(
        self, ctx: TormentContext, *, command: CommandConverter
    ) -> None:
        if not ctx.guild:
            return

        query = """
            SELECT channel_id
            FROM command_disabled
            WHERE guild_id = $1 AND command = $2
        """
        records = await self.pool.fetch(query, ctx.guild.id, command.qualified_name)

        channels = []
        for record in records:
            channel = ctx.guild.get_channel(record["channel_id"])
            if channel:
                channels.append(f"{channel.mention} [`{channel.id}`]")

        if not channels:
            return await ctx.warn(
                f"The `{command.qualified_name}` command is not disabled in any channels"
            )

        embed = discord.Embed(
            title=f"Disabled Channels for {command.qualified_name}",
            color=_color("EMBED_INFO_COLOR"),
        )
        paginator = Paginator(ctx, channels, embed)
        await paginator.start()

    @command_disable.command(
        name="list",
        help="View all disabled commands in the server",
        extras={"parameters": "n/a", "usage": "command disable list"},
    )
    @commands.has_permissions(administrator=True)
    async def command_disable_list(self, ctx: TormentContext) -> None:
        if not ctx.guild:
            return

        query = """
            SELECT command, ARRAY_AGG(channel_id) AS channel_ids
            FROM command_disabled
            WHERE guild_id = $1
            GROUP BY guild_id, command
        """
        records = await self.pool.fetch(query, ctx.guild.id)

        commands_list = []
        for record in records:
            channels = []
            for channel_id in record["channel_ids"]:
                channel = ctx.guild.get_channel(channel_id)
                if channel:
                    channels.append(channel)

            if channels:
                channel_mentions = ", ".join(ch.mention for ch in channels[:2])
                if len(channels) > 2:
                    channel_mentions += f" (+{len(channels) - 2})"
                commands_list.append(f"{record['command']} - {channel_mentions}")

        if not commands_list:
            return await ctx.warn("No commands are disabled in this server")

        embed = discord.Embed(
            title="Disabled Commands", color=_color("EMBED_INFO_COLOR")
        )
        paginator = Paginator(ctx, commands_list, embed)
        await paginator.start()

    @command_group.command(
        name="enable",
        aliases=["on"],
        help="Enable a command in a channel or all channels",
        extras={"parameters": "channel, command", "usage": "command enable [channel] (command)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def command_enable(
        self,
        ctx: TormentContext,
        channel: discord.TextChannel = None,
        *,
        command: CommandConverter,
    ) -> None:
        if not ctx.guild:
            return

        channels_to_enable = [channel] if channel else ctx.guild.text_channels
        channel_ids = [ch.id for ch in channels_to_enable]

        query = """
            DELETE FROM command_disabled
            WHERE guild_id = $1 AND command = $2 AND channel_id = ANY($3::BIGINT[])
        """
        result = await self.pool.execute(
            query, ctx.guild.id, command.qualified_name, channel_ids
        )

        deleted_count = int(result.split()[-1]) if result else 0

        if channel and deleted_count == 0:
            return await ctx.warn(
                f"The `{command.qualified_name}` command is already enabled in {channel.mention}"
            )
        elif not channel and deleted_count == 0:
            return await ctx.warn(
                f"The `{command.qualified_name}` command is already enabled in all channels"
            )

        if channel:
            return await ctx.success(
                f"Enabled the `{command.qualified_name}` command in {channel.mention}"
            )
        return await ctx.success(
            f"Enabled the `{command.qualified_name}` command in {deleted_count} channels"
        )

    @command_group.group(
        name="restrict",
        aliases=["require", "allow", "lock"],
        invoke_without_command=True,
        help="Restrict access to a command to a role",
        extras={"parameters": "role, command", "usage": "command restrict (role) (command)"},
    )
    @commands.has_permissions(administrator=True)
    async def command_restrict(
        self, ctx: TormentContext, role: discord.Role, *, command: CommandConverter
    ) -> None:
        if not ctx.guild:
            return

        query = """
            SELECT 1 FROM command_restricted
            WHERE guild_id = $1 AND role_id = $2 AND command = $3
        """
        exists = await self.pool.fetchval(
            query, ctx.guild.id, role.id, command.qualified_name
        )

        if exists:
            await self.pool.execute(
                """
                DELETE FROM command_restricted
                WHERE guild_id = $1 AND role_id = $2 AND command = $3
                """,
                ctx.guild.id,
                role.id,
                command.qualified_name,
            )
            return await ctx.success(
                f"Removed the restriction on the `{command.qualified_name}` command for {role.mention}"
            )

        await self.pool.execute(
            """
            INSERT INTO command_restricted (guild_id, role_id, command)
            VALUES ($1, $2, $3)
            """,
            ctx.guild.id,
            role.id,
            command.qualified_name,
        )
        return await ctx.success(
            f"Now allowing {role.mention} to use the `{command.qualified_name}` command"
        )

    @command_restrict.command(
        name="list",
        help="View all command restrictions in the server",
        extras={"parameters": "n/a", "usage": "command restrict list"},
    )
    @commands.has_permissions(administrator=True)
    async def command_restrict_list(self, ctx: TormentContext) -> None:
        if not ctx.guild:
            return

        query = """
            SELECT command, ARRAY_AGG(role_id) AS role_ids
            FROM command_restricted
            WHERE guild_id = $1
            GROUP BY guild_id, command
        """
        records = await self.pool.fetch(query, ctx.guild.id)

        commands_list = []
        for record in records:
            roles = []
            for role_id in record["role_ids"]:
                role = ctx.guild.get_role(role_id)
                if role:
                    roles.append(role)

            if roles:
                role_mentions = ", ".join(r.mention for r in roles)
                commands_list.append(f"{record['command']} - {role_mentions}")

        if not commands_list:
            return await ctx.warn("No commands are restricted in this server")

        embed = discord.Embed(
            title="Restricted Commands", color=_color("EMBED_INFO_COLOR")
        )
        paginator = Paginator(ctx, commands_list, embed)
        await paginator.start()

    @commands.Cog.listener("on_message")
    async def autoresponder_listener(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        query = """
            SELECT * FROM autoresponder WHERE guild_id = $1
        """
        autoresponders = await self.pool.fetch(query, message.guild.id)

        for ar in autoresponders:
            trigger = ar["trigger_text"]
            response = ar["response"]
            is_embed = ar["is_embed"]
            strict_match = ar["strict"]
            self_destruct = ar["self_destruct"]
            delete_trigger = ar["delete_trigger"]
            reply = ar["reply"]
            ignore_command_check = ar["ignore_command_check"]

            matched = False
            if strict_match:
                if message.content.lower() == trigger.lower():
                    matched = True
            else:
                if trigger.lower() in message.content.lower():
                    matched = True

            if not matched:
                continue

            if not ignore_command_check:
                ctx = await self.bot.get_context(message)
                if ctx.valid:
                    continue

            exclusive_query = """
                SELECT * FROM autoresponder_exclusive
                WHERE guild_id = $1 AND trigger = $2
            """
            exclusives = await self.pool.fetch(exclusive_query, message.guild.id, trigger)

            if exclusives:
                has_access = False
                for exclusive in exclusives:
                    if exclusive["object_type"] == "channel":
                        if message.channel.id == exclusive["object_id"]:
                            has_access = True
                            break
                    elif exclusive["object_type"] == "role":
                        role_ids = [r.id for r in message.author.roles]
                        if exclusive["object_id"] in role_ids:
                            has_access = True
                            break

                if not has_access:
                    continue

            try:
                if delete_trigger:
                    await message.delete()
            except:
                pass

            try:
                if is_embed:
                    script = await Script().convert(None, response)
                    kwargs = script.data
                    if reply:
                        kwargs["reference"] = message
                    sent = await message.channel.send(**kwargs)
                else:
                    if reply:
                        sent = await message.reply(response)
                    else:
                        sent = await message.channel.send(response)

                if self_destruct and self_destruct >= 6:
                    await sent.delete(delay=self_destruct)
            except:
                pass

    @commands.group(
        name="autoresponder",
        aliases=["ar", "autoresponse"],
        invoke_without_command=True,
        help="Manage automatic responses to messages",
        extras={"parameters": "n/a", "usage": "autoresponder"},
    )
    @commands.has_permissions(manage_guild=True)
    async def autoresponder(self, ctx: TormentContext):
        await ctx.send_help_embed(ctx.command)

    @autoresponder.command(
        name="add",
        aliases=["create"],
        help="Add an autoresponder with optional flags",
        extras={"parameters": "trigger, response [--flags]", "usage": "autoresponder add (trigger, response) [--flags]"},
    )
    @commands.has_permissions(manage_guild=True)
    async def autoresponder_add(self, ctx: TormentContext, *, args: str):
        if not ctx.guild:
            return

        if "," not in args:
            return await ctx.warn("You must separate the trigger and response with a comma (,)")

        parts = args.split(",", 1)
        trigger = parts[0].strip()
        rest = parts[1].strip()

        flags = {
            "not_strict": False,
            "self_destruct": None,
            "delete": False,
            "reply": False,
            "ignore_command_check": False
        }

        response = rest
        if "--" in rest:
            response_parts = rest.split("--")
            response = response_parts[0].strip()

            for flag_part in response_parts[1:]:
                flag_part = flag_part.strip()
                if flag_part.startswith("not_strict"):
                    flags["not_strict"] = True
                elif flag_part.startswith("self_destruct"):
                    try:
                        time_val = int(flag_part.split()[1])
                        if 6 <= time_val <= 60:
                            flags["self_destruct"] = time_val
                        else:
                            return await ctx.warn("Self destruct time must be between 6 and 60 seconds")
                    except:
                        return await ctx.warn("Invalid self_destruct value")
                elif flag_part.startswith("delete"):
                    flags["delete"] = True
                elif flag_part.startswith("reply"):
                    flags["reply"] = True
                elif flag_part.startswith("ignore_command_check"):
                    flags["ignore_command_check"] = True

        if not trigger or not response:
            return await ctx.warn("Both trigger and response are required")

        is_embed = False
        if response.startswith("{embed}"):
            is_embed = True
            try:
                script = await Script().convert(ctx, response)
            except Exception as e:
                return await ctx.warn(f"Invalid embed script: {str(e)}")

        existing = await self.pool.fetchrow(
            "SELECT * FROM autoresponder WHERE guild_id = $1 AND trigger_text = $2",
            ctx.guild.id, trigger
        )

        if existing:
            await self.pool.execute(
                """
                UPDATE autoresponder
                SET response = $1, is_embed = $2, strict = $3, self_destruct = $4,
                    delete_trigger = $5, reply = $6, ignore_command_check = $7
                WHERE guild_id = $8 AND trigger_text = $9
                """,
                response, is_embed, not flags["not_strict"], flags["self_destruct"],
                flags["delete"], flags["reply"], flags["ignore_command_check"],
                ctx.guild.id, trigger
            )
            action = "Updated"
        else:
            await self.pool.execute(
                """
                INSERT INTO autoresponder
                (guild_id, trigger_text, response, is_embed, strict, self_destruct, delete_trigger, reply, ignore_command_check)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                ctx.guild.id, trigger, response, is_embed, not flags["not_strict"],
                flags["self_destruct"], flags["delete"], flags["reply"], flags["ignore_command_check"]
            )
            action = "Created"

        response_type = "embed response" if is_embed else "text response"
        match_type = "strict match" if not flags["not_strict"] else "partial match"
        
        info_parts = [f"with a {response_type} ({match_type})"]
        if flags["reply"]:
            info_parts.append("(reply)")
        if flags["delete"]:
            info_parts.append("(delete trigger)")
        if flags["self_destruct"]:
            info_parts.append(f"(self-destruct after {flags['self_destruct']}s)")
        if flags["ignore_command_check"]:
            info_parts.append("(ignore commands)")

        await ctx.success(f"{action} auto response **{trigger}** {' '.join(info_parts)}")

    @autoresponder.command(
        name="remove",
        aliases=["delete", "del", "rm"],
        help="Remove an autoresponder",
        extras={"parameters": "trigger", "usage": "autoresponder remove (trigger)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def autoresponder_remove(self, ctx: TormentContext, *, trigger: str):
        if not ctx.guild:
            return

        result = await self.pool.execute(
            "DELETE FROM autoresponder WHERE guild_id = $1 AND trigger_text = $2",
            ctx.guild.id, trigger
        )

        if result == "DELETE 0":
            return await ctx.warn(f"No autoresponder found with trigger **{trigger}**")

        await self.pool.execute(
            "DELETE FROM autoresponder_exclusive WHERE guild_id = $1 AND trigger = $2",
            ctx.guild.id, trigger
        )

        await ctx.success(f"Removed autoresponder **{trigger}**")

    @autoresponder.command(
        name="exclusive",
        aliases=["restrict"],
        help="Make an autoresponder exclusive to a role or channel",
        extras={"parameters": "role/channel, trigger", "usage": "autoresponder exclusive (role/channel) (trigger)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def autoresponder_exclusive(
        self, ctx: TormentContext, target: Union[discord.Role, discord.TextChannel], *, trigger: str
    ):
        if not ctx.guild:
            return

        ar = await self.pool.fetchrow(
            "SELECT * FROM autoresponder WHERE guild_id = $1 AND trigger_text = $2",
            ctx.guild.id, trigger
        )

        if not ar:
            return await ctx.warn(f"No autoresponder found with trigger **{trigger}**")

        object_type = "role" if isinstance(target, discord.Role) else "channel"

        existing = await self.pool.fetchrow(
            """
            SELECT * FROM autoresponder_exclusive
            WHERE guild_id = $1 AND trigger = $2 AND object_id = $3 AND object_type = $4
            """,
            ctx.guild.id, trigger, target.id, object_type
        )

        if existing:
            await self.pool.execute(
                """
                DELETE FROM autoresponder_exclusive
                WHERE guild_id = $1 AND trigger = $2 AND object_id = $3 AND object_type = $4
                """,
                ctx.guild.id, trigger, target.id, object_type
            )
            return await ctx.success(
                f"Removed {object_type} {target.mention} from autoresponder **{trigger}** exclusives"
            )

        await self.pool.execute(
            """
            INSERT INTO autoresponder_exclusive (guild_id, trigger, object_id, object_type)
            VALUES ($1, $2, $3, $4)
            """,
            ctx.guild.id, trigger, target.id, object_type
        )

        await ctx.success(
            f"Added {object_type} {target.mention} to autoresponder **{trigger}** exclusives"
        )

    @autoresponder.command(
        name="list",
        aliases=["view", "show"],
        help="View all autoresponders in the server",
        extras={"parameters": "n/a", "usage": "autoresponder list"},
    )
    @commands.has_permissions(manage_guild=True)
    async def autoresponder_list(self, ctx: TormentContext):
        if not ctx.guild:
            return

        query = """
            SELECT * FROM autoresponder WHERE guild_id = $1 ORDER BY trigger_text
        """
        autoresponders = await self.pool.fetch(query, ctx.guild.id)

        if not autoresponders:
            return await ctx.warn("No autoresponders configured in this server")

        entries = []
        for ar in autoresponders:
            trigger = ar["trigger_text"]
            response_type = "embed" if ar["is_embed"] else "text"
            match_type = "strict" if ar["strict"] else "partial"
            
            flags = []
            if ar["reply"]:
                flags.append("reply")
            if ar["delete_trigger"]:
                flags.append("delete")
            if ar["self_destruct"]:
                flags.append(f"destruct:{ar['self_destruct']}s")
            if ar["ignore_command_check"]:
                flags.append("ignore_cmds")

            flag_str = f" [{', '.join(flags)}]" if flags else ""
            entries.append(f"**{trigger}** - {response_type} ({match_type}){flag_str}")

        embed = discord.Embed(
            title="Autoresponders",
            color=_color("EMBED_INFO_COLOR")
        )
        paginator = Paginator(ctx, entries, embed)
        await paginator.start()

    @commands.Cog.listener("on_message")
    async def sticky_listener(self, message: discord.Message):
        if not message.guild or not isinstance(message.channel, discord.TextChannel):
            return

        query = "SELECT * FROM sticky WHERE guild_id = $1 AND channel_id = $2"
        record = await self.pool.fetchrow(query, message.guild.id, message.channel.id)
        
        if not record:
            return
        elif record["message_id"] == message.id:
            return

        last_message = message.channel.get_partial_message(record["message_id"])
        
        try:
            await last_message.delete()
        except:
            pass

        script = await Script().convert(None, record["template"])
        
        try:
            new_message = await message.channel.send(**script.data)
        except:
            query = "DELETE FROM sticky WHERE guild_id = $1 AND channel_id = $2"
            await self.pool.execute(query, message.guild.id, message.channel.id)
            return

        query = "UPDATE sticky SET message_id = $3 WHERE guild_id = $1 AND channel_id = $2"
        await self.pool.execute(query, message.guild.id, message.channel.id, new_message.id)

    @commands.group(
        name="sticky",
        aliases=["stickymessage", "stickymsg", "sm"],
        invoke_without_command=True,
        help="Stick a message to the bottom of the channel",
        extras={"parameters": "n/a", "usage": "sticky"},
    )
    @commands.has_permissions(manage_messages=True)
    async def sticky(self, ctx: TormentContext):
        await ctx.send_help_embed(ctx.command)

    @sticky.command(
        name="add",
        aliases=["create"],
        help="Add a sticky message to a channel",
        extras={"parameters": "channel, script", "usage": "sticky add (channel) (script)"},
    )
    @commands.has_permissions(manage_messages=True)
    async def sticky_add(self, ctx: TormentContext, channel: discord.TextChannel, *, script_text: str):
        if not ctx.guild:
            return

        script = await Script().convert(ctx, script_text)
        message = await channel.send(**script.data)

        await self.pool.execute(
            """
            INSERT INTO sticky (guild_id, channel_id, message_id, template)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, channel_id)
            DO UPDATE SET
                message_id = EXCLUDED.message_id,
                template = EXCLUDED.template
            """,
            ctx.guild.id, channel.id, message.id, script_text
        )

        return await ctx.success(f"Added sticky message to {channel.mention}")

    @sticky.command(
        name="existing",
        aliases=["from"],
        help="Add a sticky message from an existing message",
        extras={"parameters": "channel, message", "usage": "sticky existing (channel) (message)"},
    )
    @commands.has_permissions(manage_messages=True)
    async def sticky_existing(self, ctx: TormentContext, channel: discord.TextChannel, message: discord.Message):
        if not ctx.guild:
            return

        if not message.content and not message.embeds:
            return await ctx.warn("That message doesn't have any content")

        script_text = message.content or ""
        if message.embeds:
            embed = message.embeds[0]
            script_text = f"{{embed}}$v{{title: {embed.title or ''}}}$v{{description: {embed.description or ''}}}"

        return await self.sticky_add(ctx, channel, script_text=script_text)

    @sticky.command(
        name="remove",
        aliases=["delete", "del", "rm"],
        help="Remove an existing sticky message",
        extras={"parameters": "channel", "usage": "sticky remove (channel)"},
    )
    @commands.has_permissions(manage_messages=True)
    async def sticky_remove(self, ctx: TormentContext, channel: discord.TextChannel):
        if not ctx.guild:
            return

        query = """
            DELETE FROM sticky
            WHERE guild_id = $1 AND channel_id = $2
            RETURNING message_id
        """
        message_id = await self.pool.fetchval(query, ctx.guild.id, channel.id)

        if not message_id:
            return await ctx.warn(f"No sticky message was found for {channel.mention}")

        message = channel.get_partial_message(message_id)
        try:
            await message.delete()
        except:
            pass

        return await ctx.success(f"Removed the sticky message from {channel.mention}")

    @sticky.command(
        name="view",
        aliases=["script", "template"],
        help="View the sticky message for a channel",
        extras={"parameters": "channel", "usage": "sticky view (channel)"},
    )
    @commands.has_permissions(manage_messages=True)
    async def sticky_view(self, ctx: TormentContext, channel: discord.TextChannel):
        if not ctx.guild:
            return

        query = "SELECT template FROM sticky WHERE channel_id = $1"
        template = await self.pool.fetchval(query, channel.id)

        if not template:
            return await ctx.warn(f"No sticky message was found for {channel.mention}")

        script = await Script().convert(ctx, template)
        await ctx.reply(f"```yaml\n{template}\n```")
        return await ctx.channel.send(**script.data)

    @sticky.command(
        name="list",
        help="View all channels with a sticky message",
        extras={"parameters": "n/a", "usage": "sticky list"},
    )
    @commands.has_permissions(manage_messages=True)
    async def sticky_list(self, ctx: TormentContext):
        if not ctx.guild:
            return

        query = "SELECT * FROM sticky WHERE guild_id = $1"
        records = await self.pool.fetch(query, ctx.guild.id)

        channels = []
        for record in records:
            channel = ctx.guild.get_channel(record["channel_id"])
            if channel and isinstance(channel, discord.TextChannel):
                message = channel.get_partial_message(record["message_id"])
                channels.append(f"{channel.mention} [`MESSAGE`]({message.jump_url})")

        if not channels:
            return await ctx.warn("No channels are receiving sticky messages")

        embed = discord.Embed(
            title="Sticky Messages",
            color=_color("EMBED_INFO_COLOR")
        )
        paginator = Paginator(ctx, channels, embed)
        return await paginator.start()

    @commands.group(
        name="autorole",
        aliases=["autoroles"],
        invoke_without_command=True,
        help="Manage roles automatically assigned to new members",
        extras={"parameters": "n/a", "usage": "autorole"},
    )
    @commands.has_permissions(manage_guild=True)
    async def autorole(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @autorole.command(
        name="add",
        aliases=["set"],
        help="Add a role to be assigned to new members",
        extras={"parameters": "role", "usage": "autorole add (role)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def autorole_add(self, ctx: TormentContext, *, role: discord.Role) -> None:
        if role >= ctx.guild.me.top_role:
            return await ctx.warn(f"{role.mention} is above my highest role and cannot be assigned.")
        if role.managed:
            return await ctx.warn(f"{role.mention} is a managed role and cannot be assigned.")

        existing = await self.pool.fetchval(
            "SELECT 1 FROM autoroles WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id, role.id,
        )
        if existing:
            return await ctx.warn(f"{role.mention} is already an autorole.")

        count = await self.pool.fetchval(
            "SELECT COUNT(*) FROM autoroles WHERE guild_id = $1", ctx.guild.id
        )
        if count >= 10:
            return await ctx.warn("You can only have up to **10** autoroles.")

        await self.pool.execute(
            "INSERT INTO autoroles (guild_id, role_id) VALUES ($1, $2)",
            ctx.guild.id, role.id,
        )
        await ctx.success(f"added {role.mention} as an autorole.")

    @autorole.command(
        name="remove",
        aliases=["delete", "del", "rm"],
        help="Remove a role from the autorole list",
        extras={"parameters": "role", "usage": "autorole remove (role)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def autorole_remove(self, ctx: TormentContext, *, role: discord.Role) -> None:
        result = await self.pool.execute(
            "DELETE FROM autoroles WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id, role.id,
        )
        if result == "DELETE 0":
            return await ctx.warn(f"{role.mention} is not an autorole.")
        await ctx.success(f"removed {role.mention} from autoroles.")

    @autorole.command(
        name="list",
        aliases=["show", "view"],
        help="View all autoroles configured for this server",
        extras={"parameters": "n/a", "usage": "autorole list"},
    )
    @commands.has_permissions(manage_guild=True)
    async def autorole_list(self, ctx: TormentContext) -> None:
        rows = await self.pool.fetch(
            "SELECT role_id FROM autoroles WHERE guild_id = $1", ctx.guild.id
        )
        if not rows:
            return await ctx.warn("No autoroles are configured for this server.")

        lines = []
        for i, row in enumerate(rows, 1):
            role = ctx.guild.get_role(row["role_id"])
            role_text = role.mention if role else f"<deleted role {row['role_id']}>"
            lines.append(f"`{i:02}` {role_text}")

        embed = discord.Embed(
            title="Autoroles",
            description="\n".join(lines),
            color=_color("EMBED_INFO_COLOR"),
        )
        if ctx.guild.icon:
            embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url)
        else:
            embed.set_author(name=ctx.guild.name)
        embed.set_footer(text=f"{len(rows)} role{'s' if len(rows) != 1 else ''}")
        await ctx.send(embed=embed)

    @autorole.command(
        name="reset",
        aliases=["clear"],
        help="Remove all autoroles from this server",
        extras={"parameters": "n/a", "usage": "autorole reset"},
    )
    @commands.has_permissions(manage_guild=True)
    async def autorole_reset(self, ctx: TormentContext) -> None:
        count = await self.pool.fetchval(
            "SELECT COUNT(*) FROM autoroles WHERE guild_id = $1", ctx.guild.id
        )
        if not count:
            return await ctx.warn("No autoroles are configured for this server.")
        if not await ctx.confirm(f"Are you sure you want to remove all **{count}** autorole{'s' if count != 1 else ''}?"):
            return
        await self.pool.execute("DELETE FROM autoroles WHERE guild_id = $1", ctx.guild.id)
        await ctx.success(f"removed all **{count}** autorole{'s' if count != 1 else ''}.")

    @commands.Cog.listener("on_member_join")
    async def pingonjoin_listener(self, member: discord.Member) -> None:
        rows = await self.pool.fetch(
            "SELECT channel_id, message FROM pingonjoin WHERE guild_id = $1", member.guild.id
        )
        for row in rows:
            channel = member.guild.get_channel(row["channel_id"])
            if not channel:
                continue
            content = row["message"] or member.mention
            content = content.replace("{mention}", member.mention).replace("{user}", str(member)).replace("{server}", member.guild.name)
            try:
                msg = await channel.send(content)
                await msg.delete(delay=2)
            except discord.HTTPException:
                pass

    @commands.group(
        name="pingonjoin",
        aliases=["poj"],
        invoke_without_command=True,
        help="Manage ping-on-join channels",
        extras={"parameters": "n/a", "usage": "pingonjoin"},
    )
    @commands.has_permissions(manage_guild=True)
    async def pingonjoin(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @pingonjoin.command(
        name="add",
        help="Add a channel to ping new members in",
        extras={"parameters": "channel", "usage": "pingonjoin add (channel)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def pingonjoin_add(self, ctx: TormentContext, channel: discord.TextChannel) -> None:
        existing = await self.pool.fetchval(
            "SELECT 1 FROM pingonjoin WHERE guild_id = $1 AND channel_id = $2",
            ctx.guild.id, channel.id,
        )
        if existing:
            return await ctx.warn(f"{channel.mention} is already a ping-on-join channel.")
        await self.pool.execute(
            "INSERT INTO pingonjoin (guild_id, channel_id) VALUES ($1, $2)",
            ctx.guild.id, channel.id,
        )
        await ctx.success(f"New members will now be pinged in {channel.mention}.")

    @pingonjoin.command(
        name="remove",
        aliases=["rm", "delete"],
        help="Remove a ping-on-join channel",
        extras={"parameters": "channel", "usage": "pingonjoin remove (channel)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def pingonjoin_remove(self, ctx: TormentContext, channel: discord.TextChannel) -> None:
        deleted = await self.pool.execute(
            "DELETE FROM pingonjoin WHERE guild_id = $1 AND channel_id = $2",
            ctx.guild.id, channel.id,
        )
        if deleted == "DELETE 0":
            return await ctx.warn(f"{channel.mention} is not a ping-on-join channel.")
        await ctx.success(f"Removed {channel.mention} from ping-on-join channels.")

    @pingonjoin.command(
        name="list",
        help="List all ping-on-join channels",
        extras={"parameters": "n/a", "usage": "pingonjoin list"},
    )
    @commands.has_permissions(manage_guild=True)
    async def pingonjoin_list(self, ctx: TormentContext) -> None:
        rows = await self.pool.fetch(
            "SELECT channel_id FROM pingonjoin WHERE guild_id = $1", ctx.guild.id
        )
        if not rows:
            return await ctx.warn("No ping-on-join channels configured.")
        lines = [
            ctx.guild.get_channel(r["channel_id"]).mention
            if ctx.guild.get_channel(r["channel_id"])
            else f"`{r['channel_id']}`"
            for r in rows
        ]
        embed = discord.Embed(title="Ping on Join Channels", color=_color("EMBED_INFO_COLOR"))
        paginator = Paginator(ctx, lines, embed)
        await paginator.start()

    @pingonjoin.command(
        name="reset",
        help="Remove all ping-on-join channels",
        extras={"parameters": "n/a", "usage": "pingonjoin reset"},
    )
    @commands.has_permissions(manage_guild=True)
    async def pingonjoin_reset(self, ctx: TormentContext) -> None:
        count = await self.pool.fetchval(
            "SELECT COUNT(*) FROM pingonjoin WHERE guild_id = $1", ctx.guild.id
        )
        if not count:
            return await ctx.warn("No ping-on-join channels to reset.")
        if not await ctx.confirm(f"Remove all **{count}** ping-on-join channel{'s' if count != 1 else ''}?"):
            return
        await self.pool.execute("DELETE FROM pingonjoin WHERE guild_id = $1", ctx.guild.id)
        await ctx.success(f"Removed all **{count}** ping-on-join channel{'s' if count != 1 else ''}.")

    @pingonjoin.group(
        name="message",
        aliases=["msg"],
        invoke_without_command=True,
        help="Set a custom message for a ping-on-join channel (use {mention}, {user}, {server})",
        extras={"parameters": "channel, message", "usage": "pingonjoin message (channel) (message)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def pingonjoin_message(self, ctx: TormentContext, channel: discord.TextChannel, *, message: str) -> None:
        existing = await self.pool.fetchval(
            "SELECT 1 FROM pingonjoin WHERE guild_id = $1 AND channel_id = $2",
            ctx.guild.id, channel.id,
        )
        if not existing:
            return await ctx.warn(f"{channel.mention} is not a ping-on-join channel. Add it first.")
        await self.pool.execute(
            "UPDATE pingonjoin SET message = $1 WHERE guild_id = $2 AND channel_id = $3",
            message, ctx.guild.id, channel.id,
        )
        await ctx.success(f"Updated the ping-on-join message for {channel.mention}.")

    @pingonjoin_message.command(
        name="remove",
        aliases=["reset", "clear"],
        help="Remove the custom message for a ping-on-join channel",
        extras={"parameters": "channel", "usage": "pingonjoin message remove (channel)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def pingonjoin_message_remove(self, ctx: TormentContext, channel: discord.TextChannel) -> None:
        existing = await self.pool.fetchval(
            "SELECT message FROM pingonjoin WHERE guild_id = $1 AND channel_id = $2",
            ctx.guild.id, channel.id,
        )
        if existing is None:
            return await ctx.warn(f"{channel.mention} is not a ping-on-join channel.")
        await self.pool.execute(
            "UPDATE pingonjoin SET message = NULL WHERE guild_id = $1 AND channel_id = $2",
            ctx.guild.id, channel.id,
        )
        await ctx.success(f"Cleared the custom message for {channel.mention}. It will now use the default ping.")

    @commands.Cog.listener("on_message")
    async def alias_listener(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild or not message.content:
            return
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return
        prefix = ctx.prefix
        if not prefix:
            return
        potential = message.content[len(prefix):].split()[0].lower() if message.content.startswith(prefix) else None
        if not potential:
            return
        row = await self.pool.fetchrow(
            "SELECT command FROM aliases WHERE guild_id = $1 AND alias = $2",
            message.guild.id, potential,
        )
        if not row:
            return
        rest = message.content[len(prefix) + len(potential):].strip()
        invoke = row["command"]
        if rest:
            invoke = f"{invoke} {rest}"
        message._edited_timestamp = None
        new_content = f"{prefix}{invoke}"
        message.content = new_content
        await self.bot.process_commands(message)

    @commands.group(
        name="alias",
        aliases=["shortcut"],
        invoke_without_command=True,
        help="Manage command shortcuts",
        extras={"parameters": "n/a", "usage": "alias"},
    )
    @commands.has_permissions(manage_guild=True)
    async def alias_group(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @alias_group.command(
        name="add",
        aliases=["create"],
        help="Add an alias for a command",
        extras={"parameters": "name, invoke", "usage": "alias add (name) (command)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def alias_add(self, ctx: TormentContext, name: str, *, invoke: str) -> None:
        if self.bot.get_command(name):
            return await ctx.warn(f"A command named **{name}** already exists.")
        if " " in name or not name.isprintable():
            return await ctx.warn("Alias name must be a single printable word.")
        command = self.bot.get_command(invoke.split()[0])
        if not command:
            return await ctx.warn(f"Command `{invoke.split()[0]}` doesn't exist.")
        existing = await self.pool.fetchval(
            "SELECT 1 FROM aliases WHERE guild_id = $1 AND alias = $2",
            ctx.guild.id, name.lower(),
        )
        if existing:
            return await ctx.warn(f"An alias named **{name}** already exists.")
        await self.pool.execute(
            "INSERT INTO aliases (guild_id, alias, command) VALUES ($1, $2, $3)",
            ctx.guild.id, name.lower(), invoke,
        )
        await ctx.success(f"Added alias **{name}** → `{invoke}`.")

    @alias_group.command(
        name="remove",
        aliases=["delete", "del", "rm"],
        help="Remove an alias",
        extras={"parameters": "name", "usage": "alias remove (name)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def alias_remove(self, ctx: TormentContext, name: str) -> None:
        result = await self.pool.execute(
            "DELETE FROM aliases WHERE guild_id = $1 AND alias = $2",
            ctx.guild.id, name.lower(),
        )
        if result == "DELETE 0":
            return await ctx.warn(f"No alias named **{name}** exists.")
        await ctx.success(f"Removed alias **{name}**.")

    @alias_group.command(
        name="view",
        aliases=["show"],
        help="View what an alias invokes",
        extras={"parameters": "name", "usage": "alias view (name)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def alias_view(self, ctx: TormentContext, name: str) -> None:
        row = await self.pool.fetchrow(
            "SELECT command FROM aliases WHERE guild_id = $1 AND alias = $2",
            ctx.guild.id, name.lower(),
        )
        if not row:
            return await ctx.warn(f"No alias named **{name}** exists.")
        await ctx.success(f"**{name}** invokes `{row['command']}`.")

    @alias_group.command(
        name="clear",
        aliases=["reset"],
        help="Remove all aliases in this server",
        extras={"parameters": "n/a", "usage": "alias clear"},
    )
    @commands.has_permissions(manage_guild=True)
    async def alias_clear(self, ctx: TormentContext) -> None:
        count = await self.pool.fetchval(
            "SELECT COUNT(*) FROM aliases WHERE guild_id = $1", ctx.guild.id
        )
        if not count:
            return await ctx.warn("No aliases exist for this server.")
        if not await ctx.confirm(f"Remove all **{count}** alias{'es' if count != 1 else ''}?"):
            return
        await self.pool.execute("DELETE FROM aliases WHERE guild_id = $1", ctx.guild.id)
        await ctx.success(f"Removed all **{count}** alias{'es' if count != 1 else ''}.")
    @alias_group.command(
        name="list",
        aliases=["ls"],
        help="View all command shortcuts",
        extras={"parameters": "n/a", "usage": "alias list"},
    )
    @commands.has_permissions(manage_guild=True)
    async def alias_list(self, ctx: TormentContext) -> None:
        rows = await self.pool.fetch(
            "SELECT alias, command FROM aliases WHERE guild_id = $1 ORDER BY alias",
            ctx.guild.id,
        )
        if not rows:
            return await ctx.warn("No aliases exist for this server.")
        lines = [f"**{r['alias']}** → `{r['command']}`" for r in rows]
        embed = discord.Embed(title="Command Shortcuts", color=_color("EMBED_INFO_COLOR"))
        paginator = Paginator(ctx, lines, embed)
        await paginator.start()

    @commands.Cog.listener("on_raw_reaction_add")
    async def reactionrole_add(self, payload: discord.RawReactionActionEvent) -> None:
        if not payload.guild_id or payload.member and payload.member.bot:
            return
        emoji = str(payload.emoji)
        row = await self.pool.fetchrow(
            "SELECT role_id FROM reaction_roles WHERE guild_id = $1 AND message_id = $2 AND emoji = $3",
            payload.guild_id, payload.message_id, emoji,
        )
        if not row:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = payload.member or guild.get_member(payload.user_id)
        if not member or member.bot:
            return
        role = guild.get_role(row["role_id"])
        if role:
            try:
                await member.add_roles(role, reason="Reaction role")
            except discord.HTTPException:
                pass

    @commands.Cog.listener("on_raw_reaction_remove")
    async def reactionrole_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if not payload.guild_id:
            return
        emoji = str(payload.emoji)
        row = await self.pool.fetchrow(
            "SELECT role_id FROM reaction_roles WHERE guild_id = $1 AND message_id = $2 AND emoji = $3",
            payload.guild_id, payload.message_id, emoji,
        )
        if not row:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return
        role = guild.get_role(row["role_id"])
        if role:
            try:
                await member.remove_roles(role, reason="Reaction role removed")
            except discord.HTTPException:
                pass

    @commands.group(
        name="reactionrole",
        aliases=["rr"],
        invoke_without_command=True,
        help="Manage reaction roles",
        extras={"parameters": "n/a", "usage": "reactionrole"},
    )
    @commands.has_permissions(manage_roles=True)
    async def reactionrole(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @reactionrole.command(
        name="add",
        help="Add a reaction role to a message",
        extras={"parameters": "message link, emoji, role", "usage": "reactionrole add (message link) (emoji) (role)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def reactionrole_add(self, ctx: TormentContext, link: str, emoji: str, *, role: discord.Role) -> None:
        parts = link.strip("/").split("/")
        try:
            channel_id = int(parts[-2])
            message_id = int(parts[-1])
        except (ValueError, IndexError):
            return await ctx.warn("Invalid message link.")

        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            return await ctx.warn("Channel not found.")

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            return await ctx.warn("Message not found.")

        if role >= ctx.guild.me.top_role:
            return await ctx.warn(f"{role.mention} is above my highest role.")
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.warn(f"You can't assign {role.mention} as it's above your highest role.")

        existing = await self.pool.fetchval(
            "SELECT COUNT(*) FROM reaction_roles WHERE guild_id = $1 AND message_id = $2",
            ctx.guild.id, message_id,
        )
        if existing >= 20:
            return await ctx.warn("A message can have at most **20** reaction roles.")

        await self.pool.execute(
            "INSERT INTO reaction_roles (guild_id, channel_id, message_id, emoji, role_id) VALUES ($1, $2, $3, $4, $5) ON CONFLICT DO NOTHING",
            ctx.guild.id, channel_id, message_id, emoji, role.id,
        )

        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            return await ctx.warn("Invalid emoji or I can't react with that.")

        await ctx.success(f"Added {emoji} → {role.mention} on [that message]({link}).")

    @reactionrole.command(
        name="remove",
        aliases=["rm"],
        help="Remove a reaction role from a message",
        extras={"parameters": "message link, emoji", "usage": "reactionrole remove (message link) (emoji)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def reactionrole_remove(self, ctx: TormentContext, link: str, emoji: str) -> None:
        parts = link.strip("/").split("/")
        try:
            message_id = int(parts[-1])
        except (ValueError, IndexError):
            return await ctx.warn("Invalid message link.")

        deleted = await self.pool.execute(
            "DELETE FROM reaction_roles WHERE guild_id = $1 AND message_id = $2 AND emoji = $3",
            ctx.guild.id, message_id, emoji,
        )
        if deleted == "DELETE 0":
            return await ctx.warn("No reaction role found for that emoji on that message.")

        await ctx.success(f"Removed the reaction role for {emoji}.")

    @reactionrole.command(
        name="clear",
        help="Remove all reaction roles from a message",
        extras={"parameters": "message link", "usage": "reactionrole clear (message link)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def reactionrole_clear(self, ctx: TormentContext, link: str) -> None:
        parts = link.strip("/").split("/")
        try:
            message_id = int(parts[-1])
        except (ValueError, IndexError):
            return await ctx.warn("Invalid message link.")

        count = await self.pool.fetchval(
            "SELECT COUNT(*) FROM reaction_roles WHERE guild_id = $1 AND message_id = $2",
            ctx.guild.id, message_id,
        )
        if not count:
            return await ctx.warn("No reaction roles found on that message.")

        await self.pool.execute(
            "DELETE FROM reaction_roles WHERE guild_id = $1 AND message_id = $2",
            ctx.guild.id, message_id,
        )
        await ctx.success(f"Cleared **{count}** reaction role{'s' if count != 1 else ''} from that message.")

    @reactionrole.command(
        name="list",
        help="List all reaction roles in this server",
        extras={"parameters": "n/a", "usage": "reactionrole list"},
    )
    @commands.has_permissions(manage_roles=True)
    async def reactionrole_list(self, ctx: TormentContext) -> None:
        rows = await self.pool.fetch(
            "SELECT * FROM reaction_roles WHERE guild_id = $1 ORDER BY message_id",
            ctx.guild.id,
        )
        if not rows:
            return await ctx.warn("No reaction roles configured in this server.")

        lines = []
        for row in rows:
            role = ctx.guild.get_role(row["role_id"])
            channel = ctx.guild.get_channel(row["channel_id"])
            role_fmt = role.mention if role else f"`{row['role_id']}`"
            ch_fmt = channel.mention if channel else f"`{row['channel_id']}`"
            lines.append(f"{row['emoji']} → {role_fmt} in {ch_fmt} [`{row['message_id']}`]")

        embed = discord.Embed(title="Reaction Roles", color=_color("EMBED_INFO_COLOR"))
        paginator = Paginator(ctx, lines, embed)
        await paginator.start()


    NUMBER_PATTERN = r"\d{1,3}(,\d{3})*"
    ALLOWED_STAT_CHANNEL = Union[
        discord.TextChannel,
        discord.CategoryChannel,
        discord.VoiceChannel,
        discord.StageChannel,
        discord.ForumChannel,
    ]

    @tasks.loop(minutes=10)
    async def update_statistics(self) -> None:
        records = await self.pool.fetch(
            """
            SELECT channel_id, option FROM counter
            WHERE last_update < NOW() - INTERVAL '10 minutes'
            AND (rate_limited_until IS NULL OR rate_limited_until < NOW())
            """
        )
        scheduled_deletion: list[int] = []
        for record in records:
            channel = self.bot.get_channel(record["channel_id"])
            if not channel:
                scheduled_deletion.append(record["channel_id"])
                continue
            option = record["option"]
            if option == "members":
                value = len(channel.guild.members)
            elif option == "boosts":
                value = channel.guild.premium_subscription_count
            else:
                continue
            if not re.search(self.NUMBER_PATTERN, channel.name):
                name = f"{channel.name} {value:,}"
            else:
                name = re.sub(self.NUMBER_PATTERN, f"{value:,}", channel.name)
            if channel.name == name:
                continue
            try:
                await channel.edit(name=name, reason=f"Updated {option} counter")
            except RateLimited as exc:
                await self.pool.execute(
                    "UPDATE counter SET rate_limited_until = $2 WHERE channel_id = $1",
                    record["channel_id"],
                    utcnow() + timedelta(seconds=exc.retry_after),
                )
            except discord.HTTPException:
                scheduled_deletion.append(record["channel_id"])
            else:
                await self.pool.execute(
                    "UPDATE counter SET last_update = NOW() WHERE channel_id = $1",
                    record["channel_id"],
                )
        if scheduled_deletion:
            await self.pool.execute(
                "DELETE FROM counter WHERE channel_id = ANY($1::BIGINT[])",
                scheduled_deletion,
            )

    @update_statistics.before_loop
    async def _before_update_statistics(self) -> None:
        await self.bot.wait_until_ready()

    @commands.group(
        name="statistics",
        aliases=["counter", "stats"],
        invoke_without_command=True,
        help="Set channels to display server statistics",
        extras={"parameters": "n/a", "usage": "statistics"},
    )
    @commands.has_permissions(manage_channels=True)
    async def statistics(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @statistics.command(
        name="set",
        aliases=["add", "create"],
        help="Set a channel to display server statistics",
        extras={"parameters": "members/boosts, channel", "usage": "statistics set (members/boosts) (channel)"},
    )
    @commands.has_permissions(manage_channels=True)
    async def statistics_set(
        self,
        ctx: TormentContext,
        option: Literal["members", "boosts"],
        *,
        channel: Union[
            discord.TextChannel,
            discord.CategoryChannel,
            discord.VoiceChannel,
            discord.StageChannel,
            discord.ForumChannel,
        ],
    ) -> None:
        existing_id = await self.pool.fetchval(
            "SELECT channel_id FROM counter WHERE guild_id = $1 AND option = $2",
            ctx.guild.id, option,
        )
        if existing_id:
            existing_ch = ctx.guild.get_channel(existing_id)
            if existing_ch:
                return await ctx.warn(f"The counter for `{option}` is already set to {existing_ch.mention}")
            await self.pool.execute(
                "DELETE FROM counter WHERE guild_id = $1 AND option = $2",
                ctx.guild.id, option,
            )
        value = len(ctx.guild.members) if option == "members" else ctx.guild.premium_subscription_count
        try:
            await channel.edit(
                name=f"{option.title()}: {value:,}",
                reason=f"Set as {option} counter by {ctx.author} ({ctx.author.id})",
            )
        except RateLimited as exc:
            return await ctx.warn(
                f"Rate limited while setting `{option}` counter on {channel.mention}. "
                f"Please wait **{format_timespan(int(exc.retry_after))}** before trying again"
            )
        await self.pool.execute(
            """
            INSERT INTO counter (guild_id, channel_id, option)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, channel_id) DO UPDATE SET option = EXCLUDED.option
            """,
            ctx.guild.id, channel.id, option,
        )
        return await ctx.success(f"Successfully set `{option}` counter to {channel.mention}")

    @statistics.command(
        name="remove",
        aliases=["delete", "del", "rm"],
        help="Remove a statistics counter channel",
        extras={"parameters": "channel", "usage": "statistics remove (channel)"},
    )
    @commands.has_permissions(manage_channels=True)
    async def statistics_remove(
        self,
        ctx: TormentContext,
        *,
        channel: Union[
            discord.TextChannel,
            discord.CategoryChannel,
            discord.VoiceChannel,
            discord.StageChannel,
            discord.ForumChannel,
        ],
    ) -> None:
        result = await self.pool.execute(
            "DELETE FROM counter WHERE guild_id = $1 AND channel_id = $2",
            ctx.guild.id, channel.id,
        )
        if result == "DELETE 0":
            return await ctx.warn(f"{channel.mention} is not displaying any statistics")
        return await ctx.success(f"Successfully removed statistics from {channel.mention}")

    @statistics.command(
        name="clear",
        aliases=["reset"],
        help="Remove all statistics counter channels",
        extras={"parameters": "n/a", "usage": "statistics clear"},
    )
    @commands.has_permissions(manage_channels=True)
    async def statistics_clear(self, ctx: TormentContext) -> None:
        result = await self.pool.execute(
            "DELETE FROM counter WHERE guild_id = $1", ctx.guild.id
        )
        if result == "DELETE 0":
            return await ctx.warn("No counter channels exist for this server")
        return await ctx.success("Successfully removed all counter channels")

    @statistics.command(
        name="list",
        aliases=["ls"],
        help="View all statistics counter channels",
        extras={"parameters": "n/a", "usage": "statistics list"},
    )
    @commands.has_permissions(manage_channels=True)
    async def statistics_list(self, ctx: TormentContext) -> None:
        rows = await self.pool.fetch(
            "SELECT channel_id, option FROM counter WHERE guild_id = $1", ctx.guild.id
        )
        lines = []
        for row in rows:
            ch = ctx.guild.get_channel(row["channel_id"])
            if ch:
                lines.append(f"{ch.mention} — `{row['option']}`")
        if not lines:
            return await ctx.warn("No counter channels exist for this server")
        embed = discord.Embed(title="Counter Channels", color=_color("EMBED_INFO_COLOR"))
        paginator = Paginator(ctx, lines, embed)
        await paginator.start()

    STYLE_MAP = {
        "green": discord.ButtonStyle.success,
        "blurple": discord.ButtonStyle.primary,
        "gray": discord.ButtonStyle.secondary,
        "grey": discord.ButtonStyle.secondary,
        "red": discord.ButtonStyle.danger,
    }

    def _parse_message_link(self, link: str) -> tuple[int, int] | None:
        parts = link.strip("/").split("/")
        try:
            return int(parts[-2]), int(parts[-1])
        except (ValueError, IndexError):
            return None

    @commands.group(
        name="buttonrole",
        aliases=[],
        invoke_without_command=True,
        help="Manage button roles for a message",
        extras={"parameters": "n/a", "usage": "buttonrole"},
    )
    @commands.has_permissions(manage_roles=True)
    async def buttonrole(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @buttonrole.command(
        name="add",
        help="Add a button role to a message",
        extras={"parameters": "message link, role, style, emoji, label", "usage": "buttonrole add (link) (role) (style) [emoji] [label]"},
    )
    @commands.has_permissions(manage_roles=True)
    async def buttonrole_add(
        self,
        ctx: TormentContext,
        link: str,
        role: discord.Role,
        style: str,
        emoji: str = None,
        *,
        label: str = None,
    ) -> None:
        parsed = self._parse_message_link(link)
        if not parsed:
            return await ctx.warn("Invalid message link.")
        channel_id, message_id = parsed
        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            return await ctx.warn("Channel not found.")
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            return await ctx.warn("Message not found.")
        if message.author.id != self.bot.user.id:
            return await ctx.warn("Button roles can only be placed on messages sent by me.")
        style_key = style.lower()
        if style_key not in self.STYLE_MAP:
            return await ctx.warn("Invalid style. Use: `green`, `blurple`, `gray`, or `red`.")
        existing = await self.pool.fetch(
            "SELECT role_id FROM button_roles WHERE message_id = $1", message_id
        )
        if len(existing) >= 25:
            return await ctx.warn("A message can have at most **25** button roles.")
        if any(r["role_id"] == role.id for r in existing):
            return await ctx.warn(f"{role.mention} is already a button role on that message.")
        if not label and not emoji:
            label = role.name
        resolved_emoji = None
        if emoji:
            resolved_emoji = discord.PartialEmoji.from_str(emoji)
        await self.pool.execute(
            """
            INSERT INTO button_roles (guild_id, channel_id, message_id, role_id, style, emoji, label)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            ctx.guild.id, channel_id, message_id, role.id, style_key,
            str(resolved_emoji) if resolved_emoji else None, label,
        )
        view = ButtonRoleView(self.pool, message_id)
        await view.rebuild(self.bot)
        self.bot.add_view(view, message_id=message_id)
        await message.edit(view=view)
        return await ctx.success(f"Successfully added {role.mention} as a button role on that message.")

    @buttonrole.command(
        name="remove",
        help="Remove a button role by its number",
        extras={"parameters": "message link, button number", "usage": "buttonrole remove (link) (number)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def buttonrole_remove(self, ctx: TormentContext, link: str, number: int) -> None:
        parsed = self._parse_message_link(link)
        if not parsed:
            return await ctx.warn("Invalid message link.")
        channel_id, message_id = parsed
        rows = await self.pool.fetch(
            "SELECT role_id FROM button_roles WHERE message_id = $1 ORDER BY role_id", message_id
        )
        if not rows:
            return await ctx.warn("No button roles found on that message.")
        if number < 1 or number > len(rows):
            return await ctx.warn(f"Invalid number. There are **{len(rows)}** button roles on that message.")
        target_role_id = rows[number - 1]["role_id"]
        await self.pool.execute(
            "DELETE FROM button_roles WHERE message_id = $1 AND role_id = $2",
            message_id, target_role_id,
        )
        channel = ctx.guild.get_channel(channel_id)
        if channel:
            try:
                message = await channel.fetch_message(message_id)
                remaining = await self.pool.fetch(
                    "SELECT role_id FROM button_roles WHERE message_id = $1", message_id
                )
                if remaining:
                    view = ButtonRoleView(self.pool, message_id)
                    await view.rebuild(self.bot)
                    self.bot.add_view(view, message_id=message_id)
                    await message.edit(view=view)
                else:
                    await message.edit(view=None)
            except discord.HTTPException:
                pass
        return await ctx.success(f"Successfully removed button role **#{number}** from that message.")

    @buttonrole.command(
        name="removeall",
        help="Remove all button roles from a message",
        extras={"parameters": "message link", "usage": "buttonrole removeall (link)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def buttonrole_removeall(self, ctx: TormentContext, link: str) -> None:
        parsed = self._parse_message_link(link)
        if not parsed:
            return await ctx.warn("Invalid message link.")
        channel_id, message_id = parsed
        result = await self.pool.execute(
            "DELETE FROM button_roles WHERE message_id = $1", message_id
        )
        if result == "DELETE 0":
            return await ctx.warn("No button roles found on that message.")
        channel = ctx.guild.get_channel(channel_id)
        if channel:
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(view=None)
            except discord.HTTPException:
                pass
        return await ctx.success("Successfully removed all button roles from that message.")

    @buttonrole.command(
        name="reset",
        help="Remove all button roles in this server",
        extras={"parameters": "n/a", "usage": "buttonrole reset"},
    )
    @commands.has_permissions(manage_roles=True)
    async def buttonrole_reset(self, ctx: TormentContext) -> None:
        rows = await self.pool.fetch(
            "SELECT DISTINCT message_id, channel_id FROM button_roles WHERE guild_id = $1", ctx.guild.id
        )
        if not rows:
            return await ctx.warn("No button roles exist in this server.")
        await self.pool.execute(
            "DELETE FROM button_roles WHERE guild_id = $1", ctx.guild.id
        )
        for row in rows:
            channel = ctx.guild.get_channel(row["channel_id"])
            if channel:
                try:
                    message = await channel.fetch_message(row["message_id"])
                    await message.edit(view=None)
                except discord.HTTPException:
                    pass
        return await ctx.success("Successfully removed all button roles in this server.")

    @buttonrole.command(
        name="list",
        help="View all button roles in this server",
        extras={"parameters": "n/a", "usage": "buttonrole list"},
    )
    @commands.has_permissions(manage_roles=True)
    async def buttonrole_list(self, ctx: TormentContext) -> None:
        rows = await self.pool.fetch(
            "SELECT message_id, channel_id, role_id, style, emoji, label FROM button_roles WHERE guild_id = $1 ORDER BY message_id, role_id",
            ctx.guild.id,
        )
        if not rows:
            return await ctx.warn("No button roles exist in this server.")
        lines = []
        for i, row in enumerate(rows, 1):
            role = ctx.guild.get_role(row["role_id"])
            channel = ctx.guild.get_channel(row["channel_id"])
            role_fmt = role.mention if role else f"`{row['role_id']}`"
            ch_fmt = channel.mention if channel else f"`{row['channel_id']}`"
            label_fmt = f"`{row['label']}`" if row["label"] else ""
            emoji_fmt = f"{row['emoji']} " if row["emoji"] else ""
            lines.append(f"`{i}.` {emoji_fmt}{role_fmt} {label_fmt} — {ch_fmt} [`{row['message_id']}`] `{row['style']}`")
        embed = discord.Embed(title="Button Roles", color=_color("EMBED_INFO_COLOR"))
        paginator = Paginator(ctx, lines, embed)
        await paginator.start()

    def _vanity_check():
        async def predicate(ctx: TormentContext) -> bool:
            if ctx.guild.premium_subscription_count < 14:
                raise commands.CheckFailure("This server needs at least **14 boosts** (Level 3) to use vanity roles.")
            return True
        return commands.check(predicate)

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        if after.bot or not after.guild:
            return
        config = await self.pool.fetchrow(
            "SELECT substring, channel_id, message FROM vanity_config WHERE guild_id = $1",
            after.guild.id,
        )
        if not config or not config["substring"]:
            return
        role_ids = await self.pool.fetch(
            "SELECT role_id FROM vanity_roles WHERE guild_id = $1", after.guild.id
        )
        if not role_ids:
            return
        substring = config["substring"].lower()

        def _has_vanity(member: discord.Member) -> bool:
            for activity in member.activities:
                if isinstance(activity, discord.CustomActivity) and activity.name:
                    if substring in activity.name.lower():
                        return True
            return False

        had_before = _has_vanity(before)
        has_now = _has_vanity(after)

        if had_before == has_now:
            return

        was_tracking = await self.pool.fetchval(
            "SELECT 1 FROM vanity_members WHERE guild_id = $1 AND user_id = $2",
            after.guild.id, after.id,
        )

        if has_now and not was_tracking:
            await self.pool.execute(
                "INSERT INTO vanity_members (guild_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                after.guild.id, after.id,
            )
            for row in role_ids:
                role = after.guild.get_role(row["role_id"])
                if role:
                    try:
                        await after.add_roles(role, reason="Vanity role awarded")
                    except discord.HTTPException:
                        pass
            if config["message"] and config["channel_id"]:
                channel = after.guild.get_channel(config["channel_id"])
                if channel:
                    try:
                        script = Script(config["message"], [after.guild, channel, after])
                        await script.send(channel)
                    except Exception:
                        pass

        elif not has_now and was_tracking:
            await self.pool.execute(
                "DELETE FROM vanity_members WHERE guild_id = $1 AND user_id = $2",
                after.guild.id, after.id,
            )
            for row in role_ids:
                role = after.guild.get_role(row["role_id"])
                if role and role in after.roles:
                    try:
                        await after.remove_roles(role, reason="Vanity role removed")
                    except discord.HTTPException:
                        pass

    @commands.group(
        name="vanity",
        invoke_without_command=True,
        help="Manage vanity role settings",
        extras={"parameters": "n/a", "usage": "vanity"},
    )
    @commands.has_permissions(manage_guild=True)
    async def vanity(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @vanity.command(
        name="set",
        help="Set the vanity substring to watch for in statuses",
        extras={"parameters": "substring", "usage": "vanity set (substring)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def vanity_set(self, ctx: TormentContext, *, substring: str) -> None:
        if ctx.guild.premium_subscription_count < 14:
            return await ctx.warn("This server needs at least **14 boosts** (Level 3) to use vanity roles.")
        await self.pool.execute(
            """
            INSERT INTO vanity_config (guild_id, substring)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET substring = $2
            """,
            ctx.guild.id, substring,
        )
        return await ctx.success(f"Successfully set vanity substring to `{substring}`")

    @vanity.group(
        name="role",
        invoke_without_command=True,
        help="Manage vanity award roles",
        extras={"parameters": "n/a", "usage": "vanity role"},
    )
    @commands.has_permissions(manage_guild=True)
    async def vanity_role(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @vanity_role.command(
        name="add",
        help="Add a role to award for vanity",
        extras={"parameters": "role", "usage": "vanity role add (role)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def vanity_role_add(self, ctx: TormentContext, *, role: discord.Role) -> None:
        if ctx.guild.premium_subscription_count < 14:
            return await ctx.warn("This server needs at least **14 boosts** (Level 3) to use vanity roles.")
        await self.pool.execute(
            "INSERT INTO vanity_roles (guild_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            ctx.guild.id, role.id,
        )
        return await ctx.success(f"Successfully set {role.mention} as an award role")

    @vanity_role.command(
        name="remove",
        aliases=["rm", "delete", "del"],
        help="Remove a vanity award role",
        extras={"parameters": "role", "usage": "vanity role remove (role)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def vanity_role_remove(self, ctx: TormentContext, *, role: discord.Role) -> None:
        result = await self.pool.execute(
            "DELETE FROM vanity_roles WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id, role.id,
        )
        if result == "DELETE 0":
            return await ctx.warn(f"{role.mention} is not a vanity award role")
        return await ctx.success(f"Successfully removed {role.mention} as an award role")

    @vanity_role.command(
        name="list",
        help="List all vanity award roles",
        extras={"parameters": "n/a", "usage": "vanity role list"},
    )
    @commands.has_permissions(manage_guild=True)
    async def vanity_role_list(self, ctx: TormentContext) -> None:
        rows = await self.pool.fetch(
            "SELECT role_id FROM vanity_roles WHERE guild_id = $1", ctx.guild.id
        )
        if not rows:
            return await ctx.warn("No vanity award roles set")
        lines = []
        for i, row in enumerate(rows, 1):
            role = ctx.guild.get_role(row["role_id"])
            role_fmt = role.mention if role else f"`{row['role_id']}`"
            lines.append(f"`{i}.` {role_fmt}")
        embed = discord.Embed(title="Vanity Award Roles", color=_color("EMBED_INFO_COLOR"))
        paginator = Paginator(ctx, lines, embed)
        await paginator.start()

    @vanity.command(
        name="message",
        aliases=["msg"],
        help="Set the thank you message when a user advertises your server",
        extras={"parameters": "message", "usage": "vanity message (message)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def vanity_message(self, ctx: TormentContext, *, script_text: str) -> None:
        if ctx.guild.premium_subscription_count < 14:
            return await ctx.warn("This server needs at least **14 boosts** (Level 3) to use vanity roles.")
        await Script.convert(ctx, script_text)
        await self.pool.execute(
            """
            INSERT INTO vanity_config (guild_id, message)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET message = $2
            """,
            ctx.guild.id, script_text,
        )
        return await ctx.success("Successfully set the vanity thank you message")

    @vanity.command(
        name="channel",
        aliases=["award"],
        help="Set the channel where vanity messages are sent",
        extras={"parameters": "channel", "usage": "vanity channel (channel)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def vanity_channel(self, ctx: TormentContext, channel: discord.TextChannel) -> None:
        if ctx.guild.premium_subscription_count < 14:
            return await ctx.warn("This server needs at least **14 boosts** (Level 3) to use vanity roles.")
        await self.pool.execute(
            """
            INSERT INTO vanity_config (guild_id, channel_id)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2
            """,
            ctx.guild.id, channel.id,
        )
        return await ctx.success(f"Successfully set vanity award channel to {channel.mention}")

    @tasks.loop(minutes=1)
    async def _timer_task(self) -> None:
        rows = await self.pool.fetch(
            "SELECT guild_id, channel_id, message, interval FROM timers WHERE next_send <= NOW()"
        )
        for row in rows:
            channel = self.bot.get_channel(row["channel_id"])
            if not channel:
                await self.pool.execute(
                    "DELETE FROM timers WHERE guild_id = $1 AND channel_id = $2",
                    row["guild_id"], row["channel_id"],
                )
                continue
            try:
                guild = self.bot.get_guild(row["guild_id"])
                script = Script(row["message"], [guild, channel])
                await script.send(channel)
            except Exception:
                pass
            await self.pool.execute(
                "UPDATE timers SET next_send = NOW() + interval WHERE guild_id = $1 AND channel_id = $2",
                row["guild_id"], row["channel_id"],
            )

    @_timer_task.before_loop
    async def _before_timer_task(self) -> None:
        await self.bot.wait_until_ready()

    @commands.group(
        name="timer",
        invoke_without_command=True,
        help="Manage auto messages for a channel",
        extras={"parameters": "n/a", "usage": "timer"},
    )
    @commands.has_permissions(manage_guild=True)
    async def timer(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @timer.command(
        name="add",
        help="Add an auto message to a channel",
        extras={"parameters": "channel, interval, message", "usage": "timer add (channel) (interval) (message)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def timer_add(self, ctx: TormentContext, channel: discord.TextChannel, interval: str, *, message: str) -> None:
        try:
            seconds = _parse_interval(interval)
        except ValueError as e:
            return await ctx.warn(str(e))
        await Script.convert(ctx, message)
        await self.pool.execute(
            """
            INSERT INTO timers (guild_id, channel_id, interval, message, next_send)
            VALUES ($1, $2, $3::INTERVAL, $4, NOW() + $3::INTERVAL)
            ON CONFLICT (guild_id, channel_id) DO UPDATE
            SET interval = $3::INTERVAL, message = $4, next_send = NOW() + $3::INTERVAL
            """,
            ctx.guild.id, channel.id, f"{seconds} seconds", message,
        )
        fmt = _fmt_interval(seconds)
        return await ctx.success(
            f"Successfully added an **auto message** with `{fmt}` interval to {channel.mention}.\n"
            f"You can preview your message by running `{ctx.prefix}timer view {channel.mention}`."
        )

    @timer.command(
        name="remove",
        aliases=["delete", "del", "rm"],
        help="Remove the auto message from a channel",
        extras={"parameters": "channel", "usage": "timer remove (channel)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def timer_remove(self, ctx: TormentContext, channel: discord.TextChannel) -> None:
        result = await self.pool.execute(
            "DELETE FROM timers WHERE guild_id = $1 AND channel_id = $2",
            ctx.guild.id, channel.id,
        )
        if result == "DELETE 0":
            return await ctx.warn(f"No auto message set for {channel.mention}")
        return await ctx.success(f"Successfully removed the auto message from {channel.mention}")

    @timer.command(
        name="view",
        help="Preview the auto message for a channel",
        extras={"parameters": "channel", "usage": "timer view (channel)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def timer_view(self, ctx: TormentContext, channel: discord.TextChannel) -> None:
        row = await self.pool.fetchrow(
            "SELECT message, interval, next_send FROM timers WHERE guild_id = $1 AND channel_id = $2",
            ctx.guild.id, channel.id,
        )
        if not row:
            return await ctx.warn(f"No auto message set for {channel.mention}")
        script = Script(row["message"], [ctx.guild, channel, ctx.author])
        embed = discord.Embed(title="Auto Message Preview", color=_color("EMBED_INFO_COLOR"))
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(name="Interval", value=f"`{row['interval']}`", inline=True)
        embed.add_field(name="Next Send", value=discord.utils.format_dt(row["next_send"], "R"), inline=True)
        embed.add_field(name="Message", value=f"```{row['message'][:500]}```", inline=False)
        await ctx.send(embed=embed)

    @timer.command(
        name="list",
        help="View all auto messages in this server",
        extras={"parameters": "n/a", "usage": "timer list"},
    )
    @commands.has_permissions(manage_guild=True)
    async def timer_list(self, ctx: TormentContext) -> None:
        rows = await self.pool.fetch(
            "SELECT channel_id, interval, next_send FROM timers WHERE guild_id = $1", ctx.guild.id
        )
        if not rows:
            return await ctx.warn("No auto messages set in this server")
        lines = []
        for i, row in enumerate(rows, 1):
            ch = ctx.guild.get_channel(row["channel_id"])
            ch_fmt = ch.mention if ch else f"`{row['channel_id']}`"
            lines.append(
                f"`{i}.` {ch_fmt} — every `{row['interval']}` — next {discord.utils.format_dt(row['next_send'], 'R')}"
            )
        embed = discord.Embed(title="Auto Messages", color=_color("EMBED_INFO_COLOR"))
        paginator = Paginator(ctx, lines, embed)
        await paginator.start()

    @commands.Cog.listener("on_message")
    async def _reaction_trigger_listener(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        rows = await self.pool.fetch(
            "SELECT emoji FROM reaction_triggers WHERE guild_id = $1", message.guild.id
        )
        for row in rows:
            trigger_rows = await self.pool.fetch(
                "SELECT trigger FROM reaction_trigger_words WHERE guild_id = $1 AND emoji = $2",
                message.guild.id, row["emoji"],
            )
            for tr in trigger_rows:
                if tr["trigger"].lower() in message.content.lower():
                    try:
                        await message.add_reaction(row["emoji"])
                    except discord.HTTPException:
                        pass
                    break

    @commands.Cog.listener("on_message")
    async def _reaction_messages_listener(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        rows = await self.pool.fetch(
            "SELECT emoji FROM reaction_message_channels WHERE guild_id = $1 AND channel_id = $2",
            message.guild.id, message.channel.id,
        )
        for row in rows:
            try:
                await message.add_reaction(row["emoji"])
            except discord.HTTPException:
                pass

    @commands.group(
        name="reaction",
        invoke_without_command=True,
        help="React to a message or manage reaction triggers",
        extras={"parameters": "message link, emoji", "usage": "reaction (link) (emoji)"},
    )
    @commands.has_permissions(manage_messages=True)
    async def reaction(self, ctx: TormentContext, link: str, emoji: str) -> None:
        parts = link.strip("/").split("/")
        try:
            channel_id, message_id = int(parts[-2]), int(parts[-1])
        except (ValueError, IndexError):
            return await ctx.warn("Invalid message link.")
        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            return await ctx.warn("Channel not found.")
        try:
            msg = await channel.fetch_message(message_id)
        except discord.NotFound:
            return await ctx.warn("Message not found.")
        try:
            await msg.add_reaction(emoji)
        except discord.HTTPException:
            return await ctx.warn("Invalid emoji or failed to react.")
        await ctx.message.add_reaction("✅")

    @reaction.command(
        name="add",
        help="Add a reaction trigger",
        extras={"parameters": "emoji, trigger", "usage": "reaction add (emoji) (trigger)"},
    )
    @commands.has_permissions(manage_messages=True)
    async def reaction_add(self, ctx: TormentContext, emoji: str, *, trigger: str) -> None:
        await self.pool.execute(
            "INSERT INTO reaction_triggers (guild_id, emoji) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            ctx.guild.id, emoji,
        )
        existing = await self.pool.fetchval(
            "SELECT 1 FROM reaction_trigger_words WHERE guild_id = $1 AND emoji = $2 AND trigger = $3",
            ctx.guild.id, emoji, trigger.lower(),
        )
        if existing:
            return await ctx.warn(f"That trigger already exists for {emoji}")
        await self.pool.execute(
            "INSERT INTO reaction_trigger_words (guild_id, emoji, trigger) VALUES ($1, $2, $3)",
            ctx.guild.id, emoji, trigger.lower(),
        )
        return await ctx.success(f"Successfully added trigger `{trigger}` for {emoji}")

    @reaction.command(
        name="remove",
        aliases=["rm"],
        help="Remove a reaction trigger",
        extras={"parameters": "emoji, trigger", "usage": "reaction remove (emoji) (trigger)"},
    )
    @commands.has_permissions(manage_messages=True)
    async def reaction_remove(self, ctx: TormentContext, emoji: str, *, trigger: str) -> None:
        result = await self.pool.execute(
            "DELETE FROM reaction_trigger_words WHERE guild_id = $1 AND emoji = $2 AND trigger = $3",
            ctx.guild.id, emoji, trigger.lower(),
        )
        if result == "DELETE 0":
            return await ctx.warn(f"No trigger `{trigger}` found for {emoji}")
        remaining = await self.pool.fetchval(
            "SELECT COUNT(*) FROM reaction_trigger_words WHERE guild_id = $1 AND emoji = $2",
            ctx.guild.id, emoji,
        )
        if not remaining:
            await self.pool.execute(
                "DELETE FROM reaction_triggers WHERE guild_id = $1 AND emoji = $2",
                ctx.guild.id, emoji,
            )
        return await ctx.success(f"Successfully removed trigger `{trigger}` for {emoji}")

    @reaction.command(
        name="removeall",
        help="Remove all triggers for an emoji",
        extras={"parameters": "trigger", "usage": "reaction removeall (trigger)"},
    )
    @commands.has_permissions(manage_messages=True)
    async def reaction_removeall(self, ctx: TormentContext, *, trigger: str) -> None:
        result = await self.pool.execute(
            "DELETE FROM reaction_trigger_words WHERE guild_id = $1 AND trigger = $2",
            ctx.guild.id, trigger.lower(),
        )
        if result == "DELETE 0":
            return await ctx.warn(f"No triggers found for `{trigger}`")
        return await ctx.success(f"Successfully removed all triggers for `{trigger}`")

    @reaction.command(
        name="reset",
        help="Remove all reaction triggers in this server",
        extras={"parameters": "n/a", "usage": "reaction reset"},
    )
    @commands.has_permissions(manage_messages=True)
    async def reaction_reset(self, ctx: TormentContext) -> None:
        r1 = await self.pool.execute("DELETE FROM reaction_trigger_words WHERE guild_id = $1", ctx.guild.id)
        await self.pool.execute("DELETE FROM reaction_triggers WHERE guild_id = $1", ctx.guild.id)
        if r1 == "DELETE 0":
            return await ctx.warn("No reaction triggers exist in this server")
        return await ctx.success("Successfully removed all reaction triggers")

    @reaction.command(
        name="list",
        help="View all reaction triggers in this server",
        extras={"parameters": "n/a", "usage": "reaction list"},
    )
    @commands.has_permissions(manage_messages=True)
    async def reaction_list(self, ctx: TormentContext) -> None:
        rows = await self.pool.fetch(
            "SELECT emoji, trigger FROM reaction_trigger_words WHERE guild_id = $1 ORDER BY emoji",
            ctx.guild.id,
        )
        if not rows:
            return await ctx.warn("No reaction triggers set in this server")
        lines = [f"{row['emoji']} — `{row['trigger']}`" for row in rows]
        embed = discord.Embed(title="Reaction Triggers", color=_color("EMBED_INFO_COLOR"))
        paginator = Paginator(ctx, lines, embed)
        await paginator.start()

    @reaction.group(
        name="messages",
        invoke_without_command=True,
        help="Set reactions on every message in a channel",
        extras={"parameters": "channel, [emojis]", "usage": "reaction messages (channel) [emoji1] [emoji2] [emoji3]"},
    )
    @commands.has_permissions(manage_messages=True)
    async def reaction_messages(
        self,
        ctx: TormentContext,
        channel: discord.TextChannel,
        emoji1: str = None,
        emoji2: str = None,
        emoji3: str = None,
    ) -> None:
        emojis = [e for e in [emoji1, emoji2, emoji3] if e]
        if not emojis:
            result = await self.pool.execute(
                "DELETE FROM reaction_message_channels WHERE guild_id = $1 AND channel_id = $2",
                ctx.guild.id, channel.id,
            )
            if result == "DELETE 0":
                return await ctx.warn(f"No message reactions set for {channel.mention}")
            return await ctx.success(f"Successfully removed all message reactions from {channel.mention}")
        slowmode = channel.slowmode_delay
        if slowmode < 60:
            return await ctx.warn(f"{channel.mention} must have a slowmode of at least **1 minute**.")
        await self.pool.execute(
            "DELETE FROM reaction_message_channels WHERE guild_id = $1 AND channel_id = $2",
            ctx.guild.id, channel.id,
        )
        for emoji in emojis[:3]:
            await self.pool.execute(
                "INSERT INTO reaction_message_channels (guild_id, channel_id, emoji) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                ctx.guild.id, channel.id, emoji,
            )
        emoji_fmt = " ".join(emojis[:3])
        return await ctx.success(f"Successfully set {emoji_fmt} as message reactions in {channel.mention}")

    @reaction_messages.command(
        name="list",
        help="View all message reaction channels",
        extras={"parameters": "n/a", "usage": "reaction messages list"},
    )
    @commands.has_permissions(manage_messages=True)
    async def reaction_messages_list(self, ctx: TormentContext) -> None:
        rows = await self.pool.fetch(
            "SELECT channel_id, emoji FROM reaction_message_channels WHERE guild_id = $1 ORDER BY channel_id",
            ctx.guild.id,
        )
        if not rows:
            return await ctx.warn("No message reaction channels set in this server")
        grouped: dict[int, list[str]] = {}
        for row in rows:
            grouped.setdefault(row["channel_id"], []).append(row["emoji"])
        lines = []
        for cid, emojis in grouped.items():
            ch = ctx.guild.get_channel(cid)
            ch_fmt = ch.mention if ch else f"`{cid}`"
            lines.append(f"{ch_fmt} — {' '.join(emojis)}")
        embed = discord.Embed(title="Message Reaction Channels", color=_color("EMBED_INFO_COLOR"))
        paginator = Paginator(ctx, lines, embed)
        await paginator.start()


    async def _get_booster_base(self, guild_id: int) -> int | None:
        return await self.pool.fetchval(
            "SELECT base_role_id FROM booster_role_config WHERE guild_id = $1", guild_id
        )

    async def _boosterrole_enabled(self, guild_id: int) -> bool:
        return bool(await self.pool.fetchval(
            "SELECT enabled FROM booster_role_config WHERE guild_id = $1", guild_id
        ))

    async def _get_booster_includes(self, guild_id: int) -> list[int]:
        rows = await self.pool.fetch(
            "SELECT role_id FROM booster_role_include WHERE guild_id = $1", guild_id
        )
        return [r["role_id"] for r in rows]

    @commands.Cog.listener()
    async def on_member_update_booster(self, before: discord.Member, after: discord.Member) -> None:
        if before.premium_since is not None and after.premium_since is None:
            row = await self.pool.fetchrow(
                "SELECT role_id FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
                after.guild.id, after.id,
            )
            if not row:
                return
            role = after.guild.get_role(row["role_id"])
            if role:
                try:
                    await role.delete(reason="Member stopped boosting")
                except discord.HTTPException:
                    pass
            await self.pool.execute(
                "DELETE FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
                after.guild.id, after.id,
            )

    @commands.group(
        name="boosterrole",
        aliases=["br"],
        invoke_without_command=True,
        help="Manage your custom booster role",
        extras={"parameters": "n/a", "usage": "boosterrole"},
    )
    async def boosterrole(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @boosterrole.command(
        name="create",
        help="Create your custom booster role",
        extras={"parameters": "name", "usage": "boosterrole create (name)"},
    )
    async def boosterrole_create(self, ctx: TormentContext, *, name: str) -> None:
        if not await self._boosterrole_enabled(ctx.guild.id):
            return await ctx.warn("Booster roles are not enabled in this server.")
        if not ctx.author.premium_since:
            return await ctx.warn("You must be a server booster to use this command.")

        existing = await self.pool.fetchval(
            "SELECT role_id FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        if existing:
            return await ctx.warn("You already have a booster role. Use `boosterrole color` or `boosterrole rename` to modify it.")

        base_role_id = await self._get_booster_base(ctx.guild.id)
        base_role = ctx.guild.get_role(base_role_id) if base_role_id else None

        try:
            role = await ctx.guild.create_role(name=name, reason=f"Booster role for {ctx.author}")
            if base_role:
                try:
                    await role.edit(position=base_role.position)
                except discord.HTTPException:
                    pass
            await ctx.author.add_roles(role, reason="Booster role created")
        except discord.HTTPException as e:
            return await ctx.warn(f"Failed to create role: {e}")

        await self.pool.execute(
            "INSERT INTO booster_roles (guild_id, user_id, role_id) VALUES ($1, $2, $3) ON CONFLICT (guild_id, user_id) DO UPDATE SET role_id = $3",
            ctx.guild.id, ctx.author.id, role.id,
        )
        await ctx.success(f"Created your booster role {role.mention}.")

    @boosterrole.command(
        name="color",
        aliases=["colour"],
        help="Set the color of your booster role (hex only, or 'dominant' for avatar color)",
        extras={"parameters": "hex", "usage": "boosterrole color (#RRGGBB)"},
    )
    async def boosterrole_color(self, ctx: TormentContext, *, color: str) -> None:
        if not await self._boosterrole_enabled(ctx.guild.id):
            return await ctx.warn("Booster roles are not enabled in this server.")
        if not ctx.author.premium_since:
            return await ctx.warn("You must be a server booster to use this command.")

        role_id = await self.pool.fetchval(
            "SELECT role_id FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        if not role_id:
            return await ctx.warn("You don't have a booster role yet. Use `boosterrole create` first.")

        role = ctx.guild.get_role(role_id)
        if not role:
            return await ctx.warn("Your booster role no longer exists. Use `boosterrole create` to make a new one.")

        if color.lower() == "dominant":
            avatar = ctx.author.display_avatar
            data = await avatar.read()
            parsed = await _dominant_color(data)
        else:
            parsed = _parse_color(color)
            if parsed is None:
                return await ctx.warn(f"Invalid color `{color}`. Use a hex code like `#FF0000` or `FF0000`, or use `dominant` to pull from your avatar.")

        try:
            await role.edit(color=parsed, reason="Booster role color update")
        except discord.HTTPException as e:
            return await ctx.warn(f"Failed to update color: {e}")

        await ctx.success(f"Updated your booster role color to `{parsed}`.")

    @boosterrole.command(
        name="rename",
        help="Rename your booster role",
        extras={"parameters": "name", "usage": "boosterrole rename (name)"},
    )
    async def boosterrole_rename(self, ctx: TormentContext, *, name: str) -> None:
        if not await self._boosterrole_enabled(ctx.guild.id):
            return await ctx.warn("Booster roles are not enabled in this server.")
        if not ctx.author.premium_since:
            return await ctx.warn("You must be a server booster to use this command.")

        role_id = await self.pool.fetchval(
            "SELECT role_id FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        if not role_id:
            return await ctx.warn("You don't have a booster role yet. Use `boosterrole create` first.")

        role = ctx.guild.get_role(role_id)
        if not role:
            return await ctx.warn("Your booster role no longer exists. Use `boosterrole create` to make a new one.")

        try:
            await role.edit(name=name, reason="Booster role rename")
        except discord.HTTPException as e:
            return await ctx.warn(f"Failed to rename role: {e}")

        await ctx.success(f"Renamed your booster role to **{name}**.")

    @boosterrole.command(
        name="icon",
        help="Set the icon of your booster role (Level 2+ server required)",
        extras={"parameters": "emoji or url", "usage": "boosterrole icon (emoji or url)"},
    )
    async def boosterrole_icon(self, ctx: TormentContext, *, value: str = None) -> None:
        if not await self._boosterrole_enabled(ctx.guild.id):
            return await ctx.warn("Booster roles are not enabled in this server.")
        if not ctx.author.premium_since:
            return await ctx.warn("You must be a server booster to use this command.")

        if ctx.guild.premium_tier < 2:
            return await ctx.warn("Your server needs to be at least **Level 2** to use role icons.")

        role_id = await self.pool.fetchval(
            "SELECT role_id FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        if not role_id:
            return await ctx.warn("You don't have a booster role yet. Use `boosterrole create` first.")

        role = ctx.guild.get_role(role_id)
        if not role:
            return await ctx.warn("Your booster role no longer exists.")

        display_icon = None

        if ctx.message.attachments:
            data = await ctx.message.attachments[0].read()
            display_icon = data
        elif value:
            match = EMOJI_RE.search(value) if hasattr(ctx.cog, '_emoji_re') else None
            custom_match = re.search(r"<a?:[a-zA-Z0-9_]+:(\d+)>", value)
            if custom_match:
                emoji_id = custom_match.group(1)
                animated = value.startswith("<a:")
                ext = "gif" if animated else "png"
                url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=96"
                import aiohttp as _aiohttp
                async with _aiohttp.ClientSession() as s:
                    async with s.get(url) as resp:
                        if resp.status == 200:
                            display_icon = await resp.read()
            elif value.startswith("http"):
                import aiohttp as _aiohttp
                async with _aiohttp.ClientSession() as s:
                    async with s.get(value) as resp:
                        if resp.status == 200:
                            display_icon = await resp.read()
            else:
                display_icon = value

        try:
            await role.edit(display_icon=display_icon, reason="Booster role icon update")
        except discord.HTTPException as e:
            return await ctx.warn(f"Failed to set icon: {e}")

        await ctx.success("Updated your booster role icon.")

    @boosterrole.command(
        name="delete",
        aliases=["remove"],
        help="Delete your booster role",
        extras={"parameters": "n/a", "usage": "boosterrole delete"},
    )
    async def boosterrole_delete(self, ctx: TormentContext) -> None:
        if not await self._boosterrole_enabled(ctx.guild.id):
            return await ctx.warn("Booster roles are not enabled in this server.")
        role_id = await self.pool.fetchval(
            "SELECT role_id FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        if not role_id:
            return await ctx.warn("You don't have a booster role.")

        role = ctx.guild.get_role(role_id)
        if role:
            try:
                await role.delete(reason="Booster role deleted by user")
            except discord.HTTPException:
                pass

        await self.pool.execute(
            "DELETE FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        await ctx.success("Deleted your booster role.")

    @boosterrole.command(
        name="share",
        help="Share your booster role with another member",
        extras={"parameters": "member", "usage": "boosterrole share (member)"},
    )
    async def boosterrole_share(self, ctx: TormentContext, *, member: discord.Member) -> None:
        if not await self._boosterrole_enabled(ctx.guild.id):
            return await ctx.warn("Booster roles are not enabled in this server.")
        if not ctx.author.premium_since:
            return await ctx.warn("You must be a server booster to use this command.")

        if member == ctx.author:
            return await ctx.warn("You can't share your role with yourself.")

        role_id = await self.pool.fetchval(
            "SELECT role_id FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        if not role_id:
            return await ctx.warn("You don't have a booster role yet.")

        role = ctx.guild.get_role(role_id)
        if not role:
            return await ctx.warn("Your booster role no longer exists.")

        if role in member.roles:
            try:
                await member.remove_roles(role, reason=f"Booster role unshared by {ctx.author}")
            except discord.HTTPException as e:
                return await ctx.warn(f"Failed to remove role: {e}")
            return await ctx.success(f"Removed your booster role from {member.mention}.")

        try:
            await member.add_roles(role, reason=f"Booster role shared by {ctx.author}")
        except discord.HTTPException as e:
            return await ctx.warn(f"Failed to share role: {e}")

        await ctx.success(f"Shared your booster role with {member.mention}.")

    @boosterrole.group(
        name="config",
        invoke_without_command=True,
        help="Configure the booster role system",
        extras={"parameters": "n/a", "usage": "boosterrole config"},
    )
    @commands.has_permissions(manage_guild=True)
    async def boosterrole_config(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @boosterrole.command(
        name="toggle",
        help="Enable or disable the booster role system",
        extras={"parameters": "n/a", "usage": "boosterrole toggle"},
    )
    @commands.has_permissions(manage_guild=True)
    async def boosterrole_toggle(self, ctx: TormentContext) -> None:
        current = await self.pool.fetchval(
            "SELECT enabled FROM booster_role_config WHERE guild_id = $1", ctx.guild.id
        )
        new_state = not bool(current)
        await self.pool.execute(
            "INSERT INTO booster_role_config (guild_id, enabled) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET enabled = $2",
            ctx.guild.id, new_state,
        )
        state_str = "enabled" if new_state else "disabled"
        await ctx.success(f"Booster roles are now **{state_str}**.")

    @boosterrole_config.command(
        name="base",
        help="Set the base role that booster roles are placed below",
        extras={"parameters": "role", "usage": "boosterrole config base (role)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def boosterrole_config_base(self, ctx: TormentContext, *, role: discord.Role) -> None:
        await self.pool.execute(
            "INSERT INTO booster_role_config (guild_id, base_role_id) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET base_role_id = $2",
            ctx.guild.id, role.id,
        )
        await ctx.success(f"Set the booster role base to {role.mention}.")

    @boosterrole_config.command(
        name="include",
        help="Toggle a role that can also use booster roles (non-boosters)",
        extras={"parameters": "role", "usage": "boosterrole config include (role)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def boosterrole_config_include(self, ctx: TormentContext, *, role: discord.Role) -> None:
        existing = await self.pool.fetchval(
            "SELECT 1 FROM booster_role_include WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id, role.id,
        )
        if existing:
            await self.pool.execute(
                "DELETE FROM booster_role_include WHERE guild_id = $1 AND role_id = $2",
                ctx.guild.id, role.id,
            )
            return await ctx.success(f"Removed {role.mention} from booster role access.")

        await self.pool.execute(
            "INSERT INTO booster_role_include (guild_id, role_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            ctx.guild.id, role.id,
        )
        await ctx.success(f"Added {role.mention} to booster role access.")

    @boosterrole_config.command(
        name="reset",
        help="Remove a member's booster role",
        extras={"parameters": "member", "usage": "boosterrole config reset (member)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def boosterrole_config_reset(self, ctx: TormentContext, *, member: discord.Member) -> None:
        role_id = await self.pool.fetchval(
            "SELECT role_id FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id,
        )
        if not role_id:
            return await ctx.warn(f"{member.mention} doesn't have a booster role.")

        role = ctx.guild.get_role(role_id)
        if role:
            try:
                await role.delete(reason=f"Booster role reset by {ctx.author}")
            except discord.HTTPException:
                pass

        await self.pool.execute(
            "DELETE FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id,
        )
        await ctx.success(f"Removed {member.mention}'s booster role.")

    @boosterrole_config.command(
        name="list",
        help="View all active booster roles in this server",
        extras={"parameters": "n/a", "usage": "boosterrole config list"},
    )
    @commands.has_permissions(manage_guild=True)
    async def boosterrole_config_list(self, ctx: TormentContext) -> None:
        rows = await self.pool.fetch(
            "SELECT user_id, role_id FROM booster_roles WHERE guild_id = $1 ORDER BY user_id",
            ctx.guild.id,
        )
        if not rows:
            return await ctx.warn("No booster roles exist in this server.")

        lines = []
        for i, row in enumerate(rows, 1):
            member = ctx.guild.get_member(row["user_id"])
            role = ctx.guild.get_role(row["role_id"])
            member_fmt = member.mention if member else f"`{row['user_id']}`"
            role_fmt = role.mention if role else f"`{row['role_id']}`"
            lines.append(f"`{i}.` {member_fmt} → {role_fmt}")

        embed = discord.Embed(title="Booster Roles", color=_color("EMBED_INFO_COLOR"))
        paginator = Paginator(ctx, lines, embed)
        await paginator.start()


class ButtonRoleView(discord.ui.View):
    def __init__(self, pool: asyncpg.Pool, message_id: int) -> None:
        super().__init__(timeout=None)
        self.pool = pool
        self.message_id = message_id

    async def rebuild(self, bot: commands.Bot) -> None:
        self.clear_items()
        rows = await self.pool.fetch(
            "SELECT role_id, style, emoji, label FROM button_roles WHERE message_id = $1 ORDER BY role_id",
            self.message_id,
        )
        style_map = {
            "green": discord.ButtonStyle.success,
            "blurple": discord.ButtonStyle.primary,
            "gray": discord.ButtonStyle.secondary,
            "grey": discord.ButtonStyle.secondary,
            "red": discord.ButtonStyle.danger,
        }
        for row in rows:
            style = style_map.get(row["style"], discord.ButtonStyle.primary)
            emoji = discord.PartialEmoji.from_str(row["emoji"]) if row["emoji"] else None
            label = row["label"] or None
            button = discord.ui.Button(
                style=style,
                label=label,
                emoji=emoji,
                custom_id=f"br:{self.message_id}:{row['role_id']}",
            )
            button.callback = self._make_callback(row["role_id"])
            self.add_item(button)

    def _make_callback(self, role_id: int):
        async def callback(interaction: discord.Interaction) -> None:
            if not interaction.guild:
                return
            member = interaction.guild.get_member(interaction.user.id)
            if not member:
                return
            role = interaction.guild.get_role(role_id)
            if not role:
                await interaction.response.send_message("That role no longer exists.", ephemeral=True)
                return
            if role in member.roles:
                await member.remove_roles(role, reason="Button role toggle")
                await interaction.response.send_message(f"Removed {role.mention} from you.", ephemeral=True)
            else:
                await member.add_roles(role, reason="Button role toggle")
                await interaction.response.send_message(f"Added {role.mention} to you.", ephemeral=True)
        return callback


def _parse_color(value: str) -> discord.Color | None:
    cleaned = value.strip().lstrip("#")
    try:
        return discord.Color(int(cleaned, 16))
    except ValueError:
        return None


async def _dominant_color(data: bytes) -> discord.Color:
    from PIL import Image as _Image
    import io as _io
    img = _Image.open(_io.BytesIO(data)).convert("RGB").resize((50, 50))
    pixels = list(img.getdata())
    r = sum(p[0] for p in pixels) // len(pixels)
    g = sum(p[1] for p in pixels) // len(pixels)
    b = sum(p[2] for p in pixels) // len(pixels)
    return discord.Color.from_rgb(r, g, b)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Configuration(bot))
