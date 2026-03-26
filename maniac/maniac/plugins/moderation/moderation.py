import discord
from discord.ext import commands, tasks
from maniac.core.config import Config
from maniac.core.command_example import example
from datetime import timedelta, datetime, timezone
from typing import Optional
import io
import re
import aiohttp
from PIL import Image
import numpy as np
import colorsys

DEFAULT_REASON = "No reason provided"

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.setup_role_tracking.start()
    
    def cog_unload(self):
        self.setup_role_tracking.cancel()
    
    async def log_moderation_action(self, guild: discord.Guild, action: str, user: discord.Member | discord.User, moderator: discord.Member, reason: str, channel: discord.TextChannel = None):
        from maniac.core.database import db
        
        case_count = await db.cases.count_documents({"guild_id": guild.id})
        case_id = case_count + 1
        
        await db.cases.insert_one({
            "guild_id": guild.id,
            "case_id": case_id,
            "action": action,
            "user_id": user.id,
            "moderator_id": moderator.id,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc),
            "channel_id": channel.id if channel else None
        })
        
        modlog_config = await db.modlog_config.find_one({"guild_id": guild.id})
        
        if modlog_config and modlog_config.get("channel_id"):
            modlog_channel = guild.get_channel(modlog_config["channel_id"])
            
            if modlog_channel:
                embed = discord.Embed(
                    title=f"Case #{case_id} | {action}",
                    color=Config.COLORS.DEFAULT,
                    timestamp=datetime.now(timezone.utc)
                )
                
                embed.add_field(
                    name="User:",
                    value=f"{user} ( {user.id} )",
                    inline=False
                )
                embed.add_field(
                    name="Moderator:",
                    value=f"{moderator} ( {moderator.id} )",
                    inline=False
                )
                embed.add_field(
                    name="Reason:",
                    value=reason,
                    inline=False
                )
                
                if channel:
                    embed.add_field(
                        name="Channel:",
                        value=f"# {channel.name} ( {channel.id} )",
                        inline=False
                    )
                
                if isinstance(user, discord.Member):
                    joined_at = user.joined_at
                    if joined_at:
                        days_ago = (datetime.now(timezone.utc) - joined_at).days
                        embed.add_field(
                            name="Joined:",
                            value=f"{discord.utils.format_dt(joined_at, 'D')} ( {days_ago} days ago )",
                            inline=False
                        )
                
                created_at = user.created_at
                if created_at:
                    time_ago_str = discord.utils.format_dt(created_at, 'R')
                    embed.add_field(
                        name="Created:",
                        value=f"{discord.utils.format_dt(created_at, 'D')} ( {time_ago_str} )",
                        inline=False
                    )
                
                try:
                    await modlog_channel.send(embed=embed)
                except:
                    pass
        
        return case_id
    
    @commands.Cog.listener("on_member_update")
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles != after.roles:
            from maniac.core.database import db
            
            role_ids = [role.id for role in after.roles if role.id != after.guild.default_role.id]
            
            await db.member_roles.update_one(
                {"guild_id": after.guild.id, "user_id": after.id},
                {
                    "$set": {
                        "role_ids": role_ids,
                        "updated_at": datetime.now(timezone.utc)
                    }
                },
                upsert=True
            )
    
    @commands.Cog.listener("on_member_remove")
    async def on_member_remove(self, member: discord.Member):
        from maniac.core.database import db
        from datetime import datetime, timezone
        
        role_ids = [role.id for role in member.roles if role.id != member.guild.default_role.id]
        
        if role_ids:
            await db.member_roles.update_one(
                {"guild_id": member.guild.id, "user_id": member.id},
                {
                    "$set": {
                        "role_ids": role_ids,
                        "updated_at": datetime.now(timezone.utc),
                        "left_at": datetime.now(timezone.utc)
                    }
                },
                upsert=True
            )
    
    @commands.Cog.listener("on_raw_reaction_add")
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member.bot:
            return
        
        from maniac.core.database import db
        
        reaction_role = await db.reaction_roles.find_one({
            "guild_id": payload.guild_id,
            "message_id": payload.message_id,
            "emoji": str(payload.emoji)
        })
        
        if not reaction_role:
            return
        
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        
        role = guild.get_role(reaction_role["role_id"])
        if not role:
            return
        
        try:
            await payload.member.add_roles(role, reason="Reaction role")
        except:
            pass
    
    @commands.Cog.listener("on_raw_reaction_remove")
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        from maniac.core.database import db
        
        reaction_role = await db.reaction_roles.find_one({
            "guild_id": payload.guild_id,
            "message_id": payload.message_id,
            "emoji": str(payload.emoji)
        })
        
        if not reaction_role:
            return
        
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return
        
        role = guild.get_role(reaction_role["role_id"])
        if not role:
            return
        
        try:
            await member.remove_roles(role, reason="Reaction role removed")
        except:
            pass
    
    @tasks.loop(hours=1)
    async def setup_role_tracking(self):
        pass
    
    @setup_role_tracking.before_loop
    async def before_setup_role_tracking(self):
        await self.bot.wait_until_ready()
    
    @commands.command(aliases=["deport"], help="Ban a member from the server")
    @example(",ban @offermillions spamming")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, user: discord.Member | discord.User, *, reason: str = DEFAULT_REASON):
        if isinstance(user, discord.Member):
            if user.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
                return await ctx.deny("You cannot ban this member due to role hierarchy")
            if user.top_role >= ctx.guild.me.top_role:
                return await ctx.deny("I cannot ban this member due to role hierarchy")
            if user == ctx.guild.owner:
                return await ctx.deny("You cannot ban the server owner")
        
        await ctx.guild.ban(user, reason=f"{reason} | {ctx.author} ({ctx.author.id})")
        case_id = await self.log_moderation_action(ctx.guild, "Ban", user, ctx.author, reason, ctx.channel)
        await ctx.approve(f"Successfully banned {user.mention} for {reason} (Case #{case_id})")
    
    @commands.command(help="Unban a user from the server")
    @example(",unban 123456789012345678 appealed")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user: discord.User, *, reason: str = DEFAULT_REASON):
        try:
            await ctx.guild.unban(user, reason=f"{reason} | {ctx.author} ({ctx.author.id})")
            case_id = await self.log_moderation_action(ctx.guild, "Unban", user, ctx.author, reason)
            await ctx.approve(f"Successfully unbanned {user.mention} (Case #{case_id})")
        except discord.NotFound:
            await ctx.deny(f"{user.mention} is not banned from this server")
    
    @commands.command(help="Kick a member from the server")
    @example(",kick @offermillions inappropriate behavior")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = DEFAULT_REASON):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot kick this member due to role hierarchy")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot kick this member due to role hierarchy")
        if member == ctx.guild.owner:
            return await ctx.deny("You cannot kick the server owner")
        
        await member.kick(reason=f"{reason} | {ctx.author} ({ctx.author.id})")
        case_id = await self.log_moderation_action(ctx.guild, "Kick", member, ctx.author, reason, ctx.channel)
        await ctx.approve(f"Successfully kicked {member.mention} for {reason} (Case #{case_id})")
    
    @commands.command(help="Ban and immediately unban a member to delete their messages")
    @example(",softban @offermillions spam messages")
    @commands.has_permissions(ban_members=True)
    async def softban(self, ctx, member: discord.Member, *, reason: str = DEFAULT_REASON):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot softban this member due to role hierarchy")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot softban this member due to role hierarchy")
        
        await ctx.guild.ban(member, delete_message_days=7, reason=f"{reason} | {ctx.author} ({ctx.author.id})")
        await ctx.guild.unban(member, reason=f"{reason} | {ctx.author} ({ctx.author.id})")
        
        case_id = await self.log_moderation_action(ctx.guild, "Softban", member, ctx.author, reason)
        await ctx.approve(f"Successfully softbanned {member.mention} for {reason} (Case #{case_id})")
    
    @commands.command(aliases=["tmo", "to"], help="Timeout a member for a specified duration")
    @example(",timeout @offermillions 10m spamming")
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, duration: str, *, reason: str = DEFAULT_REASON):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot timeout this member due to role hierarchy")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot timeout this member due to role hierarchy")
        
        time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        unit = duration[-1]
        if unit not in time_units:
            return await ctx.deny("Invalid time unit. Use s, m, h, or d")
        
        try:
            amount = int(duration[:-1])
        except ValueError:
            return await ctx.deny("Invalid duration format")
        
        seconds = amount * time_units[unit]
        if seconds < 60:
            return await ctx.deny("Timeout duration must be at least 1 minute")
        if seconds > 2419200:
            return await ctx.deny("Timeout duration cannot exceed 28 days")
        
        await member.timeout(timedelta(seconds=seconds), reason=f"{reason} | {ctx.author} ({ctx.author.id})")
        case_id = await self.log_moderation_action(ctx.guild, "Timeout", member, ctx.author, reason, ctx.channel)
        await ctx.approve(f"Successfully timed out {member.mention} for {duration} - {reason} (Case #{case_id})")
    
    @commands.command(aliases=["removetimeout"], help="Remove a member's timeout")
    @example(",untimeout @offermillions")
    @commands.has_permissions(moderate_members=True)
    async def untimeout(self, ctx, member: discord.Member, *, reason: str = DEFAULT_REASON):
        if not member.is_timed_out():
            return await ctx.deny(f"{member.mention} is not timed out")
        
        await member.timeout(None, reason=f"{reason} | {ctx.author} ({ctx.author.id})")
        
        case_id = await self.log_moderation_action(ctx.guild, "Untimeout", member, ctx.author, reason)
        await ctx.approve(f"Successfully removed timeout from {member.mention} (Case #{case_id})")
    
    @commands.group(aliases=["lock"], invoke_without_command=True, help="Lock a channel to prevent members from sending messages")
    @example(",lockdown #general raid protection")
    @commands.has_permissions(manage_channels=True)
    async def lockdown(self, ctx, channel: Optional[discord.TextChannel] = None, *, reason: str = DEFAULT_REASON):
        if ctx.invoked_subcommand is not None:
            return
        
        channel = channel or ctx.channel
        
        if not isinstance(channel, discord.TextChannel):
            return await ctx.deny("This command only works in text channels")
        
        overwrites = channel.overwrites_for(ctx.guild.default_role)
        
        if overwrites.send_messages is False:
            return await ctx.deny(f"{channel.mention} is already locked down")
        
        overwrites.send_messages = False
        await channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrites,
            reason=f"{reason} | {ctx.author} ({ctx.author.id})"
        )
        
        case_id = await self.log_moderation_action(ctx.guild, "Lockdown", ctx.guild.default_role, ctx.author, reason, channel)
        await ctx.approve(f"Successfully locked down {channel.mention} (Case #{case_id})")
    
    @commands.group(aliases=["unlock"], invoke_without_command=True, help="Unlock a locked channel")
    @example(",unlockdown #general")
    @commands.has_permissions(manage_channels=True)
    async def unlockdown(self, ctx, channel: Optional[discord.TextChannel] = None, *, reason: str = DEFAULT_REASON):
        if ctx.invoked_subcommand is not None:
            return
        
        channel = channel or ctx.channel
        
        if not isinstance(channel, discord.TextChannel):
            return await ctx.deny("This command only works in text channels")
        
        overwrites = channel.overwrites_for(ctx.guild.default_role)
        
        if overwrites.send_messages is not False:
            return await ctx.deny(f"{channel.mention} is not locked down")
        
        overwrites.send_messages = None
        await channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrites,
            reason=f"{reason} | {ctx.author} ({ctx.author.id})"
        )
        
        case_id = await self.log_moderation_action(ctx.guild, "Unlockdown", ctx.guild.default_role, ctx.author, reason, channel)
        await ctx.approve(f"Successfully unlocked {channel.mention} (Case #{case_id})")
    
    @commands.group(aliases=["nick", "n"], invoke_without_command=True, help="Change a member's nickname")
    @example(",nickname @offermillions retarded fool")
    @commands.has_permissions(manage_nicknames=True)
    async def nickname(self, ctx, member: discord.Member = None, *, nickname: str = None):
        if ctx.invoked_subcommand is not None:
            return
        
        if not member or not nickname:
            return
        
        if len(nickname) > 32:
            return await ctx.deny("Nickname must be 32 characters or less")
        
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot change this member's nickname due to role hierarchy")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot change this member's nickname due to role hierarchy")
        
        await member.edit(nick=nickname, reason=f"Changed by {ctx.author} ({ctx.author.id})")
        case_id = await self.log_moderation_action(ctx.guild, "Nickname", member, ctx.author, f"set to {nickname}")
        await ctx.approve(f"Successfully changed {member.mention}'s nickname to **{nickname}** (Case #{case_id})")
    
    @nickname.command(name="remove", aliases=["reset", "clear"], help="Remove a member's nickname")
    @commands.has_permissions(manage_nicknames=True)
    async def nickname_remove(self, ctx, member: discord.Member):
        if not member.nick:
            return await ctx.deny(f"{member.mention} doesn't have a nickname")
        
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot change this member's nickname due to role hierarchy")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot change this member's nickname due to role hierarchy")
        
        await member.edit(nick=None, reason=f"Removed by {ctx.author} ({ctx.author.id})")
        case_id = await self.log_moderation_action(ctx.guild, "Nickname Remove", member, ctx.author, "removed nickname")
        await ctx.approve(f"Successfully removed {member.mention}'s nickname (Case #{case_id})")
    
    @commands.group(invoke_without_command=True, help="Purge messages from the channel")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int = None):
        if amount is None:
            return

        if amount < 1 or amount > 1000:
            return await ctx.deny("Amount must be between 1 and 1000")

        if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            return await ctx.deny("I don't have permission to manage messages in this channel")

        def check(message):
            from discord.utils import utcnow
            if message.created_at < (utcnow() - timedelta(weeks=2)):
                return False
            if message.pinned:
                return False
            return True

        try:
            await ctx.message.delete()
        except:
            pass

        messages = await ctx.channel.purge(limit=amount, check=check, before=ctx.message)

        if not messages:
            return await ctx.deny("No messages were found matching the criteria")

        case_id = await self.log_moderation_action(ctx.guild, "Purge", ctx.author, ctx.author, f"Purged {len(messages)} messages in {ctx.channel.mention}")
        await ctx.approve(f"Successfully purged {len(messages)} message(s) (Case #{case_id})", delete_after=5)


    
    @purge.command(name="user", help="Purge messages from a specific user")
    @commands.has_permissions(manage_messages=True)
    async def purge_user(self, ctx, user: discord.Member, amount: int = 100):
        if amount < 1 or amount > 1000:
            return await ctx.deny("Amount must be between 1 and 1000")
        
        if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            return await ctx.deny("I don't have permission to manage messages in this channel")
        
        def check(message):
            from discord.utils import utcnow
            if message.created_at < (utcnow() - timedelta(weeks=2)):
                return False
            if message.pinned:
                return False
            return message.author == user
        
        try:
            await ctx.message.delete()
        except:
            pass
        
        messages = await ctx.channel.purge(limit=amount, check=check, before=ctx.message)
        
        if not messages:
            return await ctx.deny("No messages were found matching the criteria")
        
        case_id = await self.log_moderation_action(ctx.guild, "Purge User", user, ctx.author, f"Purged {len(messages)} messages from {user.mention} in {ctx.channel.mention}")
        await ctx.approve(f"Successfully purged {len(messages)} message(s) (Case #{case_id})", delete_after=5)
    
    @purge.command(name="bots", help="Purge messages from bots")
    @commands.has_permissions(manage_messages=True)
    async def purge_bots(self, ctx, amount: int = 100):
        if amount < 1 or amount > 1000:
            return await ctx.deny("Amount must be between 1 and 1000")
        
        if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            return await ctx.deny("I don't have permission to manage messages in this channel")
        
        def check(message):
            from discord.utils import utcnow
            if message.created_at < (utcnow() - timedelta(weeks=2)):
                return False
            if message.pinned:
                return False
            return message.author.bot
        
        try:
            await ctx.message.delete()
        except:
            pass
        
        messages = await ctx.channel.purge(limit=amount, check=check, before=ctx.message)
        
        if not messages:
            return await ctx.deny("No messages were found matching the criteria")
        
        case_id = await self.log_moderation_action(ctx.guild, "Purge Bots", ctx.author, ctx.author, f"Purged {len(messages)} bot messages in {ctx.channel.mention}")
        await ctx.approve(f"Successfully purged {len(messages)} message(s) (Case #{case_id})", delete_after=5)
    
    @purge.command(name="humans", help="Purge messages from humans")
    @commands.has_permissions(manage_messages=True)
    async def purge_humans(self, ctx, amount: int = 100):
        if amount < 1 or amount > 1000:
            return await ctx.deny("Amount must be between 1 and 1000")
        
        if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            return await ctx.deny("I don't have permission to manage messages in this channel")
        
        def check(message):
            from discord.utils import utcnow
            if message.created_at < (utcnow() - timedelta(weeks=2)):
                return False
            if message.pinned:
                return False
            return not message.author.bot
        
        try:
            await ctx.message.delete()
        except:
            pass
        
        messages = await ctx.channel.purge(limit=amount, check=check, before=ctx.message)
        
        if not messages:
            return await ctx.deny("No messages were found matching the criteria")
        
        case_id = await self.log_moderation_action(ctx.guild, "Purge Humans", ctx.author, ctx.author, f"Purged {len(messages)} human messages in {ctx.channel.mention}")
        await ctx.approve(f"Successfully purged {len(messages)} message(s) (Case #{case_id})", delete_after=5)
    
    @purge.command(name="embeds", help="Purge messages containing embeds")
    @commands.has_permissions(manage_messages=True)
    async def purge_embeds(self, ctx, amount: int = 100):
        if amount < 1 or amount > 1000:
            return await ctx.deny("Amount must be between 1 and 1000")
        
        if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            return await ctx.deny("I don't have permission to manage messages in this channel")
        
        def check(message):
            from discord.utils import utcnow
            if message.created_at < (utcnow() - timedelta(weeks=2)):
                return False
            if message.pinned:
                return False
            return len(message.embeds) > 0
        
        try:
            await ctx.message.delete()
        except:
            pass
        
        messages = await ctx.channel.purge(limit=amount, check=check, before=ctx.message)
        
        if not messages:
            return await ctx.deny("No messages were found matching the criteria")
        
        case_id = await self.log_moderation_action(ctx.guild, "Purge Embeds", ctx.author, ctx.author, f"Purged {len(messages)} messages with embeds in {ctx.channel.mention}")
        await ctx.approve(f"Successfully purged {len(messages)} message(s) (Case #{case_id})", delete_after=5)
    
    @purge.command(name="files", help="Purge messages containing files")
    @commands.has_permissions(manage_messages=True)
    async def purge_files(self, ctx, amount: int = 100):
        if amount < 1 or amount > 1000:
            return await ctx.deny("Amount must be between 1 and 1000")
        
        if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            return await ctx.deny("I don't have permission to manage messages in this channel")
        
        def check(message):
            from discord.utils import utcnow
            if message.created_at < (utcnow() - timedelta(weeks=2)):
                return False
            if message.pinned:
                return False
            return len(message.attachments) > 0
        
        try:
            await ctx.message.delete()
        except:
            pass
        
        messages = await ctx.channel.purge(limit=amount, check=check, before=ctx.message)
        
        if not messages:
            return await ctx.deny("No messages were found matching the criteria")
        
        case_id = await self.log_moderation_action(ctx.guild, "Purge Files", ctx.author, ctx.author, f"Purged {len(messages)} messages with files in {ctx.channel.mention}")
        await ctx.approve(f"Successfully purged {len(messages)} message(s) (Case #{case_id})", delete_after=5)
    
    @purge.command(name="contains", help="Purge messages containing a specific substring")
    @commands.has_permissions(manage_messages=True)
    async def purge_contains(self, ctx, substring: str, amount: int = 100):
        if amount < 1 or amount > 1000:
            return await ctx.deny("Amount must be between 1 and 1000")
        
        if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            return await ctx.deny("I don't have permission to manage messages in this channel")
        
        def check(message):
            from discord.utils import utcnow
            if message.created_at < (utcnow() - timedelta(weeks=2)):
                return False
            if message.pinned:
                return False
            return substring.lower() in message.content.lower()
        
        try:
            await ctx.message.delete()
        except:
            pass
        
        messages = await ctx.channel.purge(limit=amount, check=check, before=ctx.message)
        
        if not messages:
            return await ctx.deny("No messages were found matching the criteria")
        
        case_id = await self.log_moderation_action(ctx.guild, "Purge Contains", ctx.author, ctx.author, f"Purged {len(messages)} messages containing '{substring}' in {ctx.channel.mention}")
        await ctx.approve(f"Successfully purged {len(messages)} message(s) (Case #{case_id})", delete_after=5)
    
    @purge.command(name="startswith", help="Purge messages starting with a specific substring")
    @commands.has_permissions(manage_messages=True)
    async def purge_startswith(self, ctx, substring: str, amount: int = 100):
        if amount < 1 or amount > 1000:
            return await ctx.deny("Amount must be between 1 and 1000")
        
        if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            return await ctx.deny("I don't have permission to manage messages in this channel")
        
        def check(message):
            from discord.utils import utcnow
            if message.created_at < (utcnow() - timedelta(weeks=2)):
                return False
            if message.pinned:
                return False
            return message.content.lower().startswith(substring.lower())
        
        try:
            await ctx.message.delete()
        except:
            pass
        
        messages = await ctx.channel.purge(limit=amount, check=check, before=ctx.message)
        
        if not messages:
            return await ctx.deny("No messages were found matching the criteria")
        
        case_id = await self.log_moderation_action(ctx.guild, "Purge Startswith", ctx.author, ctx.author, f"Purged {len(messages)} messages starting with '{substring}' in {ctx.channel.mention}")
        await ctx.approve(f"Successfully purged {len(messages)} message(s) (Case #{case_id})", delete_after=5)
    
    @purge.command(name="endswith", help="Purge messages ending with a specific substring")
    @commands.has_permissions(manage_messages=True)
    async def purge_endswith(self, ctx, substring: str, amount: int = 100):
        if amount < 1 or amount > 1000:
            return await ctx.deny("Amount must be between 1 and 1000")
        
        if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            return await ctx.deny("I don't have permission to manage messages in this channel")
        
        def check(message):
            from discord.utils import utcnow
            if message.created_at < (utcnow() - timedelta(weeks=2)):
                return False
            if message.pinned:
                return False
            return message.content.lower().endswith(substring.lower())
        
        try:
            await ctx.message.delete()
        except:
            pass
        
        messages = await ctx.channel.purge(limit=amount, check=check, before=ctx.message)
        
        if not messages:
            return await ctx.deny("No messages were found matching the criteria")
        
        case_id = await self.log_moderation_action(ctx.guild, "Purge Endswith", ctx.author, ctx.author, f"Purged {len(messages)} messages ending with '{substring}' in {ctx.channel.mention}")
        await ctx.approve(f"Successfully purged {len(messages)} message(s) (Case #{case_id})", delete_after=5)
    
    @commands.group(aliases=["emote"], invoke_without_command=True, help="Manage server emojis")
    @example(",emoji list")
    async def emoji(self, ctx):
        pass
    
    @emoji.command(name="add", aliases=["create", "upload", "steal"], help="Add an emoji to the server")
    @commands.has_permissions(manage_emojis=True)
    async def emoji_add(self, ctx, emoji: Optional[discord.PartialEmoji] = None, *, name: Optional[str] = None):
        if not emoji and not ctx.message.attachments:
            return await ctx.deny("Please provide an emoji or attach an image")
        
        if len(ctx.guild.emojis) >= ctx.guild.emoji_limit:
            return await ctx.deny("This server has reached the maximum amount of emojis")
        
        if emoji:
            if emoji.is_unicode_emoji():
                return await ctx.deny("You cannot add unicode emojis")
            
            buffer = await emoji.read()
            emoji_name = name or emoji.name
        elif ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if not attachment.content_type or not attachment.content_type.startswith("image/"):
                return await ctx.deny("The attachment must be an image")
            
            buffer = await attachment.read()
            emoji_name = name or attachment.filename.split(".")[0].replace(" ", "_")[:32]
        else:
            return await ctx.deny("Please provide an emoji or attach an image")
        
        try:
            from discord.utils import utcnow, format_dt
            from discord import RateLimited, HTTPException
            new_emoji = await ctx.guild.create_custom_emoji(
                name=emoji_name,
                image=buffer,
                reason=f"Uploaded by {ctx.author} ({ctx.author.id})"
            )
            await ctx.approve(f"Successfully uploaded emoji {new_emoji} with name `{new_emoji.name}`")
        except RateLimited as exc:
            expires_at = utcnow() + timedelta(seconds=exc.retry_after)
            await ctx.deny(f"The server has been rate limited by Discord, try again {format_dt(expires_at, 'R')}")
        except HTTPException as exc:
            await ctx.deny(f"An error occurred while uploading the emoji: {exc.text}")
    
    @emoji.command(name="delete", aliases=["remove", "del", "rm"], help="Delete an emoji from the server")
    @commands.has_permissions(manage_emojis=True)
    async def emoji_delete(self, ctx, emoji: discord.Emoji):
        if emoji.guild_id != ctx.guild.id:
            return await ctx.deny("That emoji isn't from this server")
        
        emoji_name = emoji.name
        await emoji.delete(reason=f"Deleted by {ctx.author} ({ctx.author.id})")
        await ctx.approve(f"Successfully deleted emoji `{emoji_name}`")
    
    @emoji.command(name="rename", aliases=["edit"], help="Rename an emoji")
    @commands.has_permissions(manage_emojis=True)
    async def emoji_rename(self, ctx, emoji: discord.Emoji, *, name: str):
        if emoji.guild_id != ctx.guild.id:
            return await ctx.deny("That emoji isn't from this server")
        
        if len(name) < 2 or len(name) > 32:
            return await ctx.deny("Emoji name must be between 2 and 32 characters")
        
        name = name.replace(" ", "_")
        old_name = emoji.name
        await emoji.edit(name=name, reason=f"Renamed by {ctx.author} ({ctx.author.id})")
        await ctx.approve(f"Successfully renamed emoji from `{old_name}` to `{name}`")
    
    @emoji.command(name="list", help="List all server emojis")
    async def emoji_list(self, ctx):
        if not ctx.guild.emojis:
            return await ctx.deny("This server has no custom emojis")
        
        embed = discord.Embed(
            title=f"Server Emojis ({len(ctx.guild.emojis)}/{ctx.guild.emoji_limit})",
            color=Config.COLORS.DEFAULT
        )
        
        emoji_list = []
        for emoji in ctx.guild.emojis[:25]:
            emoji_list.append(f"{emoji} `:{emoji.name}:` (`{emoji.id}`)")
        
        embed.description = "\n".join(emoji_list)
        
        if len(ctx.guild.emojis) > 25:
            embed.set_footer(text=f"Showing 25 of {len(ctx.guild.emojis)} emojis")
        
        await ctx.reply(embed=embed)
    
    @emoji.command(name="enlarge", aliases=["jumbo", "big"], help="Enlarge an emoji")
    async def emoji_enlarge(self, ctx, emoji: discord.PartialEmoji):
        if emoji.is_unicode_emoji():
            return await ctx.deny("Cannot enlarge unicode emojis")
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_image(url=emoji.url)
        embed.set_footer(text=f":{emoji.name}:")
        await ctx.reply(embed=embed)
    
    @emoji.command(name="recolor", help="Recolor an emoji to a given hex color")
    @commands.has_permissions(manage_emojis=True)
    async def emoji_recolor(self, ctx, emoji: str, hex_color: str = None):
        if not hex_color:
            return await ctx.warn("Please provide a valid hex color")
        
        hex_clean = hex_color.lstrip('#')
        if not re.fullmatch(r'[0-9a-fA-F]{6}', hex_clean):
            return await ctx.warn("Please provide a valid hex color")
        
        r = int(hex_clean[0:2], 16)
        g = int(hex_clean[2:4], 16)
        b = int(hex_clean[4:6], 16)
        
        custom_match = re.match(r'<a?:(\w+):(\d+)>', emoji)
        if not custom_match:
            return await ctx.warn("Please provide a custom emoji from this or another server")
        
        emoji_name = custom_match.group(1)
        emoji_id = int(custom_match.group(2))
        animated = emoji.startswith('<a:')
        ext = 'gif' if animated else 'png'
        url = f'https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=128'
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return await ctx.warn("Could not download the emoji image")
                img_bytes = await resp.read()
        
        img = Image.open(io.BytesIO(img_bytes)).convert('RGBA')
        _, _, _, a_ch = img.split()
        
        target_h, target_s, _ = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        
        rgb_arr = np.array(img.convert('RGB'), dtype=np.float32) / 255.0
        
        Cmax = rgb_arr.max(axis=2)
        Cmin = rgb_arr.min(axis=2)
        delta = Cmax - Cmin
        
        V = Cmax
        H = np.full(V.shape, target_h, dtype=np.float32)
        S = np.full(V.shape, target_s, dtype=np.float32)
        
        i_arr = (H * 6.0).astype(int)
        f = H * 6.0 - i_arr
        p = V * (1.0 - S)
        q = V * (1.0 - f * S)
        t = V * (1.0 - (1.0 - f) * S)
        i_mod = i_arr % 6
        
        result = np.zeros_like(rgb_arr)
        for idx, (r1, g1, b1) in enumerate([(V, t, p), (q, V, p), (p, V, t), (p, q, V), (t, p, V), (V, p, q)]):
            mask = i_mod == idx
            result[:, :, 0] = np.where(mask, r1, result[:, :, 0])
            result[:, :, 1] = np.where(mask, g1, result[:, :, 1])
            result[:, :, 2] = np.where(mask, b1, result[:, :, 2])
        
        blended_img = Image.fromarray((result * 255).astype(np.uint8), 'RGB').convert('RGBA')
        blended_img.putalpha(a_ch)
        
        output = io.BytesIO()
        blended_img.save(output, format='PNG')
        output.seek(0)
        image_bytes = output.read()
        
        class AddToServerView(discord.ui.View):
            def __init__(self, img_bytes, name):
                super().__init__(timeout=60)
                self.img_bytes = img_bytes
                self.name = name
            
            @discord.ui.button(label="Add to Server", style=discord.ButtonStyle.green)
            async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("This isn't your button!", ephemeral=True)
                
                try:
                    new_emoji = await ctx.guild.create_custom_emoji(
                        name=self.name,
                        image=self.img_bytes,
                        reason=f"Recolored by {ctx.author} ({ctx.author.id})"
                    )
                    await interaction.response.send_message(f"Successfully added {new_emoji} to the server!", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"Failed to add emoji: {str(e)}", ephemeral=True)
        
        file = discord.File(io.BytesIO(image_bytes), filename=f'{emoji_name}.png')
        await ctx.send(file=file, view=AddToServerView(image_bytes, emoji_name))
    
    @emoji.command(name="stats", help="Show top ten most used emotes")
    async def emoji_stats(self, ctx):
        from maniac.core.database import db
        
        emoji_usage = await db.emoji_usage.find({
            "guild_id": ctx.guild.id
        }).sort("count", -1).limit(10).to_list(length=10)
        
        if not emoji_usage:
            return await ctx.deny("No emoji usage data available")
        
        class EmojiStatsPaginator(discord.ui.View):
            def __init__(self, ctx_inner, usage_list, per_page=10):
                super().__init__(timeout=60)
                self.ctx = ctx_inner
                self.usage = usage_list
                self.per_page = per_page
                self.current_page = 0
                self.max_pages = (len(usage_list) - 1) // per_page + 1
            
            def get_page_embed(self):
                start = self.current_page * self.per_page
                end = start + self.per_page
                page_usage = self.usage[start:end]
                
                embed = discord.Embed(
                    title="Top Emoji Usage",
                    color=Config.COLORS.DEFAULT
                )
                
                description = []
                for i, usage in enumerate(page_usage, start + 1):
                    emoji_id = usage.get("emoji_id")
                    count = usage.get("count", 0)
                    
                    emoji = self.ctx.bot.get_emoji(emoji_id)
                    if emoji:
                        description.append(f"`{i}.` {emoji} - `{count:,}` uses")
                    else:
                        description.append(f"`{i}.` Unknown Emoji - `{count:,}` uses")
                
                embed.description = "\n".join(description) if description else "No data"
                embed.set_footer(text=f"Page {self.current_page + 1}/{self.max_pages}")
                return embed
            
            @discord.ui.button(emoji=Config.EMOJIS.BACKWARD, style=discord.ButtonStyle.gray)
            async def backward_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
                
                if self.current_page > 0:
                    self.current_page -= 1
                    await interaction.response.edit_message(embed=self.get_page_embed(), view=self)
                else:
                    await interaction.response.defer()
            
            @discord.ui.button(emoji=Config.EMOJIS.FORWARD, style=discord.ButtonStyle.gray)
            async def forward_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
                
                if self.current_page < self.max_pages - 1:
                    self.current_page += 1
                    await interaction.response.edit_message(embed=self.get_page_embed(), view=self)
                else:
                    await interaction.response.defer()
            
            @discord.ui.button(emoji=Config.EMOJIS.CLOSE, style=discord.ButtonStyle.red)
            async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
                
                await interaction.message.delete()
                self.stop()
        
        view = EmojiStatsPaginator(ctx, emoji_usage)
        await ctx.send(embed=view.get_page_embed(), view=view)
    
    @commands.group(invoke_without_command=True, help="Clone and delete a channel")
    @example(",nuke")
    @commands.has_permissions(administrator=True)
    async def nuke(self, ctx):
        if ctx.invoked_subcommand is not None:
            return
        
        channel = ctx.channel
        
        if not isinstance(channel, discord.TextChannel):
            return await ctx.deny("This command can only be used in text channels")
        
        class NukeConfirmView(discord.ui.View):
            def __init__(self, ctx_inner):
                super().__init__(timeout=30)
                self.ctx = ctx_inner
                self.value = None
            
            @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
            async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your confirmation!", ephemeral=True)
                self.value = True
                self.stop()
                await interaction.response.defer()
            
            @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
            async def deny_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your confirmation!", ephemeral=True)
                self.value = False
                self.stop()
                await interaction.response.defer()
        
        view = NukeConfirmView(ctx)
        confirm_msg = await ctx.send(
            embed=discord.Embed(
                description=f"{ctx.author.mention}: Are you sure you want to nuke this channel? This action is irreversible and will delete the channel.",
                color=Config.COLORS.WARNING
            ),
            view=view
        )
        
        await view.wait()
        
        if view.value is None:
            await confirm_msg.delete()
            return await ctx.deny("Channel nuke timed out")
        
        if not view.value:
            await confirm_msg.delete()
            return await ctx.deny("Channel nuke cancelled")
        
        position = channel.position
        new_channel = await channel.clone(reason=f"Nuked by {ctx.author} ({ctx.author.id})")
        
        config_map = {
            "system_channel": ctx.guild.system_channel,
            "public_updates_channel": ctx.guild.public_updates_channel,
            "rules_channel": ctx.guild.rules_channel,
        }
        
        reconfigured = []
        for attr, ch in config_map.items():
            if ch == channel:
                config_map[attr] = new_channel
                reconfigured.append(attr.replace("_", " ").title())
        
        try:
            await ctx.guild.edit(**config_map)
        except:
            pass
        
        import asyncio
        await asyncio.gather(
            new_channel.edit(position=position),
            channel.delete(reason=f"Nuked by {ctx.author} ({ctx.author.id})")
        )
        
        embed = discord.Embed(
            title="Channel Nuked",
            description=f"This channel has been nuked by {ctx.author.mention}",
            color=Config.COLORS.DEFAULT
        )
        
        if reconfigured:
            embed.add_field(
                name="Settings Synced",
                value=">>> " + "\n".join(reconfigured)
            )
        
        await new_channel.send(embed=embed)
    
    @commands.command(help="Warn a member")
    @example(",warn @offermillions inappropriate language")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str = DEFAULT_REASON):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot warn this member due to role hierarchy")
        if member == ctx.guild.owner:
            return await ctx.deny("You cannot warn the server owner")
        if member.bot:
            return await ctx.deny("You cannot warn bots")
        
        from maniac.plugins.moderation.history import Case
        await Case.create(ctx, member, "warn", reason)
        
        try:
            embed = discord.Embed(
                title=f"You have been warned in {ctx.guild.name}",
                description=f"**Reason:** {reason}\n**Moderator:** {ctx.author}",
                color=Config.COLORS.WARNING
            )
            await member.send(embed=embed)
        except:
            pass
        
        await ctx.approve(f"Successfully warned {member.mention} for {reason}")
    
    @commands.command(help="Drag member(s) to a voice channel")
    @example(",drag @offermillions Voice Channel")
    @commands.has_permissions(move_members=True)
    async def drag(self, ctx, members: commands.Greedy[discord.Member], *, channel: discord.VoiceChannel):
        if not members:
            return await ctx.deny("You need to specify at least one member to drag")
        
        moved = 0
        for member in members:
            if member.voice and member.voice.channel:
                try:
                    await member.move_to(channel, reason=f"Dragged by {ctx.author} ({ctx.author.id})")
                    moved += 1
                except:
                    pass
        
        if moved == 0:
            return await ctx.deny("No members were moved. Make sure they are in a voice channel")
        
        await ctx.approve(f"Successfully dragged {moved} member(s) to {channel.mention}")
    
    @commands.command(help="Unban all banned users from the server")
    @example(",unbanall")
    @commands.has_permissions(administrator=True)
    async def unbanall(self, ctx):
        class UnbanAllView(discord.ui.View):
            def __init__(self, ctx_inner):
                super().__init__(timeout=30)
                self.ctx = ctx_inner
                self.value = None
            
            @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
            async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your confirmation!", ephemeral=True)
                self.value = True
                self.stop()
                await interaction.response.defer()
            
            @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
            async def deny_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your confirmation!", ephemeral=True)
                self.value = False
                self.stop()
                await interaction.response.defer()
        
        view = UnbanAllView(ctx)
        confirm_msg = await ctx.send(
            embed=discord.Embed(
                description=f"{ctx.author.mention}: Are you sure you want to unban all banned users?",
                color=Config.COLORS.WARNING
            ),
            view=view
        )
        
        await view.wait()
        
        if view.value is None:
            await confirm_msg.delete()
            return await ctx.deny("Unban all timed out")
        
        if not view.value:
            await confirm_msg.delete()
            return await ctx.deny("Unban all cancelled")
        
        await confirm_msg.delete()
        
        async with ctx.typing():
            bans = [entry async for entry in ctx.guild.bans(limit=None)]
            
            if not bans:
                return await ctx.deny("There are no banned users in this server")
            
            unbanned = 0
            for ban_entry in bans:
                try:
                    await ctx.guild.unban(ban_entry.user, reason=f"Unban all by {ctx.author} ({ctx.author.id})")
                    unbanned += 1
                except:
                    pass
        
        await ctx.approve(f"Successfully unbanned {unbanned} user(s)")
    
    @commands.command(help="List all members with a specific role")
    @example(",dump @Members")
    @commands.has_permissions(manage_roles=True)
    async def dump(self, ctx, *, role: discord.Role):
        members = [member for member in role.members]
        
        if not members:
            return await ctx.deny(f"No members have {role.mention}")
        
        class DumpPaginator(discord.ui.View):
            def __init__(self, ctx_inner, members_list, per_page=10):
                super().__init__(timeout=60)
                self.ctx = ctx_inner
                self.members = members_list
                self.per_page = per_page
                self.current_page = 0
                self.max_pages = (len(members_list) - 1) // per_page + 1
            
            def get_page_embed(self):
                start = self.current_page * self.per_page
                end = start + self.per_page
                page_members = self.members[start:end]
                
                embed = discord.Embed(
                    title=f"Members with {role.name} ({len(self.members)})",
                    description="\n".join([f"{i+start+1}. {m.mention} (`{m.id}`)" for i, m in enumerate(page_members)]),
                    color=role.color
                )
                embed.set_footer(text=f"Page {self.current_page + 1}/{self.max_pages}")
                return embed
            
            @discord.ui.button(emoji=Config.EMOJIS.BACKWARD, style=discord.ButtonStyle.gray)
            async def backward_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
                
                if self.current_page > 0:
                    self.current_page -= 1
                    await interaction.response.edit_message(embed=self.get_page_embed(), view=self)
                else:
                    await interaction.response.defer()
            
            @discord.ui.button(emoji=Config.EMOJIS.FORWARD, style=discord.ButtonStyle.gray)
            async def forward_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
                
                if self.current_page < self.max_pages - 1:
                    self.current_page += 1
                    await interaction.response.edit_message(embed=self.get_page_embed(), view=self)
                else:
                    await interaction.response.defer()
            
            @discord.ui.button(emoji=Config.EMOJIS.CLOSE, style=discord.ButtonStyle.red)
            async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
                
                await interaction.message.delete()
                self.stop()
        
        view = DumpPaginator(ctx, members)
        await ctx.send(embed=view.get_page_embed(), view=view)
    
    @commands.command(help="Change the current channel topic")
    @example(",topic Welcome to our server!")
    @commands.has_permissions(manage_channels=True)
    async def topic(self, ctx, *, new_topic: str = None):
        if not isinstance(ctx.channel, discord.TextChannel):
            return await ctx.deny("This command can only be used in text channels")
        
        if new_topic and len(new_topic) > 1024:
            return await ctx.deny("Channel topic must be 1024 characters or less")
        
        await ctx.channel.edit(topic=new_topic, reason=f"Changed by {ctx.author} ({ctx.author.id})")
        
        if new_topic:
            await ctx.approve(f"Successfully changed channel topic to: {new_topic}")
        else:
            await ctx.approve("Successfully cleared channel topic")
    
    @commands.command(help="Remove a member's attach files & embed links permission")
    @example(",imute @offermillions image spam")
    @commands.has_permissions(manage_roles=True)
    async def imute(self, ctx, member: discord.Member, *, reason: str = DEFAULT_REASON):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot mute this member due to role hierarchy")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot mute this member due to role hierarchy")
        if member == ctx.guild.owner:
            return await ctx.deny("You cannot mute the server owner")
        
        overwrites = ctx.channel.overwrites_for(member)
        overwrites.attach_files = False
        overwrites.embed_links = False
        
        await ctx.channel.set_permissions(
            member,
            overwrite=overwrites,
            reason=f"{reason} | {ctx.author} ({ctx.author.id})"
        )
        
        from maniac.plugins.moderation.history import Case
        await Case.create(ctx, member, "imute", reason)
        await ctx.approve(f"Successfully image muted {member.mention} for {reason}")
    
    @commands.command(help="Restore a member's attach files & embed links permission")
    @example(",iunmute @offermillions")
    @commands.has_permissions(manage_roles=True)
    async def iunmute(self, ctx, member: discord.Member, *, reason: str = DEFAULT_REASON):
        overwrites = ctx.channel.overwrites_for(member)
        
        if overwrites.attach_files is not False and overwrites.embed_links is not False:
            return await ctx.deny(f"{member.mention} is not image muted in this channel")
        
        overwrites.attach_files = None
        overwrites.embed_links = None
        
        await ctx.channel.set_permissions(
            member,
            overwrite=overwrites,
            reason=f"{reason} | {ctx.author} ({ctx.author.id})"
        )
        
        case_id = await self.log_moderation_action(ctx.guild, "Image Unmute", member, ctx.author, reason, ctx.channel)
        await ctx.approve(f"Successfully removed image mute from {member.mention} (Case #{case_id})")
    
    @commands.command(help="Remove a member's add reactions & use external emotes permission")
    @example(",rmute @offermillions reaction spam")
    @commands.has_permissions(manage_roles=True)
    async def rmute(self, ctx, member: discord.Member, *, reason: str = DEFAULT_REASON):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot mute this member due to role hierarchy")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot mute this member due to role hierarchy")
        if member == ctx.guild.owner:
            return await ctx.deny("You cannot mute the server owner")
        
        overwrites = ctx.channel.overwrites_for(member)
        overwrites.add_reactions = False
        overwrites.use_external_emojis = False
        
        await ctx.channel.set_permissions(
            member,
            overwrite=overwrites,
            reason=f"{reason} | {ctx.author} ({ctx.author.id})"
        )
        
        from maniac.plugins.moderation.history import Case
        await Case.create(ctx, member, "rmute", reason)
        await ctx.approve(f"Successfully reaction muted {member.mention} for {reason}")
    
    @commands.command(help="Restore a member's add reactions & use external emotes permission")
    @example(",runmute @offermillions")
    @commands.has_permissions(manage_roles=True)
    async def runmute(self, ctx, member: discord.Member, *, reason: str = DEFAULT_REASON):
        overwrites = ctx.channel.overwrites_for(member)
        
        if overwrites.add_reactions is not False and overwrites.use_external_emojis is not False:
            return await ctx.deny(f"{member.mention} is not reaction muted in this channel")
        
        overwrites.add_reactions = None
        overwrites.use_external_emojis = None
        
        await ctx.channel.set_permissions(
            member,
            overwrite=overwrites,
            reason=f"{reason} | {ctx.author} ({ctx.author.id})"
        )
        
        case_id = await self.log_moderation_action(ctx.guild, "Reaction Unmute", member, ctx.author, reason, ctx.channel)
        await ctx.approve(f"Successfully removed reaction mute from {member.mention} (Case #{case_id})")
    
    @commands.group(invoke_without_command=True, help="Ban a member and delete all their messages")
    @example(",hardban @offermillions severe violation")
    @commands.has_permissions(administrator=True)
    async def hardban(self, ctx, user: discord.Member | discord.User = None, *, reason: str = DEFAULT_REASON):
        if ctx.invoked_subcommand is not None:
            return
        
        if not user:
            return
        
        if isinstance(user, discord.Member):
            if user.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
                return await ctx.deny("You cannot hardban this member due to role hierarchy")
            if user.top_role >= ctx.guild.me.top_role:
                return await ctx.deny("I cannot hardban this member due to role hierarchy")
            if user == ctx.guild.owner:
                return await ctx.deny("You cannot hardban the server owner")
        
        class HardbanView(discord.ui.View):
            def __init__(self, ctx_inner):
                super().__init__(timeout=30)
                self.ctx = ctx_inner
                self.value = None
            
            @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
            async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your confirmation!", ephemeral=True)
                self.value = True
                self.stop()
                await interaction.response.defer()
            
            @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
            async def deny_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your confirmation!", ephemeral=True)
                self.value = False
                self.stop()
                await interaction.response.defer()
        
        view = HardbanView(ctx)
        
        embed = discord.Embed(
            title="Hardban Confirmation",
            description=f"Are you sure you want to hardban {user.mention}?\n\nThis will ban them and delete all their messages from the past 7 days.",
            color=Config.COLORS.WARNING
        )
        embed.add_field(name="User", value=f"{user} (`{user.id}`)", inline=True)
        embed.add_field(name="Reason", value=reason, inline=True)
        embed.set_footer(text="This action is irreversible")
        
        confirm_msg = await ctx.send(embed=embed, view=view)
        
        await view.wait()
        
        if view.value is None:
            await confirm_msg.delete()
            return await ctx.deny("Hardban timed out")
        
        if not view.value:
            await confirm_msg.delete()
            return await ctx.deny("Hardban cancelled")
        
        await confirm_msg.delete()
        
        await ctx.guild.ban(user, delete_message_days=7, reason=f"Hardban: {reason} | {ctx.author} ({ctx.author.id})")
        
        from maniac.plugins.moderation.history import Case
        await Case.create(ctx, user, "hardban", reason)
        
        await ctx.approve(f"Successfully hardbanned {user.mention} for {reason}")
    
    @hardban.command(name="list", help="List all hardbanned users")
    @commands.has_permissions(administrator=True)
    async def hardban_list(self, ctx):
        from maniac.core.database import db
        
        records = await db.moderation_cases.find({
            "guild_id": ctx.guild.id,
            "action": "hardban"
        }).sort("created_at", -1).to_list(length=None)
        
        if not records:
            return await ctx.deny("No hardbans found in this server")
        
        class HardbanListPaginator(discord.ui.View):
            def __init__(self, ctx_inner, records_list, per_page=10):
                super().__init__(timeout=60)
                self.ctx = ctx_inner
                self.records = records_list
                self.per_page = per_page
                self.current_page = 0
                self.max_pages = (len(records_list) - 1) // per_page + 1
            
            async def get_page_embed(self):
                start = self.current_page * self.per_page
                end = start + self.per_page
                page_records = self.records[start:end]
                
                embed = discord.Embed(
                    title=f"Hardban List ({len(self.records)})",
                    color=Config.COLORS.DEFAULT
                )
                
                description = []
                for record in page_records:
                    try:
                        user = await self.ctx.bot.fetch_user(record['target_id'])
                        description.append(
                            f"**Case #{record['case_id']}** - {user} (`{user.id}`)\n"
                            f"Reason: {record['reason']}\n"
                            f"<t:{int(record['created_at'].timestamp())}:R>"
                        )
                    except:
                        description.append(
                            f"**Case #{record['case_id']}** - Unknown User (`{record['target_id']}`)\n"
                            f"Reason: {record['reason']}\n"
                            f"<t:{int(record['created_at'].timestamp())}:R>"
                        )
                
                embed.description = "\n\n".join(description)
                embed.set_footer(text=f"Page {self.current_page + 1}/{self.max_pages}")
                return embed
            
            @discord.ui.button(emoji=Config.EMOJIS.BACKWARD, style=discord.ButtonStyle.gray)
            async def backward_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
                
                if self.current_page > 0:
                    self.current_page -= 1
                    await interaction.response.edit_message(embed=await self.get_page_embed(), view=self)
                else:
                    await interaction.response.defer()
            
            @discord.ui.button(emoji=Config.EMOJIS.FORWARD, style=discord.ButtonStyle.gray)
            async def forward_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
                
                if self.current_page < self.max_pages - 1:
                    self.current_page += 1
                    await interaction.response.edit_message(embed=await self.get_page_embed(), view=self)
                else:
                    await interaction.response.defer()
            
            @discord.ui.button(emoji=Config.EMOJIS.CLOSE, style=discord.ButtonStyle.red)
            async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
                
                await interaction.message.delete()
                self.stop()
        
        view = HardbanListPaginator(ctx, records)
        await ctx.send(embed=await view.get_page_embed(), view=view)
    
    @commands.command(help="Remove all existing invites in the server")
    @commands.has_permissions(manage_guild=True)
    async def clearinvites(self, ctx):
        class ClearInvitesView(discord.ui.View):
            def __init__(self, ctx_inner):
                super().__init__(timeout=30)
                self.ctx = ctx_inner
                self.value = None
            
            @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
            async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your confirmation!", ephemeral=True)
                self.value = True
                self.stop()
                await interaction.response.defer()
            
            @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
            async def deny_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.ctx.author.id:
                    return await interaction.response.send_message("This isn't your confirmation!", ephemeral=True)
                self.value = False
                self.stop()
                await interaction.response.defer()
        
        view = ClearInvitesView(ctx)
        confirm_msg = await ctx.send(
            embed=discord.Embed(
                description=f"{ctx.author.mention}: Are you sure you want to delete all server invites?",
                color=Config.COLORS.WARNING
            ),
            view=view
        )
        
        await view.wait()
        
        if view.value is None:
            await confirm_msg.delete()
            return await ctx.deny("Clear invites timed out")
        
        if not view.value:
            await confirm_msg.delete()
            return await ctx.deny("Clear invites cancelled")
        
        await confirm_msg.delete()
        
        async with ctx.typing():
            invites = await ctx.guild.invites()
            
            if not invites:
                return await ctx.deny("There are no invites in this server")
            
            deleted = 0
            for invite in invites:
                try:
                    await invite.delete(reason=f"Clear invites by {ctx.author} ({ctx.author.id})")
                    deleted += 1
                except:
                    pass
        
        await ctx.approve(f"Successfully deleted {deleted} invite(s)")
    
    @commands.group(invoke_without_command=True, help="Manage server stickers")
    async def sticker(self, ctx):
        pass
    
    @sticker.command(name="tag", help="Add server vanity to all stickers")
    @commands.has_permissions(manage_emojis=True)
    async def sticker_tag(self, ctx):
        if not ctx.guild.stickers:
            return await ctx.deny("This server has no stickers")
        
        vanity_code = ctx.guild.vanity_url_code
        
        if not vanity_code:
            class InviteConfirmView(discord.ui.View):
                def __init__(self, ctx_inner):
                    super().__init__(timeout=30)
                    self.ctx = ctx_inner
                    self.value = None
                
                @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
                async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id != self.ctx.author.id:
                        return await interaction.response.send_message("This isn't your confirmation!", ephemeral=True)
                    self.value = True
                    self.stop()
                    await interaction.response.defer()
                
                @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
                async def deny_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id != self.ctx.author.id:
                        return await interaction.response.send_message("This isn't your confirmation!", ephemeral=True)
                    self.value = False
                    self.stop()
                    await interaction.response.defer()
            
            view = InviteConfirmView(ctx)
            confirm_msg = await ctx.send(
                embed=discord.Embed(
                    description=f"{ctx.author.mention}: This server does not have a custom invite link. Would you like to use a normal server invite?",
                    color=Config.COLORS.WARNING
                ),
                view=view
            )
            
            await view.wait()
            
            if view.value is None:
                await confirm_msg.delete()
                return await ctx.deny("Sticker tag timed out")
            
            if not view.value:
                await confirm_msg.delete()
                return await ctx.deny("Sticker tag cancelled")
            
            await confirm_msg.delete()
            
            invite = await ctx.channel.create_invite(max_age=0, max_uses=0, reason=f"Sticker tag by {ctx.author}")
            tag = f".gg/{invite.code}"
        else:
            class VanityConfirmView(discord.ui.View):
                def __init__(self, ctx_inner):
                    super().__init__(timeout=30)
                    self.ctx = ctx_inner
                    self.value = None
                
                @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
                async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id != self.ctx.author.id:
                        return await interaction.response.send_message("This isn't your confirmation!", ephemeral=True)
                    self.value = True
                    self.stop()
                    await interaction.response.defer()
                
                @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
                async def deny_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id != self.ctx.author.id:
                        return await interaction.response.send_message("This isn't your confirmation!", ephemeral=True)
                    self.value = False
                    self.stop()
                    await interaction.response.defer()
            
            view = VanityConfirmView(ctx)
            confirm_msg = await ctx.send(
                embed=discord.Embed(
                    description=f"{ctx.author.mention}: This will rename all {len(ctx.guild.stickers)} sticker(s) with the server vanity `.gg/{vanity_code}`. Continue?",
                    color=Config.COLORS.WARNING
                ),
                view=view
            )
            
            await view.wait()
            
            if view.value is None:
                await confirm_msg.delete()
                return await ctx.deny("Sticker tag timed out")
            
            if not view.value:
                await confirm_msg.delete()
                return await ctx.deny("Sticker tag cancelled")
            
            await confirm_msg.delete()
            tag = f".gg/{vanity_code}"
        
        renamed = 0
        async with ctx.typing():
            for sticker in ctx.guild.stickers:
                if not sticker.name.startswith(".gg/"):
                    try:
                        new_name = f"{tag} {sticker.name}"
                        if len(new_name) > 30:
                            new_name = new_name[:30]
                        await sticker.edit(name=new_name, reason=f"Sticker tag by {ctx.author}")
                        renamed += 1
                    except:
                        pass
        
        await ctx.approve(f"Successfully tagged {renamed} sticker(s) with `{tag}`")
    
    @sticker.command(name="add", help="Add a sticker to the server")
    @commands.has_permissions(manage_emojis=True)
    async def sticker_add(self, ctx, *, name: str = None):
        if not ctx.message.reference and not ctx.message.attachments:
            return await ctx.deny("Please reply to a message with a sticker or attach an image")
        
        sticker_file = None
        sticker_name = name
        
        if ctx.message.reference:
            try:
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                
                if ref_msg.stickers:
                    sticker = ref_msg.stickers[0]
                    sticker_url = sticker.url
                    sticker_name = sticker_name or sticker.name
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(sticker_url) as resp:
                            if resp.status == 200:
                                sticker_file = await resp.read()
                
                elif ref_msg.attachments:
                    attachment = ref_msg.attachments[0]
                    if attachment.content_type and attachment.content_type.startswith("image/"):
                        sticker_file = await attachment.read()
                        if not sticker_name:
                            sticker_name = attachment.filename.split(".")[0]
            except:
                pass
        
        if not sticker_file and ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if attachment.content_type and attachment.content_type.startswith("image/"):
                sticker_file = await attachment.read()
                if not sticker_name:
                    sticker_name = attachment.filename.split(".")[0]
        
        if not sticker_file:
            return await ctx.deny("No valid sticker or image found")
        
        if not sticker_name:
            return await ctx.deny("Please provide a name for the sticker")
        
        if len(sticker_name) > 30:
            sticker_name = sticker_name[:30]
        
        if len(ctx.guild.stickers) >= ctx.guild.sticker_limit:
            return await ctx.deny("This server has reached the maximum amount of stickers")
        
        try:
            new_sticker = await ctx.guild.create_sticker(
                name=sticker_name,
                description=sticker_name,
                emoji="🙂",
                file=discord.File(io.BytesIO(sticker_file), filename="sticker.png"),
                reason=f"Added by {ctx.author} ({ctx.author.id})"
            )
            await ctx.approve(f"Successfully added sticker `{new_sticker.name}`")
        except Exception as e:
            await ctx.deny(f"Failed to add sticker: {str(e)}")
    
    @sticker.command(name="remove", aliases=["delete"], help="Remove a sticker from the server")
    @commands.has_permissions(manage_emojis=True)
    async def sticker_remove(self, ctx):
        if not ctx.message.reference:
            return await ctx.deny("Please reply to a message with a sticker")
        
        try:
            ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            
            if not ref_msg.stickers:
                return await ctx.deny("The replied message doesn't have a sticker")
            
            sticker = ref_msg.stickers[0]
            
            guild_sticker = discord.utils.get(ctx.guild.stickers, id=sticker.id)
            
            if not guild_sticker:
                return await ctx.deny("That sticker is not from this server")
            
            sticker_name = guild_sticker.name
            await guild_sticker.delete(reason=f"Deleted by {ctx.author} ({ctx.author.id})")
            await ctx.approve(f"Successfully deleted sticker `{sticker_name}`")
        except Exception as e:
            await ctx.deny(f"Failed to delete sticker: {str(e)}")
    
    @sticker.command(name="cleanup", help="Clean server sticker names from tags")
    @commands.has_permissions(manage_emojis=True)
    async def sticker_cleanup(self, ctx):
        if not ctx.guild.stickers:
            return await ctx.deny("This server has no stickers")
        
        cleaned = 0
        async with ctx.typing():
            for sticker in ctx.guild.stickers:
                if sticker.name.startswith(".gg/"):
                    try:
                        parts = sticker.name.split(" ", 1)
                        if len(parts) > 1:
                            new_name = parts[1]
                            await sticker.edit(name=new_name, reason=f"Sticker cleanup by {ctx.author}")
                            cleaned += 1
                    except:
                        pass
        
        if cleaned == 0:
            return await ctx.deny("No stickers needed cleaning")
        
        await ctx.approve(f"Successfully cleaned {cleaned} sticker(s)")
    
    @commands.command(help="Remove all dangerous roles from a member")
    @commands.has_permissions(manage_roles=True)
    async def strip(self, ctx, member: discord.Member, *, reason: str = DEFAULT_REASON):
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot strip roles from this member due to role hierarchy")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot strip roles from this member due to role hierarchy")
        if member == ctx.guild.owner:
            return await ctx.deny("You cannot strip roles from the server owner")
        
        dangerous_perms = [
            "administrator",
            "manage_guild",
            "manage_roles",
            "ban_members",
            "kick_members",
            "manage_channels",
            "manage_webhooks",
            "manage_emojis",
            "manage_messages",
            "mention_everyone"
        ]
        
        roles_to_remove = []
        for role in member.roles:
            if role == ctx.guild.default_role or role >= ctx.guild.me.top_role:
                continue
            
            role_perms = role.permissions
            if any(getattr(role_perms, perm, False) for perm in dangerous_perms):
                roles_to_remove.append(role)
        
        if not roles_to_remove:
            return await ctx.deny(f"{member.mention} has no dangerous roles to remove")
        
        from maniac.core.database import db
        from datetime import datetime, timezone
        
        role_ids = [role.id for role in roles_to_remove]
        
        await db.member_roles.update_one(
            {"guild_id": ctx.guild.id, "user_id": member.id},
            {
                "$set": {
                    "role_ids": role_ids,
                    "updated_at": datetime.now(timezone.utc),
                    "stripped_by": ctx.author.id
                }
            },
            upsert=True
        )
        
        try:
            await member.remove_roles(*roles_to_remove, reason=f"{reason} | {ctx.author} ({ctx.author.id})")
            case_id = await self.log_moderation_action(ctx.guild, "Strip Roles", member, ctx.author, f"Removed {len(roles_to_remove)} dangerous roles")
            await ctx.approve(f"Successfully removed {len(roles_to_remove)} dangerous role(s) from {member.mention} (Case #{case_id})")
        except Exception as e:
            await ctx.deny(f"Failed to remove roles: {str(e)}")
    
    @commands.command(help="Restore member's roles")
    @commands.has_permissions(manage_roles=True)
    async def restore(self, ctx, member: discord.Member):
        from maniac.core.database import db
        
        record = await db.member_roles.find_one({
            "guild_id": ctx.guild.id,
            "user_id": member.id
        })
        
        if not record or not record.get("role_ids"):
            return await ctx.deny(f"No saved roles found for {member.mention}")
        
        roles_to_add = []
        for role_id in record["role_ids"]:
            role = ctx.guild.get_role(role_id)
            if role and role < ctx.guild.me.top_role and role not in member.roles:
                roles_to_add.append(role)
        
        if not roles_to_add:
            return await ctx.deny(f"No roles to restore for {member.mention}")
        
        try:
            await member.add_roles(*roles_to_add, reason=f"Roles restored by {ctx.author} ({ctx.author.id})")
            case_id = await self.log_moderation_action(ctx.guild, "Restore Roles", member, ctx.author, f"Restored {len(roles_to_add)} roles")
            await ctx.approve(f"Successfully restored {len(roles_to_add)} role(s) to {member.mention} (Case #{case_id})")
        except Exception as e:
            await ctx.deny(f"Failed to restore roles: {str(e)}")
    
    @commands.command(help="Voice mute a member")
    @commands.has_permissions(mute_members=True)
    async def vcmute(self, ctx, member: discord.Member, *, reason: str = DEFAULT_REASON):
        if not member.voice:
            return await ctx.deny(f"{member.mention} is not in a voice channel")
        
        if member.voice.mute:
            return await ctx.deny(f"{member.mention} is already voice muted")
        
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot voice mute this member due to role hierarchy")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot voice mute this member due to role hierarchy")
        
        try:
            await member.edit(mute=True, reason=f"{reason} | {ctx.author} ({ctx.author.id})")
            case_id = await self.log_moderation_action(ctx.guild, "Voice Mute", member, ctx.author, reason)
            await ctx.approve(f"Successfully voice muted {member.mention} (Case #{case_id})")
        except Exception as e:
            await ctx.deny(f"Failed to voice mute: {str(e)}")
    
    @commands.command(help="Voice unmute a member")
    @commands.has_permissions(mute_members=True)
    async def vcunmute(self, ctx, member: discord.Member, *, reason: str = DEFAULT_REASON):
        if not member.voice:
            return await ctx.deny(f"{member.mention} is not in a voice channel")
        
        if not member.voice.mute:
            return await ctx.deny(f"{member.mention} is not voice muted")
        
        try:
            await member.edit(mute=False, reason=f"{reason} | {ctx.author} ({ctx.author.id})")
            case_id = await self.log_moderation_action(ctx.guild, "Voice Unmute", member, ctx.author, reason)
            await ctx.approve(f"Successfully voice unmuted {member.mention} (Case #{case_id})")
        except Exception as e:
            await ctx.deny(f"Failed to voice unmute: {str(e)}")
    
    @commands.command(help="Voice deafen a member")
    @commands.has_permissions(deafen_members=True)
    async def vcdeafen(self, ctx, member: discord.Member, *, reason: str = DEFAULT_REASON):
        if not member.voice:
            return await ctx.deny(f"{member.mention} is not in a voice channel")
        
        if member.voice.deaf:
            return await ctx.deny(f"{member.mention} is already voice deafened")
        
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot voice deafen this member due to role hierarchy")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot voice deafen this member due to role hierarchy")
        
        try:
            await member.edit(deafen=True, reason=f"{reason} | {ctx.author} ({ctx.author.id})")
            case_id = await self.log_moderation_action(ctx.guild, "Voice Deafen", member, ctx.author, reason)
            await ctx.approve(f"Successfully voice deafened {member.mention} (Case #{case_id})")
        except Exception as e:
            await ctx.deny(f"Failed to voice deafen: {str(e)}")
    
    @commands.command(help="Voice undeafen a member")
    @commands.has_permissions(deafen_members=True)
    async def vcundeafen(self, ctx, member: discord.Member, *, reason: str = DEFAULT_REASON):
        if not member.voice:
            return await ctx.deny(f"{member.mention} is not in a voice channel")
        
        if not member.voice.deaf:
            return await ctx.deny(f"{member.mention} is not voice deafened")
        
        try:
            await member.edit(deafen=False, reason=f"{reason} | {ctx.author} ({ctx.author.id})")
            case_id = await self.log_moderation_action(ctx.guild, "Voice Undeafen", member, ctx.author, reason)
            await ctx.approve(f"Successfully voice undeafened {member.mention} (Case #{case_id})")
        except Exception as e:
            await ctx.deny(f"Failed to voice undeafen: {str(e)}")
    
    @commands.command(help="Kick member from voice channel")
    @commands.has_permissions(move_members=True)
    async def vckick(self, ctx, member: discord.Member, *, reason: str = DEFAULT_REASON):
        if not member.voice:
            return await ctx.deny(f"{member.mention} is not in a voice channel")
        
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot kick this member from voice due to role hierarchy")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot kick this member from voice due to role hierarchy")
        
        try:
            await member.move_to(None, reason=f"{reason} | {ctx.author} ({ctx.author.id})")
            case_id = await self.log_moderation_action(ctx.guild, "Voice Kick", member, ctx.author, reason)
            await ctx.approve(f"Successfully kicked {member.mention} from voice channel (Case #{case_id})")
        except Exception as e:
            await ctx.deny(f"Failed to kick from voice: {str(e)}")
    
    @commands.command(name="slowmode", aliases=["slow"], help="Set channel slowmode")
    @example(",slowmode 5s")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, duration: str = None):
        if duration is None:
            current = ctx.channel.slowmode_delay
            if current == 0:
                return await ctx.warn("This channel has no slowmode set")
            await ctx.channel.edit(slowmode_delay=0, reason=f"Slowmode disabled by {ctx.author} ({ctx.author.id})")
            return await ctx.approve("Slowmode has been disabled")
        
        if duration.lower() in ["off", "0", "disable", "none"]:
            await ctx.channel.edit(slowmode_delay=0, reason=f"Slowmode disabled by {ctx.author} ({ctx.author.id})")
            return await ctx.approve("Slowmode has been disabled")
        
        time_regex = re.match(r"(\d+)([smh]?)", duration.lower())
        if not time_regex:
            return await ctx.deny("Invalid duration format. Use: 5s, 10m, 1h")
        
        amount, unit = time_regex.groups()
        amount = int(amount)
        
        if not unit:
            unit = 's'
        
        time_units = {"s": 1, "m": 60, "h": 3600}
        seconds = amount * time_units[unit]
        
        if seconds > 21600:
            return await ctx.deny("Slowmode cannot exceed 6 hours")
        
        await ctx.channel.edit(slowmode_delay=seconds, reason=f"Slowmode set by {ctx.author} ({ctx.author.id})")
        
        if seconds < 60:
            time_str = f"{seconds} seconds"
        elif seconds < 3600:
            time_str = f"{seconds // 60} minutes"
        else:
            time_str = f"{seconds // 3600} hours"
        
        await ctx.approve(f"Slowmode set to **{time_str}**")
    
    @commands.command(name="seticon", help="Set a new guild icon")
    @example(",seticon <attachment>")
    @commands.has_permissions(manage_guild=True)
    async def seticon(self, ctx):
        if not ctx.message.attachments:
            return await ctx.deny("Please attach an image to set as the server icon")
        
        attachment = ctx.message.attachments[0]
        if not attachment.content_type or not attachment.content_type.startswith("image/"):
            return await ctx.deny("The attachment must be an image")
        
        try:
            image_data = await attachment.read()
            await ctx.guild.edit(icon=image_data, reason=f"Icon changed by {ctx.author} ({ctx.author.id})")
            await ctx.approve("Successfully updated the server icon")
        except Exception as e:
            await ctx.deny(f"Failed to update server icon: {str(e)}")
    
    @commands.command(name="setsplashbackground", aliases=["setsplash"], help="Set a new guild splash background")
    @example(",setsplash <attachment>")
    @commands.has_permissions(manage_guild=True)
    async def setsplashbackground(self, ctx):
        if "INVITE_SPLASH" not in ctx.guild.features:
            return await ctx.deny("This server doesn't have access to splash backgrounds")
        
        if not ctx.message.attachments:
            return await ctx.deny("Please attach an image to set as the splash background")
        
        attachment = ctx.message.attachments[0]
        if not attachment.content_type or not attachment.content_type.startswith("image/"):
            return await ctx.deny("The attachment must be an image")
        
        try:
            image_data = await attachment.read()
            await ctx.guild.edit(splash=image_data, reason=f"Splash changed by {ctx.author} ({ctx.author.id})")
            await ctx.approve("Successfully updated the server splash background")
        except Exception as e:
            await ctx.deny(f"Failed to update splash background: {str(e)}")
    
    @commands.command(name="setbanner", help="Set a new guild banner")
    @example(",setbanner <attachment>")
    @commands.has_permissions(manage_guild=True)
    async def setbanner(self, ctx):
        if "BANNER" not in ctx.guild.features:
            return await ctx.deny("This server doesn't have access to banners")
        
        if not ctx.message.attachments:
            return await ctx.deny("Please attach an image to set as the server banner")
        
        attachment = ctx.message.attachments[0]
        if not attachment.content_type or not attachment.content_type.startswith("image/"):
            return await ctx.deny("The attachment must be an image")
        
        try:
            image_data = await attachment.read()
            await ctx.guild.edit(banner=image_data, reason=f"Banner changed by {ctx.author} ({ctx.author.id})")
            await ctx.approve("Successfully updated the server banner")
        except Exception as e:
            await ctx.deny(f"Failed to update server banner: {str(e)}")
    
    @commands.command(name="extractstickers", help="Download all server stickers in a zip file")
    @example(",extractstickers")
    @commands.has_permissions(manage_emojis=True)
    async def extractstickers(self, ctx):
        if not ctx.guild.stickers:
            return await ctx.deny("This server has no stickers")
        
        import zipfile
        import aiohttp
        
        processing = await ctx.send(f"{Config.EMOJIS.LOADING} Extracting stickers...")
        
        try:
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                async with aiohttp.ClientSession() as session:
                    for sticker in ctx.guild.stickers:
                        try:
                            async with session.get(str(sticker.url)) as resp:
                                if resp.status == 200:
                                    data = await resp.read()
                                    ext = "png" if sticker.format == discord.StickerFormatType.png else "json"
                                    zip_file.writestr(f"{sticker.name}.{ext}", data)
                        except:
                            continue
            
            zip_buffer.seek(0)
            await processing.delete()
            
            file = discord.File(zip_buffer, filename=f"{ctx.guild.name}_stickers.zip")
            await ctx.send(f"Successfully extracted **{len(ctx.guild.stickers)}** stickers", file=file)
        except Exception as e:
            await processing.delete()
            await ctx.deny(f"Failed to extract stickers: {str(e)}")
    
    @commands.command(name="extractemojis", help="Download all server emojis in a zip file")
    @example(",extractemojis")
    @commands.has_permissions(manage_emojis=True)
    async def extractemojis(self, ctx):
        if not ctx.guild.emojis:
            return await ctx.deny("This server has no custom emojis")
        
        import zipfile
        import aiohttp
        
        processing = await ctx.send(f"{Config.EMOJIS.LOADING} Extracting emojis...")
        
        try:
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                async with aiohttp.ClientSession() as session:
                    for emoji in ctx.guild.emojis:
                        try:
                            async with session.get(str(emoji.url)) as resp:
                                if resp.status == 200:
                                    data = await resp.read()
                                    ext = "gif" if emoji.animated else "png"
                                    zip_file.writestr(f"{emoji.name}.{ext}", data)
                        except:
                            continue
            
            zip_buffer.seek(0)
            await processing.delete()
            
            file = discord.File(zip_buffer, filename=f"{ctx.guild.name}_emojis.zip")
            await ctx.send(f"Successfully extracted **{len(ctx.guild.emojis)}** emojis", file=file)
        except Exception as e:
            await processing.delete()
            await ctx.deny(f"Failed to extract emojis: {str(e)}")
    
    @commands.command(name="maniacsetup", aliases=["setup"], help="Setup the maniac system (jail, modlog)")
    @example(",setup")
    @commands.has_permissions(administrator=True)
    async def maniacsetup(self, ctx):
        from maniac.core.database import db
        
        existing_config = await db.jail_config.find_one({"guild_id": ctx.guild.id})
        if existing_config:
            return await ctx.warn("Jail system is already set up. Use `,jail setup` to reconfigure")
        
        processing = await ctx.send(f"{Config.EMOJIS.LOADING} Setting up maniac system...")
        
        try:
            jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
            if not jail_role:
                jail_role = await ctx.guild.create_role(
                    name="Jailed",
                    color=discord.Color(0x2F3136),
                    reason=f"Setup by {ctx.author} ({ctx.author.id})"
                )
            
            maniac_category = discord.utils.get(ctx.guild.categories, name="maniac")
            if maniac_category:
                try:
                    await maniac_category.delete(reason=f"Recreating for setup by {ctx.author}")
                except:
                    pass
            
            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                jail_role: discord.PermissionOverwrite(view_channel=True),
                ctx.guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
            }
            
            maniac_category = await ctx.guild.create_category(
                name="maniac",
                overwrites=overwrites,
                reason=f"Setup by {ctx.author} ({ctx.author.id})"
            )
            
            jail_overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                jail_role: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_messages=True,
                    add_reactions=True,
                    attach_files=True,
                    embed_links=True
                ),
                ctx.guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_messages=True
                )
            }
            
            jail_channel = await maniac_category.create_text_channel(
                name="jail",
                overwrites=jail_overwrites,
                reason=f"Setup by {ctx.author} ({ctx.author.id})"
            )
            
            jail_log_channel = await maniac_category.create_text_channel(
                name="jail-log",
                overwrites={
                    ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    ctx.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
                },
                reason=f"Setup by {ctx.author} ({ctx.author.id})"
            )
            
            modlog_channel = await maniac_category.create_text_channel(
                name="mod-logs",
                overwrites={
                    ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    ctx.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
                },
                reason=f"Setup by {ctx.author} ({ctx.author.id})"
            )
            
            for channel in ctx.guild.channels:
                if channel.category == maniac_category:
                    continue
                try:
                    await channel.set_permissions(
                        jail_role,
                        view_channel=False,
                        send_messages=False,
                        add_reactions=False,
                        speak=False,
                        connect=False,
                        reason=f"Setup by {ctx.author} ({ctx.author.id})"
                    )
                except:
                    continue
            
            await db.jail_config.insert_one({
                "guild_id": ctx.guild.id,
                "role_id": jail_role.id,
                "category_id": maniac_category.id,
                "channel_id": jail_channel.id
            })
            
            await db.modlog_config.insert_one({
                "guild_id": ctx.guild.id,
                "channel_id": modlog_channel.id
            })
            
            await processing.delete()
            
            setup_embed = discord.Embed(
                description=f"Successfully set up **jail**, **jail-log**, **mod-logs**, **Jailed role**, and **modlog system**",
                color=Config.COLORS.SUCCESS
            )
            await ctx.send(embed=setup_embed)
            
            await modlog_channel.send(f"✅ Modlog channel configured. All moderation actions will be logged here.")
            await jail_log_channel.send(f"✅ Jail log channel configured. Jail actions will be logged here.")
            
        except Exception as e:
            await processing.delete()
            await ctx.deny(f"Failed to setup system: {str(e)}")
    
    @commands.group(name="jail", invoke_without_command=True, help="Jail a member")
    @example(",jail @offermillions spamming")
    @commands.has_permissions(manage_roles=True)
    async def jail(self, ctx, member: discord.Member = None, *, reason: str = "No reason provided"):
        if ctx.invoked_subcommand is not None:
            return
        
        if not member:
            return
        
        from maniac.core.database import db
        
        jail_config = await db.jail_config.find_one({"guild_id": ctx.guild.id})
        
        if not jail_config:
            return await ctx.deny("Jail system is not set up. Use `,setup` first")
        
        jail_role = ctx.guild.get_role(jail_config["role_id"])
        
        if not jail_role:
            return await ctx.deny("Jail role not found. Please run `,setup` again")
        
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot jail this member due to role hierarchy")
        
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot jail this member due to role hierarchy")
        
        if member == ctx.guild.owner:
            return await ctx.deny("You cannot jail the server owner")
        
        existing_jail = await db.jailed_members.find_one({
            "guild_id": ctx.guild.id,
            "user_id": member.id
        })
        
        if existing_jail:
            return await ctx.deny(f"{member.mention} is already jailed")
        
        role_ids = [role.id for role in member.roles if role.id != ctx.guild.default_role.id]
        
        await db.jailed_members.insert_one({
            "guild_id": ctx.guild.id,
            "user_id": member.id,
            "role_ids": role_ids,
            "jailed_at": datetime.now(timezone.utc),
            "jailed_by": ctx.author.id,
            "reason": reason
        })
        
        try:
            for role in member.roles:
                if role.id != ctx.guild.default_role.id and role < ctx.guild.me.top_role:
                    await member.remove_roles(role, reason=f"Jailed by {ctx.author} ({ctx.author.id})")
            
            await member.add_roles(jail_role, reason=f"Jailed by {ctx.author} ({ctx.author.id}): {reason}")
            case_id = await self.log_moderation_action(ctx.guild, "Jailed", member, ctx.author, reason)
            await ctx.approve(f"Successfully jailed {member.mention} for {reason} (Case #{case_id})")
        except Exception as e:
            await db.jailed_members.delete_one({"guild_id": ctx.guild.id, "user_id": member.id})
            await ctx.deny(f"Failed to jail member: {str(e)}")
    
    @jail.command(name="setup", help="Setup the jail system")
    @commands.has_permissions(administrator=True)
    async def jail_setup(self, ctx):
        from maniac.core.database import db
        
        existing_config = await db.jail_config.find_one({"guild_id": ctx.guild.id})
        if existing_config:
            return await ctx.warn("Jail system is already set up from `,setup` command")
        
        return await ctx.warn("Please use `,setup` command to set up the jail system")
    
    @commands.command(name="unjail", help="Unjail a member")
    @example(",unjail @offermillions")
    @commands.has_permissions(manage_roles=True)
    async def unjail(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        from maniac.core.database import db
        
        jail_config = await db.jail_config.find_one({"guild_id": ctx.guild.id})
        
        if not jail_config:
            return await ctx.warn("Jail system is not set up")
        
        jail_role = ctx.guild.get_role(jail_config["role_id"])
        
        jailed_data = await db.jailed_members.find_one({
            "guild_id": ctx.guild.id,
            "user_id": member.id
        })
        
        if not jailed_data:
            return await ctx.deny(f"{member.mention} is not jailed")
        
        try:
            if jail_role and jail_role in member.roles:
                await member.remove_roles(jail_role, reason=f"Unjailed by {ctx.author} ({ctx.author.id}): {reason}")
            
            for role_id in jailed_data.get("role_ids", []):
                role = ctx.guild.get_role(role_id)
                if role and role < ctx.guild.me.top_role:
                    await member.add_roles(role, reason=f"Unjailed by {ctx.author} ({ctx.author.id})")
            
            await db.jailed_members.delete_one({
                "guild_id": ctx.guild.id,
                "user_id": member.id
            })
            
            case_id = await self.log_moderation_action(ctx.guild, "Unjailed", member, ctx.author, reason)
            await ctx.approve(f"Successfully unjailed {member.mention} (Case #{case_id})")
        except Exception as e:
            await ctx.deny(f"Failed to unjail member: {str(e)}")
    
    @commands.command(name="modstats", aliases=["ms"], help="View moderation statistics for a user")
    @example(",modstats @offermillions")
    @commands.has_permissions(manage_messages=True)
    async def modstats(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        
        from maniac.core.database import db
        from datetime import datetime, timedelta, timezone
        
        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)
        fourteen_days_ago = now - timedelta(days=14)
        thirty_days_ago = now - timedelta(days=30)
        
        all_cases = await db.cases.find({
            "guild_id": ctx.guild.id,
            "user_id": member.id
        }).to_list(length=None)
        
        def count_actions(cases, start_date=None):
            filtered = cases if start_date is None else [c for c in cases if c.get("timestamp", now) >= start_date]
            stats = {
                "warned": 0,
                "kicked": 0,
                "banned": 0,
                "unbanned": 0,
                "timed_out": 0,
                "jailed": 0
            }
            for case in filtered:
                action = case.get("action", "").lower()
                if "warn" in action:
                    stats["warned"] += 1
                elif "kick" in action:
                    stats["kicked"] += 1
                elif "ban" in action and "unban" not in action:
                    stats["banned"] += 1
                elif "unban" in action:
                    stats["unbanned"] += 1
                elif "timeout" in action or "mute" in action:
                    stats["timed_out"] += 1
                elif "jail" in action:
                    stats["jailed"] += 1
            return stats
        
        stats_7d = count_actions(all_cases, seven_days_ago)
        stats_14d = count_actions(all_cases, fourteen_days_ago)
        stats_30d = count_actions(all_cases, thirty_days_ago)
        stats_all = count_actions(all_cases)
        
        total_actions = sum(stats_all.values())
        
        top_action = "None"
        top_count = 0
        for action, count in stats_all.items():
            if count > top_count:
                top_count = count
                top_action = action.replace("_", " ").title()
        
        if top_count == 0:
            top_action = "None (0)"
        else:
            top_action = f"{top_action} ({top_count})"
        
        last_action = "No actions recorded"
        if all_cases:
            sorted_cases = sorted(all_cases, key=lambda x: x.get("timestamp", now), reverse=True)
            last_case = sorted_cases[0]
            last_action = last_case.get("action", "Unknown")
        
        embed = discord.Embed(
            title=f"Moderation Statistics for {member}",
            color=Config.COLORS.DEFAULT
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        
        summary = f"> **Total Actions:** {total_actions}\n"
        summary += f"> **Top Action:** {top_action}\n"
        summary += f"> **Last Action:** {last_action}"
        embed.add_field(name="Summary", value=summary, inline=False)
        
        seven_days = f"> **Warned:** {stats_7d['warned']}\n"
        seven_days += f"> **Kicked:** {stats_7d['kicked']}\n"
        seven_days += f"> **Banned:** {stats_7d['banned']}\n"
        seven_days += f"> **Unbanned:** {stats_7d['unbanned']}\n"
        seven_days += f"> **Timed Out:** {stats_7d['timed_out']}\n"
        seven_days += f"> **Jailed:** {stats_7d['jailed']}"
        embed.add_field(name="7 Days", value=seven_days, inline=True)
        
        fourteen_days = f"> **Warned:** {stats_14d['warned']}\n"
        fourteen_days += f"> **Kicked:** {stats_14d['kicked']}\n"
        fourteen_days += f"> **Banned:** {stats_14d['banned']}\n"
        fourteen_days += f"> **Unbanned:** {stats_14d['unbanned']}\n"
        fourteen_days += f"> **Timed Out:** {stats_14d['timed_out']}\n"
        fourteen_days += f"> **Jailed:** {stats_14d['jailed']}"
        embed.add_field(name="14 Days", value=fourteen_days, inline=True)
        
        thirty_days = f"> **Warned:** {stats_30d['warned']}\n"
        thirty_days += f"> **Kicked:** {stats_30d['kicked']}\n"
        thirty_days += f"> **Banned:** {stats_30d['banned']}\n"
        thirty_days += f"> **Unbanned:** {stats_30d['unbanned']}\n"
        thirty_days += f"> **Timed Out:** {stats_30d['timed_out']}\n"
        thirty_days += f"> **Jailed:** {stats_30d['jailed']}"
        embed.add_field(name="30 Days", value=thirty_days, inline=True)
        
        all_time = f"> **Warned:** {stats_all['warned']}\n"
        all_time += f"> **Kicked:** {stats_all['kicked']}\n"
        all_time += f"> **Banned:** {stats_all['banned']}\n"
        all_time += f"> **Unbanned:** {stats_all['unbanned']}\n"
        all_time += f"> **Timed Out:** {stats_all['timed_out']}\n"
        all_time += f"> **Jailed:** {stats_all['jailed']}"
        embed.add_field(name="All Time", value=all_time, inline=False)
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
