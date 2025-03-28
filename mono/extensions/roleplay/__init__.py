from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.Mono import Mono


async def setup(bot: "Mono") -> None:
    from .roleplay import Roleplay

    await bot.add_cog(Roleplay(bot))
