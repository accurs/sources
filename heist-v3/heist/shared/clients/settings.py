from typing import TYPE_CHECKING, List, Optional
from functools import cached_property

from discord import Guild, Member, Role
from discord.abc import GuildChannel

from heist.framework.tools.cache import cache

if TYPE_CHECKING:
    from heist.framework import heist


class Settings:
    bot: "heist"
    guild: Guild
    prefixes: List[str]
    reskin: bool
    reposter_prefix: bool
    reposter_delete: bool
    reposter_embed: bool
    welcome_removal: bool
    booster_role_base_id: Optional[int]
    booster_role_include_ids: List[int]
    lock_role_id: Optional[int]
    lock_ignore_ids: List[int]
    log_ignore_ids: List[int]
    reassign_ignore_ids: List[int]
    reassign_roles: bool
    invoke_kick: Optional[str]
    invoke_ban: Optional[str]
    invoke_unban: Optional[str]
    invoke_timeout: Optional[str]
    invoke_untimeout: Optional[str]
    play_panel: bool
    play_deletion: bool
    dm_enabled: bool
    dm_ban: Optional[str]
    dm_unban: Optional[str]
    dm_kick: Optional[str]
    dm_jail: Optional[str]
    dm_unjail: Optional[str]
    dm_mute: Optional[str]
    dm_unmute: Optional[str]
    dm_warn: Optional[str]
    dm_timeout: Optional[str]
    dm_untimeout: Optional[str]
    dm_role_add: Optional[str]
    dm_role_remove: Optional[str]
    dm_antinuke_ban: Optional[str]
    dm_antinuke_kick: Optional[str]
    dm_antinuke_strip: Optional[str]
    dm_antiraid_ban: Optional[str]
    dm_antiraid_kick: Optional[str]
    dm_antiraid_timeout: Optional[str]
    dm_antiraid_strip: Optional[str]

    def __init__(
        self, bot: "heist", guild: Guild, record: dict
    ):
        self.bot = bot
        self.guild = guild
        # self.prefixes = record.get("prefixes", [config.CLIENT.PREFIX])
        self.reskin = record.get("reskin", False)
        self.reposter_prefix = record.get(
            "reposter_prefix", True
        )
        self.reposter_delete = record.get(
            "reposter_delete", False
        )
        self.reposter_embed = record.get(
            "reposter_embed", True
        )
        self.welcome_removal = record.get(
            "welcome_removal", False
        )
        self.booster_role_base_id = record.get(
            "booster_role_base_id"
        )
        self.booster_role_include_ids = record.get(
            "booster_role_include_ids", []
        )
        self.lock_role_id = record.get("lock_role_id")
        self.lock_ignore_ids = record.get(
            "lock_ignore_ids", []
        )
        self.log_ignore_ids = record.get(
            "log_ignore_ids", []
        )
        self.reassign_ignore_ids = record.get(
            "reassign_ignore_ids", []
        )
        self.reassign_roles = record.get(
            "reassign_roles", False
        )
        self.invoke_kick = record.get("invoke_kick")
        self.invoke_ban = record.get("invoke_ban")
        self.invoke_unban = record.get("invoke_unban")
        self.invoke_timeout = record.get("invoke_timeout")
        self.invoke_untimeout = record.get(
            "invoke_untimeout"
        )
        self.play_panel = record.get("play_panel", True)
        self.play_deletion = record.get(
            "play_deletion", False
        )
        self.dm_enabled = record.get("dm_enabled", True)
        self.dm_ban = record.get("dm_ban")
        self.dm_unban = record.get("dm_unban")
        self.dm_kick = record.get("dm_kick")
        self.dm_jail = record.get("dm_jail")
        self.dm_unjail = record.get("dm_unjail")
        self.dm_mute = record.get("dm_mute")
        self.dm_unmute = record.get("dm_unmute")
        self.dm_warn = record.get("dm_warn")
        self.dm_timeout = record.get("dm_timeout")
        self.dm_untimeout = record.get("dm_untimeout")
        self.dm_role_add = record.get("dm_role_add")
        self.dm_role_remove = record.get("dm_role_remove")
        self.dm_antinuke_ban = record.get("dm_antinuke_ban")
        self.dm_antinuke_kick = record.get(
            "dm_antinuke_kick"
        )
        self.dm_antinuke_strip = record.get(
            "dm_antinuke_strip"
        )
        self.dm_antiraid_ban = record.get("dm_antiraid_ban")
        self.dm_antiraid_kick = record.get(
            "dm_antiraid_kick"
        )
        self.dm_antiraid_timeout = record.get(
            "dm_antiraid_timeout"
        )
        self.dm_antiraid_strip = record.get(
            "dm_antiraid_strip"
        )

    @property
    def booster_role_base(self) -> Optional[Role]:
        if not self.booster_role_base_id:
            return

        return self.guild.get_role(
            self.booster_role_base_id
        )

    @property
    def booster_role_include(self) -> List[Role]:
        return [
            role
            for role_id in self.booster_role_include_ids
            if (role := self.guild.get_role(role_id))
            is not None
        ]

    @cached_property
    def lock_role(self) -> Role:
        if not self.lock_role_id:
            return self.guild.default_role
        return (
            self.guild.get_role(self.lock_role_id)
            or self.guild.default_role
        )

    @property
    def lock_ignore(self) -> List[GuildChannel]:
        return [
            channel
            for channel_id in self.lock_ignore_ids
            if (
                channel := self.guild.get_channel(
                    channel_id
                )
            )
            is not None
        ]

    @property
    def log_ignore(self) -> List[GuildChannel | Member]:
        return [
            target
            for target_id in self.log_ignore_ids
            if (target := self.guild.get_channel(target_id))
            or (target := self.guild.get_member(target_id))
        ]

    @property
    def reassign_ignore(self) -> List[Role]:
        return [
            role
            for role_id in self.reassign_ignore_ids
            if (role := self.guild.get_role(role_id))
            is not None
        ]

    async def update(self, **kwargs):
        await self.bot.pool.execute(
            """
            UPDATE settings
            SET
            reskin = $2,
            reposter_prefix = $3,
            reposter_delete = $4,
            reposter_embed = $5,
            welcome_removal = $6,
            booster_role_base_id = $7,
            booster_role_include_ids = $8,
            lock_role_id = $9,
            lock_ignore_ids = $10,
            log_ignore_ids = $11,
            reassign_ignore_ids = $12,
            reassign_roles = $13,
            invoke_kick = $14,
            invoke_ban = $15,
            invoke_unban = $16,
            invoke_timeout = $17,
            invoke_untimeout = $18,
            play_panel = $19,
            play_deletion = $20,
            dm_enabled = $21,
            dm_ban = $22,
            dm_unban = $23,
            dm_kick = $24,
            dm_jail = $25,
            dm_unjail = $26,
            dm_mute = $27,
            dm_unmute = $28,
            dm_warn = $29,
            dm_timeout = $30,
            dm_untimeout = $31,
            dm_role_add = $32,
            dm_role_remove = $33,
            dm_antinuke_ban = $34,
            dm_antinuke_kick = $35,
            dm_antinuke_strip = $36,
            dm_antiraid_ban = $37,
            dm_antiraid_kick = $38,
            dm_antiraid_timeout = $39,
            dm_antiraid_strip = $40
            WHERE guild_id = $1
            """,
            self.guild.id,
            kwargs.get("reskin", self.reskin),
            kwargs.get(
                "reposter_prefix", self.reposter_prefix
            ),
            kwargs.get(
                "reposter_delete", self.reposter_delete
            ),
            kwargs.get(
                "reposter_embed", self.reposter_embed
            ),
            kwargs.get(
                "welcome_removal", self.welcome_removal
            ),
            kwargs.get(
                "booster_role_base_id",
                self.booster_role_base_id,
            ),
            kwargs.get(
                "booster_role_include_ids",
                self.booster_role_include_ids,
            ),
            kwargs.get("lock_role_id", self.lock_role_id),
            kwargs.get(
                "lock_ignore_ids", self.lock_ignore_ids
            ),
            kwargs.get(
                "log_ignore_ids", self.log_ignore_ids
            ),
            kwargs.get(
                "reassign_ignore_ids",
                self.reassign_ignore_ids,
            ),
            kwargs.get(
                "reassign_roles", self.reassign_roles
            ),
            kwargs.get("invoke_kick", self.invoke_kick),
            kwargs.get("invoke_ban", self.invoke_ban),
            kwargs.get("invoke_unban", self.invoke_unban),
            kwargs.get(
                "invoke_timeout", self.invoke_timeout
            ),
            kwargs.get(
                "invoke_untimeout", self.invoke_untimeout
            ),
            kwargs.get("play_panel", self.play_panel),
            kwargs.get("play_deletion", self.play_deletion),
            kwargs.get("dm_enabled", self.dm_enabled),
            kwargs.get("dm_ban", self.dm_ban),
            kwargs.get("dm_unban", self.dm_unban),
            kwargs.get("dm_kick", self.dm_kick),
            kwargs.get("dm_jail", self.dm_jail),
            kwargs.get("dm_unjail", self.dm_unjail),
            kwargs.get("dm_mute", self.dm_mute),
            kwargs.get("dm_unmute", self.dm_unmute),
            kwargs.get("dm_warn", self.dm_warn),
            kwargs.get("dm_timeout", self.dm_timeout),
            kwargs.get("dm_untimeout", self.dm_untimeout),
            kwargs.get("dm_role_add", self.dm_role_add),
            kwargs.get(
                "dm_role_remove", self.dm_role_remove
            ),
            kwargs.get(
                "dm_antinuke_ban", self.dm_antinuke_ban
            ),
            kwargs.get(
                "dm_antinuke_kick", self.dm_antinuke_kick
            ),
            kwargs.get(
                "dm_antinuke_strip", self.dm_antinuke_strip
            ),
            kwargs.get(
                "dm_antiraid_ban", self.dm_antiraid_ban
            ),
            kwargs.get(
                "dm_antiraid_kick", self.dm_antiraid_kick
            ),
            kwargs.get(
                "dm_antiraid_timeout",
                self.dm_antiraid_timeout,
            ),
            kwargs.get(
                "dm_antiraid_strip", self.dm_antiraid_strip
            ),
        )

        for key, value in kwargs.items():
            setattr(self, key, value)

        self.fetch.invalidate_containing(self.guild.id)

    @classmethod
    @cache()
    async def fetch(
        cls, bot: "heist", guild: Guild
    ) -> "Settings":
        record = await bot.pool.fetchrow(
            """
            INSERT INTO settings (guild_id)
            VALUES ($1)
            ON CONFLICT (guild_id)
            DO UPDATE
            SET guild_id = EXCLUDED.guild_id
            RETURNING *
            """,
            guild.id,
        )

        return cls(bot, guild, record)
