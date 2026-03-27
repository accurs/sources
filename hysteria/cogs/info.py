import discord
from discord import app_commands
from discord.ext import commands
from utils.access import is_whitelisted

class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="bot", description="info about the bot")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_whitelisted)
    async def botinfo(self, interaction: discord.Interaction):
        ms = round(interaction.client.latency * 1000)
        embed = discord.Embed(
            color=self.bot.color,
            description="tool specially tailored for data enthusiasts, handcrafted by lord [**cosmin**](https://cursi.ng)"
        )
        embed.set_footer(text=f"{ms}ms")
        hysteria = discord.ui.Button(
            label="hysteria bot",
            url="https://discord.com/oauth2/authorize?client_id=1415512129867612375",
            emoji="<:hysteria:1418707027777032303>"
        )
        heist = discord.ui.Button(
            label="heist bot (more features)",
            url="https://discord.com/oauth2/authorize?client_id=1225070865935368265",
            emoji="<:heist:1391868311691591691>"
        )
        view = discord.ui.View()
        view.add_item(hysteria)
        view.add_item(heist)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="heistbot", description="info about heist bot")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def heistbot(self, interaction: discord.Interaction):
        ms = round(interaction.client.latency * 1000)
        embed = discord.Embed(
            color=self.bot.color,
            description="you can get access to hysteria by buying [**`heist premium`**](https://heist.lol/premium) and making a ticket [here](https://discord.gg/heistbot).\n-# heist is the upgraded and public version of hysteria, with 30x more features and constant updates, made by lord [**cosmin**](https://cursi.ng)."
        )
        heist = discord.ui.Button(
            label="get heist bot",
            url="https://discord.com/oauth2/authorize?client_id=1225070865935368265",
            emoji="<:heist:1391868311691591691>"
        )
        view = discord.ui.View()
        view.add_item(heist)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="support", description="support for the bot")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_whitelisted)
    async def support(self, interaction: discord.Interaction):
        await interaction.response.send_message("https://t.me/+iNOmlZi6rLdlYTI8")

    @app_commands.command(name="terms", description="terms of using hysteria")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(is_whitelisted)
    async def terms(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="terms of using hysteria",
            description=(
                "when we say '**lord**', we mean sir cosmin, and when we say '**bot**', "
                "we mean hysteria. by using hysteria you accept that your access "
                "to the bot can be restricted at any time, for any reason the lord "
                "finds reasonable.\nyou agree not to use any data from the bot in a "
                "shady or unethical way.\n__federal agents, government spies, or any "
                "other sort of lawful entities are strictly forbidden from using the bot__."
            ),
            color=self.bot.color
        )
        await interaction.response.send_message(embed=embed, ephemeral=False)

async def setup(bot):
    await bot.add_cog(Info(bot))
