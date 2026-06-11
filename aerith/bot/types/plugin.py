from discord.ext.commands import Cog
from ..aerith import Aerith


class Plugin(Cog):
    def __init__(self, bot: Aerith):
        self.bot = bot
