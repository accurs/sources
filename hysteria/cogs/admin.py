from discord.ext import commands
from discord import app_commands
import discord

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    admin = app_commands.Group(
        name="o", 
        description="owner stuff",
        allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True),
        allowed_installs=app_commands.AppInstallationType(guild=True, user=True)
   )

    @admin.command(name="whitelist", description="whitelist a user")
    @app_commands.describe(user="the user to whitelist")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def whitelist(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer()
        if interaction.user.id != self.bot.owner_id:
            return await self.bot.send_followup(interaction, content="oops no permission")
        async with self.bot.pool.acquire() as conn:
            record = await conn.fetchrow("SELECT * FROM users WHERE userid=$1", user.id)
            if record:
                await conn.execute("UPDATE users SET registered=TRUE WHERE userid=$1", user.id)
            else:
                await conn.execute("INSERT INTO users(userid, registered) VALUES($1, TRUE)", user.id)
        await self.bot.send_followup(interaction, content=f"{user.name} is now whitelisted")

    @admin.command(name="unwhitelist", description="remove a user from whitelist")
    @app_commands.describe(user="the user to remove")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def unwhitelist(self, interaction: discord.Interaction, user: discord.User):
        if interaction.user.id != self.bot.owner_id:
            return await self.bot.send_followup(interaction, content="oops no permission")
        await interaction.response.defer()
        async with self.bot.pool.acquire() as conn:
            await conn.execute("UPDATE users SET registered=FALSE WHERE userid=$1", user.id)
        await self.bot.send_followup(interaction, content=f"{user.name} is now removed from whitelist")

async def setup(bot):
    await bot.add_cog(Admin(bot))