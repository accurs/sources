from ...types.plugin import Plugin
from ...types.context import Context
from discord.ext.commands import command, group

from bot.converters.tagscript import TagScript
from .interface import EmbedBuilderView
from uuid import uuid4

class Embed(Plugin):
    @command(aliases=["say", "ce"])
    async def send(self, ctx: Context, *, script: TagScript):
        await ctx.send(**script.dump)  # type: ignore

    @group(aliases=["builder"])
    async def embed(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @embed.command(aliases=["new"])
    async def create(self, ctx: Context, name: str):
        view = EmbedBuilderView(self.bot.pool, name, ctx.author.id)
        await view.send(ctx, create=True)

    @embed.command(aliases=["redo"])
    async def edit(self, ctx: Context, name: str):
        view = EmbedBuilderView(self.bot.pool, name, ctx.author.id)
        await view.send(ctx, create=False)