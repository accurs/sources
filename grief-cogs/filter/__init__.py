from .filter import Filter
from grief.core.bot import Grief


async def setup(bot: Grief) -> None:
    await bot.add_cog(Filter(bot))
