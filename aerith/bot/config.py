from dataclasses import dataclass, field
from typing import List, Optional
from discord import ActivityType


@dataclass(frozen=True)
class Emojis:
    YES: str = "<:yes:1488505933771444385>"
    NO: str = "<:no:1488505932290854968>"
    WARN: str = "<:warn:1488505930881695886>"
    TIKTOK: str = "<:tiktok:1488505929572810863>"
    PY: str = "<:py:1488505928209928314>"
    GIT: str = "<:git:1488505926985191424>"
    RIGHT: str = "<:right:1488505925592551434>"
    LEFT: str = "<:left:1488505924179198003>"
    BIN: str = "<:bin:1488505921402441768>"
    GOTO: str = "<:goto:1488505919867191377>"
    _1: str = "<:1_:1488505918311366737>"
    _3: str = "<:3_:1488505916847423559>"
    _2: str = "<:2_:1488505915454914640>"

    VERIFIEDAPP1X: str = "<:VerifiedApp1x:1500102536563265617>"
    DISCORDBOOST41X: str = "<:discordboost41x:1500102534969426021>"
    DISCORDBOOST31X: str = "<:discordboost31x:1500102533664735252>"
    DISCORDBOOST21X: str = "<:discordboost21x:1500102529864699944>"
    APP1X: str = "<:App1x:1500102528682037378>"
    SUPPORTSCOMMANDS1X: str = "<:supportscommands1x:1500102527385862304>"
    ORB1X: str = "<:orb1x:1500102523799863347>"
    OLDDISCORDMOD1X: str = "<:olddiscordmod1x:1500102522239717497>"
    KOTHHYPESQUADBALANCE1X: str = "<:kothhypesquadbalance1x:1500102520163536916>"
    HYPESQUADEVENTS1X: str = "<:hypesquadevents1x:1500102518917697748>"
    HYPESQUADBRILLIANCE1X: str = "<:hypesquadbrilliance1x:1500102517726380172>"
    HYPESQUADBRAVERY1X: str = "<:hypesquadbravery1x:1500102516208308285>"
    HYPESQUADBALANCE1X: str = "<:hypesquadbalance1x:1500102513922150551>"
    GOLDENHYPESQUADBALANCE1X: str = "<:goldenhypesquadbalance1x:1500102512491892807>"
    DISCORDSTAFF1X: str = "<:discordstaff1x:1500102511435055155>"
    DISCORDPARTNER1X: str = "<:discordpartner1x:1500102510189482004>"
    DISCORDNITRO1X: str = "<:discordnitro1x:1500102508511498300>"
    DISCORDMOD1X: str = "<:discordmod1x:1500102507052007428>"
    DISCORDEARLYSUPPORTER1X: str = "<:discordearlysupporter1x:1500102505323958372>"
    DISCORDBUGHUNTER21X: str = "<:discordbughunter21x:1500102503881113641>"
    DISCORDBUGHUNTER11X: str = "<:discordbughunter11x:1500102502475890730>"
    DISCORDBOTDEV1X: str = "<:discordbotdev1x:1500102501255348336>"
    DISCORDBOOST91X: str = "<:discordboost91x:1500102499695333536>"
    DISCORDBOOST81X: str = "<:discordboost81x:1500102497786663122>"
    DISCORDBOOST71X: str = "<:discordboost71x:1500102496566378617>"


@dataclass(frozen=True, slots=True)
class Status:
    type: ActivityType
    name: str
    url: Optional[str] = None


@dataclass(frozen=True, slots=True)
class Config:
    status: Optional[Status]
    prefix: str = ","
    owner_ids: List[int] = field(
        default_factory=lambda: [
            1422609274890354979,  # nick
            1504136044767875242,  # alice
        ]
    )
    emojis: Emojis = field(default_factory=Emojis)
