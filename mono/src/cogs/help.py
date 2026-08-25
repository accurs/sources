from __future__ import annotations

from dataclasses import dataclass

import discord
from discord.ext import commands

from src.services.prefixes import DEFAULT_PREFIX, store as prefix_store


@dataclass(slots=True)
class HelpDetail:
    cog: str
    description: str
    usage: str | None
    aliases: tuple[str, ...]
    display_name: str
    subcommands: tuple[str, ...] = ()


class CogSelect(discord.ui.Select):
    def __init__(self, menu: CommandMenu) -> None:
        self.menu = menu
        super().__init__(
            placeholder="Choose a command category",
            options=[
                discord.SelectOption(
                    label=cog_name,
                    value=str(index),
                    description=f"View {len(command_lines)} command(s)",
                    default=index == menu.current_page,
                )
                for index, (cog_name, command_lines) in enumerate(menu.pages)
            ],
            disabled=menu.expired,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.menu.current_page = int(self.values[0])
        self.menu.render_page()
        await interaction.response.edit_message(view=self.menu)


class CommandMenu(discord.ui.LayoutView):

    def __init__(
        self,
        pages: list[tuple[str, list[str]]],
        author_id: int,
        prefix: str,
        current_page: int = 0,
    ) -> None:
        super().__init__(timeout=180)
        self.pages = pages
        self.author_id = author_id
        self.prefix = prefix
        self.current_page = current_page
        self.expired = False
        self.message: discord.Message | None = None
        self.render_page()

    def render_page(self) -> None:
        self.clear_items()

        cog_name, command_lines = self.pages[self.current_page]
        command_text = "```\n" + ", ".join(command_lines) + "\n```"

        selector = CogSelect(self)
        selector_row = discord.ui.ActionRow(selector)

        container = discord.ui.Container(
            discord.ui.TextDisplay(f"### {cog_name} Commands"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(command_text),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                f"-# {len(command_lines)} command(s) in {cog_name} • "
                f"/ means slash-only; unmarked commands accept the {self.prefix} prefix"
            ),
            selector_row,
        )

        self.add_item(container)

    async def on_timeout(self) -> None:
        self.expired = True
        self.render_page()

        if self.message is None:
            return

        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.author_id:
            return True

        await interaction.response.send_message(
            "This menu belongs to someone else.",
            ephemeral=True,
        )
        return False

class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def command_catalog(
        self,
        *,
        include_owner: bool = False,
    ) -> tuple[
        list[tuple[str, list[str]]],
        dict[str, HelpDetail],
    ]:
        pages: list[tuple[str, list[str]]] = []
        details: dict[str, HelpDetail] = {}
        owner_command_names: list[str] = []

        for cog_name, loaded_cog in sorted(self.bot.cogs.items()):
            command_names: list[str] = []
            added_names: set[str] = set()

            for command in loaded_cog.walk_commands():
                if command.hidden:
                    continue
                name = command.qualified_name
                prefix_name = (
                    name.replace("balance-edit", "balance edit", 1)
                    if name == "balance-edit" or name.startswith("balance-edit ")
                    else name
                )
                description = (
                    getattr(command, "description", None)
                    or command.help
                    or "No description provided."
                )
                description_text, separator, embedded_usage = description.partition(
                    "Usage:"
                )
                if separator:
                    description = description_text.rstrip()
                    usage = embedded_usage.strip() or None
                else:
                    usage = command.usage
                if not usage:
                    signature = command.signature.strip()
                    usage = f"{DEFAULT_PREFIX}{prefix_name}"
                    if signature:
                        usage += f" {signature}"
                children = tuple(
                    child.qualified_name.replace("balance-edit", "balance edit", 1)
                    for child in getattr(command, "commands", ())
                    if not child.hidden
                )
                if command.parent is None:
                    label = prefix_name
                    if children:
                        label += "+"
                    command_names.append(label)
                aliases = tuple(command.aliases)
                detail = HelpDetail(
                    cog_name, description, usage, aliases, prefix_name, children
                )
                details[name.casefold()] = detail
                details[prefix_name.casefold()] = detail
                for alias in aliases:
                    details[alias.casefold()] = detail
                added_names.add(name)

            app_commands_to_visit = list(loaded_cog.get_app_commands())
            while app_commands_to_visit:
                command = app_commands_to_visit.pop(0)
                name = command.qualified_name
                children_objects = tuple(getattr(command, "commands", ()))
                app_commands_to_visit.extend(children_objects)
                if name in added_names:
                    continue
                display_name = f"/{name}"
                if name == "o" or name.startswith("o "):
                    if not include_owner or isinstance(command, discord.app_commands.Group):
                        continue
                    owner_command_names.append(display_name)
                    detail = HelpDetail(
                        "Owner", command.description or "No description provided.",
                        None, (), display_name,
                    )
                    details[name.casefold()] = detail
                    details[display_name.casefold()] = detail
                    continue
                children = tuple(f"/{child.qualified_name}" for child in children_objects)
                if getattr(command, "parent", None) is None:
                    label = display_name
                    if children:
                        label += "+"
                    command_names.append(label)
                detail = HelpDetail(
                    cog_name, command.description or "No description provided.",
                    None, (), display_name, children,
                )
                details[name.casefold()] = detail
                details[display_name.casefold()] = detail

            if command_names:
                pages.append((cog_name, sorted(set(command_names))))

        # Owner commands are re-parented under the dynamic /o tree at startup.
        # Walk that live tree directly because they no longer reliably appear
        # beneath the cog that originally declared them.
        if include_owner:
            owner_root = self.bot.tree.get_command("o")
            owner_commands_to_visit = list(
                getattr(owner_root, "commands", ())
            )
            while owner_commands_to_visit:
                command = owner_commands_to_visit.pop(0)
                children = list(getattr(command, "commands", ()))
                if children:
                    owner_commands_to_visit.extend(children)
                    continue
                display_name = f"/{command.qualified_name}"
                owner_command_names.append(display_name)
                detail = HelpDetail(
                    "Owner", command.description or "No description provided.",
                    None, (), display_name,
                )
                details[command.qualified_name.casefold()] = detail
                details[display_name.casefold()] = detail

        if include_owner and owner_command_names:
            pages.append(("Owner", sorted(set(owner_command_names))))

        # Public slash commands can be re-parented into dynamic groups such as
        # /game and /image after their cogs load. Once moved, get_app_commands()
        # no longer exposes them through the original cog, so index the live
        # tree as a final pass.
        page_commands = {name: list(names) for name, names in pages}
        for root in self.bot.tree.get_commands():
            if root.name == "o":
                continue
            commands_to_visit = [root]
            while commands_to_visit:
                app_command = commands_to_visit.pop(0)
                # User/message context menus are right-click actions, not
                # typed slash commands, and do not expose descriptions.
                if isinstance(app_command, discord.app_commands.ContextMenu):
                    continue
                children_objects = tuple(getattr(app_command, "commands", ()))
                commands_to_visit.extend(children_objects)
                name = app_command.qualified_name
                display_name = f"/{name}"
                if name.casefold() in details or display_name.casefold() in details:
                    continue
                binding = getattr(app_command, "binding", None)
                cog_name = getattr(binding, "qualified_name", None)
                if not cog_name:
                    # Dynamic parent groups inherit the category of their first
                    # bound child (for example /game belongs to Fun).
                    child_binding = next(
                        (getattr(child, "binding", None) for child in children_objects
                         if getattr(child, "binding", None) is not None),
                        None,
                    )
                    cog_name = getattr(child_binding, "qualified_name", None) or "Other"
                children = tuple(f"/{child.qualified_name}" for child in children_objects)
                detail = HelpDetail(
                    cog_name,
                    app_command.description or "No description provided.",
                    None,
                    (),
                    display_name,
                    children,
                )
                details[name.casefold()] = detail
                details[display_name.casefold()] = detail
                if getattr(app_command, "parent", None) is None:
                    page_commands.setdefault(cog_name, []).append(
                        display_name + ("+" if children else "")
                    )

        pages = [
            (name, sorted(set(names)))
            for name, names in sorted(page_commands.items())
            if names
        ]

        return pages, details

    @commands.hybrid_command(
        name="help",
        aliases=["h"],
        description="List all available commands",
    )
    @discord.app_commands.describe(
        command="Show the description for one command",
        cog="Open Help directly on this command category",
    )
    async def help_command(
        self,
        ctx: commands.Context,
        command: str | None = None,
        cog: str | None = None,
        ephemeral: bool = False,
    ) -> None:
        include_owner = await self.bot.can_use_owner_commands(ctx.author)
        pages, details = self.command_catalog(include_owner=include_owner)
        prefix = (
            prefix_store.get(ctx.guild.id)
            if ctx.guild is not None
            else DEFAULT_PREFIX
        )

        if not pages:
            await ctx.send("No commands available.")
            return

        # Prefix invocations split `;help welcome setup` across the command and
        # cog parameters. Prefer the combined multi-word command when it exists.
        if ctx.interaction is None and command and cog:
            combined = " ".join((command, cog)).strip()
            if combined.casefold() in details:
                command = combined
                cog = None

        # For prefix use, `;help Economy` opens the cog when it is not a command.
        if command and not cog:
            normalized_argument = command.casefold().replace(" ", "").replace("_", "")
            matching_cog = next((
                name for name, _ in pages
                if name.casefold().replace(" ", "").replace("_", "")
                == normalized_argument
            ), None)
            if matching_cog and command.casefold() not in details:
                cog = matching_cog
                command = None

        if command:
            key = " ".join(command.strip().split()).casefold()
            detail = details.get(key)
            if detail is None:
                await ctx.send(
                    f"Command `{command}` not found. "
                    "Use `/help` to browse available commands."
                )
                return
            cog_name = detail.cog
            description = detail.description
            usage = detail.usage
            aliases = detail.aliases
            display_name = detail.display_name
            quoted_description = "\n".join(
                f"> {line}" if line else ">"
                for line in description.splitlines()
            )
            if usage and usage.startswith(DEFAULT_PREFIX):
                usage = prefix + usage[len(DEFAULT_PREFIX):]
            usage_text = f"\n\n**Usage:** `{usage}`" if usage else ""
            alias_text = ""
            if aliases:
                formatted_aliases = ", ".join(f"`{prefix}{alias}`" for alias in aliases)
                alias_text = f"\n\n**Prefix aliases:** {formatted_aliases}"
            subcommand_text = ""
            if detail.subcommands:
                formatted = "\n".join(
                    f"- `{name if name.startswith('/') else prefix + name}`"
                    for name in detail.subcommands
                )
                subcommand_text = f"\n\n### Subcommands\n{formatted}"
            view = discord.ui.LayoutView()
            view.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay(
                        f"## {display_name}\n{quoted_description}"
                        f"{usage_text}{alias_text}{subcommand_text}\n\n-# Cog: {cog_name}"
                    )
                )
            )
            await ctx.send(view=view)
            return

        current_page = 0
        if cog:
            wanted = cog.strip().casefold().replace(" ", "").replace("_", "")
            for index, (cog_name, _) in enumerate(pages):
                normalized = cog_name.casefold().replace(" ", "").replace("_", "")
                if normalized == wanted:
                    current_page = index
                    break
            else:
                available = ", ".join(name for name, _ in pages)
                await ctx.send(f"Unknown cog `{cog}`. Available cogs: {available}")
                return

        view = CommandMenu(
            pages=pages,
            author_id=ctx.author.id,
            prefix=prefix,
            current_page=current_page,
        )
        view.message = await ctx.send(view=view)

    @help_command.autocomplete("command")
    async def command_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[discord.app_commands.Choice[str]]:
        include_owner = await self.bot.can_use_owner_commands(interaction.user)
        _, details = self.command_catalog(include_owner=include_owner)
        query = " ".join(current.casefold().split())
        names = sorted(
            name
            for name in details
            if query in name
            and (name.startswith("/") or f"/{name}" not in details)
        )
        return [
            discord.app_commands.Choice(name=name, value=name)
            for name in names[:25]
        ]

    @help_command.autocomplete("cog")
    async def cog_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[discord.app_commands.Choice[str]]:
        include_owner = await self.bot.can_use_owner_commands(interaction.user)
        query = current.casefold().replace(" ", "").replace("_", "")
        names = [
            name for name, _ in self.command_catalog(
                include_owner=include_owner,
            )[0]
        ]
        matches = [
            name for name in names
            if query in name.casefold().replace(" ", "").replace("_", "")
        ]
        return [
            discord.app_commands.Choice(name=name, value=name)
            for name in matches[:25]
        ]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))
