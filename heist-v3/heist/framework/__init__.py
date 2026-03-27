import logging
import glob
import os
import importlib
import asyncio

from datetime import datetime, timezone
from typing import List, Optional
from pathlib import Path
from aiohttp import ClientSession

import discord_ios
import discord
from discord import (
    Intents,
    Message,
    Guild,
    AuditLogEntry,
    HTTPException,
    Activity,
    ActivityType,
    AllowedMentions,
    Interaction,
    Embed,
    app_commands
)
from discord.ext.commands import (
    AutoShardedBot,
    ExtensionError,
    MinimalHelpCommand
)

from heist.backend import Backend
from heist.shared.dynamic import DynamicRoleButton

from heist.framework.pagination import Paginator
from heist.framework.discord import Context, CommandErrorHandler
from heist.framework.discord.cv2 import cv2 as cpv2

from heist.framework.discord.checks import is_blacklisted, get_blacklist_reason
from heist.framework.discord.decorators import register_user
from heist.framework.discord.commands import CommandCache, set_bot_instance, latency_loop
from heist.framework.script.webhook import ensure_webhook_server

from heist.shared.config import Authentication, Configuration
from heist.shared.clients import postgres
from heist.shared.clients.postgres import Database
from heist.shared.clients.settings import Settings
from heist.shared.clients.redis import Redis
#from heist.shared.clients.minio import MinIO
from heist.framework.dataprocessing import cp_system

logger = logging.getLogger("heist/main")

