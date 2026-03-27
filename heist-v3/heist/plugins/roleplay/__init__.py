import discord
import aiohttp
import asyncio
from discord import app_commands, Embed, ui
from discord.ext.commands import Cog, hybrid_group
from discord.ext import commands
from typing import Optional, Union

class ActionButton(ui.View):
    def __init__(self, action: str, author: discord.Member, target: discord.Member, bot):
        super().__init__(timeout=60)
        self.action = action
        self.author = author
        self.target = target
        self.bot = bot
        self.clicked = False
        
        verb_map = {
            "slap": "Slap back",
            "hug": "Hug back", 
            "kiss": "Kiss back",
            "bite": "Bite back",
            "baka": "Call baka back",
            "cuddle": "Cuddle back",
            "feed": "Feed back",
            "handhold": "Hold hands back",
            "handshake": "Shake hands back",
            "highfive": "High five back",
            "kick": "Kick back",
            "pat": "Pat back",
            "punch": "Punch back",
            "peck": "Peck back",
            "poke": "Poke back",
            "shoot": "Shoot back"
        }
        
        button_label = verb_map.get(action, f"{action} back")
        
        self.button = ui.Button(
            label=button_label,
            style=discord.ButtonStyle.gray,
            emoji=discord.PartialEmoji(name="handsigns", id=1385054141784789133, animated=True)
        )
        self.button.callback = self.callback
        self.add_item(self.button)
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.target.id:
            await interaction.response.warn(f"Only {self.target.mention} can use this!", ephemeral=True)
            return
        
        if self.clicked:
            await interaction.response.warn("Already used!", ephemeral=True)
            return
        
        self.clicked = True
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(view=self)
        
        ordinal_count = await self.bot.get_cog("Roleplay").update_count(self.target.id, self.author.id, self.action)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://nekos.best/api/v2/{self.action}") as response:
                if response.status == 200:
                    data = await response.json()
                    gif_url = data['results'][0]['url']
                    anime_name = data['results'][0]['anime_name']
                else:
                    await interaction.followup.send("Failed to fetch GIF.")
                    return
        
        verb_conjugations = {
            "slap": "slaps",
            "hug": "hugs",
            "kiss": "kisses",
            "bite": "bites",
            "baka": "calls baka",
            "cuddle": "cuddles",
            "feed": "feeds",
            "handhold": "holds hands",
            "handshake": "shakes hands",
            "highfive": "high fives",
            "kick": "kicks",
            "pat": "pats",
            "punch": "punches",
            "peck": "pecks",
            "poke": "pokes",
            "shoot": "shoots"
        }
        
        conjugated_verb = verb_conjugations.get(self.action, f"{self.action}s")
        
        embed = Embed(
            description=f"**{self.target.mention}** **{conjugated_verb}** **{self.author.mention}** for the **{ordinal_count}** time!",
            color=self.bot.config.colors.information
        )
        embed.set_image(url=gif_url)
        embed.set_footer(text=f"From: {anime_name}")
        
        await interaction.followup.send(embed=embed)
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

