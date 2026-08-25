from __future__ import annotations

import asyncio
import importlib
import logging
import os
import platform
import time
import uuid
from pathlib import Path

import discord
import psutil
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPERATIONS_CHANNEL_ID = 1537931239980408854

RELOAD_CHOICES = [
    app_commands.Choice(name="All", value="all"),
    app_commands.Choice(name="Core", value="core"),
    app_commands.Choice(name="Media", value="media"),
    app_commands.Choice(name="Economy", value="economy"),
    app_commands.Choice(name="Gambling", value="gambling"),
    app_commands.Choice(name="Fun", value="fun"),
    app_commands.Choice(name="Polls", value="polls"),
    app_commands.Choice(name="Everyday Tools", value="everyday_tools"),
    app_commands.Choice(name="AI", value="ai"),
    app_commands.Choice(name="Guilds", value="guilds"),
    app_commands.Choice(name="Information", value="information"),
    app_commands.Choice(name="Moderation", value="moderation"),
    app_commands.Choice(name="Logging", value="logging"),
    app_commands.Choice(name="Lookup", value="lookup"),
    app_commands.Choice(name="Help", value="help"),
    app_commands.Choice(name="Utility", value="utility"),
    app_commands.Choice(name="Settings", value="settings"),
    app_commands.Choice(name="DM Watch", value="dm_watch"),
]
CLEARANCE_CHOICES = [
    app_commands.Choice(name="Lookup", value="lookup"),
    app_commands.Choice(name="AI", value="ai"),
    app_commands.Choice(name="Owner Commands", value="owner"),
    app_commands.Choice(name="Jishaku", value="jishaku"),
]
CLEARANCE_RANKS = {choice.value: index for index, choice in enumerate(CLEARANCE_CHOICES)}
CLEARANCE_NAMES = {choice.value: choice.name for choice in CLEARANCE_CHOICES}

RELOAD_ORDER = (
    "media",
    "economy",
    "gambling",
    "fun",
    "polls",
    "utility",
    "everyday_tools",
    "ai",
    "help",
    "guilds",
    "information",
    "moderation",
    "logging",
    "lookup",
    "settings",
    "dm_watch",
)


