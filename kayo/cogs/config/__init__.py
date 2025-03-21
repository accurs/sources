from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import swag


async def setup(bot: "swag") -> None:
    from .config import Config

    await bot.add_cog(Config(bot))
