import io
import re
import discord
import aiohttp
import numpy as np
from PIL import Image
from discord.ext import commands
from discord.ui import View, Button
from discord.utils import format_dt
from discord import Embed, ButtonStyle, Member, User, Role, File
from discord.ext.commands import hybrid_command
import asyncio
import json
from typing import List, Dict, Union, Optional
from datetime import datetime, timedelta
from stare.core.tools.paginator import PaginatorView
from stare.core.config import Config
from stare.core.tools.context import CustomContext as Context
from io import BytesIO
from yarl import URL


class AddToServerView(discord.ui.View):
    def __init__(self, image_bytes: bytes, emoji_name: str):
        super().__init__(timeout=120)
        self.image_bytes = image_bytes
        self.emoji_name = emoji_name

    @discord.ui.button(label="Add to Server", style=discord.ButtonStyle.secondary)
    async def add_to_server(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_emojis:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{Config.EMOJIS.DENY} {interaction.user.mention}: You're missing the permission: `Manage Expressions`!",
                    color=Config.COLORS.DENY
                ),
                ephemeral=True
            )

        try:
            emoji = await interaction.guild.create_custom_emoji(
                name=self.emoji_name,
                image=self.image_bytes,
                reason=f"Emoji recolored and added by {interaction.user}"
            )

            button.style = discord.ButtonStyle.success
            button.disabled = True
            await interaction.message.edit(view=self)

            await interaction.response.send_message(
                content=f"I've added the **emoji** to this server as: <:{emoji.name}:{emoji.id}> (:**{emoji.name}**)",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{Config.EMOJIS.DENY} {interaction.user.mention}: Missing permission(s): `Manage Expressions`",
                    color=Config.COLORS.DENY
                ),
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{Config.EMOJIS.DENY} {interaction.user.mention}: Failed to add emoji: {e}",
                    color=Config.COLORS.DENY
                ),
                ephemeral=True
            )


