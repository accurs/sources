import discord
import base64
from discord.ext import commands
from datetime import datetime
from discord.ui import View, Button, Select
from discord.utils import format_dt
import aiohttp
import http.client
import json
from urllib.parse import quote
import io
import re
import asyncio
from stare.core.config import Config
from stare.core.tools.context import CustomContext as Context
from stare.network.instagram import get_profile as get_instagram_profile
from stare.network.tiktok import get_profile as get_tiktok_profile
from stare.network.roblox import get_profile as get_roblox_profile, get_user_groups, get_user_badges, get_rolimons_data
from stare.network.valorant import get_profile as get_valorant_profile
from stare.network.screenshot import capture_screenshot
from stare.network.minecraft import get_full_data
from stare.network.cashapp import get_cashapp as get_cashapp_data, get_cashapp_qr

HAUNT_API_KEY = "xextiNirHxBB79mbdiyxfj3yVfRyNGmo"
HAUNT_API_URL = "https://haunt.gg/api/lookup/username/{username}?key=" + HAUNT_API_KEY


class Social(commands.Cog):
    """Social media and profile lookup commands"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="haunt", description="Lookup a user on haunt.gg")
    async def haunt(self, ctx: Context, username: str = None):
        """Lookup a user on haunt.gg"""
        if not username:
            return await ctx.send_help(ctx.command)

        async with aiohttp.ClientSession() as session:
            url = HAUNT_API_URL.format(username=username)
            async with session.get(url) as response:
                if response.status != 200:
                    return await ctx.warn(f"I **couldn't** find a profile for `@{username}`.")
                data = await response.json()

        if not data or data.get("error"):
            return await ctx.warn(f"I **couldn't** find a profile for `@{username}`.")

        uid = data.get("uid", "N/A")
        display_username = data.get("displayUsername", username)
        raw_username = data.get("username", username)
        view_count = data.get("viewCount", 0)
        created_at = data.get("createdAt", 0)
        profile = data.get("profile", {})
        badges = data.get("badges", [])
        custom_badges = data.get("customBadges", [])
        links = data.get("links", [])
        avatar = profile.get("avatar", None)

        about_me = profile.get("aboutMe") or profile.get("description") or "No description set."

        relative_timestamp = f"<t:{created_at}:R>" if created_at else "Unknown"

        badge_count = len(badges)
        custom_badge_count = len(custom_badges)
        link_count = len(links)

        embed = discord.Embed(
            color=15957427,
            url=f"https://haunt.gg/{raw_username}",
            title=f"{display_username} (@{raw_username})",
            description=f"<:reply:1477391892193869925> **{about_me}**",
        )

        embed.set_author(
            name=str(ctx.author),
            icon_url=ctx.author.display_avatar.url,
        )

        if avatar:
            embed.set_thumbnail(url=avatar)

        embed.add_field(
            name="Statistics:",
            value=(
                f"> **UID**: `{uid}`\n"
                f"> **Views**: `{view_count}`\n"
                f"> **Created**: {relative_timestamp}"
            ),
            inline=True,
        )

        embed.add_field(
            name="Socials:",
            value=(
                f"> **Badges**: `{badge_count}`\n"
                f"> **Custom Badges**: `{custom_badge_count}`\n"
                f"> **Links**: `{link_count}`"
            ),
            inline=True,
        )

        haunt_emoji = discord.PartialEmoji(id=1477391259990626357, name="haunt", animated=False)

        view = View()
        view.add_item(Button(
            label="Icon",
            style=discord.ButtonStyle.link,
            url=avatar if avatar else f"https://haunt.gg/{raw_username}",
            emoji=haunt_emoji,
        ))

        backgrounds = data.get("backgrounds", [])
        active_bg = next((b for b in backgrounds if b.get("active")), None)
        background = active_bg.get("backgroundUrl") if active_bg else None
        view.add_item(Button(
            label="Background",
            style=discord.ButtonStyle.link,
            url=background if background else f"https://haunt.gg/{raw_username}",
            emoji=haunt_emoji,
        ))

        await ctx.send(embed=embed, view=view)

    @commands.command(name="angelz")
    async def angelz(self, ctx: Context, username: str = None):
        """Lookup a user on angelz.bio"""
        if not username:
            return await ctx.warn('You need to provide a **username**')

        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://angelz.bio/api/profile?username={username}") as r:
                if r.status != 200:
                    return await ctx.warn(f"I **couldn't** find a profile for `@{username}`.")
                data = await r.json()

        if not data or data.get("error"):
            return await ctx.warn(f"I **couldn't** find a profile for `@{username}`.")

        uid         = data.get("uid", "N/A")
        views       = data.get("views", "N/A")
        display     = data.get("display_name", username)
        user        = data.get("username", username)
        description = data.get("bio", "")
        location    = data.get("location", "N/A") or "N/A"

        alias_raw = data.get("alias", "") or ""
        alias     = ", ".join(alias_raw.split(",")) if alias_raw else "None"

        avatar_url     = data.get("avatar") or None
        background_url = data.get("page_bg") or None


        embed = discord.Embed(
            title=f"{display} (@{user})",
            url=f"https://angelz.bio/{user}",
            description=description,
            color=0x000000
        )

        embed.set_author(
            name=str(ctx.author),
            icon_url=ctx.author.display_avatar.url
        )

        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        embed.add_field(
            name="Statistics:",
            value=f"**UID**: `{uid}`\n**Views**: `{views}`\n**Location**: {location}",
            inline=True
        )

        embed.add_field(
            name="Aliases:",
            value=f"```ansi\n\u001b[2;37m{alias}\u001b[0m\n```",
            inline=True
        )

        view = View()

        view.add_item(Button(
            label="Icon",
            style=discord.ButtonStyle.link,
            url=avatar_url if avatar_url else f"https://angelz.bio/{user}",
            emoji=discord.PartialEmoji(id=1476690758726713568, name="angelz", animated=False)
        ))

        view.add_item(Button(
            label="Background",
            style=discord.ButtonStyle.link,
            url=background_url if background_url else f"https://angelz.bio/{user}",
            emoji=discord.PartialEmoji(id=1476690758726713568, name="angelz", animated=False)
        ))

        await ctx.send(embed=embed, view=view)

    @commands.group(name="tiktok", aliases=["tt"], invoke_without_command=True)
    async def tiktok(self, ctx: Context, username: str = None):
        """Get TikTok user information"""
        if not username:
            return await ctx.warn('You need to provide a **username**')

        username = username.lstrip('@')
        data = await get_tiktok_profile(username)

        if not data:
            return await ctx.warn(f'Could not find user **{username}**')

        user_info = data.get('user', {})
        stats = data.get('stats', {})

        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(
            name=f"{user_info.get('nickname', username)} (@{user_info.get('uniqueId', username)})",
            icon_url=user_info.get('avatarLarger', '')
        )
        embed.set_thumbnail(url=user_info.get('avatarLarger', ''))

        if user_info.get('signature'):
            embed.add_field(name='Bio', value=user_info['signature'], inline=False)

        embed.add_field(name='Followers', value=f"{stats.get('followerCount', 0):,}", inline=True)
        embed.add_field(name='Following', value=f"{stats.get('followingCount', 0):,}", inline=True)

        likes = stats.get('heart', stats.get('heartCount', 0))
        embed.add_field(name='Likes', value=f"{likes:,}", inline=True)
        embed.add_field(name='Videos', value=f"{stats.get('videoCount', 0):,}", inline=True)

        if user_info.get('verified'):
            embed.add_field(name='Verified', value='✓', inline=True)

        await ctx.send(embed=embed)

    @tiktok.command(name='repost', aliases=['download', 'dl'])
    async def tiktok_repost(self, ctx: Context, url: str):
        """Download a TikTok video"""
        if 'tiktok.com' not in url:
            return await ctx.warn('Invalid TikTok URL')

        msg = await ctx.send(embed=discord.Embed(
            description='Downloading video...',
            color=Config.COLORS.DEFAULT
        ))

        try:
            conn = http.client.HTTPSConnection("tiktok-video-no-watermark2.p.rapidapi.com")
            payload = f"url={url}&hd=0"
            headers = {
                'x-rapidapi-key': Config.KEYS.RAPIDAPI,
                'x-rapidapi-host': "tiktok-video-no-watermark2.p.rapidapi.com",
                'Content-Type': "application/x-www-form-urlencoded"
            }

            conn.request("POST", "/", payload, headers)
            res = conn.getresponse()
            data = json.loads(res.read().decode("utf-8"))

            if data.get('code') != 0 or 'data' not in data:
                return await ctx.warn('Could not download video')

            video_url = data['data']['play']
            description = data['data'].get('title', 'No description available')

            async with aiohttp.ClientSession() as session:
                async with session.get(video_url) as video_resp:
                    if video_resp.status != 200:
                        return await ctx.warn('Failed to download video')
                    video_data = await video_resp.read()

            video_size_mb = len(video_data) / (1024 * 1024)

            if video_size_mb > 25:
                await msg.delete()
                return await ctx.warn(f'Video is too large ({video_size_mb:.1f}MB). Discord limit is 25MB.')

            video_file = discord.File(io.BytesIO(video_data), filename='tiktok.mp4')
            embed = discord.Embed(color=Config.COLORS.DEFAULT)
            embed.description = description

            await msg.delete()
            await ctx.send(embed=embed, file=video_file)
        except discord.HTTPException as e:
            try:
                await msg.delete()
            except:
                pass
            if e.code == 40005:
                await ctx.warn('Video is too large for Discord (max 25MB)')
            else:
                await ctx.warn('Failed to upload video')
        except Exception as e:
            try:
                await msg.delete()
            except:
                pass
            await ctx.warn('Failed to process video')

    @commands.command(aliases=['ig'])
    async def instagram(self, ctx: Context, username: str = None):
        """Get Instagram user information"""
        if not username:
            return await ctx.warn('You need to provide a **username**')

        username = username.lstrip('@')
        loading_msg = await ctx.loading(f'Fetching Instagram profile for **@{username}**...')

        try:
            user = await get_instagram_profile(username)

            if not user:
                await loading_msg.delete()
                return await ctx.warn(f'Could not find Instagram user **@{username}**')

            full_name = user.get('full_name', username)
            ig_username = user.get('username', username)
            profile_pic = user.get('profile_pic_url', '')
            biography = user.get('biography', '')
            is_verified = user.get('is_verified', False)
            is_private = user.get('is_private', False)

            followers = 0
            following = 0
            posts = 0

            if 'follower_count' in user:
                followers = user['follower_count']
            elif 'edge_followed_by' in user:
                if isinstance(user['edge_followed_by'], dict):
                    followers = user['edge_followed_by'].get('count', 0)
                else:
                    followers = user['edge_followed_by']

            if 'following_count' in user:
                following = user['following_count']
            elif 'edge_follow' in user:
                if isinstance(user['edge_follow'], dict):
                    following = user['edge_follow'].get('count', 0)
                else:
                    following = user['edge_follow']

            if 'media_count' in user:
                posts = user['media_count']
            elif 'edge_owner_to_timeline_media' in user:
                if isinstance(user['edge_owner_to_timeline_media'], dict):
                    posts = user['edge_owner_to_timeline_media'].get('count', 0)
                else:
                    posts = user['edge_owner_to_timeline_media']

            embed = discord.Embed(color=Config.COLORS.DEFAULT)
            embed.set_author(
                name=f"{full_name} (@{ig_username})",
                icon_url=profile_pic
            )
            embed.set_thumbnail(url=profile_pic)

            if biography:
                embed.add_field(name='Bio', value=biography[:1024], inline=False)

            embed.add_field(name='Followers', value=f"{followers:,}", inline=True)
            embed.add_field(name='Following', value=f"{following:,}", inline=True)
            embed.add_field(name='Posts', value=f"{posts:,}", inline=True)

            if is_verified:
                embed.add_field(name='Verified', value='✓', inline=True)

            if is_private:
                embed.add_field(name='Private', value='Yes', inline=True)

            embed.set_footer(text='Instagram')

            profile_url = f"https://www.instagram.com/{ig_username}/"
            view = View()
            view.add_item(Button(label='View Profile', style=discord.ButtonStyle.link, url=profile_url))

            await loading_msg.delete()
            await ctx.send(embed=embed, view=view)

        except Exception as e:
            try:
                await loading_msg.delete()
            except:
                pass
            print(f"Instagram command error: {e}")
            return await ctx.warn(f'Failed to fetch Instagram profile. The API might be unavailable.')

    @commands.command(aliases=['ss', 'webshot'])
    async def screenshot(self, ctx: Context, url: str = None, width: int = 1920, height: int = 1080, fullpage: str = 'false'):
        if not url:
            return await ctx.warn('You need to provide a **URL**')

        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'

        fullpage_bool = fullpage.lower() in ('true', 'yes', '1')
        loading_msg = await ctx.send(f"Capturing screenshot of `{url}`")

        try:
            data = await capture_screenshot(url, width, height, fullpage_bool)

            if not data:
                await loading_msg.delete()
                return await ctx.warn('Failed to capture screenshot. Please check the URL and try again.')

            screenshot_bytes = data.get('screenshot')
            if not screenshot_bytes:
                await loading_msg.delete()
                return await ctx.warn('Screenshot data not found in response.')

            screenshot_file = discord.File(io.BytesIO(screenshot_bytes), filename='screenshot.png')

            embed = discord.Embed(color=Config.COLORS.DEFAULT)
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            embed.title = "Website Screenshot"
            embed.description = f"**URL:** {url}\n**Resolution:** {width}x{height}\n**Full Page:** {fullpage_bool}"
            embed.set_image(url='attachment://screenshot.png')
            embed.set_footer(text='Screenshot')

            view = View()
            view.add_item(Button(label='Open URL', style=discord.ButtonStyle.link, url=url))

            await loading_msg.delete()
            await ctx.send(embed=embed, file=screenshot_file, view=view)
        except Exception as e:
            await loading_msg.delete()
            return await ctx.warn(f'Failed to capture screenshot: {str(e)}')

    @commands.command(aliases=['rblx', 'rbx'])
    async def roblox(self, ctx: Context, username: str = None):
        """Get Roblox user information"""
        if not username:
            return await ctx.warn('You need to provide a **username**')

        data = await get_roblox_profile(username)

        if not data:
            return await ctx.warn(f'Could not find Roblox user **{username}**. Please check the username and try again.')

        user_id = data.get('id')
        if not user_id:
            return await ctx.warn(f'Could not find Roblox user **{username}**. Please check the username and try again.')

        try:
            created_date = datetime.fromisoformat(data['created'].replace('Z', '+00:00'))
            created_timestamp = int(created_date.timestamp())
            created_formatted = f"<t:{created_timestamp}:R>"
        except:
            created_formatted = data.get('created', 'Unknown')

        friends = data.get('friends')
        friends_str = f"{friends:,}" if friends is not None else 'N/A'
        followers = data.get('followers')
        followers_str = f"{followers:,}" if followers is not None else 'N/A'
        items = data.get('items')
        items_str = f"{items:,}" if items is not None else 'N/A'
        rap = data.get('rap')
        rap_str = f"{rap:,}" if rap is not None else 'N/A'
        value = data.get('value')
        value_str = f"{value:,}" if value is not None else 'N/A'

        verified_badge = '✓' if data.get('hasVerifiedBadge') else ''

        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        embed.title = f"{data.get('displayName', username)} {verified_badge}"
        embed.set_thumbnail(url=data.get('avatar', ''))

        embed.add_field(
            name='User Info',
            value=f"> Username: **@{data.get('name', username)}**\n" +
                  f"> User ID: **{user_id}**\n" +
                  f"> Created: {created_formatted}",
            inline=True
        )

        embed.add_field(
            name='Stats',
            value=f"> Status: **{data.get('presence', 'Unknown')}**\n" +
                  f"> Friends: **{friends_str}**\n" +
                  f"> Followers: **{followers_str}**",
            inline=True
        )

        embed.add_field(
            name='Inventory',
            value=f"> Items: **{items_str}**\n" +
                  f"> RAP: **{rap_str}**\n" +
                  f"> Value: **{value_str}**",
            inline=True
        )

        embed.set_footer(text='Roblox')

        profile_url = f"https://www.roblox.com/users/{user_id}/profile"
        view = View()
        view.add_item(Button(label='View Profile', style=discord.ButtonStyle.link, url=profile_url))

        await ctx.send(embed=embed, view=view)

    @commands.command(aliases=['val', 'valorantprofile'])
    async def valorant(self, ctx: Context, *, full_username: str = None):
        """Get Valorant user information"""
        if not full_username:
            return await ctx.warn('You need to provide a **username#tag** (e.g., TenZ#00005)')

        if '#' not in full_username:
            return await ctx.warn('Please provide a valid Valorant username with tag (e.g., TenZ#00005)')

        last_hash_index = full_username.rfind('#')
        username = full_username[:last_hash_index].strip()
        tag = full_username[last_hash_index + 1:].strip()

        loading_msg = await ctx.loading(f'Fetching Valorant profile for **{username}#{tag}**...')

        try:
            data = await get_valorant_profile(username, tag)

            if not data:
                await loading_msg.delete()
                return await ctx.warn(f'Could not find Valorant user **{username}#{tag}**. Please check the username and tag.')

            player_name = data.get('name', username)
            player_tag = data.get('tag', tag)
            player_region = data.get('region', 'Unknown')
            account_level = data.get('accountLevel', 'N/A')
            elo = data.get('elo', 'N/A')
            rank_rating = data.get('rankRating', 0)
            rank_image = data.get('rankImage', '')
            status = data.get('status', 'Offline')

            rank_number = data.get('rank', 0)
            rank_names = {
                0: 'Unranked', 3: 'Iron 1', 4: 'Iron 2', 5: 'Iron 3',
                6: 'Bronze 1', 7: 'Bronze 2', 8: 'Bronze 3',
                9: 'Silver 1', 10: 'Silver 2', 11: 'Silver 3',
                12: 'Gold 1', 13: 'Gold 2', 14: 'Gold 3',
                15: 'Platinum 1', 16: 'Platinum 2', 17: 'Platinum 3',
                18: 'Diamond 1', 19: 'Diamond 2', 20: 'Diamond 3',
                21: 'Ascendant 1', 22: 'Ascendant 2', 23: 'Ascendant 3',
                24: 'Immortal 1', 25: 'Immortal 2', 26: 'Immortal 3',
                27: 'Radiant'
            }
            current_rank = rank_names.get(rank_number, 'Unranked')

            card = data.get('card', {})
            card_large = card.get('large', '')
            card_wide = card.get('wide', '')

            embed = discord.Embed(
                color=Config.COLORS.DEFAULT,
                title=f"{player_name}#{player_tag}",
                description=f"Region: **{player_region}**"
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)

            thumbnail_url = card_large if card_large else 'https://i.imgur.com/8qJWL0S.png'
            embed.set_thumbnail(url=thumbnail_url)

            embed.add_field(
                name='User Info',
                value=f"> Username: **{player_name}#{player_tag}**\n" +
                      f"> Region: **{player_region}**\n" +
                      f"> Level: **{account_level}**",
                inline=True
            )

            embed.add_field(
                name='Ranked Stats',
                value=f"> Rank: **{current_rank}**\n" +
                      f"> RR: **{rank_rating}**\n" +
                      f"> Elo: **{elo}**",
                inline=True
            )

            embed.add_field(
                name='Additional',
                value=f"> Card: **{'Custom' if card_wide else 'Default'}**\n" +
                      f"> Status: **{status}**",
                inline=True
            )

            if card_wide:
                embed.set_image(url=card_wide)

            embed.set_footer(text='Valorant')

            tracker_url = data.get('trackerUrl', f"https://tracker.gg/valorant/profile/riot/{quote(player_name)}%23{quote(player_tag)}/overview")
            view = View()
            view.add_item(Button(label='View Profile', style=discord.ButtonStyle.link, url=tracker_url))

            await loading_msg.delete()
            await ctx.send(embed=embed, view=view)

        except Exception as e:
            try:
                await loading_msg.delete()
            except:
                pass
            print(f"Valorant command error: {e}")
            return await ctx.warn(f'Failed to fetch Valorant profile. The API might be unavailable.')

    @commands.command(aliases=['ca', 'cash'])
    async def cashapp(self, ctx: Context, username: str = None):
        """Get CashApp payment link with QR code"""
        if not username:
            return await ctx.warn('You need to provide a **CashApp username**')

        username = username.lstrip('$').lstrip('@')
        loading_msg = await ctx.send(f"Fetching CashApp for `${username}`")

        try:
            data = await get_cashapp_data(username)

            if not data:
                await loading_msg.delete()
                return await ctx.warn(f'Could not fetch CashApp data for **${username}**')

            cashapp_url = data.get('url', '')
            if not cashapp_url:
                await loading_msg.delete()
                return await ctx.warn(f'Could not generate CashApp link for **${username}**')

            qr_bytes = await get_cashapp_qr(username)

            embed = discord.Embed(color=Config.COLORS.DEFAULT)
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            embed.title = f"${username}"
            embed.description = f"**CashApp Payment Link**\n[Click here to send money]({cashapp_url})"

            if qr_bytes:
                qr_file = discord.File(io.BytesIO(qr_bytes), filename='cashapp_qr.png')
                embed.set_thumbnail(url='attachment://cashapp_qr.png')
            else:
                qr_file = None

            embed.set_footer(text='CashApp')

            view = View()
            view.add_item(Button(label='Open CashApp', style=discord.ButtonStyle.link, url=cashapp_url))

            await loading_msg.delete()
            if qr_file:
                await ctx.send(embed=embed, file=qr_file, view=view)
            else:
                await ctx.send(embed=embed, view=view)
        except Exception as e:
            await loading_msg.delete()
            return await ctx.warn(f'Failed to fetch CashApp data: {str(e)}')

    @commands.command(aliases=['mcprofile'])
    async def minecraft(self, ctx: Context, username: str = None):
        """Get Minecraft player information"""
        if not username:
            return await ctx.warn('You need to provide a **Minecraft username**')

        loading_msg = await ctx.send(f"Fetching Minecraft profile for `{username}`")

        try:
            data = await get_full_data(username)

            if not data:
                await loading_msg.delete()
                return await ctx.warn(f'Could not find Minecraft player **{username}**')

            player_name = data.get('name', username)
            player_uuid = data.get('id', 'N/A')
            player_uuid_dashed = data.get('uuid_dashed', 'N/A')

            skin_info = data.get('skin', {})
            cape_info = data.get('cape', {})
            profile_info = data.get('profile', {})

            skin_variant = 'Slim' if skin_info.get('variant') == 'slim' else 'Classic'
            has_cape = cape_info.get('has_cape', False)
            profile_id = profile_info.get('profile_id', 'N/A')

            name_history = data.get('name_history', [])
            total_names = len(name_history)

            previous_names = []
            if total_names > 1:
                for name_entry in name_history[:-1][:3]:
                    previous_names.append(name_entry.get('name', 'Unknown'))

            previous_names_str = ', '.join(previous_names) if previous_names else 'None'

            avatar_url = data.get('avatar', {}).get('url', f"https://visage.surgeplay.com/face/256/{player_uuid}")
            render_url = data.get('render', {}).get('url', f"https://visage.surgeplay.com/full/192/{player_uuid}")

            embed = discord.Embed(color=Config.COLORS.DEFAULT)
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            embed.title = f"{player_name}"
            embed.set_thumbnail(url=avatar_url)
            embed.set_image(url=render_url)

            embed.add_field(
                name='Player Info',
                value=f"> Username: **{player_name}**\n" +
                      f"> UUID: **{player_uuid}**\n" +
                      f"> Dashed UUID: **{player_uuid_dashed}**",
                inline=True
            )

            profile_id_display = f"{profile_id[:8]}..." if len(str(profile_id)) > 8 else profile_id
            embed.add_field(
                name='Skin Info',
                value=f"> Variant: **{skin_variant}**\n" +
                      f"> Cape: **{'Yes' if has_cape else 'No'}**\n" +
                      f"> Profile ID: **{profile_id_display}**",
                inline=True
            )

            embed.add_field(
                name='Name History',
                value=f"> Total Names: **{total_names}**\n" +
                      f"> Previous: **{previous_names_str}**\n" +
                      f"> Current: **{player_name}**",
                inline=True
            )

            embed.set_footer(text='Minecraft')

            namemc_url = f"https://namemc.com/profile/{player_name}"
            view = View()
            view.add_item(Button(label='NameMC Profile', style=discord.ButtonStyle.link, url=namemc_url))

            await loading_msg.delete()
            await ctx.send(embed=embed, view=view)
        except Exception as e:
            await loading_msg.delete()
            return await ctx.warn(f'Failed to fetch Minecraft profile: {str(e)}')

    async def _pinterest_search(self, query: str, limit: int = 9) -> list:
        """Helper method to search Pinterest"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://www.pinterest.com/search/pins/?q={quote(query)}&rs=typed",
                headers={
                    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                },
            ) as response:
                if response.status != 200:
                    return []
                html = await response.text()

        urls = re.findall(
            r'"url":"(https://i\.pinimg\.com/\d+x/[^"]+\.(?:jpg|jpeg|png|webp))"',
            html
        )

        return list(dict.fromkeys(urls))[:limit]

    @commands.group(aliases=["pin"], invoke_without_command=True)
    async def pinterest(self, ctx: Context) -> None:
        """Pinterest commands"""
        await ctx.send_help(ctx.command)

    @pinterest.command(name="search")
    @commands.cooldown(1, 5, commands.BucketType.member)
    async def pinterest_search(self, ctx: Context, *, query: str):
        """Search for images on Pinterest"""
        async with ctx.typing():
            try:
                image_urls = await self._pinterest_search(query)

                if not image_urls:
                    return await ctx.warn(f"No images found for **{query}**")

                async def fetch_image(url):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                return await resp.read()
                    return None

                images = await asyncio.gather(*[fetch_image(url) for url in image_urls])
                images = [img for img in images if img is not None]

                if not images:
                    return await ctx.warn(f"No images found for **{query}**")

                files = [
                    discord.File(io.BytesIO(image), filename=f"pinterest_{i+1}.png")
                    for i, image in enumerate(images)
                ]
                await ctx.send(f"Successfully searched for **{query}**.", files=files)

            except Exception as e:
                await ctx.warn(str(e))


async def setup(bot):
    await bot.add_cog(Social(bot))
