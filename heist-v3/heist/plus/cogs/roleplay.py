import discord
import aiohttp
from discord import app_commands, Interaction, User, Embed, ui
from discord.ext import commands
from heist.plus.utils import permissions
from heist.plus.utils.error import error_handler
from heist.plus.utils.cache import get_embed_color
from heist.plus.utils.db import get_db_connection, redis_client
import os

redis = redis_client

class ActionButton(ui.View):
    def __init__(self, action: str, author: discord.User, target: discord.User, client):
        super().__init__(timeout=60)
        self.action = action
        self.author = author
        self.target = target
        self.client = client
        self.clicked = False
        
        verb_map = {
            "blowjob": "Suck",
            "pussyeat": "Eat pussy",
            "yaoi": "Have yaoi fun",
            "yuri": "Have yuri fun",
            "fuck": "Fuck",
            "anal": "Anal"
        }
        
        button_label = f"{verb_map.get(action, action)} back"
        
        self.button = ui.Button(
            label=button_label,
            style=discord.ButtonStyle.gray,
            emoji=discord.PartialEmoji(name="handsigns", id=1385054141784789133, animated=True)
        )
        self.button.callback = self.callback
        self.add_item(self.button)
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.target.id:
            return await interaction.response.send_message(f"Only {self.target.mention} can use this!", ephemeral=True)
        
        if self.clicked:
            return await interaction.response.send_message("Already used!", ephemeral=True)
        
        self.clicked = True
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(view=self)
        
        ordinal_count = await update_count(self.target.id, self.author.id, self.action)
        
        gif_url = await self._fetch_gif(self.action)
        if not gif_url:
            return await interaction.followup.send("Failed to fetch GIF.")
        
        verb_conjugations = {
            "blowjob": "sucks",
            "pussyeat": "eats pussy",
            "yaoi": "has yaoi fun",
            "yuri": "has yuri fun",
            "fuck": "fucks",
            "anal": "anal fucks"
        }
        
        conjugated_verb = verb_conjugations.get(self.action, f"{self.action}s")
        
        embed_color = await get_embed_color(str(self.target.id))
        embed = Embed(
            description=f"**{self.target.mention}** **{conjugated_verb}** **{self.author.mention} back** for the **{ordinal_count}** time!",
            color=embed_color
        )
        embed.set_image(url=gif_url)
        
        await interaction.followup.send(embed=embed)
    
    async def _fetch_gif(self, action):
        endpoints = {
            "blowjob": "https://purrbot.site/api/img/nsfw/blowjob/gif",
            "pussyeat": "https://purrbot.site/api/img/nsfw/pussylick/gif",
            "yaoi": "https://purrbot.site/api/img/nsfw/yaoi/gif",
            "yuri": "https://purrbot.site/api/img/nsfw/yuri/gif",
            "fuck": "https://purrbot.site/api/img/nsfw/fuck/gif",
            "anal": "https://purrbot.site/api/img/nsfw/anal/gif"
        }
        
        url = endpoints.get(action)
        if not url:
            return None
            
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('url') or data.get('link')
                return None
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if hasattr(self, 'message'):
            await self.message.edit(view=self)

async def update_count(interaction_user_id: int, target_user_id: int, action: str) -> str:
    cache_key = f"{interaction_user_id}_{target_user_id}_{action}"
    cached_count = await redis.get(cache_key)
    
    async with get_db_connection() as conn:
        if cached_count:
            count = int(cached_count) + 1
            query = """
                UPDATE user_actions 
                SET count = $1 
                WHERE user_id = $2 AND target_user_id = $3 AND action = $4
                RETURNING count
            """
            result = await conn.fetchrow(query, count, interaction_user_id, target_user_id, action)
        else:
            query = """
                INSERT INTO user_actions (user_id, target_user_id, action, count)
                VALUES ($1, $2, $3, 1)
                ON CONFLICT (user_id, target_user_id, action)
                DO UPDATE SET count = user_actions.count + 1
                RETURNING count
            """
            result = await conn.fetchrow(query, interaction_user_id, target_user_id, action)
            count = result['count']

    await redis.setex(cache_key, 3600, count)

    if 10 <= count % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(count % 10, 'th')
    return f"{count}{suffix}"