class Roleplay(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def update_count(self, user_id: int, target_id: int, action: str) -> str:
        cache_key = f"action:{user_id}:{target_id}:{action}"
        
        try:
            cached = await self.bot.redis.redis.get(cache_key)
            if cached:
                count = int(cached) + 1
                await self.bot.redis.redis.set(cache_key, str(count))
            else:
                query = "SELECT count FROM user_actions WHERE user_id = $1 AND target_user_id = $2 AND action = $3"
                result = await self.bot.db.fetchrow(query, user_id, target_id, action)
                
                if result:
                    count = result['count'] + 1
                    update_query = "UPDATE user_actions SET count = $1 WHERE user_id = $2 AND target_user_id = $3 AND action = $4"
                    await self.bot.db.execute(update_query, count, user_id, target_id, action)
                else:
                    count = 1
                    insert_query = "INSERT INTO user_actions (user_id, target_user_id, action, count) VALUES ($1, $2, $3, $4)"
                    await self.bot.db.execute(insert_query, user_id, target_id, action, count)
                
                await self.bot.redis.redis.setex(cache_key, 3600, str(count))
        except Exception:
            count = 1
        
        if 10 <= count % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(count % 10, 'th')
        
        return f"{count}{suffix}"

    async def send_action_embed(self, ctx, user, action):
        ordinal_count = await self.update_count(ctx.author.id, user.id, action)
        
        async with self.session.get(f"https://nekos.best/api/v2/{action}") as response:
            if response.status == 200:
                data = await response.json()
                gif_url = data['results'][0]['url']
                anime_name = data['results'][0]['anime_name']
            else:
                await ctx.warn(f"Failed to fetch {action} GIF.")
                return
        
        verb_conjugations = {
            "slap": "slaps",
            "hug": "hugs",
            "kiss": "kisses",
            "bite": "bites",
            "baka": "calls baka",
            "cuddle": "cuddles",
            "feed": "feeds",
            "handhold": "holds hands",
            "handshake": "shakes hands",
            "highfive": "high fives",
            "kick": "kicks",
            "pat": "pats",
            "punch": "punches",
            "peck": "pecks",
            "poke": "pokes",
            "shoot": "shoots"
        }
        
        conjugated_verb = verb_conjugations.get(action, f"{action}s")
        
        embed = Embed(
            description=f"**{ctx.author.mention}** **{conjugated_verb}** **{user.mention}** for the **{ordinal_count}** time!",
            color=self.bot.config.colors.information
        )
        embed.set_image(url=gif_url)
        embed.set_footer(text=f"From: {anime_name}")
        
        if user.id != ctx.author.id:
            view = ActionButton(action, ctx.author, user, self.bot)
            message = await ctx.send(embed=embed, view=view)
            view.message = message
        else:
            await ctx.send(embed=embed)

    @hybrid_group(
        name="roleplay", 
        description="Roleplay related commands",
        aliases=["rp"],
        fallback="help"
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def roleplay(self, ctx):
        if ctx.invoked_subcommand is None:
            embed = Embed(
                title="Roleplay Commands",
                description="Use these commands to roleplay with other users!",
                color=self.bot.config.colors.information
            )
            
            commands = [
                "slap", "hug", "kiss", "bite", "baka", "cuddle", "feed", 
                "handhold", "handshake", "highfive", "kick", "pat", 
                "punch", "peck", "poke", "shoot", "cry"
            ]
            
            embed.add_field(
                name="Available Actions",
                value=", ".join(f"`{cmd}`" for cmd in commands),
                inline=False
            )
            
            embed.add_field(
                name="Usage",
                value=f"Use `{ctx.prefix}roleplay <action> [@user]` or `/roleplay <action> [user]`",
                inline=False
            )
            
            await ctx.send(embed=embed)

    @roleplay.command(name="slap", description="Slap someone")
    @app_commands.describe(user="The user to slap")
    async def slap(self, ctx, user: Optional[Union[discord.Member, discord.User]] = None):
        user = user or ctx.author
        await self.send_action_embed(ctx, user, "slap")

    @roleplay.command(name="hug", description="Hug someone")
    @app_commands.describe(user="The user to hug")
    async def hug(self, ctx, user: Optional[Union[discord.Member, discord.User]] = None):
        user = user or ctx.author
        await self.send_action_embed(ctx, user, "hug")

    @roleplay.command(name="kiss", description="Kiss someone")
    @app_commands.describe(user="The user to kiss")
    async def kiss(self, ctx, user: Optional[Union[discord.Member, discord.User]] = None):
        user = user or ctx.author
        await self.send_action_embed(ctx, user, "kiss")

    @roleplay.command(name="bite", description="Bite someone")
    @app_commands.describe(user="The user to bite")
    async def bite(self, ctx, user: Optional[Union[discord.Member, discord.User]] = None):
        user = user or ctx.author
        await self.send_action_embed(ctx, user, "bite")

    @roleplay.command(name="baka", description="Call someone a baka")
    @app_commands.describe(user="The user to call baka")
    async def baka(self, ctx, user: Optional[Union[discord.Member, discord.User]] = None):
        user = user or ctx.author
        await self.send_action_embed(ctx, user, "baka")

    @roleplay.command(name="cuddle", description="Cuddle with someone")
    @app_commands.describe(user="The user to cuddle with")
    async def cuddle(self, ctx, user: Optional[Union[discord.Member, discord.User]] = None):
        user = user or ctx.author
        await self.send_action_embed(ctx, user, "cuddle")

    @roleplay.command(name="feed", description="Feed someone")
    @app_commands.describe(user="The user to feed")
    async def feed(self, ctx, user: Optional[Union[discord.Member, discord.User]] = None):
        user = user or ctx.author
        await self.send_action_embed(ctx, user, "feed")

    @roleplay.command(name="handhold", description="Hold hands with someone")
    @app_commands.describe(user="The user to hold hands with")
    async def handhold(self, ctx, user: Optional[Union[discord.Member, discord.User]] = None):
        user = user or ctx.author
        await self.send_action_embed(ctx, user, "handhold")

    @roleplay.command(name="handshake", description="Shake hands with someone")
    @app_commands.describe(user="The user to shake hands with")
    async def handshake(self, ctx, user: Optional[Union[discord.Member, discord.User]] = None):
        user = user or ctx.author
        await self.send_action_embed(ctx, user, "handshake")

    @roleplay.command(name="highfive", description="High five someone")
    @app_commands.describe(user="The user to high five")
    async def highfive(self, ctx, user: Optional[Union[discord.Member, discord.User]] = None):
        user = user or ctx.author
        await self.send_action_embed(ctx, user, "highfive")

    @roleplay.command(name="kick", description="Kick someone")
    @app_commands.describe(user="The user to kick")
    async def kick(self, ctx, user: Optional[Union[discord.Member, discord.User]] = None):
        user = user or ctx.author
        await self.send_action_embed(ctx, user, "kick")

    @roleplay.command(name="pat", description="Pat someone")
    @app_commands.describe(user="The user to pat")
    async def pat(self, ctx, user: Optional[Union[discord.Member, discord.User]] = None):
        user = user or ctx.author
        await self.send_action_embed(ctx, user, "pat")

    @roleplay.command(name="punch", description="Punch someone")
    @app_commands.describe(user="The user to punch")
    async def punch(self, ctx, user: Optional[Union[discord.Member, discord.User]] = None):
        user = user or ctx.author
        await self.send_action_embed(ctx, user, "punch")

    @roleplay.command(name="peck", description="Peck someone")
    @app_commands.describe(user="The user to peck")
    async def peck(self, ctx, user: Optional[Union[discord.Member, discord.User]] = None):
        user = user or ctx.author
        await self.send_action_embed(ctx, user, "peck")

    @roleplay.command(name="poke", description="Poke someone")
    @app_commands.describe(user="The user to poke")
    async def poke(self, ctx, user: Optional[Union[discord.Member, discord.User]] = None):
        user = user or ctx.author
        await self.send_action_embed(ctx, user, "poke")

    @roleplay.command(name="shoot", description="Shoot someone")
    @app_commands.describe(user="The user to shoot")
    async def shoot(self, ctx, user: Optional[Union[discord.Member, discord.User]] = None):
        user = user or ctx.author
        await self.send_action_embed(ctx, user, "shoot")

    @roleplay.command(name="cry", description="Let it all out")
    async def cry(self, ctx):
        ordinal_count = await self.update_count(ctx.author.id, ctx.author.id, "cry")
        
        async with self.session.get("https://nekos.best/api/v2/cry") as response:
            if response.status == 200:
                data = await response.json()
                gif_url = data['results'][0]['url']
                anime_name = data['results'][0]['anime_name']
            else:
                await ctx.warn("Failed to fetch cry GIF.")
                return
        
        embed = Embed(
            description=f"**{ctx.author.mention}** **cries** for the **{ordinal_count}** time!",
            color=self.bot.config.colors.information
        )
        embed.set_image(url=gif_url)
        embed.set_footer(text=f"From: {anime_name}")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Roleplay(bot))