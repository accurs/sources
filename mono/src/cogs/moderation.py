from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable

import discord
from discord.ext import commands

from src.services.moderation import Case, Mute, store
from src.cogs.community import MemberPages


logger = logging.getLogger(__name__)
NO_REASON = "N/A"
MAX_REASON_LENGTH = 400
PURGE_FILTERS = {
    "all", "bots", "humans", "attachments", "media", "embeds", "links", "mentions", "user"
}
DELETE_WINDOWS = {
    "0": 0,
    "none": 0,
    "1h": 60 * 60,
    "6h": 6 * 60 * 60,
    "12h": 12 * 60 * 60,
    "1d": 24 * 60 * 60,
    "3d": 3 * 24 * 60 * 60,
    "7d": 7 * 24 * 60 * 60,
}
DURATION_PATTERN = re.compile(r"^(\d+)(s|m|h|d|w)$", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


def clean_reason(reason: str | None) -> str:
    value = (reason or "").strip()
    return value[:MAX_REASON_LENGTH] if value else NO_REASON


def parse_duration(value: str) -> int | None:
    match = DURATION_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]
    seconds = amount * multiplier
    return seconds if seconds > 0 else None


def readable_duration(seconds: int) -> str:
    parts: list[str] = []
    for size, name in ((604800, "week"), (86400, "day"), (3600, "hour"), (60, "minute"), (1, "second")):
        amount, seconds = divmod(seconds, size)
        if amount:
            parts.append(f"{amount} {name}{'' if amount == 1 else 's'}")
        if len(parts) == 2:
            break
    return ", ".join(parts) or "0 seconds"


def card(title: str, details: str) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(discord.ui.TextDisplay(f"## {title}\n{details}")))
    return view


class ConfirmButton(discord.ui.Button):
    def __init__(self, confirm: bool, label: str) -> None:
        super().__init__(
            label=label,
            style=discord.ButtonStyle.danger if confirm else discord.ButtonStyle.secondary,
        )
        self.confirm = confirm

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if isinstance(view, ModerationConfirmView):
            await view.choose(interaction, self.confirm)


