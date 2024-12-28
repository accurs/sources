from core.tools import CompositeMetaClass

from .ticket import Ticket
from .alias import Alias
from .roles import Roles
from .starboard import Starboard
from .sticky import Sticky
from .statistics import Statistics
from .system import System
from .webhook import Webhook
from .level import Level
from .disboard import Disboard
# from .command import CommandManagement
from .boosterrole import BoosterRole
from .gallery import Gallery


class Extended(
    Ticket,
    Alias,
    Roles,
    Starboard,
    Sticky,
    Statistics,
    System,
    Webhook,
    Level,
    Disboard,
#     CommandManagement,
    BoosterRole,
    Gallery,
    metaclass=CompositeMetaClass,
):
    """
    Join all extended utility cogs into one.
    """
