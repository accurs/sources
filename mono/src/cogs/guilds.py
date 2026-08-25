from __future__ import annotations

import asyncio
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands
from src.cogs.owner import owner_clearance

from src.services.user_account import UserAccountClient


USER_INSTALL_DB = Path(__file__).resolve().parents[2] / ".cache" / "user_installs.db"


class UserInstallStore:
    def __init__(self, database: Path) -> None:
        self.database = database
        database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_installs (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL,
                    global_name TEXT,
                    avatar_url TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                )
                """
            )

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def remember(
        self,
        user_id: int,
        username: str,
        global_name: str | None,
        avatar_url: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO user_installs (
                    user_id, username, global_name, avatar_url, last_seen_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username,
                    global_name=excluded.global_name,
                    avatar_url=excluded.avatar_url,
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    user_id,
                    username,
                    global_name,
                    avatar_url,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def users(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT user_id, username, global_name, avatar_url, last_seen_at
                FROM user_installs
                ORDER BY username COLLATE NOCASE, user_id
                """
            ).fetchall()
        return [dict(row) for row in rows]


user_install_store = UserInstallStore(USER_INSTALL_DB)


def _escape_link_label(value: str) -> str:
    return discord.utils.escape_markdown(value).replace("]", r"\]")


def _message_channels(guild: discord.Guild) -> list[discord.abc.GuildChannel]:
    return [
        channel
        for channel in guild.channels
        if not isinstance(channel, discord.CategoryChannel)
    ]