def get_dominant_color(img: Image.Image) -> tuple:
    img = img.convert('RGBA')
    arr = np.array(img)

    mask = arr[:, :, 3] > 128
    pixels = arr[mask][:, :3]

    if len(pixels) == 0:
        return (0, 0, 0)

    img_small = img.convert('RGB').resize((50, 50), Image.LANCZOS)
    quantized = img_small.quantize(colors=5, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette()

    pixels_q = list(quantized.getdata())
    most_common_idx = max(set(pixels_q), key=pixels_q.count)

    r = palette[most_common_idx * 3]
    g = palette[most_common_idx * 3 + 1]
    b = palette[most_common_idx * 3 + 2]

    return (r, g, b)


class Utility(commands.Cog):
    """Utility commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.snipes: Dict[int, List[dict]] = {}
        self.edit_snipes: Dict[int, List[dict]] = {}
    
    def clean_old_snipes(self):
        now = datetime.utcnow()
        for channel_id in list(self.snipes.keys()):
            self.snipes[channel_id] = [s for s in self.snipes[channel_id] if now - s['time'] < timedelta(hours=2)]
            if not self.snipes[channel_id]:
                del self.snipes[channel_id]
        
        for channel_id in list(self.edit_snipes.keys()):
            self.edit_snipes[channel_id] = [s for s in self.edit_snipes[channel_id] if now - s['time'] < timedelta(hours=2)]
            if not self.edit_snipes[channel_id]:
                del self.edit_snipes[channel_id]
    
    async def cog_load(self):
        """Create utility tables"""
        if not hasattr(self.bot, 'db_pool') or not self.bot.db_pool:
            return
        
        try:
            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS afk (
                    user_id BIGINT,
                    guild_id BIGINT,
                    reason TEXT,
                    time TIMESTAMP,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)
            
            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS timezones (
                    user_id BIGINT PRIMARY KEY,
                    timezone TEXT
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    channel_id BIGINT,
                    reminder TEXT,
                    time TIMESTAMP
                )
            """)
            
            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS birthdays (
                    user_id BIGINT,
                    guild_id BIGINT,
                    month INTEGER,
                    day INTEGER,
                    year INTEGER,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)
            
            print("✅ Utility tables created/verified")
        except Exception as e:
            print(f"❌ Error creating utility tables: {e}")
    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or not message.content:
            return
        
        if message.channel.id not in self.snipes:
            self.snipes[message.channel.id] = []
        
        self.snipes[message.channel.id].insert(0, {
            'content': message.content,
            'author': message.author,
            'time': datetime.utcnow(),
            'attachments': [a.url for a in message.attachments]
        })
        
        if len(self.snipes[message.channel.id]) > 50:
            self.snipes[message.channel.id].pop()

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or before.content == after.content:
            return
        
        if before.channel.id not in self.edit_snipes:
            self.edit_snipes[before.channel.id] = []
        
        self.edit_snipes[before.channel.id].insert(0, {
            'before': before.content,
            'after': after.content,
            'author': before.author,
            'time': datetime.utcnow()
        })
        
        if len(self.edit_snipes[before.channel.id]) > 50:
            self.edit_snipes[before.channel.id].pop()
    
    @commands.command(aliases=["s"])
    async def snipe(self, ctx: Context):
        """View recently deleted messages"""
        self.clean_old_snipes()
        
        if ctx.channel.id not in self.snipes or not self.snipes[ctx.channel.id]:
            return await ctx.warn("No deleted messages **found**")
        
        embeds = []
        for snipe in self.snipes[ctx.channel.id][:10]:
            embed = discord.Embed(
                description=snipe['content'],
                color=Config.COLORS.DEFAULT,
                timestamp=snipe['time']
            )
            embed.set_author(name=str(snipe['author']), icon_url=snipe['author'].display_avatar.url)
            if snipe['attachments']:
                embed.set_image(url=snipe['attachments'][0])
            embeds.append(embed)
        
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            view = PaginatorView(embeds, user=ctx.author)
            await ctx.send(embed=embeds[0], view=view)
    
    @commands.command(aliases=["es"])
    async def editsnipe(self, ctx: Context):
        """View recently edited messages"""
        self.clean_old_snipes()
        
        if ctx.channel.id not in self.edit_snipes or not self.edit_snipes[ctx.channel.id]:
            return await ctx.warn("No edited messages found")
        
        embeds = []
        for snipe in self.edit_snipes[ctx.channel.id][:10]:
            embed = discord.Embed(color=Config.COLORS.DEFAULT, timestamp=snipe['time'])
            embed.set_author(name=str(snipe['author']), icon_url=snipe['author'].display_avatar.url)
            embed.add_field(name="Before", value=snipe['before'][:1024], inline=False)
            embed.add_field(name="After", value=snipe['after'][:1024], inline=False)
            embeds.append(embed)
        
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            view = PaginatorView(embeds, user=ctx.author)
            await ctx.send(embed=embeds[0], view=view)

    @commands.command(aliases=["cs"])
    @commands.has_permissions(manage_messages=True)
    async def clearsnipe(self, ctx: Context):
        """Clear snipes for this channel"""
        if ctx.channel.id in self.snipes:
            del self.snipes[ctx.channel.id]
        if ctx.channel.id in self.edit_snipes:
            del self.edit_snipes[ctx.channel.id]
        await ctx.message.add_reaction("👍")
    @hybrid_command(name="ping", aliases=["ws", "latency"])
    async def ping(self, ctx: Context):
        """Check the bot's latency"""
        latency = round(self.bot.latency * 1000)
        await ctx.approve(f"It took me **{latency}ms** to reach you!")

    @commands.command(aliases=["calc"])
    async def calculate(self, ctx: Context, *, expression: str):
        """Calculate a mathematical expression"""
        try:
            result = eval(expression, {"__builtins__": {}}, {})
            e = discord.Embed(
                color=Config.COLORS.DEFAULT,
                description=f"```{expression} = {result}```"
            )
            await ctx.send(embed=e)
        except:
            await ctx.warn("Invalid expression")
    
    @commands.command()
    async def poll(self, ctx: Context, *, question: str):
        """Create a poll"""
        e = discord.Embed(
            color=Config.COLORS.DEFAULT,
            description=f"📊 **{question}**"
        )
        e.set_author(name=f"Poll by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        e.set_footer(text="React to vote!")
        msg = await ctx.send(embed=e)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")
    
    @commands.command()
    async def invites(self, ctx: Context, member: discord.Member = None):
        """View invite count for a member"""
        m = member or ctx.author
        invites = await ctx.guild.invites()
        user_invites = [i for i in invites if i.inviter == m]
        total = sum(i.uses for i in user_invites)
        
        e = discord.Embed(
            color=Config.COLORS.DEFAULT,
            description=f"{m.mention} has **{total}** invites"
        )
        await ctx.send(embed=e)
    @commands.group(invoke_without_command=True)
    async def emoji(self, ctx: Context):
        """Emoji management commands"""
        await ctx.send_help(ctx.command)
    
    @emoji.command(name='add')
    @commands.has_permissions(manage_emojis=True)
    async def emoji_add(self, ctx: Context, emoji: Union[discord.PartialEmoji, str], *, name: str = None):
        """Add an emoji to the server"""
        if isinstance(emoji, str):
            if emoji.startswith('http'):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(emoji) as resp:
                            if resp.status != 200:
                                return await ctx.warn('Failed to download emoji')
                            image_data = await resp.read()
                    
                    emoji_name = name or 'emoji'
                    new_emoji = await ctx.guild.create_custom_emoji(name=emoji_name, image=image_data)
                    return await ctx.approve(f'Added emoji {new_emoji}')
                except Exception as e:
                    return await ctx.warn(f'Failed to add emoji: {str(e)}')
            else:
                return await ctx.warn('Please provide a valid emoji or URL')
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(emoji.url) as resp:
                    if resp.status != 200:
                        return await ctx.warn('Failed to download emoji')
                    image_data = await resp.read()
            
            emoji_name = name or emoji.name
            new_emoji = await ctx.guild.create_custom_emoji(name=emoji_name, image=image_data)
            await ctx.approve(f'Added emoji {new_emoji}')
        except discord.HTTPException as e:
            if e.code == 30008:
                await ctx.warn('Maximum number of emojis reached')
            else:
                await ctx.warn(f'Failed to add emoji: {str(e)}')
        except Exception as e:
            await ctx.warn(f'Failed to add emoji: {str(e)}')
    
    @emoji.command(name='steal')
    @commands.has_permissions(manage_emojis=True)
    async def emoji_steal(self, ctx: Context, emoji: Union[discord.PartialEmoji, str], *, name: str = None):
        """Steal an emoji from another server"""
        if isinstance(emoji, str):
            if emoji.startswith('http'):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(emoji) as resp:
                            if resp.status != 200:
                                return await ctx.warn('Failed to download emoji')
                            image_data = await resp.read()
                    
                    emoji_name = name or 'emoji'
                    new_emoji = await ctx.guild.create_custom_emoji(name=emoji_name, image=image_data)
                    return await ctx.approve(f'Stole emoji {new_emoji}')
                except Exception as e:
                    return await ctx.warn(f'Failed to steal emoji: {str(e)}')
            else:
                return await ctx.warn('Please provide a valid emoji or URL')
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(emoji.url) as resp:
                    if resp.status != 200:
                        return await ctx.warn('Failed to download emoji')
                    image_data = await resp.read()
            
            emoji_name = name or emoji.name
            new_emoji = await ctx.guild.create_custom_emoji(name=emoji_name, image=image_data)
            await ctx.approve(f'Stole emoji {new_emoji}')
        except discord.HTTPException as e:
            if e.code == 30008:
                await ctx.warn('Maximum number of emojis reached')
            else:
                await ctx.warn(f'Failed to steal emoji: {str(e)}')
        except Exception as e:
            await ctx.warn(f'Failed to steal emoji: {str(e)}')
    
    @emoji.command(name='remove', aliases=['delete'])
    @commands.has_permissions(manage_emojis=True)
    async def emoji_remove(self, ctx: Context, emoji: discord.Emoji):
        """Remove an emoji from the server"""
        if emoji.guild_id != ctx.guild.id:
            return await ctx.warn('That emoji is not from this server')
        
        try:
            await emoji.delete(reason=f'Deleted by {ctx.author}')
            await ctx.approve(f'Deleted emoji `:{emoji.name}:`')
        except Exception as e:
            await ctx.warn(f'Failed to delete emoji: {str(e)}')
    
    @emoji.command(name='rename')
    @commands.has_permissions(manage_emojis=True)
    async def emoji_rename(self, ctx: Context, emoji: discord.Emoji, *, name: str):
        """Rename an emoji"""
        if emoji.guild_id != ctx.guild.id:
            return await ctx.warn('That emoji is not from this server')
        
        old_name = emoji.name
        try:
            await emoji.edit(name=name, reason=f'Renamed by {ctx.author}')
            await ctx.approve(f'Renamed emoji from `:{old_name}:` to `:{name}:`')
        except Exception as e:
            await ctx.warn(f'Failed to rename emoji: {str(e)}')
    
    @emoji.command(name='image')
    async def emoji_image(self, ctx: Context, *, name: str):
        """Get the image URL of an emoji by name"""
        emoji = discord.utils.get(ctx.guild.emojis, name=name)
        
        if not emoji:
            return await ctx.warn(f'No emoji found with name `{name}`')
        
        e = discord.Embed(
            color=Config.COLORS.DEFAULT,
            title=f":{emoji.name}:",
            url=emoji.url
        )
        e.set_image(url=emoji.url)
        e.add_field(name="URL", value=f"[Click here]({emoji.url})", inline=False)
        await ctx.send(embed=e)
    
    @emoji.command(name='remix', aliases=['combine', 'merge'])
    async def emoji_remix(self, ctx: Context, *, emojis: str):
        """Combine two emojis into a single emoji"""
        emojis_list = [
            emoji
            for emoji in list("".join(char for char in emojis if char != "\ufe0f"))
            if emoji.strip()
        ]
        
        if len(emojis_list) != 2:
            return await ctx.warn("You need to provide exactly two emojis to remix")

        response = await self.bot.session.get(
            URL.build(
                scheme="https",
                host="tenor.googleapis.com",
                path="/v2/featured",
                query={
                    "key": "AIzaSyACvEq5cnT7AcHpDdj64SE3TJZRhW-iHuo",
                    "client_key": "emoji_kitchen_funbox",
                    "q": "_".join(emojis_list),
                    "collection": "emoji_kitchen_v6",
                    "contentfilter": "high",
                },
            )
        )
        data = await response.json()
        if not data.get("results"):
            return await ctx.warn("Those emojis aren't able to be combined")

        response = await self.bot.session.get(data["results"][0]["url"])
        buffer = await response.read()
        return await ctx.reply(file=File(BytesIO(buffer), "emoji.png"))

    @emoji.command(name='recolor')
    @commands.has_permissions(manage_emojis=True)
    async def emoji_recolor(self, ctx: Context, emoji: str, hex_color: str = None):
        """Recolor an emoji to a given hex color"""
        if not hex_color:
            return await ctx.warn('Please provide a valid **hex color**.')

        hex_clean = hex_color.lstrip('#')
        if not re.fullmatch(r'[0-9a-fA-F]{6}', hex_clean):
            return await ctx.warn('Please provide a valid **hex color**.')

        r = int(hex_clean[0:2], 16)
        g = int(hex_clean[2:4], 16)
        b = int(hex_clean[4:6], 16)

        custom_match = re.match(r'<a?:(\w+):(\d+)>', emoji)
        if not custom_match:
            return await ctx.warn('Please provide a **custom emoji** from this or another server.')

        emoji_name = custom_match.group(1)
        emoji_id = int(custom_match.group(2))
        animated = emoji.startswith('<a:')
        ext = 'gif' if animated else 'png'
        url = f'https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=128'

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return await ctx.warn('Could not download the emoji image.')
                img_bytes = await resp.read()

        img = Image.open(io.BytesIO(img_bytes)).convert('RGBA')

        # Preserve the original alpha channel
        _, _, _, a_ch = img.split()

        # Convert target color to HSV
        import colorsys
        target_h, target_s, _ = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)

        # Convert image RGB to HSV using numpy (vectorized)
        rgb_arr = np.array(img.convert('RGB'), dtype=np.float32) / 255.0
        hsv_img = Image.fromarray((rgb_arr * 255).astype(np.uint8)).convert('HSV') if hasattr(Image, 'HSV') else None

        # Manual vectorized HSV conversion
        Cmax = rgb_arr.max(axis=2)
        Cmin = rgb_arr.min(axis=2)
        delta = Cmax - Cmin

        # Value = Cmax (keep original brightness)
        V = Cmax

        # Replace hue and saturation with target color's values
        # Then convert back HSV -> RGB
        H = np.full(V.shape, target_h, dtype=np.float32)
        S = np.full(V.shape, target_s, dtype=np.float32)

        # HSV to RGB vectorized
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

        # Send as plain file + button, no embed
        file = discord.File(io.BytesIO(image_bytes), filename=f'{emoji_name}.png')
        embed = discord.Embed(
            description=f"Recolored **:{emoji_name}:** to `#{hex_clean.upper()}`",
            color=int(hex_clean, 16)
        )
        embed.set_image(url=f'attachment://{emoji_name}.png')

        await ctx.send(embed=embed, file=file, view=AddToServerView(image_bytes, emoji_name))

    @commands.command(name='dominant', aliases=['dom'])
    async def dominant(self, ctx: Context, target: str = None):
        """View the dominant color of an image"""
        img_bytes = None
        image_url = None

        if target and target.startswith('http'):
            image_url = target
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status == 200:
                        img_bytes = await resp.read()

        elif target:
            user_match = re.match(r'<@!?(\d+)>', target)
            if user_match:
                user_id = int(user_match.group(1))
                user = ctx.guild.get_member(user_id) or await self.bot.fetch_user(user_id)
                if user:
                    image_url = str(user.display_avatar.url)
                    async with aiohttp.ClientSession() as session:
                        async with session.get(image_url) as resp:
                            if resp.status == 200:
                                img_bytes = await resp.read()

        if not img_bytes and ctx.message.attachments:
            img_bytes = await ctx.message.attachments[0].read()
            image_url = ctx.message.attachments[0].url

        if not img_bytes and ctx.message.reference:
            ref = ctx.message.reference.resolved
            if ref and ref.attachments:
                img_bytes = await ref.attachments[0].read()
                image_url = ref.attachments[0].url

        if not img_bytes:
            return await ctx.warn('Please provide an **image**, **URL**, or **user mention**.')

        img = Image.open(io.BytesIO(img_bytes))
        dom_r, dom_g, dom_b = get_dominant_color(img)
        hex_str = f'{dom_r:02X}{dom_g:02X}{dom_b:02X}'
        color_int = (dom_r << 16) + (dom_g << 8) + dom_b

        embed = discord.Embed(color=color_int)
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        embed.set_thumbnail(url=image_url)
        embed.add_field(name='Hex', value=f'**`#{hex_str}`**', inline=True)
        embed.add_field(name='RGB', value=f'**`{dom_r}, {dom_g}, {dom_b}`**', inline=True)
        embed.set_footer(
            text=ctx.guild.name,
            icon_url=ctx.guild.icon.url if ctx.guild.icon else None
        )

        await ctx.send(embed=embed)
    @commands.command(aliases=['inr'])
    async def perms(self, ctx: Context, member: discord.Member = None):
        """View permissions for a member"""
        m = member or ctx.author
        perms = [p[0].replace('_', ' ').title() for p in m.guild_permissions if p[1]]
        
        embeds = []
        for i in range(0, len(perms), 15):
            chunk = perms[i:i+15]
            desc = "\n".join([f"• {p}" for p in chunk])
            embed = discord.Embed(
                color=Config.COLORS.DEFAULT,
                title=f"Permissions for {m.display_name}",
                description=desc
            )
            embeds.append(embed)
        
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            paginator = PaginatorView(embeds, user=ctx.author)
            await ctx.send(embed=embeds[0], view=paginator)
    
    @commands.command()
    async def permissions(self, ctx: Context, role: discord.Role):
        """View permissions for a role"""
        perms = [p[0].replace('_', ' ').title() for p in role.permissions if p[1]]
        
        embeds = []
        for i in range(0, len(perms), 15):
            chunk = perms[i:i+15]
            desc = "\n".join([f"• {p}" for p in chunk])
            embed = discord.Embed(
                color=Config.COLORS.DEFAULT,
                title=f"Permissions for {role.name}",
                description=desc
            )
            embeds.append(embed)
        
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            paginator = PaginatorView(embeds, user=ctx.author)
            await ctx.send(embed=embeds[0], view=paginator)
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        
        if not message.guild:
            return
        
        if not self.bot.db_pool:
            return
        
        try:
            check = await self.bot.db_pool.fetchrow(
                "SELECT reason, time FROM afk WHERE user_id = $1 AND guild_id = $2",
                message.author.id, message.guild.id
            )
            
            if check:
                await self.bot.db_pool.execute(
                    "DELETE FROM afk WHERE user_id = $1 AND guild_id = $2",
                    message.author.id, message.guild.id
                )
                timestamp = int(check['time'].timestamp())
                await message.channel.send(
                    f"Welcome back {message.author.mention}, you were afk <t:{timestamp}:R>",
                    delete_after=5
                )
            
            for mention in message.mentions:
                afk_check = await self.bot.db_pool.fetchrow(
                    "SELECT reason, time FROM afk WHERE user_id = $1 AND guild_id = $2",
                    mention.id, message.guild.id
                )
                if afk_check:
                    timestamp = int(afk_check['time'].timestamp())
                    await message.channel.send(
                        f"{mention.mention} is afk: {afk_check['reason']} - <t:{timestamp}:R>",
                        delete_after=10
                    )
        except Exception as e:
            pass
    
    @commands.command()
    async def afk(self, ctx: Context, *, reason: str = "AFK"):
        """Set yourself as AFK"""
        await self.bot.db_pool.execute(
            "INSERT INTO afk (user_id, guild_id, reason, time) VALUES ($1, $2, $3, $4) ON CONFLICT (user_id, guild_id) DO UPDATE SET reason = $3, time = $4",
            ctx.author.id, ctx.guild.id, reason, datetime.utcnow()
        )
        await ctx.message.add_reaction("👍")
    @commands.command()
    async def support(self, ctx: Context):
        """Submit a support request to bot owners"""
        from stare.plugins.developer.owner import SupportModal
        
        modal = SupportModal(self.bot)
        
        view = discord.ui.View()
        button = discord.ui.Button(label="Open Support Form", style=discord.ButtonStyle.primary)
        
        async def button_callback(interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("This is not your support request!", ephemeral=True)
            await interaction.response.send_modal(modal)
        
        button.callback = button_callback
        view.add_item(button)
        
        await ctx.approve("Click the button below to open the support form", view=view)
    @commands.command(aliases=['embedmaker', 'eb'])
    @commands.has_permissions(manage_messages=True)
    async def embed(self, ctx: Context, *, json_code: str = None):
        """Create an embed from JSON code"""
        if not json_code:
            example = {
                "title": "Example Embed",
                "description": "Use JSON to create embeds!",
                "color": Config.COLORS.DEFAULT,
                "fields": [
                    {"name": "Field Name", "value": "Field Value", "inline": False}
                ]
            }
            example_json = json.dumps(example, indent=2)
            return await ctx.send(
                f"**Embed Maker**\n"
                f"Use `;embed` with JSON code to create an embed.\n\n"
                f"Example:\n```json\n{example_json}\n```"
            )
        
        json_code = json_code.strip()
        if json_code.startswith('```'):
            json_code = json_code.strip('`')
            if json_code.startswith('json'):
                json_code = json_code[4:]
            json_code = json_code.strip()
        
        try:
            data = json.loads(json_code)
        except json.JSONDecodeError as e:
            return await ctx.warn(f"Invalid JSON: {str(e)}")
        
        try:
            if 'embeds' in data and isinstance(data['embeds'], list):
                embeds = []
                for embed_data in data['embeds']:
                    embed = self._create_embed_from_data(embed_data)
                    embeds.append(embed)
                
                view = None
                if 'components' in data:
                    view = self._create_view_from_components(data['components'])
                
                if embeds:
                    await ctx.send(embeds=embeds, view=view)
                else:
                    return await ctx.warn("No valid embeds found")
            else:
                embed = self._create_embed_from_data(data)
                await ctx.send(embed=embed)
            
            try:
                await ctx.message.delete()
            except:
                pass
                
        except Exception as e:
            return await ctx.warn(f"Error creating embed: {str(e)}")
    
    def _create_embed_from_data(self, data: dict) -> discord.Embed:
        embed = discord.Embed()
        
        if 'title' in data:
            embed.title = data['title']
        if 'description' in data:
            embed.description = data['description']
        
        if not embed.description:
            embed.description = "\u200b"
        
        if 'color' in data:
            embed.color = data['color']
        elif 'colour' in data:
            embed.color = data['colour']
        else:
            embed.color = Config.COLORS.DEFAULT
        
        if 'url' in data:
            embed.url = data['url']
        
        if 'timestamp' in data:
            if data['timestamp'] == 'now':
                embed.timestamp = datetime.utcnow()
        
        if 'author' in data:
            author = data['author']
            embed.set_author(
                name=author.get('name', ''),
                url=author.get('url'),
                icon_url=author.get('icon_url')
            )
        
        if 'footer' in data:
            footer = data['footer']
            embed.set_footer(
                text=footer.get('text', ''),
                icon_url=footer.get('icon_url')
            )
        
        if 'thumbnail' in data and data['thumbnail'].get('url'):
            embed.set_thumbnail(url=data['thumbnail']['url'])
        
        if 'image' in data and data['image'].get('url'):
            embed.set_image(url=data['image']['url'])
        
        if 'fields' in data:
            for field in data['fields']:
                embed.add_field(
                    name=field.get('name', 'Field'),
                    value=field.get('value', 'Value'),
                    inline=field.get('inline', False)
                )
        
        return embed
    
    def _create_view_from_components(self, components: list) -> View:
        view = View(timeout=None)
        
        for action_row in components:
            if action_row.get('type') != 1:
                continue
            
            for component in action_row.get('components', []):
                if component.get('type') == 2:
                    style = component.get('style', 1)
                    label = component.get('label', 'Button')
                    url = component.get('url')
                    
                    if style == 5:
                        button = Button(style=ButtonStyle.link, label=label, url=url)
                    else:
                        button = Button(style=ButtonStyle(style), label=label, disabled=True)
                    
                    view.add_item(button)
        
        return view


async def setup(bot):
    await bot.add_cog(Utility(bot))
