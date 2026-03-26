import discord
from discord.ext import commands
from stare.core.config import Config
from stare.core.tools.context import CustomContext as Context
from datetime import datetime
import aiohttp
from typing import Optional


class Information(commands.Cog):
    """Information commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name="botinfo", aliases=["bi", "about", "info"])
    async def botinfo(self, ctx: Context):
        """Shows information about the bot"""
        import psutil
        import os
        
        # Calculate stats
        total_users = sum(guild.member_count for guild in self.bot.guilds)
        total_guilds = len(self.bot.guilds)
        
        # Count all commands including subcommands
        total_commands = 0
        
        # Iterate through cogs
        for cog_name, cog in self.bot.cogs.items():
            # Skip jishaku and API
            if cog_name.lower() in ['jishaku', 'api']:
                continue
            
            # Get the module path to determine folder/category
            module_path = cog.__module__
            if 'stare.plugins.' in module_path:
                parts = module_path.split('.')
                if len(parts) >= 3:
                    category = parts[2].capitalize()
                    # Skip developer folder
                    if category.lower() == 'developer':
                        continue
            
            # Count commands from this cog
            for cmd in cog.get_commands():
                if cmd.hidden:
                    continue
                
                total_commands += 1
                
                # Count subcommands if it's a group
                if isinstance(cmd, commands.Group):
                    for subcmd in cmd.commands:
                        if not subcmd.hidden:
                            total_commands += 1
        
        total_modules = len(self.bot.extensions)
        
        # Calculate latency
        latency = round(self.bot.latency * 1000)
        
        # Get RAM usage
        process = psutil.Process(os.getpid())
        ram_mb = round(process.memory_info().rss / 1024 / 1024, 2)
        
        # Get latest commit from GitHub
        commit_id = "unknown"
        commit_url = "https://github.com/StareServices/stare/commits/main"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.github.com/repos/StareServices/stare/commits/main",
                    headers={"Accept": "application/vnd.github+json"}
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        commit_id = data["sha"][:7]
                        commit_url = data["html_url"]
                    else:
                        # Fallback: try listing commits
                        async with session.get(
                            "https://api.github.com/repos/StareServices/stare/commits?per_page=1",
                            headers={"Accept": "application/vnd.github+json"}
                        ) as resp2:
                            if resp2.status == 200:
                                data2 = await resp2.json()
                                if data2:
                                    commit_id = data2[0]["sha"][:7]
                                    commit_url = data2[0]["html_url"]
        except Exception:
            pass
        
        # Build Components v2 payload
        payload = {
            "flags": 32768,
            "components": [
                {
                    "type": 17,
                    "components": [
                        {
                            "type": 10,
                            "content": "<:bot_information:1475693652364886172> **stare** is developed and maintained by [**cal**](https://github.com/4tsx), [**rep**](https://rep.rest) & [**zen**](https://github.com/offermillions)"
                        },
                        {
                            "type": 14
                        },
                        {
                            "type": 9,
                            "components": [
                                {
                                    "type": 10,
                                    "content": f"**Statistics** \n> **{total_users:,}** users \n> **{total_guilds}** guilds \n> **{total_commands}** commands \n\n**System** \n> Latency: **{latency}ms** \n> Discord.py: **2.6.4** \n> RAM: `{ram_mb}MiB` \n\n**GitHub**   \n> Branch: **Main**\n> Repository: [`StareServices/stare`](https://github.com/StareServices/stare) \n> Latest Commit: **[{commit_id}]({commit_url})**  \n"
                                }
                            ],
                            "accessory": {
                                "type": 11,
                                "media": {
                                    "url": str(self.bot.user.display_avatar.url)
                                }
                            }
                        },
                        {
                            "type": 14
                        },
                        {
                            "type": 10,
                            "content": f"-# **{total_modules}** modules across **{total_commands}** commands"
                        },
                        {
                            "type": 1,
                            "components": [
                                {
                                    "type": 2,
                                    "style": 5,
                                    "url": "https://stare.lat",
                                    "label": "Website"
                                },
                                {
                                    "type": 2,
                                    "style": 5,
                                    "url": "https://discordapp.com/oauth2/authorize?client_id=1472023540227117322&scope=bot+applications.commands&permissions=8",
                                    "label": "Invite"
                                },
                                {
                                    "type": 2,
                                    "style": 5,
                                    "url": "https://discord.gg/starebot",
                                    "label": "Support"
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        # Send via HTTP since discord.py doesn't support Components v2
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bot {self.bot.http.token}",
                "Content-Type": "application/json"
            }
            url = f"https://discord.com/api/v10/channels/{ctx.channel.id}/messages"
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"Components v2 failed with status {resp.status}: {error_text}")
    
    @commands.command(name="serverinfo", aliases=["si", "server", "guildinfo", "gi"])
    async def serverinfo(self, ctx: Context):
        """Shows information about the server"""
        guild = ctx.guild
        
        if not guild:
            return await ctx.send("This command can only be used in a server!")
        
        # Get channel counts
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        
        # Get member counts
        total_members = guild.member_count
        humans = len([m for m in guild.members if not m.bot])
        bots = len([m for m in guild.members if m.bot])
    
        # Get other stats
        total_roles = len(guild.roles)
        total_emojis = len(guild.emojis)
        emoji_limit = guild.emoji_limit
        total_stickers = len(guild.stickers)
        sticker_limit = guild.sticker_limit
        
        # Get creation timestamp
        created_timestamp = int(guild.created_at.timestamp())
        
        # Get shard ID
        shard_id = guild.shard_id if guild.shard_id is not None else 0
        
        # Create embed
        embed = discord.Embed(
            title=guild.name,
            description=f"-# <:s_info:1475695155544592404> __{ctx.guild.name}__ is running on **Shard ID: {shard_id}** \n>>> **Owner**: {guild.owner.mention if guild.owner else 'Unknown'} \n**Created**: <t:{created_timestamp}:R>",
            color=Config.COLORS.DEFAULT
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        embed.add_field(
            name="Channels",
            value=f"> **Text**: `{text_channels}` \n> **Voice**: `{voice_channels}` \n> **Categories**: `{categories}`",
            inline=True
        )
        
        embed.add_field(
            name="Members",
            value=f"> **Total**: `{total_members:,}` \n> **Humans**: `{humans:,}` \n> **Bots**: `{bots:,}`",
            inline=True
        )
        
        embed.add_field(
            name="Extra",
            value=f"> **Roles**: `{total_roles}`\n> **Emojis**: `{total_emojis}/{emoji_limit}`\n> **Stickers**: `{total_stickers}/{sticker_limit}`",
            inline=True
        )
        
        if guild.banner:
            embed.set_image(url=guild.banner.url)
        
        embed.set_footer(text=f"Server ID: {guild.id}")
        
        await ctx.send(embed=embed)
    
    @commands.command(name="inviteinfo", aliases=["ii"])
    async def inviteinfo(self, ctx: Context, invite_code: str):
        """Shows information about an invite"""
        try:
            invite = await self.bot.fetch_invite(invite_code, with_counts=True)
        except discord.NotFound:
            return await ctx.warn("Invalid invite code")
        except discord.HTTPException:
            return await ctx.warn("Failed to fetch invite")
        
        guild = invite.guild
        inviter = invite.inviter
        channel = invite.channel
        
        # Build description
        desc = "**Invite Info**\n\n"
        desc += "**Invite:**\n"
        desc += f"> Channel: {channel.mention if hasattr(channel, 'mention') else channel.name}\n"
        desc += f"> Inviter: {inviter.mention if inviter else 'Unknown'}\n\n"
        desc += "**Design:**\n"
        desc += f"> Icon: [Click here]({guild.icon.url})\n" if guild.icon else "> Icon: N/A\n"
        desc += f"> Banner: [Click here]({guild.banner.url})\n" if guild.banner else "> Banner: N/A\n"
        desc += f"> Splash: [Click here]({guild.splash.url})\n" if guild.splash else "> Splash: N/A\n"
        desc += f"\nInvite: `{invite.code}`"
        
        e = discord.Embed(
            description=desc,
            color=2303786
        )
        
        e.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        
        if guild.icon:
            e.set_thumbnail(url=guild.icon.url)
        
        # Add guild field
        guild_value = f"> Server name: **{guild.name}**\n"
        guild_value += f"> All Members: **{invite.approximate_member_count or 'Unknown'}**"
        e.add_field(name="Guild", value=guild_value, inline=True)
        
        await ctx.send(embed=e)

    @commands.command(name="userinfo", aliases=["ui"])
    @commands.guild_only()
    async def userinfo(self, ctx: Context, *, member: Optional[discord.Member] = None):
        """Shows information about a user"""
        member = member or ctx.author

        joined_ts = int(member.joined_at.timestamp()) if member.joined_at else None
        created_ts = int(member.created_at.timestamp())

        # Status
        status_map = {
            discord.Status.online: "Online",
            discord.Status.idle: "Idle",
            discord.Status.dnd: "Do Not Disturb",
            discord.Status.offline: "Offline",
        }
        user_status = status_map.get(member.status, "Offline")

        # Custom status shown in description instead of plain status
        custom_status = None
        for a in member.activities:
            if isinstance(a, discord.CustomActivity) and a.name:
                custom_status = a.name
                break

        description_text = f"<:information:1475693202626445322> `{custom_status if custom_status else user_status}`"

        # Roles (excluding @everyone, reversed so highest is first, max 10)
        roles = [r for r in reversed(member.roles) if r.name != "@everyone"]
        role_count = len(roles)
        roles_display = " ".join(r.mention for r in roles[:10])
        if not roles_display:
            roles_display = "No roles"

        # Activities — exclude CustomActivity, only real activities
        activity_parts = []
        for a in member.activities:
            if isinstance(a, discord.CustomActivity):
                continue
            elif isinstance(a, discord.Spotify):
                activity_parts.append(f"Listening to **{a.title}** by **{a.artist}**")
            elif isinstance(a, discord.Game):
                activity_parts.append(f"Playing **{a.name}**")
            elif isinstance(a, discord.Streaming):
                activity_parts.append(f"Streaming **{a.name}**")
            elif isinstance(a, discord.Activity):
                if a.type == discord.ActivityType.playing:
                    activity_parts.append(f"Playing **{a.name}**")
                elif a.type == discord.ActivityType.watching:
                    activity_parts.append(f"Watching **{a.name}**")
                elif a.type == discord.ActivityType.listening:
                    activity_parts.append(f"Listening to **{a.name}**")
                elif a.type == discord.ActivityType.competing:
                    activity_parts.append(f"Competing in **{a.name}**")
                elif a.name:
                    activity_parts.append(f"**{a.name}**")

        activity_value = " and ".join(activity_parts) if activity_parts else "None"

        embed = discord.Embed(
            description=description_text,
            color=0xFFFFFF
        )

        embed.set_author(
            name=f"{member.name} ({member.id})",
            icon_url=member.display_avatar.url
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        if joined_ts:
            embed.add_field(
                name="Joined",
                value=f"<t:{joined_ts}:D>\n<t:{joined_ts}:R>",
                inline=True
            )
        else:
            embed.add_field(name="Joined", value="Unknown", inline=True)

        embed.add_field(
            name="Created",
            value=f"<t:{created_ts}:D>\n<t:{created_ts}:R>",
            inline=True
        )

        embed.add_field(
            name=f"Roles ({role_count})",
            value=roles_display,
            inline=True
        )

        embed.add_field(
            name="Activity",
            value=activity_value,
            inline=False
        )

        # Join position
        sorted_members = sorted(
            [m for m in ctx.guild.members if m.joined_at],
            key=lambda m: m.joined_at
        )
        join_position = sorted_members.index(member) + 1 if member in sorted_members else "?"

        embed.set_footer(text=f"Join position: {join_position} • {ctx.guild.name}")

        await ctx.send(embed=embed)
    
    @commands.command(name="avatar", aliases=["av", "pfp"])
    async def avatar(self, ctx: Context, member: discord.User = None):
        m = member or ctx.author
        e = discord.Embed(
            color=Config.COLORS.DEFAULT,
            title=f"{m.name}'s avatar",
            url=m.display_avatar.url
        )
        e.set_image(url=m.display_avatar.url)
        await ctx.send(embed=e)
    
    @commands.command(name="banner")
    async def banner(self, ctx: Context, member: discord.User = None):
        m = member or ctx.author
        user = await self.bot.fetch_user(m.id)
        
        if not user.banner:
            return await ctx.warn("No banner found")
        
        e = discord.Embed(
            color=Config.COLORS.DEFAULT,
            title=f"{m.name}'s banner",
            url=user.banner.url
        )
        e.set_image(url=user.banner.url)
        await ctx.send(embed=e)
    
    @commands.command(name="roles")
    async def roles(self, ctx: Context):
        roles = sorted(ctx.guild.roles[1:], reverse=True)
        embeds = []
        chunk_size = 10
        
        for i in range(0, len(roles), chunk_size):
            chunk = roles[i:i + chunk_size]
            desc = "\n".join([
                f"`{str(idx+1).zfill(2)}.` {role.mention} - **{len(role.members)}** member{'s' if len(role.members) != 1 else ''}"
                for idx, role in enumerate(chunk, start=i)
            ])
            embed = discord.Embed(color=Config.COLORS.DEFAULT, title="Roles", description=desc)
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            embeds.append(embed)
        
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            from stare.core.tools.paginator import PaginatorView
            view = PaginatorView(embeds, user=ctx.author)
            await ctx.send(embed=embeds[0], view=view)
    
    @commands.command(name="roleinfo", aliases=["ri"])
    async def roleinfo(self, ctx: Context, role: discord.Role):
        info = f"**ID:** `{role.id}`\n"
        info += f"**Members:** {len(role.members)}\n"
        info += f"**Position:** {role.position}\n"
        info += f"**Color:** `{str(role.color)}`\n"
        info += f"**Mentionable:** {'Yes' if role.mentionable else 'No'}\n"
        info += f"**Hoisted:** {'Yes' if role.hoist else 'No'}\n"
        info += f"**Created:** {discord.utils.format_dt(role.created_at, 'R')}"
        
        e = discord.Embed(
            color=role.color if role.color != discord.Color.default() else Config.COLORS.DEFAULT,
            description=info
        )
        e.set_author(name=role.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        await ctx.send(embed=e)
    
    @commands.command(name="emojis")
    async def emojis(self, ctx: Context):
        emojis = [str(e) for e in ctx.guild.emojis]
        
        if not emojis:
            return await ctx.warn("This server has no custom emojis")
        
        e = discord.Embed(
            color=Config.COLORS.DEFAULT,
            description=' '.join(emojis)
        )
        e.set_author(name=f"{ctx.guild.name}'s Emojis ({len(emojis)})", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        await ctx.send(embed=e)
    
    @commands.command(name="emojiinfo", aliases=["ei"])
    async def emojiinfo(self, ctx: Context, emoji: discord.Emoji):
        info = f"**ID:** `{emoji.id}`\n"
        info += f"**Animated:** {'Yes' if emoji.animated else 'No'}\n"
        info += f"**Created:** {discord.utils.format_dt(emoji.created_at, 'R')}\n"
        info += f"**URL:** [Click here]({emoji.url})"
        
        e = discord.Embed(color=Config.COLORS.DEFAULT, description=info)
        e.set_author(name=f":{emoji.name}:", icon_url=emoji.url)
        e.set_thumbnail(url=emoji.url)
        await ctx.send(embed=e)
    
    @commands.command(name="membercount", aliases=["mc"])
    async def membercount(self, ctx: Context):
        g = ctx.guild
        total = g.member_count
        online = len([m for m in g.members if m.status != discord.Status.offline])
        bots = len([m for m in g.members if m.bot])
        
        e = discord.Embed(
            title=f"{g.name}'s member count",
            color=Config.COLORS.DEFAULT
        )
        e.add_field(name="Total:", value=f"> {total:,}", inline=True)
        e.add_field(name="Online:", value=f"> {online:,}", inline=True)
        e.add_field(name="Bots:", value=f"> {bots:,}", inline=True)
        e.set_footer(text=f"Requested by {ctx.author}")
        await ctx.send(embed=e)
    
    @commands.command(name="boosters", aliases=["boosts"])
    async def boosters(self, ctx: Context):
        boosters = sorted(ctx.guild.premium_subscribers, key=lambda m: m.premium_since)
        
        if not boosters:
            return await ctx.send(embed=discord.Embed(
                color=Config.COLORS.DEFAULT,
                description="No boosters"
            ))
        
        embeds = []
        chunks = [boosters[i:i+10] for i in range(0, len(boosters), 10)]
        
        for chunk in chunks:
            desc = "\n".join([
                f"`{i+1:02d}.` - {m.mention} (<t:{int(m.premium_since.timestamp())}:R>)"
                for i, m in enumerate(chunk, start=boosters.index(chunk[0]))
            ])
            e = discord.Embed(color=Config.COLORS.DEFAULT, title="Boosters", description=desc)
            e.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
            embeds.append(e)
        
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            from stare.core.tools.paginator import PaginatorView
            view = PaginatorView(embeds, user=ctx.author)
            await ctx.send(embed=embeds[0], view=view)
    
    @commands.command(name="channelinfo", aliases=["ci"])
    async def channelinfo(self, ctx: Context, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        
        info = f"**ID:** `{ch.id}`\n"
        info += f"**Category:** {ch.category.name if ch.category else 'None'}\n"
        info += f"**Created:** {discord.utils.format_dt(ch.created_at, 'R')}\n"
        info += f"**NSFW:** {'Yes' if ch.is_nsfw() else 'No'}\n"
        info += f"**Slowmode:** {f'{ch.slowmode_delay}s' if ch.slowmode_delay else 'None'}"
        
        if ch.topic:
            info += f"\n\n**Topic:**\n{ch.topic}"
        
        e = discord.Embed(color=Config.COLORS.DEFAULT, description=info)
        e.set_author(name=f"#{ch.name}", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        await ctx.send(embed=e)
    
    @commands.command(name="icon")
    async def icon(self, ctx: Context):
        if not ctx.guild.icon:
            return await ctx.warn("This server has no icon")
        
        e = discord.Embed(color=Config.COLORS.DEFAULT)
        e.set_author(name=f"{ctx.guild.name}'s icon", icon_url=ctx.guild.icon.url)
        e.set_image(url=ctx.guild.icon.url)
        await ctx.send(embed=e)
    
    @commands.command(name="serverbanner")
    async def serverbanner(self, ctx: Context):
        if not ctx.guild.banner:
            return await ctx.warn("This server has no banner")
        
        e = discord.Embed(color=Config.COLORS.DEFAULT)
        e.set_author(name=f"{ctx.guild.name}'s banner", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        e.set_image(url=ctx.guild.banner.url)
        await ctx.send(embed=e)
    
    @commands.command(name="splash")
    async def splash(self, ctx: Context):
        if not ctx.guild.splash:
            return await ctx.warn("This server has no splash image")
        
        e = discord.Embed(color=Config.COLORS.DEFAULT)
        e.set_author(name=f"{ctx.guild.name}'s splash", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        e.set_image(url=ctx.guild.splash.url)
        await ctx.send(embed=e)


async def setup(bot):
    await bot.add_cog(Information(bot))