def format_bytes(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{amount:.1f} TiB"


def readable_duration(seconds: int) -> str:
    parts: list[str] = []
    for size, name in (
        (86400, "day"),
        (3600, "hour"),
        (60, "minute"),
        (1, "second"),
    ):
        amount, seconds = divmod(seconds, size)
        if amount:
            parts.append(f"{amount:,} {name}{'' if amount == 1 else 's'}")
        if len(parts) == 2:
            break
    return ", ".join(parts) or "0 seconds"


def directory_size(path: Path) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for filename in files:
            try:
                total += (Path(root) / filename).stat().st_size
            except OSError:
                continue
    return total


def application_command_count(commands_to_count: list[app_commands.Command | app_commands.Group]) -> int:
    total = 0
    for command in commands_to_count:
        children = getattr(command, "commands", None)
        total += application_command_count(list(children)) if children else 1
    return total


def usage_bar(percent: float, width: int = 10) -> str:
    filled = max(0, min(width, round(percent / 100 * width)))
    return "▰" * filled + "▱" * (width - filled)


class BotInfoPageSelect(discord.ui.Select):
    def __init__(self, menu: "BotInfoPaginator") -> None:
        self.menu = menu
        super().__init__(
            placeholder="Choose an information page",
            options=[
                discord.SelectOption(
                    label=title,
                    value=str(index),
                    default=index == menu.current_page,
                )
                for index, (title, _) in enumerate(menu.pages)
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.menu.current_page = int(self.values[0])
        self.menu.render_page()
        await interaction.response.edit_message(view=self.menu)


class BotInfoPaginator(discord.ui.LayoutView):
    navigation = discord.ui.ActionRow()

    def __init__(
        self,
        *,
        author_id: int,
        pages: list[tuple[str, str]],
        thumbnail_url: str | None,
        guild_invite_url: str | None,
        user_install_url: str | None,
    ) -> None:
        super().__init__(timeout=180)
        self.author_id = author_id
        self.pages = pages
        self.thumbnail_url = thumbnail_url
        self.guild_invite_url = guild_invite_url
        self.user_install_url = user_install_url
        self.current_page = 0
        self.message: discord.Message | None = None
        self.render_page()

    def render_page(self) -> None:
        self.clear_items()
        title, body = self.pages[self.current_page]
        heading: discord.ui.Item
        if self.thumbnail_url:
            heading = discord.ui.Section(
                discord.ui.TextDisplay(f"## {title}"),
                accessory=discord.ui.Thumbnail(
                    self.thumbnail_url,
                    description="Bot avatar",
                ),
            )
        else:
            heading = discord.ui.TextDisplay(f"## {title}")
        self.previous.disabled = self.current_page == 0
        self.next.disabled = self.current_page == len(self.pages) - 1
        self.add_item(
            discord.ui.Container(
                heading,
                discord.ui.Separator(),
                discord.ui.TextDisplay(body),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"-# {title} · Page {self.current_page + 1} of {len(self.pages)}"
                ),
                discord.ui.ActionRow(BotInfoPageSelect(self)),
                self.navigation,
                *(
                    (
                        discord.ui.ActionRow(
                            *(
                                [
                                    discord.ui.Button(
                                        label="Add to Server",
                                        style=discord.ButtonStyle.link,
                                        url=self.guild_invite_url,
                                    )
                                ]
                                if self.guild_invite_url
                                else []
                            ),
                            *(
                                [
                                    discord.ui.Button(
                                        label="Install for Yourself",
                                        style=discord.ButtonStyle.link,
                                        url=self.user_install_url,
                                    )
                                ]
                                if self.user_install_url
                                else []
                            ),
                        ),
                    )
                    if self.guild_invite_url or self.user_install_url
                    else ()
                ),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This bot information menu belongs to someone else.",
            ephemeral=True,
        )
        return False

    async def on_timeout(self) -> None:
        self.previous.disabled = True
        self.next.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @navigation.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self.current_page -= 1
        self.render_page()
        await interaction.response.edit_message(view=self)

    @navigation.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self.current_page += 1
        self.render_page()
        await interaction.response.edit_message(view=self)


class Core(commands.Cog):
    """Bot administration and runtime-health commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._resource_cache: tuple[float, dict[str, int | float]] | None = None
        self._resource_lock = asyncio.Lock()

    async def _notify_operations(
        self,
        title: str,
        details: str,
        *,
        status: str = "info",
    ) -> None:
        notifier = getattr(self.bot, "notify_operations_channel", None)
        if callable(notifier):
            await notifier(title, details, status=status)
            return
        try:
            channel = self.bot.get_channel(OPERATIONS_CHANNEL_ID)
            if channel is None:
                channel = await self.bot.fetch_channel(OPERATIONS_CHANNEL_ID)
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

    async def _resource_snapshot(self) -> dict[str, int | float]:
        now = time.monotonic()
        if self._resource_cache is not None and now - self._resource_cache[0] < 15:
            return self._resource_cache[1]

        async with self._resource_lock:
            now = time.monotonic()
            if self._resource_cache is not None and now - self._resource_cache[0] < 15:
                return self._resource_cache[1]

            def collect() -> dict[str, int | float]:
                process = psutil.Process()
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage(str(PROJECT_ROOT))
                return {
                    "process_memory": process.memory_info().rss,
                    "process_cpu": process.cpu_percent(interval=0.1),
                    "system_cpu": psutil.cpu_percent(interval=None),
                    "threads": process.num_threads(),
                    "system_memory_total": memory.total,
                    "system_memory_used": memory.used,
                    "system_memory_available": memory.available,
                    "system_memory_percent": memory.percent,
                    "disk_total": disk.total,
                    "disk_used": disk.used,
                    "disk_free": disk.free,
                    "disk_percent": disk.percent,
                    "bot_size": directory_size(PROJECT_ROOT),
                    "cache_size": directory_size(PROJECT_ROOT / ".cache"),
                    "system_boot": int(psutil.boot_time()),
                }

            snapshot = await asyncio.to_thread(collect)
            self._resource_cache = (time.monotonic(), snapshot)
            return snapshot

    async def _lookup_allowlist_owner_check(
        self, interaction: discord.Interaction
    ) -> bool:
        if await self.bot.is_primary_owner(interaction.user):
            return True
        await interaction.response.send_message(
            "Only the bot owner can manage lookup access.", ephemeral=True
        )
        return False

    @app_commands.command(
        name="allow",
        description="Grant a command-clearance level to a user",
    )
    @app_commands.describe(user="User to authorize",clearance="Access level to grant")
    @app_commands.choices(clearance=CLEARANCE_CHOICES)
    async def allow(self, interaction: discord.Interaction, user: discord.User, clearance: app_commands.Choice[str]) -> None:
        if not await self._lookup_allowlist_owner_check(interaction):
            return
        if user.bot:
            await interaction.response.send_message(
                "Bots cannot be added to the command allowlist.", ephemeral=True
            )
            return
        existing = self.bot.clearance_for(user.id)
        if existing is not None and CLEARANCE_RANKS[existing] >= CLEARANCE_RANKS[clearance.value]:
            message = (
                f"{user.mention} already has **{CLEARANCE_NAMES[existing]}** clearance, "
                f"which includes **{clearance.name}**."
            )
        else:
            for allowed in self.bot.command_clearances.values():
                allowed.discard(user.id)
            self.bot.command_clearances[clearance.value].add(user.id)
            self.bot.save_allowed_users()
            inherited = [
                choice.name for choice in CLEARANCE_CHOICES
                if CLEARANCE_RANKS[choice.value] < CLEARANCE_RANKS[clearance.value]
            ]
            message = f"Granted {user.mention} **{clearance.name}** clearance."
            if inherited:
                message += " This also includes " + ", ".join(inherited) + "."
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(
        name="disallow", description="Remove a command-clearance level from a user"
    )
    @app_commands.describe(user="User to restrict",clearance="Access level to remove")
    @app_commands.choices(clearance=CLEARANCE_CHOICES)
    async def disallow(
        self, interaction: discord.Interaction, user: discord.User, clearance: app_commands.Choice[str]
    ) -> None:
        if not await self._lookup_allowlist_owner_check(interaction):
            return
        existing = self.bot.clearance_for(user.id)
        if existing is None:
            message = f"{user.mention} does not have any delegated clearance."
        elif existing != clearance.value:
            message = (
                f"{user.mention} is assigned **{CLEARANCE_NAMES[existing]}**, not "
                f"**{clearance.name}**. Remove their assigned level directly."
            )
        else:
            self.bot.command_clearances[existing].remove(user.id)
            self.bot.save_allowed_users()
            message = f"Removed {user.mention}'s **{clearance.name}** clearance."
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(
        name="allowed", description="Show users with restricted command access"
    )
    async def allowed(self, interaction: discord.Interaction) -> None:
        if not await self._lookup_allowlist_owner_check(interaction):
            return
        sections: list[str] = []
        for clearance in CLEARANCE_CHOICES:
            lines: list[str] = []
            for user_id in sorted(self.bot.command_clearances[clearance.value]):
                user = self.bot.get_user(user_id)
                if user is None:
                    try:user = await self.bot.fetch_user(user_id)
                    except (discord.NotFound, discord.HTTPException):user = None
                lines.append(f"{user.mention if user else 'Unknown user'} · `{user_id}`")
            sections.append(f"### {clearance.name}\n"+("\n".join(lines) if lines else "Nobody"))
        body="\n\n".join(sections)
        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                        f"## Restricted Command Access\n{body}\n\n"
                        "-# Hierarchy: Jishaku → Owner Commands → AI → Lookup. Higher levels include every level below them."
                )
            )
        )
        await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(name="reload-cog", description="Reload a cog")
    @app_commands.describe(cog="The cog to reload")
    @app_commands.choices(cog=RELOAD_CHOICES)
    async def reload_cog(
        self,
        interaction: discord.Interaction,
        cog: app_commands.Choice[str],
    ) -> None:
        if not await self.bot.can_use_owner_commands(interaction.user):
            await interaction.response.send_message(
                "Only the bot owner can use this command.",
                ephemeral=True,
            )
            return
        if cog.value == "core":
            await interaction.response.send_message(
                "Core owns the reload command and cannot safely reload itself. "
                "Use `.\\bot restart` from the bot folder instead.",
                ephemeral=True,
            )
            return

        logger.warning(
            "──────── COG RELOAD (%s) requested by %s (ID: %s) ────────",
            cog.name,
            interaction.user,
            interaction.user.id,
        )
        await interaction.response.defer(ephemeral=True)
        cog_names = RELOAD_ORDER if cog.value == "all" else (cog.value,)
        if cog.value == "economy":
            cog_names = ("economy", "gambling", "fun")
        command_tree_before = [
            command.to_dict(self.bot.tree)
            for command in self.bot.tree.get_commands()
        ]
        try:
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
                await self.bot.reload_extension(f"{__package__}.{cog_name}")
            self.bot.organize_owner_commands()
            command_tree_after = [
                command.to_dict(self.bot.tree)
                for command in self.bot.tree.get_commands()
            ]
            commands_changed = command_tree_before != command_tree_after
            if commands_changed:
                await self.bot.tree.sync()
            else:
                logger.info(
                    "COG RELOAD (%s) skipped command sync; command definitions unchanged",
                    cog.name,
                )
        except Exception as error:
            error_id = uuid.uuid4().hex[:8]
            logger.error(
                "COG RELOAD (%s) failed [%s]: %s",
                cog.name,
                error_id,
                error,
                exc_info=True,
            )
            error_text = str(error).strip() or error.__class__.__name__
            error_view = discord.ui.LayoutView()
            error_view.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay(
                        "## Cog Reload Failed\n"
                        f"**Cog:** `{cog.name}`\n"
                        f"**Error ID:** `{error_id}`\n"
                        f"**Type:** `{error.__class__.__name__}`\n\n"
                        "### Error\n"
                        f"```\n{error_text[:1500]}\n```"
                    ),
                    accent_colour=discord.Color.red(),
                )
            )
            await interaction.followup.send(
                view=error_view,
                ephemeral=True,
            )
            await self._notify_operations(
                "Cog Reload Failed",
                f"**Cog:** `{cog.name}`\n"
                f"**Requested by:** {interaction.user} (`{interaction.user.id}`)\n"
                f"**Error ID:** `{error_id}`\n"
                f"**Type:** `{error.__class__.__name__}`\n\n"
                f"```\n{error_text[:1500]}\n```",
                status="error",
            )
            return

        logger.info("COG RELOAD (%s) completed successfully", cog.name)
        if cog.value in {"dm_watch", "all"}:
            await self.bot.wait_for_linked_accounts()
        await self._notify_operations(
            "Cog Reloaded",
            f"**Cog:** {cog.name}\n"
            f"**Requested by:** {interaction.user}\n"
            + (
                "The command tree changed and was synced."
                if commands_changed
                else "Command definitions were unchanged, so no sync was needed."
            ),
            status="success",
        )
        message = f"Successfully reloaded `{cog.name}`."
        await interaction.followup.send(message, ephemeral=True)

    @app_commands.command(
        name="reload",
        description="Restart the bot and reconnect to Discord",
    )
    async def reload_bot(self, interaction: discord.Interaction) -> None:
        if not await self.bot.can_use_owner_commands(interaction.user):
            await interaction.response.send_message(
                "Only the bot owner can use this command.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Restarting the bot now. It should be back online shortly.",
            ephemeral=True,
        )
        logger.warning(
            "──────── BOT RELOAD requested by %s (ID: %s) ────────",
            interaction.user,
            interaction.user.id,
        )
        self.bot.restart_requested = True
        await self.bot.close()

    @commands.hybrid_command(
        name="botinfo",
        aliases=["bi"],
        description="Show the bot's statistics, resources, and runtime information",
    )
    async def botinfo(
        self,
        ctx: commands.Context,
        ephemeral: bool = False,
    ) -> None:
        if ctx.interaction is not None and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(ephemeral=ephemeral, thinking=True)

        started_at = getattr(self.bot, "started_at", discord.utils.utcnow())
        resources = await self._resource_snapshot()
        prefix_commands = sum(1 for _ in self.bot.walk_commands())
        application_commands = application_command_count(
            list(self.bot.tree.get_commands())
        )
        member_placements = sum(
            guild.member_count or 0 for guild in self.bot.guilds
        )
        channel_count = sum(len(guild.channels) for guild in self.bot.guilds)
        uptime_seconds = max(0, int(time.time() - started_at.timestamp()))
        uptime_text = readable_duration(uptime_seconds)
        bot_user = self.bot.user
        try:
            application = getattr(self.bot, "application", None) or await self.bot.application_info()
        except discord.HTTPException:
            application = None
        developer = getattr(application, "owner", None)
        team = getattr(application, "team", None)
        if team is not None:
            developer = getattr(team, "owner", None) or developer
        description = (
            getattr(application, "description", "").strip()
            if application is not None
            else ""
        ) or "A multipurpose Discord bot built for useful tools, media, games, and communities."
        user_installs = getattr(application, "approximate_user_install_count", None)

        category_lines: list[str] = []
        for cog_name, loaded_cog in sorted(self.bot.cogs.items()):
            if cog_name == "Owner" and not await self.bot.can_use_owner_commands(ctx.author):
                continue
            names = {
                command.qualified_name
                for command in loaded_cog.walk_commands()
                if not command.hidden
            }
            pending = list(loaded_cog.get_app_commands())
            while pending:
                command = pending.pop(0)
                children = list(getattr(command, "commands", ()))
                if children:
                    pending.extend(children)
                else:
                    names.add(command.qualified_name)
            if names:
                category_lines.append(f"**{cog_name}:** `{len(names):,}`")

        application_id = self.bot.application_id or (
            bot_user.id if bot_user is not None else None
        )
        guild_invite_url = None
        user_install_url = None
        if application_id is not None:
            guild_invite_url = (
                "https://discord.com/oauth2/authorize?"
                f"client_id={application_id}&scope=bot%20applications.commands"
                "&permissions=8&integration_type=0"
            )
            user_install_url = (
                "https://discord.com/oauth2/authorize?"
                f"client_id={application_id}&scope=applications.commands"
                "&integration_type=1"
            )

        created_timestamp = (
            int(bot_user.created_at.timestamp()) if bot_user is not None else 0
        )
        reach_lines = (
            f"**Servers:** `{len(self.bot.guilds):,}`\n"
            f"**Cached users:** `{len(self.bot.users):,}`\n"
            f"**Member placements:** `{member_placements:,}`\n"
            f"**Channels:** `{channel_count:,}`"
        )
        if user_installs is not None:
            reach_lines += f"\n**User installs:** `{int(user_installs):,}`"

        ram_percent = float(resources["system_memory_percent"])
        disk_percent = float(resources["disk_percent"])
        cpu_percent = float(resources["system_cpu"])
        pages = [
            (
                "Overview",
                f"{description}\n\n"
                "### Status\n"
                f"**Uptime:** `{uptime_text}`\n"
                f"**Latency:** `{round(self.bot.latency * 1000):,} ms`\n"
                f"**Started:** <t:{int(started_at.timestamp())}:R>\n\n"
                "### Identity\n"
                f"**Account:** {bot_user.mention if bot_user else 'Connecting...'}\n"
                f"**Developer:** {developer.mention if developer else 'N/A'}\n"
                f"**Created:** {f'<t:{created_timestamp}:D>' if created_timestamp else 'N/A'}\n"
                f"**Bot ID:** `{bot_user.id if bot_user else 'N/A'}`\n\n"
                "### At a Glance\n"
                f"`{len(self.bot.guilds):,}` servers · `{len(self.bot.users):,}` cached users · "
                f"`{application_commands:,}` application commands",
            ),
            (
                "Reach & Usage",
                f"### Discord Reach\n{reach_lines}\n\n"
                "### Command System\n"
                f"**Application commands:** `{application_commands:,}`\n"
                f"**Prefix commands:** `{prefix_commands:,}`\n"
                f"**Loaded cogs:** `{len(self.bot.cogs):,}`\n"
                f"**Shards:** `{self.bot.shard_count or 1:,}`\n\n"
                "-# Member placements count the same person once in every shared server.",
            ),
            (
                "Commands",
                "### Commands by Category\n"
                + ("\n".join(category_lines) if category_lines else "No categories loaded.")
                + "\n\n-# Hybrid commands are counted once, even when they support both / and the server prefix.",
            ),
            (
                "Hosting",
                "### Current Load\n"
                f"**CPU:** `{cpu_percent:.1f}%`  {usage_bar(cpu_percent)}\n"
                f"**RAM:** `{ram_percent:.1f}%`  {usage_bar(ram_percent)}\n"
                f"`{format_bytes(int(resources['system_memory_used']))}` / "
                f"`{format_bytes(int(resources['system_memory_total']))}`\n"
                f"**Storage:** `{disk_percent:.1f}%`  {usage_bar(disk_percent)}\n"
                f"`{format_bytes(int(resources['disk_used']))}` / "
                f"`{format_bytes(int(resources['disk_total']))}`\n\n"
                "### Bot Footprint\n"
                f"**Process RAM:** `{format_bytes(int(resources['process_memory']))}`\n"
                f"**Process CPU:** `{float(resources['process_cpu']):.1f}%`\n"
                f"**Bot folder:** `{format_bytes(int(resources['bot_size']))}`\n"
                f"**Cache:** `{format_bytes(int(resources['cache_size']))}`",
            ),
            (
                "Runtime",
                "### Software\n"
                f"**Python:** `{platform.python_version()}`\n"
                f"**discord.py:** `{discord.__version__}`\n"
                f"**Operating system:** `{platform.system()} {platform.release()}`\n\n"
                "### Process\n"
                f"**Logical CPU cores:** `{psutil.cpu_count(logical=True) or 0:,}`\n"
                f"**Threads:** `{int(resources['threads']):,}`\n"
                f"**Server started:** <t:{int(resources['system_boot'])}:R>\n"
                f"**Bot connected:** <t:{int(started_at.timestamp())}:R>",
            ),
        ]
        thumbnail_url = (
            str(bot_user.display_avatar.url) if bot_user is not None else None
        )
        view = BotInfoPaginator(
            author_id=ctx.author.id,
            pages=pages,
            thumbnail_url=thumbnail_url,
            guild_invite_url=guild_invite_url,
            user_install_url=user_install_url,
        )
        view.message = await ctx.send(view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Core(bot))
