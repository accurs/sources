from __future__ import annotations

from discord.ext import commands

from bot.helpers.context import TormentContext


class CoreCommands(commands.Cog):
    __cog_name__ = "core"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(
        name="ping",
        help="check the bot latency",
        extras={"parameters": "n/a", "usage": "ping"},
    )
    async def ping(self, ctx: TormentContext) -> None:
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"It took **{latency}ms** to ping **torment's shards**.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CoreCommands(bot))
