import discord
from discord.ext import commands
import aiohttp
import io
import asyncio
from datetime import datetime
from maniac.core.command_example import example
from maniac.core.config import Config

HAUNT_API_KEY = "xextiNirHxBB79mbdiyxfj3yVfRyNGmo"
EMOGIRLS_API_KEY = "139ccf8fe20f7843c3380ca528d96858d88f84ed08efe045d79b2415d4fd8855"

class Social(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name="angelz")
    @example(",angelz username")
    async def angelz(self, ctx, username: str = None):
        if not username:
            return await ctx.warn('You need to provide a **username**')
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://angelz.bio/api/profile?username={username}") as r:
                if r.status != 200:
                    return await ctx.warn(f"I **couldn't** find a profile for `@{username}`")
                
                data = await r.json()
                
                if not data or data.get("error"):
                    return await ctx.warn(f"I **couldn't** find a profile for `@{username}`")
                
                uid = data.get("uid", "N/A")
                views = data.get("views", "N/A")
                display = data.get("display_name", username)
                user = data.get("username", username)
                description = data.get("bio", "")
                location = data.get("location", "N/A") or "N/A"
                
                alias_raw = data.get("alias", "") or ""
                alias = ", ".join(alias_raw.split(",")) if alias_raw else "None"
                
                avatar_url = data.get("avatar") or None
                background_url = data.get("page_bg") or None
                
                embed = discord.Embed(
                    title=f"{display} (@{user})",
                    url=f"https://angelz.bio/{user}",
                    description=f">>> {description}" if description else None,
                    color=Config.COLORS.DEFAULT
                )
                
                embed.set_author(
                    name=str(ctx.author),
                    icon_url=ctx.author.display_avatar.url
                )
                
                if avatar_url:
                    embed.set_thumbnail(url=avatar_url)
                
                embed.add_field(
                    name="Statistics:",
                    value=f"> **UID**: `{uid}`\n> **Views**: `{views}`\n> **Location**: {location}",
                    inline=True
                )
                
                embed.add_field(
                    name="Aliases:",
                    value=f"> {alias}",
                    inline=True
                )
                
                view = discord.ui.View()
                view.add_item(
                    discord.ui.Button(
                        label="Icon",
                        style=discord.ButtonStyle.link,
                        url=avatar_url if avatar_url else f"https://angelz.bio/{user}",
                        emoji=discord.PartialEmoji(id=1476690758726713568, name="angelz", animated=False)
                    )
                )
                view.add_item(
                    discord.ui.Button(
                        label="Background",
                        style=discord.ButtonStyle.link,
                        url=background_url if background_url else f"https://angelz.bio/{user}",
                        emoji=discord.PartialEmoji(id=1476690758726713568, name="angelz", animated=False)
                    )
                )
                
                await ctx.send(embed=embed, view=view)
    
    @commands.group(name="haunt", invoke_without_command=True)
    @example(",haunt username")
    async def haunt(self, ctx, user: str = None):
        if ctx.invoked_subcommand is not None:
            return
        
        if not user:
            return await ctx.warn('You need to provide a **username** or **UID**')
        
        async with aiohttp.ClientSession() as session:
            if user.isdigit():
                url = f"https://haunt.gg/api/lookup/uid/{user}?key={HAUNT_API_KEY}"
            else:
                url = f"https://haunt.gg/api/lookup/username/{user}?key={HAUNT_API_KEY}"
            
            async with session.get(url) as r:
                if r.status != 200:
                    return await ctx.warn(f"I **couldn't** find a profile for `{user}`")
                
                data = await r.json()
                
                if not data or data.get("error"):
                    return await ctx.warn(f"I **couldn't** find a profile for `{user}`")
                
                uid = data.get("uid", "N/A")
                username = data.get("username", "N/A")
                display_username = data.get("displayUsername", username)
                created_at = data.get("createdAt", 0)
                banned = data.get("banned", False)
                
                profile = data.get("profile", {})
                avatar = profile.get("avatar")
                banner = profile.get("banner")
                description = profile.get("description", "")
                view_count = profile.get("viewCount", 0)
                
                badges = data.get("badges", [])
                custom_badges = data.get("customBadges", [])
                links = data.get("links", [])
                
                badge_count = len([b for b in badges if b.get("enabled", False)])
                custom_badge_count = len([b for b in custom_badges if b.get("enabled", False)])
                link_count = len([l for l in links if l.get("active", False)])
                
                embed = discord.Embed(
                    title=f"{display_username} (@{username})",
                    url=f"https://haunt.gg/{username}",
                    description=f">>> {description}" if description else None,
                    color=Config.COLORS.DEFAULT
                )
                
                embed.set_author(
                    name=str(ctx.author),
                    icon_url=ctx.author.display_avatar.url
                )
                
                if avatar:
                    embed.set_thumbnail(url=avatar)
                
                if banner:
                    embed.set_image(url=banner)
                
                embed.add_field(
                    name="Statistics:",
                    value=f"> **UID**: `{uid}`\n> **Views**: `{view_count:,}`\n> **Created**: <t:{created_at}:R>",
                    inline=True
                )
                
                embed.add_field(
                    name="Profile:",
                    value=f"> **Badges**: {badge_count}\n> **Custom Badges**: {custom_badge_count}\n> **Links**: {link_count}",
                    inline=True
                )
                
                if banned:
                    embed.set_footer(text="⚠️ This user is banned")
                
                view = discord.ui.View()
                view.add_item(
                    discord.ui.Button(
                        label="View Profile",
                        style=discord.ButtonStyle.link,
                        url=f"https://haunt.gg/{username}"
                    )
                )
                
                if avatar:
                    view.add_item(
                        discord.ui.Button(
                            label="Avatar",
                            style=discord.ButtonStyle.link,
                            url=avatar
                        )
                    )
                
                if banner:
                    view.add_item(
                        discord.ui.Button(
                            label="Banner",
                            style=discord.ButtonStyle.link,
                            url=banner
                        )
                    )
                
                await ctx.send(embed=embed, view=view)
    
    @commands.command(name="emogirls", aliases=["emo"])
    @example(",emogirls username")
    async def emogirls(self, ctx, slug: str = None):
        if not slug:
            return await ctx.warn('You need to provide a **username**')
        
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {EMOGIRLS_API_KEY}"}
            async with session.get(f"https://api.emogir.ls/api/v1/profiles/{slug}", headers=headers) as r:
                if r.status != 200:
                    return await ctx.warn(f"I **couldn't** find a profile for `{slug}`")
                
                data = await r.json()
                
                if not data or data.get("error"):
                    return await ctx.warn(f"I **couldn't** find a profile for `{slug}`")
                
                username = data.get("username", slug)
                display_name = data.get("displayName", username)
                bio = data.get("bio", "")
                avatar = data.get("avatar")
                banner = data.get("banner")
                views = data.get("views", 0)
                created_at = data.get("createdAt")
                
                badges = data.get("badges", [])
                widgets = data.get("widgets", [])
                
                embed = discord.Embed(
                    title=f"{display_name} (@{username})",
                    url=f"https://emogir.ls/{username}",
                    description=f">>> {bio}" if bio else None,
                    color=Config.COLORS.DEFAULT
                )
                
                embed.set_author(
                    name=str(ctx.author),
                    icon_url=ctx.author.display_avatar.url
                )
                
                if avatar:
                    embed.set_thumbnail(url=avatar)
                
                if banner:
                    embed.set_image(url=banner)
                
                stats_value = f"**Views**: `{views:,}`"
                if created_at:
                    stats_value += f"\n**Created**: <t:{int(created_at / 1000)}:R>"
                
                embed.add_field(
                    name="Statistics:",
                    value=f"> {stats_value}",
                    inline=True
                )
                
                embed.add_field(
                    name="Profile:",
                    value=f"> **Badges**: {len(badges)}\n> **Widgets**: {len(widgets)}",
                    inline=True
                )
                
                view = discord.ui.View()
                view.add_item(
                    discord.ui.Button(
                        label="View Profile",
                        style=discord.ButtonStyle.link,
                        url=f"https://emogir.ls/{username}"
                    )
                )
                
                if avatar:
                    view.add_item(
                        discord.ui.Button(
                            label="Avatar",
                            style=discord.ButtonStyle.link,
                            url=avatar
                        )
                    )
                
                if banner:
                    view.add_item(
                        discord.ui.Button(
                            label="Banner",
                            style=discord.ButtonStyle.link,
                            url=banner
                        )
                    )
                
                await ctx.send(embed=embed, view=view)
    
    @commands.command(name="emoleaderboard", aliases=["emolb"])
    @example(",emoleaderboard")
    async def emoleaderboard(self, ctx):
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {EMOGIRLS_API_KEY}"}
            async with session.get("https://api.emogir.ls/api/v1/stats/leaderboard", headers=headers) as r:
                if r.status != 200:
                    return await ctx.warn("Failed to fetch the leaderboard")
                
                data = await r.json()
                
                if not data or data.get("error"):
                    return await ctx.warn("Failed to fetch the leaderboard")
                
                embed = discord.Embed(
                    title="Emogir.ls Views Leaderboard",
                    color=Config.COLORS.DEFAULT,
                    url="https://emogir.ls"
                )
                
                embed.set_author(
                    name=str(ctx.author),
                    icon_url=ctx.author.display_avatar.url
                )
                
                description = []
                for i, user in enumerate(data[:10], 1):
                    username = user.get("username", "Unknown")
                    views = user.get("views", 0)
                    
                    medal = ""
                    if i == 1:
                        medal = "🥇"
                    elif i == 2:
                        medal = "🥈"
                    elif i == 3:
                        medal = "🥉"
                    else:
                        medal = f"`{i}.`"
                    
                    description.append(f"{medal} **{username}** - `{views:,}` views")
                
                embed.description = "\n".join(description)
                
                await ctx.send(embed=embed)
    
    @commands.group(name="roblox", aliases=["rblx"], invoke_without_command=True, help="View info about a Roblox user")
    @example(",roblox Builderman")
    async def roblox(self, ctx, username: str = None):
        if ctx.invoked_subcommand is not None:
            return
        
        if not username:
            return await ctx.warn("You need to provide a Roblox username")
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json"
                }
                
                async with session.post(
                    "https://users.roblox.com/v1/usernames/users",
                    json={"usernames": [username], "excludeBannedUsers": False},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    if r.status != 200:
                        return await ctx.warn(f"I couldn't find a Roblox user named `{username}`")
                    
                    data = await r.json()
                    
                    if not data.get("data"):
                        return await ctx.warn(f"I couldn't find a Roblox user named `{username}`")
                    
                    user_data = data["data"][0]
                    user_id = user_data["id"]
                
                async with session.get(
                    f"https://users.roblox.com/v1/users/{user_id}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    if r.status != 200:
                        return await ctx.warn("Failed to fetch user information")
                    
                    user_info = await r.json()
                
                async with session.get(
                    f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Png",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    avatar_data = await r.json()
                    avatar_url = avatar_data["data"][0]["imageUrl"] if avatar_data.get("data") else None
                
                try:
                    async with session.get(
                        f"https://groups.roblox.com/v1/users/{user_id}/groups/roles",
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as r:
                        if r.status == 200:
                            groups_data = await r.json()
                            groups = groups_data.get("data", [])
                        else:
                            groups = []
                except:
                    groups = []
        
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            return await ctx.deny(f"Failed to connect to Roblox API. The service may be temporarily unavailable")
        except Exception as e:
            return await ctx.deny(f"An error occurred: {str(e)}")
        
        display_name = user_info.get("displayName", username)
        username = user_info.get("name", username)
        description = user_info.get("description", "")
        created = user_info.get("created")
        is_banned = user_info.get("isBanned", False)
        
        embed = discord.Embed(
            title=f"{display_name} (@{username})",
            url=f"https://www.roblox.com/users/{user_id}/profile",
            description=f">>> {description[:200] + '...' if len(description) > 200 else description}" if description else None,
            color=Config.COLORS.ERROR if is_banned else Config.COLORS.DEFAULT
        )
        
        embed.set_author(
            name=str(ctx.author),
            icon_url=ctx.author.display_avatar.url
        )
        
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
        
        embed.add_field(
            name="Statistics",
            value=f"> **ID:** `{user_id}`\n> **Created:** <t:{int(datetime.fromisoformat(created.replace('Z', '+00:00')).timestamp())}:R>" if created else f"> **ID:** `{user_id}`",
            inline=True
        )
        
        if groups:
            group_names = [g["group"]["name"] for g in groups[:5]]
            group_text = "\n".join(group_names)
            if len(groups) > 5:
                group_text += f"\n... {len(groups) - 5} more"
            embed.add_field(
                name=f"Groups ({len(groups)})",
                value=f"> {group_text}",
                inline=True
            )
        
        if is_banned:
            embed.set_footer(text="⚠️ This user is banned")
        
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="View Profile",
                style=discord.ButtonStyle.link,
                url=f"https://www.roblox.com/users/{user_id}/profile"
            )
        )
        
        await ctx.send(embed=embed, view=view)
    
    @roblox.command(name="outfits", help="View a Roblox user's outfits")
    async def roblox_outfits(self, ctx, username: str = None):
        if not username:
            return await ctx.warn("You need to provide a Roblox username")
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json"
                }
                
                async with session.post(
                    "https://users.roblox.com/v1/usernames/users",
                    json={"usernames": [username], "excludeBannedUsers": False},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    if r.status != 200:
                        return await ctx.warn(f"I couldn't find a Roblox user named `{username}`")
                    
                    data = await r.json()
                    
                    if not data.get("data"):
                        return await ctx.warn(f"I couldn't find a Roblox user named `{username}`")
                    
                    user_data = data["data"][0]
                    user_id = user_data["id"]
                
                async with session.get(
                    f"https://avatar.roblox.com/v1/users/{user_id}/outfits?page=1&itemsPerPage=25",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    if r.status != 200:
                        return await ctx.warn("Failed to fetch outfits")
                    
                    outfits_data = await r.json()
                    outfits = outfits_data.get("data", [])
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return await ctx.deny("Failed to connect to Roblox API. The service may be temporarily unavailable")
        except Exception as e:
            return await ctx.deny(f"An error occurred: {str(e)}")
        
        if not outfits:
            return await ctx.deny(f"`{username}` has no outfits")
        
        class OutfitSelector(discord.ui.Select):
            def __init__(self, outfits_list):
                options = []
                for i, outfit in enumerate(outfits_list[:25]):
                    options.append(
                        discord.SelectOption(
                            label=outfit["name"][:100],
                            value=str(i),
                            description=f"Outfit {i + 1}/{len(outfits_list)}"
                        )
                    )
                super().__init__(placeholder="Select an outfit...", options=options)
            
            async def callback(self, interaction: discord.Interaction):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("This isn't your menu!", ephemeral=True)
                
                outfit_index = int(self.values[0])
                outfit = outfits[outfit_index]
                
                try:
                    async with aiohttp.ClientSession() as session:
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                            "Accept": "application/json"
                        }
                        async with session.get(
                            f"https://thumbnails.roblox.com/v1/users/outfits?userOutfitIds={outfit['id']}&size=420x420&format=Png",
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as r:
                            thumb_data = await r.json()
                            thumb_url = thumb_data["data"][0]["imageUrl"] if thumb_data.get("data") else None
                except:
                    thumb_url = None
                
                embed = discord.Embed(
                    title=outfit["name"],
                    color=Config.COLORS.DEFAULT
                )
                
                if thumb_url:
                    embed.set_image(url=thumb_url)
                
                embed.add_field(
                    name="Details",
                    value=f"> **Outfit ID:** `{outfit['id']}`\n> **User:** {username}",
                    inline=False
                )
                
                await interaction.response.edit_message(embed=embed, view=self.view)
        
        class OutfitView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.add_item(OutfitSelector(outfits))
        
        embed = discord.Embed(
            title=f"{username}'s Outfits ({len(outfits)})",
            description="Select an outfit from the dropdown below",
            color=Config.COLORS.DEFAULT
        )
        
        await ctx.send(embed=embed, view=OutfitView())
    
    @roblox.command(name="template", help="Download asset for an item")
    async def roblox_template(self, ctx, asset_id: int):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://assetdelivery.roblox.com/v1/asset/?id={asset_id}") as r:
                if r.status != 200:
                    return await ctx.warn(f"Failed to fetch asset `{asset_id}`")
                
                content_type = r.headers.get("Content-Type", "")
                
                if "image" in content_type:
                    image_data = await r.read()
                    file = discord.File(io.BytesIO(image_data), filename=f"asset_{asset_id}.png")
                    await ctx.send(file=file)
                elif "text/xml" in content_type or "application/xml" in content_type:
                    xml_data = await r.text()
                    if len(xml_data) > 2000:
                        file = discord.File(io.BytesIO(xml_data.encode()), filename=f"asset_{asset_id}.xml")
                        await ctx.send(file=file)
                    else:
                        await ctx.send(f"```xml\n{xml_data}\n```")
                else:
                    data = await r.read()
                    file = discord.File(io.BytesIO(data), filename=f"asset_{asset_id}.dat")
                    await ctx.send(file=file)
    
    @commands.command(name="github", aliases=["gh"], help="View GitHub user information")
    @example(",github torvalds")
    async def github(self, ctx, username: str):
        async with aiohttp.ClientSession() as session:
            headers = {"Accept": "application/vnd.github.v3+json"}
            
            async with session.get(f"https://api.github.com/users/{username}", headers=headers) as r:
                if r.status != 200:
                    return await ctx.warn(f"I couldn't find a GitHub user named `{username}`")
                
                data = await r.json()
        
        name = data.get("name") or username
        bio = data.get("bio") or "No bio"
        avatar = data.get("avatar_url")
        public_repos = data.get("public_repos", 0)
        followers = data.get("followers", 0)
        following = data.get("following", 0)
        created_at = data.get("created_at")
        location = data.get("location") or "Unknown"
        blog = data.get("blog") or None
        
        embed = discord.Embed(
            title=f"{name} (@{username})",
            url=f"https://github.com/{username}",
            description=f">>> {bio}",
            color=Config.COLORS.DEFAULT
        )
        
        embed.set_author(
            name=str(ctx.author),
            icon_url=ctx.author.display_avatar.url
        )
        
        if avatar:
            embed.set_thumbnail(url=avatar)
        
        embed.add_field(
            name="Statistics",
            value=f"> **Repos:** {public_repos:,}\n> **Followers:** {followers:,}\n> **Following:** {following:,}",
            inline=True
        )
        
        embed.add_field(
            name="Info",
            value=f"> **Location:** {location}\n> **Joined:** <t:{int(__import__('datetime').datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp())}:R>",
            inline=True
        )
        
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="View Profile",
                style=discord.ButtonStyle.link,
                url=f"https://github.com/{username}"
            )
        )
        
        if blog:
            view.add_item(
                discord.ui.Button(
                    label="Website",
                    style=discord.ButtonStyle.link,
                    url=blog if blog.startswith("http") else f"https://{blog}"
                )
            )
        
        await ctx.send(embed=embed, view=view)
    
    @commands.command(name="reddit", help="View Reddit user information")
    @example(",reddit spez")
    async def reddit(self, ctx, username: str):
        username = username.replace("u/", "").replace("/u/", "")
        
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "Mozilla/5.0"}
            
            async with session.get(f"https://www.reddit.com/user/{username}/about.json", headers=headers) as r:
                if r.status != 200:
                    return await ctx.warn(f"I couldn't find a Reddit user named `{username}`")
                
                data = await r.json()
                
                if "error" in data:
                    return await ctx.warn(f"I couldn't find a Reddit user named `{username}`")
                
                user_data = data["data"]
        
        name = user_data.get("name", username)
        icon = user_data.get("icon_img", "").split("?")[0]
        created = user_data.get("created_utc", 0)
        link_karma = user_data.get("link_karma", 0)
        comment_karma = user_data.get("comment_karma", 0)
        total_karma = user_data.get("total_karma", link_karma + comment_karma)
        is_gold = user_data.get("is_gold", False)
        
        embed = discord.Embed(
            title=f"u/{name}",
            url=f"https://www.reddit.com/user/{name}",
            description=f">>> Reddit user since <t:{int(created)}:D>",
            color=Config.COLORS.DEFAULT
        )
        
        embed.set_author(
            name=str(ctx.author),
            icon_url=ctx.author.display_avatar.url
        )
        
        if icon:
            embed.set_thumbnail(url=icon)
        
        embed.add_field(
            name="Karma",
            value=f"> **Total:** {total_karma:,}\n> **Post:** {link_karma:,}\n> **Comment:** {comment_karma:,}",
            inline=True
        )
        
        embed.add_field(
            name="Info",
            value=f"> **Premium:** {'Yes' if is_gold else 'No'}\n> **Joined:** <t:{int(created)}:R>",
            inline=True
        )
        
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="View Profile",
                style=discord.ButtonStyle.link,
                url=f"https://www.reddit.com/user/{name}"
            )
        )
        
        await ctx.send(embed=embed, view=view)
    
    @commands.command(name="twitch", help="View Twitch user information")
    @example(",twitch ninja")
    async def twitch(self, ctx, username: str):
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "Mozilla/5.0"}
            
            async with session.get(f"https://decapi.me/twitch/avatar/{username}") as r:
                avatar_url = await r.text()
                if "error" in avatar_url.lower() or r.status != 200:
                    avatar_url = None
            
            async with session.get(f"https://decapi.me/twitch/creation/{username}") as r:
                created = await r.text()
                if "error" in created.lower() or r.status != 200:
                    return await ctx.warn(f"I couldn't find a Twitch user named `{username}`")
            
            async with session.get(f"https://decapi.me/twitch/followers/{username}") as r:
                followers = await r.text()
                if "error" in followers.lower():
                    followers = "Unknown"
            
            async with session.get(f"https://decapi.me/twitch/uptime/{username}") as r:
                uptime = await r.text()
                is_live = "offline" not in uptime.lower() and "error" not in uptime.lower()
        
        embed = discord.Embed(
            title=f"{username}",
            url=f"https://twitch.tv/{username}",
            description=f">>> {'🔴 Currently Live' if is_live else '⚫ Offline'}",
            color=Config.COLORS.DEFAULT
        )
        
        embed.set_author(
            name=str(ctx.author),
            icon_url=ctx.author.display_avatar.url
        )
        
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
        
        embed.add_field(
            name="Info",
            value=f"> **Followers:** {followers}\n> **Created:** {created}",
            inline=False
        )
        
        if is_live:
            embed.add_field(
                name="Stream Uptime",
                value=f"> {uptime}",
                inline=False
            )
        
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="View Channel",
                style=discord.ButtonStyle.link,
                url=f"https://twitch.tv/{username}"
            )
        )
        
        await ctx.send(embed=embed, view=view)
    
    @commands.command(name="steam", help="View Steam user information")
    @example(",steam gabelogannewell")
    async def steam(self, ctx, steam_id: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://steamcommunity.com/id/{steam_id}/?xml=1") as r:
                if r.status != 200:
                    async with session.get(f"https://steamcommunity.com/profiles/{steam_id}/?xml=1") as r2:
                        if r2.status != 200:
                            return await ctx.warn(f"I couldn't find a Steam user with ID `{steam_id}`")
                        xml_data = await r2.text()
                else:
                    xml_data = await r.text()
        
        if "error" in xml_data.lower() or "profile could not be found" in xml_data.lower():
            return await ctx.warn(f"I couldn't find a Steam user with ID `{steam_id}`")
        
        import re
        
        name_match = re.search(r'<steamID><!\[CDATA\[(.*?)\]\]></steamID>', xml_data)
        name = name_match.group(1) if name_match else steam_id
        
        avatar_match = re.search(r'<avatarFull><!\[CDATA\[(.*?)\]\]></avatarFull>', xml_data)
        avatar = avatar_match.group(1) if avatar_match else None
        
        state_match = re.search(r'<onlineState>(.*?)</onlineState>', xml_data)
        state = state_match.group(1) if state_match else "Unknown"
        
        member_since_match = re.search(r'<memberSince>(.*?)</memberSince>', xml_data)
        member_since = member_since_match.group(1) if member_since_match else "Unknown"
        
        embed = discord.Embed(
            title=name,
            url=f"https://steamcommunity.com/id/{steam_id}",
            description=f">>> {state}",
            color=Config.COLORS.DEFAULT
        )
        
        embed.set_author(
            name=str(ctx.author),
            icon_url=ctx.author.display_avatar.url
        )
        
        if avatar:
            embed.set_thumbnail(url=avatar)
        
        embed.add_field(
            name="Info",
            value=f"> **Member Since:** {member_since}",
            inline=False
        )
        
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="View Profile",
                style=discord.ButtonStyle.link,
                url=f"https://steamcommunity.com/id/{steam_id}"
            )
        )
        
        await ctx.send(embed=embed, view=view)


    @commands.group(name="tiktok", aliases=["tt"], invoke_without_command=True, help="View TikTok user information")
    @example(",tiktok username")
    async def tiktok(self, ctx, username: str = None):
        if ctx.invoked_subcommand is not None:
            return
        
        if not username:
            return await ctx.warn("You need to provide a TikTok username")
        
        await ctx.send("TikTok user lookup coming soon!")
    
    @tiktok.command(name="country", help="Check a TikTok user's country")
    @example(",tiktok country username")
    async def tiktok_country(self, ctx, username: str = None):
        if not username:
            return await ctx.warn("You need to provide a TikTok username")
        
        username = username.lstrip("@")
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                
                async with session.get(
                    f"https://www.tiktok.com/@{username}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    if r.status != 200:
                        return await ctx.warn(f"I couldn't find a TikTok user named `@{username}`")
                    
                    html = await r.text()
                    
                    import re
                    country_match = re.search(r'"region":"([^"]+)"', html)
                    
                    if not country_match:
                        return await ctx.warn(f"Couldn't determine the country for `@{username}`")
                    
                    country_code = country_match.group(1)
                    
                    country_names = {
                        "US": "United States 🇺🇸",
                        "GB": "United Kingdom 🇬🇧",
                        "CA": "Canada 🇨🇦",
                        "AU": "Australia 🇦🇺",
                        "DE": "Germany 🇩🇪",
                        "FR": "France 🇫🇷",
                        "IT": "Italy 🇮🇹",
                        "ES": "Spain 🇪🇸",
                        "MX": "Mexico 🇲🇽",
                        "BR": "Brazil 🇧🇷",
                        "IN": "India 🇮🇳",
                        "JP": "Japan 🇯🇵",
                        "KR": "South Korea 🇰🇷",
                        "CN": "China 🇨🇳",
                        "RU": "Russia 🇷🇺",
                        "NL": "Netherlands 🇳🇱",
                        "SE": "Sweden 🇸🇪",
                        "NO": "Norway 🇳🇴",
                        "DK": "Denmark 🇩🇰",
                        "FI": "Finland 🇫🇮",
                        "PL": "Poland 🇵🇱",
                        "TR": "Turkey 🇹🇷",
                        "SA": "Saudi Arabia 🇸🇦",
                        "AE": "United Arab Emirates 🇦🇪",
                        "ZA": "South Africa 🇿🇦",
                        "NG": "Nigeria 🇳🇬",
                        "EG": "Egypt 🇪🇬",
                        "AR": "Argentina 🇦🇷",
                        "CL": "Chile 🇨🇱",
                        "CO": "Colombia 🇨🇴",
                        "PE": "Peru 🇵🇪",
                        "VE": "Venezuela 🇻🇪",
                        "PH": "Philippines 🇵🇭",
                        "TH": "Thailand 🇹🇭",
                        "VN": "Vietnam 🇻🇳",
                        "ID": "Indonesia 🇮🇩",
                        "MY": "Malaysia 🇲🇾",
                        "SG": "Singapore 🇸🇬",
                        "NZ": "New Zealand 🇳🇿",
                        "IE": "Ireland 🇮🇪",
                        "PT": "Portugal 🇵🇹",
                        "GR": "Greece 🇬🇷",
                        "CZ": "Czech Republic 🇨🇿",
                        "HU": "Hungary 🇭🇺",
                        "RO": "Romania 🇷🇴",
                        "UA": "Ukraine 🇺🇦",
                        "IL": "Israel 🇮🇱",
                        "PK": "Pakistan 🇵🇰",
                        "BD": "Bangladesh 🇧🇩",
                    }
                    
                    country_display = country_names.get(country_code, f"{country_code}")
                    
                    embed = discord.Embed(
                        description=f"**{username}**'s TikTok country is **{country_display}**",
                        color=Config.COLORS.DEFAULT
                    )
                    
                    embed.set_footer(text="This data is provided by TikTok and is considered public")
                    
                    await ctx.send(embed=embed)
                    
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return await ctx.deny("Failed to connect to TikTok. The service may be temporarily unavailable")
        except Exception as e:
            return await ctx.deny(f"An error occurred: {str(e)}")
    
    @commands.command(name="minecraft", aliases=["mc"], help="View Minecraft player information")
    @example(",minecraft Notch")
    async def minecraft(self, ctx, username: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.mojang.com/users/profiles/minecraft/{username}") as r:
                if r.status != 200:
                    return await ctx.warn(f"I couldn't find a Minecraft player named `{username}`")
                
                data = await r.json()
                uuid = data["id"]
                name = data["name"]
            
            async with session.get(f"https://sessionserver.mojang.com/session/minecraft/profile/{uuid}") as r:
                if r.status != 200:
                    return await ctx.warn("Failed to fetch player profile")
                
                profile_data = await r.json()
        
        formatted_uuid = f"{uuid[:8]}-{uuid[8:12]}-{uuid[12:16]}-{uuid[16:20]}-{uuid[20:]}"
        skin_url = f"https://crafatar.com/renders/body/{uuid}?overlay"
        head_url = f"https://crafatar.com/avatars/{uuid}?overlay"
        
        embed = discord.Embed(
            title=f"Minecraft Player: {name}",
            color=Config.COLORS.DEFAULT
        )
        
        embed.set_author(
            name=str(ctx.author),
            icon_url=ctx.author.display_avatar.url
        )
        
        embed.set_thumbnail(url=head_url)
        embed.set_image(url=skin_url)
        
        embed.add_field(
            name="Info",
            value=f"> **Username:** {name}\n> **UUID:** `{formatted_uuid}`",
            inline=False
        )
        
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="NameMC",
                style=discord.ButtonStyle.link,
                url=f"https://namemc.com/profile/{name}"
            )
        )
        view.add_item(
            discord.ui.Button(
                label="Download Skin",
                style=discord.ButtonStyle.link,
                url=f"https://crafatar.com/skins/{uuid}"
            )
        )
        
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Social(bot))
