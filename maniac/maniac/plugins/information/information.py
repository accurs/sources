import discord
from discord.ext import commands
from maniac.core.config import Config
from maniac.core.command_example import example
from datetime import datetime, timezone
import psutil
import time

class Information(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.process = psutil.Process()
        self.start_time = time.time()
    
    def format_uptime(self, seconds):
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs}s")
        
        return " ".join(parts)
    
    @commands.command(name="botinfo", aliases=["about", "info"])
    @example(",botinfo")
    async def botinfo(self, ctx):
        uptime_seconds = int(time.time() - self.start_time)
        uptime_str = self.format_uptime(uptime_seconds)
        
        embed = discord.Embed(
            description="\n".join([
                f"Serving `{len(self.bot.guilds):,}` servers with `{len(self.bot.users):,}` users",
                f"Utilizing `{len(set(self.bot.walk_commands())):,}` commands across `{len(self.bot.cogs)}` extensions"
            ]),
            color=Config.COLORS.DEFAULT
        )
        
        embed.set_author(
            name=self.bot.user.display_name,
            url="https://discord.gg/your_invite",
            icon_url=self.bot.user.display_avatar.url
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        
        memory_mb = self.process.memory_info().rss / 1024 / 1024
        embed.add_field(
            name="Process",
            value="\n".join([
                f"**CPU:** `{self.process.cpu_percent()}%`",
                f"**RAM:** `{memory_mb:.2f} MB`",
                f"**Launched:** {uptime_str} ago"
            ]),
            inline=True
        )
        
        embed.add_field(
            name="Links",
            value="\n".join([
                f"[Invite]({discord.utils.oauth_url(self.bot.user.id)})",
                "[Website](https://your-website.com)",
                "[Discord Server](https://discord.gg/Trq9NZFfey)"
            ]),
            inline=True
        )
        
        embed.set_footer(text=f"v1.0.0 with discord.py v{discord.__version__}")
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="serverinfo", aliases=["si", "guildinfo"])
    @example(",serverinfo")
    async def serverinfo(self, ctx):
        guild = ctx.guild
        
        embed = discord.Embed(
            title=guild.name,
            color=Config.COLORS.DEFAULT,
            timestamp=datetime.now(timezone.utc)
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        embed.add_field(
            name="General",
            value="\n".join([
                f"**Owner:** {guild.owner.mention}",
                f"**Created:** <t:{int(guild.created_at.timestamp())}:R>",
                f"**ID:** `{guild.id}`",
                f"**Verification:** {str(guild.verification_level).title()}"
            ]),
            inline=True
        )
        
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        
        embed.add_field(
            name="Channels",
            value="\n".join([
                f"**Text:** {text_channels}",
                f"**Voice:** {voice_channels}",
                f"**Categories:** {categories}",
                f"**Total:** {text_channels + voice_channels}"
            ]),
            inline=True
        )
        
        total_members = guild.member_count
        bots = len([m for m in guild.members if m.bot])
        humans = total_members - bots
        
        embed.add_field(
            name="Members",
            value="\n".join([
                f"**Total:** {total_members:,}",
                f"**Humans:** {humans:,}",
                f"**Bots:** {bots:,}"
            ]),
            inline=True
        )
        
        embed.add_field(
            name="Other",
            value="\n".join([
                f"**Roles:** {len(guild.roles)}",
                f"**Emojis:** {len(guild.emojis)}/{guild.emoji_limit}",
                f"**Boosts:** {guild.premium_subscription_count} (Level {guild.premium_tier})"
            ]),
            inline=True
        )
        
        if guild.banner:
            embed.set_image(url=guild.banner.url)
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="userinfo", aliases=["ui", "whois"])
    @example(",userinfo @offermillions")
    async def userinfo(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        
        embed = discord.Embed(
            title=f"{member}",
            color=member.color if member.color != discord.Color.default() else Config.COLORS.DEFAULT,
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        
        embed.add_field(
            name="General",
            value="\n".join([
                f"**ID:** `{member.id}`",
                f"**Nickname:** {member.nick or 'None'}",
                f"**Bot:** {'Yes' if member.bot else 'No'}",
                f"**Created:** <t:{int(member.created_at.timestamp())}:R>"
            ]),
            inline=True
        )
        
        embed.add_field(
            name="Server",
            value="\n".join([
                f"**Joined:** <t:{int(member.joined_at.timestamp())}:R>",
                f"**Roles:** {len(member.roles) - 1}",
                f"**Top Role:** {member.top_role.mention if member.top_role.name != '@everyone' else 'None'}",
                f"**Boosting:** {'Yes' if member.premium_since else 'No'}"
            ]),
            inline=True
        )
        
        perms = []
        if member.guild_permissions.administrator:
            perms.append("Administrator")
        elif member.guild_permissions.manage_guild:
            perms.append("Manage Server")
        elif member.guild_permissions.manage_channels:
            perms.append("Manage Channels")
        elif member.guild_permissions.manage_messages:
            perms.append("Manage Messages")
        
        embed.add_field(
            name="Key Permissions",
            value=", ".join(perms) if perms else "None",
            inline=False
        )
        
        if len(member.roles) > 1:
            roles = [role.mention for role in reversed(member.roles[1:11])]
            embed.add_field(
                name=f"Roles [{len(member.roles) - 1}]",
                value=" ".join(roles) + (f" (+{len(member.roles) - 11})" if len(member.roles) > 11 else ""),
                inline=False
            )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="avatar", aliases=["av", "pfp"])
    @example(",avatar @offermillions")
    async def avatar(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        
        embed = discord.Embed(
            title=f"{member}'s Avatar",
            color=Config.COLORS.DEFAULT
        )
        
        embed.set_image(url=member.display_avatar.url)
        embed.add_field(
            name="Links",
            value=f"[PNG]({member.display_avatar.replace(format='png', size=4096).url}) | "
                  f"[JPG]({member.display_avatar.replace(format='jpg', size=4096).url}) | "
                  f"[WEBP]({member.display_avatar.replace(format='webp', size=4096).url})"
        )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="banner")
    @example(",banner @offermillions")
    async def banner(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        
        user = await self.bot.fetch_user(member.id)
        
        if not user.banner:
            return await ctx.deny(f"{member.mention} doesn't have a banner")
        
        embed = discord.Embed(
            title=f"{member}'s Banner",
            color=Config.COLORS.DEFAULT
        )
        
        embed.set_image(url=user.banner.url)
        embed.add_field(
            name="Links",
            value=f"[PNG]({user.banner.replace(format='png', size=4096).url}) | "
                  f"[JPG]({user.banner.replace(format='jpg', size=4096).url}) | "
                  f"[WEBP]({user.banner.replace(format='webp', size=4096).url})"
        )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="servericon", aliases=["icon"])
    @example(",servericon")
    async def servericon(self, ctx):
        if not ctx.guild.icon:
            return await ctx.deny("This server doesn't have an icon")
        
        embed = discord.Embed(
            title=f"{ctx.guild.name}'s Icon",
            color=Config.COLORS.DEFAULT
        )
        
        embed.set_image(url=ctx.guild.icon.url)
        embed.add_field(
            name="Links",
            value=f"[PNG]({ctx.guild.icon.replace(format='png', size=4096).url}) | "
                  f"[JPG]({ctx.guild.icon.replace(format='jpg', size=4096).url}) | "
                  f"[WEBP]({ctx.guild.icon.replace(format='webp', size=4096).url})"
        )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="serverbanner")
    @example(",serverbanner")
    async def serverbanner(self, ctx):
        if not ctx.guild.banner:
            return await ctx.deny("This server doesn't have a banner")
        
        embed = discord.Embed(
            title=f"{ctx.guild.name}'s Banner",
            color=Config.COLORS.DEFAULT
        )
        
        embed.set_image(url=ctx.guild.banner.url)
        embed.add_field(
            name="Links",
            value=f"[PNG]({ctx.guild.banner.replace(format='png', size=4096).url}) | "
                  f"[JPG]({ctx.guild.banner.replace(format='jpg', size=4096).url}) | "
                  f"[WEBP]({ctx.guild.banner.replace(format='webp', size=4096).url})"
        )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="roleinfo", aliases=["ri"])
    @example(",roleinfo @Member")
    async def roleinfo(self, ctx, *, role: discord.Role):
        embed = discord.Embed(
            title=role.name,
            color=role.color if role.color != discord.Color.default() else Config.COLORS.DEFAULT,
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="General",
            value="\n".join([
                f"**ID:** `{role.id}`",
                f"**Color:** `{role.color}`",
                f"**Position:** {role.position}",
                f"**Created:** <t:{int(role.created_at.timestamp())}:R>"
            ]),
            inline=True
        )
        
        embed.add_field(
            name="Settings",
            value="\n".join([
                f"**Mentionable:** {'Yes' if role.mentionable else 'No'}",
                f"**Hoisted:** {'Yes' if role.hoist else 'No'}",
                f"**Managed:** {'Yes' if role.managed else 'No'}",
                f"**Members:** {len(role.members)}"
            ]),
            inline=True
        )
        
        key_perms = []
        if role.permissions.administrator:
            key_perms.append("Administrator")
        if role.permissions.manage_guild:
            key_perms.append("Manage Server")
        if role.permissions.manage_roles:
            key_perms.append("Manage Roles")
        if role.permissions.manage_channels:
            key_perms.append("Manage Channels")
        if role.permissions.kick_members:
            key_perms.append("Kick Members")
        if role.permissions.ban_members:
            key_perms.append("Ban Members")
        
        if key_perms:
            embed.add_field(
                name="Key Permissions",
                value=", ".join(key_perms),
                inline=False
            )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="ping")
    @example(",ping")
    async def ping(self, ctx):
        latency = round(self.bot.latency * 1000)
        await ctx.reply(f"`{latency}ms`")
    
    @commands.command(name="rotate", help="Rotate an image by a provided degree")
    @example(",rotate 90 @offermillions")
    async def rotate(self, ctx, degree: int, member: discord.Member = None):
        import io
        from PIL import Image
        import aiohttp
        
        image_url = None
        
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if attachment.content_type and attachment.content_type.startswith("image/"):
                image_url = attachment.url
        elif member:
            image_url = member.display_avatar.url
        elif ctx.message.reference:
            try:
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                if ref_msg.attachments:
                    attachment = ref_msg.attachments[0]
                    if attachment.content_type and attachment.content_type.startswith("image/"):
                        image_url = attachment.url
            except:
                pass
        
        if not image_url:
            return await ctx.deny("Please provide an image, mention a member, or reply to a message with an image")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    return await ctx.deny("Failed to download the image")
                img_bytes = await resp.read()
        
        img = Image.open(io.BytesIO(img_bytes))
        rotated = img.rotate(degree, expand=True)
        
        output = io.BytesIO()
        rotated.save(output, format='PNG')
        output.seek(0)
        
        file = discord.File(output, filename="rotated.png")
        await ctx.send(file=file)
    
    @commands.command(name="membercount", aliases=["mc"], help="View server member count")
    @example(",membercount")
    async def membercount(self, ctx):
        total = ctx.guild.member_count
        humans = len([m for m in ctx.guild.members if not m.bot])
        bots = total - humans
        
        embed = discord.Embed(
            title=f"{ctx.guild.name} Member Count",
            color=Config.COLORS.DEFAULT
        )
        
        embed.add_field(name="Total", value=f"`{total:,}`", inline=True)
        embed.add_field(name="Humans", value=f"`{humans:,}`", inline=True)
        embed.add_field(name="Bots", value=f"`{bots:,}`", inline=True)
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="channelinfo", aliases=["ci"], help="View information about a channel")
    @example(",channelinfo #general")
    async def channelinfo(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        
        embed = discord.Embed(
            title=f"#{channel.name}",
            color=Config.COLORS.DEFAULT
        )
        
        embed.add_field(
            name="General",
            value="\n".join([
                f"**ID:** `{channel.id}`",
                f"**Category:** {channel.category.name if channel.category else 'None'}",
                f"**Position:** {channel.position}",
                f"**Created:** <t:{int(channel.created_at.timestamp())}:R>"
            ]),
            inline=True
        )
        
        embed.add_field(
            name="Settings",
            value="\n".join([
                f"**NSFW:** {'Yes' if channel.is_nsfw() else 'No'}",
                f"**Slowmode:** {channel.slowmode_delay}s" if channel.slowmode_delay else "**Slowmode:** None",
                f"**Topic:** {channel.topic[:50] + '...' if channel.topic and len(channel.topic) > 50 else channel.topic or 'None'}"
            ]),
            inline=True
        )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="inviteinfo", aliases=["ii"], help="View information about an invite")
    @example(",inviteinfo discord")
    async def inviteinfo(self, ctx, invite_code: str):
        try:
            invite = await self.bot.fetch_invite(invite_code)
            
            embed = discord.Embed(
                title=f"Invite: {invite.code}",
                url=invite.url,
                color=Config.COLORS.DEFAULT
            )
            
            if invite.guild:
                embed.add_field(
                    name="Server",
                    value="\n".join([
                        f"**Name:** {invite.guild.name}",
                        f"**ID:** `{invite.guild.id}`",
                        f"**Members:** {invite.approximate_member_count:,}" if invite.approximate_member_count else "**Members:** Unknown",
                        f"**Online:** {invite.approximate_presence_count:,}" if invite.approximate_presence_count else "**Online:** Unknown"
                    ]),
                    inline=True
                )
                
                if invite.guild.icon:
                    embed.set_thumbnail(url=invite.guild.icon.url)
                
                if invite.guild.banner:
                    embed.set_image(url=invite.guild.banner.url)
            
            if invite.inviter:
                embed.add_field(
                    name="Inviter",
                    value=f"{invite.inviter.mention}\n`{invite.inviter.id}`",
                    inline=True
                )
            
            if invite.channel:
                embed.add_field(
                    name="Channel",
                    value=f"#{invite.channel.name}",
                    inline=True
                )
            
            if invite.expires_at:
                embed.add_field(
                    name="Expires",
                    value=f"<t:{int(invite.expires_at.timestamp())}:R>",
                    inline=True
                )
            
            await ctx.reply(embed=embed)
        except:
            await ctx.deny("Invalid invite code or invite not found")
    
    @commands.group(name="boosters", invoke_without_command=True, help="View list of server boosters")
    @example(",boosters")
    async def boosters(self, ctx):
        if ctx.invoked_subcommand is not None:
            return
        
        boosters = [m for m in ctx.guild.members if m.premium_since]
        
        if not boosters:
            return await ctx.deny("This server has no boosters")
        
        boosters.sort(key=lambda m: m.premium_since)
        
        class BoostersPaginator(discord.ui.View):
            def __init__(self, ctx_inner, boosters_list, per_page=10):
                super().__init__(timeout=60)
                self.ctx = ctx_inner
                self.boosters = boosters_list
                self.per_page = per_page
                self.current_page = 0
                self.max_pages = (len(boosters_list) - 1) // per_page + 1
            
            def get_page_embed(self):
                start = self.current_page * self.per_page
                end = start + self.per_page
                page_boosters = self.boosters[start:end]
                
                embed = discord.Embed(
                    title=f"Server Boosters ({len(self.boosters)})",
                    color=Config.COLORS.DEFAULT
                )
                
                description = []
                for i, booster in enumerate(page_boosters, start + 1):
                    description.append(
                        f"`{i}.` {booster.mention} - <t:{int(booster.premium_since.timestamp())}:R>"
                    )
                
                embed.description = "\n".join(description)
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
        
        view = BoostersPaginator(ctx, boosters)
        await ctx.send(embed=view.get_page_embed(), view=view)
    
    @boosters.command(name="lost", help="View list of most recent lost boosters")
    async def boosters_lost(self, ctx):
        from maniac.core.database import db
        
        lost_boosters = await db.lost_boosters.find({
            "guild_id": ctx.guild.id
        }).sort("lost_at", -1).limit(50).to_list(length=50)
        
        if not lost_boosters:
            return await ctx.deny("No lost boosters data available")
        
        class LostBoostersPaginator(discord.ui.View):
            def __init__(self, ctx_inner, boosters_list, per_page=10):
                super().__init__(timeout=60)
                self.ctx = ctx_inner
                self.boosters = boosters_list
                self.per_page = per_page
                self.current_page = 0
                self.max_pages = (len(boosters_list) - 1) // per_page + 1
            
            async def get_page_embed(self):
                start = self.current_page * self.per_page
                end = start + self.per_page
                page_boosters = self.boosters[start:end]
                
                embed = discord.Embed(
                    title=f"Lost Boosters ({len(self.boosters)})",
                    color=Config.COLORS.ERROR
                )
                
                description = []
                for i, booster in enumerate(page_boosters, start + 1):
                    try:
                        user = await self.ctx.bot.fetch_user(booster['user_id'])
                        description.append(
                            f"`{i}.` {user.mention} - <t:{int(booster['lost_at'].timestamp())}:R>"
                        )
                    except:
                        description.append(
                            f"`{i}.` Unknown User (`{booster['user_id']}`) - <t:{int(booster['lost_at'].timestamp())}:R>"
                        )
                
                embed.description = "\n".join(description)
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
        
        view = LostBoostersPaginator(ctx, lost_boosters)
        await ctx.send(embed=await view.get_page_embed(), view=view)
    
    @commands.command(name="weather", help="Get weather information for a location")
    @example(",weather New York")
    async def weather(self, ctx, *, location: str):
        import aiohttp
        
        api_key = "96f73a3d7687ea16da532311a0215b9d"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric") as r:
                if r.status != 200:
                    return await ctx.warn(f"Couldn't find weather data for `{location}`")
                
                data = await r.json()
                
                if data.get("cod") != 200:
                    return await ctx.warn(f"Couldn't find weather data for `{location}`")
                
                city = data["name"]
                country = data["sys"]["country"]
                temp = data["main"]["temp"]
                feels_like = data["main"]["feels_like"]
                humidity = data["main"]["humidity"]
                description = data["weather"][0]["description"].title()
                icon = data["weather"][0]["icon"]
                wind_speed = data["wind"]["speed"]
                
                embed = discord.Embed(
                    title=f"Weather in {city}, {country}",
                    description=description,
                    color=Config.COLORS.DEFAULT
                )
                
                embed.set_thumbnail(url=f"http://openweathermap.org/img/wn/{icon}@2x.png")
                
                embed.add_field(
                    name="Temperature",
                    value=f"**Current:** {temp}°C\n**Feels Like:** {feels_like}°C",
                    inline=True
                )
                
                embed.add_field(
                    name="Conditions",
                    value=f"**Humidity:** {humidity}%\n**Wind Speed:** {wind_speed} m/s",
                    inline=True
                )
                
                await ctx.send(embed=embed)
    
    @commands.command(name="invites", help="View your server invite statistics")
    @example(",invites @offermillions")
    async def invites(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        
        try:
            invites = await ctx.guild.invites()
        except:
            return await ctx.deny("I don't have permission to view invites")
        
        member_invites = [inv for inv in invites if inv.inviter and inv.inviter.id == member.id]
        
        if not member_invites:
            return await ctx.deny(f"{member.mention} has no invites in this server")
        
        total_uses = sum(inv.uses for inv in member_invites)
        
        embed = discord.Embed(
            title=f"{member.name}'s Invites",
            color=Config.COLORS.DEFAULT
        )
        
        embed.add_field(
            name="Statistics",
            value=f"**Total Invites:** {len(member_invites)}\n**Total Uses:** {total_uses}",
            inline=False
        )
        
        invite_list = []
        for inv in sorted(member_invites, key=lambda x: x.uses, reverse=True)[:10]:
            expires = f"<t:{int(inv.expires_at.timestamp())}:R>" if inv.expires_at else "Never"
            invite_list.append(f"**{inv.code}** - {inv.uses} uses (expires {expires})")
        
        if invite_list:
            embed.add_field(
                name="Top Invites",
                value="\n".join(invite_list),
                inline=False
            )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="joinposition", aliases=["joinpos"], help="Show member's join position")
    @example(",joinposition @offermillions")
    async def joinposition(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        
        members = sorted(ctx.guild.members, key=lambda m: m.joined_at)
        position = members.index(member) + 1
        
        embed = discord.Embed(
            title=f"{member.name}'s Join Position",
            description=f"{member.mention} was the **{position:,}** member to join {ctx.guild.name}",
            color=Config.COLORS.DEFAULT
        )
        
        embed.add_field(
            name="Joined",
            value=f"<t:{int(member.joined_at.timestamp())}:F>",
            inline=False
        )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="emojis", help="List all server emojis")
    @example(",emojis")
    async def emojis(self, ctx):
        if not ctx.guild.emojis:
            return await ctx.deny("This server has no custom emojis")
        
        class EmojiPaginator(discord.ui.View):
            def __init__(self, ctx_inner, emojis_list, per_page=10):
                super().__init__(timeout=60)
                self.ctx = ctx_inner
                self.emojis = emojis_list
                self.per_page = per_page
                self.current_page = 0
                self.max_pages = (len(emojis_list) - 1) // per_page + 1
            
            def get_page_embed(self):
                start = self.current_page * self.per_page
                end = start + self.per_page
                page_emojis = self.emojis[start:end]
                
                embed = discord.Embed(
                    title=f"Server Emojis ({len(self.emojis)}/{self.ctx.guild.emoji_limit})",
                    color=Config.COLORS.DEFAULT
                )
                
                description = []
                for i, emoji in enumerate(page_emojis, start + 1):
                    animated = "Yes" if emoji.animated else "No"
                    description.append(f"`{i}.` {emoji} `:{emoji.name}:` - ID: `{emoji.id}` - Animated: {animated}")
                
                embed.description = "\n".join(description)
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
        
        view = EmojiPaginator(ctx, list(ctx.guild.emojis))
        await ctx.send(embed=view.get_page_embed(), view=view)
    
    @commands.command(name="stickers", help="List all server stickers")
    @example(",stickers")
    async def stickers(self, ctx):
        if not ctx.guild.stickers:
            return await ctx.deny("This server has no stickers")
        
        class StickerPaginator(discord.ui.View):
            def __init__(self, ctx_inner, stickers_list, per_page=10):
                super().__init__(timeout=60)
                self.ctx = ctx_inner
                self.stickers = stickers_list
                self.per_page = per_page
                self.current_page = 0
                self.max_pages = (len(stickers_list) - 1) // per_page + 1
            
            def get_page_embed(self):
                start = self.current_page * self.per_page
                end = start + self.per_page
                page_stickers = self.stickers[start:end]
                
                embed = discord.Embed(
                    title=f"Server Stickers ({len(self.stickers)}/{self.ctx.guild.sticker_limit})",
                    color=Config.COLORS.DEFAULT
                )
                
                description = []
                for i, sticker in enumerate(page_stickers, start + 1):
                    description.append(f"`{i}.` **{sticker.name}** - ID: `{sticker.id}` - [View]({sticker.url})")
                
                embed.description = "\n".join(description)
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
        
        view = StickerPaginator(ctx, list(ctx.guild.stickers))
        await ctx.send(embed=view.get_page_embed(), view=view)

async def setup(bot):
    await bot.add_cog(Information(bot))

