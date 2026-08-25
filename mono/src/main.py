from __future__ import annotations

import asyncio
import copy
import importlib
import json
import logging
import os
import socket
import threading
import uuid
from pathlib import Path
from typing import BinaryIO, ClassVar

if os.name == "nt":
    import msvcrt

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from src.cogs.owner import OwnerOnlyGroup
from src.services.prefixes import DEFAULT_PREFIX, store as prefix_store

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALLOWED_USERS_FILE = PROJECT_ROOT / "allowed_users.json"
INSTANCE_LOCK_FILE = PROJECT_ROOT / ".bot-instance.lock"
OPERATIONS_CHANNEL_ID = 1537931239980408854
COG_NAMES = (
    "core",
    "guilds",
    "information",
    "moderation",
    "community",
    "logging",
    "economy",
    "gambling",
    "fun",
    "polls",
    "media",
    "utility",
    "everyday_tools",
    "ai",
    "owner",
    "help",
    "lookup",
    "settings",
    "prefixes",
    "dm_watch",
)


def command_prefix(bot: commands.Bot, message: discord.Message) -> str:
    if message.guild is None:
        return DEFAULT_PREFIX
    return prefix_store.get(message.guild.id)

load_dotenv(PROJECT_ROOT / ".env")

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
DEV_GUILD = os.getenv("DEV_GUILD", "").strip()
MEMBERS_INTENT_ENABLED = os.getenv(
    "MEMBERS_INTENT",
    "",
).strip().lower() in {"1", "true", "yes", "on"}


class DiscordReconnectFilter(logging.Filter):
    """Turn expected DNS reconnect tracebacks into useful one-line messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not record.exc_info:
            return True

        error: BaseException | None = record.exc_info[1]
        while error is not None:
            if isinstance(
                error,
                (aiohttp.ClientConnectorDNSError, socket.gaierror),
            ):
                record.msg = (
                    "Discord connection temporarily lost because DNS lookup "
                    "failed. Retrying automatically."
                )
                record.args = ()
                record.exc_info = None
                record.exc_text = None
                break
            error = error.__cause__ or error.__context__
        return True


READY_LEVEL = 25
logging.addLevelName(READY_LEVEL, "READY")


class FriendlyConsoleFormatter(logging.Formatter):
    """Compact, coloured console logs with friendly component names."""

    RESET = "\033[0m"
    DIM = "\033[90m"
    COMPONENT = "\033[95m"
    LEVEL_COLOURS: ClassVar[dict[int, str]] = {
        logging.DEBUG: "\033[90m",
        logging.INFO: "\033[36m",
        READY_LEVEL: "\033[92m",
        logging.WARNING: "\033[93m",
        logging.ERROR: "\033[91m",
        logging.CRITICAL: "\033[1;91m",
    }

    def __init__(self, *, use_colour: bool) -> None:
        super().__init__(datefmt="%H:%M:%S")
        self.use_colour = use_colour

    @staticmethod
    def component_name(logger_name: str) -> str:
        if logger_name in {"__main__", "src.main"}:
            return "BOT"
        if logger_name == "src.cogs.dm_watch":
            return "DM WATCH"
        if logger_name.startswith("selfcord"):
            return "SELFCORD"
        if logger_name.startswith("discord"):
            return "DISCORD"
        if logger_name.startswith("src.cogs."):
            return logger_name.removeprefix("src.cogs.").replace("_", " ").upper()
        return logger_name.rsplit(".", 1)[-1].replace("_", " ").upper()

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, self.datefmt)
        level = record.levelname
        component = self.component_name(record.name)
        message = record.getMessage()

        if self.use_colour:
            level_colour = self.LEVEL_COLOURS.get(record.levelno, "")
            line = (
                f"{self.DIM}{timestamp}{self.RESET}  "
                f"{level_colour}{level:<8}{self.RESET} "
                f"{self.COMPONENT}[{component:<10}]{self.RESET}  {message}"
            )
        else:
            line = f"{timestamp}  {level:<8} [{component:<10}]  {message}"

        if record.exc_info:
            exception_text = self.formatException(record.exc_info)
            line = f"{line}\n{exception_text}"
        if record.stack_info:
            line = f"{line}\n{self.formatStack(record.stack_info)}"
        return line


console_handler = logging.StreamHandler()
console_handler.setFormatter(
    FriendlyConsoleFormatter(
        use_colour=console_handler.stream.isatty() and "NO_COLOR" not in os.environ,
    )
)
logging.basicConfig(level=logging.INFO, handlers=[console_handler], force=True)
logger = logging.getLogger(__name__)
logging.getLogger("discord.client").addFilter(DiscordReconnectFilter())
# These contain browser fingerprints and other implementation details that are
# not useful during normal operation. Warnings and errors remain visible.
logging.getLogger("selfcord.http").setLevel(logging.WARNING)


def acquire_instance_lock() -> BinaryIO:
    lock_file = INSTANCE_LOCK_FILE.open("a+b")
    if lock_file.tell() == 0:
        lock_file.write(b"\0")
        lock_file.flush()
    lock_file.seek(0)
    if os.name != "nt":
        return lock_file
    try:
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock_file.close()
        raise SystemExit(
            "Another copy of the bot is already running. Stop its terminal "
            "before starting a new one."
        ) from None
    return lock_file


class BotContext(commands.Context):
    """Context that applies a command's slash-response visibility choice."""

    async def send(self, *args, **kwargs):
        if self.interaction is not None and "ephemeral" not in kwargs:
            kwargs["ephemeral"] = bool(self.kwargs.get("ephemeral", False))
        return await super().send(*args, **kwargs)


