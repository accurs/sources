import discord

from typing import Any, Optional

from discord import Message
from discord.ext.commands import Context as BaseContext
from discord.ext.commands import _types

from ..managers.ui.embed import Embed

BotT = _types.BotT


class Context(BaseContext):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.flags = {}

    async def respond(
        self,
        text: str,
        *,
        emoji: Optional[str] = None,
        state: Optional[str] = None,
        delete_after: Optional[float] = None,
        reply: bool = False,
        author: bool = True,
        view: Optional[discord.ui.View] = None,
    ) -> Message:
        emojis = self.bot.config.emojis
        state_map = {
            "yes": emojis.YES,
            "no": emojis.NO,
            "warn": emojis.WARN,
        }

        resolved_emoji = state_map.get(state.lower()) if state else emoji

        prefix_parts: list[str] = []
        if resolved_emoji:
            prefix_parts.append(resolved_emoji)
        if author:
            prefix_parts.append(f"{self.author.mention}:")

        prefix = " ".join(prefix_parts)
        description = f"{prefix} {text}".strip() if prefix else text

        embed = Embed(description=description, components=view)

        kwargs: dict[str, Any] = {"view": embed}
        if delete_after is not None:
            kwargs["delete_after"] = delete_after

        send = self.reply if reply else self.send
        return await send(**kwargs)

    async def send_help(self, *args: Any) -> Any:
        return await super().send_help(*args)
