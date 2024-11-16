from .embedcreator import EmbedCreator

from grief.core.bot import Grief

async def setup(bot: Grief):
    await bot.add_cog(EmbedCreator(bot))
