from contextlib import suppress
import os
from logging import getLogger
from pathlib import Path
import uuid
import traceback

from discord import Activity, AllowedMentions, HTTPException, Intents, Message
from discord.ext.commands import (
	AutoShardedBot, 
	BadLiteralArgument,
	BotMissingPermissions,
	ChannelNotFound,
	CheckFailure,
	CommandInvokeError,
	CommandNotFound,
	CommandOnCooldown,
	DisabledCommand,
	MaxConcurrencyReached,
	MemberNotFound,
	MissingPermissions,
	MissingRequiredArgument,
	MissingRequiredAttachment,
	NSFWChannelRequired,
	NotOwner,
	RoleNotFound,
	UserNotFound,
	CooldownMapping,
	BucketType
)

from jishaku import Flags

from bot.services.api import API   
from bot.config import Config
from bot.types.context import Context
from bot.utilities.logging import setup_logging
from bot.managers.postgres import Postgres
from bot.managers.redis import Redis
from bot.services.session import HTTP
from bot.managers.ui.help import Help

setup_logging()
log = getLogger(__name__)

class Aerith(AutoShardedBot):
	def __init__(self, config: Config):
		self.config = config

		self.cooldown = CooldownMapping.from_cooldown(
			3, 5.8, BucketType.user
		)

		super().__init__(
			owner_ids=self.config.owner_ids,
			intents=Intents.all(),
			command_prefix=(self.get_prefix), # pyright: ignore[reportArgumentType]
			help_command=Help(),
			case_insensitive=True,
			allowed_mentions=AllowedMentions(
				everyone=False, users=False,
				roles=False, replied_user=False
			),
			activity=Activity(
				type=self.config.status.type,
				name=self.config.status.name,
				url=self.config.status.url
			) if self.config.status is not None else None
		)

	async def get_context(self, message: Message, *, cls=Context) -> Context:
		return await super().get_context(message, cls=cls)

	async def get_prefix(self, message: Message):
		prefixes = []

		if self.pool:
			user_prefix = await self.pool.fetchval(
				"SELECT prefix FROM users WHERE id = $1",
				message.author.id 
			)
			if user_prefix:
				prefixes.append(user_prefix)
			
			guild_prefix = await self.pool.fetchval(
				"SELECT prefix FROM guilds WHERE id = $1",
				message.guild.id if message.guild else None
			)

			if guild_prefix:
				prefixes.append(guild_prefix)

		else:
			return self.config.prefix
		
		prefixes.append(self.config.prefix)
		return prefixes

	async def load_from_dir(self, path: str, base_module: str) -> None:
		root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
		abs_path = os.path.join(root, path)
	
		if not os.path.exists(abs_path):
			log.error("Extension directory not found: %s", abs_path)
			return
	
		extensions = [
			e for e in os.scandir(abs_path)
			if e.is_dir() and os.path.isfile(os.path.join(e.path, "__init__.py"))
		]
	
		if not extensions:
			log.warning("No valid extensions found in /%s.", path)
			return
	
		for entry in extensions:
			module_path = f"{base_module}.{entry.name}"
	
			try:
				await self.load_extension(module_path)
				log.info("Loaded extension: %s", module_path)
	
			except Exception:
				log.exception("Failed to load extension: %s", module_path)

	async def cooldown_check(self, ctx: Context):
		if (bucket := self.cooldown.get_bucket(ctx.message or ctx)) and (retry_after := bucket.update_rate_limit()):
			raise CommandOnCooldown(bucket, retry_after, BucketType.user)
		
		return True

	async def setup_hook(self):
		log.info("booting the bot")
		for flag in ("NO_DM_TRACEBACK", "FORCE_PAGINATOR", "NO_UNDERSCORE", "HIDE"):
			setattr(Flags, flag, True)

		log.info("setting up checks and tasks")

		self.add_check(self.cooldown_check)

		log.info("creating database & redis connection")

		pclient = Postgres()
		self.pool = await pclient.create(
			schema=True, 
			schema_path=Path("~/aerith/bot/assets/tables.sql").expanduser()
		)
		
		rclient = Redis()
		self.redis = await rclient.create()

		log.info("created database & redis connection")

		self.session = await HTTP(1.0).connect()

		log.info("created http & lastfm session")
		log.info("loading extensions")
		
		await self.load_extension("jishaku")
		await self.load_from_dir("bot/plugins", "bot.plugins")

		log.info("loaded extensions")
		log.info("starting the API at api.aerith.lol")
		
		self.api = API()
		await self.api.start(self.pool)
		
		log.info("completed booting succesfully")

	async def on_ready(self):
		await self.api.push_all(self)
		
	async def on_message_edit(self, before: Message, after: Message):
		await self.process_commands(after)

	async def on_message(self, message: Message):
		if message.author.bot: return
		if message.guild and not message.channel.permissions_for(message.guild.me).send_messages:
			return
		
		if message.content == self.user.mention: # pyright: ignore[reportOptionalMemberAccess]
			return await message.reply(f"my prefix is `{self.config.prefix}`")
		
		await self.process_commands(message)

	async def on_command_error(self, ctx: Context, exception: Exception):
		if not ctx.guild or not ctx.channel.permissions_for(ctx.guild.me).send_messages:
			return

		if isinstance(exception, CommandInvokeError):
			exception = exception.original

		match exception:
			case (
				NotOwner()
				| CommandNotFound()
				| DisabledCommand()
			):
				return

			case (
				MissingRequiredArgument()
				| MissingRequiredAttachment()
				| BadLiteralArgument()
			):
				return await ctx.send_help(ctx.command)

			case CommandOnCooldown():
				return await ctx.respond(
					f"The command is on cooldown. Try again in {round(exception.retry_after, 1)}s"
				)

			case MissingPermissions() | BotMissingPermissions():
				missing = ", ".join(
					f"`{perm.replace('_', ' ').title()}`"
					for perm in exception.missing_permissions
				)

				prefix = (
					"You need"
					if isinstance(exception, MissingPermissions)
					else "I need"
				)

				return await ctx.respond(
					f"{prefix} the following permission(s): {missing}",
					state="warn",
				)

			case (
				MemberNotFound()
				| UserNotFound()
				| RoleNotFound()
				| ChannelNotFound()
			):
				return await ctx.respond(str(exception), state="warn")

			case NSFWChannelRequired():
				return await ctx.respond(
					"This command only works in **NSFW** channels.",
					state="warn",
				)

			case MaxConcurrencyReached():
				return await ctx.respond(
					f"Too many people are using this command. (Limit: {exception.number})",
					state="warn",
				)

			case CheckFailure():
				return await ctx.respond(
					"You don't have permission to use this command.",
					state="warn",
				)

			case HTTPException():
				with suppress(HTTPException):
					await ctx.respond(str(exception), state="warn")

			case _:
				if self.redis is not None:
					error_id = str(uuid.uuid4().hex[:12])

					await self.redis.set(
						name=f"err-{error_id}", 
						value="".join(
							traceback.format_exception( # type: ignore
                                type(exception),
                                exception,
                                exception.__traceback__
                            )
						),
						ex=60 * 60 * 4 # 4 hours
					)

					return await ctx.respond(
						f"An unexpected error occurred while running **{ctx.command.qualified_name if ctx.command is not None else 'Unknown Command'}**. \n-# Please report the following code in the [support server](https://discord.gg/aerithbot). `{error_id}`",
						state="no",
					)
				else:
					return await ctx.respond(f"An unexpected error occured. Please try again later.", state="no")