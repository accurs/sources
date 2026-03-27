from discord import ui
import discord
from discord.ui import View, button
from discord import (app_commands, NotFound, HTTPException, ButtonStyle, Button, Embed, Role, User, Invite, Message, utils, Member, TextChannel, VoiceChannel, CategoryChannel, ForumChannel, StageChannel, Permissions)
from discord.utils import oauth_url
from discord.ext import commands
from discord.ext.commands import (Cog, hybrid_command, command, Author)
from datetime import datetime, timedelta, timezone
import time
from contextlib import suppress
from heist.framework.discord import Context
from heist.framework.tools import is_dangerous
import urllib.parse
from urllib.parse import quote, urlparse
import asyncio
import psutil
from PIL import Image, ImageOps
from typing import Iterable, Optional, cast, Union
from discord.utils import format_dt
from humanize import precisedelta
from heist.framework.discord.checks import is_blacklisted, get_blacklist_reason
from heist.framework.discord.decorators import check_donor, check_famous, check_owner, check_blacklisted, donor_only
from heist.framework.tools.separator import makeseparator, maketintedlogo
from heist.framework.tools.titles import get_title
from heist.framework.script.agecheck import AgeCheck, AgeCheckView
import os, aiohttp, asyncio, io
from typing import TYPE_CHECKING
import base64
if TYPE_CHECKING:
    from heist.framework.discord.cv2 import cv2 as cpv2

LASTFM_KEY = os.getenv("LASTFM_API_KEY")

