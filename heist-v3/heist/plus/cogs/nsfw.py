import discord
from discord.ext import commands
from heist.plus.utils import permissions
from discord import app_commands, Interaction, User, Embed, ui
from discord.ext import commands
import aiohttp
import random
import ujson as json

API_KEY = "0c5189c7e8155c13180eab96d9e618de3b5f1b2a69d99286e2452eeb4ce29758b414a61842537b96e956614a6f13a02241a30b4d225cec01c12c076ab6ffadcf"
USER_ID = "5568513"

class NSFW(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    nsfw = app_commands.Group(
        name="nsfw", 
        description="NSFW related commands",
        allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=False, private_channel=True),
        allowed_installs=app_commands.AppInstallationType(guild=True, user=True)
    )

    hentainsfw = app_commands.Group(
        name="hentai", 
        description="Hentai related commands",
        parent=nsfw
    )

    rule34 = app_commands.Group(
        name="rule34", 
        description="rule34 related commands",
        parent=nsfw
    )

    @rule34.command(name="search", description="Search Rule34 for NSFW content", nsfw=True)
    @app_commands.describe(query="Search query for Rule34 content")
    async def rule34search(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(thinking=True)
        api_url = (
            f"https://api.rule34.xxx/index.php?"
            f"page=dapi&s=post&q=index&json=1&limit=100&tags={query}"
            f"&user_id={USER_ID}&api_key={API_KEY}"
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status != 200:
                    await interaction.followup.send("Failed to fetch data from Rule34.")
                    return

                try:
                    data = await response.json()
                except Exception:
                    text = await response.text()
                    await interaction.followup.send(f"Rule34 returned an invalid response:\n```{text[:500]}```")
                    return

                if not isinstance(data, list) or not data:
                    await interaction.followup.send(f"No results found for `{query}`.")
                    return

                post = random.choice(data)
                image_url = post.get("file_url")
                if not image_url:
                    await interaction.followup.send(f"No image found for `{query}`.")
                    return

                await interaction.followup.send(image_url)

    @rule34search.autocomplete("query")
    async def rule34_autocomplete(self, interaction: discord.Interaction, current: str):
        if not current:
            return []

        url = f"https://api.rule34.xxx/autocomplete.php?q={current}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return []
                try:
                    text = await response.text()
                    data = json.loads(text)
                    return [
                        app_commands.Choice(name=tag["label"], value=tag["value"])
                        for tag in data[:25]
                    ]
                except Exception:
                    return []

    @hentainsfw.command(name="ecchi", description="✨ Spicy hentai content: ecchi", nsfw=True)
    @app_commands.check(permissions.is_donor)
    async def ecchi(self, interaction: discord.Interaction):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.waifu.im/search/?included_tags=ecchi&is_nsfw=true') as response:
                if response.status == 200:
                    data = await response.json()
                    image_url = data['images'][0]['url']
                    await interaction.response.send_message(f"[ecchi]({image_url})")

    @hentainsfw.command(name="hentai", description="✨ Spicy hentai content: hentai", nsfw=True)
    @app_commands.check(permissions.is_donor)
    async def hentai(self, interaction: discord.Interaction):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.waifu.im/search/?included_tags=hentai&is_nsfw=true') as response:
                if response.status == 200:
                    data = await response.json()
                    image_url = data['images'][0]['url']
                    await interaction.response.send_message(f"[hentai]({image_url})")

    @hentainsfw.command(name="uniform", description="✨ Spicy hentai content: uniform", nsfw=True)
    @app_commands.check(permissions.is_donor)
    async def uniform(self, interaction: discord.Interaction):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.waifu.im/search/?included_tags=uniform&is_nsfw=true') as response:
                if response.status == 200:
                    data = await response.json()
                    image_url = data['images'][0]['url']
                    await interaction.response.send_message(f"[uniform]({image_url})")

    @hentainsfw.command(name="maid", description="✨ Spicy hentai content: maid", nsfw=True)
    @app_commands.check(permissions.is_donor)
    async def maid(self, interaction: discord.Interaction):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.waifu.im/search/?included_tags=maid&is_nsfw=true') as response:
                if response.status == 200:
                    data = await response.json()
                    image_url = data['images'][0]['url']
                    await interaction.response.send_message(f"[maid]({image_url})")

    @hentainsfw.command(name="oppai", description="✨ Spicy hentai content: oppai", nsfw=True)
    @app_commands.check(permissions.is_donor)
    async def oppai(self, interaction: discord.Interaction):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.waifu.im/search/?included_tags=oppai&is_nsfw=true') as response:
                if response.status == 200:
                    data = await response.json()
                    image_url = data['images'][0]['url']
                    await interaction.response.send_message(f"[oppai]({image_url})")

    @hentainsfw.command(name="selfies", description="✨ Spicy hentai content: selfies", nsfw=True)
    @app_commands.check(permissions.is_donor)
    async def selfies(self, interaction: discord.Interaction):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.waifu.im/search/?included_tags=selfies&is_nsfw=true') as response:
                if response.status == 200:
                    data = await response.json()
                    image_url = data['images'][0]['url']
                    await interaction.response.send_message(f"[selfies]({image_url})")

    @hentainsfw.command(name="raiden", description="✨ Spicy hentai content: raiden", nsfw=True)
    @app_commands.check(permissions.is_donor)
    async def raiden(self, interaction: discord.Interaction):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.waifu.im/search/?included_tags=raiden&is_nsfw=true') as response:
                if response.status == 200:
                    data = await response.json()
                    image_url = data['images'][0]['url']
                    await interaction.response.send_message(f"[raiden]({image_url})")

    @hentainsfw.command(name="marin", description="✨ Spicy hentai content: marin", nsfw=True)
    @app_commands.check(permissions.is_donor)
    async def marin(self, interaction: discord.Interaction):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.waifu.im/search/?included_tags=marin&is_nsfw=true') as response:
                if response.status == 200:
                    data = await response.json()
                    image_url = data['images'][0]['url']
                    await interaction.response.send_message(f"[marin]({image_url})")

    @hentainsfw.command(name="ass", description="✨ Spicy hentai content: ass", nsfw=True)
    @app_commands.check(permissions.is_donor)
    async def ass(self, interaction: discord.Interaction):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.waifu.im/search/?included_tags=ass&is_nsfw=true') as response:
                if response.status == 200:
                    data = await response.json()
                    image_url = data['images'][0]['url']
                    await interaction.response.send_message(f"[ass]({image_url})")

    @hentainsfw.command(name="paizuri", description="✨ Spicy hentai content: paizuri", nsfw=True)
    @app_commands.check(permissions.is_donor)
    async def paizuri(self, interaction: discord.Interaction):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.waifu.im/search/?included_tags=paizuri&is_nsfw=true') as response:
                if response.status == 200:
                    data = await response.json()
                    image_url = data['images'][0]['url']
                    await interaction.response.send_message(f"[paizuri]({image_url})")

    @hentainsfw.command(name="ero", description="✨ Spicy hentai content: ero", nsfw=True)
    @app_commands.check(permissions.is_donor)
    async def ero(self, interaction: discord.Interaction):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.waifu.im/search/?included_tags=ero&is_nsfw=true') as response:
                if response.status == 200:
                    data = await response.json()
                    image_url = data['images'][0]['url']
                    await interaction.response.send_message(f"[ero]({image_url})")

    @hentainsfw.command(name="milf", description="✨ Spicy hentai content: milf")
    @app_commands.check(permissions.is_donor)
    async def milf(self, interaction: discord.Interaction):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.waifu.im/search/?included_tags=milf&is_nsfw=true') as response:
                if response.status == 200:
                    data = await response.json()
                    image_url = data['images'][0]['url']
                    await interaction.response.send_message(f"[milf]({image_url})")

    @hentainsfw.command(name="oral", description="✨ Spicy hentai content: oral", nsfw=True)
    @app_commands.check(permissions.is_donor)
    async def oral(self, interaction: discord.Interaction):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.waifu.im/search/?included_tags=oral&is_nsfw=true') as response:
                if response.status == 200:
                    data = await response.json()
                    image_url = data['images'][0]['url']
                    await interaction.response.send_message(f"[oral]({image_url})")

async def setup(bot):
    await bot.add_cog(NSFW(bot))
