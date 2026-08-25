from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import discord
from discord.ext import commands

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_SETTINGS_FILE = PROJECT_ROOT / "server_logs.json"
LOG_CATEGORIES = ("moderation", "messages", "members", "server", "voice")
logger = logging.getLogger(__name__)


def _safe(value: object, limit: int = 1400) -> str:
    text = str(value) if value not in (None, "") else "*Empty*"
    return text.replace("```", "`\u200b``")[:limit]


def _chunks(lines: list[str], limit: int = 3500) -> list[str]:
    result: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n\n{line}".strip()
        if current and len(candidate) > limit:
            result.append(current)
            current = line
        else:
            current = candidate
    if current:
        result.append(current)
    return result


class Logging(commands.Cog):
    """Prefix-only configuration and comprehensive server-event logging."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._settings = self._load_settings()
        self._settings_lock = asyncio.Lock()

    @staticmethod
    def _load_settings() -> dict[str, dict]:
        try:
            raw = json.loads(LOG_SETTINGS_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        if not isinstance(raw, dict):
            return {}
        settings: dict[str, dict] = {}
        for guild_id, value in raw.items():
            if isinstance(value, int):
                settings[str(guild_id)] = {"default": value, "categories": {}}
                continue
            if not isinstance(value, dict):
                continue
            default = value.get("default")
            try:
                default = int(default) if default is not None else None
            except (TypeError, ValueError):
                default = None
            categories: dict[str, int | None] = {}
            for category, channel_id in value.get("categories", {}).items():
                if category not in LOG_CATEGORIES:
                    continue
                try:
                    categories[category] = int(channel_id) if channel_id is not None else None
                except (TypeError, ValueError):
                    continue
            settings[str(guild_id)] = {"default": default, "categories": categories}
        return settings

    async def _save_settings(self) -> None:
        payload = json.dumps(self._settings, indent=2, sort_keys=True) + "\n"
        async with self._settings_lock:
            await asyncio.to_thread(
                LOG_SETTINGS_FILE.write_text, payload, encoding="utf-8"
            )

    def _guild_settings(self, guild_id: int) -> dict:
        return self._settings.setdefault(
            str(guild_id), {"default": None, "categories": {}}
        )

    def _channel_for(
        self, guild: discord.Guild, category: str
    ) -> discord.TextChannel | None:
        settings = self._settings.get(str(guild.id))
        if not settings:
            return None
        overrides = settings.get("categories", {})
        channel_id = (
            overrides[category]
            if category in overrides
            else settings.get("default")
        )
        if channel_id is None:
            return None
        channel = guild.get_channel(channel_id)
        return channel if isinstance(channel, discord.TextChannel) else None

    @staticmethod
    def _card(title: str, details: str) -> discord.ui.LayoutView:
        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(discord.ui.TextDisplay(f"## {title}\n{details}"))
        )
        return view

    async def log_event(
        self,
        guild: discord.Guild,
        category: str,
        title: str,
        details: str,
    ) -> None:
        channel = self._channel_for(guild, category)
        if channel is None:
            return
        timestamp = int(discord.utils.utcnow().timestamp())
        view = self._card(
            title,
            f"{details[:3500]}\n\n"
            f"-# {category.title()} • <t:{timestamp}:F> • <t:{timestamp}:R>",
        )
        try:
            await channel.send(
                view=view, allowed_mentions=discord.AllowedMentions.none()
            )
        except discord.HTTPException:
            logger.warning(
                "Could not send %s log to channel %s",
                category,
                channel.id,
                exc_info=True,
            )

    async def _recent_audit_entry(
        self,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        target_id: int,
    ) -> discord.AuditLogEntry | None:
        """Find the matching fresh audit entry when View Audit Log is available."""
        try:
            async for entry in guild.audit_logs(limit=5, action=action):
                if getattr(entry.target, "id", None) != target_id:
                    continue
                age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                if age <= 15:
                    return entry
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    @commands.group(
        name="logs",
        aliases=["log"],
        invoke_without_command=True,
        help="Configure server event logging.",
    )
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def logs(self, ctx: commands.Context) -> None:
        await ctx.send(
            "Use `;logs setup #channel`, `;logs category set <category> #channel`, "
            "`;logs category disable <category>`, `;logs status`, or "
            "`;logs test <category>`."
        )

    @logs.command(
        name="setup",
        help="Set the default log channel. Usage: ;logs setup <channel>",
    )
    async def logs_setup(
        self, ctx: commands.Context, channel: discord.TextChannel
    ) -> None:
        if not channel.permissions_for(ctx.guild.me).send_messages:
            await ctx.send("I cannot send messages in that channel.")
            return
        self._guild_settings(ctx.guild.id)["default"] = channel.id
        await self._save_settings()
        await ctx.send(f"The default logging channel is now {channel.mention}.")

    @logs.group(
        name="category",
        invoke_without_command=True,
        help="Configure one logging category.",
    )
    async def logs_category(self, ctx: commands.Context) -> None:
        await ctx.send(f"Categories: `{', '.join(LOG_CATEGORIES)}`")

    @logs_category.command(
        name="set",
        help="Route a category. Usage: ;logs category set <category> <channel>",
    )
    async def logs_category_set(
        self,
        ctx: commands.Context,
        category: str,
        channel: discord.TextChannel,
    ) -> None:
        category = category.casefold()
        if category not in LOG_CATEGORIES:
            await ctx.send(f"Choose one of: `{', '.join(LOG_CATEGORIES)}`")
            return
        if not channel.permissions_for(ctx.guild.me).send_messages:
            await ctx.send("I cannot send messages in that channel.")
            return
        self._guild_settings(ctx.guild.id)["categories"][category] = channel.id
        await self._save_settings()
        await ctx.send(
            f"`{category.title()}` logs will now go to {channel.mention}."
        )

    @logs_category.command(
        name="disable",
        help="Disable a category. Usage: ;logs category disable <category>",
    )
    async def logs_category_disable(
        self, ctx: commands.Context, category: str
    ) -> None:
        category = category.casefold()
        if category not in LOG_CATEGORIES:
            await ctx.send(f"Choose one of: `{', '.join(LOG_CATEGORIES)}`")
            return
        self._guild_settings(ctx.guild.id)["categories"][category] = None
        await self._save_settings()
        await ctx.send(f"Disabled `{category.title()}` logs.")

    @logs.command(name="disable", help="Disable all logging in this server.")
    async def logs_disable(self, ctx: commands.Context) -> None:
        removed = self._settings.pop(str(ctx.guild.id), None)
        await self._save_settings()
        await ctx.send(
            "Logging is now disabled."
            if removed
            else "Logging was already disabled."
        )

    @logs.command(name="status", help="Show logging destinations.")
    async def logs_status(self, ctx: commands.Context) -> None:
        settings = self._settings.get(str(ctx.guild.id), {})
        default_id = settings.get("default")
        default = ctx.guild.get_channel(default_id) if default_id else None
        lines = [f"**Default:** {default.mention if default else 'Disabled'}"]
        overrides = settings.get("categories", {})
        for category in LOG_CATEGORIES:
            if category not in overrides:
                destination = "Default"
            elif overrides[category] is None:
                destination = "Disabled"
            else:
                channel = ctx.guild.get_channel(overrides[category])
                destination = channel.mention if channel else "Missing channel"
            lines.append(f"**{category.title()}:** {destination}")
        await ctx.send(view=self._card("Logging Status", "\n".join(lines)))

    @logs.command(
        name="test",
        help="Send a test event. Usage: ;logs test <category>",
    )
    async def logs_test(self, ctx: commands.Context, category: str) -> None:
        category = category.casefold()
        if category not in LOG_CATEGORIES:
            await ctx.send(f"Choose one of: `{', '.join(LOG_CATEGORIES)}`")
            return
        if self._channel_for(ctx.guild, category) is None:
            await ctx.send("That category has no active logging channel.")
            return
        await self.log_event(
            ctx.guild,
            category,
            "Logging Test",
            f"**Requested by:** {ctx.author} (`{ctx.author.id}`)\n"
            "This category is configured correctly.",
        )
        await ctx.send(f"Sent a `{category}` test log.")

    @commands.command(
        name="auditlog",
        aliases=["audit"],
        help="Show audit entries. Usage: ;auditlog [limit] [user] [action]",
    )
    @commands.guild_only()
    @commands.has_guild_permissions(view_audit_log=True)
    @commands.bot_has_guild_permissions(view_audit_log=True)
    async def auditlog(
        self,
        ctx: commands.Context,
        limit: int = 10,
        user: discord.User | None = None,
        *,
        action: str = "",
    ) -> None:
        if not 1 <= limit <= 50:
            await ctx.send("Choose a limit from `1` to `50`.")
            return
        entries = [
            entry
            async for entry in ctx.guild.audit_logs(
                limit=100 if (user or action) else limit
            )
        ]
        query = action.casefold().replace(" ", "_")
        filtered = []
        for entry in entries:
            if user is not None and getattr(entry.target, "id", None) != user.id:
                continue
            if query and query not in str(entry.action).casefold():
                continue
            filtered.append(entry)
            if len(filtered) >= limit:
                break
        lines = [
            f"**{str(entry.action).replace('_', ' ').title()}** • "
            f"<t:{int(entry.created_at.timestamp())}:R>\n"
            f"Actor: {entry.user or 'Unknown'} • Target: {entry.target or 'Unknown'}\n"
            f"Reason: {entry.reason or 'N/A'}"
            for entry in filtered
        ]
        view = discord.ui.LayoutView()
        for index, chunk in enumerate(_chunks(lines) or ["No matching entries found."]):
            heading = f"## Audit Log — {ctx.guild.name}\n" if index == 0 else ""
            view.add_item(
                discord.ui.Container(discord.ui.TextDisplay(f"{heading}{chunk}"))
            )
        await ctx.send(view=view)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        attachments = "\n".join(item.url for item in message.attachments) or "None"
        await self.log_event(
            message.guild,
            "messages",
            "Message Deleted",
            f"**Author:** {message.author} (`{message.author.id}`)\n"
            f"**Channel:** {message.channel.mention}\n"
            f"**Attachments:** {_safe(attachments)}\n"
            f"**Content:**\n{_safe(message.content)}",
        )

    @commands.Cog.listener()
    async def on_bulk_message_delete(
        self, messages: list[discord.Message]
    ) -> None:
        if not messages or messages[0].guild is None:
            return
        await self.log_event(
            messages[0].guild,
            "messages",
            "Messages Bulk Deleted",
            f"**Channel:** {messages[0].channel.mention}\n"
            f"**Cached messages:** `{len(messages)}`",
        )

    @commands.Cog.listener()
    async def on_message_edit(
        self, before: discord.Message, after: discord.Message
    ) -> None:
        if (
            before.guild is None
            or before.author.bot
            or before.content == after.content
        ):
            return
        await self.log_event(
            before.guild,
            "messages",
            "Message Edited",
            f"**Author:** {before.author} (`{before.author.id}`)\n"
            f"**Channel:** {before.channel.mention}\n"
            f"**Message:** [Jump to message]({after.jump_url})\n"
            f"**Before:**\n{_safe(before.content)}\n\n"
            f"**After:**\n{_safe(after.content)}",
        )

    @commands.Cog.listener()
    async def on_guild_channel_pins_update(
        self,
        channel: discord.abc.GuildChannel,
        last_pin: object,
    ) -> None:
        await self.log_event(
            channel.guild,
            "messages",
            "Channel Pins Updated",
            f"**Channel:** {channel.mention}\n**Last pin:** {last_pin or 'N/A'}",
        )

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        await self.log_event(
            thread.guild,
            "messages",
            "Thread Created",
            f"**Thread:** {thread.mention}\n**Owner:** <@{thread.owner_id}>\n"
            f"**ID:** `{thread.id}`",
        )

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread) -> None:
        await self.log_event(
            thread.guild,
            "messages",
            "Thread Deleted",
            f"**Thread:** {thread.name}\n**ID:** `{thread.id}`",
        )

    @commands.Cog.listener()
    async def on_thread_update(
        self, before: discord.Thread, after: discord.Thread
    ) -> None:
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** {before.name} → {after.name}")
        if before.archived != after.archived:
            changes.append(f"**Archived:** {before.archived} → {after.archived}")
        if before.locked != after.locked:
            changes.append(f"**Locked:** {before.locked} → {after.locked}")
        if changes:
            await self.log_event(
                after.guild,
                "messages",
                "Thread Updated",
                f"**Thread:** {after.mention}\n" + "\n".join(changes),
            )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self.log_event(
            member.guild,
            "members",
            "Member Joined",
            f"**User:** {member} (`{member.id}`)\n"
            f"**Account created:** <t:{int(member.created_at.timestamp())}:F>",
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await asyncio.sleep(1)
        kick = await self._recent_audit_entry(
            member.guild, discord.AuditLogAction.kick, member.id
        )
        if kick is not None:
            if getattr(kick.user, "id", None) != getattr(self.bot.user, "id", None):
                await self.log_event(
                    member.guild,
                    "moderation",
                    "Member Kicked",
                    f"**User:** {member} (`{member.id}`)\n"
                    f"**Moderator:** {kick.user or 'Unknown'}\n"
                    f"**Reason:** {kick.reason or 'N/A'}",
                )
            return
        roles = ", ".join(role.name for role in member.roles[1:]) or "None"
        await self.log_event(
            member.guild,
            "members",
            "Member Left",
            f"**User:** {member} (`{member.id}`)\n**Roles:** {roles}",
        )

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        changes = []
        if before.nick != after.nick:
            changes.append(
                f"**Nickname:** {before.nick or 'None'} → {after.nick or 'None'}"
            )
        before_roles = {role.id: role for role in before.roles}
        after_roles = {role.id: role for role in after.roles}
        added = [
            role.mention
            for role_id, role in after_roles.items()
            if role_id not in before_roles
        ]
        removed = [
            role.mention
            for role_id, role in before_roles.items()
            if role_id not in after_roles
        ]
        if added:
            changes.append(f"**Roles added:** {', '.join(added)}")
        if removed:
            changes.append(f"**Roles removed:** {', '.join(removed)}")
        if before.timed_out_until != after.timed_out_until:
            changes.append(
                f"**Timeout:** {before.timed_out_until or 'None'} → "
                f"{after.timed_out_until or 'None'}"
            )
        if changes:
            await self.log_event(
                after.guild,
                "members",
                "Member Updated",
                f"**User:** {after} (`{after.id}`)\n" + "\n".join(changes),
            )

    @commands.Cog.listener()
    async def on_member_ban(
        self, guild: discord.Guild, user: discord.User
    ) -> None:
        await asyncio.sleep(1)
        entry = await self._recent_audit_entry(
            guild, discord.AuditLogAction.ban, user.id
        )
        if entry is not None and getattr(entry.user, "id", None) == getattr(self.bot.user, "id", None):
            return
        await self.log_event(
            guild,
            "moderation",
            "Member Banned",
            f"**User:** {user} (`{user.id}`)\n"
            f"**Moderator:** {entry.user if entry else 'Unknown'}\n"
            f"**Reason:** {entry.reason if entry and entry.reason else 'N/A'}",
        )

    @commands.Cog.listener()
    async def on_member_unban(
        self, guild: discord.Guild, user: discord.User
    ) -> None:
        await asyncio.sleep(1)
        entry = await self._recent_audit_entry(
            guild, discord.AuditLogAction.unban, user.id
        )
        if entry is not None and getattr(entry.user, "id", None) == getattr(self.bot.user, "id", None):
            return
        await self.log_event(
            guild,
            "moderation",
            "Member Unbanned",
            f"**User:** {user} (`{user.id}`)\n"
            f"**Moderator:** {entry.user if entry else 'Unknown'}\n"
            f"**Reason:** {entry.reason if entry and entry.reason else 'N/A'}",
        )

    @commands.Cog.listener()
    async def on_guild_channel_create(
        self, channel: discord.abc.GuildChannel
    ) -> None:
        await self.log_event(
            channel.guild,
            "server",
            "Channel Created",
            f"**Channel:** {channel.name}\n**Type:** {channel.type}\n"
            f"**ID:** `{channel.id}`",
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(
        self, channel: discord.abc.GuildChannel
    ) -> None:
        await self.log_event(
            channel.guild,
            "server",
            "Channel Deleted",
            f"**Channel:** {channel.name}\n**Type:** {channel.type}\n"
            f"**ID:** `{channel.id}`",
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** {before.name} → {after.name}")
        if before.position != after.position:
            changes.append(f"**Position:** {before.position} → {after.position}")
        if before.overwrites != after.overwrites:
            changes.append("**Permission overwrites changed**")
        if changes:
            await self.log_event(
                after.guild,
                "server",
                "Channel Updated",
                f"**Channel:** {after.mention}\n" + "\n".join(changes),
            )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        await self.log_event(
            role.guild,
            "server",
            "Role Created",
            f"**Role:** {role.mention}\n**ID:** `{role.id}`",
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await self.log_event(
            role.guild,
            "server",
            "Role Deleted",
            f"**Role:** {role.name}\n**ID:** `{role.id}`",
        )

    @commands.Cog.listener()
    async def on_guild_role_update(
        self, before: discord.Role, after: discord.Role
    ) -> None:
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** {before.name} → {after.name}")
        if before.permissions != after.permissions:
            changes.append("**Permissions changed**")
        if before.colour != after.colour:
            changes.append(f"**Color:** {before.colour} → {after.colour}")
        if changes:
            await self.log_event(
                after.guild,
                "server",
                "Role Updated",
                f"**Role:** {after.mention}\n" + "\n".join(changes),
            )

    @commands.Cog.listener()
    async def on_guild_update(
        self, before: discord.Guild, after: discord.Guild
    ) -> None:
        changes = []
        for label, old, new in (
            ("Name", before.name, after.name),
            ("Description", before.description, after.description),
            ("Verification level", before.verification_level, after.verification_level),
            ("AFK channel", before.afk_channel, after.afk_channel),
        ):
            if old != new:
                changes.append(f"**{label}:** {old or 'None'} → {new or 'None'}")
        if changes:
            await self.log_event(
                after, "server", "Server Updated", "\n".join(changes)
            )

    @commands.Cog.listener()
    async def on_guild_emojis_update(
        self,
        guild: discord.Guild,
        before: tuple[discord.Emoji, ...],
        after: tuple[discord.Emoji, ...],
    ) -> None:
        await self.log_event(
            guild,
            "server",
            "Emojis Updated",
            f"**Before:** `{len(before)}`\n**After:** `{len(after)}`",
        )

    @commands.Cog.listener()
    async def on_guild_stickers_update(
        self,
        guild: discord.Guild,
        before: tuple[discord.GuildSticker, ...],
        after: tuple[discord.GuildSticker, ...],
    ) -> None:
        await self.log_event(
            guild,
            "server",
            "Stickers Updated",
            f"**Before:** `{len(before)}`\n**After:** `{len(after)}`",
        )

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if invite.guild is not None:
            await self.log_event(
                invite.guild,
                "server",
                "Invite Created",
                f"**Code:** `{invite.code}`\n**Channel:** {invite.channel}\n"
                f"**Creator:** {invite.inviter or 'Unknown'}\n"
                f"**Uses:** `{invite.max_uses or 'Unlimited'}`",
            )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if invite.guild is not None:
            await self.log_event(
                invite.guild,
                "server",
                "Invite Deleted",
                f"**Code:** `{invite.code}`\n**Channel:** {invite.channel}",
            )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        changes = []
        if before.channel != after.channel:
            before_channel = before.channel.mention if before.channel else "None"
            after_channel = after.channel.mention if after.channel else "None"
            changes.append(f"**Channel:** {before_channel} → {after_channel}")
        for label, old, new in (
            ("Server muted", before.mute, after.mute),
            ("Server deafened", before.deaf, after.deaf),
            ("Streaming", before.self_stream, after.self_stream),
            ("Camera", before.self_video, after.self_video),
        ):
            if old != new:
                changes.append(f"**{label}:** {old} → {new}")
        if changes:
            await self.log_event(
                member.guild,
                "voice",
                "Voice State Updated",
                f"**User:** {member} (`{member.id}`)\n" + "\n".join(changes),
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Logging(bot))