class Info(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.LASTFM_KEY = LASTFM_KEY

    @hybrid_command(
        name="ping",
        aliases=["ms", "latency", "lat"],
        description="View the bot's latency"
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def ping(self, ctx):
        start_time = time.time()
        embed = Embed(color=await self.bot.get_color(ctx.author.id))
        
        latency = round(self.bot.latency * 1000)
        description = (
            f"> 📡 **Ping:** `{latency}ms`\n"
            f"> 🗄️ **Database:** `2ms`"
        )
            
        embed.description = description
        
        if ctx.interaction:
            if ctx.interaction.response.is_done():
                message = await ctx.interaction.followup.send(embed=embed)
            else:
                await ctx.interaction.response.send_message(embed=embed)
                message = await ctx.interaction.original_response()
        else:
            message = await ctx.send(embed=embed)

        edit_ping = round((time.time() - start_time) * 1000)
        await asyncio.sleep(1)
            
        description = (
            f"> 📡 **Ping:** `{latency}ms` (edit: **{edit_ping}ms**)\n"
            f"> 🗄️ **Database:** `2ms`"
        )
            
        embed.description = description
        await message.edit(embed=embed)
            
    @hybrid_command(
        name="about",
        aliases=["bi", "botinfo"],
        description="View info about the bot."
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def about(self, ctx):
        await ctx.typing()

        total_members = sum(g.member_count for g in self.bot.guilds)
        total_bots = sum(len([m for m in g.members if m.bot]) for g in self.bot.guilds)
        total_users = total_members - total_bots
        latency = round(self.bot.latency * 1000)

        process = psutil.Process()
        ram_usage = process.memory_full_info().rss / 1024**2
        cpu_usage = psutil.cpu_percent()

        def fmt_uptime(x):
            h = x // 3600
            m = (x % 3600) // 60
            return f"{h}h{m}m"

        uptime = None
        try:
            if self.bot.uptime:
                u = time.time() - self.bot.uptime.timestamp()
                uptime = fmt_uptime(int(u))
        except:
            pass

        async with aiohttp.ClientSession() as session:
            async with session.get("http://127.0.0.1:5002/getcount") as resp:
                stats = await resp.json()
                install_count = stats["discord_user_install_count"]

        main_color = await self.bot.get_color(ctx.author.id)

        logo_bytes = await maketintedlogo(self.bot, ctx.author.id)
        logo_buf = io.BytesIO(logo_bytes)

        title_block = [
            ui.TextDisplay(
                "### Heist, your <:discordlogo:1442002842356285642> Discord companion\n"
                "-# Developed by the [**Heist Team**](https://github.com/heistindustries) • "
                "[**Cosmin**](https://cursi.ng) & [**Lane**](https://github.com/heistindustries)"
            )
        ]

        stats_txt = (
            f"-# Commands » `{len(self.bot.commands):,}`\n"
            f"-# Latency » `{latency}ms`\n"
            f"-# Uptime » {f'<t:{int(self.bot.uptime.timestamp())}:R>' if uptime else '`?`'}\n"
            f"-# Servers » `{len(self.bot.guilds):,}`\n"
            f"-# Users » `{total_users:,}`\n"
            f"-# Installed Users » `{install_count:,}`\n"
            f"-# Memory » `{ram_usage/1024:.1f}%` ({ram_usage:.2f} MiB)"
        )

        stats_block = [
            ui.Section(
                ui.TextDisplay(stats_txt),
                accessory=ui.Thumbnail("attachment://heist.png")
            )
        ]

        links_block = [
            ui.TextDisplay(
                "-# [Website](https://heist.lol) • "
                "[Quickstart](https://heist.lol/quickstart) • "
                "[Discord](https://discord.gg/heistbot)"
            )
        ]

        advanced = [
            title_block,
            stats_block,
            links_block
        ]

        buttons = [
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                url="https://discord.com/oauth2/authorize?client_id=1225070865935368265",
                emoji="<:plus:1375956327448449084>",
                label="Authorize"
            ),
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                url="https://discord.gg/heistbot",
                emoji="<:support:1362140985261297904>",
                label="Support"
            )
        ]

        await cpv2.send(
            ctx,
            advanced_sections=advanced,
            color=main_color,
            files=[discord.File(logo_buf, filename="heist.png")],
            buttons=buttons,
            buttons_inside=True
        )
    
    @command()
    async def joins(self, ctx: Context):
        """View recent joins in the server"""
        guild = ctx.guild
        
        members = sorted(guild.members, key=lambda m: m.joined_at or datetime.min, reverse=True)
        
        now = datetime.now(timezone.utc)
        recent_joins = [m for m in members if m.joined_at and (now - m.joined_at).days < 1]
        
        if not recent_joins:
            embed = Embed(
                color=ctx.config.colors.information,
                title=f"0 joins in the last 1d in {guild.name}",
                description="No recent joins found."
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)
        
        entries = []
        for idx, member in enumerate(recent_joins, start=1):
            timestamp = int(member.joined_at.timestamp())
            entries.append(f"`{idx:02d}` {member.display_name} - <t:{timestamp}:R>")
        
        if len(entries) > 5:
            base_embed = Embed(
                color=ctx.config.colors.information,
                title=f"{len(recent_joins)} joins in the last 1d in {guild.name}"
            )
            base_embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            await ctx.paginate(entries, embed=base_embed, per_page=5)
        else:
            embed = Embed(
                color=ctx.config.colors.information,
                title=f"{len(recent_joins)} joins in the last 1d in {guild.name}",
                description="\n".join(entries)
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
    
    @command()
    async def bots(self, ctx: Context):
        """View bots in the server"""
        guild = ctx.guild
        
        bot_members = [m for m in guild.members if m.bot]
        
        if not bot_members:
            embed = Embed(
                color=ctx.config.colors.information,
                title="0 Bots",
                description="No bots found in this server."
            )
            return await ctx.send(embed=embed)
        
        entries = []
        for idx, bot in enumerate(bot_members, start=1):
            entries.append(f"`{idx:02d}` <@{bot.id}> (`{bot.id}`)")
        
        if len(entries) > 10:
            base_embed = Embed(
                color=ctx.config.colors.information,
                title=f"{len(bot_members)} Bots"
            )
            await ctx.paginate(entries, embed=base_embed, per_page=10)
        else:
            embed = Embed(
                color=ctx.config.colors.information,
                title=f"{len(bot_members)} Bots",
                description="\n".join(entries)
            )
            await ctx.send(embed=embed)
    
    @command(aliases=["ri"])
    async def roleinfo(self, ctx: Context, role: Role):
        """View information about a role"""
        
        has_dangerous_perms = is_dangerous(role)
        
        if has_dangerous_perms:
            dangerous_perms = [
                "administrator", "kick_members", "ban_members", "manage_guild",
                "manage_roles", "manage_channels", "manage_expressions",
                "manage_webhooks", "manage_nicknames", "mention_everyone"
            ]
            role_perms = [perm for perm, value in role.permissions if value and perm in dangerous_perms]
        else:
            role_perms = []
        
        embed = Embed(
            color=role.color if role.color.value != 0 else ctx.config.colors.information,
            title=role.name
        )
        
        embed.add_field(
            name="Role ID",
            value=f"`{role.id}`",
            inline=True
        )
        
        embed.add_field(
            name="Role color",
            value="No color" if role.color.value == 0 else f"#{role.color.value:06x}",
            inline=True
        )
        
        embed.add_field(
            name="Created",
            value=f"<t:{int(role.created_at.timestamp())}:f> **{utils.format_dt(role.created_at, 'R')}**",
            inline=False
        )
        
        members_with_role = [m for m in ctx.guild.members if role in m.roles]
        member_count = len(members_with_role)
        
        if member_count == 0:
            member_text = "No members"
        elif member_count == 1:
            member_text = members_with_role[0].display_name
        else:
            member_text = f"{member_count} members"
        
        embed.add_field(
            name=f"{member_count} Member{'s' if member_count != 1 else ''}",
            value=member_text,
            inline=False
        )
        
        if role_perms:
            perm_names = [perm.replace('_', ' ').title() for perm in role_perms]
            embed.add_field(
                name="Dangerous Permissions",
                value=", ".join(perm_names),
                inline=False
            )
        
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)
    
    @command(aliases=["perms"])
    async def permissions(self, ctx: Context):
        """View your permissions in the server"""
        member = ctx.author
        guild = ctx.guild
        
        user_perms = [perm for perm, value in member.guild_permissions if value]
        
        perm_names = [perm.replace('_', ' ').title() for perm in user_perms]
        
        entries = perm_names
        
        if len(entries) > 10:
            base_embed = Embed(
                color=ctx.config.colors.information
            )
            base_embed.set_author(
                name=f"Your permissions in {guild.name} ({len(entries)})",
                icon_url=ctx.author.display_avatar.url
            )
            await ctx.paginate(entries, embed=base_embed, per_page=10)
        else:
            numbered_entries = []
            for idx, perm in enumerate(entries, start=1):
                numbered_entries.append(f"`{idx:02d}` {perm}")
            
            embed = Embed(
                color=ctx.config.colors.information,
                description="\n".join(numbered_entries)
            )
            embed.set_author(
                name=f"Your permissions in {guild.name} ({len(entries)})",
                icon_url=ctx.author.display_avatar.url
            )
            await ctx.send(embed=embed)
    
    @hybrid_command(aliases=["av", "pfp"])
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def avatar(self, ctx: Context, *, member: User = None):
        """View a user's avatar"""
        if not member:
            member = ctx.author
        
        await ctx.neutral(
            "",
            title=f"{member.display_name}'s avatar",
            image=member.display_avatar.url,
            footer=f"User ID: {member.id}"
        )
    
    @hybrid_command()
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def banner(self, ctx: Context, *, member: User = None):
        """View a user's banner"""
        if not member:
            member = ctx.author
        
        user = await self.bot.fetch_user(member.id)
        
        if not user.banner:
            return await ctx.warn(f"{member.display_name} doesn't have a banner.")
        
        await ctx.neutral(
            "",
            title=f"{member.display_name}'s banner",
            image=user.banner.url,
            footer=f"User ID: {member.id}"
        )
    
    @command(aliases=["sav"])
    async def serveravatar(self, ctx: Context, *, member: Member = None):
        """View a user's server avatar"""
        if not member:
            member = ctx.author
        
        if not member.guild_avatar:
            return await ctx.warn(f"{member.display_name} doesn't have a server avatar.")
        
        await ctx.neutral(
            "",
            title=f"{member.display_name}'s server avatar",
            image=member.guild_avatar.url,
            footer=f"User ID: {member.id}"
        )
    
    @command(aliases=["sbanner"])
    async def serverbanner(self, ctx: Context):
        """View the server's banner"""
        guild = ctx.guild
        
        if not guild.banner:
            return await ctx.warn(f"{guild.name} doesn't have a banner.")
        
        await ctx.neutral(
            "",
            title=f"{guild.name}'s Banner",
            image=guild.banner.url,
            footer=f"Server ID: {guild.id}"
        )
    
    @command(aliases=["ci"])
    async def channelinfo(self, ctx: Context, channel=None):
        """View information about a channel"""
        if not channel:
            channel = ctx.channel
        else:
            try:
                channel = await commands.TextChannelConverter().convert(ctx, str(channel))
            except:
                try:
                    channel = ctx.bot.get_channel(int(channel))
                    if not channel:
                        return await ctx.warn("Channel not found.")
                except:
                    return await ctx.warn("Invalid channel ID.")
        
        channel_types = {
            TextChannel: "text",
            VoiceChannel: "voice", 
            CategoryChannel: "category",
            ForumChannel: "forum",
            StageChannel: "stage"
        }
        
        channel_type = channel_types.get(type(channel), "unknown")
        
        embed = Embed(
            color=ctx.config.colors.information,
            title=channel.name
        )
        
        embed.add_field(
            name="Channel ID",
            value=f"`{channel.id}`",
            inline=True
        )
        
        embed.add_field(
            name="Type",
            value=channel_type,
            inline=True
        )
        
        embed.add_field(
            name="Created At",
            value=f"<t:{int(channel.created_at.timestamp())}:F>",
            inline=True
        )
        
        embed.add_field(
            name="Guild",
            value=f"{channel.guild.name} (`{channel.guild.id}`)",
            inline=True
        )
        
        await ctx.send(embed=embed)
    
    @command()
    async def roles(self, ctx: Context):
        """View roles in the server"""
        guild = ctx.guild
        
        roles_with_members = [role for role in guild.roles if len(role.members) > 0 and role != guild.default_role]
        roles_with_members.sort(key=lambda r: len(r.members), reverse=True)
        
        if not roles_with_members:
            embed = Embed(
                color=ctx.config.colors.information,
                title="Roles with Members (0)",
                description="No roles with members found."
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)
        
        entries = []
        for idx, role in enumerate(roles_with_members, start=1):
            entries.append(f"`{idx:02d}`   **<@&{role.id}>**")
        
        if len(entries) > 10:
            base_embed = Embed(
                color=ctx.config.colors.information,
                title=f"Roles with Members ({len(roles_with_members)})"
            )
            base_embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            await ctx.paginate(entries, embed=base_embed, per_page=10)
        else:
            embed = Embed(
                color=ctx.config.colors.information,
                title=f"Roles with Members ({len(roles_with_members)})",
                description="\n".join(entries)
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

    @command(name="inviteinfo", aliases=["ii"])
    async def inviteinfo(self, ctx: Context, *, code: Invite):
        """View information about a guild using an invite code."""
        return await ctx.send(
            embed=Embed(title=f"Invite Code: {code.code}", color=ctx.config.colors.information)
            .add_field(
                name="Invite & Channel",
                value=f"**Name:** {code.channel.name} \n**ID:** {code.channel.id} \n**Created:** {format_dt(code.created_at, 'F') if code.created_at else 'Unknown'} \n**Expiration:** {format_dt(code.expires_at) if code.expires_at else 'Never'} \n**Inviter:** {code.inviter if code.inviter else 'Vanity URL'}",  # type: ignore
            )
            .add_field(
                name="Guild",
                value=f"**Name:** {code.guild.name} \n**Created:** {format_dt(code.guild.created_at, 'F')} \n**Members:** {code.approximate_member_count: ,} \n**Active:** {code.approximate_presence_count: ,} \n**Verification:** {code.guild.verification_level}",  # type: ignore
            )
            .set_author(name=ctx.author, icon_url=ctx.author.display_avatar)
            .set_thumbnail(url=code.guild.icon)
        )

    @command(name="banreason", description="Get a user's ban reason.")
    @commands.has_permissions(ban_members=True)
    async def banreason(self, ctx: Context, *, user: User):
        """View the reason why someone was banned."""
        bans = [entry async for entry in ctx.guild.bans()]  # type: ignore
        entry = next((b for b in bans if b.user.id == user.id), None)

        if not entry:
            return await ctx.warn("This member is **not** banned.")

        async for log in ctx.guild.audit_logs(action=discord.AuditLogAction.ban):
            if log.target.id == user.id:
                timestamp = int(log.created_at.timestamp())
                return await ctx.neutral(
                    f"**{user.name}** was banned for **{entry.reason or 'No reason provided'}** "
                    f"at <t:{timestamp}:f>."
                )

        return await ctx.neutral(
        f"**{user.name}** was banned for **{entry.reason or 'No reason provided'}**, "
        f"but the timestamp is unknown."
    )

    @command()
    @commands.has_permissions(manage_guild=True)
    async def invites(self, ctx: Context):
        """View server invites"""
        invites = await ctx.guild.invites()
        
        if not invites:
            return await ctx.warn("No invites found")
        
        entries = []
        for idx, invite in enumerate(invites, start=1):
            inviter = invite.inviter.display_name if invite.inviter else "Unknown"
            inviter_id = invite.inviter.id if invite.inviter else "Unknown"
            entries.append(f"`{idx:02d}` [{invite.code}](https://discord.gg/{invite.code}) by **{inviter}** (`{inviter_id}`)") 
        
        embed = Embed(
            color=ctx.config.colors.information,
            title=f"{len(invites)} invites",
            description="\n".join(entries)
        )
        
        await ctx.send(embed=embed)

    @command()
    async def inrole(self, ctx: Context, *, role: Role):
        """View members in a role"""
        members = role.members
        
        if not members:
            return await ctx.warn(f"No members found in {role.name}")
        
        entries = []
        for idx, member in enumerate(members, start=1):
            you_text = " - **you**" if member.id == ctx.author.id else ""
            entries.append(f"`{idx:02d}` <@{member.id}> (`{member.id}`){you_text}")
        
        embed = Embed(
            color=ctx.config.colors.information,
            title=f"{len(members)} members in {role.name}",
            description="\n".join(entries)
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        
        await ctx.send(embed=embed)

    @command()
    async def boosters(self, ctx: Context):
        """View server boosters"""
        boosters = ctx.guild.premium_subscribers
        
        if not boosters:
            return await ctx.warn("No boosters found")
        
        entries = []
        for idx, member in enumerate(boosters, start=1):
            you_text = " - **you**" if member.id == ctx.author.id else ""
            entries.append(f"`{idx:02d}` <@{member.id}> (`{member.id}`){you_text}")
        
        embed = Embed(
            color=ctx.config.colors.information,
            title=f"{len(boosters)} boosters",
            description="\n".join(entries)
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        
        await ctx.send(embed=embed)

    @command(aliases=["fm"])
    async def firstmessage(self, ctx: Context, *, member: Member = None):
        """Find the first message sent by a user in this channel"""
        if not member:
            member = ctx.author
        
        async for message in ctx.channel.history(limit=None, oldest_first=True):
            if message.author.id == member.id:
                message_url = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{message.id}"
                return await ctx.neutral(
                    f"Jump to the [first message]({message_url}) sent by **{member.display_name}**"
                )
        
        await ctx.warn(f"No messages found from **{member.display_name}** in this channel")

    @hybrid_command()
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def getbotinvite(self, ctx: Context, *, user: User):
        """
        Get an invite of a bot
        """

        if not user.bot:
            return await ctx.warn("This is not a bot")

        invite_url = f"https://discord.com/oauth2/authorize?client_id={user.id}"
        return await ctx.reply(f"Invite [{user}]({invite_url})")
        
    @commands.hybrid_command(name="me", description="View your Heist info")
    @app_commands.allowed_installs(users=True, guilds=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(user="Lookup Heist user by Discord ID", uid="Lookup user by Heist UID")
    async def me(self, ctx: Union[commands.Context, discord.Interaction], user: Optional[discord.User] = None, uid: Optional[str] = None):
        interaction = ctx if isinstance(ctx, discord.Interaction) else None
        ctx = await commands.Context.from_interaction(ctx) if interaction else ctx

        async def get_lastfm_user(user_id: int):
            async with self.bot.pool.acquire() as conn:
                data = await conn.fetchrow("SELECT lastfm_username, hidden FROM lastfm_users WHERE discord_id = $1", user_id)
                if not data or not data["lastfm_username"]:
                    return None
                return data["lastfm_username"], data["hidden"]

        if uid and user:
            return await ctx.warn("You cannot use both the UID and User parameters.")
        if uid:
            if not uid.isdigit():
                return await ctx.warn("The provided UID is not a valid integer.")
            if uid == "0":
                uid = "1"
            user_id = await self.bot.pool.fetchval("SELECT user_id FROM user_data WHERE hid = $1", int(uid))
            if not user_id:
                return await ctx.warn("This HID does not belong to anyone.")
            try:
                user = await self.bot.fetch_user(int(user_id))
            except:
                return await ctx.warn("Could not fetch user information.")
        elif user:
            user_id = str(user.id)
            hid = await self.bot.pool.fetchval("SELECT hid FROM user_data WHERE user_id = $1", user_id)
            if not hid:
                return await ctx.warn("User is not in Heist's database.")
        else:
            user = ctx.author
            user_id = str(user.id)

        user_name = user.name
        async with self.bot.pool.acquire() as conn:
            exists = await conn.fetchval("SELECT 1 FROM user_data WHERE user_id = $1", user_id)
            if not exists:
                await conn.execute("INSERT INTO user_data (user_id) VALUES ($1)", user_id)
            hid = await conn.fetchval("SELECT hid FROM user_data WHERE user_id = $1", user_id)

        is_donor = await check_donor(self.bot, int(user_id))
        is_famous = await check_famous(self.bot, int(user_id))
        is_owner = await check_owner(self.bot, int(user.id))
        is_blacklisted_user = await check_blacklisted(self.bot, int(user.id))

        donor_data = await self.bot.pool.fetchrow("SELECT subscription_type, expires_at FROM donors WHERE user_id = $1", user_id)
        premium_expiry = None
        if donor_data and donor_data["subscription_type"] == "temporary" and donor_data["expires_at"]:
            premium_expiry = donor_data["expires_at"]
        redis_expiry = await self.bot.redis.ttl(f"premium_expiry:{user_id}")
        if redis_expiry > 0 and not premium_expiry:
            premium_expiry = datetime.now(timezone.utc) + timedelta(seconds=redis_expiry)

        fame_status = await self.bot.pool.fetchval("SELECT fame FROM user_data WHERE user_id = $1", user_id)

        lastfm_info = ""
        try:
            user_data_lfm = await get_lastfm_user(int(user_id))
            if user_data_lfm:
                lastfm_username, hidden = user_data_lfm
                if not hidden:
                    api_key = self.LASTFM_KEY
                    recent_tracks_url = f"http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={lastfm_username}&api_key={api_key}&format=json"
                    async with self.session.get(recent_tracks_url) as r:
                        if r.status == 200:
                            tracks = (await r.json())["recenttracks"].get("track", [])
                            if tracks:
                                track = tracks[0]
                                is_now_playing = "@attr" in track and "nowplaying" in track["@attr"] and track["@attr"]["nowplaying"] == "true"
                                artist_name = track["artist"]["#text"]
                                track_name = track["name"]
                                if is_now_playing:
                                    artistenc = urllib.parse.quote(artist_name)
                                    trackenc = urllib.parse.quote(track_name)
                                    spotify_url = f"http://127.0.0.1:2053/api/search?lastfm_username={lastfm_username}&track_name={trackenc}&artist_name={artistenc}"
                                    async with self.session.get(spotify_url) as spotify_response:
                                        status = "<:lastfm:1275185763574874134>"
                                        if spotify_response.status == 200:
                                            spotify_data = await spotify_response.json()
                                            spotify_track_url = spotify_data.get("spotify_link")
                                            if spotify_track_url:
                                                lastfm_info = f"{status} ***[{track_name}]({spotify_track_url})*** ([@{lastfm_username}](https://www.last.fm/user/{lastfm_username}))\n\n"
                                            else:
                                                lastfm_info = f"{status} ***{track_name}*** ([@{lastfm_username}](https://www.last.fm/user/{lastfm_username}))\n\n"
                                        else:
                                            lastfm_info = f"{status} ***{track_name}*** ([@{lastfm_username}](https://www.last.fm/user/{lastfm_username}))\n\n"
                                else:
                                    lastfm_info = f"<:lastfm:1275185763574874134> [@{lastfm_username}](https://www.last.fm/user/{lastfm_username})\n\n"
        except:
            pass

        async with self.bot.pool.acquire() as conn:
            redeemed_row = await conn.fetchrow(
                """
                SELECT code, target_user_id, actor_id
                FROM premium_gift_logs
                WHERE action='redeemed'
                AND target_user_id=$1
                AND created_at > (
                    SELECT COALESCE(
                        (SELECT created_at FROM premium_gift_logs 
                        WHERE action='premium_reset' AND target_user_id=$1 
                        ORDER BY created_at DESC LIMIT 1),
                        '1970-01-01'
                    )
                )
                ORDER BY created_at DESC LIMIT 1
                """,
                int(user_id)
            )

        if is_blacklisted_user:
            bl_badges = (
                "<:bl1:1263853643216584764>"
                "<:bl2:1263853966618394724>"
                "<:bl3:1263854236601552907>"
                "<:bl4:1263854052559552555>"
                "<:bl5:1263854267228356731>"
            )
            if is_donor:
                if premium_expiry:
                    expire = int(premium_expiry.timestamp())
                    premium_line = (
                        f"<:premium:1311062205650833509> **`Premium`**\n"
                        f"-# Premium expires <t:{expire}:f> (<t:{expire}:R>)"
                    )
                else:
                    premium_line = "<:premium:1311062205650833509> **`Premium`**"
                status_string = f"{bl_badges}\n\n{premium_line}"
            else:
                status_string = bl_badges
        else:
            statuses = []
            custom_title = await get_title(user.id)
            if custom_title:
                statuses.append(custom_title)
            if is_owner:
                statuses.append("<a:heistowner:1343768654357205105> **`Heist Owner`**")
            if fame_status:
                statuses.append("<:famous:1311067416251596870> **`Famous`**")
            if is_donor:
                if premium_expiry:
                    expire = int(premium_expiry.timestamp())
                    statuses.append(
                        f"<:premium:1311062205650833509> **`Premium`**\n"
                        f"-# Premium expires <t:{expire}:f> (<t:{expire}:R>)"
                    )
                else:
                    statuses.append("<:premium:1311062205650833509> **`Premium`**")
            else:
                statuses.append("<:heist:1391969039361904794> **`Standard`**")
            status_string = ", ".join(statuses)

        embed_user = discord.Embed(description=lastfm_info + status_string, color=await self.bot.get_color(ctx.author.id))
        embed_user.set_thumbnail(url=user.display_avatar.url)
        embed_user.set_author(name=f"{user_name} ; uid {hid}", icon_url=user.display_avatar.url)
        embed_user.set_footer(text=f"heist.lol • {user.id}", icon_url="https://git.cursi.ng/heist.png?a?")
        sepbyte = await makeseparator(self.bot, user.id)
        sep = discord.File(io.BytesIO(sepbyte), filename="separator.png")
        embed_user.set_image(url="attachment://separator.png")

        class StaffView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=120)
                self.state = "user"

            async def on_timeout(self):
                for c in self.children:
                    c.disabled = True
                with suppress(Exception):
                    await self.message.edit(view=self)

        view = StaffView()

        async def toggle_callback(interaction: discord.Interaction):
            if not await check_owner(self.bot, interaction.user.id):
                return await interaction.response.send_message("Only Heist staff can use this.", ephemeral=True)

            if view.state == "user":
                bl = await is_blacklisted(self.bot, int(user_id), "user")
                bl_text = ""
                if bl:
                    row = await self.bot.pool.fetchrow(
                        "SELECT information, moderator, date FROM blacklist WHERE user_id=$1",
                        int(user_id)
                    )
                    reason = row["information"] if row else "No reason provided."
                    mod_id = row["moderator"] if row else None
                    date = row["date"] if row else None
                    ts = int(date.timestamp()) if date else None
                    if ts:
                        bl_text = (
                            f"{lastfm_info}"
                            f"<:bl1:1263853643216584764>"
                            f"<:bl2:1263853966618394724>"
                            f"<:bl3:1263854236601552907>"
                            f"<:bl4:1263854052559552555>"
                            f"<:bl5:1263854267228356731>\n"
                            f"-# Blacklist reason: {reason} (by <@{mod_id}>, <t:{ts}:R>)"
                        )
                    else:
                        bl_text = (
                            f"{lastfm_info}"
                            f"<:bl1:1263853643216584764>"
                            f"<:bl2:1263853966618394724>"
                            f"<:bl3:1263854236601552907>"
                            f"<:bl4:1263854052559552555>"
                            f"<:bl5:1263854267228356731>\n"
                            f"-# Blacklist reason: {reason}"
                        )

                async with self.bot.pool.acquire() as conn:
                    redeemed_row = await conn.fetchrow(
                        """
                        SELECT code, target_user_id, actor_id
                        FROM premium_gift_logs
                        WHERE action='redeemed'
                        AND target_user_id=$1
                        AND created_at > (
                            SELECT COALESCE(
                                (SELECT created_at FROM premium_gift_logs 
                                WHERE action='premium_reset' AND target_user_id=$1 
                    ORDER BY created_at DESC LIMIT 1),
                                '1970-01-01'
                            )
                        )
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        int(user_id)
                    )

                if bl:
                    parts = [bl_text, ""]
                    if is_donor:
                        if premium_expiry:
                            expire = int(premium_expiry.timestamp())
                            parts.append(
                                f"<:premium:1311062205650833509> **`Premium`**\n"
                                f"-# Premium expires <t:{expire}:f> (<t:{expire}:R>)"
                            )
                        else:
                            parts.append("<:premium:1311062205650833509> **`Premium`**")
                        if redeemed_row:
                            parts.append(
                                f"-# Redeemed using **`{redeemed_row['code']}`** (from: {redeemed_row['actor_id']})"
                            )
                        else:
                            parts.append("-# Bought directly from Heist.")
                    embed_staff = discord.Embed(description="\n".join(parts), color=await self.bot.get_color(ctx.author.id))
                    embed_staff.set_thumbnail(url=user.display_avatar.url)
                    embed_staff.set_author(name=f"{user_name} ; uid {hid}", icon_url=user.display_avatar.url)
                    embed_staff.set_footer(text=f"heist.lol • {user.id}", icon_url="https://git.cursi.ng/heist.png?a?")
                    embed_staff.set_image(url="attachment://separator.png")
                    view.state = "staff"
                    return await interaction.response.edit_message(embed=embed_staff, view=view)

                parts = [lastfm_info + status_string]
                if redeemed_row:
                    parts.append(
                        f"-# Redeemed using **`{redeemed_row['code']}`** (from: {redeemed_row['actor_id']})"
                    )
                embed_staff = discord.Embed(description="\n".join(parts), color=await self.bot.get_color(ctx.author.id))
                embed_staff.set_thumbnail(url=user.display_avatar.url)
                embed_staff.set_author(name=f"{user_name} ; uid {hid}", icon_url=user.display_avatar.url)
                embed_staff.set_footer(text=f"heist.lol • {user.id}", icon_url="https://git.cursi.ng/heist.png?a?")
                embed_staff.set_image(url="attachment://separator.png")
                view.state = "staff"
                return await interaction.response.edit_message(embed=embed_staff, view=view)

            view.state = "user"
            return await interaction.response.edit_message(embed=embed_user, view=view)

        if await check_owner(self.bot, ctx.author.id):
            btn = discord.ui.Button(emoji="🕵️", style=discord.ButtonStyle.secondary)
            btn.callback = toggle_callback
            view.add_item(btn)

        sent = await ctx.send(embed=embed_user, file=sep, view=view)
        view.message = sent

    @app_commands.command()
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def invite(self, interaction: discord.Interaction):
        """Get Heist's invite link"""
        await interaction.response.send_message("https://discord.com/oauth2/authorize?client_id=1225070865935368265", ephemeral=True)
        return

    @app_commands.command()
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def plus(self, interaction: discord.Interaction):
        """Get Heist+ invite link"""
        if await AgeCheck.check(self.bot, interaction.user.id):
            await interaction.response.send_message("https://discord.com/oauth2/authorize?client_id=1340773265978949652", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="Age Check Required",
            description="**heist+** is only available to users aged **18+**.\nPlease set your age using the button below.",
            color=0xd3d6f1
        )
        
        view = AgeCheckView(self)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()

async def setup(bot):
    await bot.add_cog(Info(bot))