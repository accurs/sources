from __future__ import annotations

import asyncio

from discord.ext import commands

from src.services.prefixes import DEFAULT_PREFIX, store


class Prefixes(commands.Cog):
    """Administrator controls for server-specific command prefixes."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.group(
        name="prefix",
        invoke_without_command=True,
        help="Show or change this server's command prefix.",
    )
    @commands.guild_only()
    async def prefix(self, ctx: commands.Context) -> None:
        assert ctx.guild is not None
        current = store.get(ctx.guild.id)
        await ctx.send(
            f"This server's prefix is `{current}`.\n"
            f"Administrators can change it with `{current}prefix set <prefix>` or "
            f"reset it with `{current}prefix set`."
        )

    @prefix.command(
        name="set",
        help="Set this server's prefix; leave blank to reset it to ;.",
    )
    @commands.has_guild_permissions(administrator=True)
    async def prefix_set(
        self,
        ctx: commands.Context,
        *,
        new_prefix: str = "",
    ) -> None:
        assert ctx.guild is not None
        current = store.get(ctx.guild.id)
        if not new_prefix.strip():
            if current == DEFAULT_PREFIX:
                await ctx.send(
                    f"Enter a new prefix, for example `{DEFAULT_PREFIX}prefix set !`."
                )
                return
            await asyncio.to_thread(store.reset, ctx.guild.id)
            await ctx.send(f"The server prefix was reset to `{DEFAULT_PREFIX}`.")
            return

        new_prefix = new_prefix.strip()
        if len(new_prefix) > 5:
            await ctx.send("A prefix can be at most `5` characters long.")
            return
        if any(character.isspace() for character in new_prefix):
            await ctx.send("A prefix cannot contain spaces.")
            return
        if new_prefix.startswith(("<@", "/")):
            await ctx.send("Choose a visible prefix that is not a mention or `/`.")
            return

        if new_prefix == DEFAULT_PREFIX:
            await asyncio.to_thread(store.reset, ctx.guild.id)
            await ctx.send(f"The server prefix was reset to `{DEFAULT_PREFIX}`.")
            return

        await asyncio.to_thread(store.set, ctx.guild.id, new_prefix)
        await ctx.send(
            f"The server prefix is now `{new_prefix}`. Commands now begin with "
            f"`{new_prefix}`, including `{new_prefix}prefix set`."
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Prefixes(bot))
