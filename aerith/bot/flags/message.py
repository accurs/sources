from discord.ext.commands import Flag
from . import Flags


class Parameters(Flags):
    self_destruct = Flag(
        aliases=["delete_after"],
        default=None,
    )
