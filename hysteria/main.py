import discord
from discord.ext import commands
import random
from utils.advert import advertise
from dotenv import dotenv_values
import asyncpg
import redis.asyncio as aioredis
import aiohttp
import asyncio

config = dotenv_values(".env")
TOKEN = config["DISCORD_TOKEN"]
DATABASE_URL = config["DATABASE_URL"]
REDIS_URL = config["REDIS_URL"]

#WEBHOOK = "https://discord.com/api/webhooks/1425239360252547185/M6mWJfoIoMOhyut8Zj6ys_Fhr9W53qu_lFHwe49rE66F4gTgwZ0MSmOjlNcm8qqTlGrd"
WEBHOOK = "https://discord.com/api/webhooks/1425259712261259358/2ZzyA007Xhp4zQ9YZtU6LII4xRn5ItawOpGrcw347ArUesRL2d25DQzUiDtCkN7WsfYc"

async def send_log_to_webhook(embed):
    async with aiohttp.ClientSession() as session:
        data = {"embeds": [embed.to_dict()]}
        try:
            async with session.post(WEBHOOK, json=data) as response:
                if response.status != 204:
                    print(f"failed to send log: {response.status}")
        except Exception as e:
            print(f"failed to send logs: {e}")

class Hysteria(commands.AutoShardedBot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="+", intents=intents, help_command=None)
        self.color = discord.Color(0xD3D6F1)
        self.pool = None
        self.owner_id = 1173788423308451841
        self.redis = None

    async def setup_hook(self):
        self.pool = await asyncpg.create_pool(DATABASE_URL)
        self.redis = await aioredis.from_url(REDIS_URL)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS users (
                userid BIGINT PRIMARY KEY,
                registered BOOLEAN DEFAULT FALSE
            );
        """)
        for cog in ["cogs.utility", "cogs.info", "cogs.admin"]:
            await self.load_extension(cog)

    async def on_ready(self):
        print(f"logged in as {self.user} (id: {self.user.id})")
        await self.tree.sync()
        from utils.commands import CommandCache
        await CommandCache.load_commands(self)

    async def on_interaction(self, interaction: discord.Interaction):
        uid = interaction.user.id
        user = interaction.user.name
        data = interaction.data

        if not data:
            return

        interaction_type = data.get('type')
        if interaction_type == 1:
            if 'options' in data and data['options'] and data['options'][0].get('type') == 1:
                cmd = f"{data['name']} {data['options'][0]['name']}"
                options = data['options'][0].get('options', [])
            else:
                cmd = data['name']
                options = data.get('options', [])
            if 'options' in data:
                for option in data['options']:
                    if option.get('type') == 2:
                        subcommand = option.get('options', [{}])[0]
                        cmd = f"{data['name']} {option['name']} {subcommand.get('name', '')}"
                        options = subcommand.get('options', [])
                        break
        elif interaction_type == 2:
            cmd = f"context menu: {data['name']}"
            options = []
            if 'target_id' in data:
                options.append({'name': 'target', 'value': data['target_id']})
        else:
            return

        options_str = "\n".join([f"* {opt['name']}: `{opt['value']}`" for opt in options])
        embed = discord.Embed(description=f"* **{cmd}**\n{options_str}", color=self.color)
        embed.set_author(name=f"{user} ({uid})")

        if interaction.type == discord.InteractionType.application_command:
            await send_log_to_webhook(embed)

    async def on_application_command_error(self, interaction: discord.Interaction, error):
        embed = discord.Embed(description=f"```yaml\n{error}```", color=self.color)
        await send_log_to_webhook(embed)

    async def send_followup(self, interaction: discord.Interaction, **kwargs):
        if "view" not in kwargs or kwargs["view"] is None:
            view = advertise()
            if view:
                kwargs["view"] = view
        await interaction.followup.send(**kwargs)

client = Hysteria()
client.run(TOKEN)