class Bot(commands.Bot):
    def __init__(self) -> None:
        self.started_at = discord.utils.utcnow()
        self.restart_requested = False
        self.shutdown_requested = False
        self._startup_notification_sent = False
        self._owner_user: discord.abc.User | None = None
        self.startup_issues: list[str] = []
        self.loaded_extension_count = 0
        self.runtime_loop: asyncio.AbstractEventLoop | None = None
        self.command_clearances = self._load_allowed_users()
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = MEMBERS_INTENT_ENABLED

        super().__init__(
            command_prefix=command_prefix,
            intents=intents,
            help_command=None,
            activity=discord.Game(name="Hello"),
            allowed_contexts=app_commands.AppCommandContext(
                guild=True,
                dm_channel=True,
                private_channel=True,
            ),
            allowed_installs=app_commands.AppInstallationType(
                guild=True,
                user=True,
            ),
        )

    @staticmethod
    def _load_allowed_users() -> dict[str, set[int]]:
        empty = {"lookup": set(), "ai": set(), "owner": set(), "jishaku": set()}
        if not ALLOWED_USERS_FILE.exists():
            return empty
        try:
            data = json.loads(ALLOWED_USERS_FILE.read_text(encoding="utf-8"))
            if "clearances" in data:
                loaded = {
                    name: {int(user_id) for user_id in data["clearances"].get(name, [])}
                    for name in empty
                }
            else:
                legacy = {int(user_id) for user_id in data.get("user_ids", [])}
                loaded = {
                    "lookup": set(),
                    "ai": set(legacy),
                    "owner": set(),
                    "jishaku": set(),
                }
            all_users = set().union(*loaded.values())
            for user_id in all_users:
                highest = next(
                    name for name in ("jishaku", "owner", "ai", "lookup")
                    if user_id in loaded[name]
                )
                for name in loaded:
                    if name != highest:
                        loaded[name].discard(user_id)
            return loaded
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            logger.exception("Could not read %s", ALLOWED_USERS_FILE)
            return empty

    def save_allowed_users(self) -> None:
        ALLOWED_USERS_FILE.write_text(
            json.dumps(
                {
                    "clearances": {
                        name: sorted(user_ids)
                        for name, user_ids in self.command_clearances.items()
                    }
                },
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

    async def is_primary_owner(self, user: discord.abc.User) -> bool:
        return await super().is_owner(user)

    def clearance_for(self, user_id: int) -> str | None:
        for name in ("jishaku", "owner", "ai", "lookup"):
            if user_id in self.command_clearances[name]:
                return name
        return None

    def has_clearance(self, user_id: int, required: str) -> bool:
        levels = {"lookup": 0, "ai": 1, "owner": 2, "jishaku": 3}
        assigned = self.clearance_for(user_id)
        return assigned is not None and levels[assigned] >= levels[required]

    async def is_owner(self, user: discord.abc.User, /) -> bool:
        return (
            await self.is_primary_owner(user)
            or self.has_clearance(user.id, "jishaku")
        )

    async def can_use_lookup(self, user: discord.abc.User) -> bool:
        return await self.is_primary_owner(user) or self.has_clearance(user.id, "lookup")

    async def can_use_ai(self, user: discord.abc.User) -> bool:
        return await self.is_primary_owner(user) or self.has_clearance(user.id, "ai")

    async def can_use_owner_commands(self, user: discord.abc.User) -> bool:
        return await self.is_primary_owner(user) or self.has_clearance(user.id, "owner")

    async def can_use_restricted_commands(self, user: discord.abc.User) -> bool:
        return await self.can_use_ai(user)

    async def get_context(
        self,
        origin,
        /,
        *,
        cls=BotContext,
    ):
        # Prefix commands can use a friendlier nested spelling while the slash
        # tree keeps /balance-edit (Discord does not allow /balance to be both
        # a runnable command and a parent group).
        if isinstance(origin, discord.Message):
            prefix = command_prefix(self, origin)
            for root in ("balance", "bal", "wallet"):
                nested = f"{prefix}{root} edit"
                if origin.content == nested or origin.content.startswith(nested + " "):
                    rewritten = copy.copy(origin)
                    rewritten.content = (
                        f"{prefix}balance-edit" + origin.content[len(nested):]
                    )
                    origin = rewritten
                    break
        return await super().get_context(origin, cls=cls)

    async def setup_hook(self) -> None:
        self.runtime_loop = asyncio.get_running_loop()
        self.tree.on_error = self.on_app_command_error
        await self.load_cogs()
        self.organize_owner_commands()
        await self.sync_commands()

    def organize_owner_commands(self) -> None:
        """Arrange owner-only and related public application commands."""
        owner_root = self.tree.get_command("o")
        if not isinstance(owner_root, app_commands.Group):
            owner_root = OwnerOnlyGroup(self)
            self.tree.add_command(owner_root)

        category_descriptions = {
            "core": "Bot access and runtime controls",
            "information": "Owner-only Discord information",
            "lookup": "Linked accounts and cache controls",
            "recache": "Linked-account member cache controls",
            "settings": "Bot profile and presence settings",
            "emojis": "Bot application emoji controls",
            "economy": "Owner-only economy controls",
        }

        categories: dict[str, app_commands.Group] = {}
        for name, description in category_descriptions.items():
            category = owner_root.get_command(name)
            if not isinstance(category, app_commands.Group):
                category = OwnerOnlyGroup(
                    self,
                    name=name,
                    description=description,
                    parent=owner_root,
                )
            categories[name] = category

        def move_top_level(command_name: str, category_name: str) -> None:
            command = self.tree.get_command(command_name)
            if command is None or command is owner_root:
                return
            self.tree.remove_command(command_name)
            categories[category_name].add_command(command, override=True)

        def move_nested(
            root_name: str,
            path: tuple[str, ...],
            category_name: str,
        ) -> None:
            root = self.tree.get_command(root_name)
            if not isinstance(root, app_commands.Group):
                return
            parent = root
            parents = [root]
            for part in path[:-1]:
                child = parent.get_command(part)
                if not isinstance(child, app_commands.Group):
                    return
                parent = child
                parents.append(parent)
            command = parent.get_command(path[-1])
            if command is None:
                return
            parent.remove_command(path[-1])
            categories[category_name].add_command(command, override=True)

            # Remove source groups that became empty so they do not leave
            # useless entries in the public slash-command menu.
            for index in range(len(parents) - 1, -1, -1):
                group = parents[index]
                if group.commands:
                    break
                if index == 0:
                    self.tree.remove_command(root_name)
                else:
                    parents[index - 1].remove_command(group.name)

        for command_name in (
            "allow", "disallow", "allowed", "reload-cog", "reload",
            "linked-status",
        ):
            move_top_level(command_name, "core")

        for command_name in ("inviteinfo", "userinfo"):
            move_top_level(command_name, "information")

        for command_name in (
            "cache-status", "user-servers",
            "mutual-servers", "checkuser",
        ):
            move_top_level(command_name, "lookup")
        move_nested("linked-account", ("refresh",), "lookup")
        move_nested("recache", ("start",), "recache")
        move_nested("recache", ("retry-failed",), "recache")

        for command_name in ("avatar", "username", "bio", "status", "activity"):
            move_nested("set", (command_name,), "settings")

        for command_name in ("list", "add", "rename", "delete"):
            move_nested("bot-emojis", (command_name,), "emojis")

        for command_name in ("add", "remove"):
            move_nested("economy", ("admins", command_name), "economy")

        self._organize_public_commands()

    def _organize_public_commands(self) -> None:
        """Group related slash commands without changing their prefix forms."""
        group_specs = {
            "image": (
                "Image and media editing tools",
                ("caption", "caption-studio", "convert", "resize", "pixelate", "ascii"),
            ),
            "game": (
                "Interactive games and party questions",
                (
                    "rpc",
                    "tic-tac-toe",
                    "connect4",
                    "guess-number",
                    "would-you-rather",
                    "truth-or-dare",
                ),
            ),
        }

        for group_name, (description, command_names) in group_specs.items():
            group = self.tree.get_command(group_name)
            if not isinstance(group, app_commands.Group):
                group = app_commands.Group(
                    name=group_name,
                    description=description,
                )
                self.tree.add_command(group)

            for command_name in command_names:
                command = self.tree.get_command(command_name)
                if command is None or command is group:
                    continue
                self.tree.remove_command(command_name)
                group.add_command(command, override=True)

    async def load_cogs(self) -> None:
        package = "src.cogs"
        loaded = 0
        failures: list[str] = []

        # Jishaku exposes powerful owner-only debugging commands. Keep its
        # root command out of the public help catalog while retaining access
        # through the configured prefix (for example, `;jsk`).
        os.environ.setdefault("JISHAKU_HIDE", "true")
        try:
            await self.load_extension("jishaku")
        except Exception as error:
            logger.exception("Failed to load Jishaku")
            summary = (str(error).strip() or error.__class__.__name__)[:350]
            self.startup_issues.append(
                f"**Jishaku failed:** `{error.__class__.__name__}: {summary}`"
            )

        for cog_name in COG_NAMES:
            try:
                await self.load_extension(f"{package}.{cog_name}")
            except Exception as error:
                logger.exception("Failed to load cog: %s", cog_name)
                failures.append(cog_name)
                summary = (str(error).strip() or error.__class__.__name__)[:350]
                self.startup_issues.append(
                    f"**Cog `{cog_name}` failed:** "
                    f"`{error.__class__.__name__}: {summary}`"
                )
            else:
                loaded += 1

        self.loaded_extension_count = loaded

        logger.info(
            "Loaded %d cog(s); %d failed",
            loaded,
            len(failures),
        )
        # Stay connected when one extension fails so the owner receives a DM
        # identifying the broken cog. The failed extension remains unavailable.

    async def sync_commands(self) -> None:
        global_commands = await self.tree.sync()
        logger.info("Synced %d global command(s)", len(global_commands))

        # Remove obsolete server-only copies that would otherwise appear
        # alongside the global commands.
        if not DEV_GUILD:
            return

        try:
            guild = discord.Object(id=int(DEV_GUILD))
        except ValueError:
            raise RuntimeError(
                "DEV_GUILD must be a numeric Discord server ID"
            ) from None

        self.tree.clear_commands(guild=guild)
        await self.tree.sync(guild=guild)
        logger.info("Removed development-server command copies from %s", DEV_GUILD)

    async def notify_owner(
        self,
        title: str,
        details: str,
        *,
        status: str = "info",
    ) -> None:
        try:
            if self._owner_user is None:
                application = await self.application_info()
                owner = application.owner
                if isinstance(owner, discord.Team):
                    owner = owner.owner
                if not isinstance(owner, discord.abc.User):
                    return
                self._owner_user = owner
            occurred_at = int(discord.utils.utcnow().timestamp())
            accent = {
                "success": discord.Color.green(),
                "warning": discord.Color.orange(),
                "error": discord.Color.red(),
                "info": discord.Color.blurple(),
            }.get(status, discord.Color.blurple())
            view = discord.ui.LayoutView()
            view.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay(
                        f"## {title}\n{details}\n\n"
                        f"-# <t:{occurred_at}:F> • <t:{occurred_at}:R>"
                    ),
                    accent_colour=accent,
                )
            )
            await self._owner_user.send(view=view)
        except discord.HTTPException:
            logger.warning("Could not DM the bot owner: %s", title, exc_info=True)

    async def notify_operations_channel(
        self,
        title: str,
        details: str,
        *,
        status: str = "info",
    ) -> None:
        try:
            channel = self.get_channel(OPERATIONS_CHANNEL_ID)
            if channel is None:
                channel = await self.fetch_channel(OPERATIONS_CHANNEL_ID)
            occurred_at = int(discord.utils.utcnow().timestamp())
            accent = {
                "success": discord.Color.green(),
                "warning": discord.Color.orange(),
                "error": discord.Color.red(),
                "info": discord.Color.blurple(),
            }.get(status, discord.Color.blurple())
            view = discord.ui.LayoutView()
            view.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay(
                        f"## {title}\n{details}\n\n"
                        f"-# <t:{occurred_at}:F> • <t:{occurred_at}:R>"
                    ),
                    accent_colour=accent,
                )
            )
            await channel.send(view=view)
        except (discord.HTTPException, AttributeError):
            logger.warning(
                "Could not send operations notice to channel %s: %s",
                OPERATIONS_CHANNEL_ID,
                title,
                exc_info=True,
            )

    async def wait_for_linked_accounts(self) -> tuple[int, int]:
        dm_watch = self.get_cog("DMWatch")
        clients = getattr(dm_watch, "_user_clients", [])
        if clients:
            for _ in range(60):
                if all(client.is_ready() for client in clients):
                    break
                await asyncio.sleep(0.5)
        return sum(client.is_ready() for client in clients), len(clients)

    async def _notify_when_fully_ready(self) -> None:
        linked_ready, linked_total = await self.wait_for_linked_accounts()
        expected_extensions = len(COG_NAMES)
        issues = list(self.startup_issues)
        if self.loaded_extension_count != expected_extensions:
            issues.append(
                f"**Extensions:** `{self.loaded_extension_count}/{expected_extensions}` loaded"
            )
        if linked_ready < linked_total:
            issues.append(
                f"**Linked accounts:** `{linked_ready}/{linked_total}` connected"
            )
        healthy = not issues
        status_section = (
            "### Status\n`Healthy` — everything started successfully."
            if healthy
            else "### Issues Detected\n" + "\n".join(
                f"- {issue}" for issue in issues
            )
        )
        await self.notify_operations_channel(
            "Bot Ready" if healthy else "Bot Started with Issues",
            f"**Bot:** {self.user}\n"
            f"**Extensions:** {self.loaded_extension_count}/{expected_extensions} loaded\n"
            f"**Cog instances:** {len(self.cogs)} active\n"
            f"**Linked accounts:** {linked_ready}/{linked_total} ready\n"
            f"**Servers:** {len(self.guilds):,}\n\n"
            f"{status_section}",
            status="success" if healthy else "error",
        )

    async def on_ready(self) -> None:
        if self.user is not None:
            logger.log(
                READY_LEVEL,
                "Connected as %s (ID: %s)",
                self.user,
                self.user.id,
            )
        if not self._startup_notification_sent:
            self._startup_notification_sent = True
            asyncio.create_task(self._notify_when_fully_ready())

    async def on_disconnect(self) -> None:
        logger.warning(
            "Disconnected from Discord. The client will reconnect automatically."
        )

    async def on_resumed(self) -> None:
        logger.info("Discord connection restored; the previous session resumed.")
        await self.notify_operations_channel(
            "Connection Restored",
            "The bot reconnected to Discord and resumed its previous session.",
            status="success",
        )

    async def on_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        async def send_error(message: str) -> None:
            try:
                if ctx.interaction is None:
                    await ctx.send(message)
                elif ctx.interaction.response.is_done():
                    await ctx.interaction.followup.send(
                        message,
                        ephemeral=True,
                    )
                else:
                    await ctx.interaction.response.send_message(
                        message,
                        ephemeral=True,
                    )
            except discord.NotFound:
                logger.warning(
                    "Could not deliver a command error because the "
                    "interaction token had expired."
                )
            except discord.HTTPException as send_exception:
                logger.warning(
                    "Could not deliver a command error response: %s",
                    send_exception,
                )

        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.NotOwner):
            await send_error("You don't have permission to use this command.")
            return

        if isinstance(error, commands.CommandOnCooldown):
            await send_error(
                f"That command is on cooldown. Try again in "
                f"{error.retry_after:.1f} seconds."
            )
            return

        if isinstance(error, commands.BotMissingPermissions):
            permissions = ", ".join(
                permission.replace("_", " ").title()
                for permission in error.missing_permissions
            )
            await send_error(f"I am missing these permissions: {permissions}.")
            return

        if isinstance(error, commands.MissingPermissions):
            await send_error("You don't have permission to use this command.")
            return

        if isinstance(error, commands.NoPrivateMessage):
            await send_error("That command can only be used in a server.")
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await send_error(f"Missing argument: `{error.param.name}`")
            return

        if isinstance(error, commands.UserNotFound):
            await send_error(
                "I couldn't find that user. Use a user mention or a numeric "
                "user ID; role mentions such as `@&role` are not valid."
            )
            return

        if isinstance(
            error,
            (
                commands.UnexpectedQuoteError,
                commands.InvalidEndOfQuotedStringError,
                commands.ExpectedClosingQuoteError,
            ),
        ):
            await send_error(
                "That input contains an invalid quote character. Remove any "
                "quotes and use `;lookup <user ID>` or the `/lookup` user picker."
            )
            return

        if isinstance(error, commands.BadArgument):
            await send_error(
                "That argument is invalid. Use the slash-command picker or "
                "check the ID and try again."
            )
            return

        original = (
            error.original if isinstance(error, commands.CommandInvokeError) else error
        )
        error_id = uuid.uuid4().hex[:8]
        await send_error(
            f"Something went wrong while running that command. Error ID: `{error_id}`"
        )
        logger.error(
            "Unhandled prefix-command error %s in %s",
            error_id,
            ctx.command,
            exc_info=(
                type(original),
                original,
                original.__traceback__,
            ),
        )

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CommandOnCooldown):
            message = (
                f"That command is on cooldown. Try again in "
                f"{error.retry_after:.1f} seconds."
            )
        elif isinstance(error, app_commands.TransformerError):
            message = (
                "One of the provided options is invalid. Check your selection "
                "and try again."
            )
        elif isinstance(error, app_commands.BotMissingPermissions):
            permissions = ", ".join(
                permission.replace("_", " ").title()
                for permission in error.missing_permissions
            )
            message = f"I am missing these permissions: {permissions}."
        elif isinstance(
            error,
            (
                app_commands.MissingPermissions,
                app_commands.CheckFailure,
            ),
        ):
            message = "You do not have permission to use that command."
        else:
            original = (
                error.original
                if isinstance(error, app_commands.CommandInvokeError)
                else error
            )
            error_id = uuid.uuid4().hex[:8]
            message = (
                "Something went wrong while running that command. "
                f"Error ID: `{error_id}`"
            )
            logger.error(
                "Unhandled application-command error %s in %s",
                error_id,
                interaction.command,
                exc_info=(
                    type(original),
                    original,
                    original.__traceback__,
                ),
            )

        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(
                    message,
                    ephemeral=True,
                )
        except discord.HTTPException:
            logger.warning(
                "Could not deliver an application-command error response",
                exc_info=True,
            )


