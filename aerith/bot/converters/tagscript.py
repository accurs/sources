from discord.ext.commands import Converter
from bot import tagscript
from bot.types.context import Context
from bot.models.tagscript import ScriptObject
from typing import Optional

class TagScript(Converter):
    async def convert(self, ctx: Context, argument: str) -> ScriptObject:
        script: ScriptObject = tagscript.parse(
            script=argument,
            user=ctx.author,
            channel=ctx.channel,
        )
        return script


class LastFMTagScript:
    """Use this instead of TagScript when Last.fm context is available."""

    @staticmethod
    def parse(
        script: str,
        ctx: Context,
    ) -> ScriptObject:
        return tagscript.parse(
            script=script,
            user=ctx.author,
            channel=ctx.channel,
            guild=ctx.guild
        )