class ServerInfoView(discord.ui.LayoutView):
    actions = discord.ui.ActionRow()

    def __init__(
        self,
        *,
        guild: discord.Guild,
        author_id: int,
        items: list[discord.ui.Item],
    ) -> None:
        super().__init__(timeout=180)
        self.guild = guild
        self.clear_items()
        self.add_item(discord.ui.Container(*items, self.actions))

    async def _send_panel(
        self,
        interaction: discord.Interaction,
        title: str,
        lines: list[str],
    ) -> None:
        chunks: list[str] = []
        current = ""
        for line in lines:
            candidate = f"{current}\n{line}".strip()
            if current and len(candidate) > 3500:
                chunks.append(current)
                current = line
            else:
                current = candidate
        if current:
            chunks.append(current)

        view = discord.ui.LayoutView()
        for index, chunk in enumerate(chunks or ["None"]):
            content = f"## {title}\n{chunk}" if index == 0 else chunk
            view.add_item(discord.ui.Container(discord.ui.TextDisplay(content)))
        await interaction.response.send_message(view=view, ephemeral=True)

    @actions.button(label="Channels", style=discord.ButtonStyle.secondary)
    async def channels(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        lines = [
            f"• [#{_escape_link_label(channel.name)}]"
            f"(https://discord.com/channels/{self.guild.id}/{channel.id}) "
            f"• `{channel.id}`"
            for channel in _message_channels(self.guild)
        ]
        await self._send_panel(interaction, f"Channels — {len(lines)}", lines)

    @actions.button(label="Roles", style=discord.ButtonStyle.secondary)
    async def roles(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        roles = [role for role in reversed(self.guild.roles) if not role.is_default()]
        lines = [f"• {role.mention} • `{role.id}`" for role in roles]
        await self._send_panel(interaction, f"Roles — {len(lines)}", lines)

    @actions.button(label="Bot Permissions", style=discord.ButtonStyle.secondary)
    async def permissions(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        member = self.guild.me
        permissions = (
            [
                name.replace("_", " ").title()
                for name, enabled in member.guild_permissions
                if enabled
            ]
            if member
            else []
        )
        await self._send_panel(
            interaction,
            f"Bot Permissions — {len(permissions)}",
            [f"• {permission}" for permission in permissions],
        )


class AccountServerInfoView(discord.ui.LayoutView):
    actions = discord.ui.ActionRow()

    def __init__(
        self,
        *,
        permissions: list[str],
        features: list[str],
        items: list[discord.ui.Item],
    ) -> None:
        super().__init__(timeout=180)
        self.permissions = permissions
        self.features = features
        self.permissions_button.disabled = not permissions
        self.features_button.disabled = not features
        self.clear_items()
        self.add_item(discord.ui.Container(*items, self.actions))

    @staticmethod
    async def _send_private_list(
        interaction: discord.Interaction,
        title: str,
        values: list[str],
    ) -> None:
        lines = "\n".join(f"• {value}" for value in values) or "None"
        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(discord.ui.TextDisplay(f"## {title}\n{lines[:3900]}"))
        )
        await interaction.response.send_message(view=view, ephemeral=True)

    @actions.button(
        label="Account Permissions",
        style=discord.ButtonStyle.secondary,
    )
    async def permissions_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._send_private_list(
            interaction,
            f"Account Permissions — {len(self.permissions)}",
            self.permissions,
        )

    @actions.button(label="Features", style=discord.ButtonStyle.secondary)
    async def features_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._send_private_list(
            interaction,
            f"Server Features — {len(self.features)}",
            self.features,
        )


class BotServerPaginator(discord.ui.LayoutView):
    navigation = discord.ui.ActionRow()

    def __init__(
        self,
        *,
        guilds: list[discord.Guild],
        author_id: int,
        invite_urls: dict[int, str | None],
    ) -> None:
        super().__init__(timeout=180)
        self.guilds = guilds
        self.author_id = author_id
        self.invite_urls = invite_urls
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
        guilds = self.guilds[start : start + self.page_size]
        items: list[discord.ui.Item] = [
            discord.ui.TextDisplay(f"## Bot Servers — {len(self.guilds)}"),
        ]
        if guilds:
            items.append(discord.ui.Separator())
        for offset, guild in enumerate(guilds):
            index = start + offset + 1
            name = _escape_link_label(guild.name)
            invite_url = self.invite_urls.get(guild.id)
            linked_name = f"[{name}]({invite_url})" if invite_url else name
            details = (
                f"`{index}.` {linked_name}\n"
                f"`{guild.id}` • {guild.member_count or 0:,} members • "
                f"{len(_message_channels(guild))} channels"
            )
            if guild.icon is not None:
                item: discord.ui.Item = discord.ui.Section(
                    discord.ui.TextDisplay(details),
                    accessory=discord.ui.Thumbnail(
                        str(guild.icon.url),
                        description=f"{guild.name} server icon",
                    ),
                )
            else:
                item = discord.ui.TextDisplay(details)
            items.append(item)
            if offset < len(guilds) - 1:
                items.append(discord.ui.Separator())

        self.previous.disabled = self.current_page == 0
        self.next.disabled = self.current_page >= self.page_count - 1
        if not guilds:
            items.append(discord.ui.TextDisplay("The bot is not in any servers."))
        items.extend(
            (
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"Page {self.current_page + 1} of {self.page_count}"
                ),
                self.navigation,
            )
        )
        self.add_item(
            discord.ui.Container(
                *items,
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


class UserInstallPaginator(discord.ui.LayoutView):
    navigation = discord.ui.ActionRow()

    def __init__(
        self,
        *,
        users: list[dict],
        author_id: int,
        approximate_total: int | None,
    ) -> None:
        super().__init__(timeout=180)
        self.users = users
        self.author_id = author_id
        self.approximate_total = approximate_total
        self.current_page = 0
        self.page_size = 5
        self.message: discord.Message | None = None
        self.render_page()

    @property
    def page_count(self) -> int:
        return max((len(self.users) + self.page_size - 1) // self.page_size, 1)

    def render_page(self) -> None:
        self.clear_items()
        start = self.current_page * self.page_size
        page_users = self.users[start : start + self.page_size]
        items: list[discord.ui.Item] = [
            discord.ui.TextDisplay(f"## Known User Installs — {len(self.users):,}"),
        ]
        if page_users:
            items.append(discord.ui.Separator())
            for offset, user in enumerate(page_users):
                username = discord.utils.escape_markdown(str(user["username"]))
                items.append(
                    discord.ui.Section(
                        discord.ui.TextDisplay(
                            f"### @{username}\n**User ID:** `{user['user_id']}`"
                        ),
                        accessory=discord.ui.Thumbnail(
                            str(user["avatar_url"]),
                            description=f"@{username}'s profile picture",
                        ),
                    )
                )
                if offset < len(page_users) - 1:
                    items.append(discord.ui.Separator())
        else:
            items.append(
                discord.ui.TextDisplay(
                    "No verified user installations have been observed yet."
                )
            )

        if self.approximate_total is None:
            install_note = "Discord did not provide an approximate total"
        else:
            install_note = f"Discord reports approximately {self.approximate_total:,} total"
        self.previous.disabled = self.current_page == 0
        self.next.disabled = self.current_page >= self.page_count - 1
        items.extend(
            [
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"-# Page {self.current_page + 1} of {self.page_count} • "
                    f"{install_note}\n"
                    "-# Users appear here after using the app through a user install."
                ),
                self.navigation,
            ]
        )
        self.add_item(discord.ui.Container(*items))

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This user-install list belongs to someone else.",
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

class Guilds(commands.Cog):
    """Owner-only server inventory and management commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.account = UserAccountClient()
        self._account_guilds: list[dict] = []
        self._account_guilds_cached_at = 0.0
        self._account_guilds_lock = asyncio.Lock()
        self._server_invite_urls: dict[int, str | None] = {}

    async def _server_invite_url(self, guild: discord.Guild) -> str | None:
        if guild.id in self._server_invite_urls:
            return self._server_invite_urls[guild.id]

        if guild.vanity_url is not None:
            invite_url = str(guild.vanity_url)
            self._server_invite_urls[guild.id] = invite_url
            return invite_url

        bot_member = guild.me
        if bot_member is None:
            self._server_invite_urls[guild.id] = None
            return None

        channels: list[discord.TextChannel] = []
        for channel in (guild.system_channel, guild.rules_channel, *guild.text_channels):
            if channel is not None and channel not in channels:
                channels.append(channel)

        for channel in channels:
            permissions = channel.permissions_for(bot_member)
            if not (permissions.view_channel and permissions.create_instant_invite):
                continue
            try:
                invite = await channel.create_invite(
                    max_age=0,
                    max_uses=0,
                    unique=False,
                    reason="Requested through the bot server list",
                )
            except discord.HTTPException:
                continue
            invite_url = str(invite.url)
            self._server_invite_urls[guild.id] = invite_url
            return invite_url

        self._server_invite_urls[guild.id] = None
        return None

    async def _server_invites(
        self,
        guilds: list[discord.Guild],
    ) -> dict[int, str | None]:
        semaphore = asyncio.Semaphore(5)

        async def resolve(guild: discord.Guild) -> tuple[int, str | None]:
            async with semaphore:
                return guild.id, await self._server_invite_url(guild)

        return dict(await asyncio.gather(*(resolve(guild) for guild in guilds)))

    async def _remember_user_install(self, interaction: discord.Interaction) -> None:
        if (
            interaction.type is not discord.InteractionType.application_command
            or not interaction.is_user_integration()
        ):
            return
        user = interaction.user
        await asyncio.to_thread(
            user_install_store.remember,
            user.id,
            user.name,
            user.global_name,
            user.display_avatar.url,
        )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        await self._remember_user_install(interaction)

    async def _get_account_guilds(self) -> list[dict]:
        if (
            self._account_guilds
            and time.monotonic() - self._account_guilds_cached_at < 60
        ):
            return self._account_guilds

        async with self._account_guilds_lock:
            if (
                self._account_guilds
                and time.monotonic() - self._account_guilds_cached_at < 60
            ):
                return self._account_guilds
            self._account_guilds = await self.account.fetch_guilds()
            self._account_guilds_cached_at = time.monotonic()
            return self._account_guilds

    async def refresh_linked_account_guilds(self) -> list[dict]:
        async with self._account_guilds_lock:
            guilds = await self.account.fetch_guilds()
            self._account_guilds = guilds
            self._account_guilds_cached_at = time.monotonic()
            return guilds

    async def _send_account_serverinfo(
        self,
        ctx: commands.Context,
        guild: dict,
    ) -> None:
        guild_id = str(guild.get("id", "Unknown"))
        name = str(guild.get("name", "Unknown Server"))
        icon_hash = guild.get("icon")
        icon_url = (
            f"https://cdn.discordapp.com/icons/{guild_id}/{icon_hash}.png?size=1024"
            if icon_hash
            else self.bot.user.display_avatar.url
        )
        member_count = guild.get("approximate_member_count")
        online_count = guild.get("approximate_presence_count")
        counts = (
            f"{member_count:,} members • {online_count:,} online"
            if isinstance(member_count, int) and isinstance(online_count, int)
            else "Unavailable"
        )
        permission_value = guild.get("permissions")
        permission_names: list[str] = []
        if permission_value is not None:
            try:
                permissions = discord.Permissions(int(permission_value))
                permission_names = [
                    permission.replace("_", " ").title()
                    for permission, enabled in permissions
                    if enabled
                ]
            except (TypeError, ValueError):
                pass
        raw_features = guild.get("features")
        feature_names = (
            [str(feature).replace("_", " ").title() for feature in raw_features]
            if isinstance(raw_features, list)
            else []
        )
        guild_url = f"https://discord.com/channels/{guild_id}"
        view = AccountServerInfoView(
            permissions=permission_names,
            features=feature_names,
            items=[
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        f"## {name}\n`{guild_id}` • Linked Account server"
                    ),
                    accessory=discord.ui.Thumbnail(
                        icon_url,
                        description=f"{name} icon",
                    ),
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    "### Account Access\n"
                    f"**Counts:** {counts}\n"
                    f"**Account owner:** {'Yes' if guild.get('owner') else 'No'}\n"
                    f"**Server:** "
                    f"[Open in Discord]({guild_url})"
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"### Account Permissions — {len(permission_names)}\n"
                    "Press **Account Permissions** to view them privately."
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"### Features — {len(feature_names)}\n"
                    "Press **Features** to view them privately."
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    "Detailed channels, roles, boosts, and ownership data are "
                    "only available when the bot itself is in the server.\n\n"
                    "Buttons are available to everyone for 180 seconds. "
                    "Responses are private."
                ),
            ],
        )
        await ctx.send(view=view)

    @commands.command(
        name="servers",
        aliases=["guilds"],
        help="List every server the bot is connected to",
        hidden=True,
    )
    @owner_clearance()
    async def servers(
        self,
        ctx: commands.Context,
    ) -> None:
        guilds = sorted(
            self.bot.guilds,
            key=lambda guild: guild.name.casefold(),
        )
        invite_urls = await self._server_invites(guilds)
        view = BotServerPaginator(
            guilds=guilds,
            author_id=ctx.author.id,
            invite_urls=invite_urls,
        )
        view.message = await ctx.send(view=view)

    @commands.command(
        name="users",
        help="List known users who installed and used the app",
        hidden=True,
    )
    @owner_clearance()
    async def users(
        self,
        ctx: commands.Context,
    ) -> None:
        known_users = await asyncio.to_thread(user_install_store.users)
        try:
            application = await self.bot.application_info()
            approximate_total = application.approximate_user_install_count
        except discord.HTTPException:
            approximate_total = None
        view = UserInstallPaginator(
            users=known_users,
            author_id=ctx.author.id,
            approximate_total=approximate_total,
        )
        view.message = await ctx.send(view=view)

    @commands.command(
        name="leave",
        help="Make the bot leave a server",
        hidden=True,
    )
    @owner_clearance()
    async def leave(
        self,
        ctx: commands.Context,
        guild: str,
    ) -> None:
        if not guild.isdigit():
            await ctx.send("Choose a server from the list or provide its ID.")
            return
        selected = self.bot.get_guild(int(guild))
        if selected is None:
            await ctx.send(f"No server was found with ID `{guild}`.")
            return

        name = selected.name
        try:
            await selected.leave()
        except discord.HTTPException:
            await ctx.send(f"Discord could not remove me from **{name}**.")
            return

        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Left Server\n"
                    f"Successfully left **{name}**.\n"
                    f"Server ID: `{guild}`"
                )
            )
        )
        await ctx.send(view=view)

    @commands.command(
        name="serverinfo",
        aliases=["si", "guildinfo"],
        help="Show detailed information about a server",
        hidden=True,
    )
    @owner_clearance()
    async def serverinfo(
        self,
        ctx: commands.Context,
        guild: str | None = None,
    ) -> None:
        if guild is None:
            selected = ctx.guild
        elif guild.isdigit():
            selected = self.bot.get_guild(int(guild))
        else:
            selected = None
        if selected is None and guild and guild.isdigit():
            try:
                account_guilds = await self._get_account_guilds()
            except RuntimeError as error:
                await ctx.send(f"Could not load Linked Account servers: {error}")
                return
            account_guild = next(
                (item for item in account_guilds if str(item.get("id", "")) == guild),
                None,
            )
            if account_guild is not None:
                await self._send_account_serverinfo(ctx, account_guild)
                return

        if selected is None:
            await ctx.send("Choose a server from the list or provide its ID.")
            return

        owner = selected.owner
        owner_text = f"{owner} (`{owner.id}`)" if owner else f"`{selected.owner_id}`"
        verification = str(selected.verification_level).replace("_", " ").title()
        features = (
            ", ".join(
                feature.replace("_", " ").title() for feature in selected.features
            )
            or "None"
        )
        icon_url = (
            selected.icon.url if selected.icon else self.bot.user.display_avatar.url
        )
        items: list[discord.ui.Item] = [
            discord.ui.Section(
                discord.ui.TextDisplay(f"## {selected.name}\n`{selected.id}`"),
                accessory=discord.ui.Thumbnail(
                    icon_url,
                    description=f"{selected.name} icon",
                ),
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "### Overview\n"
                f"**Owner:** {owner_text}\n"
                f"**Created:** <t:{int(selected.created_at.timestamp())}:F>\n"
                f"**Members:** {selected.member_count or 0:,}\n"
                f"**Verification:** {verification}"
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "### Server Details\n"
                f"**Channels:** {len(_message_channels(selected))}\n"
                f"**Roles:** {max(len(selected.roles) - 1, 0)}\n"
                f"**Emojis:** {len(selected.emojis)}\n"
                f"**Stickers:** {len(selected.stickers)}\n"
                f"**Boosts:** {selected.premium_subscription_count or 0}\n"
                f"**Boost tier:** {selected.premium_tier}"
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"### Features\n{features[:3000]}"),
        ]
        await ctx.send(
            view=ServerInfoView(
                guild=selected,
                author_id=ctx.author.id,
                items=items,
            )
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Guilds(bot))
