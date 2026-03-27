import discord_ios
import discord
from discord.ext import commands, tasks
from dotenv import dotenv_values
import os
import redis
import asyncpg
import aiohttp
import asyncio
from heist.plus.utils.db import redis_client, get_db_connection
import time

env_path = os.path.join(os.path.dirname(__file__), ".env")
config = dotenv_values(env_path)
DATA_DB = config["DATA_DB"]
TOKEN = config["HEIST_PLUS_TOKEN"]

class HeistPlus(commands.AutoShardedBot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(
            command_prefix="+",
            intents=intents,
            help_command=None)
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        self.db_pool = None

    async def setup_hook(self):
        self.db_pool = await asyncpg.create_pool(dsn=DATA_DB)
        for cog in [
            "heist.plus.cogs.roleplay",
            "heist.plus.cogs.nsfw",
            "heist.plus.cogs.info",
            "heist.plus.cogs.utility"
        ]:           
            await self.load_extension(cog)

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print(f'Using {self.shard_count} shards')
        await self.tree.sync()
        await self.preload_stalk()
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name="Cinderella",
            details="on SoundCloud", 
            state="By Bladee & Ecco2k",
            assets={
                "large_image": "cinderella",
                "large_text": "Cinderella"
            }
        )

        await self.change_presence(status=discord.Status.online, activity=activity)
        #await self.change_presence(activity=discord.CustomActivity(name="🔗 heist.lol/discord"))

    async def preload_stalk(self):
        async with get_db_connection() as conn:
            stalk_lists = await conn.fetch("SELECT stalker_id, target_id FROM stalking")

        for stalk_list in stalk_lists:
            stalker_id = stalk_list["stalker_id"]
            target_id = stalk_list["target_id"]
            await redis_client.sadd(f"stalker:{target_id}:stalkers", stalker_id)
            await redis_client.sadd(f"stalker:{stalker_id}:targets", target_id)

    async def on_interaction(self, interaction: discord.Interaction):
        uid = interaction.user.id
        user = interaction.user.name
        redis_key = f"user:{uid}:exists"
        user_exists_in_cache = self.redis_client.get(redis_key)

        if user_exists_in_cache:
            user_exists = True
        else:
            if self.db_pool is None:
                self.db_pool = await asyncpg.create_pool(dsn=DATA_DB)

            user_exists = await self.db_pool.fetchval("SELECT 1 FROM user_data WHERE user_id = $1", str(uid))

            if not user_exists:
                embed = discord.Embed(
                    description="You must authorize & use [Heist](https://discord.com/oauth2/authorize?client_id=1225070865935368265) once in order to use Heist+.",
                    color=0xd3d6f1
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            self.redis_client.set(redis_key, '1', ex=1200)

        interaction_type = interaction.data.get('type')

        if interaction_type == 1:
            if 'options' in interaction.data and interaction.data['options'] and interaction.data['options'][0].get('type') == 1:
                cmd = f"{interaction.data['name']} {interaction.data['options'][0]['name']}"
                options = interaction.data['options'][0].get('options', [])
            else:
                cmd = interaction.data['name']
                options = interaction.data.get('options', [])
                
            if 'options' in interaction.data:
                for option in interaction.data['options']:
                    if option.get('type') == 2:
                        subcommand = option.get('options', [{}])[0]
                        cmd = f"{interaction.data['name']} {option['name']} {subcommand.get('name', '')}"
                        options = subcommand.get('options', [])
                        break
                        
        elif interaction_type == 2:
            cmd = f"Context Menu: {interaction.data['name']}"
            options = []
            
            if 'target_id' in interaction.data:
                options.append({
                    'name': 'target',
                    'value': interaction.data['target_id']
                })
        else:
            return

        options_str = "\n".join([f"* {opt['name']}: `{opt['value']}`" for opt in options])

        embed = discord.Embed(description=f"* **{cmd}**\n{options_str}", color=0x000f)
        embed.set_author(name=f"{user} ({uid})")
        embed.set_footer(text="part of heist+")

        #if interaction.type == discord.InteractionType.application_command:
            #await send_log_to_webhook(embed)

client = HeistPlus()

client.run(f"{TOKEN}")