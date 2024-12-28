from core.tools import CompositeMetaClass
from .antinuke import AntiNuke, AntiRaid
from .logging import Logging
from .jail import Jail


class Extended(
    AntiRaid,
    AntiNuke,
    Jail,
    Logging,
    metaclass=CompositeMetaClass,
):
    """
    Join all extended config cogs into one.
    """