class heist(AutoShardedBot):
    """
    Custom bot class that extends AutoShardedBot.
    """
    backend: Backend
    database: Database
    redis: Redis
    version: str = "4.0.1"
    session: ClientSession
    config: Configuration
    cp_system = cp_system

    def __init__(
        self,
        Configuration: Configuration,
        port: int,
        cluster_id: int,
        shard_ids: List[int] = None,
        shard_count: int = None,
    ):
        super().__init__(
            command_prefix=self.get_prefix,
            help_command=MinimalHelpCommand(),
            case_insensitive=True,
            strip_after_prefix=True,
            owner_ids=Authentication.owner_ids,
            intents=Intents.all(),
            allowed_mentions=AllowedMentions(
                everyone=False,
                roles=False,
                users=True,
                replied_user=False,
            ),
            activity=Activity(
                type=ActivityType.streaming,
                name="🔗 heist.lol",
                url=f"https://twitch.tv/heist",
            ),
            shard_ids=shard_ids,
            shard_count=shard_count,
        )
        self.cluster_id = cluster_id
        self.backend = Backend(self, port)
        self.uptime = datetime.now(timezone.utc)
        self.Configuration = Configuration
        self.config = Configuration

    def get_message(
        self, message_id: int
    ) -> Optional[Message]:
        """
        Fetch a message from the cache.
        """
        return self._connection._get_message(message_id)

    async def get_guild_prefix(self, guild_id: int) -> str:
        """
        Get the prefix for a guild.
        """
        cache_key = f"prefix:guild:{guild_id}"

        if cached := await self.redis.get(cache_key):
            return cached

        try:
            if res := await self.pool.fetchrow(
                """
                SELECT prefix FROM prefix 
                WHERE guild_id = $1
                """,
                guild_id,
            ):
                prefix = (
                    res["prefix"]
                    or Configuration().defaults.prefix
                )
                if prefix:
                    await self.redis.set(
                        cache_key, prefix, ex=3600
                    )
                return prefix
        except Exception:
            pass

        return Configuration().defaults.prefix

    async def get_user_prefix(
        self, user_id: int
    ) -> Optional[str]:
        """
        Get the prefix for a user.
        """
        cache_key = f"prefix:user:{user_id}"

        if cached := await self.redis.get(cache_key):
            return cached

        if record := await self.pool.fetchrow(
            """
            SELECT prefix FROM "user".settings 
            WHERE user_id = $1
            """,
            user_id,
        ):
            prefix = record["prefix"]
            if prefix:
                await self.redis.set(
                    cache_key, prefix, ex=3600
                )
            return prefix

        return None

    async def get_prefix(
        self, message: Message
    ) -> List[str]:
        """
        Get the prefix for a message.
        """
        if not message.guild:
            return [self.Configuration.defaults.prefix]

        prefixes = []

        guild_prefix = await self.get_guild_prefix(
            message.guild.id
        )
        user_prefix = await self.get_user_prefix(
            message.author.id
        )

        if guild_prefix:
            prefixes.append(guild_prefix)
        if user_prefix:
            prefixes.append(user_prefix)
        if not prefixes:
            prefixes.append(
                self.Configuration.defaults.prefix
            )

        return [str(prefix) for prefix in prefixes]

    async def update_guild_prefix(self, guild_id: int, prefix: str) -> None:
        """
        Update the prefix for a guild.
        """
        try:
            existing = await self.pool.fetchval(
                """
                SELECT 1 FROM prefix 
                WHERE guild_id = $1 LIMIT 1
                """,
                guild_id,
            )

            if existing:
                await self.pool.execute(
                    """
                    UPDATE prefix SET prefix = $2 
                    WHERE guild_id = $1
                    """,
                    guild_id,
                    prefix,
                )
            else:
                await self.pool.execute(
                    """
                    INSERT INTO prefix (guild_id, prefix) 
                    VALUES ($1, $2)
                    """,
                    guild_id,
                    prefix,
                )

            if prefix:
                await self.redis.set(
                    f"prefix:guild:{guild_id}", prefix, ex=3600
                )
            else:
                await self.redis.delete(f"prefix:guild:{guild_id}")
        except Exception:
            pass


    async def update_user_prefix(
        self, user_id: int, prefix: Optional[str] = None
    ) -> None:
        """
        Update the prefix for a user.
        """
        if prefix is None:
            await self.pool.execute(
                """
                UPDATE "user".settings 
                SET prefix = NULL 
                WHERE user_id = $1
                """,
                user_id,
            )
            await self.redis.delete(
                f"prefix:user:{user_id}"
            )
        else:
            await self.pool.execute(
                """
                INSERT INTO "user".settings (user_id, prefix)
                VALUES ($1, $2)
                ON CONFLICT (user_id) 
                DO UPDATE SET prefix = $2
                """,
                user_id,
                prefix,
            )
            await self.redis.set(
                f"prefix:user:{user_id}", prefix, ex=3600
            )

    async def setup_whitelist_table(self):
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS whitelist (
                guild_id BIGINT PRIMARY KEY,
                added_at TIMESTAMP DEFAULT NOW()
            )
        """)

    async def is_whitelisted(self, guild_id: int) -> bool:
        result = await self.pool.fetchval(
            "SELECT 1 FROM whitelist WHERE guild_id = $1", guild_id
        )
        return result is not None

    async def check_guild_whitelist(self):
        for guild in self.guilds:
            if not await self.is_whitelisted(guild.id):
                try:
                    embed = discord.Embed(
                        title="Access Denied",
                        description="This server is not whitelisted. The bot will now leave.",
                        color=0xff0000
                    )
                    await self.notify(guild, embed=embed)
                except:
                    pass
                
                try:
                    await guild.leave()
                    logger.info(f"Left non-whitelisted guild: {guild.name} ({guild.id})")
                except:
                    pass

    async def on_ready(
        self,
    ):
        """
        Log in to the bot.
        """
        logger.info(
            f"Logged in as {self.user} (ID: {self.user.id})"
        )
        if self.shard_id:
            shard_guilds = sum(
                1
                for guild in self.guilds
                if guild.shard_id == self.shard_id
            )
            logger.info(
                f"Shard: {self.shard_id + 1}/{self.shard_count} with {shard_guilds} guild(s)"
            )
        
        await self.cp_system.initialize()
        await self.setup_whitelist_table()
        await CommandCache.load_commands(self)
        
        set_bot_instance(self)
        self.loop.create_task(latency_loop(self))

        from heist.framework.discord.commands import start_api
        asyncio.create_task(start_api())
        logger.info("Started API server on port 4323")
        
        await asyncio.sleep(5)
        await self.check_guild_whitelist()

    async def on_shard_ready(self, shard_id: int) -> None:
        """
        Custom on_shard_ready method that logs shard status.
        """
        try:
            guilds_in_shard = len([
                g
                for g in self.guilds
                if (g.id >> 22) % self.shard_count
                == shard_id
            ])
            logger.info(
                f"Shard {shard_id} ready: Serving {guilds_in_shard:,} guilds"
            )

            if shard_id == self.shard_count - 1:
                total_guilds = len(self.guilds)
                uptime_delta = (
                    datetime.now(timezone.utc) - self.uptime
                ).total_seconds()

                logger.info(
                    f"All {self.shard_count} shards connected ({uptime_delta:.2f}s): "
                    f"Serving {total_guilds:,} guilds"
                )

        except Exception as e:
            logger.error(
                f"Error in on_shard_ready for shard {shard_id}: {e}",
                exc_info=True,
            )

    async def on_shard_resumed(self, shard_id: int) -> None:
        """
        Custom on_shard_resumed method that logs shard status.
        """
        logger.info(f"Shard ID {shard_id} has resumed .")

    async def notify(
        self, guild: Guild, *args, **kwargs
    ) -> Optional[Message]:
        """
        Send a message to the first available channel.
        """
        if not isinstance(guild, Guild):
            logger.error(
                f"Expected Guild object, got {type(guild).__name__}"
            )
            return

        if (
            guild.system_channel
            and guild.system_channel.permissions_for(
                guild.me
            ).send_messages
        ):
            try:
                return await guild.system_channel.send(
                    *args, **kwargs
                )
            except HTTPException:
                return

        for channel in guild.text_channels:
            if channel.permissions_for(
                guild.me
            ).send_messages:
                try:
                    return await channel.send(
                        *args, **kwargs
                    )
                except HTTPException:
                    break

    async def _load_patches(self) -> None:
        """
        Load all patches in the framework directory.
        """
        for module in glob.glob(
            "heist/framework/discord/patches/**/*.py",
            recursive=True,
        ):
            if module.endswith("__init__.py"):
                continue

            module_name = (
                module.replace(os.path.sep, ".")
                .replace("/", ".")
                .replace(".py", "")
            )
            try:
                importlib.import_module(module_name)
                logger.info(f"Patched: {module}")

            except (ModuleNotFoundError, ImportError) as e:
                logger.error(
                    f"Error importing {module_name}: {e}"
                )

    async def _load_extensions(self) -> None:
        """
        Load all plugins in the framework directory.
        """
        loaded_count = 0
        jishaku_loaded = False

        for extension in sorted(
            Path("heist/plugins").glob("*")
        ):
            if extension.name.startswith(("_", ".")):
                continue

            package = (
                extension.stem
                if extension.is_file()
                and extension.suffix == ".py"
                else (
                    extension.name
                    if extension.is_dir()
                    and (extension / "__init__.py").exists()
                    else None
                )
            )

            if not package:
                continue

            try:
                if not jishaku_loaded:
                    await self.load_extension("jishaku")
                    jishaku_loaded = True

                await self.load_extension(
                    f"heist.plugins.{package}"
                )

                loaded_count += 1
                logger.info(f"Loaded extension: {package}")

            except ExtensionError as e:
                logger.error(
                    f"Error loading extension {package}: {e}"
                )

        logger.info(
            f"Loaded {loaded_count} extension(s)"
        )

    async def on_guild_join(self, guild):
        if not await self.is_whitelisted(guild.id):
            try:
                embed = discord.Embed(
                    title="Access Denied",
                    description="This server is not whitelisted. The bot will now leave.",
                    color=0xff0000
                )
                await self.notify(guild, embed=embed)
            except:
                pass
            
            try:
                await guild.leave()
                logger.info(f"Left non-whitelisted guild on join: {guild.name} ({guild.id})")
            except:
                pass

    async def setup_hook(self) -> None:
        """
        Initialize bot resources with cluster awareness
        """
        self.session = ClientSession(
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; U; CPU iPhone OS 4_0 like Mac OS X; en-us)"
                " AppleWebKit/532.9 (KHTML, like Gecko) Version/4.0.5 Mobile/8A293 Safari/6531.22.7"
            },
        )

        self.redis = await Redis.from_url()
        logger.info("Connected to Redis")

        self.database = await postgres.connect()
        logger.info("Connected to shared resources")

        await self._load_patches()
        logger.info("Loaded patches")

        await self._load_extensions()
        logger.info("Loaded packages")
        
        self.backend.start_task()
        logger.info("Started backend task")

        try:
            await ensure_webhook_server(self)
            logger.info("Started webhook server")
        except Exception as e:
            logger.info(e)

        self.add_dynamic_items(DynamicRoleButton)
        logger.info("Added dynamic views")
        
        async def global_app_command_check(interaction: Interaction) -> bool:
            if await is_blacklisted(self, interaction.user.id, "user"):
                print('hello 1 1 1', flush=True)
                reason = await get_blacklist_reason(self, interaction.user.id, "user")
                reason = reason or "**Breaking [Heist's Terms of Service](<https://heist.lol/terms>).**"

                await interaction.response.send_message(
                    f"""You are **blacklisted** from using [Heist](<https://heist.lol>) for: "**{reason}**".\n"""
                    f"-# Wrongfully blacklisted? You may appeal [**here**](<https://discord.gg/heistbot>).",
                    ephemeral=True
                )
                return False
            
            if interaction.guild and await is_blacklisted(self, interaction.guild.id, "guild"):
                print('hello 2 2 2', flush=True)
                reason = await get_blacklist_reason(self, interaction.guild.id, "guild")
                reason = reason or "**Breaking [Heist's Terms of Service](<https://heist.lol/terms>).**"

                await interaction.response.send_message(
                    f"""This **server** is blacklisted from using [Heist](<https://heist.lol>) for: "**{reason}**".\n"""
                    f"-# Wrongfully blacklisted? You may appeal [**here**](<https://discord.gg/heistbot>).",
                    ephemeral=True
                )
                return False

            return True

        self.tree.interaction_check = global_app_command_check
        logger.info("Added global app command check")

        asyncio.create_task(self.clear_txids())

        return await super().setup_hook()

    async def clear_txids(self):
        try:
            keys = await self.redis.keys("txid:*")
            if keys:
                await self.redis.delete(*keys)
        except Exception as e:
            logger.error(f"Failed to clear txid keys on startup: {e}")

    async def db_execute(self, query, params=(), fetchone=False):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                if fetchone:
                    return await conn.fetchrow(query, *params)
                return await conn.execute(query, *params)

    async def get_color(self, user_id: int) -> int:
        redis_key = f"color:{user_id}"
        cached = await self.redis.get(redis_key)
        if cached:
            return int(cached)
        row = await self.pool.fetchrow("SELECT color FROM preferences WHERE user_id = $1", user_id)
        color_value = row['color'] if row else 0xd3d6f1
        await self.redis.set(redis_key, str(color_value), ex=300)
        return color_value

    async def get_context(
        self, 
        message: Message | Interaction,
        *, 
        cls=Context
    ) -> Context:
        """
        Custom get_context method that adds the config attribute to the context.
        """
        if isinstance(message, Interaction):
            return await super().get_context(message, cls=cls)
        
        context = await super().get_context(
            message, cls=cls
        )
        
        try:
            if context.guild is not None:
                context.config = await Configuration.from_guild(
                    context.guild.id, self
                )
                context.settings = await Settings.fetch(
                    self, context.guild
                )
            else:
                context.config = Configuration()
                context.settings = None
        except Exception:
            context.config = Configuration()
            context.settings = None
        
        return context

    async def on_command_error(
        self, context: Context, exception: Exception
    ) -> None:
        """
        Custom error handler for commands.
        """
        await CommandErrorHandler.on_command_error(
            self, context, exception
        )

    async def on_command(self, ctx: Context) -> None:
        """
        Custom on_command method that logs command usage.
        """
        if not ctx.guild or not ctx.command:
            return

        try:
            logger.info(
                "%s (%s) used %s in %s (%s)",
                ctx.author.name,
                ctx.author.id,
                ctx.command.qualified_name,
                ctx.guild.name,
                ctx.guild.id,
            )
        except Exception as e:
            logger.error(f"Error logging command usage: {e}")

    async def close(self) -> None:
        """
        Cleanup resources and close the bot
        """
        if hasattr(self, 'session'):
            await self.session.close()
        if hasattr(self, 'database'):
            await self.database.close()
        if hasattr(self, 'redis'):
            await self.redis.close()
        if hasattr(self, 'backend'):
            await self.backend.stop()
        # await self.minio.close()

        await super().close()

    async def start(
        self, *, reconnect: bool = True
    ) -> None:  # type: ignore
        return await super().start(
            Authentication.token, reconnect=reconnect
        )

    @property
    def pool(self) -> Database:
        """
        Convenience property to access the database.
        """
        return self.database

    async def on_audit_log_entry_create(
        self, entry: AuditLogEntry
    ):
        """
        Handle audit log entry creation.
        """
        if not self.is_ready():
            return

        event = f"audit_log_entry_{entry.action.name}"
        self.dispatch(event, entry)

    async def process_commands(self, message: Message, /):
        """
        Proccess commands for a message.
        """
        if message.author.bot or not message.guild:
            return

        if await is_blacklisted(
            self, message.author.id, "user"
        ) or await is_blacklisted(
            self, message.guild.id, "guild"
        ):
            print("blacklisted")
            return
        
        await register_user(self, message.author.id, message.author.name, message.author.display_name)

        ctx = await self.get_context(message)
        if not ctx.valid:
            self.dispatch("message_without_command", ctx)
            return

        if await is_blacklisted(self, message.author.id, "user") or await is_blacklisted(self, message.guild.id, "guild"):
            return
        
        await register_user(self, message.author.id, message.author.name, message.author.display_name)

        if ctx.valid:
            ratelimit = await self.redis.ratelimited(
                f"global:{message.author.id}",
                limit=2,
                timespan=3,
            )
            if ratelimit:
                reaction_ratelimit = (
                    await self.redis.ratelimited(
                        f"reaction:{message.author.id}",
                        limit=1,
                        timespan=3,
                    )
                )
                if not reaction_ratelimit:
                    await ctx.message.add_reaction("⏳")
                logger.warning(
                    f"ignored possible abuse: user:{message.author.id} guild:{message.guild.id} command:{ctx.command}"
                )
                return

            await self.invoke(ctx)
    
    async def interaction_check(self, interaction: Interaction) -> bool:
        """
        Global check for all slash commands and interactions.
        """
        print(f"Interaction check for user {interaction.user.id}")
        if await is_blacklisted(self, interaction.user.id, "user"):
            print(f"User {interaction.user.id} is blacklisted")
            return False
        if interaction.guild and await is_blacklisted(self, interaction.guild.id, "guild"):
            print(f"Guild {interaction.guild.id} is blacklisted")
            return False
        
        await register_user(self, interaction.user.id, interaction.user.name, interaction.user.display_name)
        print("Interaction check passed")
        return True
    
    async def on_message(self, message: Message) -> None:
        """
        Handle incoming messages, including bot mentions.
        """
        if message.author.bot:
            return
            
        if self.user in message.mentions and message.guild and not message.reference:
            ctx = await self.get_context(message)
            prefix = await self.get_guild_prefix(message.guild.id)
            await ctx.reply(embed=Embed(
                description=f"{ctx.author.mention}: **Server prefix**: `{prefix}`",
                color=ctx.config.colors.information,
            ))
            return
            
        await self.process_commands(message)
    
    async def on_message_edit(self, before: Message, after: Message) -> None:
        """
        Custom on_message_edit method that handles message edits.
        """
        self.dispatch("member_activity", after.channel, after.author)
        if before.content == after.content:
            return

        if after.guild and not after.author.bot:
            ratelimit = await self.redis.ratelimited(
                f"global:{after.author.id}",
                limit=2,
                timespan=3,
            )
            if ratelimit:
                reaction_ratelimit = await self.redis.ratelimited(
                    f"reaction:{after.author.id}",
                    limit=1,
                    timespan=3,
                )
                if not reaction_ratelimit:
                    await after.add_reaction("⏳")
                
                logger.warning(
                    f"ignored possible abuse: user:{after.author.id} guild:{after.guild.id} command:{after.content}"
                )
                return

        return await self.process_commands(after)

__all__ = ("heist", "Context", "Paginator", "cp_system")
