from discord.ext import commands, tasks
from discord.ext.commands import Cog
from discord import RawReactionActionEvent, Embed, utils
from collections import defaultdict
from asyncio import Lock
from random import sample
from datetime import datetime, timedelta
from humanfriendly import parse_timespan
from heist.framework.discord import Context

class GiveawayEvents(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.locks = defaultdict(Lock)

    async def cog_load(self):
        self.giveaway_check.start()

    async def cog_unload(self):
        self.giveaway_check.stop()

    @tasks.loop(seconds=10)
    async def giveaway_check(self):
        async with self.locks["giveaway"]:
            try:
                giveaways = await self.bot.pool.fetch(
                    "SELECT * FROM giveaway WHERE ended = false AND ends_at <= $1", utils.utcnow()
                )
                for giveaway in giveaways:
                    channel = self.bot.get_channel(giveaway['channel_id'])
                    if channel:
                        self.bot.dispatch("giveaway_end", channel.guild, channel, giveaway)
            except Exception:
                pass

    @Cog.listener("on_giveaway_end")
    async def giveaway_ended(self, guild, channel, giveaway):
        try:
            message = await channel.fetch_message(giveaway['message_id'])
        except:
            message = None

        entries = await self.bot.pool.fetch(
            "SELECT user_id FROM giveaway_entries WHERE message_id = $1", giveaway['message_id']
        )
        valid_entries = [guild.get_member(entry['user_id']) for entry in entries if guild.get_member(entry['user_id'])]

        if not valid_entries:
            embed = Embed(title="🎉 Giveaway Ended", description="No entries for this giveaway.")
            await (message.edit(embed=embed) if message else channel.edit(embed=embed))
            await self.bot.pool.execute("UPDATE giveaway SET ended = true WHERE message_id = $1", giveaway['message_id'])
            return

        if len(valid_entries) < giveaway['winners']:
            winners = valid_entries
        else:
            winners = sample(valid_entries, giveaway['winners'])

        winners_string = ", ".join(m.mention for m in winners)
        embed = Embed(
            title="🎉 Giveaway ended",
            description=f"Won by: {winners_string}",
            timestamp=datetime.now()
        )
        await (message.edit(embed=embed) if message else channel.edit(embed=embed))
        await self.bot.pool.execute("UPDATE giveaway SET ended = true WHERE message_id = $1", giveaway['message_id'])

    @Cog.listener("on_raw_reaction_add")
    async def on_giveaway_enter(self, payload: RawReactionActionEvent):
        if str(payload.emoji) != "🎉":
            return
        if not (guild := self.bot.get_guild(payload.guild_id)):
            return
        if not (member := guild.get_member(payload.user_id)):
            return
        if member.bot:
            return

        giveaway = await self.bot.pool.fetchrow(
            "SELECT * FROM giveaway WHERE message_id = $1 AND ended = false", payload.message_id
        )
        if not giveaway:
            return

        existing = await self.bot.pool.fetchrow(
            "SELECT * FROM giveaway_entries WHERE message_id = $1 AND user_id = $2",
            payload.message_id, member.id
        )
        if existing:
            return

        await self.bot.pool.execute(
            "INSERT INTO giveaway_entries (message_id, user_id) VALUES ($1, $2)",
            payload.message_id, member.id
        )

    @Cog.listener("on_raw_reaction_remove")
    async def on_giveaway_leave(self, payload: RawReactionActionEvent):
        if str(payload.emoji) != "🎉":
            return
        if not (guild := self.bot.get_guild(payload.guild_id)):
            return
        if not (member := guild.get_member(payload.user_id)):
            return
        if member.bot:
            return

        await self.bot.pool.execute(
            "DELETE FROM giveaway_entries WHERE message_id = $1 AND user_id = $2",
            payload.message_id, member.id
        )

async def setup(bot):
    await bot.add_cog(GiveawayEvents(bot))