class Roleplay(commands.Cog):
    def __init__(self, client):
        self.client = client

    roleplay = app_commands.Group(
        name="roleplay", 
        description="Roleplay related commands",
        allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=False, private_channel=True),
        allowed_installs=app_commands.AppInstallationType(guild=True, user=True)
    )

    nsfwroleplay = app_commands.Group(
        name="nsfw", 
        description="NSFW roleplay related commands",
        parent=roleplay
    )

    async def _fetch_gif(self, url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('url') or data.get('link')
                return None

    async def send_action_embed(self, interaction, user, action, description_template, endpoint):
        ordinal_count = await update_count(interaction.user.id, user.id, action)

        gif_url = await self._fetch_gif(endpoint)
        if not gif_url:
            return await interaction.followup.send(f"Failed to fetch {action} GIF.")

        embed_color = await get_embed_color(str(interaction.user.id))
        embed = Embed(
            description=description_template.format(
                user_mention=interaction.user.mention,
                target_mention=user.mention,
                ordinal_count=ordinal_count
            ),
            color=embed_color
        )
        embed.set_image(url=gif_url)

        view = ActionButton(action, interaction.user, user, self.client)
        message = await interaction.followup.send(embed=embed, view=view)
        view.message = message

    @nsfwroleplay.command(nsfw=True)
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.check(permissions.is_blacklisted)
    @permissions.requires_perms(embed_links=True)
    @app_commands.describe(user="The user to give a blowjob to.")
    async def blowjob(self, interaction: Interaction, user: User = None):
        """Suck someone's dick"""
        user = user or interaction.user
        await self.send_action_embed(
            interaction, 
            user, 
            "blowjob",
            "**{user_mention}** **sucks** **{target_mention}**'s dick for the **{ordinal_count}** time!",
            "https://purrbot.site/api/img/nsfw/blowjob/gif"
        )

    @nsfwroleplay.command(nsfw=True)
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.check(permissions.is_blacklisted)
    @permissions.requires_perms(embed_links=True)
    @app_commands.describe(user="The user to eat the pussy of.")
    async def eatpussy(self, interaction: Interaction, user: User = None):
        """Eat someone's pussy"""
        user = user or interaction.user
        await self.send_action_embed(
            interaction, 
            user, 
            "pussyeat",
            "**{user_mention}** **eats** **{target_mention}**'s pussy for the **{ordinal_count}** time!",
            "https://purrbot.site/api/img/nsfw/pussylick/gif"
        )

    @nsfwroleplay.command(nsfw=True)
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.check(permissions.is_blacklisted)
    @permissions.requires_perms(embed_links=True)
    @app_commands.describe(user="The user to have fun with.")
    async def yaoi(self, interaction: Interaction, user: User = None):
        """Have some yaoi fun with someone"""
        user = user or interaction.user
        await self.send_action_embed(
            interaction, 
            user, 
            "yaoi",
            "**{user_mention}** **has yaoi fun with** **{target_mention}** for the **{ordinal_count}** time!",
            "https://purrbot.site/api/img/nsfw/yaoi/gif"
        )

    @nsfwroleplay.command(nsfw=True)
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.check(permissions.is_blacklisted)
    @permissions.requires_perms(embed_links=True)
    @app_commands.describe(user="The user to have fun with.")
    async def yuri(self, interaction: Interaction, user: User = None):
        """Have some yuri fun with someone"""
        user = user or interaction.user
        await self.send_action_embed(
            interaction, 
            user, 
            "yuri",
            "**{user_mention}** **has yuri fun with** **{target_mention}** for the **{ordinal_count}** time!",
            "https://purrbot.site/api/img/nsfw/yuri/gif"
        )

    @nsfwroleplay.command(nsfw=True)
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.check(permissions.is_blacklisted)
    @permissions.requires_perms(embed_links=True)
    @app_commands.describe(user="The user to fuck.")
    async def fuck(self, interaction: Interaction, user: User = None):
        """Fuck someone"""
        user = user or interaction.user
        await self.send_action_embed(
            interaction, 
            user, 
            "fuck",
            "**{user_mention}** **fucks** **{target_mention}** for the **{ordinal_count}** time!",
            "https://purrbot.site/api/img/nsfw/fuck/gif"
        )

    @nsfwroleplay.command(nsfw=True)
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.check(permissions.is_blacklisted)
    @permissions.requires_perms(embed_links=True)
    @app_commands.describe(user="The user to fuck in the ass.")
    async def anal(self, interaction: Interaction, user: User = None):
        """Fuck someone in the ass"""
        user = user or interaction.user
        await self.send_action_embed(
            interaction, 
            user, 
            "anal",
            "**{user_mention}** **fucks** **{target_mention}** **in the ass** for the **{ordinal_count}** time!",
            "https://purrbot.site/api/img/nsfw/anal/gif"
        )

    @nsfwroleplay.command(nsfw=True)
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    @app_commands.choices(gender=[
        app_commands.Choice(name="Female", value="female"),
        app_commands.Choice(name="Male", value="male")
    ])
    @app_commands.check(permissions.is_blacklisted)
    @permissions.requires_perms(embed_links=True)
    async def masturbate(self, interaction: Interaction, gender: str = "female"):
        """Please yourself a little"""
        ordinal_count = await update_count(interaction.user.id, interaction.user.id, "masturbate")
        
        endpoint = "https://purrbot.site/api/img/nsfw/solo/gif" if gender == "female" else "https://purrbot.site/api/img/nsfw/solo_male/gif"
        gif_url = await self._fetch_gif(endpoint)
        if not gif_url:
            return await interaction.followup.send("Failed to fetch masturbate GIF.")
        
        embed_color = await get_embed_color(str(interaction.user.id))
        embed = Embed(
            description=f"**{interaction.user.mention}** **masturbates** for the **{ordinal_count}** time!",
            color=embed_color
        )
        embed.set_image(url=gif_url)
        
        await interaction.followup.send(embed=embed)

async def setup(client):
    await client.add_cog(Roleplay(client))