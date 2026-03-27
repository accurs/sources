from asyncio import Lock
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional
from discord import Client, Embed, Guild, Member, utils
from discord.ext.commands import Cog

class AntiRaidEvents(Cog):
    def __init__(self, bot: Client):
        self.bot = bot
        self.locks = defaultdict(Lock)

    async def check_member(
        self,
        member: Member,
        guild: Guild,
        config: dict,
        dispatch: Optional[bool] = True,
    ) -> tuple:
        whitelist = config.get('whitelist') or []
        if config.get('raid_status') is True and member.id not in whitelist:
            if datetime.now() > config.get('raid_expires_at'):
                await self.bot.pool.execute(
                    """UPDATE antiraid SET raid_triggered_at = NULL, raid_expires_at = NULL WHERE guild_id = $1""",
                    guild.id,
                )
            else:
                return True, config.get('join_punishment'), "Raid is active"
        if member.id in whitelist:
            return False, None, None
        if (
            config.get('new_accounts') is True
            and member.created_at
            < datetime.now() - timedelta(days=config.get('new_account_threshold'))
        ):
            return True, config.get('new_account_punishment'), "New Account"
        if config.get('no_avatar') and not member.avatar:
            return True, config.get('no_avatar_punishment'), "No Avatar"
        if (
            await self.bot.redis.get(f"raid:{guild.id}")
            and int(await self.bot.redis.get(f"raid:{guild.id}")) >= config.get('join_threshold', 10)
        ):
            expiration = datetime.now() + timedelta(minutes=10)
            await self.bot.pool.execute(
                """INSERT INTO antiraid (guild_id, raid_status, raid_triggered_at, raid_expires_at) VALUES($1, $2, $3, $4) ON CONFLICT(guild_id) DO UPDATE SET raid_status = excluded.raid_status, raid_triggered_at = excluded.raid_triggered_at, raid_expires_at = excluded.raid_expires_at""",
                guild.id,
                True,
                datetime.now(),
                expiration,
            )
            self.bot.dispatch("raid", member, guild, expiration)
            return True, config.get('join_punishment'), "Mass Join"

        return False, None, None

    @Cog.listener("on_member_update")
    async def on_accepted(self, before: Member, after: Member):
        if before.pending and not after.pending:
            self.bot.dispatch("member_agree", after)

    @Cog.listener("on_raid")
    async def new_raid(self, member: Member, guild: Guild, expiration: datetime):
        try:
            await guild.owner.send(
                embed=Embed(
                    title="RAID",
                    description=f"your server {guild.name} (`{guild.id}`) is being raided, the raid will expire {utils.format_dt(expiration, style='R')}",
                )
            )
        except Exception:
            pass

async def setup(bot: Client):
    await bot.add_cog(AntiRaidEvents(bot))