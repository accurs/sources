from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from src.cogs.owner import owner_clearance

from src.services.user_account import UserAccountClient
from src.services.member_cache import MemberCache

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MEMBER_CACHE_FILE = PROJECT_ROOT / ".cache" / "linked_users.db"
logger = logging.getLogger(__name__)
LOADING_EMOJI = os.getenv("LOADING_EMOJI", "⏳").strip() or "⏳"


BADGE_EMOJI_NAMES = {
    "staff": "staff",
    "partner": "partner",
    "hypesquad": "hypesquad",
    "hypesquad_house_1": "bravery",
    "hypesquad_house_2": "brilliance",
    "hypesquad_house_3": "balance",
    "bug_hunter_level_1": "bug_hunter",
    "bug_hunter_level_2": "gold_bug_hunter",
    "premium_early_supporter": "early_supporter",
    "verified_developer": "early_developer",
    "certified_moderator": "moderator",
    "active_developer": "active_developer",
    "quest_completed": "quest",
    "legacy_username": "legacy_username",
    "supports_commands": "commands",
}


def _badge_emoji_names(
    badge_id: str,
) -> tuple[str, str]:
    safe_id = re.sub(r"[^a-z0-9_]", "_", badge_id.casefold())
    legacy_name = "badge_" + safe_id[:25]
    name = BADGE_EMOJI_NAMES.get(badge_id)
    if name is None:
        tenure = re.fullmatch(r"premium_tenure_(\d+)_month(?:_v\d*)?", badge_id)
        booster = re.fullmatch(r"guild_booster_lvl(\d+)", badge_id)
        april = re.fullmatch(r"april_fools_(\d{4})", badge_id)
        if tenure:
            months = int(tenure.group(1))
            name = f"nitro_{months // 12}y" if months % 12 == 0 else f"nitro_{months}m"
        elif booster:
            name = f"booster_lvl{booster.group(1)}"
        elif april:
            name = f"april_fools_{april.group(1)[2:]}"
        else:
            name = safe_id[:32]
    return name[:32], legacy_name


