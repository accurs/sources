import discord
from discord.ext import commands

from heist.framework.discord.context import Context

class Whitelist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="whitelist", invoke_without_command=True)
    @commands.is_owner()
    async def whitelist(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @whitelist.command(name="add")
    @commands.is_owner()
    async def whitelist_add(self, ctx: Context, guild_id: int):
        await self.bot.pool.execute(
            "INSERT INTO whitelist (guild_id) VALUES ($1) ON CONFLICT DO NOTHING",
            guild_id
        )
        await ctx.approve(f"Added guild {guild_id} to whitelist")

    @whitelist.command(name="remove")
    @commands.is_owner()
    async def whitelist_remove(self, ctx: Context, guild_id: int):
        await self.bot.pool.execute(
            "DELETE FROM whitelist WHERE guild_id = $1", guild_id
        )
        
        guild = self.bot.get_guild(guild_id)
        if guild:
            try:
                embed = discord.Embed(
                    title="Access Denied",
                    description="This server has been removed from whitelist. The bot will now leave.",
                    color=0xff0000
                )
                await self.bot.notify(guild, embed=embed)
                await guild.leave()
            except:
                pass
        
        await ctx.approve(f"Removed guild {guild_id} from whitelist")

    @whitelist.command(name="list")
    @commands.is_owner()
    async def whitelist_list(self, ctx: Context):
        guilds = await self.bot.pool.fetch("SELECT guild_id FROM whitelist")
        
        if not guilds:
            return await ctx.deny("No whitelisted guilds")
        
        guild_list = []
        for row in guilds:
            guild = self.bot.get_guild(row['guild_id'])
            name = guild.name if guild else "Unknown"
            guild_list.append(f"{row['guild_id']} - {name}")
        
        embed = discord.Embed(
            title="Whitelisted Guilds",
            description="\n".join(guild_list),
            color=ctx.config.colors.neutral
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Whitelist(bot))