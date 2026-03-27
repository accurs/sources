from discord.ext import commands
from discord.ext.commands import Cog, command, group
from discord import Message, TextChannel, Embed, utils
from heist.framework.discord import Context
from discord.ext.commands import CommandError
from datetime import datetime, timedelta
from humanfriendly import parse_timespan
from typing import Optional
from random import sample

class Giveaway(Cog):
    def __init__(self, bot):
        self.bot = bot

    @group(name="giveaway", aliases=["gw"], invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def giveaway(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @giveaway.command(name="start")
    @commands.has_permissions(manage_channels=True)
    async def start(self, ctx: Context, channel: TextChannel, duration: str, winners: int, *, prize: str):
        """Start a giveaway"""
        end_time = datetime.now() + timedelta(seconds=parse_timespan(duration))
        embed = Embed(
            title=prize,
            description=f"React with 🎉 to enter the giveaway.\n**Ends:** {utils.format_dt(end_time, style='R')} ({utils.format_dt(end_time, style='F')})\n**Winners:** {winners}\n**Hosted by:** {ctx.author}",
            timestamp=datetime.now()
        )
        message = await channel.send(embed=embed)
        await message.add_reaction("🎉")
        await self.bot.pool.execute(
            "INSERT INTO giveaway (guild_id, user_id, channel_id, message_id, prize, emoji, winners, ends_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
            ctx.guild.id, ctx.author.id, channel.id, message.id, prize, "🎉", winners, end_time
        )
        return await ctx.message.add_reaction("👍")

    @giveaway.command(name="end")
    @commands.has_permissions(manage_channels=True)
    async def end(self, ctx: Context, message: Message):
        """End a giveaway early"""
        giveaway = await self.bot.pool.fetchrow(
            "SELECT * FROM giveaway WHERE message_id = $1", message.id
        )
        if not giveaway:
            return await ctx.warn("That is not a giveaway")
        
        self.bot.dispatch("giveaway_end", ctx.guild, message.channel, giveaway)
        return await ctx.message.add_reaction("👍")

    @giveaway.command(name="reroll")
    @commands.has_permissions(manage_channels=True)
    async def reroll(self, ctx: Context, message: Message, winners: int = 1):
        """Reroll giveaway winners"""
        giveaway = await self.bot.pool.fetchrow(
            "SELECT * FROM giveaway WHERE message_id = $1", message.id
        )
        if not giveaway:
            return await ctx.warn("That is not a giveaway")
        
        entries = await self.bot.pool.fetch(
            "SELECT user_id FROM giveaway_entries WHERE message_id = $1", message.id
        )
        valid_entries = [ctx.guild.get_member(entry['user_id']) for entry in entries if ctx.guild.get_member(entry['user_id'])]
        
        if not valid_entries:
            return await ctx.warn("No valid entries found")
        
        if len(valid_entries) < winners:
            new_winners = valid_entries
        else:
            new_winners = sample(valid_entries, winners)
        
        winners_string = ", ".join(m.mention for m in new_winners)
        embed = Embed(
            title=f"Winners for {giveaway['prize'][:25]}",
            description=f"{winners_string} {'have' if len(new_winners) > 1 else 'has'} won the giveaway from <@{giveaway['user_id']}>"
        )
        await ctx.reply(embed=embed)
        return await ctx.message.add_reaction("👍")

    @giveaway.command(name="cancel")
    @commands.has_permissions(manage_channels=True)
    async def cancel(self, ctx: Context, message: Message):
        """Cancel a giveaway"""
        await self.bot.pool.execute("DELETE FROM giveaway WHERE message_id = $1", message.id)
        await message.delete()
        return await ctx.approve("Successfully cancelled that giveaway")

    @giveaway.command(name="list")
    @commands.has_permissions(manage_channels=True)
    async def list(self, ctx: Context):
        """List active giveaways"""
        giveaways = await self.bot.pool.fetch(
            "SELECT * FROM giveaway WHERE guild_id = $1 AND ended = false", ctx.guild.id
        )
        if not giveaways:
            raise CommandError("There are no active giveaways in this server")
        
        embed = Embed(title="Giveaways")
        rows = []
        for i, giveaway in enumerate(giveaways, 1):
            link = f"https://discord.com/channels/{giveaway['guild_id']}/{giveaway['channel_id']}/{giveaway['message_id']}"
            rows.append(f"`{i}` [**{giveaway['prize']}**]({link})")
        
        return await ctx.paginate(rows, embed=embed)

async def setup(bot):
    from .events import GiveawayEvents
    await bot.add_cog(Giveaway(bot))
    await bot.add_cog(GiveawayEvents(bot))