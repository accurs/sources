from typing import Optional
from discord.ext.commands import flag
from heist.framework.discord.flags import FlagConverter

class ActionParameters(FlagConverter):
    action: Optional[int] = flag(description="Action to take (1=kick, 2=ban)", default=2)

class AntiRaidParameters(FlagConverter):
    action: Optional[int] = flag(description="Action to take (1=kick, 2=ban)", default=2)
    threshold: Optional[int] = flag(description="Threshold for triggering", default=7)
    lock: Optional[bool] = flag(description="Lock channels during raid", default=False)
    punish: Optional[bool] = flag(description="Punish new members", default=True)