def _profile_badges(profile: dict) -> list[dict]:
    """Collect normal and experimental badge objects from a profile payload."""
    found: list[dict] = []

    def collect(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                collect(item)
            return
        if not isinstance(value, dict):
            return
        if value.get("icon") and (value.get("id") or value.get("description")):
            found.append(value)
            return
        for nested_key, nested_value in value.items():
            if "badge" in str(nested_key).casefold() or isinstance(
                nested_value, (list, dict)
            ):
                collect(nested_value)

    for key, value in profile.items():
        if "badge" in str(key).casefold():
            collect(value)
    user_profile = profile.get("user_profile")
    if isinstance(user_profile, dict):
        for key, value in user_profile.items():
            if "badge" in str(key).casefold():
                collect(value)

    unique: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for badge in found:
        identity = (str(badge.get("id") or ""), str(badge.get("icon") or ""))
        if identity not in seen:
            seen.add(identity)
            unique.append(badge)
    return unique


@dataclass(slots=True)
class LinkedProfileUser:
    id: int
    name: str
    display_name: str
    avatar_url: str
    bot: bool

    @property
    def created_at(self):
        return discord.utils.snowflake_time(self.id)

    @classmethod
    def from_profile(
        cls,
        data: dict,
        fallback_id: int,
    ) -> LinkedProfileUser:
        try:
            user_id = int(data.get("id", fallback_id))
        except (TypeError, ValueError):
            user_id = fallback_id

        username = str(data.get("username") or "Unknown")
        display_name = str(data.get("global_name") or username)
        avatar_hash = data.get("avatar")
        if avatar_hash:
            extension = "gif" if str(avatar_hash).startswith("a_") else "png"
            avatar_url = (
                f"https://cdn.discordapp.com/avatars/{user_id}/"
                f"{avatar_hash}.{extension}?size=1024"
            )
        else:
            avatar_url = (
                f"https://cdn.discordapp.com/embed/avatars/{(user_id >> 22) % 6}.png"
            )
        return cls(
            id=user_id,
            name=username,
            display_name=display_name,
            avatar_url=avatar_url,
            bot=bool(data.get("bot", False)),
        )


def _split_lines(lines: list[str], limit: int = 3500) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    for line in lines:
        added_length = len(line) + (1 if current else 0)
        if current and current_length + added_length > limit:
            chunks.append("\n".join(current))
            current = []
            current_length = 0
        current.append(line)
        current_length += added_length

    if current:
        chunks.append("\n".join(current))
    return chunks


def _escape_link_label(value: str) -> str:
    return discord.utils.escape_markdown(value).replace("]", r"\]")


class MutualGuildView(discord.ui.LayoutView):
    actions = discord.ui.ActionRow()

    def __init__(
        self,
        *,
        author_id: int,
        profile_user_id: int,
        guild_entries: list[tuple[str, str]],
        details_text: str,
        container_items: list[discord.ui.Item],
    ) -> None:
        super().__init__(timeout=180)
        self.author_id = author_id
        self.guild_entries = guild_entries
        self.details_text = details_text
        self.message: discord.Message | None = None
        if not guild_entries:
            self.show_guilds.disabled = True
            self.show_guilds.label = "No Mutual Servers"
        self.actions.add_item(
            discord.ui.Button(
                label="View Profile",
                url=f"https://discord.com/users/{profile_user_id}",
            )
        )
        self.clear_items()
        self.add_item(
            discord.ui.Container(
                *container_items,
                self.actions,
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This guild list belongs to someone else.",
            ephemeral=True,
        )
        return False

    async def on_timeout(self) -> None:
        self.show_guilds.disabled = True
        self.profile_details.disabled = True
        if self.guild_entries:
            self.show_guilds.label = "Guilds (Expired)"
        self.profile_details.label = "Details (Expired)"
        if self.message is None:
            return
        try:
            await self.message.edit(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass

    async def _build_guild_lines(self) -> list[str]:
        return [
            (
                f"• [{_escape_link_label(name)}]"
                f"(https://discord.com/channels/{guild_id}) "
                f"• Open Server • `{guild_id}`"
            )
            for name, guild_id in self.guild_entries
        ]

    @actions.button(label="Details", emoji="📋", style=discord.ButtonStyle.secondary)
    async def profile_details(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        view = discord.ui.LayoutView(timeout=180)
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("## Profile Details"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(self.details_text),
            )
        )
        await interaction.response.send_message(view=view, ephemeral=True)

    @actions.button(
        label="Guilds",
        emoji="🌐",
        style=discord.ButtonStyle.secondary,
    )
    async def show_guilds(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_lines = await self._build_guild_lines()
        private_view = MutualGuildPaginator(
            guild_lines=guild_lines,
            author_id=self.author_id,
        )
        private_view.message = await interaction.followup.send(
            view=private_view,
            ephemeral=True,
            wait=True,
        )


class MutualGuildPaginator(discord.ui.LayoutView):
    navigation = discord.ui.ActionRow()

    def __init__(
        self,
        *,
        guild_lines: list[str],
        author_id: int,
    ) -> None:
        super().__init__(timeout=180)
        self.guild_lines = guild_lines
        self.author_id = author_id
        self.pages = _split_lines(guild_lines, limit=3000) or [
            "No mutual servers found."
        ]
        self.current_page = 0
        self.message: discord.WebhookMessage | None = None
        self.render_page()

    def render_page(self) -> None:
        self.clear_items()
        self.previous.disabled = self.current_page == 0
        self.next.disabled = self.current_page >= len(self.pages) - 1
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Mutual Servers\n"
                    f"Found **{len(self.guild_lines)}** shared server(s)."
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(self.pages[self.current_page]),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"Page {self.current_page + 1} of {len(self.pages)}"
                ),
                self.navigation,
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This invite list belongs to someone else.",
            ephemeral=True,
        )
        return False

    async def on_timeout(self) -> None:
        self.previous.disabled = True
        self.next.disabled = True
        if self.message is None:
            return
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


class AccountGuildPaginator(discord.ui.LayoutView):
    navigation = discord.ui.ActionRow()

    def __init__(
        self,
        *,
        guilds: list[dict],
        author_id: int,
    ) -> None:
        super().__init__(timeout=180)
        self.guilds = guilds
        self.author_id = author_id
        self.current_page = 0
        self.page_size = 8
        self.message: discord.Message | None = None
        self.render_page()

    @property
    def page_count(self) -> int:
        return max((len(self.guilds) + self.page_size - 1) // self.page_size, 1)

    def render_page(self) -> None:
        self.clear_items()
        start = self.current_page * self.page_size
        page_guilds = self.guilds[start : start + self.page_size]
        lines = []
        for index, guild in enumerate(page_guilds, start=start + 1):
            guild_id = str(guild.get("id", "Unknown"))
            name = str(guild.get("name", "Unknown Server"))
            safe_name = _escape_link_label(name)
            member_count = guild.get("approximate_member_count")
            online_count = guild.get("approximate_presence_count")
            counts = (
                f"{member_count:,} members • {online_count:,} online"
                if isinstance(member_count, int) and isinstance(online_count, int)
                else "Counts unavailable"
            )
            owner = " • Owner" if guild.get("owner") else ""
            lines.append(
                f"`{index}.` [{safe_name}]"
                f"(https://discord.com/channels/{guild_id})"
                f"{owner}\n`{guild_id}` • {counts}"
            )

        self.previous.disabled = self.current_page == 0
        self.next.disabled = self.current_page >= self.page_count - 1
        content = "\n\n".join(lines) if lines else "No servers found."
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"## Linked Account Servers — {len(self.guilds)}\n{content}"
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"Page {self.current_page + 1} of {self.page_count}"
                ),
                self.navigation,
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This server list belongs to someone else.",
            ephemeral=True,
        )
        return False

    async def on_timeout(self) -> None:
        self.previous.disabled = True
        self.next.disabled = True
        if self.message is None:
            return
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


class UsernameLengthPaginator(discord.ui.LayoutView):
    navigation = discord.ui.ActionRow()

    def __init__(
        self,
        *,
        member_cache: MemberCache,
        minimum: int,
        maximum: int,
        total: int,
        author_id: int,
    ) -> None:
        super().__init__(timeout=180)
        self.member_cache = member_cache
        self.minimum = minimum
        self.maximum = maximum
        self.total = total
        self.author_id = author_id
        self.current_page = 0
        self.page_size = 15
        self.message: discord.Message | None = None
        self.render_page()

    @property
    def page_count(self) -> int:
        return max((self.total + self.page_size - 1) // self.page_size, 1)

    def render_page(self) -> None:
        self.clear_items()
        users = self.member_cache.usernames_by_length(
            self.minimum,
            self.maximum,
            limit=self.page_size,
            offset=self.current_page * self.page_size,
        )
        start = self.current_page * self.page_size
        lines = []
        for index, user in enumerate(users, start=start + 1):
            username = discord.utils.escape_markdown(str(user["username"]))
            user_id = int(user["user_id"])
            shared = int(user["shared_servers"] or 0)
            lines.append(
                f"`{index}.` **{username}** · `{len(str(user['username']))}` characters\n"
                f"`{user_id}` · `{shared:,}` shared server{'s' if shared != 1 else ''}"
            )

        length_label = (
            str(self.minimum)
            if self.minimum == self.maximum
            else f"{self.minimum}-{self.maximum}"
        )
        self.previous.disabled = self.current_page == 0
        self.next.disabled = self.current_page >= self.page_count - 1
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"## Cached Usernames · {length_label} Characters\n"
                    + (
                        "\n\n".join(lines)
                        if lines
                        else "No cached usernames found."
                    )
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"Page `{self.current_page + 1}` of `{self.page_count}` · "
                    f"`{self.total:,}` result{'s' if self.total != 1 else ''}"
                ),
                self.navigation,
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This username list belongs to someone else.", ephemeral=True
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
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.current_page -= 1
        self.render_page()
        await interaction.response.edit_message(view=self)

    @navigation.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.current_page += 1
        self.render_page()
        await interaction.response.edit_message(view=self)


class Lookup(commands.Cog):
    linked_account = app_commands.Group(
        name="linked-account",
        description="Manage the linked Discord account data",
    )
    recache = app_commands.Group(
        name="recache",
        description="Manage the linked-account member cache",
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.account = UserAccountClient()
        self.member_cache = MemberCache(MEMBER_CACHE_FILE)
        self._relationship_users: list[dict] = []
        # SQLite is the source of truth. Loading hundreds of thousands of
        # users here blocks Discord heartbeats whenever this cog is reloaded.
        self._known_users: dict[str, dict] = {}
        self._selfcord_guild_cursor = 0
        self._member_cache_task: asyncio.Task | None = None
        self._last_cache_failures: list[tuple[str, int, str, int]] = []
        self._badge_emoji_lock = asyncio.Lock()
        # Refresh after a cog reload so emojis added in the Developer Portal or
        # by the setup process are discovered instead of duplicated.
        bot._application_badge_emojis = None

    async def cog_load(self) -> None:
        await asyncio.to_thread(self.member_cache.rebuild_search_index)

    async def cog_unload(self) -> None:
        if self._member_cache_task is not None:
            self._member_cache_task.cancel()
            await asyncio.gather(self._member_cache_task, return_exceptions=True)
            self._member_cache_task = None

    async def _badge_emoji(self, badge: dict) -> str | None:
        badge_id = str(badge.get("id") or "").strip().casefold()
        icon_hash = str(badge.get("icon") or "").strip()
        if not badge_id or not icon_hash:
            return None
        emoji_name, legacy_name = _badge_emoji_names(
            badge_id,
        )

        async with self._badge_emoji_lock:
            emoji_cache = getattr(self.bot, "_application_badge_emojis", None)
            if emoji_cache is None:
                try:
                    emojis = await self.bot.fetch_application_emojis()
                except discord.HTTPException:
                    logger.warning("Could not load application badge emojis", exc_info=True)
                    return None
                emoji_cache = {emoji.name: emoji for emoji in emojis}
                self.bot._application_badge_emojis = emoji_cache

            existing = emoji_cache.get(emoji_name)
            if existing is not None:
                return str(existing)

            legacy = emoji_cache.get(legacy_name)
            booster_match = re.fullmatch(r"guild_booster_lvl(\d+)", badge_id)
            if legacy is None and booster_match:
                legacy_name = f"booster_{booster_match.group(1)}"
                legacy = emoji_cache.get(legacy_name)
            if legacy is not None and legacy_name != emoji_name:
                try:
                    renamed = await legacy.edit(name=emoji_name)
                except discord.HTTPException:
                    logger.warning(
                        "Could not rename badge emoji %s to %s",
                        legacy_name,
                        emoji_name,
                        exc_info=True,
                    )
                    return str(legacy)
                emoji_cache.pop(legacy_name, None)
                emoji_cache[emoji_name] = renamed
                logger.info(
                    "Renamed application badge emoji %s to %s",
                    legacy_name,
                    emoji_name,
                )
                return str(renamed)

            url = f"https://cdn.discordapp.com/badge-icons/{icon_hash}.png?size=128"
            timeout = aiohttp.ClientTimeout(total=10)
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as response:
                        response.raise_for_status()
                        image = await response.read()
                emoji = await self.bot.create_application_emoji(
                    name=emoji_name,
                    image=image,
                )
            except (aiohttp.ClientError, TimeoutError, discord.HTTPException):
                logger.warning(
                    "Could not create application emoji for badge %s",
                    badge_id,
                    exc_info=True,
                )
                return None
            emoji_cache[emoji_name] = emoji
            logger.info("Created application badge emoji %s", emoji_name)
            return str(emoji)

    async def _refresh_linked_member_cache(
        self,
        retry_failures: list[tuple[str, int, str, int]] | None = None,
    ) -> bool:
        """Progressively cache members visible to linked Selfcord clients."""
        run_id: int | None = None
        processed = 0
        updated = 0
        failure_map = {
            guild_id: (name, guild_id, reason, visible_members)
            for name, guild_id, reason, visible_members in (retry_failures or [])
        }
        self._last_cache_failures = list(failure_map.values())
        try:
            clients = []
            for _ in range(120):
                dm_watch = self.bot.get_cog("DMWatch")
                all_clients = getattr(dm_watch, "_user_clients", [])
                clients = [client for client in all_clients if client.is_ready()]
                if clients and len(clients) == len(all_clients):
                    break
                await asyncio.sleep(0.5)
            if not clients:
                logger.warning("Linked member cache skipped: no Selfcord clients ready.")
                return False

            guilds = {}
            for client in clients:
                for guild in client.guilds:
                    guilds.setdefault(guild.id, guild)

            if retry_failures is not None:
                retry_ids = set(failure_map)
                guilds = {
                    guild_id: guild
                    for guild_id, guild in guilds.items()
                    if guild_id in retry_ids
                }
                total_guilds = len(retry_ids)
            else:
                failure_map.clear()
                total_guilds = len(guilds)

            logger.info(
                "%s linked member cache for %d server(s)",
                "Retrying" if retry_failures is not None else "Refreshing",
                total_guilds,
            )
            run_id = await asyncio.to_thread(
                self.member_cache.start_run,
                total_guilds,
            )
            for index, guild in enumerate(guilds.values(), start=1):
                # A successful retry removes the previous failure. If this
                # attempt fails, the entry is replaced with the current reason.
                failure_map.pop(guild.id, None)
                members = list(guild.members)
                try:
                    scraped = await asyncio.wait_for(
                        guild.fetch_members(
                            cache=True,
                            force_scraping=True,
                            delay=0.35,
                        ),
                        timeout=120,
                    )
                    if scraped:
                        members_by_id = {member.id: member for member in members}
                        members_by_id.update(
                            {member.id: member for member in scraped}
                        )
                        members = list(members_by_id.values())
                except asyncio.CancelledError:
                    raise
                except TimeoutError:
                    failure_map[guild.id] = (
                        guild.name,
                        guild.id,
                        "Scan timed out after 2 minutes",
                        len(guild.members),
                    )
                    logger.warning(
                        "Member scan timed out for %s (%s); saving the %d "
                        "members found so far.",
                        guild.name,
                        guild.id,
                        len(guild.members),
                    )
                except Exception as error:
                    reason = str(error).strip() or type(error).__name__
                    failure_map[guild.id] = (
                        guild.name,
                        guild.id,
                        reason[:300],
                        len(guild.members),
                    )
                    logger.warning(
                        "Could not scan the full member sidebar for %s (%s); "
                        "saving members already visible.",
                        guild.name,
                        guild.id,
                    )

                # Scraping may cache useful partial results before timing out.
                members_by_id = {member.id: member for member in members}
                members_by_id.update(
                    {member.id: member for member in guild.members}
                )
                members = list(members_by_id.values())

                records: list[dict] = []
                for member in members:
                    user_id = str(member.id)
                    data = {
                        "id": user_id,
                        "username": member.name,
                        "global_name": member.global_name,
                        "nick": member.nick,
                        "discriminator": str(member.discriminator or "0"),
                        "bot": bool(member.bot),
                    }
                    records.append(data)
                    if member.bot:
                        self._known_users.pop(user_id, None)
                        continue
                    if self._known_users.get(user_id) != data:
                        self._known_users[user_id] = data
                        updated += 1
                await asyncio.to_thread(
                    self.member_cache.upsert_guild_members,
                    guild.id,
                    records,
                )
                processed = index

                logger.info(
                    "Member cache progress: %d/%d server(s), %d user(s) updated",
                    index,
                    total_guilds,
                    updated,
                )
                await asyncio.sleep(1.5)

            self._last_cache_failures = list(failure_map.values())
            await asyncio.to_thread(
                self.member_cache.replace_failures,
                self._last_cache_failures,
            )
            failed = len(self._last_cache_failures)

            logger.info(
                "Linked member cache pass finished: %d known user(s)",
                await asyncio.to_thread(self.member_cache.count_users),
            )
            await asyncio.to_thread(
                self.member_cache.rebuild_search_index,
                force=True,
            )
            if run_id is not None:
                await asyncio.to_thread(
                    self.member_cache.finish_run,
                    run_id,
                    processed=processed,
                    failed=failed,
                    updated=updated,
                    status="partial" if failed else "complete",
                )
            return True
        except asyncio.CancelledError:
            failed = len(failure_map)
            if run_id is not None:
                await asyncio.to_thread(
                    self.member_cache.finish_run,
                    run_id,
                    processed=processed,
                    failed=failed,
                    updated=updated,
                    status="cancelled",
                )
            raise
        except Exception:
            failed = len(failure_map)
            logger.exception("Linked member cache refresh failed.")
            if run_id is not None:
                await asyncio.to_thread(
                    self.member_cache.finish_run,
                    run_id,
                    processed=processed,
                    failed=failed,
                    updated=updated,
                    status="failed",
                )
            return False

    async def _run_member_cache_command(
        self,
        requested_by: str,
        retry_failures: list[tuple[str, int, str, int]] | None = None,
    ) -> None:
        before = await asyncio.to_thread(self.member_cache.stats)
        before_size = MEMBER_CACHE_FILE.stat().st_size
        started = time.monotonic()
        succeeded = await self._refresh_linked_member_cache(retry_failures)
        elapsed = max(0, round(time.monotonic() - started))
        if succeeded:
            after = await asyncio.to_thread(self.member_cache.stats)
            after_size = MEMBER_CACHE_FILE.stat().st_size
            latest = after["latest_run"] or {}

            def change(previous: int, current: int) -> str:
                difference = current - previous
                return f"{difference:+,}"

            hours, remainder = divmod(elapsed, 3600)
            minutes, seconds = divmod(remainder, 60)
            duration_parts = []
            if hours:
                duration_parts.append(f"{hours}h")
            if minutes or hours:
                duration_parts.append(f"{minutes}m")
            duration_parts.append(f"{seconds}s")
            duration = " ".join(duration_parts)

            before_megabytes = before_size / 1_048_576
            after_megabytes = after_size / 1_048_576
            size_change = after_megabytes - before_megabytes
            await self.bot.notify_operations_channel(
                "Member Cache Retry Finished"
                if retry_failures is not None
                else "Member Cache Finished",
                f"**Servers checked:** "
                f"`{int(latest.get('servers_processed', 0)):,} / "
                f"{int(latest.get('servers_total', 0)):,}`\n"
                f"**Incomplete scans:** "
                f"`{int(latest.get('servers_failed', 0)):,}`\n\n"
                f"**Unique users:** `{before['users']:,}` → "
                f"`{after['users']:,}` (`{change(before['users'], after['users'])}`)\n"
                f"**Server memberships:** `{before['memberships']:,}` → "
                f"`{after['memberships']:,}` "
                f"(`{change(before['memberships'], after['memberships'])}`)\n"
                f"**Users updated:** "
                f"`{int(latest.get('users_updated', 0)):,}`\n\n"
                f"**Time taken:** `{duration}`\n"
                f"**Database size:** `{before_megabytes:,.2f} MB` → "
                f"`{after_megabytes:,.2f} MB` (`{size_change:+,.2f} MB`)\n"
                f"**Requested by:** {requested_by}\n"
                "The linked-server member cache pass has finished.",
            )
        else:
            await self.bot.notify_operations_channel(
                "Member Cache Failed",
                f"**Requested by:** {requested_by}\n"
                "The cache could not start or encountered a fatal error. "
                "Check the terminal for details.",
            )

    async def _search_mutual_selfcord_members(
        self,
        query: str,
        *,
        max_guild_queries: int = 20,
        timeout: float = 2.25,
    ) -> list[dict]:
        dm_watch = self.bot.get_cog("DMWatch")
        clients = [
            client
            for client in getattr(dm_watch, "_user_clients", [])
            if client.is_ready()
        ]
        if not clients:
            return []

        searchable_guilds = {}
        for client in clients:
            for guild in client.guilds:
                searchable_guilds.setdefault(guild.id, guild)

        search_text = query.removeprefix("@").strip().casefold()
        users: dict[int, dict] = {}
        for guild in searchable_guilds.values():
            for member in guild.members:
                names = (member.name, member.global_name or "", member.nick or "")
                if not any(name.casefold().startswith(search_text) for name in names if name):
                    continue
                users[member.id] = {
                    "id": str(member.id),
                    "username": member.name,
                    "global_name": member.global_name,
                    "nick": member.nick,
                    "bot": bool(member.bot),
                }
                if len(users) >= 25:
                    return list(users.values())

        guilds = list(searchable_guilds.values())
        if guilds:
            start = self._selfcord_guild_cursor % len(guilds)
            count = min(max_guild_queries, len(guilds))
            selected_guilds = [guilds[(start + index) % len(guilds)] for index in range(count)]
            self._selfcord_guild_cursor = (start + count) % len(guilds)
        else:
            selected_guilds = []

        tasks = [
            asyncio.create_task(
                guild.query_members(
                    query.removeprefix("@").strip(),
                    limit=25,
                    cache=True,
                    presences=False,
                )
            )
            for guild in selected_guilds
        ]
        if not tasks:
            return []

        try:
            done, pending = await asyncio.wait(tasks, timeout=timeout)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        for task in done:
            try:
                members = task.result()
            except Exception:
                continue
            for member in members:
                users[member.id] = {
                    "id": str(member.id),
                    "username": member.name,
                    "global_name": member.global_name,
                    "nick": member.nick,
                    "bot": bool(member.bot),
                }
                if len(users) >= 25:
                    return list(users.values())
        return list(users.values())

    # Adapted from discord.py Guild.get_member_named
    def get_member_named(self, name: str, /) -> dict | None:
        """
        Return the first cached linked or relationship user matching ``name``.

        The lookup order mirrors discord.py:
        1. Username#Discriminator (legacy)
        2. Username#0 (migrated users)
        3. Nickname
        4. Global name
        5. Username
        """
        candidates: list[dict] = []
        seen: set[str] = set()

        for user_id, data in self._known_users.items():
            if user_id in seen:
                continue
            candidates.append(data)
            seen.add(user_id)

        for user in self._relationship_users:
            user_id = str(user.get("id", ""))
            if not user_id or user_id in seen:
                continue
            candidates.append(user)
            seen.add(user_id)

        username, _, discriminator = name.rpartition("#")

        # Without a '#', rpartition puts the full name in discriminator.
        if not username:
            discriminator, username = username, discriminator

        if discriminator == "0" or (
            len(discriminator) == 4 and discriminator.isdigit()
        ):
            for user in candidates:
                if (
                    str(user.get("username", "")) == username
                    and str(user.get("discriminator", "0")) == discriminator
                ):
                    return user
            return None

        for user in candidates:
            nickname = str(user.get("nick") or "")
            global_name = str(user.get("global_name") or "")
            username_value = str(user.get("username") or "")
            if nickname == name or global_name == name or username_value == name:
                return user

        return None

    async def _remember_profile_user(
        self,
        user: LinkedProfileUser,
    ) -> None:
        data = {
            "id": str(user.id),
            "username": user.name,
            "global_name": (
                user.display_name if user.display_name != user.name else None
            ),
            "bot": user.bot,
        }
        if user.bot:
            self._known_users.pop(str(user.id), None)
            await asyncio.to_thread(self.member_cache.upsert_users, [data])
            return
        if self._known_users.get(str(user.id)) == data:
            return
        self._known_users[str(user.id)] = data
        await asyncio.to_thread(self.member_cache.upsert_users, [data])

    async def _remember_relationship_users(
        self,
        users: list[dict],
    ) -> None:
        changed_records: list[dict] = []
        for user in users:
            user_id = str(user.get("id", ""))
            username = user.get("username")
            if not user_id or not username:
                continue
            data = {
                "id": user_id,
                "username": str(username),
                "global_name": user.get("global_name"),
                "bot": bool(user.get("bot", False)),
            }
            if data["bot"]:
                self._known_users.pop(user_id, None)
                changed_records.append(data)
                continue
            if self._known_users.get(user_id) != data:
                self._known_users[user_id] = data
                changed_records.append(data)
        if changed_records:
            await asyncio.to_thread(
                self.member_cache.upsert_users,
                changed_records,
            )

    async def _load_relationship_users(self, *, refresh: bool = False) -> list[dict]:
        if self._relationship_users and not refresh:
            return self._relationship_users
        self._relationship_users = await self.account.fetch_relationship_users()
        return self._relationship_users

    async def _search_linked_guild_members(self, query: str) -> int | None:
        members = await self._search_mutual_selfcord_members(
            query,
            max_guild_queries=80,
            timeout=7.0,
        )
        search_name = query.removeprefix("@").strip()
        search_casefold = search_name.casefold()
        exact: list[dict] = []
        partial: list[dict] = []

        for member in members:
            username = str(member.get("username") or "")
            global_name = str(member.get("global_name") or "")
            nickname = str(member.get("nick") or "")
            discriminator = str(member.get("discriminator") or "0")
            legacy_name = f"{username}#{discriminator}"
            names = (nickname, global_name, username, legacy_name)
            if any(name.casefold() == search_casefold for name in names if name):
                exact.append(member)
            elif any(
                search_casefold in name.casefold()
                for name in (nickname, global_name, username)
                if name
            ):
                partial.append(member)

        matches = exact or partial
        if not matches:
            return None
        if len(matches) > 1:
            suggestions = ", ".join(
                f"`{member.get('username', 'Unknown')}`" for member in matches[:5]
            )
            raise LookupError(
                f"Multiple linked-server users matched: {suggestions}. "
                "Use the exact username, nickname, or global name."
            )

        user = matches[0]
        user_id = str(user.get("id", ""))
        if not user_id.isdigit():
            return None
        data = {
            "id": user_id,
            "username": str(user.get("username") or "Unknown"),
            "global_name": user.get("global_name"),
            "nick": user.get("nick"),
            "discriminator": str(user.get("discriminator") or "0"),
            "bot": bool(user.get("bot", False)),
        }
        if data["bot"]:
            self._known_users.pop(user_id, None)
        else:
            self._known_users[user_id] = data
        await asyncio.to_thread(self.member_cache.upsert_users, [data])
        return int(user_id)

    async def _resolve_linked_user_id(self, query: str) -> int:
        query = query.strip()
        mention = re.fullmatch(r"<@!?(\d+)>", query)
        if mention:
            query = mention.group(1)
        if query.isdigit():
            return int(query)

        normalized = query.removeprefix("@").casefold()
        candidates: dict[int, tuple[str, list[str]]] = {}

        cached_users = await asyncio.to_thread(
            self.member_cache.search_users,
            query,
            100,
        )
        for user in cached_users:
            try:
                numeric_id = int(user["id"])
            except (KeyError, TypeError, ValueError):
                continue
            username = str(user.get("username", "Unknown"))
            names = [
                username,
                str(user.get("global_name") or ""),
                str(user.get("nick") or ""),
            ]
            candidates[numeric_id] = (
                username,
                [name for name in names if name],
            )

        cached_exact = [
            (user_id, username)
            for user_id, (username, names) in candidates.items()
            if any(name.casefold() == normalized for name in names)
        ]
        if len(cached_exact) == 1:
            return cached_exact[0][0]
        if len(cached_exact) > 1:
            suggestions = ", ".join(
                f"`{username}`" for _, username in cached_exact[:5]
            )
            raise LookupError(
                f"Multiple users matched: {suggestions}. "
                "Use the exact username or user ID."
            )

        cached_partial = [
            (user_id, username)
            for user_id, (username, names) in candidates.items()
            if any(normalized in name.casefold() for name in names)
        ]
        if len(cached_partial) == 1:
            return cached_partial[0][0]
        if len(cached_partial) > 1:
            suggestions = ", ".join(
                f"`{username}`" for _, username in cached_partial[:5]
            )
            raise LookupError(
                f"Multiple users matched: {suggestions}. "
                "Use the exact username or user ID."
            )

        try:
            relationships = await self._load_relationship_users()
        except RuntimeError:
            relationships = self._relationship_users

        named_user = self.get_member_named(query.removeprefix("@"))
        if named_user is not None:
            try:
                return int(named_user["id"])
            except (KeyError, TypeError, ValueError):
                pass

        for user in relationships:
            try:
                user_id = int(user["id"])
            except (KeyError, TypeError, ValueError):
                continue
            username = str(user.get("username", "Unknown"))
            names = [
                username,
                str(user.get("global_name") or ""),
            ]
            candidates[user_id] = (
                username,
                [name for name in names if name],
            )

        exact = [
            (user_id, username)
            for user_id, (username, names) in candidates.items()
            if any(name.casefold() == normalized for name in names)
        ]
        if exact:
            if len(exact) > 1:
                suggestions = ", ".join(f"`{username}`" for _, username in exact[:5])
                raise LookupError(
                    f"Multiple users matched: {suggestions}. "
                    "Use the exact username or user ID."
                )
            return exact[0][0]

        matches = [
            (user_id, username)
            for user_id, (username, names) in candidates.items()
            if any(normalized in name.casefold() for name in names)
        ]
        if len(matches) == 1:
            return matches[0][0]
        if len(matches) > 1:
            suggestions = ", ".join(f"`{username}`" for _, username in matches[:5])
            raise LookupError(
                f"Multiple users matched: {suggestions}. "
                "Use the exact username or user ID."
            )

        live_user_id = await self._search_linked_guild_members(query)
        if live_user_id is not None:
            return live_user_id
        raise LookupError(
            "No user with that name was found in the linked account's "
            "relationships, known profiles, or shared servers."
        )

    async def send_public_profile(
        self,
        ctx: commands.Context,
        user: LinkedProfileUser,
    ) -> None:
        view = discord.ui.LayoutView()
        header = discord.ui.Section(
            discord.ui.TextDisplay(
                f"## {user.display_name}\n@{user.name} • `{user.id}`"
            ),
            accessory=discord.ui.Thumbnail(
                user.avatar_url,
                description=f"{user.display_name}'s avatar",
            ),
        )
        container = discord.ui.Container(
            header,
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "### Account\n"
                f"**Created:** <t:{int(user.created_at.timestamp())}:F>\n"
                f"**Account type:** {'Bot' if user.bot else 'User'}"
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "### Private or Limited Profile\n"
                "Discord did not expose extended profile details to the "
                "linked accounts. This may be caused by profile privacy or "
                "no accessible mutual server. Public account information is "
                "shown above."
            ),
            discord.ui.ActionRow(
                discord.ui.Button(
                    label="View Profile",
                    url=f"https://discord.com/users/{user.id}",
                )
            ),
        )
        view.add_item(container)
        await self._send_lookup_result(ctx, view=view)

    @staticmethod
    async def _send_lookup_result(
        ctx: commands.Context,
        content: str | None = None,
        *,
        view: discord.ui.LayoutView | None = None,
    ) -> discord.Message:
        loading_message = getattr(ctx, "_lookup_loading_message", None)
        if isinstance(loading_message, discord.Message):
            ctx._lookup_loading_message = None
            return await loading_message.edit(content=content, view=view)
        return await ctx.send(content, view=view)

    async def _start_loading_indicator(
        self,
        ctx: commands.Context,
    ) -> None:
        """Send the prefix-command message that will become the result."""
        message = await ctx.send(
            f"{LOADING_EMOJI} Searching linked accounts and shared servers..."
        )
        ctx._lookup_loading_message = message

    @recache.command(
        name="start",
        description="Refresh every linked-account server in the background",
    )
    async def recache_users(self, interaction: discord.Interaction) -> None:
        if not await self.bot.can_use_owner_commands(interaction.user):
            await interaction.response.send_message(
                "Only the bot owner can refresh the member cache.",
                ephemeral=True,
            )
            return

        if self._member_cache_task is not None and not self._member_cache_task.done():
            await interaction.response.send_message(
                "A member cache pass is already running.",
                ephemeral=True,
            )
            return

        self._member_cache_task = asyncio.create_task(
            self._run_member_cache_command(str(interaction.user))
        )
        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Member Cache Started\n"
                    "Linked servers are being processed in the background. "
                    "I will DM you when the cache pass finishes."
                )
            )
        )
        await interaction.response.send_message(view=view, ephemeral=True)

    @recache.command(
        name="retry-failed",
        description="Retry only servers that failed the latest cache attempt",
    )
    async def retry_failed_recache(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not await self.bot.can_use_owner_commands(interaction.user):
            await interaction.response.send_message(
                "Only the bot owner can retry the member cache.",
                ephemeral=True,
            )
            return

        if self._member_cache_task is not None and not self._member_cache_task.done():
            await interaction.response.send_message(
                "A member cache pass is already running.",
                ephemeral=True,
            )
            return

        failures = await asyncio.to_thread(self.member_cache.load_failures)
        if not failures:
            await interaction.response.send_message(
                "There are no failed server scans to retry.",
                ephemeral=True,
            )
            return

        self._member_cache_task = asyncio.create_task(
            self._run_member_cache_command(
                str(interaction.user),
                retry_failures=failures,
            )
        )
        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Cache Retry Started\n"
                    f"Retrying `{len(failures):,}` failed server scan(s) in "
                    "the background. I will DM you when it finishes."
                )
            )
        )
        await interaction.response.send_message(view=view, ephemeral=True)

    @app_commands.command(
        name="cache-status",
        description="Show linked-user cache totals and latest recache status",
    )
    @app_commands.describe(
        ephemeral="Only show the cache status to you",
    )
    async def cache_status(
        self,
        interaction: discord.Interaction,
        ephemeral: bool = False,
    ) -> None:
        if not await self.bot.can_use_owner_commands(interaction.user):
            await interaction.response.send_message(
                "Only the bot owner can view cache details.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=ephemeral)
        stats = await asyncio.to_thread(self.member_cache.stats)
        database_size = await asyncio.to_thread(MEMBER_CACHE_FILE.stat)
        latest = stats["latest_run"]
        if latest is None:
            latest_text = "No recache has been recorded yet."
        else:
            def format_time(value: str | None) -> str:
                if not value:
                    return "Still running"
                parsed = discord.utils.parse_time(value)
                if parsed is None:
                    return value
                timestamp = int(parsed.timestamp())
                return f"<t:{timestamp}:F> (<t:{timestamp}:R>)"

            started = format_time(latest["started_at"])
            finished = format_time(latest["finished_at"])
            latest_text = (
                f"**Status:** {str(latest['status']).title()}\n"
                f"**Servers processed:** {latest['servers_processed']:,}/"
                f"{latest['servers_total']:,}\n"
                f"**Servers with incomplete scans:** {latest['servers_failed']:,}\n"
                f"**Users updated during run:** {latest['users_updated']:,}\n"
                f"**Started:** {started}\n"
                f"**Finished:** {finished}"
            )

        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Linked User Cache\n"
                    f"**Unique users:** {stats['users']:,}\n"
                    f"**Server memberships:** {stats['memberships']:,}\n"
                    f"**Servers represented:** {stats['servers']:,}\n"
                    f"**Database size:** {database_size.st_size / 1_048_576:.2f} MB\n\n"
                    "### Latest Recache\n"
                    f"{latest_text}"
                )
            )
        )
        await interaction.followup.send(view=view, ephemeral=ephemeral)

    @linked_account.command(
        name="refresh",
        description="Refresh the linked account's cached server list",
    )
    async def refresh_linked_account(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not await self.bot.can_use_owner_commands(interaction.user):
            await interaction.response.send_message(
                "Only the bot owner can refresh the linked account.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            guilds_cog = self.bot.get_cog("Guilds")
            refresh = getattr(
                guilds_cog,
                "refresh_linked_account_guilds",
                None,
            )
            if refresh is not None:
                guilds = await refresh()
            else:
                guilds = await self.account.fetch_guilds()
            try:
                relationships = await self._load_relationship_users(
                    refresh=True,
                )
                await self._remember_relationship_users(relationships)
            except RuntimeError:
                relationships = []
        except RuntimeError as error:
            await interaction.followup.send(
                f"Linked Account refresh failed: {error}",
                ephemeral=True,
            )
            return

        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Linked Account Refreshed\n"
                    f"Configured tokens: **{self.account.token_count()}**\n"
                    f"Accessible servers: **{len(guilds)}**\n"
                    f"Searchable relationships: **{len(relationships)}**"
                )
            )
        )
        await interaction.followup.send(view=view, ephemeral=True)

    @commands.hybrid_command(
        name="user-servers",
        description="Show servers visible to the linked account",
    )
    @owner_clearance()
    async def user_servers(
        self,
        ctx: commands.Context,
        ephemeral: bool = False,
    ) -> None:
        if ctx.interaction is not None and not ctx.interaction.response.is_done():
            try:
                await ctx.interaction.response.defer(
                    ephemeral=ephemeral,
                    thinking=True,
                )
            except discord.NotFound:
                return

        try:
            guilds = await self.account.fetch_guilds()
        except RuntimeError as error:
            await ctx.send(f"Server list failed: {error}")
            return

        guilds.sort(key=lambda guild: str(guild.get("name", "")).casefold())
        view = AccountGuildPaginator(
            guilds=guilds,
            author_id=ctx.author.id,
        )
        view.message = await ctx.send(
            view=view,
            ephemeral=ephemeral if ctx.interaction is not None else False,
        )

    @commands.hybrid_command(
        name="lookup",
        description="Look up a Discord profile",
    )
    @app_commands.describe(
        query="User ID, mention, exact username, or unique partial username"
    )
    async def lookup(
        self,
        ctx: commands.Context,
        query: str,
        ephemeral: bool = False,
    ) -> None:
        if not await self.bot.can_use_lookup(ctx.author):
            await ctx.send(
                "You do not have access to `/lookup`. Ask the bot owner to add you with `/allow`."
            )
            return
        if ctx.interaction is not None and not ctx.interaction.response.is_done():
            try:
                await ctx.interaction.response.defer(
                    ephemeral=ephemeral,
                    thinking=True,
                )
            except discord.NotFound:
                return
        else:
            await self._start_loading_indicator(ctx)

        try:
            user_id = await self._resolve_linked_user_id(query)
        except LookupError as error:
            await self._send_lookup_result(ctx, str(error))
            return
        except RuntimeError as error:
            await self._send_lookup_result(
                ctx,
                f"User search failed: {error}",
            )
            return

        try:
            profile = await self.account.fetch_profile(user_id)
        except LookupError:
            try:
                public_user = await self.bot.fetch_user(user_id)
            except discord.NotFound:
                await self._send_lookup_result(
                    ctx, "Discord did not expose a profile for that user ID."
                )
                return
            except discord.HTTPException:
                await self._send_lookup_result(
                    ctx,
                    "Discord could not load the public account information. "
                    "Please try again shortly.",
                )
                return

            limited_user = LinkedProfileUser(
                id=public_user.id,
                name=public_user.name,
                display_name=public_user.display_name,
                avatar_url=str(public_user.display_avatar.url),
                bot=public_user.bot,
            )
            await self.send_public_profile(ctx, limited_user)
            return
        except RuntimeError as error:
            await self._send_lookup_result(
                ctx,
                f"Profile lookup failed: {error}",
            )
            return

        profile_user = profile.get("user")
        user_profile = profile.get("user_profile")
        if not isinstance(profile_user, dict):
            profile_user = {}
        if not isinstance(user_profile, dict):
            user_profile = {}
        user = LinkedProfileUser.from_profile(profile_user, user_id)
        await self._remember_profile_user(user)
        bio = user_profile.get("bio") or profile_user.get("bio") or "None"
        nitro = profile.get("premium_since")
        nitro_date = discord.utils.parse_time(nitro) if isinstance(nitro, str) else None
        nitro_str = (
            f"Since <t:{int(nitro_date.timestamp())}:F> "
            f"(<t:{int(nitro_date.timestamp())}:R>)"
            if nitro_date
            else "User has no Nitro"
        )
        account_guild_names = profile.get("_guild_names") or {}
        mutual_guilds = profile.get("mutual_guilds") or []
        mutual_entries: list[tuple[str, str]] = []
        for guild in mutual_guilds:
            if not isinstance(guild, dict):
                continue

            guild_id = str(guild.get("id", ""))
            guild_name = guild.get("name") or account_guild_names.get(guild_id)
            if guild_name:
                mutual_entries.append((str(guild_name), guild_id))
            elif guild_id:
                mutual_entries.append(("Unknown Server", guild_id))
        connections = profile.get("connected_accounts") or []
        connection_names = [
            f"{connection.get('type', 'unknown')} \u2022 "
            f"`{connection.get('name', 'Unknown')}`"
            for connection in connections
            if isinstance(connection, dict)
        ]
        connection_str = "\n".join(connection_names) if connection_names else "None"

        pronouns = str(user_profile.get("pronouns") or "").strip()
        badge_items: list[tuple[str, str | None]] = []
        profile_badges = _profile_badges(profile)
        for badge in profile_badges:
            badge_name = badge.get("description") or badge.get("id")
            if badge_name:
                badge_items.append(
                    (str(badge_name), await self._badge_emoji(badge))
                )
        badge_items = list(dict.fromkeys(badge_items))

        detail_sections: list[str] = []
        if badge_items:
            badge_text = " ".join(
                emoji or name for name, emoji in badge_items
            )
            detail_sections.append(f"### Badges\n{badge_text[:1200]}")
        else:
            detail_sections.append("### Badges\nNone")
        detail_sections.append(f"### Connections\n{connection_str[:1500]}")
        details_text = "\n\n".join(detail_sections)

        header = discord.ui.Section(
            discord.ui.TextDisplay(
                f"## {user.display_name}\n@{user.name} • `{user.id}`"
            ),
            accessory=discord.ui.Thumbnail(
                user.avatar_url,
                description=f"{user.display_name}'s avatar",
            ),
        )
        overview_lines = []
        if pronouns:
            overview_lines.append(f"**Pronouns:** {pronouns[:100]}")
        overview_lines.extend(
            [
                f"**Created:** <t:{int(user.created_at.timestamp())}:F>",
                f"**Type:** {'Bot' if user.bot else 'User'}",
                f"**Nitro:** {nitro_str}",
                f"**Mutual servers:** {len(mutual_entries)}",
            ]
        )
        overview = discord.ui.TextDisplay("\n".join(overview_lines))

        view = MutualGuildView(
            author_id=ctx.author.id,
            profile_user_id=user.id,
            guild_entries=mutual_entries,
            details_text=details_text,
            container_items=[
                header,
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"### Bio\n{str(bio)[:900]}"),
                discord.ui.Separator(),
                overview,
            ],
        )
        view.message = await self._send_lookup_result(ctx, view=view)

    @commands.hybrid_command(
        name="usernames",
        description="Browse cached usernames by character length",
    )
    @app_commands.describe(
        length="Exact length or range, such as 2 or 2-3",
        ephemeral="Only show the results to you",
    )
    async def usernames(
        self,
        ctx: commands.Context,
        length: str,
        ephemeral: bool = False,
    ) -> None:
        if not await self.bot.can_use_lookup(ctx.author):
            await ctx.send(
                "You do not have access to lookup commands. "
                "Ask the bot owner to add you with `/allow`."
            )
            return

        match = re.fullmatch(
            r"\s*(\d{1,2})(?:\s*(?:-|to)\s*(\d{1,2}))?\s*",
            length,
            flags=re.IGNORECASE,
        )
        if match is None:
            await ctx.send("Use an exact length like `2` or a range like `2-3`.")
            return

        minimum = int(match.group(1))
        maximum = int(match.group(2) or minimum)
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        if minimum < 2 or maximum > 32:
            await ctx.send("Username lengths must be between `2` and `32` characters.")
            return

        total = await asyncio.to_thread(
            self.member_cache.count_usernames_by_length,
            minimum,
            maximum,
        )
        if total == 0:
            label = str(minimum) if minimum == maximum else f"{minimum}-{maximum}"
            await ctx.send(f"No cached usernames are `{label}` characters long.")
            return

        view = UsernameLengthPaginator(
            member_cache=self.member_cache,
            minimum=minimum,
            maximum=maximum,
            total=total,
            author_id=ctx.author.id,
        )
        view.message = await ctx.send(
            view=view,
            ephemeral=ephemeral if ctx.interaction is not None else False,
        )

    @commands.hybrid_command(
        name="mutual-servers",
        description="Show servers shared by every linked account",
    )
    @owner_clearance()
    async def mutual_servers(
        self,
        ctx: commands.Context,
        ephemeral: bool = False,
    ) -> None:
        if ctx.interaction is not None and not ctx.interaction.response.is_done():
            try:
                await ctx.interaction.response.defer(
                    ephemeral=ephemeral,
                    thinking=True,
                )
            except discord.NotFound:
                return
        else:
            await self._start_loading_indicator(ctx)

        try:
            guilds, account_count = await self.account.fetch_mutual_guilds()
        except RuntimeError as error:
            await self._send_lookup_result(
                ctx,
                f"Linked-account mutual-server lookup failed: {error}",
            )
            return

        guilds.sort(key=lambda guild: str(guild.get("name", "")).casefold())
        if not guilds:
            await self._send_lookup_result(
                ctx,
                f"No servers are shared by all **{account_count}** "
                "configured linked accounts.",
            )
            return

        guild_lines = [
            (
                f"• **{discord.utils.escape_markdown(str(guild.get('name') or 'Unknown Server'))}** "
                f"— `{guild.get('id', 'Unknown')}`"
            )
            for guild in guilds
        ]
        chunks = _split_lines(guild_lines)
        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"## Linked-Account Mutual Servers — {len(guilds)}\n"
                    f"Shared by all **{account_count}** configured accounts."
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(chunks[0]),
            )
        )
        for chunk in chunks[1:]:
            view.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay(chunk),
                )
            )
        await self._send_lookup_result(ctx, view=view)

    @commands.hybrid_command(
        name="checkuser",
        description="Check whether a Discord username is taken",
    )
    @app_commands.describe(username="Username to check")
    @owner_clearance()
    async def checkuser(
        self,
        ctx: commands.Context,
        username: str,
        ephemeral: bool = False,
    ) -> None:
        username = username.strip().lower()
        if not 2 <= len(username) <= 32:
            await ctx.send("Usernames must contain between 2 and 32 characters.")
            return
        if not re.fullmatch(r"[a-z0-9._]+", username):
            await ctx.send(
                "Usernames may only contain lowercase letters, numbers, "
                "underscores, and periods."
            )
            return
        if ".." in username:
            await ctx.send("Usernames cannot contain two consecutive periods.")
            return
        blocked_names = {"everyone", "here"}
        blocked_terms = ("discord", "nitro")
        if username in blocked_names or any(term in username for term in blocked_terms):
            await ctx.send("That username contains a reserved or disallowed term.")
            return

        url = "https://discord.com/api/v9/unique-username/username-attempt-unauthed"
        timeout = aiohttp.ClientTimeout(total=10)

        try:
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.post(url, json={"username": username}) as resp,
            ):
                if resp.status == 400:
                    await ctx.send(
                        "Discord rejected that username as invalid. It may "
                        "contain a reserved word or another restricted pattern."
                    )
                    return
                if resp.status != 200:
                    await ctx.send(
                        f"Discord returned an error (HTTP {resp.status}). "
                        "Please try again later."
                    )
                    return
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError):
            await ctx.send("Discord could not be reached. Please try again later.")
            return

        taken = data.get("taken")
        if not isinstance(taken, bool):
            await ctx.send("Discord returned an unexpected response.")
            return

        status = "❌ Taken" if taken else "✅ Available"
        view = discord.ui.LayoutView()
        container = discord.ui.Container(
            discord.ui.TextDisplay("## Username Check"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"### `{username}`\n**Status:** {status}"),
        )
        view.add_item(container)
        await ctx.send(view=view)

    @lookup.autocomplete("query")
    async def lookup_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        query = current.casefold()
        choices: list[app_commands.Choice[str]] = []
        seen: set[int] = set()
        linked_members: list[dict] = []

        # Cached prefix matches are local and reliably finish inside Discord's
        # short autocomplete deadline. Avoid waiting on live guild requests
        # when the cache already has recommendations.
        cached_prefixes = await asyncio.to_thread(
            self.member_cache.autocomplete_users,
            current,
            25,
        )
        for user in cached_prefixes:
            try:
                numeric_id = int(user["id"])
            except (KeyError, TypeError, ValueError):
                continue
            username = str(user.get("username", "Unknown"))
            global_name = str(user.get("global_name") or "")
            nickname = str(user.get("nick") or "")
            label = f"@{username}"
            display_name = nickname or global_name
            if display_name and display_name != username:
                label += f" • {display_name}"
            choices.append(
                app_commands.Choice(
                    name=f"{label} ({numeric_id})"[:100],
                    value=str(numeric_id),
                )
            )
            seen.add(numeric_id)
        # Never start live linked-account member queries from autocomplete.
        # Discord expects suggestions within a few seconds, and abandoned
        # Selfcord queries otherwise keep running until their 30-second timeout.
        return choices

        if len(query.strip().removeprefix("@")) >= 2:
            try:
                linked_members = await asyncio.wait_for(
                    self._search_mutual_selfcord_members(
                        current,
                        max_guild_queries=4,
                        timeout=1.0,
                    ),
                    timeout=1.25,
                )
            except (RuntimeError, TimeoutError):
                linked_members = []

        for user in linked_members:
            try:
                user_id = int(user["id"])
            except (KeyError, TypeError, ValueError):
                continue
            username = str(user.get("username") or "Unknown")
            global_name = str(user.get("global_name") or "")
            nickname = str(user.get("nick") or "")
            label = f"@{username}"
            display_name = nickname or global_name
            if display_name and display_name != username:
                label += f" • {display_name}"
            choices.append(
                app_commands.Choice(
                    name=f"{label} ({user_id})"[:100],
                    value=str(user_id),
                )
            )
            seen.add(user_id)
            if len(choices) >= 25:
                return choices

        cached_users = await asyncio.to_thread(
            self.member_cache.search_users,
            current,
            25,
        )
        for user in cached_users:
            try:
                numeric_id = int(user["id"])
            except (KeyError, TypeError, ValueError):
                continue
            if numeric_id in seen:
                continue
            username = str(user.get("username", "Unknown"))
            global_name = str(user.get("global_name") or "")
            label = f"@{username}"
            if global_name and global_name != username:
                label += f" • {global_name}"
            choices.append(
                app_commands.Choice(
                    name=f"{label} ({numeric_id})"[:100],
                    value=str(numeric_id),
                )
            )
            seen.add(numeric_id)
            if len(choices) >= 25:
                return choices

        for user in self._relationship_users:
            try:
                user_id = int(user["id"])
            except (KeyError, TypeError, ValueError):
                continue
            if user_id in seen:
                continue
            username = str(user.get("username", "Unknown"))
            global_name = str(user.get("global_name") or "")
            label = f"@{username}"
            if global_name and global_name != username:
                label += f" • {global_name}"
            choices.append(
                app_commands.Choice(
                    name=f"{label} ({user_id})"[:100],
                    value=str(user_id),
                )
            )
            if len(choices) >= 25:
                break
        return choices


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Lookup(bot))
