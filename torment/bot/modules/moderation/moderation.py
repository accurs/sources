from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.helpers.context import TormentContext, _color
from bot.helpers.moderation import is_clear_token


class Moderation(commands.Cog):
    __cog_name__ = "moderation"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.nuke_task.start()

    def cog_unload(self) -> None:
        self.nuke_task.cancel()

    @tasks.loop(minutes=5)
    async def nuke_task(self) -> None:
        pool = self.bot.storage.pool
        if not pool:
            return
        rows = await pool.fetch(
            """
            UPDATE nuke_schedule SET next_trigger = next_trigger + interval
            WHERE next_trigger <= NOW()
            RETURNING guild_id, channel_id, interval
            """
        )
        to_delete = []
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if not guild:
                to_delete.append((row["guild_id"], row["channel_id"]))
                continue
            channel = guild.get_channel(row["channel_id"])
            if not isinstance(channel, discord.TextChannel):
                to_delete.append((row["guild_id"], row["channel_id"]))
                continue
            try:
                interval_str = _fmt_delta(row["interval"])
                new_channel = await channel.clone(reason=f"Scheduled nuke every {interval_str}")
                synced = await _reconfigure_channel_settings(pool, guild, channel, new_channel)
                await asyncio.gather(
                    new_channel.edit(position=channel.position),
                    channel.delete(reason=f"Scheduled nuke every {interval_str}"),
                )
                embed = discord.Embed(
                    title="Channel Nuked",
                    description=f"This channel was automatically nuked (every **{interval_str}**)",
                    color=_color("EMBED_SUCCESS_COLOR"),
                )
                if synced:
                    embed.add_field(name="Settings Synced", value=">>> " + "\n".join(synced))
                try:
                    await new_channel.send(embed=embed)
                except discord.HTTPException:
                    pass
            except discord.HTTPException:
                to_delete.append((row["guild_id"], row["channel_id"]))
        if to_delete:
            await pool.executemany(
                "DELETE FROM nuke_schedule WHERE guild_id = $1 AND channel_id = $2",
                to_delete,
            )

    @nuke_task.before_loop
    async def before_nuke_task(self) -> None:
        await self.bot.wait_until_ready()

    @property
    def storage(self):
        return self.bot.storage

    def audit_reason(self, ctx: TormentContext, reason: str | None) -> str:
        base = reason or "no reason provided"
        return f"{base} | executed by {ctx.author} ({ctx.author.id})"

    def display_target(self, target: discord.abc.Snowflake | None, fallback: str) -> str:
        if isinstance(target, (discord.Member, discord.User)):
            return f"{target} ({target.id})"
        if isinstance(target, discord.Role):
            return f"{target.name} ({target.id})"
        if isinstance(target, discord.abc.GuildChannel):
            return f"#{target.name} ({target.id})"
        return fallback

    def discord_timestamp(self, value: Any, style: str = "f") -> str:
        if hasattr(value, "timestamp"):
            return f"<t:{int(value.timestamp())}:{style}>"
        return "unknown"

    def case_metadata_lines(self, case: dict[str, Any]) -> list[str]:
        metadata = case.get("metadata") or {}
        lines: list[str] = []
        for key, value in metadata.items():
            label = key.replace("_", " ").strip().title()
            lines.append(f"**{label}:** {value}")
        return lines

    async def get_config(self, guild_id: int) -> dict[str, Any]:
        return await self.storage.get_config(guild_id)

    async def ensure_member_target(self, ctx: TormentContext, member: discord.Member) -> bool:
        if not ctx.guild:
            return False
        if member.id == ctx.guild.owner_id:
            await ctx.warn(f"I can't moderate {member.mention} because they're the **server owner**.")
            return False
        if ctx.guild.owner_id != ctx.author.id and member.top_role >= ctx.author.top_role:
            await ctx.warn(f"I can't moderate {member.mention} because your **highest role** is not above theirs.")
            return False
        bot_member = ctx.guild.me
        if not bot_member:
            await ctx.warn("I couldn't resolve my member state.")
            return False
        if member.top_role >= bot_member.top_role:
            await ctx.warn(f"I can't moderate {member.mention} because my **highest role** is not above theirs.")
            return False
        return True

    async def ensure_role_assignable(self, ctx: TormentContext, role: discord.Role) -> bool:
        if not ctx.guild:
            return False
        bot_member = ctx.guild.me
        if not bot_member:
            await ctx.warn("I couldn't resolve my member state.")
            return False
        if role.managed:
            await ctx.warn(f"I can't manage {role.mention} because it is **managed**.")
            return False
        if role >= bot_member.top_role:
            await ctx.warn(f"I can't manage {role.mention} because my **highest role** is not above it.")
            return False
        return True

    async def send_modlog_case(self, ctx: TormentContext, case: dict[str, Any]) -> None:
        if not ctx.guild:
            return
        config = await self.get_config(ctx.guild.id)
        channel_id = config.get("modlog_channel_id")
        if not channel_id:
            return
        channel = ctx.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        reason = case["reason"] or "no reason provided"
        embed = discord.Embed(color=_color("EMBED_INFO_COLOR"))
        embed.set_author(name=f"Case #{case['id']}")
        lines = [
            f"**Action:** {case['action']}",
            f"**User:** {case['target_name']}",
            f"**Moderator:** {case['moderator_name']}",
            f"> **Reason:** {reason}",
            f"> **Created:** {self.discord_timestamp(case['created_at'])}",
        ]
        lines.extend(f"> {line}" for line in self.case_metadata_lines(case))
        embed.description = "\n".join(lines)
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            return

    async def create_case(
        self,
        ctx: TormentContext,
        *,
        action: str,
        target: discord.abc.Snowflake | None,
        fallback_name: str,
        reason: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not ctx.guild:
            raise RuntimeError("guild context required")
        case = await self.storage.create_case(
            guild_id=ctx.guild.id,
            action=action,
            target_id=getattr(target, "id", None),
            target_name=self.display_target(target, fallback_name),
            moderator_id=ctx.author.id,
            moderator_name=f"{ctx.author} ({ctx.author.id})",
            reason=reason,
            metadata=metadata,
        )
        await self.send_modlog_case(ctx, case)
        return case

    async def send_dm_notification(
        self,
        target: discord.User | discord.Member,
        *,
        action: str,
        guild: discord.Guild,
        moderator: discord.Member | discord.User,
        reason: str | None,
        duration: str | None = None,
    ) -> bool:
        try:
            action_titles = {
                "warned": "Warned",
                "kicked": "Kicked",
                "banned": "Banned",
                "unbanned": "Unbanned",
                "muted": "Muted",
                "unmuted": "Unmuted",
                "timed out": "Timed Out",
                "timeout removed": "Timeout Removed",
                "softbanned": "Softbanned",
                "hardbanned": "Hardbanned",
                "image muted": "Image Muted",
                "image unmuted": "Image Unmuted",
                "reaction muted": "Reaction Muted",
                "reaction unmuted": "Reaction Unmuted",
                "stripped staff": "Staff Roles Removed",
            }
            
            title = action_titles.get(action.lower(), action.title())
            
            embed = discord.Embed(color=_color("EMBED_DENY_COLOR"))
            embed.title = title
            
            if action.lower() in ["timeout removed", "unmuted", "unbanned", "image unmuted", "reaction unmuted"]:
                description = f"Your {action.lower().replace('removed', '').replace('un', '').strip()} was removed in **{guild.name}**"
            else:
                description = f"You have been {action.lower()} in **{guild.name}**"
            
            embed.description = description
            
            embed.add_field(name="Moderator", value=moderator.name, inline=True)
            
            if duration:
                embed.add_field(name="Duration", value=duration, inline=True)
            
            embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            
            from discord.utils import utcnow, format_dt
            timestamp = utcnow()
            embed.description += f"\n\nIf you would like to dispute this punishment, contact a staff member. • {format_dt(timestamp, style='f')}"
            
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)
            
            await target.send(embed=embed)
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    async def resolve_user(self, ctx: TormentContext, token: str) -> discord.User | discord.Member | None:
        try:
            return await commands.MemberConverter().convert(ctx, token)
        except commands.BadArgument:
            pass
        try:
            return await commands.UserConverter().convert(ctx, token)
        except commands.BadArgument:
            pass
        raw = token.strip()
        if raw.startswith("<@") and raw.endswith(">"):
            raw = raw.replace("<@", "").replace("!", "").replace(">", "")
        if raw.isdigit():
            try:
                return await self.bot.fetch_user(int(raw))
            except discord.HTTPException:
                return None
        return None

    async def ban_user(
        self,
        guild: discord.Guild,
        user: discord.abc.Snowflake,
        *,
        reason: str,
        delete_seconds: int,
    ) -> None:
        try:
            await guild.ban(user, reason=reason, delete_message_seconds=delete_seconds)
            return
        except TypeError:
            pass

        delete_days = max(0, min(7, delete_seconds // 86400))
        try:
            await guild.ban(user, reason=reason, delete_message_days=delete_days)
            return
        except TypeError:
            pass

        await guild.ban(user, reason=reason)

    async def resolve_channel(self, ctx: TormentContext, token: str | None) -> discord.TextChannel | discord.CategoryChannel | None:
        if not ctx.guild or not token:
            return None
        raw = token.strip()
        if raw.startswith("<#") and raw.endswith(">"):
            raw = raw[2:-1]
        if raw.isdigit():
            channel = ctx.guild.get_channel(int(raw))
            if isinstance(channel, (discord.TextChannel, discord.CategoryChannel)):
                return channel
        lowered = raw.lower()
        for channel in ctx.guild.channels:
            if isinstance(channel, (discord.TextChannel, discord.CategoryChannel)) and channel.name.lower() == lowered:
                return channel
        return None

    async def resolve_visibility_target(
        self,
        ctx: TormentContext,
        token: str | None,
    ) -> discord.Role | discord.Member | None:
        if not ctx.guild or not token:
            return None
        try:
            return await commands.RoleConverter().convert(ctx, token)
        except commands.BadArgument:
            pass
        try:
            return await commands.MemberConverter().convert(ctx, token)
        except commands.BadArgument:
            return None

    async def apply_forced_nickname(self, member: discord.Member) -> None:
        if not member.guild.me or member.guild.me.top_role <= member.top_role:
            return
        record = await self.storage.get_forced_nickname(member.guild.id, member.id)
        if not record:
            return
        nickname = record["nickname"]
        if member.nick == nickname:
            return
        try:
            await member.edit(nick=nickname, reason="forced nickname sync")
        except discord.HTTPException:
            return

    def case_summary(self, case: dict[str, Any]) -> str:
        reason = case["reason"] or "no reason provided"
        lines = [
            f"`#{case['id']}` **{case['action']}** - {case['target_name']}\n"
            f"> Moderator: {case['moderator_name']}\n"
            f"> Reason: {reason}"
        ]
        lines.extend(f"> {line}" for line in self.case_metadata_lines(case))
        return "\n".join(lines)

    async def send_case_pages(self, ctx: TormentContext, title: str, cases: list[dict[str, Any]]) -> None:
        if not cases:
            await ctx.warn("No **cases** were found.")
            return
        pages: list[discord.Embed] = []
        chunk_size = 5
        for index in range(0, len(cases), chunk_size):
            chunk = cases[index:index + chunk_size]
            embed = discord.Embed(
                title=title,
                description="\n\n".join(self.case_summary(case) for case in chunk),
                color=_color("EMBED_INFO_COLOR"),
            )
            pages.append(embed)
        total = len(pages)
        for page_index, page in enumerate(pages, start=1):
            page.set_footer(text=f"Page {page_index}/{total} ({len(cases)} entries)")
        await ctx.paginate(pages)

    async def apply_configured_role_action(
        self,
        ctx: TormentContext,
        member: discord.Member,
        *,
        config_key: str,
        role_label: str,
        action: str,
        success_msg: str,
        reason: str | None,
        remove: bool = False,
    ) -> None:
        if not ctx.guild:
            return
        if not await self.ensure_member_target(ctx, member):
            return
        config = await self.get_config(ctx.guild.id)
        role_id = config.get(config_key)
        if not role_id:
            await ctx.warn(f"The **{role_label}** role is **not configured**.")
            return
        role = ctx.guild.get_role(role_id)
        if not role:
            await ctx.warn(f"The configured **{role_label}** role no longer exists.")
            return
        if not await self.ensure_role_assignable(ctx, role):
            return

        try:
            if remove:
                await member.remove_roles(role, reason=self.audit_reason(ctx, reason))
            else:
                await member.add_roles(role, reason=self.audit_reason(ctx, reason))
        except discord.Forbidden:
            await ctx.warn("I couldn't update roles because I'm **missing permissions**.")
            return
        except discord.HTTPException:
            await ctx.warn("I couldn't update roles.")
            return

        await self.send_dm_notification(
            member,
            action=action,
            guild=ctx.guild,
            moderator=ctx.author,
            reason=reason,
        )

        case = await self.create_case(
            ctx,
            action=action,
            target=member,
            fallback_name=f"{member} ({member.id})",
            reason=reason,
            metadata={"role": role.name},
        )
        message = success_msg.format(target=member.mention, role=role.mention)
        await ctx.success(f"{message} (`#case {case['id']}`) - **{reason or 'no reason provided'}**")

    async def set_visibility(
        self,
        ctx: TormentContext,
        *,
        action: str,
        success_msg: str,
        channel: discord.TextChannel | discord.CategoryChannel,
        target: discord.Role | discord.Member,
        visible: bool,
    ) -> None:
        channels: list[discord.TextChannel]
        if isinstance(channel, discord.CategoryChannel):
            channels = [item for item in channel.channels if isinstance(item, discord.TextChannel)]
        else:
            channels = [channel]
        for item in channels:
            overwrite = item.overwrites_for(target)
            overwrite.view_channel = visible
            await item.set_permissions(target, overwrite=overwrite, reason=self.audit_reason(ctx, None))
            await self.create_case(
                ctx,
                action=action,
                target=item,
                fallback_name=f"#{item.name} ({item.id})",
                reason=f"{target} visibility updated",
                metadata={"subject": getattr(target, 'name', str(target))},
            )
        if isinstance(channel, discord.CategoryChannel):
            label = f"**{channel.name}** ({len(channels)} channels)"
        else:
            label = channel.mention
        target_label = target.mention if hasattr(target, "mention") else f"**{target}**"
        await ctx.success(success_msg.format(channel=label, target=target_label))

    async def set_lock_state(
        self,
        ctx: TormentContext,
        *,
        action: str,
        success_msg: str,
        channel: discord.TextChannel | discord.CategoryChannel,
        locked: bool,
        reason: str | None,
    ) -> None:
        channels: list[discord.TextChannel]
        if isinstance(channel, discord.CategoryChannel):
            channels = [item for item in channel.channels if isinstance(item, discord.TextChannel)]
        else:
            channels = [channel]
        default_role = ctx.guild.default_role if ctx.guild else None
        if not default_role:
            return
        for item in channels:
            overwrite = item.overwrites_for(default_role)
            overwrite.send_messages = not locked
            await item.set_permissions(default_role, overwrite=overwrite, reason=self.audit_reason(ctx, reason))
            await self.create_case(
                ctx,
                action=action,
                target=item,
                fallback_name=f"#{item.name} ({item.id})",
                reason=reason,
            )
        if isinstance(channel, discord.CategoryChannel):
            label = f"**{channel.name}** ({len(channels)} channels)"
        else:
            label = channel.mention
        await ctx.success(success_msg.format(channel=label))

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self.apply_forced_nickname(member)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.nick != after.nick:
            await self.apply_forced_nickname(after)

    @commands.hybrid_group(
        name="setup",
        invoke_without_command=True,
        help="Set up moderation channels and roles for your server",
        extras={"parameters": "n/a", "usage": "setup"},
    )
    @commands.has_permissions(manage_guild=True)
    async def setup_group(self, ctx: TormentContext) -> None:
        if not ctx.guild:
            return

        config = await self.get_config(ctx.guild.id)
        if all([
            config.get("modlog_channel_id"),
            config.get("muted_role_id"),
            config.get("image_muted_role_id"),
            config.get("reaction_muted_role_id")
        ]):
            await ctx.warn("Moderation is already set up. Use `setup view` to see the current configuration or use subcommands to modify specific settings.")
            return

        bot_member = ctx.guild.me
        if not bot_member:
            await ctx.warn("I couldn't resolve my member state.")
            return
        if not bot_member.guild_permissions.manage_roles:
            await ctx.warn("I'm **missing** permission(s): `manage roles`.")
            return
        if not bot_member.guild_permissions.manage_channels:
            await ctx.warn("I'm **missing** permission(s): `manage channels`.")
            return

        modlog_channel, created_modlog = await self.ensure_modlog_channel(ctx)
        muted_role, created_muted = await self.ensure_named_role(ctx, "Muted")
        image_muted_role, created_image_muted = await self.ensure_named_role(ctx, "Image Muted")
        reaction_muted_role, created_reaction_muted = await self.ensure_named_role(ctx, "Reaction Muted")

        await self.storage.set_config_value(ctx.guild.id, "modlog_channel_id", modlog_channel.id)
        await self.storage.set_config_value(ctx.guild.id, "muted_role_id", muted_role.id)
        await self.storage.set_config_value(ctx.guild.id, "image_muted_role_id", image_muted_role.id)
        await self.storage.set_config_value(ctx.guild.id, "reaction_muted_role_id", reaction_muted_role.id)

        configured: list[str] = []
        configured.append("**modlog channel**")
        configured.append("**Muted** role")
        configured.append("**Image Muted** role")
        configured.append("**Reaction Muted** role")

        created: list[str] = []
        if created_modlog:
            created.append(modlog_channel.mention)
        if created_muted:
            created.append(muted_role.mention)
        if created_image_muted:
            created.append(image_muted_role.mention)
        if created_reaction_muted:
            created.append(reaction_muted_role.mention)

        message = f"set up {self.human_join(configured)}"
        if created:
            message += f" and created {self.human_join(created)}"
        await ctx.success(message)

    def human_join(self, parts: list[str]) -> str:
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return f"{parts[0]} and {parts[1]}"
        return ", ".join(parts[:-1]) + f", and {parts[-1]}"

    async def ensure_modlog_channel(self, ctx: TormentContext) -> tuple[discord.TextChannel, bool]:
        if not ctx.guild:
            raise RuntimeError("guild context required")

        existing_names = {"modlog", "mod-log", "moderation-log", "moderation-logs"}
        for channel in ctx.guild.text_channels:
            if channel.name.lower() in existing_names:
                return channel, False

        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        }
        for role in ctx.guild.roles:
            if role.permissions.administrator or role.permissions.manage_guild or role.permissions.moderate_members:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        channel = await ctx.guild.create_text_channel(
            "mod-log",
            overwrites=overwrites,
            reason=self.audit_reason(ctx, "automatic moderation setup"),
        )
        return channel, True

    async def ensure_named_role(self, ctx: TormentContext, name: str) -> tuple[discord.Role, bool]:
        if not ctx.guild:
            raise RuntimeError("guild context required")

        lowered = name.lower()
        for role in ctx.guild.roles:
            if role.name.lower() == lowered:
                return role, False

        role = await ctx.guild.create_role(
            name=name,
            reason=self.audit_reason(ctx, "automatic moderation setup"),
        )
        return role, True

    @setup_group.command(
        name="view",
        help="View the current moderation configuration for your server",
        extras={"parameters": "n/a", "usage": "setup view"},
    )
    async def setup_view(self, ctx: TormentContext) -> None:
        if not ctx.guild:
            return
        config = await self.get_config(ctx.guild.id)
        embed = discord.Embed(title="Moderation Setup", color=_color("EMBED_INFO_COLOR"))
        modlog = ctx.guild.get_channel(config["modlog_channel_id"]) if config["modlog_channel_id"] else None
        muted = ctx.guild.get_role(config["muted_role_id"]) if config["muted_role_id"] else None
        imuted = ctx.guild.get_role(config["image_muted_role_id"]) if config["image_muted_role_id"] else None
        rmuted = ctx.guild.get_role(config["reaction_muted_role_id"]) if config["reaction_muted_role_id"] else None
        embed.description = "\n".join(
            [
                f"**Modlog:** {modlog.mention if modlog else 'not set'}",
                f"**Muted:** {muted.mention if muted else 'not set'}",
                f"**Image Muted:** {imuted.mention if imuted else 'not set'}",
                f"**Reaction Muted:** {rmuted.mention if rmuted else 'not set'}",
            ]
        )
        await ctx.send(embed=embed)

    @setup_group.command(
        name="modlog",
        help="Set or clear the moderation log channel",
        extras={"parameters": "channel|off", "usage": "setup modlog (channel|off)"},
    )
    async def setup_modlog(self, ctx: TormentContext, target: str) -> None:
        if not ctx.guild:
            return
        if is_clear_token(target):
            await self.storage.set_config_value(ctx.guild.id, "modlog_channel_id", None)
            await ctx.success("Successfully cleared the modlog channel")
            return
        channel = await commands.TextChannelConverter().convert(ctx, target)
        await self.storage.set_config_value(ctx.guild.id, "modlog_channel_id", channel.id)
        await ctx.success(f"Successfully set the **modlog channel** to {channel.mention}")

    @setup_group.command(
        name="muted",
        help="Set or clear the muted role for your server",
        extras={"parameters": "role|off", "usage": "setup muted (role|off)"},
    )
    async def setup_muted(self, ctx: TormentContext, target: str) -> None:
        await self.configure_role(ctx, target, "muted_role_id", "Muted")

    @setup_group.command(
        name="imuted",
        help="Set or clear the image muted role for your server",
        extras={"parameters": "role|off", "usage": "setup imuted (role|off)"},
    )
    async def setup_imuted(self, ctx: TormentContext, target: str) -> None:
        await self.configure_role(ctx, target, "image_muted_role_id", "Image Muted")

    @setup_group.command(
        name="rmuted",
        help="Set or clear the reaction muted role for your server",
        extras={"parameters": "role|off", "usage": "setup rmuted (role|off)"},
    )
    async def setup_rmuted(self, ctx: TormentContext, target: str) -> None:
        await self.configure_role(ctx, target, "reaction_muted_role_id", "Reaction Muted")

    async def configure_role(self, ctx: TormentContext, target: str, field: str, label: str) -> None:
        if not ctx.guild:
            return
        if is_clear_token(target):
            await self.storage.set_config_value(ctx.guild.id, field, None)
            await ctx.success(f"Successfully cleared **{label}**")
            return
        role = await commands.RoleConverter().convert(ctx, target)
        await self.storage.set_config_value(ctx.guild.id, field, role.id)
        await ctx.success(f"Successfully set **{label}** to {role.mention}")

    @commands.hybrid_command(
        name="warn",
        help="Issue a warning to a member for rule violations",
        extras={"parameters": "member, reason", "usage": "warn (member) [reason]"},
    )
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(member="The member to warn", reason="The reason for the warning")
    async def warn(self, ctx: TormentContext, member: discord.Member, *, reason: str | None = None) -> None:
        if not await self.ensure_member_target(ctx, member):
            return
        case = await self.create_case(
            ctx,
            action="warn",
            target=member,
            fallback_name=f"{member} ({member.id})",
            reason=reason,
        )
        await self.send_dm_notification(
            member,
            action="warned",
            guild=ctx.guild,
            moderator=ctx.author,
            reason=reason,
        )
        await ctx.success(f"Successfully warned {member.mention} (`#case {case['id']}`) - **{reason or 'no reason provided'}**")

    @commands.hybrid_command(
        name="warnings",
        aliases=["warns"],
        help="View all warning cases for a specific member",
        extras={"parameters": "member", "usage": "warnings [member]"},
    )
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(member="The member to view warnings for")
    async def warnings(self, ctx: TormentContext, member: discord.Member | None = None) -> None:
        if not ctx.guild:
            return
        cases = await self.storage.list_cases(ctx.guild.id, target_id=getattr(member, "id", None), action="warn")
        title = f"warnings for {member}" if member else "warnings"
        await self.send_case_pages(ctx, title, cases)

    @commands.hybrid_command(
        name="cases",
        aliases=["history", "modlogs"],
        help="View all moderation cases for a specific member",
        extras={"parameters": "member", "usage": "cases [member]"},
    )
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(member="The member to view cases for")
    async def cases(self, ctx: TormentContext, member: discord.Member | None = None) -> None:
        if not ctx.guild:
            return
        cases = await self.storage.list_cases(ctx.guild.id, target_id=getattr(member, "id", None))
        title = f"cases for {member}" if member else "cases"
        await self.send_case_pages(ctx, title, cases)

    @commands.hybrid_command(
        name="case",
        help="View detailed information about a specific moderation case",
        extras={"parameters": "case_id", "usage": "case (case_id)"},
    )
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(case_id="The case ID to view")
    async def case(self, ctx: TormentContext, case_id: int) -> None:
        case = await self.storage.get_case(case_id)
        if not case or (ctx.guild and case["guild_id"] != ctx.guild.id):
            await ctx.warn(f"Case **#{case_id}** does **not** exist.")
            return
        embed = discord.Embed(
            title=f"Case #{case['id']}",
            color=_color("EMBED_INFO_COLOR"),
            description="\n".join([
                f"**Action:** {case['action']}",
                f"**User:** {case['target_name']}",
                f"**Moderator:** {case['moderator_name']}",
                f"**Reason:** {case['reason'] or 'no reason provided'}",
                f"**Created:** {self.discord_timestamp(case['created_at'])}",
            ] + self.case_metadata_lines(case)),
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="reason",
        help="Update the reason for an existing moderation case",
        extras={"parameters": "case_id, reason", "usage": "reason (case_id) (reason)"},
    )
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(case_id="The case ID to update", reason="The new reason")
    async def reason(self, ctx: TormentContext, case_id: int, *, reason: str) -> None:
        case = await self.storage.get_case(case_id)
        if not case or (ctx.guild and case["guild_id"] != ctx.guild.id):
            await ctx.warn(f"Case **#{case_id}** does **not** exist.")
            return
        await self.storage.update_case_reason(case_id, reason)
        await ctx.success(f"Successfully updated case **#{case_id}**")

    @commands.hybrid_command(
        name="kick",
        help="Kick a member from the server",
        extras={"parameters": "member, reason", "usage": "kick (member) [reason]"},
    )
    @commands.has_permissions(kick_members=True)
    @app_commands.describe(member="The member to kick", reason="The reason for the kick")
    async def kick(self, ctx: TormentContext, member: discord.Member, *, reason: str | None = None) -> None:
        if not await self.ensure_member_target(ctx, member):
            return
        try:
            await member.kick(reason=self.audit_reason(ctx, reason))
        except discord.Forbidden:
            await ctx.warn("I couldn't kick that member because I'm **missing permissions**.")
            return
        except discord.HTTPException:
            await ctx.warn("I couldn't kick that member.")
            return
        await self.send_dm_notification(
            member,
            action="kicked",
            guild=ctx.guild,
            moderator=ctx.author,
            reason=reason,
        )
        case = await self.create_case(
            ctx,
            action="kick",
            target=member,
            fallback_name=f"{member} ({member.id})",
            reason=reason,
        )
        await ctx.success(f"Successfully kicked {member.mention} (`#case {case['id']}`) - **{reason or 'no reason provided'}**")

    @commands.hybrid_command(
        name="ban",
        help="Ban a user from the server",
        extras={"parameters": "user, reason", "usage": "ban (user) [reason]"},
    )
    @commands.has_permissions(ban_members=True)
    @app_commands.describe(target="The user to ban (mention, ID, or username)", reason="The reason for the ban")
    async def ban(self, ctx: TormentContext, target: str, *, reason: str | None = None) -> None:
        if not ctx.guild:
            return
        user = await self.resolve_user(ctx, target)
        if not user:
            await ctx.warn(f"I was unable to find **{target}**.")
            return
        member = user if isinstance(user, discord.Member) else ctx.guild.get_member(user.id)
        if member and not await self.ensure_member_target(ctx, member):
            return
        try:
            await self.ban_user(
                ctx.guild,
                user,
                reason=self.audit_reason(ctx, reason),
                delete_seconds=86400,
            )
        except discord.Forbidden:
            await ctx.warn("I couldn't ban that user because I'm **missing permissions**.")
            return
        except discord.HTTPException:
            await ctx.warn("I couldn't ban that user.")
            return
        await self.send_dm_notification(
            user,
            action="banned",
            guild=ctx.guild,
            moderator=ctx.author,
            reason=reason,
        )
        case = await self.create_case(
            ctx,
            action="ban",
            target=user,
            fallback_name=f"{user} ({user.id})",
            reason=reason,
        )
        mention = member.mention if member else f"**{user}**"
        await ctx.success(f"Successfully banned {mention} (`#case {case['id']}`) - **{reason or 'no reason provided'}**")

    @commands.hybrid_command(
        name="hardban",
        help="Ban a user and delete their messages from the past 7 days",
        extras={"parameters": "user, reason", "usage": "hardban (user) [reason]"},
    )
    @commands.has_permissions(ban_members=True)
    @app_commands.describe(target="The user to hardban (mention, ID, or username)", reason="The reason for the hardban")
    async def hardban(self, ctx: TormentContext, target: str, *, reason: str | None = None) -> None:
        if not ctx.guild:
            return
        user = await self.resolve_user(ctx, target)
        if not user:
            await ctx.warn(f"I was unable to find **{target}**.")
            return
        member = user if isinstance(user, discord.Member) else ctx.guild.get_member(user.id)
        if member and not await self.ensure_member_target(ctx, member):
            return
        try:
            await self.ban_user(
                ctx.guild,
                user,
                reason=self.audit_reason(ctx, reason),
                delete_seconds=604800,
            )
        except discord.Forbidden:
            await ctx.warn("I couldn't hardban that user because I'm **missing permissions**.")
            return
        except discord.HTTPException:
            await ctx.warn("I couldn't hardban that user.")
            return
        await self.send_dm_notification(
            user,
            action="hardbanned",
            guild=ctx.guild,
            moderator=ctx.author,
            reason=reason,
        )
        try:
            await ctx.guild.unban(user, reason=self.audit_reason(ctx, "hardban release"))
        except discord.HTTPException:
            pass
        case = await self.create_case(
            ctx,
            action="hardban",
            target=user,
            fallback_name=f"{user} ({user.id})",
            reason=reason,
        )
        await ctx.success(f"Successfully hardbanned **{user}** (`#case {case['id']}`) - **{reason or 'no reason provided'}**")

    @commands.hybrid_command(
        name="unban",
        help="Unban a previously banned user from the server",
        extras={"parameters": "user, reason", "usage": "unban (user) [reason]"},
    )
    @commands.has_permissions(ban_members=True)
    @app_commands.describe(target="The user to unban (mention, ID, or username)", reason="The reason for the unban")
    async def unban(self, ctx: TormentContext, target: str, *, reason: str | None = None) -> None:
        if not ctx.guild:
            return
        user = await self.resolve_user(ctx, target)
        if not user:
            raw = target.strip().replace("<@", "").replace("!", "").replace(">", "")
            if not raw.isdigit():
                await ctx.warn(f"I was unable to find **{target}**.")
                return
            try:
                user = await self.bot.fetch_user(int(raw))
            except discord.HTTPException:
                await ctx.warn(f"I was unable to find **{target}**.")
                return
        try:
            await ctx.guild.unban(user, reason=self.audit_reason(ctx, reason))
        except discord.NotFound:
            await ctx.warn(f"**{user}** is not currently banned.")
            return
        except discord.Forbidden:
            await ctx.warn("I couldn't unban that user because I'm **missing permissions**.")
            return
        except discord.HTTPException:
            await ctx.warn("I couldn't unban that user.")
            return
        await self.send_dm_notification(
            user,
            action="unbanned",
            guild=ctx.guild,
            moderator=ctx.author,
            reason=reason,
        )
        case = await self.create_case(
            ctx,
            action="unban",
            target=user,
            fallback_name=f"{user} ({user.id})",
            reason=reason,
        )
        await ctx.success(f"Successfully unbanned **{user}** (`#case {case['id']}`) - **{reason or 'no reason provided'}**")

    @commands.hybrid_command(
        name="nickname",
        aliases=["nick"],
        help="Change or reset a member's nickname",
        extras={"parameters": "member, nickname", "usage": "nickname (member) [nickname]"},
    )
    @commands.has_permissions(manage_nicknames=True)
    @app_commands.describe(member="The member to change nickname for", nickname="The new nickname (leave empty to reset)")
    async def nickname(self, ctx: TormentContext, member: discord.Member, *, nickname: str | None = None) -> None:
        if not await self.ensure_member_target(ctx, member):
            return
        try:
            await member.edit(nick=nickname, reason=self.audit_reason(ctx, "nickname update"))
        except discord.Forbidden:
            await ctx.warn("I couldn't update that nickname because I'm **missing permissions**.")
            return
        except discord.HTTPException:
            await ctx.warn("I couldn't update that nickname.")
            return
        case = await self.create_case(
            ctx,
            action="nickname",
            target=member,
            fallback_name=f"{member} ({member.id})",
            reason=f"set nickname to {nickname or 'none'}",
        )
        if nickname:
            await ctx.success(f"Successfully updated {member.mention}'s nickname (`#case {case['id']}`)")
        else:
            await ctx.success(f"Successfully cleared {member.mention}'s nickname (`#case {case['id']}`)")

    @commands.hybrid_group(
        name="forcenickname",
        aliases=["fnick"],
        invoke_without_command=True,
        help="Force a permanent nickname on a member that resets automatically",
        extras={"parameters": "member, nickname", "usage": "forcenickname (member) (nickname)"},
    )
    @commands.has_permissions(manage_nicknames=True)
    @app_commands.describe(member="The member to force nickname on", nickname="The nickname to force")
    async def forcenickname(self, ctx: TormentContext, member: discord.Member | None = None, *, nickname: str | None = None) -> None:
        if not member or not nickname:
            await ctx.send_help_embed(ctx.command)
            return
        if not await self.ensure_member_target(ctx, member):
            return
        await self.storage.set_forced_nickname(ctx.guild.id, member.id, nickname, ctx.author.id)
        try:
            await member.edit(nick=nickname, reason=self.audit_reason(ctx, "forced nickname set"))
        except discord.HTTPException:
            pass
        case = await self.create_case(
            ctx,
            action="forcenickname",
            target=member,
            fallback_name=f"{member} ({member.id})",
            reason=f"set forced nickname to {nickname}",
        )
        await ctx.success(f"Successfully set {member.mention}'s forced nickname (`#case {case['id']}`)")

    @forcenickname.command(
        name="remove",
        help="Remove a forced nickname from a member",
        extras={"parameters": "member", "usage": "forcenickname remove (member)"},
    )
    async def forcenickname_remove(self, ctx: TormentContext, member: discord.Member) -> None:
        await self.storage.remove_forced_nickname(ctx.guild.id, member.id)
        case = await self.create_case(
            ctx,
            action="forcenickname remove",
            target=member,
            fallback_name=f"{member} ({member.id})",
            reason="removed forced nickname",
        )
        await ctx.success(f"Successfully removed {member.mention}'s forced nickname (`#case {case['id']}`)")

    @forcenickname.command(
        name="list",
        help="List all members with forced nicknames in the server",
        extras={"parameters": "n/a", "usage": "forcenickname list"},
    )
    async def forcenickname_list(self, ctx: TormentContext) -> None:
        records = await self.storage.list_forced_nicknames(ctx.guild.id)
        if not records:
            await ctx.warn("No **forced nicknames** were found.")
            return
        pages: list[discord.Embed] = []
        chunk_size = 10
        for index in range(0, len(records), chunk_size):
            chunk = records[index:index + chunk_size]
            embed = discord.Embed(
                title="Forced Nicknames",
                description="\n".join(
                    f"<@{record['user_id']}> - `{record['nickname']}`"
                    for record in chunk
                ),
                color=_color("EMBED_INFO_COLOR"),
            )
            pages.append(embed)
        total = len(pages)
        for page_index, page in enumerate(pages, start=1):
            page.set_footer(text=f"Page {page_index}/{total} ({len(records)} entries)")
        await ctx.paginate(pages)

    @forcenickname.command(
        name="sync",
        help="Manually sync forced nicknames for members in the server",
        extras={"parameters": "member", "usage": "forcenickname sync [member]"},
    )
    async def forcenickname_sync(self, ctx: TormentContext, member: discord.Member | None = None) -> None:
        if member:
            await self.apply_forced_nickname(member)
            await ctx.success(f"Successfully synced {member.mention}'s forced nickname")
            return
        records = await self.storage.list_forced_nicknames(ctx.guild.id)
        synced = 0
        for record in records:
            target = ctx.guild.get_member(record["user_id"])
            if not target:
                continue
            await self.apply_forced_nickname(target)
            synced += 1
        await ctx.success(f"Successfully synced **{synced}** forced nicknames")

    @commands.hybrid_group(
        name="lock",
        invoke_without_command=True,
        help="Lock a channel to prevent members from sending messages",
        extras={"parameters": "channel, reason", "usage": "lock [channel] [reason]"},
    )
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx: TormentContext, *, args: str | None = None) -> None:
        channel_token = None
        reason = None
        if args:
            tokens = args.split()
            resolved = await self.resolve_channel(ctx, tokens[0])
            if resolved:
                channel_token = tokens[0]
                reason = args.split(" ", 1)[1].strip() if len(tokens) > 1 else None
            else:
                reason = args
        target = await self.resolve_channel(ctx, channel_token) if channel_token else ctx.channel
        if not isinstance(target, (discord.TextChannel, discord.CategoryChannel)):
            await ctx.send_help_embed(ctx.command)
            return
        await self.set_lock_state(
            ctx,
            action="locked",
            success_msg="Successfully locked {channel}",
            channel=target,
            locked=True,
            reason=reason,
        )

    @lock.command(
        name="category",
        help="Lock all channels in a category",
        extras={"parameters": "category, reason", "usage": "lock category [category] [reason]"},
    )
    async def lock_category(self, ctx: TormentContext, category: discord.CategoryChannel | None = None, *, reason: str | None = None) -> None:
        target = category or ctx.channel.category
        if not target:
            await ctx.send_help_embed(ctx.command)
            return
        await self.set_lock_state(
            ctx,
            action="locked",
            success_msg="Successfully locked {channel}",
            channel=target,
            locked=True,
            reason=reason,
        )

    @commands.hybrid_group(
        name="unlock",
        invoke_without_command=True,
        help="Unlock a channel to allow members to send messages",
        extras={"parameters": "channel, reason", "usage": "unlock [channel] [reason]"},
    )
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx: TormentContext, *, args: str | None = None) -> None:
        channel_token = None
        reason = None
        if args:
            tokens = args.split()
            resolved = await self.resolve_channel(ctx, tokens[0])
            if resolved:
                channel_token = tokens[0]
                reason = args.split(" ", 1)[1].strip() if len(tokens) > 1 else None
            else:
                reason = args
        target = await self.resolve_channel(ctx, channel_token) if channel_token else ctx.channel
        if not isinstance(target, (discord.TextChannel, discord.CategoryChannel)):
            await ctx.send_help_embed(ctx.command)
            return
        await self.set_lock_state(
            ctx,
            action="unlocked",
            success_msg="Successfully unlocked {channel}",
            channel=target,
            locked=False,
            reason=reason,
        )

    @unlock.command(
        name="category",
        help="Unlock all channels in a category",
        extras={"parameters": "category, reason", "usage": "unlock category [category] [reason]"},
    )
    async def unlock_category(self, ctx: TormentContext, category: discord.CategoryChannel | None = None, *, reason: str | None = None) -> None:
        target = category or ctx.channel.category
        if not target:
            await ctx.send_help_embed(ctx.command)
            return
        await self.set_lock_state(
            ctx,
            action="unlocked",
            success_msg="Successfully unlocked {channel}",
            channel=target,
            locked=False,
            reason=reason,
        )

    @commands.hybrid_group(
        name="hide",
        invoke_without_command=True,
        help="Hide a channel from a role or member's view",
        extras={"parameters": "channel, role_or_member", "usage": "hide [channel] [role_or_member]"},
    )
    @commands.has_permissions(manage_channels=True)
    async def hide(self, ctx: TormentContext, *, args: str | None = None) -> None:
        if not ctx.guild:
            return
        tokens = args.split() if args else []
        channel = await self.resolve_channel(ctx, tokens[0]) if tokens else ctx.channel
        if not isinstance(channel, (discord.TextChannel, discord.CategoryChannel)):
            await ctx.send_help_embed(ctx.command)
            return
        target_token = tokens[1] if tokens and await self.resolve_channel(ctx, tokens[0]) else (tokens[0] if tokens else None)
        target = await self.resolve_visibility_target(ctx, target_token) if target_token else ctx.guild.default_role
        if not target:
            target = ctx.guild.default_role
        await self.set_visibility(
            ctx,
            action="hid",
            success_msg="Successfully hid {channel} from {target}",
            channel=channel,
            target=target,
            visible=False,
        )

    @hide.command(
        name="category",
        help="Hide an entire category from a role or member's view",
        extras={"parameters": "category, role_or_member", "usage": "hide category [category] [role_or_member]"},
    )
    async def hide_category(self, ctx: TormentContext, category: discord.CategoryChannel | None = None, target: str | None = None) -> None:
        if not ctx.guild:
            return
        actual_category = category or ctx.channel.category
        if not actual_category:
            await ctx.send_help_embed(ctx.command)
            return
        subject = await self.resolve_visibility_target(ctx, target) if target else ctx.guild.default_role
        if not subject:
            subject = ctx.guild.default_role
        await self.set_visibility(
            ctx,
            action="hid",
            success_msg="Successfully hid {channel} from {target}",
            channel=actual_category,
            target=subject,
            visible=False,
        )

    @commands.hybrid_group(
        name="reveal",
        aliases=["unhide"],
        invoke_without_command=True,
        help="Reveal a hidden channel to a role or member",
        extras={"parameters": "channel, role_or_member", "usage": "reveal [channel] [role_or_member]"},
    )
    @commands.has_permissions(manage_channels=True)
    async def reveal(self, ctx: TormentContext, *, args: str | None = None) -> None:
        if not ctx.guild:
            return
        tokens = args.split() if args else []
        channel = await self.resolve_channel(ctx, tokens[0]) if tokens else ctx.channel
        if not isinstance(channel, (discord.TextChannel, discord.CategoryChannel)):
            await ctx.send_help_embed(ctx.command)
            return
        target_token = tokens[1] if tokens and await self.resolve_channel(ctx, tokens[0]) else (tokens[0] if tokens else None)
        target = await self.resolve_visibility_target(ctx, target_token) if target_token else ctx.guild.default_role
        if not target:
            target = ctx.guild.default_role
        await self.set_visibility(
            ctx,
            action="revealed",
            success_msg="Successfully revealed {channel} for {target}",
            channel=channel,
            target=target,
            visible=True,
        )

    @reveal.command(
        name="category",
        help="Reveal a hidden category to a role or member",
        extras={"parameters": "category, role_or_member", "usage": "reveal category [category] [role_or_member]"},
    )
    async def reveal_category(self, ctx: TormentContext, category: discord.CategoryChannel | None = None, target: str | None = None) -> None:
        if not ctx.guild:
            return
        actual_category = category or ctx.channel.category
        if not actual_category:
            await ctx.send_help_embed(ctx.command)
            return
        subject = await self.resolve_visibility_target(ctx, target) if target else ctx.guild.default_role
        if not subject:
            subject = ctx.guild.default_role
        await self.set_visibility(
            ctx,
            action="revealed",
            success_msg="Successfully revealed {channel} for {target}",
            channel=actual_category,
            target=subject,
            visible=True,
        )

    @commands.hybrid_command(
        name="mute",
        help="Mute a member to prevent them from sending messages",
        extras={"parameters": "member, reason", "usage": "mute (member) [reason]"},
    )
    @commands.has_permissions(moderate_members=True)
    @app_commands.describe(member="The member to mute", reason="The reason for the mute")
    async def mute(self, ctx: TormentContext, member: discord.Member, *, reason: str | None = None) -> None:
        await self.apply_configured_role_action(
            ctx,
            member,
            config_key="muted_role_id",
            role_label="Muted",
            action="mute",
            success_msg="muted {target}",
            reason=reason,
        )

    @commands.hybrid_command(
        name="unmute",
        help="Unmute a member to allow them to send messages again",
        extras={"parameters": "member, reason", "usage": "unmute (member) [reason]"},
    )
    @commands.has_permissions(moderate_members=True)
    @app_commands.describe(member="The member to unmute", reason="The reason for the unmute")
    async def unmute(self, ctx: TormentContext, member: discord.Member, *, reason: str | None = None) -> None:
        await self.apply_configured_role_action(
            ctx,
            member,
            config_key="muted_role_id",
            role_label="Muted",
            action="unmute",
            success_msg="unmuted {target}",
            reason=reason,
            remove=True,
        )

    @commands.hybrid_command(
        name="imute",
        help="Remove a member's ability to send images and attachments",
        extras={"parameters": "member, reason", "usage": "imute (member) [reason]"},
    )
    @commands.has_permissions(moderate_members=True)
    @app_commands.describe(member="The member to image mute", reason="The reason for the image mute")
    async def imute(self, ctx: TormentContext, member: discord.Member, *, reason: str | None = None) -> None:
        await self.apply_configured_role_action(
            ctx,
            member,
            config_key="image_muted_role_id",
            role_label="Image Muted",
            action="imute",
            success_msg="removed embed and file perms for {target}",
            reason=reason,
        )

    @commands.hybrid_command(
        name="iunmute",
        help="Restore a member's ability to send images and attachments",
        extras={"parameters": "member, reason", "usage": "iunmute (member) [reason]"},
    )
    @commands.has_permissions(moderate_members=True)
    @app_commands.describe(member="The member to image unmute", reason="The reason for the image unmute")
    async def iunmute(self, ctx: TormentContext, member: discord.Member, *, reason: str | None = None) -> None:
        await self.apply_configured_role_action(
            ctx,
            member,
            config_key="image_muted_role_id",
            role_label="Image Muted",
            action="iunmute",
            success_msg="restored embed and file perms for {target}",
            reason=reason,
            remove=True,
        )

    @commands.hybrid_command(
        name="rmute",
        help="Remove a member's ability to add reactions to messages",
        extras={"parameters": "member, reason", "usage": "rmute (member) [reason]"},
    )
    @commands.has_permissions(moderate_members=True)
    @app_commands.describe(member="The member to reaction mute", reason="The reason for the reaction mute")
    async def rmute(self, ctx: TormentContext, member: discord.Member, *, reason: str | None = None) -> None:
        await self.apply_configured_role_action(
            ctx,
            member,
            config_key="reaction_muted_role_id",
            role_label="Reaction Muted",
            action="rmute",
            success_msg="removed reaction perms for {target}",
            reason=reason,
        )

    @commands.hybrid_command(
        name="runmute",
        help="Restore a member's ability to add reactions to messages",
        extras={"parameters": "member, reason", "usage": "runmute (member) [reason]"},
    )
    @commands.has_permissions(moderate_members=True)
    @app_commands.describe(member="The member to reaction unmute", reason="The reason for the reaction unmute")
    async def runmute(self, ctx: TormentContext, member: discord.Member, *, reason: str | None = None) -> None:
        await self.apply_configured_role_action(
            ctx,
            member,
            config_key="reaction_muted_role_id",
            role_label="Reaction Muted",
            action="runmute",
            success_msg="restored reaction perms for {target}",
            reason=reason,
            remove=True,
        )

    @commands.hybrid_group(
        name="purge",
        aliases=["clear", "prune"],
        invoke_without_command=True,
        help="Delete multiple messages from a channel at once",
        extras={"parameters": "amount", "usage": "purge (amount)"},
    )
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @app_commands.describe(amount="The number of messages to delete")
    async def purge(self, ctx: TormentContext, amount: int) -> None:
        if not ctx.guild:
            return

        if amount < 1:
            return await ctx.warn("You must specify at least 1 message to purge!")

        if amount > 1000:
            return await ctx.warn("You cannot purge more than 1000 messages at once!")

        try:
            deleted = await ctx.channel.purge(limit=amount + 1)
            count = len(deleted) - 1
            await ctx.success(f"purged {count} message{'s' if count != 1 else ''}")
        except discord.HTTPException as e:
            await ctx.warn(f"Failed to purge messages: {str(e)}")

    @purge.command(
        name="user",
        aliases=["member"],
        help="Delete messages from a specific user in the channel",
        extras={"parameters": "user, amount", "usage": "purge user (user) [amount]"},
    )
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_user(self, ctx: TormentContext, user: discord.User, amount: int = 100) -> None:
        if not ctx.guild:
            return

        if amount < 1:
            return await ctx.warn("You must specify at least 1 message to check!")

        if amount > 1000:
            return await ctx.warn("You cannot check more than 1000 messages at once!")

        def check(m: discord.Message) -> bool:
            return m.author.id == user.id

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check)
            count = len(deleted)
            await ctx.success(f"purged {count} message{'s' if count != 1 else ''} from {user.mention}")
        except discord.HTTPException as e:
            await ctx.warn(f"Failed to purge messages: {str(e)}")

    @purge.command(
        name="bots",
        aliases=["bot"],
        help="Delete messages from bots in the channel",
        extras={"parameters": "amount", "usage": "purge bots [amount]"},
    )
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_bots(self, ctx: TormentContext, amount: int = 100) -> None:
        if not ctx.guild:
            return

        if amount < 1:
            return await ctx.warn("You must specify at least 1 message to check!")

        if amount > 1000:
            return await ctx.warn("You cannot check more than 1000 messages at once!")

        def check(m: discord.Message) -> bool:
            return m.author.bot

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check)
            count = len(deleted)
            await ctx.success(f"purged {count} bot message{'s' if count != 1 else ''}")
        except discord.HTTPException as e:
            await ctx.warn(f"Failed to purge messages: {str(e)}")

    @purge.command(
        name="files",
        aliases=["attachments", "images"],
        help="Delete messages containing attachments or files",
        extras={"parameters": "amount", "usage": "purge files [amount]"},
    )
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_files(self, ctx: TormentContext, amount: int = 100) -> None:
        if not ctx.guild:
            return

        if amount < 1:
            return await ctx.warn("You must specify at least 1 message to check!")

        if amount > 1000:
            return await ctx.warn("You cannot check more than 1000 messages at once!")

        def check(m: discord.Message) -> bool:
            return len(m.attachments) > 0

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check)
            count = len(deleted)
            await ctx.success(f"purged {count} message{'s' if count != 1 else ''} with attachments")
        except discord.HTTPException as e:
            await ctx.warn(f"Failed to purge messages: {str(e)}")

    @purge.command(
        name="embeds",
        aliases=["embed"],
        help="Delete messages containing embeds",
        extras={"parameters": "amount", "usage": "purge embeds [amount]"},
    )
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_embeds(self, ctx: TormentContext, amount: int = 100) -> None:
        if not ctx.guild:
            return

        if amount < 1:
            return await ctx.warn("You must specify at least 1 message to check!")

        if amount > 1000:
            return await ctx.warn("You cannot check more than 1000 messages at once!")

        def check(m: discord.Message) -> bool:
            return len(m.embeds) > 0

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check)
            count = len(deleted)
            await ctx.success(f"purged {count} message{'s' if count != 1 else ''} with embeds")
        except discord.HTTPException as e:
            await ctx.warn(f"Failed to purge messages: {str(e)}")

    @purge.command(
        name="links",
        aliases=["urls"],
        help="Delete messages containing links or URLs",
        extras={"parameters": "amount", "usage": "purge links [amount]"},
    )
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_links(self, ctx: TormentContext, amount: int = 100) -> None:
        if not ctx.guild:
            return

        if amount < 1:
            return await ctx.warn("You must specify at least 1 message to check!")

        if amount > 1000:
            return await ctx.warn("You cannot check more than 1000 messages at once!")

        def check(m: discord.Message) -> bool:
            return "http://" in m.content.lower() or "https://" in m.content.lower()

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check)
            count = len(deleted)
            await ctx.success(f"purged {count} message{'s' if count != 1 else ''} with links")
        except discord.HTTPException as e:
            await ctx.warn(f"Failed to purge messages: {str(e)}")

    @purge.command(
        name="invites",
        aliases=["invite"],
        help="Delete messages containing Discord invite links",
        extras={"parameters": "amount", "usage": "purge invites [amount]"},
    )
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_invites(self, ctx: TormentContext, amount: int = 100) -> None:
        if not ctx.guild:
            return

        if amount < 1:
            return await ctx.warn("You must specify at least 1 message to check!")

        if amount > 1000:
            return await ctx.warn("You cannot check more than 1000 messages at once!")

        def check(m: discord.Message) -> bool:
            content = m.content.lower()
            return "discord.gg/" in content or "discord.com/invite/" in content

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check)
            count = len(deleted)
            await ctx.success(f"purged {count} message{'s' if count != 1 else ''} with invites")
        except discord.HTTPException as e:
            await ctx.warn(f"Failed to purge messages: {str(e)}")

    @purge.command(
        name="mentions",
        aliases=["mention"],
        help="Delete messages containing user or role mentions",
        extras={"parameters": "amount", "usage": "purge mentions [amount]"},
    )
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_mentions(self, ctx: TormentContext, amount: int = 100) -> None:
        if not ctx.guild:
            return

        if amount < 1:
            return await ctx.warn("You must specify at least 1 message to check!")

        if amount > 1000:
            return await ctx.warn("You cannot check more than 1000 messages at once!")

        def check(m: discord.Message) -> bool:
            return len(m.mentions) > 0 or len(m.role_mentions) > 0

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check)
            count = len(deleted)
            await ctx.success(f"purged {count} message{'s' if count != 1 else ''} with mentions")
        except discord.HTTPException as e:
            await ctx.warn(f"Failed to purge messages: {str(e)}")

    @purge.command(
        name="contains",
        aliases=["match", "text"],
        help="Delete messages containing specific text",
        extras={"parameters": "text, amount", "usage": "purge contains (text) [amount]"},
    )
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_contains(self, ctx: TormentContext, text: str, amount: int = 100) -> None:
        if not ctx.guild:
            return

        if amount < 1:
            return await ctx.warn("You must specify at least 1 message to check!")

        if amount > 1000:
            return await ctx.warn("You cannot check more than 1000 messages at once!")

        def check(m: discord.Message) -> bool:
            return text.lower() in m.content.lower()

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check)
            count = len(deleted)
            await ctx.success(f"purged {count} message{'s' if count != 1 else ''} containing `{text}`")
        except discord.HTTPException as e:
            await ctx.warn(f"Failed to purge messages: {str(e)}")

    @purge.command(
        name="startswith",
        aliases=["starts"],
        help="Delete messages starting with specific text",
        extras={"parameters": "text, amount", "usage": "purge startswith (text) [amount]"},
    )
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_startswith(self, ctx: TormentContext, text: str, amount: int = 100) -> None:
        if not ctx.guild:
            return

        if amount < 1:
            return await ctx.warn("You must specify at least 1 message to check!")

        if amount > 1000:
            return await ctx.warn("You cannot check more than 1000 messages at once!")

        def check(m: discord.Message) -> bool:
            return m.content.lower().startswith(text.lower())

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check)
            count = len(deleted)
            await ctx.success(f"purged {count} message{'s' if count != 1 else ''} starting with `{text}`")
        except discord.HTTPException as e:
            await ctx.warn(f"Failed to purge messages: {str(e)}")

    @purge.command(
        name="endswith",
        aliases=["ends"],
        help="Delete messages ending with specific text",
        extras={"parameters": "text, amount", "usage": "purge endswith (text) [amount]"},
    )
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_endswith(self, ctx: TormentContext, text: str, amount: int = 100) -> None:
        if not ctx.guild:
            return

        if amount < 1:
            return await ctx.warn("You must specify at least 1 message to check!")

        if amount > 1000:
            return await ctx.warn("You cannot check more than 1000 messages at once!")

        def check(m: discord.Message) -> bool:
            return m.content.lower().endswith(text.lower())

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check)
            count = len(deleted)
            await ctx.success(f"purged {count} message{'s' if count != 1 else ''} ending with `{text}`")
        except discord.HTTPException as e:
            await ctx.warn(f"Failed to purge messages: {str(e)}")

    @purge.command(
        name="reactions",
        aliases=["reaction"],
        help="Delete messages with reactions",
        extras={"parameters": "amount", "usage": "purge reactions [amount]"},
    )
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_reactions(self, ctx: TormentContext, amount: int = 100) -> None:
        if not ctx.guild:
            return

        if amount < 1:
            return await ctx.warn("You must specify at least 1 message to check!")

        if amount > 1000:
            return await ctx.warn("You cannot check more than 1000 messages at once!")

        def check(m: discord.Message) -> bool:
            return len(m.reactions) > 0

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check)
            count = len(deleted)
            await ctx.success(f"purged {count} message{'s' if count != 1 else ''} with reactions")
        except discord.HTTPException as e:
            await ctx.warn(f"Failed to purge messages: {str(e)}")

    @purge.command(
        name="humans",
        aliases=["human"],
        help="Delete messages from human users only",
        extras={"parameters": "amount", "usage": "purge humans [amount]"},
    )
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_humans(self, ctx: TormentContext, amount: int = 100) -> None:
        if not ctx.guild:
            return

        if amount < 1:
            return await ctx.warn("You must specify at least 1 message to check!")

        if amount > 1000:
            return await ctx.warn("You cannot check more than 1000 messages at once!")

        def check(m: discord.Message) -> bool:
            return not m.author.bot

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check)
            count = len(deleted)
            await ctx.success(f"purged {count} human message{'s' if count != 1 else ''}")
        except discord.HTTPException as e:
            await ctx.warn(f"Failed to purge messages: {str(e)}")

    @commands.hybrid_command(
        name="softban",
        help="Ban and immediately unban a user to delete their messages",
        extras={"parameters": "user, reason", "usage": "softban (user) [reason]"},
    )
    @commands.has_permissions(ban_members=True)
    @app_commands.describe(target="The user to softban (mention, ID, or username)", reason="The reason for the softban")
    async def softban(self, ctx: TormentContext, target: str, *, reason: str | None = None) -> None:
        if not ctx.guild:
            return
        user = await self.resolve_user(ctx, target)
        if not user:
            await ctx.warn(f"I was unable to find **{target}**.")
            return
        member = user if isinstance(user, discord.Member) else ctx.guild.get_member(user.id)
        if member and not await self.ensure_member_target(ctx, member):
            return
        try:
            await self.ban_user(
                ctx.guild,
                user,
                reason=self.audit_reason(ctx, reason),
                delete_seconds=604800,
            )
            await ctx.guild.unban(user, reason=self.audit_reason(ctx, "softban unban"))
        except discord.Forbidden:
            await ctx.warn("I couldn't softban that user because I'm **missing permissions**.")
            return
        except discord.HTTPException:
            await ctx.warn("I couldn't softban that user.")
            return
        await self.send_dm_notification(
            user,
            action="softbanned",
            guild=ctx.guild,
            moderator=ctx.author,
            reason=reason,
        )
        case = await self.create_case(
            ctx,
            action="softban",
            target=user,
            fallback_name=f"{user} ({user.id})",
            reason=reason,
            metadata={"messages_deleted": "7 days"},
        )
        mention = member.mention if member else f"**{user}**"
        await ctx.success(f"Successfully softbanned {mention} (`#case {case['id']}`) - **{reason or 'no reason provided'}**")

    @commands.hybrid_group(
        name="notes",
        aliases=["note"],
        invoke_without_command=True,
        help="Manage moderator notes for users",
        extras={"parameters": "n/a", "usage": "notes"},
    )
    @commands.has_permissions(manage_messages=True)
    async def notes_group(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @notes_group.command(
        name="add",
        help="Add a note to a user",
        extras={"parameters": "user, note", "usage": "notes add (user) (note)"},
    )
    @commands.has_permissions(manage_messages=True)
    async def notes_add(self, ctx: TormentContext, user: discord.User, *, note: str) -> None:
        if not ctx.guild:
            return
        
        query = """
            INSERT INTO user_notes (guild_id, user_id, moderator_id, note)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """
        note_id = await self.storage.pool.fetchval(query, ctx.guild.id, user.id, ctx.author.id, note)
        await ctx.success(f"Added note **#{note_id}** for {user.mention}")

    @notes_group.command(
        name="view",
        aliases=["list", "show"],
        help="View all notes for a user",
        extras={"parameters": "user", "usage": "notes view (user)"},
    )
    @commands.has_permissions(manage_messages=True)
    async def notes_view(self, ctx: TormentContext, user: discord.User) -> None:
        if not ctx.guild:
            return
        
        query = """
            SELECT id, moderator_id, note, created_at
            FROM user_notes
            WHERE guild_id = $1 AND user_id = $2
            ORDER BY created_at DESC
        """
        records = await self.storage.pool.fetch(query, ctx.guild.id, user.id)
        
        if not records:
            return await ctx.warn(f"No notes found for {user.mention}")
        
        pages: list[discord.Embed] = []
        chunk_size = 5
        for index in range(0, len(records), chunk_size):
            chunk = records[index:index + chunk_size]
            lines = []
            for record in chunk:
                moderator = ctx.guild.get_member(record["moderator_id"])
                mod_name = moderator.mention if moderator else f"<@{record['moderator_id']}>"
                timestamp = self.discord_timestamp(record["created_at"], "R")
                lines.append(
                    f"`#{record['id']}` by {mod_name} {timestamp}\n"
                    f"> {record['note']}"
                )
            
            embed = discord.Embed(
                title=f"Notes for {user}",
                description="\n\n".join(lines),
                color=_color("EMBED_INFO_COLOR"),
            )
            pages.append(embed)
        
        total = len(pages)
        for page_index, page in enumerate(pages, start=1):
            page.set_footer(text=f"Page {page_index}/{total} ({len(records)} notes)")
        
        await ctx.paginate(pages)

    @notes_group.command(
        name="remove",
        aliases=["delete", "del", "rm"],
        help="Remove a note by ID",
        extras={"parameters": "note_id", "usage": "notes remove (note_id)"},
    )
    @commands.has_permissions(manage_messages=True)
    async def notes_remove(self, ctx: TormentContext, note_id: int) -> None:
        if not ctx.guild:
            return
        
        query = "DELETE FROM user_notes WHERE id = $1 AND guild_id = $2"
        result = await self.storage.pool.execute(query, note_id, ctx.guild.id)
        
        if result == "DELETE 0":
            return await ctx.warn(f"Note **#{note_id}** does not exist")
        
        await ctx.success(f"Removed note **#{note_id}**")

    @notes_group.command(
        name="clear",
        help="Clear all notes for a user",
        extras={"parameters": "user", "usage": "notes clear (user)"},
    )
    @commands.has_permissions(manage_messages=True)
    async def notes_clear(self, ctx: TormentContext, user: discord.User) -> None:
        if not ctx.guild:
            return
        
        if not await ctx.confirm(f"Are you sure you want to clear all notes for {user.mention}?"):
            return
        
        query = "DELETE FROM user_notes WHERE guild_id = $1 AND user_id = $2"
        result = await self.storage.pool.execute(query, ctx.guild.id, user.id)
        
        count = int(result.split()[-1]) if result else 0
        if count == 0:
            return await ctx.warn(f"No notes found for {user.mention}")
        
        await ctx.success(f"Cleared **{count}** note{'s' if count != 1 else ''} for {user.mention}")

    @commands.hybrid_command(
        name="timeout",
        help="Timeout a member to prevent them from interacting",
        extras={"parameters": "member, duration, reason", "usage": "timeout (member) (duration) [reason]"},
    )
    @commands.has_permissions(moderate_members=True)
    @app_commands.describe(
        member="The member to timeout",
        duration="Duration (e.g., 10m, 1h, 1d)",
        reason="The reason for the timeout"
    )
    async def timeout_command(
        self,
        ctx: TormentContext,
        member: discord.Member,
        duration: str,
        *,
        reason: str | None = None
    ) -> None:
        if not ctx.guild:
            return
        
        if not await self.ensure_member_target(ctx, member):
            return
        
        import re
        from datetime import timedelta, timezone as tz
        
        duration_match = re.match(r'^(\d+)([smhd])$', duration.lower())
        if not duration_match:
            return await ctx.warn("Invalid duration format. Use: `10s`, `5m`, `2h`, or `1d`")
        
        amount = int(duration_match.group(1))
        unit = duration_match.group(2)
        
        multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        seconds = amount * multipliers[unit]
        
        if seconds < 1:
            return await ctx.warn("Timeout duration must be at least 1 second")
        if seconds > 2419200:
            return await ctx.warn("Timeout duration cannot exceed 28 days")
        
        timeout_until = discord.utils.utcnow() + timedelta(seconds=seconds)
        
        try:
            await member.timeout(timeout_until, reason=self.audit_reason(ctx, reason))
        except discord.Forbidden:
            return await ctx.warn("I couldn't timeout that member because I'm **missing permissions**.")
        except discord.HTTPException:
            return await ctx.warn("I couldn't timeout that member.")
        
        await self.send_dm_notification(
            member,
            action="timed out",
            guild=ctx.guild,
            moderator=ctx.author,
            reason=reason,
            duration=duration,
        )
        
        case = await self.create_case(
            ctx,
            action="timeout",
            target=member,
            fallback_name=f"{member} ({member.id})",
            reason=reason,
            metadata={"duration": duration, "until": timeout_until.isoformat()},
        )
        
        await ctx.success(
            f"Successfully timed out {member.mention} for **{duration}** "
            f"(`#case {case['id']}`) - **{reason or 'no reason provided'}**"
        )

    @commands.hybrid_group(
        name="untimeout",
        aliases=["removetimeout"],
        invoke_without_command=True,
        help="Remove timeout from a member",
        extras={"parameters": "member, reason", "usage": "untimeout (member) [reason]"},
    )
    @commands.has_permissions(moderate_members=True)
    @app_commands.describe(member="The member to remove timeout from", reason="The reason")
    async def untimeout_command(
        self,
        ctx: TormentContext,
        member: discord.Member,
        *,
        reason: str | None = None
    ) -> None:
        if not ctx.guild:
            return
        
        if not member.is_timed_out():
            return await ctx.warn(f"{member.mention} is not timed out")
        
        try:
            await member.timeout(None, reason=self.audit_reason(ctx, reason))
        except discord.Forbidden:
            return await ctx.warn("I couldn't remove timeout because I'm **missing permissions**.")
        except discord.HTTPException:
            return await ctx.warn("I couldn't remove the timeout.")
        
        await self.send_dm_notification(
            member,
            action="timeout removed",
            guild=ctx.guild,
            moderator=ctx.author,
            reason=reason,
        )
        
        case = await self.create_case(
            ctx,
            action="untimeout",
            target=member,
            fallback_name=f"{member} ({member.id})",
            reason=reason,
        )
        
        await ctx.success(
            f"Successfully removed timeout from {member.mention} "
            f"(`#case {case['id']}`) - **{reason or 'no reason provided'}**"
        )

    @commands.hybrid_command(
        name="slowmode",
        help="Set or disable slowmode in a channel",
        extras={"parameters": "duration", "usage": "slowmode [duration]"},
    )
    @commands.has_permissions(manage_channels=True)
    @app_commands.describe(duration="Slowmode duration (e.g., 5s, 10s, 1m) or leave empty to toggle")
    async def slowmode_command(
        self,
        ctx: TormentContext,
        duration: str | None = None
    ) -> None:
        if not isinstance(ctx.channel, discord.TextChannel):
            return await ctx.warn("This command can only be used in text channels")
        
        if duration is None:
            if ctx.channel.slowmode_delay > 0:
                await ctx.channel.edit(slowmode_delay=0, reason=self.audit_reason(ctx, "slowmode disabled"))
                return await ctx.success("Disabled slowmode in this channel")
            else:
                return await ctx.warn("Please provide a duration (e.g., `5s`, `10s`, `1m`)")
        
        import re
        
        duration_match = re.match(r'^(\d+)([smh])$', duration.lower())
        if not duration_match:
            return await ctx.warn("Invalid duration format. Use: `5s`, `30s`, `1m`, `5m`, `1h`")
        
        amount = int(duration_match.group(1))
        unit = duration_match.group(2)
        
        multipliers = {'s': 1, 'm': 60, 'h': 3600}
        seconds = amount * multipliers[unit]
        
        if seconds < 0:
            return await ctx.warn("Slowmode duration must be positive")
        if seconds > 21600:
            return await ctx.warn("Slowmode duration cannot exceed 6 hours")
        
        try:
            await ctx.channel.edit(
                slowmode_delay=seconds,
                reason=self.audit_reason(ctx, f"slowmode set to {duration}")
            )
        except discord.Forbidden:
            return await ctx.warn("I couldn't set slowmode because I'm **missing permissions**.")
        except discord.HTTPException:
            return await ctx.warn("I couldn't set slowmode.")
        
        if seconds == 0:
            await ctx.success("Disabled slowmode in this channel")
        else:
            await ctx.success(f"Set slowmode to **{duration}** in this channel")

    @commands.hybrid_group(
        name="bind",
        invoke_without_command=True,
        help="Bind roles for special purposes",
        extras={"parameters": "n/a", "usage": "bind"},
    )
    @commands.has_permissions(manage_guild=True)
    async def bind_group(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @bind_group.command(
        name="staff",
        help="Toggle a role as a staff role for stripstaff command",
        extras={"parameters": "role", "usage": "bind staff (role)"},
    )
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(role="The role to toggle as staff")
    async def bind_staff(self, ctx: TormentContext, role: discord.Role) -> None:
        if not ctx.guild:
            return
        
        is_added = await self.storage.toggle_staff_role(ctx.guild.id, role.id)
        
        if is_added:
            await ctx.success(f"Bound {role.mention} as a **staff role**")
        else:
            await ctx.success(f"Unbound {role.mention} from **staff roles**")

    @commands.hybrid_command(
        name="stripstaff",
        help="Remove all staff roles from a member",
        extras={"parameters": "member, reason", "usage": "stripstaff (member) [reason]"},
    )
    @commands.has_permissions(administrator=True)
    @app_commands.describe(member="The member to strip staff roles from", reason="The reason for stripping staff roles")
    async def stripstaff(self, ctx: TormentContext, member: discord.Member, *, reason: str | None = None) -> None:
        if not ctx.guild:
            return
        
        if not await self.ensure_member_target(ctx, member):
            return
        
        staff_role_ids = await self.storage.get_staff_roles(ctx.guild.id)
        
        if not staff_role_ids:
            return await ctx.warn("No **staff roles** have been configured. Use `bind staff @role` to set them up.")
        
        member_staff_roles = [role for role in member.roles if role.id in staff_role_ids]
        
        if not member_staff_roles:
            return await ctx.warn(f"{member.mention} doesn't have any **staff roles**.")
        
        removed_roles: list[discord.Role] = []
        for role in member_staff_roles:
            if not await self.ensure_role_assignable(ctx, role):
                continue
            try:
                await member.remove_roles(role, reason=self.audit_reason(ctx, reason))
                removed_roles.append(role)
            except discord.Forbidden:
                continue
            except discord.HTTPException:
                continue
        
        if not removed_roles:
            return await ctx.warn("I couldn't remove any **staff roles** from that member.")
        
        await self.send_dm_notification(
            member,
            action="stripped staff",
            guild=ctx.guild,
            moderator=ctx.author,
            reason=reason,
        )
        
        case = await self.create_case(
            ctx,
            action="stripstaff",
            target=member,
            fallback_name=f"{member} ({member.id})",
            reason=reason,
            metadata={"roles_removed": ", ".join(role.name for role in removed_roles)},
        )
        
        roles_list = ", ".join(role.mention for role in removed_roles)
        await ctx.success(f"Stripped staff roles from {member.mention} (`#case {case['id']}`) - **{reason or 'no reason provided'}**\nRemoved: {roles_list}")

    @commands.group(
        name="thread",
        invoke_without_command=True,
        help="Manage threads",
        extras={"parameters": "n/a", "usage": "thread"},
    )
    @commands.has_permissions(manage_threads=True)
    async def thread_group(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @thread_group.command(
        name="lock",
        help="Lock a thread",
        extras={"parameters": "[thread]", "usage": "thread lock [thread]"},
    )
    @commands.has_permissions(manage_threads=True)
    async def thread_lock(self, ctx: TormentContext, *, thread: discord.Thread = None) -> None:
        target = thread or (ctx.channel if isinstance(ctx.channel, discord.Thread) else None)
        if not target:
            return await ctx.warn("Please run this inside a thread or provide one.")
        await target.edit(locked=True, archived=True)
        await ctx.success(f"Locked {target.mention}.")

    @thread_group.command(
        name="unlock",
        help="Unlock a thread",
        extras={"parameters": "[thread]", "usage": "thread unlock [thread]"},
    )
    @commands.has_permissions(manage_threads=True)
    async def thread_unlock(self, ctx: TormentContext, *, thread: discord.Thread = None) -> None:
        target = thread or (ctx.channel if isinstance(ctx.channel, discord.Thread) else None)
        if not target:
            return await ctx.warn("Please run this inside a thread or provide one.")
        await target.edit(locked=False, archived=False)
        await ctx.success(f"Unlocked {target.mention}.")

    @thread_group.command(
        name="rename",
        help="Rename a thread",
        extras={"parameters": "name, [thread]", "usage": "thread rename (name)"},
    )
    @commands.has_permissions(manage_threads=True)
    async def thread_rename(self, ctx: TormentContext, *, name: str) -> None:
        target = ctx.channel if isinstance(ctx.channel, discord.Thread) else None
        if not target:
            return await ctx.warn("Run this command inside a thread.")
        await target.edit(name=name)
        await ctx.success(f"Renamed thread to **{name}**.")

    @thread_group.command(
        name="add",
        help="Add a member to a thread",
        extras={"parameters": "member, [thread]", "usage": "thread add (member)"},
    )
    @commands.has_permissions(manage_threads=True)
    async def thread_add(self, ctx: TormentContext, member: discord.Member) -> None:
        target = ctx.channel if isinstance(ctx.channel, discord.Thread) else None
        if not target:
            return await ctx.warn("Run this command inside a thread.")
        await target.add_user(member)
        await ctx.success(f"Added {member.mention} to {target.mention}.")

    @thread_group.command(
        name="remove",
        aliases=["kick"],
        help="Remove a member from a thread",
        extras={"parameters": "member", "usage": "thread remove (member)"},
    )
    @commands.has_permissions(manage_threads=True)
    async def thread_remove(self, ctx: TormentContext, member: discord.Member) -> None:
        target = ctx.channel if isinstance(ctx.channel, discord.Thread) else None
        if not target:
            return await ctx.warn("Run this command inside a thread.")
        await target.remove_user(member)
        await ctx.success(f"Removed {member.mention} from {target.mention}.")

    @thread_group.group(
        name="watch",
        invoke_without_command=True,
        help="Watch a thread — get DM'd if it gets deleted",
        extras={"parameters": "[thread]", "usage": "thread watch [thread]"},
    )
    async def thread_watch(self, ctx: TormentContext, *, thread: discord.Thread = None) -> None:
        target = thread or (ctx.channel if isinstance(ctx.channel, discord.Thread) else None)
        if not target:
            return await ctx.warn("Please run this inside a thread or provide one.")
        existing = await self.storage.pool.fetchrow(
            "SELECT 1 FROM thread_watch WHERE guild_id = $1 AND thread_id = $2 AND user_id = $3",
            ctx.guild.id, target.id, ctx.author.id,
        )
        if existing:
            await self.storage.pool.execute(
                "DELETE FROM thread_watch WHERE guild_id = $1 AND thread_id = $2 AND user_id = $3",
                ctx.guild.id, target.id, ctx.author.id,
            )
            return await ctx.success(f"No longer watching {target.mention}.")
        await self.storage.pool.execute(
            "INSERT INTO thread_watch (guild_id, thread_id, user_id) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
            ctx.guild.id, target.id, ctx.author.id,
        )
        await ctx.success(f"Now watching {target.mention}. You'll be DM'd if it gets deleted.")

    @thread_watch.command(
        name="list",
        help="List all threads you're watching",
        extras={"parameters": "n/a", "usage": "thread watch list"},
    )
    async def thread_watch_list(self, ctx: TormentContext) -> None:
        rows = await self.storage.pool.fetch(
            "SELECT thread_id FROM thread_watch WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        if not rows:
            return await ctx.warn("You're not watching any threads in this server.")
        from bot.helpers.paginator import Paginator
        lines = []
        for row in rows:
            thread = ctx.guild.get_thread(row["thread_id"])
            lines.append(thread.mention if thread else f"`{row['thread_id']}` *(deleted)*")
        embed = discord.Embed(title="Watched Threads", color=_color("EMBED_INFO_COLOR"))
        paginator = Paginator(ctx, lines, embed)
        await paginator.start()

    @commands.Cog.listener("on_thread_delete")
    async def thread_watch_notify(self, thread: discord.Thread) -> None:
        rows = await self.storage.pool.fetch(
            "SELECT user_id FROM thread_watch WHERE guild_id = $1 AND thread_id = $2",
            thread.guild.id, thread.id,
        )
        if not rows:
            return
        await self.storage.pool.execute(
            "DELETE FROM thread_watch WHERE guild_id = $1 AND thread_id = $2",
            thread.guild.id, thread.id,
        )
        embed = discord.Embed(
            description=f"A thread you were watching was deleted.\n**Thread:** {thread.name} (`{thread.id}`)\n**Server:** {thread.guild.name}",
            color=_color("EMBED_WARN_COLOR"),
        )
        for row in rows:
            user = self.bot.get_user(row["user_id"])
            if not user:
                try:
                    user = await self.bot.fetch_user(row["user_id"])
                except discord.HTTPException:
                    continue
            try:
                await user.send(embed=embed)
            except discord.HTTPException:
                pass

    @commands.group(
        name="role",
        aliases=["r"],
        invoke_without_command=True,
        help="Add or remove a role from a member",
        extras={"parameters": "member role", "usage": "role (member) (role)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def role(self, ctx: TormentContext, member: discord.Member, *, role: discord.Role) -> None:
        if role >= ctx.guild.me.top_role:
            return await ctx.warn(f"I can't manage {role.mention} as it's above my highest role")
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.warn(f"You can't manage {role.mention} as it's above your highest role")
        if role in member.roles:
            await member.remove_roles(role, reason=f"Role toggle by {ctx.author} ({ctx.author.id})")
            await ctx.success(f"Successfully removed {role.mention} from {member.mention}")
        else:
            await member.add_roles(role, reason=f"Role toggle by {ctx.author} ({ctx.author.id})")
            await ctx.success(f"Successfully added {role.mention} to {member.mention}")

    @role.command(
        name="add",
        aliases=["grant"],
        help="Add a role to a member",
        extras={"parameters": "member role", "usage": "role add (member) (role)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def role_add(self, ctx: TormentContext, member: discord.Member, *, role: discord.Role) -> None:
        if role >= ctx.guild.me.top_role:
            return await ctx.warn(f"I can't manage {role.mention} as it's above my highest role")
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.warn(f"You can't manage {role.mention} as it's above your highest role")
        if role in member.roles:
            return await ctx.warn(f"{member.mention} already has {role.mention}")
        await member.add_roles(role, reason=f"Added by {ctx.author} ({ctx.author.id})")
        await ctx.success(f"Successfully added {role.mention} to {member.mention}")

    @role.command(
        name="remove",
        aliases=["revoke", "rm"],
        help="Remove a role from a member",
        extras={"parameters": "member role", "usage": "role remove (member) (role)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def role_remove(self, ctx: TormentContext, member: discord.Member, *, role: discord.Role) -> None:
        if role >= ctx.guild.me.top_role:
            return await ctx.warn(f"I can't manage {role.mention} as it's above my highest role")
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.warn(f"You can't manage {role.mention} as it's above your highest role")
        if role not in member.roles:
            return await ctx.warn(f"{member.mention} doesn't have {role.mention}")
        await member.remove_roles(role, reason=f"Removed by {ctx.author} ({ctx.author.id})")
        await ctx.success(f"Successfully removed {role.mention} from {member.mention}")

    @role.command(
        name="create",
        aliases=["make"],
        help="Create a new role",
        extras={"parameters": "name", "usage": "role create (name)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def role_create(self, ctx: TormentContext, *, name: str) -> None:
        if len(ctx.guild.roles) >= 250:
            return await ctx.warn("This server has reached the maximum number of roles (**250**)")
        role = await ctx.guild.create_role(name=name, reason=f"Created by {ctx.author} ({ctx.author.id})")
        await ctx.success(f"Successfully created {role.mention}")

    @role.command(
        name="delete",
        aliases=["del"],
        help="Delete a role",
        extras={"parameters": "role", "usage": "role delete (role)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def role_delete(self, ctx: TormentContext, *, role: discord.Role) -> None:
        if role >= ctx.guild.me.top_role:
            return await ctx.warn(f"I can't manage {role.mention} as it's above my highest role")
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.warn(f"You can't manage {role.mention} as it's above your highest role")
        name = role.name
        await role.delete(reason=f"Deleted by {ctx.author} ({ctx.author.id})")
        await ctx.success(f"Successfully deleted the **{name}** role")

    @role.command(
        name="color",
        aliases=["colour"],
        help="Change a role's color",
        extras={"parameters": "role color", "usage": "role color (role) (color)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def role_color(self, ctx: TormentContext, role: discord.Role, *, color: discord.Color) -> None:
        if role >= ctx.guild.me.top_role:
            return await ctx.warn(f"I can't manage {role.mention} as it's above my highest role")
        await role.edit(color=color, reason=f"Color changed by {ctx.author} ({ctx.author.id})")
        await ctx.success(f"Successfully changed {role.mention}'s color to `{color}`")

    @role.command(
        name="rename",
        aliases=["name"],
        help="Rename a role",
        extras={"parameters": "role name", "usage": "role rename (role) (name)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def role_rename(self, ctx: TormentContext, role: discord.Role, *, name: str) -> None:
        if role >= ctx.guild.me.top_role:
            return await ctx.warn(f"I can't manage {role.mention} as it's above my highest role")
        await role.edit(name=name, reason=f"Renamed by {ctx.author} ({ctx.author.id})")
        await ctx.success(f"Successfully renamed the role to **{name}**")

    @role.command(
        name="hoist",
        help="Toggle whether a role is shown separately in the member list",
        extras={"parameters": "role", "usage": "role hoist (role)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def role_hoist(self, ctx: TormentContext, *, role: discord.Role) -> None:
        if role >= ctx.guild.me.top_role:
            return await ctx.warn(f"I can't manage {role.mention} as it's above my highest role")
        await role.edit(hoist=not role.hoist, reason=f"Hoist toggled by {ctx.author} ({ctx.author.id})")
        state = "now" if role.hoist else "no longer"
        await ctx.success(f"Successfully updated {role.mention} — it is {state} hoisted")

    @role.command(
        name="mentionable",
        help="Toggle whether a role can be mentioned by everyone",
        extras={"parameters": "role", "usage": "role mentionable (role)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def role_mentionable(self, ctx: TormentContext, *, role: discord.Role) -> None:
        if role >= ctx.guild.me.top_role:
            return await ctx.warn(f"I can't manage {role.mention} as it's above my highest role")
        await role.edit(mentionable=not role.mentionable, reason=f"Mentionable toggled by {ctx.author} ({ctx.author.id})")
        state = "now" if role.mentionable else "no longer"
        await ctx.success(f"Successfully updated {role.mention} — it is {state} mentionable")

    @role.command(
        name="icon",
        help="Set a role's icon (requires boost level 2)",
        extras={"parameters": "role icon", "usage": "role icon (role) [emoji/attachment]"},
    )
    @commands.has_permissions(manage_roles=True)
    async def role_icon(self, ctx: TormentContext, role: discord.Role, *, icon: str = None) -> None:
        if ctx.guild.premium_tier < 2:
            return await ctx.warn("Role icons require **Server Boost Level 2** or higher")
        if role >= ctx.guild.me.top_role:
            return await ctx.warn(f"I can't manage {role.mention} as it's above my highest role")
        import re as _re
        import aiohttp
        reason = f"Icon changed by {ctx.author} ({ctx.author.id})"
        if ctx.message.attachments:
            att = ctx.message.attachments[0]
            if not att.content_type or not att.content_type.startswith("image/"):
                return await ctx.warn("Attachment must be an image")
            await role.edit(display_icon=await att.read(), reason=reason)
            return await ctx.success(f"Successfully changed {role.mention}'s icon")
        if icon:
            custom = _re.fullmatch(r"<(?:a?):(\w+):(\d+)>", icon)
            if custom:
                emoji_id = custom.group(2)
                ext = "gif" if icon.startswith("<a:") else "png"
                url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"
            else:
                code = "-".join(f"{ord(c):x}" for c in icon)
                url = f"https://twemoji.maxcdn.com/v/latest/72x72/{code}.png"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return await ctx.warn("Invalid emoji provided")
                    data = await resp.read()
            await role.edit(display_icon=data, reason=reason)
            return await ctx.success(f"Successfully changed {role.mention}'s icon to {icon}")
        return await ctx.warn("Provide an emoji or attach an image")

    @role.group(
        name="all",
        aliases=["everyone"],
        invoke_without_command=True,
        help="Add a role to all members",
        extras={"parameters": "role", "usage": "role all (role)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def role_all(self, ctx: TormentContext, *, role: discord.Role) -> None:
        await _do_mass_role(ctx, role)

    @role_all.command(
        name="remove",
        aliases=["revoke", "rm"],
        help="Remove a role from all members",
        extras={"parameters": "role", "usage": "role all remove (role)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def role_all_remove(self, ctx: TormentContext, *, role: discord.Role) -> None:
        await _do_mass_role(ctx, role, action="remove")

    @role.group(
        name="humans",
        invoke_without_command=True,
        help="Add a role to all human members",
        extras={"parameters": "role", "usage": "role humans (role)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def role_humans(self, ctx: TormentContext, *, role: discord.Role) -> None:
        await _do_mass_role(ctx, role, predicate=lambda m: not m.bot)

    @role_humans.command(
        name="remove",
        aliases=["revoke", "rm"],
        help="Remove a role from all human members",
        extras={"parameters": "role", "usage": "role humans remove (role)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def role_humans_remove(self, ctx: TormentContext, *, role: discord.Role) -> None:
        await _do_mass_role(ctx, role, predicate=lambda m: not m.bot, action="remove")

    @role.group(
        name="bots",
        invoke_without_command=True,
        help="Add a role to all bots",
        extras={"parameters": "role", "usage": "role bots (role)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def role_bots(self, ctx: TormentContext, *, role: discord.Role) -> None:
        await _do_mass_role(ctx, role, predicate=lambda m: m.bot)

    @role_bots.command(
        name="remove",
        aliases=["revoke", "rm"],
        help="Remove a role from all bots",
        extras={"parameters": "role", "usage": "role bots remove (role)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def role_bots_remove(self, ctx: TormentContext, *, role: discord.Role) -> None:
        await _do_mass_role(ctx, role, predicate=lambda m: m.bot, action="remove")

    @role.command(
        name="has",
        aliases=["with", "in"],
        help="Add a role to all members who have another role",
        extras={"parameters": "role assign_role", "usage": "role has (role) (assign_role)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def role_has(self, ctx: TormentContext, role: discord.Role, *, assign_role: discord.Role) -> None:
        await _do_mass_role(ctx, assign_role, predicate=lambda m: role in m.roles)

    @commands.group(
        name="nuke",
        invoke_without_command=True,
        help="Clone the current channel and delete the original",
        extras={"parameters": "n/a", "usage": "nuke"},
    )
    @commands.has_permissions(administrator=True)
    async def nuke(self, ctx: TormentContext) -> None:
        if not isinstance(ctx.channel, discord.TextChannel):
            return await ctx.warn("This command can only be used in text channels")
        if not await ctx.confirm("Are you sure you want to nuke this channel? This action is irreversible."):
            return
        channel = ctx.channel
        new_channel = await channel.clone(reason=f"Nuked by {ctx.author} ({ctx.author.id})")
        synced = await _reconfigure_channel_settings(self.bot.storage.pool, ctx.guild, channel, new_channel)
        await asyncio.gather(
            new_channel.edit(position=channel.position),
            channel.delete(reason=f"Nuked by {ctx.author} ({ctx.author.id})"),
        )
        embed = discord.Embed(
            title="Channel Nuked",
            description=f"This channel was nuked by {ctx.author.mention}",
            color=_color("EMBED_SUCCESS_COLOR"),
        )
        if synced:
            embed.add_field(name="Settings Synced", value=">>> " + "\n".join(synced))
        await new_channel.send(embed=embed)

    @nuke.command(
        name="schedule",
        aliases=["add", "timer"],
        help="Schedule automatic nukes for a channel",
        extras={"parameters": "channel interval", "usage": "nuke schedule (channel) (interval)"},
    )
    @commands.has_permissions(administrator=True)
    async def nuke_schedule(self, ctx: TormentContext, channel: discord.TextChannel, *, interval: str) -> None:
        delta = _parse_duration(interval)
        if delta is None:
            return await ctx.warn("Invalid interval. Use formats like `1h`, `6h`, `1d`, `7d` (min 1h, max 7d)")
        if delta < timedelta(hours=1) or delta > timedelta(days=7):
            return await ctx.warn("Interval must be between **1 hour** and **7 days**")
        next_trigger = datetime.now(timezone.utc) + delta
        await self.bot.storage.pool.execute(
            """
            INSERT INTO nuke_schedule (guild_id, channel_id, interval, next_trigger)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, channel_id) DO UPDATE SET
                interval = EXCLUDED.interval,
                next_trigger = EXCLUDED.next_trigger
            """,
            ctx.guild.id, channel.id, delta, next_trigger,
        )
        await ctx.success(f"Successfully scheduled {channel.mention} to be nuked every **{_fmt_delta(delta)}**")

    @nuke.command(
        name="remove",
        aliases=["delete", "del", "rm"],
        help="Remove a scheduled nuke from a channel",
        extras={"parameters": "channel", "usage": "nuke remove (channel)"},
    )
    @commands.has_permissions(administrator=True)
    async def nuke_remove(self, ctx: TormentContext, channel: discord.TextChannel) -> None:
        result = await self.bot.storage.pool.execute(
            "DELETE FROM nuke_schedule WHERE guild_id = $1 AND channel_id = $2",
            ctx.guild.id, channel.id,
        )
        if result == "DELETE 0":
            return await ctx.warn(f"{channel.mention} is not scheduled for automatic nukes")
        await ctx.success(f"Successfully removed the scheduled nuke from {channel.mention}")

    @nuke.command(
        name="list",
        help="View all channels scheduled for automatic nukes",
        extras={"parameters": "n/a", "usage": "nuke list"},
    )
    @commands.has_permissions(administrator=True)
    async def nuke_list(self, ctx: TormentContext) -> None:
        rows = await self.bot.storage.pool.fetch(
            "SELECT channel_id, interval FROM nuke_schedule WHERE guild_id = $1",
            ctx.guild.id,
        )
        entries = []
        for row in rows:
            ch = ctx.guild.get_channel(row["channel_id"])
            if ch:
                entries.append(f"{ch.mention} every **{_fmt_delta(row['interval'])}**")
        if not entries:
            return await ctx.warn("No channels are scheduled for automatic nukes")
        from bot.helpers.paginator import Paginator
        embed = discord.Embed(title="Scheduled Nukes", color=_color("EMBED_INFO_COLOR"))
        paginator = Paginator(ctx, entries, embed=embed, per_page=10, counter=True)
        await paginator.start()

    @commands.hybrid_command(
        name="inrole",
        help="List all members with a specific role",
        extras={"parameters": "role", "usage": "inrole (role)"},
    )
    @app_commands.describe(role="The role to list members for")
    async def inrole(self, ctx: TormentContext, *, role: discord.Role) -> None:
        if not ctx.guild.chunked:
            await ctx.guild.chunk(cache=True)
        members = [m for m in role.members]
        if not members:
            return await ctx.warn(f"No members have {role.mention}")
        entries = [f"{m.mention} (`{m.id}`)" for m in sorted(members, key=lambda m: m.display_name.lower())]
        from bot.helpers.paginator import Paginator
        embed = discord.Embed(
            title=f"Members with {role.name}",
            color=role.color if role.color.value else _color("EMBED_INFO_COLOR"),
        )
        embed.set_footer(text=f"{len(members)} member{'s' if len(members) != 1 else ''}")
        paginator = Paginator(ctx, entries, embed=embed, per_page=10, counter=True)
        await paginator.start()


async def _do_mass_role(
    ctx: TormentContext,
    role: discord.Role,
    predicate=lambda m: True,
    action: str = "add",
) -> None:
    if not ctx.guild.me.guild_permissions.manage_roles:
        return await ctx.warn("I don't have permission to **manage roles**")
    if not ctx.guild.chunked:
        await ctx.guild.chunk(cache=True)
    verb = "to" if action == "add" else "from"
    members = []
    for member in ctx.guild.members:
        if not predicate(member):
            continue
        if action == "add" and role in member.roles:
            continue
        if action == "remove" and role not in member.roles:
            continue
        if role >= ctx.guild.me.top_role:
            continue
        members.append(member)
    if not members:
        return await ctx.warn(f"No members to {action} {role.mention} {verb}")
    msg = await ctx.success(f"{'Adding' if action == 'add' else 'Removing'} {role.mention} {verb} **{len(members)}** members...")
    success, failed = 0, 0
    for member in members:
        try:
            if action == "add":
                await member.add_roles(role, reason=f"Mass role by {ctx.author} ({ctx.author.id})")
            else:
                await member.remove_roles(role, reason=f"Mass role by {ctx.author} ({ctx.author.id})")
            success += 1
        except discord.HTTPException:
            failed += 1
    try:
        await msg.delete()
    except discord.HTTPException:
        pass
    result = f"Successfully {'added' if action == 'add' else 'removed'} {role.mention} {verb} **{success}** member{'s' if success != 1 else ''}"
    if failed:
        result += f" (**{failed}** failed)"
    await ctx.success(result)


async def _reconfigure_channel_settings(pool, guild: discord.Guild, old: discord.TextChannel, new: discord.TextChannel) -> list[str]:
    synced = []
    tables = [
        ("welcome_messages", "Welcome Messages"),
        ("goodbye_messages", "Goodbye Messages"),
        ("boost_messages", "Boost Messages"),
        ("sticky", "Sticky Message"),
        ("command_disabled", "Disabled Commands"),
        ("reaction_roles", "Reaction Roles"),
        ("birthday_config", "Birthday Channel"),
    ]
    for table, label in tables:
        result = await pool.execute(
            f"UPDATE {table} SET channel_id = $2 WHERE channel_id = $1",
            old.id, new.id,
        )
        if result != "UPDATE 0":
            synced.append(label)
    return synced


def _parse_duration(text: str) -> timedelta | None:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    import re
    match = re.fullmatch(r"(\d+)\s*([smhdw])", text.strip().lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    return timedelta(seconds=value * units[unit])


def _fmt_delta(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    if total >= 86400 and total % 86400 == 0:
        d = total // 86400
        return f"{d} day{'s' if d != 1 else ''}"
    if total >= 3600 and total % 3600 == 0:
        h = total // 3600
        return f"{h} hour{'s' if h != 1 else ''}"
    if total >= 60 and total % 60 == 0:
        m = total // 60
        return f"{m} minute{'s' if m != 1 else ''}"
    return f"{total} second{'s' if total != 1 else ''}"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))

