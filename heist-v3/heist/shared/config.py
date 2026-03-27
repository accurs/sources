from os import getenv
from json import loads
from cashews import cache
from discord import Member
from redis.asyncio import Redis
from urllib.parse import urlparse, quote, unquote
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Self,
    TYPE_CHECKING,
    ClassVar,
    Literal,
)
from dotenv import load_dotenv

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)

load_dotenv(override=True)

if TYPE_CHECKING:
    from heist.framework import heist


class Defaults(BaseModel):
    prefix: str = ";"
    help_menu: Literal["Heist", "Basic", "Dropdown"] = (
        "Heist"
    )
    auto_transcription: bool = False
    ignored_channels: List[int] = []
    disabled_commands: List[str] = []
    disabled_cogs: List[str] = []


class Colors(BaseModel):
    approve: int = 0xa4ec7c
    deny: int = 0xd3d6f1
    warn: int = 0xd3d6f1
    information: int = 0xd3d6f1
    neutral: int = 0xd3d6f1
    juul: int = 0xd3d6f1
    no_juul: int = 0xd3d6f1
    blunt: int = 0xd3d6f1

class InterfaceEmojis(BaseSettings):
    lock: str = "<:lock:1402024761516621897>"
    unlock: str = "<:unlock:1402024772799430787>"
    ghost: str = "<:ghost:1402024692239569011>"
    reveal: str = "<:reveal:1402024749986484374>"
    claim: str = "<:claim:1402024657758060785>"
    disconnect: str = "<:disconnect:1402024681384448181>"
    activity: str = "<:activity:1402024646446026852>"
    information: str = "<:information:1402024728113447014>"
    increase: str = "<:increase:1402024706298744832>"
    decrease: str = "<:decrease:1402024667593838724>"
    transfer: str = "<:crown:1402075744565461042>"

    model_config = SettingsConfigDict(
        env_prefix=getenv(
            "EMOJIS_INTERFACE_ENV_PREFIX",
            "EMOJIS_INTERFACE_",
        )
    )


class PaginatorEmojis(BaseSettings):
    next: str = "<:right:1265476229876678768>"
    navigate: str = "<:sort:1317260205381386360>"
    previous: str = "<:left:1265476224742850633>"
    cancel: str = "<:bin:1317214464231079989>"

    model_config = SettingsConfigDict(
        env_prefix=getenv(
            "EMOJIS_PAGINATOR_ENV_PREFIX",
            "EMOJIS_PAGINATOR_",
        )
    )

class ContextEmojis(BaseSettings):
    approve: str = "<:check:1344689360527949834>"
    deny: str = "<:no:1423109075083989062>"
    warn: str = "<:warning:1350239604925530192>"
    premium: str = "<:premium:1311062205650833509>"
    cash: str = "<:eco_cash:1439036453727371435>"

    model_config = SettingsConfigDict(
        env_prefix=getenv(
            "EMOJIS_CONTEXT_ENV_PREFIX", "EMOJIS_CONTEXT_"
        )
    )


class Emojis(BaseModel):
    interface: InterfaceEmojis = InterfaceEmojis()
    paginator: PaginatorEmojis = PaginatorEmojis()
    context: ContextEmojis = ContextEmojis()

class LoggingGuilds(BaseModel):
    primary: int = 1434702504637239296
    logging: int = 1434702504637239296
    testing: int = 1434702504637239296


class LoggingTypes(BaseModel):
    command: int = 1428888442452049920
    status: int = 1428888442452049920

    guild_blacklist: int = 1428888442452049920
    guild_unblacklist: int = 1428888442452049920

    user_blacklist: int = 1428888442452049920
    user_unblacklist: int = 1428888442452049920

    guild_joined: int = 1428888442452049920
    guild_left: int = 1428888442452049920


class Logging(BaseModel):
    guilds: LoggingGuilds = LoggingGuilds()
    types: LoggingTypes = LoggingTypes()


class Authentication:
    token: ClassVar[str] = getenv("TOKEN", "")
    discord_secret: ClassVar[str] = getenv("DISCORD_SECRET", "")
    redis: ClassVar[Redis] = Redis.from_url(
        getenv("REDIS_URL", "redis://localhost:6379")
    )
    logging: ClassVar[Logging] = Logging()
    owner_ids: ClassVar[List[int]] = loads(
        getenv(
            "OWNER_IDS",
            """[
                1150918662769881088,
                1403159604493549748,
                1173788423308451841
            ]""",
        )
    )

class Configuration:
    colors: Colors
    emojis: Emojis
    defaults: Defaults
    authentication: ClassVar[Authentication] = (
        Authentication()
    )

    __slots__ = ("colors", "emojis", "defaults")

    def __init__(
        self,
        *,
        colors: Optional[Colors] = None,
        emojis: Optional[Emojis] = None,
        defaults: Optional[Defaults] = None,
    ):
        self.colors = colors or Colors()
        self.emojis = emojis or Emojis()
        self.defaults = defaults or Defaults()
    
    @property
    def clean_prefix(self) -> str:
        """Return the clean prefix without special characters."""
        if hasattr(self.defaults, 'prefix') and self.defaults.prefix:
            return self.defaults.prefix.strip()
        return ";"

    @classmethod
    @cache(ttl="3m", key="configuration:guild:{guild_id}")
    async def from_guild(
        cls, guild_id: int, bot: "heist"
    ) -> Self:
        config: Dict[str, Any] = loads(
            await bot.pool.fetchval(
                """
                SELECT config 
                FROM guild.settings 
                WHERE guild_id = $1
                """,
                guild_id,
            )
            or '{"defaults": {}, "emojis": {}, "colors": {}}'
        )
        return cls(
            colors=Colors(**config["colors"]) if config["colors"] else Colors(),
            emojis=Emojis(**config["emojis"]) if config["emojis"] else Emojis(),
            defaults=Defaults(**config["defaults"]) if config["defaults"] else Defaults(),
        )

    @classmethod
    @cache(ttl="3m", key="configuration:user:{user_id}")
    async def from_user(
        cls, user_id: int, bot: "heist"
    ) -> Self:
        config: Dict[str, Any] = loads(
            await bot.pool.fetchval(
                """
                SELECT config 
                FROM user.settings 
                WHERE user_id = $1
                """,
                user_id,
            )
            or str({
                "defaults": {},
                "emojis": {},
                "colors": {},
            })
        )
        return cls(
            colors=Colors(**config["colors"]) if config["colors"] else Colors(),
            emojis=Emojis(**config["emojis"]) if config["emojis"] else Emojis(),
            defaults=Defaults(**config["defaults"]) if config["defaults"] else Defaults(),
        )
