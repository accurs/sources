from __future__ import annotations

import io
import time
import requests
from datetime import timezone, datetime, timedelta
from pathlib import Path
from typing import Any
from re import match

import discord
from discord import app_commands
import psutil
from discord.ext import commands
from aiohttp import ClientSession
from PIL import Image
from colorthief import ColorThief
from discord.utils import format_dt

from bot.helpers.context import TormentContext
from bot.helpers.paginator import Paginator


class Information(commands.Cog):
    __cog_name__ = "information"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await self.bot.storage.pool.execute("""
            CREATE TABLE IF NOT EXISTS avatar_history (
                id         SERIAL PRIMARY KEY,
                user_id    BIGINT NOT NULL,
                avatar_url TEXT NOT NULL,
                saved_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

    @commands.Cog.listener("on_user_update")
    async def avatar_history_listener(self, before: discord.User, after: discord.User) -> None:
        if before.display_avatar.key == after.display_avatar.key:
            return
        url = str(after.display_avatar.replace(size=1024, format="png"))
        await self.bot.storage.pool.execute(
            "INSERT INTO avatar_history (user_id, avatar_url) VALUES ($1, $2)",
            after.id, url,
        )

    @commands.hybrid_command(
        name="avatar",
        aliases=["av", "pfp"],
        help="Display a user's avatar with download links",
        extras={"parameters": "user", "usage": "avatar [user]"},
    )
    @app_commands.describe(user="The user to view avatar for (optional)")
    async def avatar(self, ctx: TormentContext, *, user: discord.Member | discord.User = None) -> None:
        target = user or ctx.author
        avatar = target.display_avatar

        avatar_url = str(avatar.replace(size=4096))
        png_url = str(avatar.replace(format="png", size=4096))
        webp_url = str(avatar.replace(format="webp", size=4096))
        jpg_url = str(avatar.replace(format="jpeg", size=4096))

        try:
            async with ClientSession() as session:
                async with session.get(avatar_url) as resp:
                    if resp.status != 200:
                        return await ctx.warn("Failed to fetch avatar image!")
                    image_data = await resp.read()

            filename = f"{target.id}_avatar.png"
            file = discord.File(io.BytesIO(image_data), filename=filename)

            class AvatarView(discord.ui.LayoutView):
                container1 = discord.ui.Container(
                    discord.ui.TextDisplay(content=f"**{target.name}'s Avatar**"),
                    discord.ui.MediaGallery(
                        discord.MediaGalleryItem(
                            media=f"attachment://{filename}",
                        ),
                    ),
                    discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
                    discord.ui.ActionRow(
                        discord.ui.Button(
                            url=png_url,
                            style=discord.ButtonStyle.link,
                            label="PNG",
                        ),
                        discord.ui.Button(
                            url=webp_url,
                            style=discord.ButtonStyle.link,
                            label="WEBP",
                        ),
                        discord.ui.Button(
                            url=jpg_url,
                            style=discord.ButtonStyle.link,
                            label="JPG",
                        ),
                    ),
                )

            view = AvatarView()
            await ctx.send(view=view, file=file)
        except Exception as e:
            await ctx.warn(f"Failed to display avatar: {str(e)}")

    @commands.hybrid_command(
        name="banner",
        help="Display a user's banner with download links",
        extras={"parameters": "user", "usage": "banner [user]"},
    )
    @app_commands.describe(user="The user to view banner for (optional)")
    async def banner(self, ctx: TormentContext, *, user: discord.Member | discord.User = None) -> None:
        target = user or ctx.author

        if isinstance(target, discord.Member):
            target = await self.bot.fetch_user(target.id)

        if not target.banner:
            return await ctx.warn(f"**{target.name}** does not have a banner set!")

        banner = target.banner
        banner_url = str(banner.replace(size=4096))
        png_url = str(banner.replace(format="png", size=4096))
        webp_url = str(banner.replace(format="webp", size=4096))
        jpg_url = str(banner.replace(format="jpeg", size=4096))

        try:
            async with ClientSession() as session:
                async with session.get(banner_url) as resp:
                    if resp.status != 200:
                        return await ctx.warn("Failed to fetch banner image!")
                    image_data = await resp.read()

            filename = f"{target.id}_banner.png"
            file = discord.File(io.BytesIO(image_data), filename=filename)

            class BannerView(discord.ui.LayoutView):
                container1 = discord.ui.Container(
                    discord.ui.TextDisplay(content=f"**{target.name}'s Banner**"),
                    discord.ui.MediaGallery(
                        discord.MediaGalleryItem(
                            media=f"attachment://{filename}",
                        ),
                    ),
                    discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
                    discord.ui.ActionRow(
                        discord.ui.Button(
                            url=png_url,
                            style=discord.ButtonStyle.link,
                            label="PNG",
                        ),
                        discord.ui.Button(
                            url=webp_url,
                            style=discord.ButtonStyle.link,
                            label="WEBP",
                        ),
                        discord.ui.Button(
                            url=jpg_url,
                            style=discord.ButtonStyle.link,
                            label="JPG",
                        ),
                    ),
                )

            view = BannerView()
            await ctx.send(view=view, file=file)
        except Exception as e:
            await ctx.warn(f"Failed to display banner: {str(e)}")

    @commands.hybrid_command(
        name="userinfo",
        aliases=["ui", "whois"],
        help="Display detailed information about a user",
        extras={"parameters": "user", "usage": "userinfo [user]"},
    )
    @app_commands.describe(user="The user to view information for (optional)")
    async def userinfo(self, ctx: TormentContext, *, user: discord.Member | discord.User = None) -> None:
        target = user or ctx.author

        if isinstance(target, discord.Member):
            fetched_user = await self.bot.fetch_user(target.id)
        else:
            fetched_user = target
            if ctx.guild:
                target = ctx.guild.get_member(target.id) or target

        created_at = discord.utils.format_dt(target.created_at, style="R")
        created_full = discord.utils.format_dt(target.created_at, style="F")

        info_lines = [
            f"**User Information**",
            f"**Username:** {target.name}",
            f"**ID:** `{target.id}`",
            f"**Created:** {created_at} ({created_full})",
        ]

        if isinstance(target, discord.Member) and ctx.guild:
            joined_at = discord.utils.format_dt(target.joined_at, style="R") if target.joined_at else "Unknown"
            joined_full = discord.utils.format_dt(target.joined_at, style="F") if target.joined_at else "Unknown"

            roles = [f"<@&{role.id}>" for role in target.roles if role.name != "@everyone"]
            roles_text = ", ".join(roles[:10]) if roles else "None"
            if len(roles) > 10:
                roles_text += f" (+{len(roles) - 10} more)"

            info_lines.extend([
                f"",
                f"**Server Information**",
                f"**Joined:** {joined_at} ({joined_full})",
                f"**Roles [{len(roles)}]:** {roles_text}",
            ])

            if target.premium_since:
                boosting_since = discord.utils.format_dt(target.premium_since, style="R")
                info_lines.append(f"**Boosting Since:** {boosting_since}")

        try:
            avatar_url = str(target.display_avatar.replace(size=1024))
            async with ClientSession() as session:
                async with session.get(avatar_url) as resp:
                    if resp.status != 200:
                        return await ctx.warn("Failed to fetch user avatar!")
                    avatar_data = await resp.read()

            filename = f"{target.id}_userinfo.png"
            file = discord.File(io.BytesIO(avatar_data), filename=filename)

            avatar_png = str(target.display_avatar.replace(format="png", size=4096))
            avatar_webp = str(target.display_avatar.replace(format="webp", size=4096))
            avatar_jpg = str(target.display_avatar.replace(format="jpeg", size=4096))

            class UserinfoView(discord.ui.LayoutView):
                container1 = discord.ui.Container(
                    discord.ui.TextDisplay(content=f"**{target.name}**"),
                    discord.ui.MediaGallery(
                        discord.MediaGalleryItem(
                            media=f"attachment://{filename}",
                        ),
                    ),
                    discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
                    discord.ui.TextDisplay(content="\n".join(info_lines)),
                    discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
                    discord.ui.ActionRow(
                        discord.ui.Button(
                            url=avatar_png,
                            style=discord.ButtonStyle.link,
                            label="Avatar PNG",
                        ),
                        discord.ui.Button(
                            url=avatar_webp,
                            style=discord.ButtonStyle.link,
                            label="Avatar WEBP",
                        ),
                        discord.ui.Button(
                            url=avatar_jpg,
                            style=discord.ButtonStyle.link,
                            label="Avatar JPG",
                        ),
                    ),
                )

            view = UserinfoView()
            await ctx.send(view=view, file=file, allowed_mentions=discord.AllowedMentions.none())
        except Exception as e:
            await ctx.warn(f"Failed to display user info: {str(e)}")

    @commands.hybrid_command(
        name="serverinfo",
        aliases=["si", "guildinfo", "guild"],
        help="Display detailed information about the server",
        extras={"parameters": "n/a", "usage": "serverinfo"},
    )
    async def serverinfo(self, ctx: TormentContext) -> None:
        if not ctx.guild:
            return await ctx.warn("This command can only be used in a server!")

        guild = ctx.guild
        premium_tier = guild.premium_tier
        if premium_tier == 0:
            role_limit = 250
        elif premium_tier == 1:
            role_limit = 250
        elif premium_tier == 2:
            role_limit = 500
        elif premium_tier == 3:
            role_limit = 2500

        embed = discord.Embed(
            title=f"{guild.name}",
            description=f"Server created on {format_dt(guild.created_at, 'D')} ({format_dt(guild.created_at, 'R')})",
            color=discord.Color.from_str("#9FAB85"),
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        embed.set_author(
            name=ctx.author.display_name,
            icon_url=ctx.author.display_avatar.url,
        )
        
        embed.add_field(
            name="Owner",
            value=f"{guild.owner.mention} \n({guild.owner.id})",
            inline=True,
        )
        embed.add_field(
            name="Members",
            value=f"**Total:** {guild.member_count} \n**Humans:** {sum(1 for member in guild.members if not member.bot)} \n**Bots:** {sum(1 for member in guild.members if member.bot)}",
            inline=True,
        )
        embed.add_field(
            name="Information",
            value=f"**Verification:** {guild.verification_level} \n**Boosts:** {guild.premium_subscription_count}",
            inline=True,
        )
        embed.add_field(
            name="Design",
            value=f"**Splash:** [click here]({guild.splash.url if guild.splash else 'https://none.none'}) \n**Banner:** [click here]({guild.banner.url if guild.banner else 'https://none.none'}) \n**Icon:** [click here]({guild.icon.url if guild.icon else 'https://none.none'})",
            inline=True,
        )
        embed.add_field(
            name=f"Channels ({len(guild.channels)})",
            value=f"**Text:** {len(guild.text_channels)} \n**Voice:** {len(guild.voice_channels)} \n**Categories:** {len(guild.categories)}",
            inline=True,
        )
        embed.add_field(
            name="Counts",
            value=f"**Roles:** {len(guild.roles)}/{role_limit} \n**Emojis:** {len(guild.emojis)}/{guild.emoji_limit} \n**Boosters:** {len(guild.premium_subscribers)}",
            inline=True,
        )
        
        return await ctx.send(embed=embed)

    @commands.command(
        name="inviteinfo",
        aliases=["ii"],
        help="Get information about a guild using their invite code",
        extras={"parameters": "invite", "usage": "inviteinfo (invite)"},
    )
    async def inviteinfo(self, ctx: TormentContext, *, invite: discord.Invite = None) -> None:
        if invite is None:
            return await ctx.warn("An `invite code` is missing.")

        embed = discord.Embed(
            title=f"Invite code: {invite.code}",
            color=discord.Color.from_str("#9FAB85"),
        )
        
        embed.set_author(
            name=ctx.author.name,
            icon_url=ctx.author.display_avatar.url,
        )
        
        if invite.guild and invite.guild.icon:
            embed.set_thumbnail(url=invite.guild.icon.url)
        
        embed.add_field(
            name="Channel & Invite",
            value=f"**Name:** {invite.channel.name} (`text`) \n**ID:** `{invite.channel.id}` \n**Created**: {format_dt(invite.created_at, 'F') if invite.created_at else 'Unknown'} ({format_dt(invite.created_at, 'R') if invite.created_at else ''}) \n**Invite Expiration:** {format_dt(invite.expires_at) if invite.expires_at else 'Never'} \n**Inviter:** {invite.inviter if invite.inviter else 'Vanity URL'} \n **Temporary:** {invite.temporary if invite.temporary else 'N/A'} \n**Usage:** {invite.uses}",
            inline=True,
        )
        embed.add_field(
            name="Guild",
            value=f"**Name:** {invite.guild.name} \n**ID:** `{invite.guild.id}` \n**Created:** {format_dt(invite.guild.created_at, 'F')} ({format_dt(invite.guild.created_at, 'R')}) \n**Members:** {invite.approximate_member_count: ,} \n**Online Members:** {invite.approximate_presence_count: ,} \n**Verification Level:** {invite.guild.verification_level}",
            inline=True,
        )
        
        view = discord.ui.View()
        if invite.guild:
            if invite.guild.icon:
                view.add_item(discord.ui.Button(label="Icon", emoji="🖼️", url=invite.guild.icon.url))
            if invite.guild.splash:
                view.add_item(discord.ui.Button(label="Splash", emoji="🎨", url=invite.guild.splash.url))
            if invite.guild.banner:
                view.add_item(discord.ui.Button(label="Banner", emoji="🏳️", url=invite.guild.banner.url))
        
        return await ctx.send(embed=embed, view=view if view.children else None)

    @commands.command(
        name="hex",
        aliases=["dominant"],
        help="Get a hex code from an image",
        extras={"parameters": "user", "usage": "hex [user]"},
    )
    async def hex(self, ctx: TormentContext, *, user: discord.User = None) -> None:
        user = user or ctx.author
        image_url = None

        if ctx.message.attachments:
            image_url = ctx.message.attachments[0].url
        elif user.display_avatar:
            image_url = user.display_avatar.url
        else:
            image_url = ctx.author.display_avatar.url

        async with ctx.typing():
            try:
                response = requests.get(image_url)
                image_bytes = io.BytesIO(response.content)
                image = Image.open(image_bytes)
                color_thief = ColorThief(image_bytes)
                dominant = color_thief.get_color(quality=1)
                hex_discord = int("0x{:02x}{:02x}{:02x}".format(*dominant), 16)
                hex_code = "#{:02x}{:02x}{:02x}".format(*dominant)

                embed = discord.Embed(
                    title=f"Showing hex code: {hex_code}",
                    color=discord.Color(hex_discord),
                )
                embed.add_field(name="RGB Value", value=f"{dominant}")
                
                return await ctx.send(embed=embed)
            except Exception as e:
                return await ctx.warn(f"An error occurred: `{e}`")

    @commands.command(
        name="botinfo",
        aliases=["bi", "about"],
        help="View information about torment",
        extras={"parameters": "n/a", "usage": "botinfo"},
    )
    async def botinfo(self, ctx: TormentContext) -> None:
        total_users = sum(g.member_count or 0 for g in self.bot.guilds)
        total_servers = len(self.bot.guilds)

        def count_commands(cmds):
            total = 0
            for cmd in cmds:
                total += 1
                if isinstance(cmd, commands.Group):
                    total += count_commands(cmd.commands)
            return total

        total_commands = count_commands(self.bot.commands)

        import os
        total_lines = 0
        skip_dirs = {"__pycache__", ".git", "venv", ".venv", "node_modules"}
        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in skip_dirs and os.path.join(root, d).replace("\\", "/") != "./bot/helpers"]
            for file in files:
                if file.endswith(".py"):
                    try:
                        with open(os.path.join(root, file), "r", encoding="utf-8", errors="ignore") as f:
                            total_lines += sum(1 for _ in f)
                    except Exception:
                        pass

        cpu_usage = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        mem_used_bytes = mem.used
        if mem_used_bytes >= 1024 ** 3:
            mem_used_str = f"{round(mem_used_bytes / (1024 ** 3), 2)}GiB"
        else:
            mem_used_str = f"{round(mem_used_bytes / (1024 ** 2), 2)}MiB"

        bot_created_ts = discord.utils.format_dt(self.bot.user.created_at, style="R")
        start_time = getattr(self.bot, "start_time", datetime.now(tz=timezone.utc))
        startup_ts = discord.utils.format_dt(start_time, style="R")

        header_text = (
            f"# [torment](https://torment.lat)\n"
            f"Developed and maintained by [**rain**](https://discord.com/users/1460003194771083296) "
            f"& [**zen**](https://discord.com/users/1285277569113133161).\n"
            f"-# Utilizing `{total_commands}` commands with `{total_lines}` lines"
        )

        info_text = (
            f"<:info:1480243883664474303> **Bot**\n"
            f"> **Users**: `{total_users}`\n"
            f"> **Servers**: `{total_servers}`\n"
            f"> **Created**: {bot_created_ts}\n\n"
            f"<:info:1480243883664474303> **System**\n"
            f"> **CPU**: `{cpu_usage}%`\n"
            f"> **Memory**: `{mem_used_str}`\n"
            f"> **Started**: {startup_ts}"
        )

        class BotInfoView(discord.ui.LayoutView):
            container1 = discord.ui.Container(
                discord.ui.Section(
                    discord.ui.TextDisplay(content=header_text),
                    accessory=discord.ui.Thumbnail(
                        media="https://cdn.discordapp.com/attachments/1479938152662700092/1481681136097689670/1479559891680235610_avatar.png?ex=69b43297&is=69b2e117&hm=9ef8dd6857fc19ef13ebec545d5d7a743c8f8d866ddcaa0ce84b66756218f767&",
                    ),
                ),
                discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
                discord.ui.TextDisplay(content=info_text),
                discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
                discord.ui.ActionRow(
                    discord.ui.Button(
                        url="https://discordapp.com/oauth2/authorize?client_id=1479559891680235610&scope=bot+applications.commands&permissions=8",
                        style=discord.ButtonStyle.link,
                        label="Invite",
                    ),
                    discord.ui.Button(
                        url="https://torment.lat/",
                        style=discord.ButtonStyle.link,
                        label="Website",
                    ),
                    discord.ui.Button(
                        url="https://discord.gg/b7VV2mpQSw",
                        style=discord.ButtonStyle.link,
                        label="Support Server",
                    ),
                ),
            )

        view = BotInfoView()
        await ctx.send(view=view, allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(
        name="invite",
        aliases=["inv"],
        help="Get the bot's invite link",
        extras={"parameters": "n/a", "usage": "invite"},
    )
    async def invite(self, ctx: TormentContext) -> None:
        permissions = discord.Permissions(
            administrator=True
        )
        invite_url = discord.utils.oauth_url(
            self.bot.user.id,
            permissions=permissions,
            scopes=["bot", "applications.commands"]
        )

        class InviteView(discord.ui.LayoutView):
            text_display1 = discord.ui.TextDisplay(
                content="Note that Torment is still in beta."
            )

            action_row1 = discord.ui.ActionRow(
                discord.ui.Button(
                    url=invite_url,
                    style=discord.ButtonStyle.link,
                    label="Invite Torment",
                ),
            )

        view = InviteView()
        await ctx.send(view=view)

    @commands.command(
        name="newmembers",
        aliases=["newusers", "nm"],
        help="View the most recently joined members",
        extras={"parameters": "[amount]", "usage": "newmembers [amount]"},
    )
    async def newmembers(self, ctx: TormentContext, amount: int = 10) -> None:
        if not ctx.guild:
            return
        amount = max(1, min(amount, 50))
        members = sorted(
            [m for m in ctx.guild.members if m.joined_at],
            key=lambda m: m.joined_at,
            reverse=True,
        )[:amount]

        lines = [
            f"`{i:02}` {m.mention} — joined {format_dt(m.joined_at, 'R')}"
            for i, m in enumerate(members, 1)
        ]
        embed = discord.Embed(
            title=f"Newest Members",
            color=discord.Color.from_str("#9FAB85"),
        )
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        from bot.helpers.paginator import Paginator
        paginator = Paginator(ctx, lines, embed)
        await paginator.start()

    @commands.command(
        name="bans",
        help="View all banned users in the server",
        extras={"parameters": "n/a", "usage": "bans"},
    )
    @commands.has_permissions(ban_members=True)
    async def bans(self, ctx: TormentContext) -> None:
        if not ctx.guild:
            return
        ban_list = [entry async for entry in ctx.guild.bans()]
        if not ban_list:
            return await ctx.warn("There are no banned users in this guild.")

        lines = [
            f"`{i:02}` **{entry.user}** (`{entry.user.id}`)"
            + (f" — *{entry.reason}*" if entry.reason else "")
            for i, entry in enumerate(ban_list, 1)
        ]
        embed = discord.Embed(
            title=f"Bans ({len(ban_list)})",
            color=discord.Color.from_str("#9FAB85"),
        )
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        from bot.helpers.paginator import Paginator
        paginator = Paginator(ctx, lines, embed)
        await paginator.start()

    @commands.Cog.listener("on_message")
    async def seen_listener(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        await self.bot.storage.pool.execute(
            """
            INSERT INTO seen (guild_id, user_id, seen_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (guild_id, user_id) DO UPDATE SET seen_at = NOW()
            """,
            message.guild.id, message.author.id,
        )

    @commands.command(
        name="seen",
        help="Check when a member was last active in the server",
        extras={"parameters": "member", "usage": "seen (member)"},
    )
    async def seen(self, ctx: TormentContext, *, member: discord.Member) -> None:
        if not ctx.guild:
            return
        row = await self.bot.storage.pool.fetchrow(
            "SELECT seen_at FROM seen WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id,
        )
        if not row:
            return await ctx.warn(f"{member.mention} has not been seen in this server yet.")
        embed = discord.Embed(
            description=f"{member.mention} was last seen {format_dt(row['seen_at'], 'R')} ({format_dt(row['seen_at'], 'F')})",
            color=discord.Color.from_str("#9FAB85"),
        )
        await ctx.send(embed=embed)


    @commands.hybrid_command(
        name="firstmessage",
        help="Get a link to the first message in a channel",
        extras={"parameters": "channel", "usage": "firstmessage [channel]"},
    )
    @app_commands.describe(channel="The channel to get the first message from")
    async def firstmessage(self, ctx: TormentContext, channel: discord.TextChannel = None) -> None:
        channel = channel or ctx.channel
        async for message in channel.history(limit=1, oldest_first=True):
            embed = discord.Embed(
                description=f"The first message in {channel.mention} was sent by {message.author.mention} {format_dt(message.created_at, 'R')}",
                color=discord.Color.from_str("#9FAB85"),
            )
            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="Jump to Message",
                url=message.jump_url,
            ))
            return await ctx.send(embed=embed, view=view)
        await ctx.warn(f"No messages found in {channel.mention}.")

    @commands.hybrid_command(
        name="invites",
        help="List all active invites in the server",
        extras={"parameters": "n/a", "usage": "invites"},
    )
    @commands.has_permissions(manage_guild=True)
    async def invites(self, ctx: TormentContext) -> None:
        if not ctx.guild:
            return
        guild_invites = await ctx.guild.invites()
        if not guild_invites:
            return await ctx.warn("This server has no active invites.")

        entries = []
        for inv in guild_invites:
            if inv.max_age == 0:
                expires = "**Never**"
            else:
                from datetime import timedelta
                expires_at = inv.created_at + timedelta(seconds=inv.max_age)
                expires = f"in {format_dt(expires_at, 'R').replace('in ', '')}"
                expires = format_dt(expires_at, "R")
            entries.append(f"**{inv.code}** expires {expires}")

        embed = discord.Embed(
            title="Server Invites",
            color=discord.Color.from_str("#9FAB85"),
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        paginator = Paginator(ctx, entries, embed=embed, per_page=10, counter=True)
        await paginator.start()

    @commands.hybrid_command(
        name="permissions",
        aliases=["perms"],
        help="Show a member's permissions in the current channel",
        extras={"parameters": "member", "usage": "permissions [member]"},
    )
    @app_commands.describe(member="The member to check permissions for")
    async def permissions(self, ctx: TormentContext, member: discord.Member = None) -> None:
        member = member or ctx.author
        perms = member.guild_permissions
        allowed = [f"`{p.replace('_', ' ').title()}`" for p, v in perms if v]
        denied = [f"`{p.replace('_', ' ').title()}`" for p, v in perms if not v]
        embed = discord.Embed(color=discord.Color.from_str("#9FAB85"))
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        if allowed:
            embed.add_field(name="Allowed", value=", ".join(allowed), inline=False)
        if denied:
            embed.add_field(name="Denied", value=", ".join(denied), inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="channelinfo",
        help="View detailed information about a channel",
        extras={"parameters": "channel", "usage": "channelinfo [channel]"},
    )
    @app_commands.describe(channel="The channel to get info for")
    async def channelinfo(self, ctx: TormentContext, channel: discord.abc.GuildChannel = None) -> None:
        channel = channel or ctx.channel
        embed = discord.Embed(color=discord.Color.from_str("#9FAB85"))
        embed.set_author(name=f"{channel.name} ({channel.id})")

        ch_type = type(channel).__name__.replace("Channel", "").replace("Thread", "Thread")
        created = format_dt(channel.created_at, "F")
        created_rel = format_dt(channel.created_at, "R")

        general_lines = [
            f"**Type**: {ch_type}",
            f"**Created**: {created} ({created_rel})",
        ]
        embed.add_field(
            name="General",
            value="> " + "\n> ".join(general_lines),
            inline=True,
        )

        guild_line = f"**Guild**: {channel.guild.name} ({channel.guild.id})"
        category_line = f"**Category**: {channel.category.name} ({channel.category.id})" if channel.category else "**Category**: None"
        embed.add_field(
            name="Location",
            value="> " + "\n> ".join([guild_line, category_line]),
            inline=True,
        )

        if isinstance(channel, discord.TextChannel):
            settings_lines = [
                f"**NSFW**: {'Yes' if channel.is_nsfw() else 'No'}",
                f"**Slowmode**: {channel.slowmode_delay}s",
                f"**News Channel**: {'Yes' if channel.is_news() else 'No'}",
                f"**Position**: {channel.position}",
            ]
            embed.add_field(
                name="Settings",
                value="> " + "\n> ".join(settings_lines),
                inline=False,
            )
            if channel.topic:
                embed.add_field(name="Topic", value=channel.topic, inline=False)

        elif isinstance(channel, discord.VoiceChannel):
            settings_lines = [
                f"**Bitrate**: {channel.bitrate // 1000}kbps",
                f"**User Limit**: {channel.user_limit or 'Unlimited'}",
                f"**Position**: {channel.position}",
            ]
            embed.add_field(
                name="Settings",
                value="> " + "\n> ".join(settings_lines),
                inline=False,
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="roleinfo",
        help="View detailed information about a role",
        extras={"parameters": "role", "usage": "roleinfo (role)"},
    )
    @app_commands.describe(role="The role to get info for")
    async def roleinfo(self, ctx: TormentContext, *, role: discord.Role) -> None:
        perms = [p.replace("_", " ").title() for p, v in role.permissions if v]
        embed = discord.Embed(color=role.color if role.color.value else discord.Color.from_str("#9FAB85"))
        embed.set_author(name=f"{role.name} ({role.id})")
        embed.add_field(name="Created", value=f"{format_dt(role.created_at, 'F')} ({format_dt(role.created_at, 'R')})", inline=False)
        embed.add_field(name="Members", value=str(len(role.members)), inline=True)
        embed.add_field(name="Mentionable", value="Yes" if role.mentionable else "No", inline=True)
        embed.add_field(name="Hoisted", value="Yes" if role.hoist else "No", inline=True)
        embed.add_field(name="Position", value=str(role.position), inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        if perms:
            embed.add_field(name="Key Permissions", value=", ".join(f"`{p}`" for p in perms[:15]), inline=False)
        await ctx.send(embed=embed)

    @commands.group(
        name="avatarhistory",
        aliases=["avh"],
        invoke_without_command=True,
        help="View a user's avatar history",
        extras={"parameters": "user", "usage": "avatarhistory [user]"},
    )
    async def avatarhistory(self, ctx: TormentContext, *, user: discord.User = None) -> None:
        target = user or ctx.author
        rows = await self.bot.storage.pool.fetch(
            "SELECT avatar_url, saved_at FROM avatar_history WHERE user_id = $1 ORDER BY saved_at DESC",
            target.id,
        )
        if not rows:
            return await ctx.warn(f"No avatar history found for **{target.name}**.")

        pages: list[discord.Embed] = []
        total = len(rows)
        for i, row in enumerate(rows, 1):
            embed = discord.Embed(
                title=f"{target.name}'s avatar history",
                color=discord.Color.from_str("#9FAB85"),
            )
            embed.set_author(name=target.name, icon_url=target.display_avatar.url)
            embed.set_image(url=row["avatar_url"])
            embed.set_footer(text=f"Page {i}/{total}")
            pages.append(embed)

        await ctx.paginate(pages)

    @avatarhistory.command(
        name="reset",
        help="Reset your avatar history",
        extras={"parameters": "n/a", "usage": "avatarhistory reset"},
    )
    async def avatarhistory_reset(self, ctx: TormentContext) -> None:
        deleted = await self.bot.storage.pool.fetchval(
            "WITH d AS (DELETE FROM avatar_history WHERE user_id = $1 RETURNING 1) SELECT COUNT(*) FROM d",
            ctx.author.id,
        )
        if not deleted:
            return await ctx.warn("You have no avatar history to reset.")
        await ctx.success(f"Cleared **{deleted}** avatar{'s' if deleted != 1 else ''} from your history.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Information(bot))
