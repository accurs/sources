from .plugin import Embed


async def setup(bot):
    await bot.add_cog(Embed(bot))
