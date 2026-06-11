from __future__ import annotations

import discord
from discord.ext import commands
from typing import Mapping, Optional, Sequence, TYPE_CHECKING, List, TypeVar, cast, Any

from bot.types.context import Context
from bot.managers.ui.embed import Embed as Container

if TYPE_CHECKING:
    from discord.ext.commands.cog import Cog

T = TypeVar("T", bound=commands.Command[Any, Any, Any])


class Help(commands.HelpCommand):
    def __init__(self, **options: Any) -> None:
        self.excluded_cogs: set[str] = {"jishaku", "developer"}
        super().__init__(
            command_attrs={"aliases": ["h", "cmds", "commands"], "hidden": True},
            **options,
        )

    @property
    def ctx(self) -> Context:
        return cast(Context, self.context)

    @property
    def thumbnail(self) -> Optional[str]:
        guild = self.ctx.message.guild
        return (
            (
                guild.me.display_avatar.url
                if guild
                else self.ctx.bot.user.display_avatar.url
            )
            if self.ctx.message.author.avatar
            else None
        )

    def _prefix(self) -> str:
        return cast(str, getattr(self.context, "clean_prefix", ","))

    async def _filter(self, cmds: Sequence[T]) -> List[T]:
        return cast(List[T], await self.filter_commands(list(cmds), sort=True))

    def _permissions(self, command: commands.Command[Any, Any, Any]) -> List[str]:
        perms: List[str] = []
        for check in command.checks:
            for cell in getattr(check, "__closure__", None) or []:
                try:
                    val = cell.cell_contents
                    if isinstance(val, dict):
                        perms.extend(p.replace("_", " ") for p, v in val.items() if v)
                except ValueError:
                    continue
        return perms

    def _build(
        self, command: commands.Command[Any, Any, Any], *, footer: Optional[str] = None
    ) -> Container:
        aliases = ", ".join(command.aliases) if command.aliases else "none"
        perms = self._permissions(command)

        desc = "\n".join(
            filter(
                None,
                [
                    f"-# **aliases**: {aliases}",
                    f"-# **permissions**: {', '.join(perms)}" if perms else None,
                    f"```{self._prefix()}{command.qualified_name} {command.signature}```",
                    command.description or command.help or "no description provided.",
                ],
            )
        )

        layout = Container(
            title=command.qualified_name.lower(),
            description=desc,
            thumbnail=self.thumbnail,
        )
        layout.set_footer(text=footer or f"; module: {command.cog_name or 'global'}")
        return layout

    async def send_command_help(self, command: commands.Command[Any, Any, Any]) -> None:
        await self.ctx.reply(view=self._build(command))

    async def send_group_help(self, group: commands.Group[Any, Any, Any]):
        subcommands = sorted(group.commands, key=lambda c: c.name)

        if not subcommands:
            return await self.ctx.reply(view=self._build(group))

        layout = self._build(
            group,
            footer=f"; module: {group.cog_name or 'global'} · {len(subcommands)} subcommands",
        )

        select = discord.ui.Select(
            placeholder="select a subcommand...",
            options=[
                discord.SelectOption(
                    label=c.qualified_name[:100],
                    value=c.qualified_name,
                    description=(c.description or c.help or "no description")[:100],
                )
                for c in subcommands
            ],
        )

        async def on_select(interaction: discord.Interaction):
            if interaction.user.id != self.ctx.author.id:
                return await interaction.response.send_message(
                    "this menu isn't for you.", ephemeral=True
                )
            cmd = next(
                (c for c in subcommands if c.qualified_name == select.values[0]), None
            )
            if not cmd:
                return
            new_layout = self._build(
                cmd,
                footer=f"; module: {cmd.cog_name or 'global'} · {group.qualified_name}",
            )
            new_layout._components.append(select)
            new_layout._rebuild()
            await interaction.response.edit_message(view=new_layout)

        select.callback = on_select
        layout._components.append(select)
        layout._rebuild()
        await self.ctx.reply(view=layout)

    async def send_cog_help(self, cog: Cog):
        if cog.qualified_name.lower() in self.excluded_cogs:
            return await self.send_error_message(
                self.command_not_found(cog.qualified_name)
            )

        cmds = await self._filter(list(cog.get_commands()))
        if not cmds:
            return await self.ctx.respond(
                f"no visible commands in **{cog.qualified_name}**.", state="no"
            )

        layout = Container(
            title=cog.qualified_name.lower(),
            description=f"```{', '.join(c.qualified_name for c in cmds)}```",
            thumbnail=self.thumbnail,
        )
        layout.set_footer(text=f"; {len(cmds)} command{'s' if len(cmds) != 1 else ''}")
        await self.ctx.reply(view=layout)

    async def send_bot_help(
        self, mapping: Mapping[Optional[Cog], Sequence[commands.Command[Any, Any, Any]]]
    ) -> None:
        layout = Container(
            description="> use [the website](https://aerith.lol/commands) for the command list"
        )
        await self.context.send(view=layout)

    async def send_error_message(self, error: str) -> None:
        await self.ctx.respond(error.lower(), state="no")

    def command_not_found(self, string: str) -> str:
        return f"no command called `{string}` found"

    def subcommand_not_found(
        self, command: commands.Command[Any, Any, Any], string: str
    ) -> str:
        if hasattr(command, "commands"):
            return f"`{command.qualified_name}` has no subcommand called `{string}`"
        return f"`{command.qualified_name}` has no subcommands"
