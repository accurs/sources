from ...types.plugin import Plugin
from ...types.context import Context

from subprocess import check_output

from discord.ext.commands import command, group


class Developer(Plugin):
    async def cog_check(self, ctx: Context):
        return await self.bot.is_owner(ctx.author)

    @group(aliases=["sys"])
    async def system(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            return

    @system.command(aliases=["r"])
    async def restart(self, ctx: Context, *, process: str = "aerith"):
        await ctx.respond("restarting")
        output = check_output(["systemctl", "restart", process], text=True)

        await ctx.respond(f"```{output}```")

    @system.command(aliases=["l"])
    async def logs(self, ctx: Context, *, process: str = "aerith"):
        output = check_output(
            ["journalctl", "-u", process, "-n", "100", "--no-pager"], text=True
        )

        await ctx.respond(f"```ansi\n{output[-3900:]}\n```")

    @system.command(aliases=["tb", "err"])
    async def traceback(self, ctx: Context, *, error: str):
        if self.bot.redis is not None:
            err = await self.bot.redis.get(name=f"err-{error}")

            if err is None:
                return await ctx.respond("error doesnt exist")
            return await ctx.respond(f"```ansi\n{err}\n```")

    @command()
    async def test(self, ctx: Context):
        if a := ctx.flags.get("a"):
            await ctx.respond(f"flag a is {a}")
        else:
            await ctx.respond("this is a test command")
