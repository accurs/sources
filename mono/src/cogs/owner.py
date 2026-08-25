from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


def owner_clearance():
    async def predicate(ctx: commands.Context) -> bool:
        checker = getattr(ctx.bot, "can_use_owner_commands", None)
        return bool(checker and await checker(ctx.author))

    return commands.check(predicate)


class OwnerOnlyGroup(app_commands.Group):
    """Application-command group that rejects every non-owner invocation."""

    def __init__(
        self,
        bot: commands.Bot,
        *,
        name: str = "o",
        description: str = "Bot owner controls",
        parent: app_commands.Group | None = None,
    ) -> None:
        self.bot = bot
        super().__init__(
            name=name,
            description=description,
            parent=parent,
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        is_primary_owner = getattr(self.bot, "can_use_owner_commands", None)
        return bool(
            is_primary_owner
            and await is_primary_owner(interaction.user)
        )


class Owner(commands.Cog):
    """Marker cog for the hidden owner-only application-command section."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Owner(bot))
