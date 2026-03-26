import discord
from discord.ext import commands
from discord import Embed, TextChannel, VoiceChannel, Member, User, Message, Role
from typing import Optional
from datetime import datetime
from stare.core.tools.context import CustomContext as Context
from stare.core.config import Config


class Logs(commands.Cog):
    """Server logging system"""
    
    def __init__(self, bot):
        self.bot = bot
        self.case_numbers = {}  # Track case numbers per guild

    async def cog_load(self):
        """Create logs table"""
        if self.bot.db_pool:
            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS logs_config (
                    guild_id BIGINT PRIMARY KEY,
                    category_id BIGINT,
                    moderation_logs BIGINT,
                    message_logs BIGINT,
                    member_logs BIGINT,
                    voice_logs BIGINT,
                    server_logs BIGINT
                )
            """)

    async def get_log_channel(self, guild_id: int, log_type: str) -> Optional[TextChannel]:
        """Get the log channel for a specific type"""
        if not self.bot.db_pool:
            return None
        
        result = await self.bot.db_pool.fetchrow(
            f"SELECT {log_type} FROM logs_config WHERE guild_id = $1",
            guild_id
        )
        
        if result and result[log_type]:
            return self.bot.get_channel(result[log_type])
        return None

    async def get_next_case_number(self, guild_id: int) -> int:
        """Get the next case number for moderation logs"""
        if guild_id not in self.case_numbers:
            self.case_numbers[guild_id] = 1
        else:
            self.case_numbers[guild_id] += 1
        return self.case_numbers[guild_id]

    @commands.group(name="logs", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def logs(self, ctx: Context):
        """Logging system commands"""
        await ctx.send_help(ctx.command)

    @logs.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def logs_setup(self, ctx: Context):
        """Set up the logging system with all channels"""
        if not self.bot.db_pool:
            return await ctx.deny("Database not available!")

        # Check if already set up
        existing = await self.bot.db_pool.fetchrow(
            "SELECT * FROM logs_config WHERE guild_id = $1",
            ctx.guild.id
        )
        
        if existing:
            return await ctx.deny("Logging system is already set up! Use `;logs reset` to start over.")

        loading_msg = await ctx.loading("Hold tight, creating your channels now!")

        try:
            # Create private category
            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            category = await ctx.guild.create_category("Logs", overwrites=overwrites)

            # Create log channels
            moderation_logs = await ctx.guild.create_text_channel("moderation-logs", category=category)
            message_logs = await ctx.guild.create_text_channel("message-logs", category=category)
            member_logs = await ctx.guild.create_text_channel("member-logs", category=category)
            voice_logs = await ctx.guild.create_text_channel("voice-logs", category=category)
            server_logs = await ctx.guild.create_text_channel("server-logs", category=category)

            # Save to database
            await self.bot.db_pool.execute("""
                INSERT INTO logs_config (guild_id, category_id, moderation_logs, message_logs, member_logs, voice_logs, server_logs)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, ctx.guild.id, category.id, moderation_logs.id, message_logs.id, member_logs.id, voice_logs.id, server_logs.id)

            await loading_msg.delete()
            await ctx.approve("Logging system set up successfully!")
        except Exception as e:
            await loading_msg.delete()
            await ctx.deny(f"Failed to set up logging system: {str(e)}")

    @logs.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def logs_reset(self, ctx: Context):
        """Reset the logging system (deletes category and channels)"""
        if not self.bot.db_pool:
            return await ctx.deny("Database not available!")

        config = await self.bot.db_pool.fetchrow(
            "SELECT * FROM logs_config WHERE guild_id = $1",
            ctx.guild.id
        )
        
        if not config:
            return await ctx.deny("Logging system is not set up!")

        try:
            # Delete category and all channels
            category = ctx.guild.get_channel(config['category_id'])
            if category:
                for channel in category.channels:
                    await channel.delete()
                await category.delete()

            # Remove from database
            await self.bot.db_pool.execute(
                "DELETE FROM logs_config WHERE guild_id = $1",
                ctx.guild.id
            )

            await ctx.approve("Logging system has been reset!")
        except Exception as e:
            await ctx.deny(f"Failed to reset logging system: {str(e)}")

    # MODERATION LOGS
    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: User):
        """Log bans"""
        channel = await self.get_log_channel(guild.id, "moderation_logs")
        if not channel:
            return

        case_num = await self.get_next_case_number(guild.id)

        # Try to get ban reason
        try:
            ban_entry = await guild.fetch_ban(user)
            reason = ban_entry.reason or "No reason provided"
        except:
            reason = "No reason provided"

        embed = Embed(
            title=f"Case #{case_num}",
            description=f"1. **Banned** {user.mention} {discord.utils.format_dt(datetime.now(), 'R')} {reason}",
            color=Config.COLORS.DEFAULT
        )
        embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: User):
        """Log unbans"""
        channel = await self.get_log_channel(guild.id, "moderation_logs")
        if not channel:
            return

        case_num = await self.get_next_case_number(guild.id)

        embed = Embed(
            title=f"Case #{case_num}",
            description=f"1. **Unbanned** {user.mention} {discord.utils.format_dt(datetime.now(), 'R')} No reason provided.",
            color=Config.COLORS.DEFAULT
        )
        embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
        await channel.send(embed=embed)

    # MESSAGE LOGS
    @commands.Cog.listener()
    async def on_message_delete(self, message: Message):
        """Log deleted messages"""
        if message.author.bot or not message.guild:
            return

        channel = await self.get_log_channel(message.guild.id, "message_logs")
        if not channel:
            return

        embed = Embed(
            description=f"**Message deleted in** {message.channel.mention}\n**Content:** {message.content[:1000] if message.content else '*No content*'}",
            color=Config.COLORS.DEFAULT,
            timestamp=datetime.now()
        )
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        embed.set_footer(text=f"User ID: {message.author.id}")
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: Message, after: Message):
        """Log edited messages"""
        if before.author.bot or not before.guild or before.content == after.content:
            return

        channel = await self.get_log_channel(before.guild.id, "message_logs")
        if not channel:
            return

        embed = Embed(
            description=f"**Message edited in** {before.channel.mention}\n**Before:** {before.content[:500]}\n**After:** {after.content[:500]}",
            color=Config.COLORS.DEFAULT,
            timestamp=datetime.now()
        )
        embed.set_author(name=before.author.display_name, icon_url=before.author.display_avatar.url)
        embed.set_footer(text=f"User ID: {before.author.id}")
        await channel.send(embed=embed)

    # MEMBER LOGS
    @commands.Cog.listener()
    async def on_member_join(self, member: Member):
        """Log member joins"""
        channel = await self.get_log_channel(member.guild.id, "member_logs")
        if not channel:
            return

        embed = Embed(
            title="Member Joined",
            description=f"{member.mention} joined the server",
            color=Config.COLORS.DEFAULT,
            timestamp=datetime.now()
        )
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.set_footer(text=f"User ID: {member.id}")
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, 'R'))
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: Member):
        """Log member leaves"""
        channel = await self.get_log_channel(member.guild.id, "member_logs")
        if not channel:
            return

        embed = Embed(
            title="Member Left",
            description=f"{member.mention} left the server",
            color=Config.COLORS.DEFAULT,
            timestamp=datetime.now()
        )
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.set_footer(text=f"User ID: {member.id}")
        await channel.send(embed=embed)

    # VOICE LOGS
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: Member, before: discord.VoiceState, after: discord.VoiceState):
        """Log voice channel activity"""
        channel = await self.get_log_channel(member.guild.id, "voice_logs")
        if not channel:
            return

        # Joined voice channel
        if before.channel is None and after.channel is not None:
            embed = Embed(
                title="Voice Channel Join",
                description=f"{member.mention} joined {after.channel.mention}\n{discord.utils.format_dt(datetime.now(), 'F')}",
                color=Config.COLORS.DEFAULT,
                timestamp=datetime.now()
            )
            embed.set_author(name=member.guild.name, icon_url=member.guild.icon.url if member.guild.icon else None)
            embed.set_footer(text=f"User ID: {member.id}")
            await channel.send(embed=embed)

        # Left voice channel
        elif before.channel is not None and after.channel is None:
            embed = Embed(
                title="Voice Channel Leave",
                description=f"{member.mention} left {before.channel.mention}\n{discord.utils.format_dt(datetime.now(), 'F')}",
                color=Config.COLORS.DEFAULT,
                timestamp=datetime.now()
            )
            embed.set_author(name=member.guild.name, icon_url=member.guild.icon.url if member.guild.icon else None)
            embed.set_footer(text=f"User ID: {member.id}")
            await channel.send(embed=embed)

    # SERVER LOGS
    @commands.Cog.listener()
    async def on_guild_role_create(self, role: Role):
        """Log role creation"""
        channel = await self.get_log_channel(role.guild.id, "server_logs")
        if not channel:
            return

        embed = Embed(
            title="Role Created",
            description=f"Role {role.mention} was created",
            color=Config.COLORS.DEFAULT,
            timestamp=datetime.now()
        )
        embed.set_author(name=role.guild.name, icon_url=role.guild.icon.url if role.guild.icon else None)
        embed.set_footer(text=f"Role ID: {role.id}")
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: Role):
        """Log role deletion"""
        channel = await self.get_log_channel(role.guild.id, "server_logs")
        if not channel:
            return

        embed = Embed(
            title="Role Deleted",
            description=f"Role **{role.name}** was deleted",
            color=Config.COLORS.DEFAULT,
            timestamp=datetime.now()
        )
        embed.set_author(name=role.guild.name, icon_url=role.guild.icon.url if role.guild.icon else None)
        embed.set_footer(text=f"Role ID: {role.id}")
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: Role, after: Role):
        """Log role edits"""
        if before.name == after.name and before.permissions == after.permissions and before.color == after.color:
            return

        channel = await self.get_log_channel(before.guild.id, "server_logs")
        if not channel:
            return

        changes = []
        if before.name != after.name:
            changes.append(f"Name: {before.name} → {after.name}")
        if before.color != after.color:
            changes.append(f"Color: {before.color} → {after.color}")
        if before.hoist != after.hoist:
            changes.append(f"Hoist: {before.hoist} → {after.hoist}")

        if not changes:
            return

        embed = Embed(
            title="Role Edited",
            description=f"Role {after.mention} was edited\n\n**Changes**\n" + "\n".join(changes),
            color=Config.COLORS.DEFAULT,
            timestamp=datetime.now()
        )
        embed.set_author(name=before.guild.name, icon_url=before.guild.icon.url if before.guild.icon else None)
        embed.set_footer(text=f"Role ID: {after.id}")
        await channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Logs(bot))
