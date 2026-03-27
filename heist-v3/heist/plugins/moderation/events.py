from discord import Member, Guild, User
from discord.ext.commands import Cog

class ModerationEvents(Cog):
    def __init__(self, bot):
        self.bot = bot

    @Cog.listener("on_member_update")
    async def on_forcenick(self, before: Member, after: Member):
        """Enforce force nicknames when members try to change them"""
        if before.guild.me.guild_permissions.manage_nicknames:
            if str(before.nick) != str(after.nick):
                redis_key = f"forcenick:{before.guild.id}:{before.id}"
                nickname = await self.bot.redis.get(redis_key)
                
                if not nickname:
                    nickname = await self.bot.pool.fetchval(
                        "SELECT nickname FROM forcenick WHERE guild_id = $1 AND user_id = $2",
                        before.guild.id, before.id
                    )
                    if nickname:
                        await self.bot.redis.set(redis_key, nickname, ex=3600)
                
                if nickname and str(after.nick) != nickname:
                    if (
                        after.top_role < after.guild.me.top_role
                        and after.id != after.guild.owner_id
                    ):
                        await after.edit(nick=nickname, reason="Force nickname")

    @Cog.listener()
    async def on_member_remove(self, member: Member):
        await self.bot.pool.execute(
            """
            INSERT INTO role_restore VALUES ($1,$2,$3)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET
            roles = $3
            """,
            member.guild.id,
            member.id,
            list(map(lambda r: r.id, member.roles)),
        )

    @Cog.listener("on_member_join")
    async def hardban_check(self, member: Member):
        """Listen for hardbanned users joining"""
        if await self.bot.pool.fetchrow(
            "SELECT * FROM hardban WHERE guild_id = $1 AND user_id = $2",
            member.guild.id, member.id
        ):
            await member.guild.ban(member, reason="User is hardbanned")

async def setup(bot):
    await bot.add_cog(ModerationEvents(bot))