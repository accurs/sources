from __future__ import annotations

import importlib

from discord.ext import commands

from . import ascii_art as ascii_art_module
from . import image_tools as image_tools_module
from . import pixelate as pixelate_module

# These modules contain the sizeable studio implementations. Reloading them
# here keeps `/reload-cog media` useful while presenting one actual Discord cog.
importlib.reload(ascii_art_module)
importlib.reload(image_tools_module)
importlib.reload(pixelate_module)


class Media(
    ascii_art_module.AsciiArt,
    pixelate_module.Pixelate,
    image_tools_module.ImageTools,
):
    """Image, GIF, video, ASCII, caption, and pixel-art tools."""

    def __init__(self, bot: commands.Bot) -> None:
        # All implementations are real Cog classes with their own setup.
        # Explicit calls are required here: cooperative ``super()`` cannot be
        # used because the parent initializers do not call it themselves.
        ascii_art_module.AsciiArt.__init__(self, bot)
        pixelate_module.Pixelate.__init__(self, bot)
        image_tools_module.ImageTools.__init__(self, bot)

    async def cog_unload(self) -> None:
        await ascii_art_module.AsciiArt.cog_unload(self)
        await pixelate_module.Pixelate.cog_unload(self)
        await image_tools_module.ImageTools.cog_unload(self)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Media(bot))