class ModerationConfirmView(discord.ui.LayoutView):
    def __init__(
        self,
        *,
        moderator_id: int,
        title: str,
        details: str,
        confirm_label: str,
        action: Callable[[], Awaitable[str]],
    ) -> None:
        super().__init__(timeout=60)
        self.moderator_id = moderator_id
        self.title = title
        self.details = details
        self.confirm_label = confirm_label
        self.action = action
        self.message: discord.Message | None = None
        self.finished = False
        self.render()

    def render(self, result: str | None = None) -> None:
        self.clear_items()
        if result is not None:
            self.add_item(discord.ui.Container(discord.ui.TextDisplay(result)))
            return
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## {self.title}\n{self.details}"),
                discord.ui.Separator(),
                discord.ui.ActionRow(
                    ConfirmButton(True, self.confirm_label),
                    ConfirmButton(False, "Cancel"),
                ),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.moderator_id:
            return True
        await interaction.response.send_message(
            "Only the moderator who started this action can use these buttons.",
            ephemeral=True,
        )
        return False

    async def choose(self, interaction: discord.Interaction, confirm: bool) -> None:
        if self.finished:
            await interaction.response.send_message("This confirmation is no longer active.", ephemeral=True)
            return
        self.finished = True
        self.stop()
        if not confirm:
            self.render("## Action Cancelled\nNo moderation action was taken.")
            await interaction.response.edit_message(view=self)
            return
        await interaction.response.defer()
        try:
            result = await self.action()
        except discord.Forbidden:
            result = "## Action Failed\nDiscord refused the action. Check my permissions and role position."
        except discord.HTTPException as error:
            logger.warning("Confirmed moderation action failed: %s", error)
            result = "## Action Failed\nDiscord could not complete that action."
        self.render(result)
        await interaction.edit_original_response(view=self)

    async def on_timeout(self) -> None:
        if self.finished:
            return
        self.finished = True
        self.render("## Confirmation Expired\nNo moderation action was taken.")
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class Moderation(commands.Cog):
    """Prefix-only server moderation with persistent cases."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._muted_configured: set[int] = set()
        self._mute_tasks: dict[tuple[int, int], asyncio.Task[None]] = {}
        self._restore_mutes_task = asyncio.create_task(self._restore_timed_mutes())

    async def cog_unload(self) -> None:
        self._restore_mutes_task.cancel()
        for task in self._mute_tasks.values():
            task.cancel()
        self._mute_tasks.clear()

    async def _log(self, guild: discord.Guild, title: str, details: str) -> None:
        logging_cog = self.bot.get_cog("Logging")
        sender = getattr(logging_cog, "log_event", None)
        if sender is not None:
            await sender(guild, "moderation", title, details)

    async def _dm_member(self, member: discord.Member, title: str, details: str) -> None:
        try:
            await member.send(view=card(title, f"**Server:** {member.guild.name}\n{details}"))
        except discord.HTTPException:
            pass

    @commands.command(name="modstats", help="Show moderation action totals. Usage: ;modstats [moderator]")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def modstats(self, ctx: commands.Context, moderator: discord.Member | None = None) -> None:
        assert ctx.guild is not None
        stats = await asyncio.to_thread(
            store.moderator_stats, ctx.guild.id, moderator.id if moderator else None
        )
        title = f"Moderation Stats — {moderator.display_name}" if moderator else "Server Moderation Stats"
        await ctx.send(view=card(title, "\n".join((
            f"**Warnings:** `{stats['warn']:,}`",
            f"**Mutes:** `{stats['mute']:,}`",
            f"**Kicks:** `{stats['kick']:,}`",
            f"**Bans:** `{stats['ban']:,}`",
            f"**Removed cases:** `{stats['removed']:,}`",
        ))))

    @staticmethod
    async def _require_target(
        ctx: commands.Context,
        target: discord.Member,
        *,
        allow_self: bool = False,
    ) -> bool:
        guild = ctx.guild
        author = ctx.author
        if guild is None or not isinstance(author, discord.Member):
            return False
        if not allow_self and target.id == author.id:
            await ctx.send("You cannot use that action on yourself.")
            return False
        if target.id == guild.owner_id:
            await ctx.send("The server owner cannot be targeted.")
            return False
        if target.id == ctx.bot.user.id:
            await ctx.send("I cannot moderate myself.")
            return False
        if author.id != guild.owner_id and target.top_role >= author.top_role:
            await ctx.send("That member has an equal or higher role than you.")
            return False
        bot_member = guild.me
        if bot_member is None or target.top_role >= bot_member.top_role:
            await ctx.send("That member has an equal or higher role than me.")
            return False
        return True

    async def _new_case(
        self,
        ctx: commands.Context,
        action: str,
        target: discord.abc.User | None,
        reason: str,
        *,
        expires_at: int | None = None,
        active: bool = True,
        extra: dict | None = None,
    ) -> Case:
        assert ctx.guild is not None
        return await asyncio.to_thread(
            store.create_case,
            ctx.guild.id,
            action,
            target.id if target else None,
            ctx.author.id,
            reason,
            expires_at=expires_at,
            active=active,
            extra=extra,
        )

    async def _get_muted_role(self, guild: discord.Guild) -> discord.Role:
        role = discord.utils.find(lambda item: item.name.casefold() == "muted", guild.roles)
        if role is None:
            self._muted_configured.discard(guild.id)
            role = await guild.create_role(
                name="Muted",
                permissions=discord.Permissions.none(),
                reason="Muted role required by the moderation system",
            )
        return role

    @staticmethod
    async def _apply_muted_overwrite(channel: discord.abc.GuildChannel, role: discord.Role) -> None:
        overwrite = channel.overwrites_for(role)
        overwrite.send_messages = False
        overwrite.add_reactions = False
        overwrite.create_public_threads = False
        overwrite.create_private_threads = False
        overwrite.send_messages_in_threads = False
        overwrite.speak = False
        overwrite.stream = False
        await channel.set_permissions(role, overwrite=overwrite, reason="Configure Muted role")

    async def _configure_muted_role(self, guild: discord.Guild, role: discord.Role) -> None:
        results = await asyncio.gather(
            *(self._apply_muted_overwrite(channel, role) for channel in guild.channels),
            return_exceptions=True,
        )
        failures = sum(isinstance(result, Exception) for result in results)
        if failures:
            logger.warning("Could not configure Muted role in %d channel(s) in %s", failures, guild.id)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        role = discord.utils.find(lambda item: item.name.casefold() == "muted", channel.guild.roles)
        if role is None:
            return
        try:
            await self._apply_muted_overwrite(channel, role)
        except discord.HTTPException:
            logger.warning("Could not configure Muted role in new channel %s", channel.id)

    async def _restore_timed_mutes(self) -> None:
        await self.bot.wait_until_ready()
        for mute in await asyncio.to_thread(store.timed_mutes):
            self._schedule_mute(mute)

    def _schedule_mute(self, mute: Mute) -> None:
        if mute.expires_at is None:
            return
        key = (mute.guild_id, mute.user_id)
        previous = self._mute_tasks.pop(key, None)
        if previous is not None:
            previous.cancel()
        task = asyncio.create_task(self._wait_for_mute(mute))
        self._mute_tasks[key] = task
        task.add_done_callback(lambda completed, mute_key=key: self._mute_task_done(mute_key, completed))

    def _mute_task_done(
        self,
        key: tuple[int, int],
        task: asyncio.Task[None],
    ) -> None:
        if self._mute_tasks.get(key) is task:
            self._mute_tasks.pop(key, None)
        if not task.cancelled() and (error := task.exception()) is not None:
            logger.error(
                "Timed mute task failed for guild %s user %s",
                *key,
                exc_info=(type(error), error, error.__traceback__),
            )

    def _cancel_mute_task(self, guild_id: int, user_id: int) -> None:
        task = self._mute_tasks.pop((guild_id, user_id), None)
        if task is not None:
            task.cancel()

    async def _wait_for_mute(self, mute: Mute) -> None:
        assert mute.expires_at is not None
        await asyncio.sleep(max(0, mute.expires_at - time.time()))

        current = await asyncio.to_thread(store.get_mute, mute.guild_id, mute.user_id)
        if (
            current is None
            or current.case_number != mute.case_number
            or current.expires_at != mute.expires_at
        ):
            return

        guild = self.bot.get_guild(mute.guild_id)
        if guild is None:
            logger.warning("Could not expire mute in unavailable guild %s", mute.guild_id)
            return
        member = guild.get_member(mute.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(mute.user_id)
            except discord.NotFound:
                member = None
            except discord.HTTPException:
                logger.warning("Could not fetch muted user %s in %s", mute.user_id, mute.guild_id)
                return
        role = guild.get_role(mute.role_id)
        if member is not None and role is not None:
            try:
                await member.remove_roles(role, reason="Timed mute expired")
            except discord.HTTPException:
                logger.warning("Could not remove expired mute from %s in %s", mute.user_id, mute.guild_id)
                return
        await asyncio.to_thread(store.remove_mute, mute.guild_id, mute.user_id)
        await self._log(
            guild,
            "Mute Expired",
            f"**User:** <@{mute.user_id}> (`{mute.user_id}`)\n**Case:** `#{mute.case_number}`",
        )

    @commands.command(name="warn", help="Warn a member. Usage: ;warn <user> [reason]")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "") -> None:
        if not await self._require_target(ctx, member):
            return
        reason = clean_reason(reason)
        case = await self._new_case(ctx, "warn", member, reason)
        await self._dm_member(member, "You Were Warned", f"**Reason:** {reason}\n**Case:** `#{case.case_number}`")
        await self._log(ctx.guild, "Member Warned", f"**User:** {member} (`{member.id}`)\n**Moderator:** {ctx.author}\n**Reason:** {reason}\n**Case:** `#{case.case_number}`")
        await ctx.send(view=card("Member Warned", f"{member.mention}\n**Reason:** {reason}\n**Case:** `#{case.case_number}`"))

    @commands.command(name="mute", aliases=["silence"], help="Mute a member. Usage: ;mute <user> [duration] [reason]")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(manage_roles=True, manage_channels=True)
    async def mute(self, ctx: commands.Context, member: discord.Member, *, details: str = "") -> None:
        if not await self._require_target(ctx, member):
            return
        if member.guild_permissions.administrator:
            await ctx.send("Members with **Administrator** cannot be restricted by a Muted role.")
            return
        tokens = details.split(maxsplit=1)
        duration = parse_duration(tokens[0]) if tokens else None
        if duration is not None:
            reason = clean_reason(tokens[1] if len(tokens) > 1 else "")
        else:
            reason = clean_reason(details)
        expires_at = int(time.time()) + duration if duration else None
        role = await self._get_muted_role(ctx.guild)
        if role >= ctx.guild.me.top_role:
            await ctx.send("Move my role above the `Muted` role, then try again.")
            return
        if ctx.guild.id not in self._muted_configured:
            await self._configure_muted_role(ctx.guild, role)
            self._muted_configured.add(ctx.guild.id)
        await member.add_roles(role, reason=reason)
        case = await self._new_case(ctx, "mute", member, reason, expires_at=expires_at)
        await asyncio.to_thread(store.set_mute, ctx.guild.id, member.id, role.id, case.case_number, expires_at)
        if expires_at is not None:
            self._schedule_mute(
                Mute(ctx.guild.id, member.id, role.id, case.case_number, expires_at)
            )
        else:
            self._cancel_mute_task(ctx.guild.id, member.id)
        duration_text = readable_duration(duration) if duration else "Indefinite"
        await self._dm_member(member, "You Were Muted", f"**Duration:** {duration_text}\n**Reason:** {reason}\n**Case:** `#{case.case_number}`")
        await self._log(ctx.guild, "Member Muted", f"**User:** {member} (`{member.id}`)\n**Moderator:** {ctx.author}\n**Duration:** {duration_text}\n**Reason:** {reason}\n**Case:** `#{case.case_number}`")
        await ctx.send(view=card("Member Muted", f"{member.mention}\n**Duration:** {duration_text}\n**Reason:** {reason}\n**Case:** `#{case.case_number}`"))

    @commands.command(name="unmute", aliases=["unsilence"], help="Unmute a member. Usage: ;unmute <user> [reason]")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member, *, reason: str = "") -> None:
        if not await self._require_target(ctx, member):
            return
        role = discord.utils.find(lambda item: item.name.casefold() == "muted", ctx.guild.roles)
        if role is None or role not in member.roles:
            await ctx.send("That member is not muted.")
            return
        reason = clean_reason(reason)
        self._cancel_mute_task(ctx.guild.id, member.id)
        await member.remove_roles(role, reason=reason)
        await asyncio.to_thread(store.remove_mute, ctx.guild.id, member.id)
        case = await self._new_case(ctx, "unmute", member, reason, active=False)
        await self._dm_member(member, "You Were Unmuted", f"**Reason:** {reason}\n**Case:** `#{case.case_number}`")
        await self._log(ctx.guild, "Member Unmuted", f"**User:** {member} (`{member.id}`)\n**Moderator:** {ctx.author}\n**Reason:** {reason}\n**Case:** `#{case.case_number}`")
        await ctx.send(view=card("Member Unmuted", f"{member.mention}\n**Reason:** {reason}\n**Case:** `#{case.case_number}`"))

    async def _kick_member(self, ctx: commands.Context, member: discord.Member, reason: str) -> str:
        await member.kick(reason=reason)
        case = await self._new_case(ctx, "kick", member, reason, active=False)
        await self._log(ctx.guild, "Member Kicked", f"**User:** {member} (`{member.id}`)\n**Moderator:** {ctx.author}\n**Reason:** {reason}\n**Case:** `#{case.case_number}`")
        return f"## Member Kicked\n{member} (`{member.id}`)\n**Reason:** {reason}\n**Case:** `#{case.case_number}`"

    @commands.command(name="kick", help="Kick a member. Usage: ;kick <user> [reason]")
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "") -> None:
        if not await self._require_target(ctx, member):
            return
        reason = clean_reason(reason)
        if member.premium_since is None:
            result = await self._kick_member(ctx, member, reason)
            await ctx.send(view=card("Member Kicked", result.removeprefix("## Member Kicked\n")))
            return
        view = ModerationConfirmView(
            moderator_id=ctx.author.id,
            title="Confirm Kick",
            details=f"**User:** {member} (`{member.id}`)\n**Reason:** {reason}\n\n⚠️ **This member is currently boosting the server.**",
            confirm_label="Kick",
            action=lambda: self._kick_member(ctx, member, reason),
        )
        view.message = await ctx.send(view=view)

    async def _ban_user(self, ctx: commands.Context, user: discord.User | discord.Member, reason: str, delete_seconds: int, action: str = "ban") -> str:
        await ctx.guild.ban(user, reason=reason, delete_message_seconds=delete_seconds)
        if action == "softban":
            await ctx.guild.unban(user, reason=f"Softban completed by {ctx.author}")
        case = await self._new_case(ctx, action, user, reason, active=action == "ban", extra={"delete_message_seconds": delete_seconds})
        title = "Member Softbanned" if action == "softban" else "Member Banned"
        await self._log(ctx.guild, title, f"**User:** {user} (`{user.id}`)\n**Moderator:** {ctx.author}\n**Reason:** {reason}\n**Messages deleted:** {readable_duration(delete_seconds) if delete_seconds else 'None'}\n**Case:** `#{case.case_number}`")
        return f"## {title}\n{user} (`{user.id}`)\n**Reason:** {reason}\n**Case:** `#{case.case_number}`"

    @commands.command(name="ban", help="Ban a member. Usage: ;ban <user> [none|1h|6h|12h|1d|3d|7d] [reason]")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, details: str = "") -> None:
        if not await self._require_target(ctx, member):
            return
        tokens = details.split(maxsplit=1)
        has_delete_option = bool(tokens and tokens[0].casefold() in DELETE_WINDOWS)
        deletion_key = tokens[0].casefold() if has_delete_option else "none"
        reason = clean_reason(
            tokens[1] if has_delete_option and len(tokens) > 1
            else ("" if has_delete_option else details)
        )
        delete_seconds = DELETE_WINDOWS[deletion_key]
        booster = "\n\n⚠️ **This member is currently boosting the server.**" if member.premium_since else ""
        view = ModerationConfirmView(
            moderator_id=ctx.author.id,
            title="Confirm Ban",
            details=f"**User:** {member} (`{member.id}`)\n**Delete messages:** {deletion_key}\n**Reason:** {reason}{booster}",
            confirm_label="Ban",
            action=lambda: self._ban_user(ctx, member, reason, delete_seconds),
        )
        view.message = await ctx.send(view=view)

    @commands.command(name="softban", help="Softban a member. Usage: ;softban <user> [reason]")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def softban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "") -> None:
        if not await self._require_target(ctx, member):
            return
        reason = clean_reason(reason)
        booster = "\n\n⚠️ **This member is currently boosting the server.**" if member.premium_since else ""
        view = ModerationConfirmView(
            moderator_id=ctx.author.id,
            title="Confirm Softban",
            details=f"**User:** {member} (`{member.id}`)\n**Reason:** {reason}{booster}",
            confirm_label="Softban",
            action=lambda: self._ban_user(ctx, member, reason, 7 * 86400, "softban"),
        )
        view.message = await ctx.send(view=view)

    @commands.command(name="unban", help="Unban a user. Usage: ;unban <user-id> [reason]")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user: discord.User, *, reason: str = "") -> None:
        reason = clean_reason(reason)
        try:
            await ctx.guild.fetch_ban(user)
        except discord.NotFound:
            await ctx.send("That user is not banned from this server.")
            return
        await ctx.guild.unban(user, reason=reason)
        case = await self._new_case(ctx, "unban", user, reason, active=False)
        await self._log(ctx.guild, "Member Unbanned", f"**User:** {user} (`{user.id}`)\n**Moderator:** {ctx.author}\n**Reason:** {reason}\n**Case:** `#{case.case_number}`")
        await ctx.send(view=card("Member Unbanned", f"{user} (`{user.id}`)\n**Reason:** {reason}\n**Case:** `#{case.case_number}`"))

    @commands.command(name="warnings-clear", aliases=["clearwarns", "cw"], help="Clear active warnings. Usage: ;warnings-clear <user> [reason]")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def warnings_clear(self, ctx: commands.Context, member: discord.Member, *, reason: str = "") -> None:
        if not await self._require_target(ctx, member):
            return
        reason = clean_reason(reason)
        cleared = await asyncio.to_thread(store.clear_warnings, ctx.guild.id, member.id)
        case = await self._new_case(ctx, "warnings cleared", member, reason, active=False, extra={"cleared": cleared})
        await self._log(ctx.guild, "Warnings Cleared", f"**User:** {member} (`{member.id}`)\n**Moderator:** {ctx.author}\n**Cleared:** `{cleared}`\n**Reason:** {reason}\n**Case:** `#{case.case_number}`")
        await ctx.send(view=card("Warnings Cleared", f"**User:** {member.mention}\n**Warnings cleared:** `{cleared}`\n**Reason:** {reason}\n**Case:** `#{case.case_number}`"))

    @commands.command(name="purge", aliases=["clear"], help="Delete filtered messages. Usage: ;purge <amount> [filter] [user]")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge(self, ctx: commands.Context, amount: int, filter_name: str = "all", member: discord.Member | None = None) -> None:
        if not 1 <= amount <= 1000:
            await ctx.send("Choose an amount from `1` to `1000`.")
            return
        selected = filter_name.casefold().replace("images/videos", "media")
        if selected not in PURGE_FILTERS:
            await ctx.send("Filters: `all`, `bots`, `humans`, `attachments`, `media`, `embeds`, `links`, `mentions`, `user`.")
            return
        if selected == "user" and member is None:
            await ctx.send("The `user` filter requires a member mention.")
            return

        def matches(message: discord.Message) -> bool:
            # The command invocation is always removed, but it does not count
            # toward the number of earlier messages the moderator requested.
            if message.id == ctx.message.id:
                return True
            if member is not None and message.author.id != member.id:
                return False
            if selected in {"all", "user"}:
                return True
            if selected == "bots":
                return message.author.bot
            if selected == "humans":
                return not message.author.bot
            if selected == "attachments":
                return bool(message.attachments)
            if selected == "media":
                return any(
                    (item.content_type or "").startswith(("image/", "video/"))
                    for item in message.attachments
                )
            if selected == "embeds":
                return bool(message.embeds)
            if selected == "links":
                return bool(URL_PATTERN.search(message.content))
            return bool(message.mentions or message.role_mentions or message.mention_everyone)

        deleted = await ctx.channel.purge(
            limit=amount + 1,
            check=matches,
            reason=f"Purge by {ctx.author}",
        )
        matching_deleted = sum(message.id != ctx.message.id for message in deleted)
        command_deleted = any(message.id == ctx.message.id for message in deleted)
        case = await self._new_case(ctx, "purge", member, NO_REASON, active=False, extra={"searched": amount, "deleted": matching_deleted, "command_deleted": command_deleted, "filter": selected, "channel_id": ctx.channel.id})
        await self._log(ctx.guild, "Messages Purged", f"**Moderator:** {ctx.author}\n**Channel:** {ctx.channel.mention}\n**Searched:** `{amount}`\n**Deleted:** `{matching_deleted}` + command\n**Filter:** `{selected}`\n**User:** {member or 'Any'}\n**Case:** `#{case.case_number}`")
        message = await ctx.send(f"Deleted `{matching_deleted}` matching message(s) plus the purge command.")
        await asyncio.sleep(5)
        try:
            await message.delete()
        except discord.HTTPException:
            pass

    @commands.command(name="slowmode", aliases=["slow"], help="Set slowmode. Usage: ;slowmode <duration>")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, duration: str) -> None:
        seconds = 0 if duration.casefold() in {"0", "0s", "off"} else parse_duration(duration)
        if seconds is None or seconds > 21600:
            await ctx.send("Use a duration between `0s` and `6h`.")
            return
        await ctx.channel.edit(slowmode_delay=seconds, reason=f"Changed by {ctx.author}")
        await self._log(ctx.guild, "Slowmode Changed", f"**Moderator:** {ctx.author}\n**Channel:** {ctx.channel.mention}\n**Duration:** {readable_duration(seconds) if seconds else 'Off'}")
        await ctx.send(f"Slowmode is now **{readable_duration(seconds)}**." if seconds else "Slowmode is now disabled.")

    @commands.command(name="lock", aliases=["lockdown"], help="Lock a channel. Usage: ;lock [channel] [reason]")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context, channel: discord.TextChannel | None = None, *, reason: str = "") -> None:
        target = channel or ctx.channel
        overwrite = target.overwrites_for(ctx.guild.default_role)
        saved = await asyncio.to_thread(
            store.save_lock, ctx.guild.id, target.id, overwrite.send_messages
        )
        if not saved:
            await ctx.send("That channel is already locked through this bot.")
            return
        overwrite.send_messages = False
        reason = clean_reason(reason)
        await target.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=reason)
        await self._log(ctx.guild, "Channel Locked", f"**Moderator:** {ctx.author}\n**Channel:** {target.mention}\n**Reason:** {reason}")
        await ctx.send(f"Locked {target.mention}.")

    @commands.command(name="unlock", help="Unlock a channel. Usage: ;unlock [channel] [reason]")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context, channel: discord.TextChannel | None = None, *, reason: str = "") -> None:
        target = channel or ctx.channel
        found, previous = await asyncio.to_thread(store.pop_lock, ctx.guild.id, target.id)
        if not found:
            await ctx.send("That channel was not locked through this bot.")
            return
        overwrite = target.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = previous
        reason = clean_reason(reason)
        await target.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=reason)
        await self._log(ctx.guild, "Channel Unlocked", f"**Moderator:** {ctx.author}\n**Channel:** {target.mention}\n**Reason:** {reason}")
        await ctx.send(f"Unlocked {target.mention} and restored its previous setting.")

    @commands.command(name="nickname", aliases=["nick"], help="Set or reset a nickname. Usage: ;nickname <user> [nickname] [| reason]")
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def nickname(self, ctx: commands.Context, member: discord.Member, *, details: str = "") -> None:
        if not await self._require_target(ctx, member):
            return
        nickname_text, separator, reason_text = details.partition("|")
        nickname = nickname_text.strip() or None
        if nickname is not None and len(nickname) > 32:
            await ctx.send("Nicknames can contain at most `32` characters.")
            return
        reason = clean_reason(reason_text if separator else "")
        await member.edit(nick=nickname, reason=reason)
        action = "nickname reset" if nickname is None else "nickname changed"
        case = await self._new_case(ctx, action, member, reason, active=False, extra={"nickname": nickname})
        await self._log(ctx.guild, "Nickname Reset" if nickname is None else "Nickname Changed", f"**User:** {member} (`{member.id}`)\n**Moderator:** {ctx.author}\n**Nickname:** {nickname or 'Reset'}\n**Reason:** {reason}\n**Case:** `#{case.case_number}`")
        await ctx.send(f"Reset {member.mention}'s nickname." if nickname is None else f"Changed {member.mention}'s nickname to **{nickname}**.")

    @commands.group(name="role", invoke_without_command=True, help="Toggle a role. Usage: ;role <user> <role> [reason]")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role(self, ctx: commands.Context, member: discord.Member, role: discord.Role, *, reason: str = "") -> None:
        if not await self._require_target(ctx, member):
            return
        if role.is_default() or role.is_bot_managed() or role.is_integration() or role.managed:
            await ctx.send("That role is managed by Discord and cannot be toggled.")
            return
        author = ctx.author
        if author.id != ctx.guild.owner_id and role >= author.top_role:
            await ctx.send("That role is equal to or higher than your highest role.")
            return
        if role >= ctx.guild.me.top_role:
            await ctx.send("That role is equal to or higher than my highest role.")
            return
        reason = clean_reason(reason)
        if role in member.roles:
            await member.remove_roles(role, reason=reason)
            action = "role removed"
        else:
            await member.add_roles(role, reason=reason)
            action = "role added"
        case = await self._new_case(ctx, action, member, reason, active=False, extra={"role_id": role.id})
        await self._log(ctx.guild, action.title(), f"**User:** {member} (`{member.id}`)\n**Role:** {role.name} (`{role.id}`)\n**Moderator:** {ctx.author}\n**Reason:** {reason}\n**Case:** `#{case.case_number}`")
        await ctx.send(f"{action.title()} **{role.name}** {'to' if action == 'role added' else 'from'} {member.mention}.")

    @role.command(name="members", help="List members with a role. Usage: ;role members <role>")
    async def role_members(self, ctx: commands.Context, role: discord.Role) -> None:
        members = sorted(role.members, key=lambda member: member.display_name.casefold())
        view = MemberPages(ctx.author.id, role, members)
        await ctx.send(embed=view.embed(), view=view)

    @commands.command(name="cases", aliases=["modcases"], help="Show a member's cases. Usage: ;cases <user>")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def cases(self, ctx: commands.Context, member: discord.User) -> None:
        cases = await asyncio.to_thread(store.list_cases, ctx.guild.id, member.id, 20)
        if not cases:
            await ctx.send(f"{member.mention} has no moderation cases in this server.")
            return
        lines = [
            f"`#{item.case_number}` **{item.action.title()}** • <t:{item.created_at}:R>\n"
            f"Moderator: <@{item.moderator_id}> • Reason: {item.reason}"
            for item in cases
        ]
        await ctx.send(view=card(f"Cases — {member}", "\n\n".join(lines)[:3800]))

    @commands.group(name="case", aliases=["modcase"], invoke_without_command=True, help="View or manage a case.")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def case(self, ctx: commands.Context) -> None:
        await ctx.send("Use `;case view <number>`, `;case edit-reason <number> <reason>`, or `;case remove <number> [reason]`.")

    @case.command(name="view", help="View one case. Usage: ;case view <number>")
    async def case_view(self, ctx: commands.Context, case_number: int) -> None:
        item = await asyncio.to_thread(store.get_case, ctx.guild.id, case_number)
        if item is None or item.removed:
            await ctx.send("That case does not exist.")
            return
        expiry = f"<t:{item.expires_at}:F> • <t:{item.expires_at}:R>" if item.expires_at else "N/A"
        target = (
            f"<@{item.target_id}> (`{item.target_id}`)"
            if item.target_id is not None else "N/A"
        )
        await ctx.send(view=card(f"Case #{item.case_number}", f"**Action:** {item.action.title()}\n**User:** {target}\n**Moderator:** <@{item.moderator_id}> (`{item.moderator_id}`)\n**Reason:** {item.reason}\n**Created:** <t:{item.created_at}:F>\n**Expires:** {expiry}\n**Active:** {'Yes' if item.active else 'No'}"))

    @case.command(name="edit-reason", help="Edit a case reason. Usage: ;case edit-reason <number> <reason>")
    async def case_edit_reason(self, ctx: commands.Context, case_number: int, *, reason: str) -> None:
        reason = clean_reason(reason)
        if reason == NO_REASON:
            await ctx.send("Enter the new reason.")
            return
        if not await asyncio.to_thread(store.edit_reason, ctx.guild.id, case_number, reason):
            await ctx.send("That case does not exist.")
            return
        await self._log(ctx.guild, "Case Reason Edited", f"**Case:** `#{case_number}`\n**Moderator:** {ctx.author}\n**New reason:** {reason}")
        await ctx.send(f"Updated the reason for case `#{case_number}`.")

    @case.command(name="remove", help="Remove a case. Usage: ;case remove <number> [reason]")
    async def case_remove(self, ctx: commands.Context, case_number: int, *, reason: str = "") -> None:
        reason = clean_reason(reason)
        if not await asyncio.to_thread(store.remove_case, ctx.guild.id, case_number):
            await ctx.send("That case does not exist or was already removed.")
            return
        await self._log(ctx.guild, "Case Removed", f"**Case:** `#{case_number}`\n**Moderator:** {ctx.author}\n**Reason:** {reason}")
        await ctx.send(f"Removed case `#{case_number}`.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
