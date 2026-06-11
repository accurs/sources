from .plugin import Information


async def setup(bot):
    await bot.add_cog(Information(bot))
