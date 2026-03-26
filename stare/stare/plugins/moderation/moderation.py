import discord
from discord.ext import commands
from discord.ext.commands import Cog, command, has_permissions
from discord import Member, User, TextChannel, Message
from discord.ui import View, Button
from stare.core.tools.context import CustomContext as Context
from stare.core.tools.paginator import PaginatorView
from stare.core.config import Config
from typing import Optional
from datetime import timedelta
import re


class Time:
    @staticmethod
    def convert(duration: int, unit: str) -> int:
        """Convert time duration to seconds"""
        units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}
        return duration * units.get(unit.lower(), 0)


class ConfirmationView(View):
    def __init__(self, ctx: Context, member: Member, reason: str, action: str):
        super().__init__(timeout=30)
        self.ctx = ctx
        self.member = member
        self.reason = reason
        self.action = action
        self.confirmed = False

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("u cant use this lil bro", ephemeral=True)
        
        self.confirmed = True
        self.stop()
        await interaction.response.edit_message(content=f"**Confirmed** {self.action} for {self.member.mention}", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("u cant use this lil bro", ephemeral=True)
        
        self.stop()
        await interaction.response.edit_message(content=f"aw man i wanted to go kaboom on them... maybe next time", view=None)


class Moderation(Cog):
    """Moderation commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    def is_bot_owner(self, user_id: int) -> bool:
        """Check if user is a bot owner"""
        return user_id in self.bot.owner_ids
    
    def can_bypass_permissions(self, user_id: int) -> bool:
        """Check if user can bypass permission checks"""
        return self.is_bot_owner(user_id)
    
    async def cog_load(self):
        """Create moderation tables if they don't exist"""
        if not self.bot.db_pool:
            return
        
        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS mod_logs (
                guild_id BIGINT PRIMARY KEY,
                channel_id BIGINT
            )
        """)
        
        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS message_logs (
                guild_id BIGINT PRIMARY KEY,
                channel_id BIGINT
            )
        """)
        
        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS vc_logs (
                guild_id BIGINT PRIMARY KEY,
                channel_id BIGINT
            )
        """)
        
        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS force_nicknames (
                guild_id BIGINT,
                user_id BIGINT,
                nickname TEXT,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        
        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                moderator_id BIGINT NOT NULL,
                reason TEXT NOT NULL,
                warned_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS hardbans (
                user_id BIGINT,
                guild_id BIGINT,
                reason TEXT,
                banned_by BIGINT,
                banned_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (user_id, guild_id)
            )
        """)
        
        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS ping_on_join (
                guild_id BIGINT PRIMARY KEY,
                channel_id BIGINT
            )
        """)
    
    @command(name="ban", aliases=["b"], help="Ban a member from the server")
    async def ban(self, ctx: Context, member: Optional[Member] = None, *, reason: Optional[str] = "No reason provided") -> Message:
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        # Check permissions (bypass for bot owners)
        if not self.can_bypass_permissions(ctx.author.id):
            if not ctx.author.guild_permissions.ban_members:
                return await ctx.warn("You are missing permission(s): `Ban Members`")
        
        if member is None:
            return await ctx.deny("Please mention a member to ban.")
        
        if member == ctx.author:
            return await ctx.deny("You **can't** ban yourself.")
        
        # Protect bot owners from being banned
        if self.is_bot_owner(member.id):
            return await ctx.deny("You **can't** ban a bot owner.")
        
        # Skip role hierarchy check for bot owners
        if not self.can_bypass_permissions(ctx.author.id):
            if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner.id:
                return await ctx.deny("You **can't** ban a member with a higher role.")
        
        # Check if user is boosting
        if member.premium_since:
            # Check if there's a pending confirmation for this user
            cache_key = f"ban_confirm_{ctx.guild.id}_{member.id}_{ctx.author.id}"
            
            if not hasattr(self.bot, '_ban_confirmations'):
                self.bot._ban_confirmations = {}
            
            if cache_key not in self.bot._ban_confirmations:
                # First attempt - warn about booster
                self.bot._ban_confirmations[cache_key] = True
                # Set expiry after 60 seconds
                import asyncio
                asyncio.create_task(self._clear_ban_confirmation(cache_key, 60))
                return await ctx.warn(f'This user is currently **boosting** the server! Run the command again to confirm the ban.')
            else:
                # Second attempt - proceed with ban
                del self.bot._ban_confirmations[cache_key]
        
        try:
            await member.ban(reason=reason)
            return await ctx.approve(f"**Banned** {member.mention} for: **{reason}**")
        except discord.Forbidden:
            return await ctx.deny(f"I don't have permission to ban {member.mention}. Make sure my role is higher than theirs.")
        except Exception as e:
            return await ctx.deny(f"Failed to ban {member.mention}: {str(e)}")
    
    async def _clear_ban_confirmation(self, cache_key: str, delay: int):
        """Clear ban confirmation after delay"""
        import asyncio
        await asyncio.sleep(delay)
        if hasattr(self.bot, '_ban_confirmations') and cache_key in self.bot._ban_confirmations:
            del self.bot._ban_confirmations[cache_key]

    
    @commands.group(name="warn", aliases=["w"], invoke_without_command=True, help="Warn a member")
    @has_permissions(moderate_members=True)
    async def warn(self, ctx: Context, member: Optional[Member] = None, *, reason: Optional[str] = "No reason provided") -> Message:
        """Warn system commands"""
        if member is None:
            return await ctx.deny("Please mention a member to warn.")
        
        # Default behavior: add a warning
        return await self.warn_add(ctx, member, reason=reason)
    
    @warn.command(name="add", help="Add a warning to a member")
    @has_permissions(moderate_members=True)
    async def warn_add(self, ctx: Context, member: Optional[Member] = None, *, reason: Optional[str] = "No reason provided") -> Message:
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if member is None:
            return await ctx.deny("Please mention a member to warn.")
        
        if member == ctx.author:
            return await ctx.deny("You **can't** warn yourself.")
        
        if member.bot:
            return await ctx.deny("You **can't** warn bots.")
        
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner.id:
            return await ctx.deny("You **can't** warn a member with a higher role.")
        
        # Add warning to database
        warn_id = await self.bot.db_pool.fetchval(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES ($1, $2, $3, $4) RETURNING id",
            ctx.guild.id, member.id, ctx.author.id, reason
        )
        
        # Get total warnings for this user
        total_warns = await self.bot.db_pool.fetchval(
            "SELECT COUNT(*) FROM warnings WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id
        )
        
        # Try to DM the user
        try:
            dm_embed = discord.Embed(
                title="⚠️ You have been warned",
                color=Config.COLORS.WARNING
            )
            dm_embed.add_field(name="Server", value=ctx.guild.name, inline=True)
            dm_embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            dm_embed.add_field(name="Total Warnings", value=str(total_warns), inline=True)
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.set_footer(text=f"Warning ID: {warn_id}")
            if ctx.guild.icon:
                dm_embed.set_thumbnail(url=ctx.guild.icon.url)
            await member.send(embed=dm_embed)
        except:
            pass  # User has DMs disabled
        
        return await ctx.approve(f"**Warned** {member.mention} for: **{reason}** (Total warnings: **{total_warns}**)")
    
    @warn.command(name="list", aliases=["view", "check"], help="View warnings for a member")
    @has_permissions(moderate_members=True)
    async def warn_list(self, ctx: Context, member: Optional[Member] = None) -> Message:
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if member is None:
            member = ctx.author
        
        # Get all warnings for this user
        warns = await self.bot.db_pool.fetch(
            "SELECT * FROM warnings WHERE guild_id = $1 AND user_id = $2 ORDER BY warned_at DESC",
            ctx.guild.id, member.id
        )
        
        if not warns:
            return await ctx.deny(f"{member.mention} has **no warnings**.")
        
        # Create embed
        embed = discord.Embed(
            title=f"Warnings for {member.display_name}",
            description=f"**Total Warnings:** {len(warns)}",
            color=Config.COLORS.DEFAULT
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        
        for warn in warns[:5]:  # Show first 5
            moderator = ctx.guild.get_member(warn['moderator_id'])
            mod_name = moderator.display_name if moderator else "Unknown Moderator"
            timestamp = discord.utils.format_dt(warn['warned_at'], 'R')
            embed.add_field(
                name=f"Warning #{warn['id']}",
                value=f"**Reason:** {warn['reason']}\n**Moderator:** {mod_name}\n**Date:** {timestamp}",
                inline=False
            )
        
        if len(warns) > 5:
            embed.set_footer(text=f"Showing 5 of {len(warns)} warnings")
        
        await ctx.send(embed=embed)
    
    @warn.command(name="clear", aliases=["reset"], help="Clear all warnings for a member")
    @has_permissions(moderate_members=True)
    async def warn_clear(self, ctx: Context, member: Optional[Member] = None) -> Message:
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if member is None:
            return await ctx.deny("Please mention a member.")
        
        # Get warning count before deletion
        warn_count = await self.bot.db_pool.fetchval(
            "SELECT COUNT(*) FROM warnings WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id
        )
        
        if warn_count == 0:
            return await ctx.deny(f"{member.mention} has **no warnings** to clear.")
        
        # If multiple warnings, require confirmation
        if warn_count > 1:
            view = ConfirmationView(ctx, member, f"clear {warn_count} warnings", "clear warnings")
            embed = discord.Embed(
                title="⚠️ Clear Warnings Confirmation",
                description=f"Are you sure you want to **clear all {warn_count} warnings** from {member.mention}?\n\nTo remove a specific warning, use `{Config.PREFIX}warn remove <member> <warning_id>` instead.",
                color=Config.COLORS.WARNING
            )
            message = await ctx.send(embed=embed, view=view)
            await view.wait()
            
            if not view.confirmed:
                return
        
        # Delete all warnings
        await self.bot.db_pool.execute(
            "DELETE FROM warnings WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id
        )
        
        return await ctx.approve(f"**Cleared** {warn_count} warning(s) from {member.mention}")
    
    @warn.command(name="remove", aliases=["delete", "del"], help="Delete a specific warning by ID")
    @has_permissions(moderate_members=True)
    async def warn_remove(self, ctx: Context, member: Optional[Member] = None, warn_id: Optional[int] = None) -> Message:
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if member is None or warn_id is None:
            return await ctx.deny(f"Usage: `{Config.PREFIX}warn remove <member> <warning_id>`")
        
        # Check if warning exists for this specific user in this guild
        warn = await self.bot.db_pool.fetchrow(
            "SELECT * FROM warnings WHERE id = $1 AND guild_id = $2 AND user_id = $3",
            warn_id, ctx.guild.id, member.id
        )
        
        if not warn:
            return await ctx.deny(f"Warning with ID **{warn_id}** not found for {member.mention} in this server.")
        
        # Delete the warning
        await self.bot.db_pool.execute("DELETE FROM warnings WHERE id = $1", warn_id)
        
        return await ctx.approve(f"**Deleted** warning **#{warn_id}** from {member.mention}")
    
    @command(name="kick", aliases=["k"], help="Kick a member from the server")
    async def kick(self, ctx: Context, member: Optional[Member] = None, *, reason: Optional[str] = "No reason provided") -> Message:
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        # Check permissions (bypass for bot owners)
        if not self.can_bypass_permissions(ctx.author.id):
            if not ctx.author.guild_permissions.kick_members:
                return await ctx.warn("You are missing permission(s): `Kick Members`")
        
        if member is None:
            return await ctx.deny("Please mention a member to kick.")
        
        if member == ctx.author:
            return await ctx.deny("You **can't** kick yourself.")
        
        # Protect bot owners from being kicked
        if self.is_bot_owner(member.id):
            return await ctx.deny("You **can't** kick a bot owner.")
        
        # Skip role hierarchy check for bot owners
        if not self.can_bypass_permissions(ctx.author.id):
            if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner.id:
                return await ctx.deny("You **can't** kick a member with a higher role.")
        
        try:
            await member.kick(reason=reason)
            return await ctx.approve(f"**Kicked** {member.mention} for: **{reason}**")
        except discord.Forbidden:
            return await ctx.deny(f"I don't have permission to kick {member.mention}. Make sure my role is higher than theirs.")
        except Exception as e:
            return await ctx.deny(f"Failed to kick {member.mention}: {str(e)}")
    
    @command(name="unban", aliases=["ub"], help="Unban a member from the server")
    @has_permissions(ban_members=True)
    async def unban(self, ctx: Context, member: Optional[User] = None, *, reason: Optional[str] = "No reason provided") -> Message:
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if member is None:
            return await ctx.deny("Please provide a user to unban.")
        
        if member == ctx.author:
            return await ctx.deny("You **can't** unban yourself.")
        
        try:
            await ctx.guild.unban(member, reason=reason)
            return await ctx.approve(f"**Unbanned** {member.mention} for: **{reason}**")
        except discord.NotFound:
            return await ctx.deny(f"{member.mention} is not banned.")
        except discord.Forbidden:
            return await ctx.deny("I don't have permission to unban members.")
        except Exception as e:
            return await ctx.deny(f"Failed to unban {member.mention}: {str(e)}")
    
    @command(name="timeout", help="Timeout a member from the server", aliases=["tm", "mute"])
    async def timeout(self, ctx: Context, member: Optional[Member] = None, duration: str = None, *, reason: Optional[str] = "No reason provided") -> Message:
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        # Check permissions (bypass for bot owners)
        if not self.can_bypass_permissions(ctx.author.id):
            if not ctx.author.guild_permissions.moderate_members:
                return await ctx.warn("You are missing permission(s): `Moderate Members`")
        
        if member is None or duration is None:
            return await ctx.deny(f"Usage: `{Config.PREFIX}timeout <member> <duration> [reason]`")
        
        if member == ctx.author:
            return await ctx.deny("You **can't** timeout yourself.")
        
        # Protect bot owners from being timed out
        if self.is_bot_owner(member.id):
            return await ctx.deny("You **can't** timeout a bot owner.")
        
        # Skip role hierarchy check for bot owners
        if not self.can_bypass_permissions(ctx.author.id):
            if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner.id:
                return await ctx.deny("You **can't** timeout a member with a higher role.")
        
        # Parse duration string (e.g., "10m", "5h", "1d")
        match = re.match(r'^(\d+)([smhdw])$', duration.lower())
        if not match:
            return await ctx.deny("**Invalid** duration format. Use format like: `10m`, `5h`, `1d`")
        
        amount, unit = match.groups()
        seconds = Time.convert(int(amount), unit)
        
        if seconds == 0:
            return await ctx.deny("**Invalid** duration or unit.")
        
        if seconds > 2419200:  # Discord's max timeout is 28 days
            return await ctx.deny("Timeout duration cannot exceed **28 days**.")
        
        try:
            await member.timeout(timedelta(seconds=seconds), reason=reason)
            
            # Format duration for display
            if unit == 's':
                duration_text = f"{amount} second(s)"
            elif unit == 'm':
                duration_text = f"{amount} minute(s)"
            elif unit == 'h':
                duration_text = f"{amount} hour(s)"
            elif unit == 'd':
                duration_text = f"{amount} day(s)"
            elif unit == 'w':
                duration_text = f"{amount} week(s)"
            
            return await ctx.approve(f"**Timed out** {member.mention} for **{duration_text}** - Reason: **{reason}**")
        except discord.Forbidden:
            return await ctx.deny(f"I don't have permission to timeout {member.mention}. Make sure my role is higher than theirs.")
        except Exception as e:
            return await ctx.deny(f"Failed to timeout {member.mention}: {str(e)}")

    
    @command(name="untimeout", help="Untimeout a member from the server", aliases=["utm", "unmute"])
    @has_permissions(moderate_members=True)
    async def untimeout(self, ctx: Context, member: Optional[Member] = None, *, reason: Optional[str] = "No reason provided") -> Message:
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if member is None:
            return await ctx.deny("Please mention a member to untimeout.")
        
        if member == ctx.author:
            return await ctx.deny("You **can't** untimeout yourself.")
        
        await member.timeout(None, reason=reason)
        return await ctx.approve(f"**Untimed out** {member.mention} for: **{reason}**")
    
    @command(name="purge", help="Purge messages from the channel", aliases=["clear"])
    @has_permissions(manage_messages=True)
    async def purge(self, ctx: Context, amount: int = None, *, reason: Optional[str] = "No reason provided") -> Message:
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if amount is None:
            return await ctx.deny("Please provide an amount of messages to purge.")
        
        if amount <= 0:
            return await ctx.deny("**Invalid** amount.")
        
        if not isinstance(ctx.channel, TextChannel):
            return await ctx.deny("This command can **only** be used in a text channel.")
        
        await ctx.channel.purge(limit=amount)
        return await ctx.approve(f"**Purged** {amount} messages for: **{reason}**")
    
    @command(name="lock", aliases=["l"], help="Lock a channel")
    @has_permissions(manage_roles=True)
    async def lock(self, ctx: Context, channel: Optional[TextChannel] = None):
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if channel is None:
            channel = ctx.channel
        
        await channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.message.add_reaction("🔒")
    
    @command(name="unlock", aliases=["ul"], help="Unlock a channel")
    @has_permissions(manage_roles=True)
    async def unlock(self, ctx: Context, channel: Optional[TextChannel] = None):
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if channel is None:
            channel = ctx.channel
        
        await channel.set_permissions(ctx.guild.default_role, send_messages=True)
        await ctx.message.add_reaction("🔓")
    
    @command(name="hide", help="Hide a channel")
    @has_permissions(manage_roles=True)
    async def hide(self, ctx: Context, channel: Optional[TextChannel] = None):
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if channel is None:
            channel = ctx.channel
        
        await channel.set_permissions(ctx.guild.default_role, view_channel=False)
        await ctx.message.add_reaction("👻")
    
    @command(name="reveal", help="Reveal a channel")
    @has_permissions(manage_roles=True)
    async def reveal(self, ctx: Context, channel: Optional[TextChannel] = None):
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if channel is None:
            channel = ctx.channel
        
        await channel.set_permissions(ctx.guild.default_role, view_channel=True)
        await ctx.message.add_reaction("👁")
    
    @command(name="hardban", aliases=["hb"], help="Bans a member and autobans them when they get unbanned")
    @has_permissions(ban_members=True)
    async def hardban(self, ctx: Context, member: Optional[Member] = None, *, reason: Optional[str] = "No reason provided") -> Message:
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if member is None:
            return await ctx.deny("Please mention a member to hardban.")
        
        if member == ctx.author:
            return await ctx.deny("You **can't** hardban yourself.")
        
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner.id:
            return await ctx.deny("You **can't** hardban a member with a higher role.")
        
        # Confirmation view
        view = ConfirmationView(ctx, member, reason, "hardban")
        embed = discord.Embed(
            title="",
            description=f"Are you sure you want to **hardban** {member.mention}?",
            color=0x8B0000
        )
        message = await ctx.send(embed=embed, view=view)
        await view.wait()
        
        if view.confirmed:
            await member.ban(reason=f"[HARDBAN] {reason}", delete_message_days=7)
            
            # Store in hardban database
            await self.bot.db_pool.execute(
                "INSERT INTO hardbans (user_id, guild_id, reason, banned_by) VALUES ($1, $2, $3, $4) ON CONFLICT (user_id, guild_id) DO UPDATE SET reason = $3, banned_by = $4, banned_at = NOW()",
                member.id, ctx.guild.id, reason, ctx.author.id
            )
            
            return await ctx.approve(f"**Hardbanned** {member.mention} for: **{reason}**")
        else:
            return await ctx.deny("Hardban **cancelled**.")
    
    @command(name="softban", aliases=["sb"], help="Ban and immediately unban a member to clear their messages")
    @has_permissions(ban_members=True)
    async def softban(self, ctx: Context, member: Optional[Member] = None, *, reason: Optional[str] = "No reason provided") -> Message:
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if member is None:
            return await ctx.deny("Please mention a member to softban.")
        
        if member == ctx.author:
            return await ctx.deny("You **can't** softban yourself.")
        
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner.id:
            return await ctx.deny("You **can't** softban a member with a higher role.")
        
        try:
            await member.ban(reason=f"[SOFTBAN] {reason}", delete_message_days=1)
            await ctx.guild.unban(member, reason=f"[SOFTBAN UNBAN] {reason}")
            return await ctx.approve(f"**Softbanned** {member.mention} for: **{reason}** (messages cleared)")
        except Exception as e:
            return await ctx.deny(f"Failed to softban {member.mention}: {str(e)}")
    
    @command(name="slowmode", help="Set slowmode for a channel", aliases=["sm"])
    @has_permissions(manage_channels=True)
    async def slowmode(self, ctx: Context, seconds: Optional[int] = None, channel: Optional[TextChannel] = None) -> Message:
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if seconds is None:
            return await ctx.deny("Please provide a slowmode duration in seconds.")
        
        if channel is None:
            channel = ctx.channel
        
        if not isinstance(channel, TextChannel):
            return await ctx.deny("This command can **only** be used in a text channel.")
        
        if seconds < 0 or seconds > 21600:  # Discord's max slowmode is 6 hours
            return await ctx.deny("Slowmode must be between **0** and **21600** seconds (6 hours).")
        
        await channel.edit(slowmode_delay=seconds)
        
        if seconds == 0:
            return await ctx.approve(f"**Disabled** slowmode in {channel.mention}")
        else:
            return await ctx.approve(f"**Set** slowmode to **{seconds}** seconds in {channel.mention}")
    
    @command(name="unhardban", help="Remove a user from hardban list and unban them", aliases=["hardban_remove"])
    @has_permissions(ban_members=True)
    async def unhardban(self, ctx: Context, user: Optional[User] = None, *, reason: Optional[str] = "No reason provided") -> Message:
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if user is None:
            return await ctx.deny("Please provide a user to unhardban.")
        
        # Check if user is hardbanned
        hardban_record = await self.bot.db_pool.fetchrow(
            "SELECT * FROM hardbans WHERE user_id = $1 AND guild_id = $2",
            user.id, ctx.guild.id
        )
        
        if not hardban_record:
            return await ctx.deny(f"{user.mention} is **not** hardbanned.")
        
        try:
            # Remove from hardban database
            await self.bot.db_pool.execute(
                "DELETE FROM hardbans WHERE user_id = $1 AND guild_id = $2",
                user.id, ctx.guild.id
            )
            
            # Unban the user
            await ctx.guild.unban(user, reason=f"[UNHARDBAN] {reason}")
            return await ctx.approve(f"**Removed hardban** for {user.mention} and unbanned them.")
        except discord.NotFound:
            # User wasn't banned, just remove from database
            return await ctx.approve(f"**Removed hardban** for {user.mention} (they weren't banned).")
        except Exception as e:
            return await ctx.deny(f"Failed to unhardban {user.mention}: {str(e)}")

    
    @command(name="inrole", aliases=["ir"], help="List all members with a specific role")
    @has_permissions(manage_roles=True)
    async def inrole(self, ctx: Context, role: discord.Role):
        """List all members with a specific role"""
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        members = role.members
        
        if not members:
            return await ctx.deny(f"No members have the {role.mention} role.")
        
        # Format members as numbered list with just mentions
        member_list = []
        for i, member in enumerate(members, 1):
            member_list.append(f"`{i:02d}` {member.mention}")
        
        # Split into pages of 10 members each
        pages = []
        per_page = 10
        for i in range(0, len(member_list), per_page):
            page_members = member_list[i:i + per_page]
            embed = discord.Embed(
                description=f"**Members with {role.name}**\n\n" + "\n".join(page_members),
                color=Config.COLORS.DEFAULT
            )
            embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
            pages.append(embed)
        
        # Use paginator if multiple pages
        if len(pages) > 1:
            paginator = PaginatorView(pages, user=ctx.author)
            message = await ctx.send(embed=pages[0], view=paginator)
            return message
        else:
            return await ctx.send(embed=pages[0])
    
    @command(name="invoke", aliases=["sudo"], help="Make a user run a command")
    @has_permissions(administrator=True)
    async def invoke(self, ctx: Context, member: Member, *, command: str):
        """Make another user invoke a command"""
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        # Create a fake message from the member
        msg = ctx.message
        msg.author = member
        msg.content = command
        new_ctx = await self.bot.get_context(msg, cls=type(ctx))
        await self.bot.invoke(new_ctx)
    
    @command(name="forcenickname", aliases=["forcenick", "fn"], help="Force a nickname on a user")
    @has_permissions(manage_nicknames=True)
    async def forcenickname(self, ctx: Context, member: Member, *, nickname: str):
        """Force a nickname on a user that persists"""
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if len(nickname) > 32:
            return await ctx.deny("Nickname must be 32 characters or less.")
        
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner.id:
            return await ctx.deny("You **can't** force nickname a member with a higher role.")
        
        # Store in database
        await self.bot.db_pool.execute(
            "INSERT INTO force_nicknames (guild_id, user_id, nickname) VALUES ($1, $2, $3) ON CONFLICT (guild_id, user_id) DO UPDATE SET nickname = $3",
            ctx.guild.id, member.id, nickname
        )
        
        # Apply nickname
        await member.edit(nick=nickname)
        return await ctx.approve(f"Forced nickname **{nickname}** on {member.mention}")
    
    @command(name="unforcenickname", aliases=["unforcenick", "ufn"], help="Remove forced nickname from a user")
    @has_permissions(manage_nicknames=True)
    async def unforcenickname(self, ctx: Context, member: Member):
        """Remove forced nickname from a user"""
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        result = await self.bot.db_pool.execute(
            "DELETE FROM force_nicknames WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id
        )
        
        if result == "DELETE 0":
            return await ctx.deny(f"{member.mention} doesn't have a forced nickname.")
        
        return await ctx.approve(f"Removed forced nickname from {member.mention}")
    
    @command(name="changenickname", aliases=["cn", "nick"], help="Change a user's nickname")
    @has_permissions(manage_nicknames=True)
    async def changenickname(self, ctx: Context, member: Member, *, nickname: Optional[str] = None):
        """Change a user's nickname"""
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if nickname and len(nickname) > 32:
            return await ctx.deny("Nickname must be 32 characters or less.")
        
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner.id:
            return await ctx.deny("You **can't** change nickname of a member with a higher role.")
        
        await member.edit(nick=nickname)
        
        if nickname:
            return await ctx.approve(f"Changed {member.mention}'s nickname to **{nickname}**")
        else:
            return await ctx.approve(f"Removed {member.mention}'s nickname")
    
    @commands.group(name="role", aliases=['r'], invoke_without_command=True, help="Role management commands")
    @has_permissions(manage_roles=True)
    async def role(self, ctx: Context, member: discord.Member = None, role: discord.Role = None):
        """Role management commands - add/remove roles from members"""
        if member is None or role is None:
            return await ctx.send_help("role")
        
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        # Check if member has the role
        if role in member.roles:
            # Remove the role
            await member.remove_roles(role, reason=f"Role removed by {ctx.author}")
            return await ctx.approve(f"Removed {role.mention} from {member.mention}")
        else:
            # Add the role
            await member.add_roles(role, reason=f"Role added by {ctx.author}")
            return await ctx.approve(f"Added {role.mention} to {member.mention}")
    
    @role.command(name="create", help="Create a new role")
    @has_permissions(manage_roles=True)
    async def role_create(self, ctx: Context, *, name: str):
        """Create a new role"""
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        role = await ctx.guild.create_role(name=name)
        return await ctx.approve(f"Created role {role.mention}")
    
    @role.command(name="delete", help="Delete a role")
    @has_permissions(manage_roles=True)
    async def role_delete(self, ctx: Context, role: discord.Role):
        """Delete a role"""
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner.id:
            return await ctx.deny("You **can't** delete a role higher than yours.")
        
        role_name = role.name
        await role.delete()
        return await ctx.approve(f"Deleted role **{role_name}**")
    
    @role.command(name="add", help="Add a role to a member")
    @has_permissions(manage_roles=True)
    async def role_add(self, ctx: Context, member: Member, role: discord.Role):
        """Add a role to a member"""
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner.id:
            return await ctx.deny("You **can't** add a role higher than yours.")
        
        if role in member.roles:
            return await ctx.deny(f"{member.mention} already has {role.mention}")
        
        await member.add_roles(role)
        return await ctx.approve(f"Added {role.mention} to {member.mention}")
    
    @role.command(name="remove", help="Remove a role from a member")
    @has_permissions(manage_roles=True)
    async def role_remove(self, ctx: Context, member: Member, role: discord.Role):
        """Remove a role from a member"""
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner.id:
            return await ctx.deny("You **can't** remove a role higher than yours.")
        
        if role not in member.roles:
            return await ctx.deny(f"{member.mention} doesn't have {role.mention}")
        
        await member.remove_roles(role)
        return await ctx.approve(f"Removed {role.mention} from {member.mention}")
    
    @role.command(name="all", help="Give a role to all members")
    @has_permissions(manage_roles=True)
    async def role_all(self, ctx: Context, role: discord.Role):
        """Give a role to all members in the server"""
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner.id:
            return await ctx.deny("You **can't** assign a role higher than yours.")
        
        loading_msg = await ctx.loading(f"Adding {role.mention} to all members...")
        
        success_count = 0
        fail_count = 0
        
        for member in ctx.guild.members:
            if member.bot:
                continue
            if role in member.roles:
                continue
            
            try:
                await member.add_roles(role, reason=f"Role all by {ctx.author}")
                success_count += 1
            except:
                fail_count += 1
        
        await loading_msg.delete()
        
        if fail_count > 0:
            return await ctx.approve(f"Added {role.mention} to **{success_count}** members ({fail_count} failed)")
        else:
            return await ctx.approve(f"Added {role.mention} to **{success_count}** members")
    
    # Event listeners for logging
    @Cog.listener()
    async def on_member_join(self, member: Member):
        """Ping user on join if enabled"""
        if not self.bot.db_pool:
            return
        
        # Check for ping on join
        ping_config = await self.bot.db_pool.fetchrow(
            "SELECT channel_id FROM ping_on_join WHERE guild_id = $1",
            member.guild.id
        )
        
        if ping_config:
            channel = member.guild.get_channel(ping_config['channel_id'])
            if channel:
                try:
                    msg = await channel.send(member.mention)
                    await msg.delete()
                except:
                    pass
    
    @Cog.listener()
    async def on_member_update(self, before: Member, after: Member):
        """Check for forced nickname changes"""
        if before.nick == after.nick:
            return
        
        # Check if user has forced nickname
        record = await self.bot.db_pool.fetchrow(
            "SELECT nickname FROM force_nicknames WHERE guild_id = $1 AND user_id = $2",
            after.guild.id, after.id
        )
        
        if record and after.nick != record['nickname']:
            # Reapply forced nickname
            try:
                await after.edit(nick=record['nickname'])
            except:
                pass
    
    @command(name="nuke", help="Clone and delete a channel to clear all messages")
    @has_permissions(manage_channels=True)
    async def nuke(self, ctx: Context):
        """Nuke a channel (clone and delete it)"""
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if not isinstance(ctx.channel, TextChannel):
            return await ctx.deny("This command can **only** be used in a text channel.")
        
        # Create confirmation view
        class NukeView(View):
            def __init__(self):
                super().__init__(timeout=30)
                self.confirmed = False
            
            @discord.ui.button(emoji=Config.EMOJIS.SUCCESS, style=discord.ButtonStyle.secondary)
            async def confirm(self, interaction: discord.Interaction, button: Button):
                if interaction.user != ctx.author:
                    return await interaction.response.send_message("Only the command author can confirm this action.", ephemeral=True)
                
                self.confirmed = True
                self.stop()
                
                # Clone the channel
                new_channel = await ctx.channel.clone(reason=f"Nuked by {ctx.author}")
                await new_channel.edit(position=ctx.channel.position)
                
                # Delete the old channel
                await ctx.channel.delete()
                
                # Send confirmation in new channel as normal message
                await new_channel.send(f"first in chat")
            
            @discord.ui.button(emoji=Config.EMOJIS.ERROR, style=discord.ButtonStyle.secondary)
            async def cancel(self, interaction: discord.Interaction, button: Button):
                if interaction.user != ctx.author:
                    return await interaction.response.send_message("Only the command author can cancel this action.", ephemeral=True)
                
                self.stop()
                await interaction.response.edit_message(content="aw man i wanted to go kaboom...", embed=None, view=None)
        
        # Send confirmation
        view = NukeView()
        await ctx.warn("Are you **sure** you want to nuke this **channel**?", view=view)
    
    @commands.group(name="pingonjoin", aliases=["poj"], invoke_without_command=True, help="Ping on join settings")
    @has_permissions(manage_guild=True)
    async def pingonjoin(self, ctx: Context):
        """Ping on join settings"""
        await ctx.send_help(ctx.command)
    
    @pingonjoin.command(name="set", help="Set the channel to ping users when they join")
    @has_permissions(manage_guild=True)
    async def pingonjoin_set(self, ctx: Context, channel: Optional[TextChannel] = None):
        """Set the channel to ping users when they join"""
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        if channel is None:
            channel = ctx.channel
        
        await self.bot.db_pool.execute(
            "INSERT INTO ping_on_join (guild_id, channel_id) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2",
            ctx.guild.id, channel.id
        )
        
        return await ctx.approve(f"Set ping on join channel to {channel.mention}")
    
    @pingonjoin.command(name="remove", aliases=["disable", "off"], help="Disable ping on join")
    @has_permissions(manage_guild=True)
    async def pingonjoin_remove(self, ctx: Context):
        """Disable ping on join"""
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        result = await self.bot.db_pool.execute(
            "DELETE FROM ping_on_join WHERE guild_id = $1",
            ctx.guild.id
        )
        
        if result == "DELETE 0":
            return await ctx.deny("Ping on join is **not** enabled.")
        
        return await ctx.approve("Disabled ping on join")
    
    @pingonjoin.command(name="view", aliases=["check"], help="View current ping on join settings")
    @has_permissions(manage_guild=True)
    async def pingonjoin_view(self, ctx: Context):
        """View current ping on join settings"""
        if not ctx.guild:
            return await ctx.deny("This command can **only** be used in a server.")
        
        config = await self.bot.db_pool.fetchrow(
            "SELECT channel_id FROM ping_on_join WHERE guild_id = $1",
            ctx.guild.id
        )
        
        if not config:
            return await ctx.deny("Ping on join is **not** enabled.")
        
        channel = ctx.guild.get_channel(config['channel_id'])
        if channel:
            return await ctx.approve(f"Ping on join is enabled in {channel.mention}")
        else:
            return await ctx.deny("Ping on join channel no longer exists.")


async def setup(bot):
    await bot.add_cog(Moderation(bot))