class ConsoleCommands:
    """Read and run local commands without blocking Discord's event loop."""

    COMMANDS: ClassVar[dict[str, str]] = {
        "help": "Show all available terminal commands.",
        "dm": "Send a message to a server channel or known DM user.",
        "discord-commands": "List all loaded Discord commands.",
        "reload-cog": "Reload one loaded cog without restarting the bot.",
        "secret-commands": "List hidden owner-only Discord commands.",
        "status": "Show whether the bot is connected and ready.",
        "sync": "Sync Discord slash commands now.",
        "restart": "Restart the bot without closing this window.",
        "stop": "Shut down the bot and close this window.",
    }
    SECRET_COMMANDS: ClassVar[dict[str, str]] = {
        "/o core": "Bot access, linked-account, reload, and runtime controls.",
        "/o information": "Owner-only invite and user information.",
        "/o lookup": "Linked-account lookup and cache information.",
        "/o recache start": "Start a complete linked-server cache pass.",
        "/o recache retry-failed": "Retry only the latest failed server scans.",
        "/o settings": "Change the bot profile and presence.",
        "/o emojis": "Manage application emojis.",
        "/o economy": "Manage economy administrators.",
        "<prefix>servers": "List every server the bot is connected to.",
        "<prefix>users": "List known users who installed and used the app.",
        "<prefix>leave <server ID>": "Make the bot leave a server.",
        "<prefix>serverinfo [server ID]": "Show detailed server information.",
    }

    def __init__(self) -> None:
        self.bot: Bot | None = None
        self._thread: threading.Thread | None = None

    def set_bot(self, bot: Bot) -> None:
        self.bot = bot

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._read_commands,
            name="console-commands",
            daemon=True,
        )
        self._thread.start()

    @classmethod
    def print_help(cls) -> None:
        print("\nAvailable terminal commands:")
        width = max(map(len, cls.COMMANDS)) + 2
        for name, description in cls.COMMANDS.items():
            print(f"  {name:<{width}}{description}")
        print()

    @classmethod
    def print_secret_commands(cls) -> None:
        print("\nSecret owner-only Discord commands:")
        width = max(map(len, cls.SECRET_COMMANDS)) + 2
        for usage, description in cls.SECRET_COMMANDS.items():
            print(f"  {usage:<{width}}{description}")
        print("  <prefix> means that server's configured prefix (default: ;).")
        print()

    def _read_commands(self) -> None:
        self.print_help()
        while True:
            try:
                command = input("bot> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return

            if not command:
                continue
            if command == "help":
                self.print_help()
                continue
            if command == "secret-commands":
                self.print_secret_commands()
                continue
            if command not in self.COMMANDS:
                print(f"Unknown command: {command!r}. Type 'help' for a list.")
                continue

            bot = self.bot
            if bot is None or bot.runtime_loop is None or bot.runtime_loop.is_closed():
                print("The bot is still starting. Try that command again shortly.")
                continue
            if command == "dm":
                self._run_dm_menu(bot)
                continue
            if command == "reload-cog":
                self._run_reload_cog_menu(bot)
                continue
            asyncio.run_coroutine_threadsafe(
                self._run(command, bot),
                bot.runtime_loop,
            )

    @staticmethod
    def _choose(prompt: str, item_count: int) -> int | None:
        choice = input(prompt).strip().lower()
        if choice in {"cancel", "back", "q", "quit"}:
            return None
        try:
            index = int(choice) - 1
        except ValueError:
            print("Enter one of the displayed numbers, or type 'cancel'.")
            return None
        if not 0 <= index < item_count:
            print("That number is not in the list.")
            return None
        return index

    def _submit(self, bot: Bot, coroutine):
        if bot.runtime_loop is None:
            raise RuntimeError("The bot is not running yet")
        return asyncio.run_coroutine_threadsafe(coroutine, bot.runtime_loop).result()

    async def _dm_targets(
        self,
        bot: Bot,
    ) -> tuple[list[discord.Guild], list[discord.DMChannel]]:
        servers = sorted(bot.guilds, key=lambda guild: guild.name.casefold())
        dm_channels = sorted(
            (
                channel
                for channel in bot.private_channels
                if isinstance(channel, discord.DMChannel) and channel.recipient is not None
            ),
            key=lambda channel: str(channel.recipient).casefold(),
        )
        return servers, dm_channels

    def _run_dm_menu(self, bot: Bot) -> None:
        self._run_dm_once(bot)

    def _run_reload_cog_menu(self, bot: Bot) -> None:
        if not bot.is_ready():
            print("The bot is not ready yet. Try again after it connects.")
            return
        loaded = [
            name for name in COG_NAMES if f"src.cogs.{name}" in bot.extensions
        ]
        choices = ["all", *loaded]
        print("\nLoaded cogs:")
        for index, name in enumerate(choices, 1):
            print(f"  {index}. {name.replace('_', ' ').title()}")
        selected = self._choose(
            "Choose a cog, or type 'cancel': ", len(choices)
        )
        if selected is None:
            print("Cog reload cancelled.")
            return
        cog_name = choices[selected]
        print(f"Reloading {cog_name.replace('_', ' ').title()}...")
        try:
            commands_changed = self._submit(
                bot, self._reload_cogs(bot, cog_name)
            )
        except Exception as error:
            error_id = uuid.uuid4().hex[:8]
            logger.exception(
                "Terminal cog reload failed for %s [%s]", cog_name, error_id
            )
            error_text = str(error).strip() or error.__class__.__name__
            try:
                self._submit(
                    bot,
                    bot.notify_operations_channel(
                        "Terminal Cog Reload Failed",
                        f"**Cog:** `{cog_name}`\n"
                        f"**Error ID:** `{error_id}`\n"
                        f"**Type:** `{error.__class__.__name__}`\n\n"
                        f"```\n{error_text[:1500]}\n```",
                        status="error",
                    ),
                )
            except Exception:
                logger.exception("Could not send terminal reload failure notice")
            print(
                f"Failed to reload {cog_name}. Error ID: {error_id}. "
                "The operations channel was notified."
            )
            return
        sync_note = (
            " Discord commands were synced because they changed."
            if commands_changed
            else " No Discord command sync was needed."
        )
        print(f"Successfully reloaded {cog_name}.{sync_note}")

    @staticmethod
    async def _reload_cogs(bot: Bot, selected: str) -> bool:
        if selected == "all":
            cog_names = tuple(name for name in COG_NAMES if name != "core") + (
                "core",
            )
        else:
            cog_names = (selected,)
            if selected == "economy":
                cog_names = ("economy", "gambling", "fun")
        command_tree_before = [
            command.to_dict(bot.tree) for command in bot.tree.get_commands()
        ]
        if "lookup" in cog_names:
            member_cache_service = importlib.import_module(
                "src.services.member_cache"
            )
            importlib.reload(member_cache_service)
        if "economy" in cog_names:
            economy_service = importlib.import_module(
                "src.services.economy"
            )
            importlib.reload(economy_service)
        for cog_name in cog_names:
            await bot.reload_extension(f"src.cogs.{cog_name}")
        bot.organize_owner_commands()
        command_tree_after = [
            command.to_dict(bot.tree) for command in bot.tree.get_commands()
        ]
        commands_changed = command_tree_before != command_tree_after
        if commands_changed:
            await bot.tree.sync()
        if "dm_watch" in cog_names:
            await bot.wait_for_linked_accounts()
        return commands_changed

    def _run_dm_once(self, bot: Bot) -> bool:
        if not bot.is_ready():
            print("The bot is not ready yet. Try again after it connects.")
            return False
        try:
            servers, dm_channels = self._submit(bot, self._dm_targets(bot))
            print("\nMessage destination:")
            print(f"  1. Server channel ({len(servers)} servers)")
            print(f"  2. Known DM user ({len(dm_channels)} users)")
            destination = self._choose("Choose 1-2, or 'cancel': ", 2)
            if destination is None:
                return False

            target: discord.abc.Messageable | None = None
            target_name = ""
            if destination == 0:
                if not servers:
                    print("The bot is not currently in any servers.")
                    return False
                print("\nServers:")
                for index, guild in enumerate(servers, 1):
                    print(f"  {index}. {guild.name} ({guild.id})")
                server_index = self._choose("Choose a server: ", len(servers))
                if server_index is None:
                    return False
                guild = servers[server_index]
                print(f"\nMessage someone or a channel in {guild.name}:")
                print("  1. Channel")
                print("  2. Member")
                server_target = self._choose("Choose 1-2, or 'cancel': ", 2)
                if server_target is None:
                    return False

                if server_target == 0:
                    channels = [
                        channel
                        for channel in guild.text_channels
                        if guild.me is not None
                        and channel.permissions_for(guild.me).view_channel
                        and channel.permissions_for(guild.me).send_messages
                    ]
                    if not channels:
                        print("The bot cannot send messages in any text channel there.")
                        return False
                    print(f"\nMessageable channels in {guild.name}:")
                    for index, channel in enumerate(channels, 1):
                        print(f"  {index}. #{channel.name}")
                    channel_index = self._choose("Choose a channel: ", len(channels))
                    if channel_index is None:
                        return False
                    target = channels[channel_index]
                    target_name = f"#{target.name} in {guild.name}"
                else:
                    members = sorted(
                        (member for member in guild.members if not member.bot),
                        key=lambda member: member.display_name.casefold(),
                    )
                    if not members:
                        print(
                            "No members are available. Enable the Members Intent "
                            "for this bot if the server member list is missing."
                        )
                        return False
                    print(f"\nMembers in {guild.name}:")
                    for index, member in enumerate(members, 1):
                        print(
                            f"  {index}. {member.display_name} "
                            f"(@{member.name}, {member.id})"
                        )
                    member_index = self._choose("Choose a member: ", len(members))
                    if member_index is None:
                        return False
                    target = members[member_index]
                    target_name = f"{target} from {guild.name}"
            else:
                if not dm_channels:
                    print(
                        "No known DM users are available. Discord does not provide "
                        "bots with a complete list of user-app installations."
                    )
                    return False
                print("\nKnown DM users:")
                for index, channel in enumerate(dm_channels, 1):
                    print(f"  {index}. {channel.recipient} ({channel.recipient.id})")
                user_index = self._choose("Choose a user: ", len(dm_channels))
                if user_index is None:
                    return False
                target = dm_channels[user_index]
                target_name = str(target.recipient)

            print(f"\nSending to {target_name}. Type 'cancel' when finished.")
            while True:
                message = input("Message: ").strip()
                if message.lower() == "cancel":
                    print("Message menu closed.")
                    return False
                if not message:
                    print("Enter a message, or type 'cancel'.")
                    continue
                self._submit(bot, target.send(message))
                print(f"Message sent to {target_name}.")
        except (discord.Forbidden, discord.HTTPException) as error:
            print(f"Discord could not send that message: {error}")
            return False
        except Exception:
            logger.exception("Terminal DM command failed")
            print("The message menu failed. Check the error above.")
            return False

    async def _run(self, command: str, bot: Bot) -> None:
        if command == "discord-commands":
            command_rows: list[tuple[str, str]] = []
            for discord_command in bot.tree.walk_commands():
                if isinstance(discord_command, app_commands.Group):
                    continue
                if isinstance(discord_command, app_commands.ContextMenu):
                    usage = f"Context menu: {discord_command.name}"
                    description = "Right-click command"
                else:
                    usage = f"/{discord_command.qualified_name}"
                    description = (
                        getattr(discord_command, "description", None)
                        or "No description provided."
                    )
                command_rows.append((usage, description))

            command_rows.sort(key=lambda row: row[0].casefold())
            print(f"\nLoaded Discord commands ({len(command_rows)}):")
            for usage, description in command_rows:
                print(f"  {usage:<28} {description}")
            print()
        elif command == "status":
            state = "ready" if bot.is_ready() else "connecting"
            latency = f"{bot.latency * 1000:.0f} ms" if bot.is_ready() else "n/a"
            print(
                f"Bot status: {state} | Servers: {len(bot.guilds)} | "
                f"Latency: {latency}"
            )
        elif command == "sync":
            print("Syncing Discord commands...")
            try:
                await bot.sync_commands()
            except Exception:
                logger.exception("Terminal command sync failed")
            else:
                print("Discord commands synced successfully.")
        elif command == "restart":
            if os.getenv("BOT_RUNNER") != "run.bat":
                print(
                    "Full restart requires run.bat. Type 'stop', then launch "
                    ".\\run.bat instead of 'python -m src.main'."
                )
                return
            print("Restarting bot...")
            bot.restart_requested = True
            bot.shutdown_requested = True
            await bot.close()
        elif command == "stop":
            print("Stopping bot...")
            bot.shutdown_requested = True
            await bot.close()


def main() -> None:
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN is missing. Add it to the project's .env file.")

    instance_lock = acquire_instance_lock()
    console = ConsoleCommands()
    console.start()
    restart_requested = False
    try:
        bot = Bot()
        console.set_bot(bot)
        try:
            bot.run(TOKEN, log_handler=None)
        except (AttributeError, aiohttp.ClientConnectionError):
            if not bot.shutdown_requested:
                raise
            logger.info("Bot stopped while Discord was reconnecting")
        restart_requested = bot.restart_requested
    finally:
        instance_lock.close()

    if restart_requested:
        logger.info("Restarting bot and reloading project files")
        raise SystemExit(75)


if __name__ == "__main__":
    main()
