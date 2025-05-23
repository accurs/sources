import asyncio
from inspect import iscoroutinefunction as iscoro
from inspect import isfunction as isfunc
from io import BytesIO

import discord
from discord import File


class prev_page(discord.ui.Button):
    def __init__(self, label, emoji, style, row):
        super().__init__(label=label, emoji=emoji, style=style, row=row)

    async def callback(self, interaction):
        await interaction.response.defer()
        view = self.view
        view.page -= 1
        if view.page < 0:
            view.page = len(view.embeds) - 1
        view.update_view()
        # await interaction.response.defer()
        await view.edit_embed(interaction)


class first_page(discord.ui.Button):
    def __init__(self, label, emoji, style, row):
        super().__init__(label=label, emoji=emoji, style=style, row=row)

    async def callback(self, interaction):
        await interaction.response.defer()
        view = self.view
        view.page = 0
        view.update_view()
        # await interaction.response.defer()
        await view.edit_embed(interaction)


class next_page(discord.ui.Button):
    def __init__(self, label, emoji, style, row):
        super().__init__(label=label, emoji=emoji, style=style, row=row)

    async def callback(self, interaction):
        await interaction.response.defer()
        view = self.view
        view.page += 1
        if view.page == len(view.embeds):
            view.page = 0
        view.update_view()
        # await interaction.response.defer()
        await view.edit_embed(interaction)


class last_page(discord.ui.Button):
    def __init__(self, label, emoji, style, row):
        super().__init__(label=label, emoji=emoji, style=style, row=row)

    async def callback(self, interaction):
        await interaction.response.defer()
        view = self.view
        view.page = len(view.embeds) - 1
        view.update_view()
        # await interaction.response.defer()
        await view.edit_embed(interaction)


class delete_page(discord.ui.Button):
    def __init__(self, label, emoji, style, row):
        super().__init__(label=label, emoji=emoji, style=style, row=row)

    async def callback(self, interaction):
        view = self.view
        await view.message.delete()
        # await interaction.response.defer()
        view.stop()


class end_page(discord.ui.Button):
    def __init__(self, label, emoji, style, row):
        super().__init__(label=label, emoji=emoji, style=style, row=row)

    async def callback(self, interaction):
        view = self.view
        for child in view.children:
            child.disabled = True
        await view.edit_embed(interaction)
        view.stop()


class show_page(discord.ui.Button):
    def __init__(self, label, emoji, style, row):
        super().__init__(label=label, emoji=emoji, style=style, disabled=True, row=row)


class goto_modal(discord.ui.Modal, title="Go to"):
    def __init__(self, button):
        super().__init__()
        self.button = button
        self.page_num = discord.ui.TextInput(
            label="Page",
            placeholder=f"page number 1-{len(self.button.view.embeds)}",
            style=discord.TextStyle.short,
            required=True,
        )
        self.add_item(self.page_num)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            view = self.button.view
            num = int(self.page_num.value) - 1

            if num in range(len(view.embeds)):
                view.page = num
            else:
                return await interaction.followup.send(
                    content="Invalid number: aborting", ephemeral=True
                )

            view.update_view()
            await view.edit_embed(interaction)
            try:
                await interaction.defer()
            except Exception:
                pass
        except ValueError:
            return await interaction.response.send_message(
                content="That's not a number", ephemeral=True
            )


class goto_page(discord.ui.Button):
    def __init__(self, label, emoji, style, row):
        super().__init__(label=label, emoji=emoji, style=style, row=row)

    async def callback(self, interaction):
        await interaction.response.send_modal(goto_modal(self))


class lock_page(discord.ui.Button):
    def __init__(self, label, emoji, style, row):
        super().__init__(label=label, emoji=emoji, style=style, row=row)

    async def callback(self, interaction):
        view = self.view
        view.clear_items()
        await view.edit_embed(interaction)
        view.stop()


class Paginator(discord.ui.View):
    def __init__(
        self,
        bot,
        embeds,
        destination,
        /,
        *,
        invoker=None,
        attachments=None,
        error_emoji=None,
        error_color=None,
    ):
        """A class which controls everything that happens
        Parameters
        -----------
        bot: :class:`Bot`
            The bot object
        embeds: :class:`list`
            The embeds that will be paginated
        destination: :class:`discord.abc.Messageable`
            The channel the pagination message will be sent to
        interactionfailed: Optional[Callable[..., :class:`bool`]]
            A function that will be called when the check failes
        check: Optional[Callable[..., :class:`bool`]]
            A predicate to check what to wait for.
        timeout: Optional[:class:`float`]
            The number of seconds to wait before timing out.
        """
        super().__init__(timeout=None)
        self.timeout = None
        interactionfailed = None
        check = None
        defer = True
        if error_emoji is None:
            self.emoji = "⚠️"
        else:
            self.emoji = error_emoji
        if error_color is None:
            self.color = int("d6bcd0", 16)
        else:
            self.color = int(error_color, 16)
        self.check = check
        self.bot = bot
        self.attachments = attachments
        self.defer = defer
        self.embeds = embeds
        self.page = 0
        self.destination = destination
        self.interactionfailed = interactionfailed
        self.invoker = invoker
        self.page_button = None

    def default_pagination(self):
        self.add_button("first", label="first")
        self.add_button("back", label="back")
        self.add_button("page", label="page")
        self.add_button("next", label="next")
        self.add_button("last", label="last")
        self.add_button("delete", label="Close paginator")

    async def edit_embed(self, interaction):
        current = self.embeds[self.page]
        if self.attachments:
            current_attachment = [self.attachments[self.page]]
            if isinstance(current, str):
                await interaction.message.edit(
                    content=current,
                    embed=None,
                    view=self,
                    attachments=current_attachment,
                )
            elif isinstance(current, discord.Embed):
                await interaction.message.edit(
                    content=None,
                    embed=current,
                    view=self,
                    attachments=current_attachment,
                )
            elif isinstance(current, tuple):
                dct = {}
                for item in current:
                    if isinstance(item, str):
                        dct["content"] = item
                    elif isinstance(item, discord.Embed):
                        dct["embed"] = item
                await interaction.message.edit(
                    content=dct.get("content", None),
                    embed=dct.get("embed", None),
                    view=self,
                    attachments=current_attachment,
                )
            elif isinstance(current, dict):
                attachments = []
                if files := current.get("files", current.get("attachments")):
                    for file in files:
                        attachments.append(
                            File(fp=BytesIO(file["data"]), filename=file["filename"])
                        )
                    current["attachments"] = attachments
                    current.pop("files", None)
                await interaction.message.edit(**current, view=self)
        else:
            if isinstance(current, str):
                await interaction.message.edit(content=current, embed=None, view=self)
            elif isinstance(current, discord.Embed):
                await interaction.message.edit(content=None, embed=current, view=self)
            elif isinstance(current, tuple):
                dct = {}
                for item in current:
                    if isinstance(item, str):
                        dct["content"] = item
                    elif isinstance(item, discord.Embed):
                        dct["embed"] = item
                await interaction.message.edit(
                    content=dct.get("content", None),
                    embed=dct.get("embed", None),
                    view=self,
                )
            elif isinstance(current, dict):
                attachments = []
                c = {}
                if files := current.get("files", current.get("attachments")):
                    for file in files:
                        attachments.append(
                            File(fp=BytesIO(file["data"]), filename=file["filename"])
                        )
                    c["attachments"] = attachments
                for key, value in current.items():
                    if key not in ("files", "attachments"):
                        c[key] = value
                await interaction.message.edit(**c, view=self)

    async def start(self):
        try:
            current = self.embeds[self.page]
            if self.attachments:
                current_attachment = self.attachments[self.page]
                if isinstance(current, str):
                    self.message = await self.destination.send(
                        content=current, embed=None, view=self, file=current_attachment
                    )
                elif isinstance(current, discord.Embed):
                    self.message = await self.destination.send(
                        content=None, embed=current, view=self, file=current_attachment
                    )
                elif isinstance(current, tuple):
                    dct = {}
                    for item in current:
                        if isinstance(item, str):
                            dct["content"] = item
                        elif isinstance(item, discord.Embed):
                            dct["embed"] = item
                    self.message = await self.destination.send(
                        content=dct.get("content", None),
                        embed=dct.get("embed", None),
                        view=self,
                        file=current_attachment,
                    )
            else:
                if isinstance(current, str):
                    self.message = await self.destination.send(
                        content=current, embed=None, view=self
                    )
                elif isinstance(current, discord.Embed):
                    self.message = await self.destination.send(
                        content=None, embed=current, view=self
                    )
                elif isinstance(current, dict):
                    attachments = []
                    c = {}
                    if files := current.get("files", current.get("attachments")):
                        for file in files:
                            attachments.append(
                                File(
                                    fp=BytesIO(file["data"]), filename=file["filename"]
                                )
                            )
                        c["files"] = attachments
                    for key, value in current.items():
                        if key not in ("files", "attachments"):
                            c[key] = value
                    self.message = await self.destination.send(**c, view=self)
                elif isinstance(current, tuple):
                    dct = {}
                    for item in current:
                        if isinstance(item, str):
                            dct["content"] = item
                        elif isinstance(item, discord.Embed):
                            dct["embed"] = item
                    self.message = await self.destination.send(
                        content=dct.get("content", None),
                        embed=dct.get("embed", None),
                        view=self,
                        file=current_attachment,
                    )

        except discord.HTTPException:
            self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        emoji = self.emoji
        if not self.invoker:
            pass
        else:
            if interaction.user.id != self.invoker:
                return await interaction.response.send_message(
                    ephemeral=True,
                    embed=discord.Embed(
                        description=f"{emoji} {interaction.user.mention}: **You aren't the author of this embed**",
                        color=self.color,
                    ),
                )
            else:
                pass
                return interaction.user.id == self.invoker
        if self.check is None:
            return True
        if not isfunc(self.check):
            raise ValueError
        try:
            if not self.check(interaction):
                if self.interactionfailed:
                    if iscoro(self.interactionfailed):
                        await self.interactionfailed(interaction)
                        await interaction.response.defer()
                return False
            return True
        except Exception:
            raise ValueError

    async def on_timeout(self):
        view = self.view
        view.clear_items()
        self.stop()

    def update_view(self):
        try:
            self.page_button.label = None
        except (NameError, AttributeError):
            pass

    def add_button(
        self,
        action,
        /,
        *,
        label="",
        emoji=None,
        style=discord.ButtonStyle.grey,
        row=None,
    ):
        action = action.strip().lower()
        if action not in [
            "first",
            "prev",
            "previous",
            "back",
            "delete",
            "next",
            "last",
            "end",
            "page",
            "show",
            "goto",
            "lock",
        ]:
            return
        elif action == "first":
            self.add_item(first_page(label, emoji, style, row))
        elif action in ["back", "prev", "previous"]:
            self.add_item(prev_page(label, emoji, style, row))
        elif action in ["page", "show"]:
            button = show_page("1", emoji, style, row)
            self.page_button = button
            self.add_item(button)
            self.update_view()
        elif action == "goto":
            button = goto_page(None, emoji, style, row)
            self.page_button = button
            self.add_item(button)
            self.update_view()
        elif action == "next":
            self.add_item(next_page(label, emoji, style, row))
        elif action == "last":
            self.add_item(last_page(label, emoji, style, row))
        elif action == "end":
            self.add_item(end_page(label, emoji, style, row))
        elif action == "delete":
            self.add_item(delete_page(label, emoji, style, row))
        elif action == "lock":
            self.add_item(lock_page(label, emoji, style, row))


def embed_creator(
    text, num, /, *, title="", prefix="", suffix="", color=None, colour=None
):
    """A helper function which takes some string and returns a list of embeds"""
    if color is not None and colour is not None:
        raise ValueError

    return [
        discord.Embed(
            title=title,
            description=prefix + (text[i : i + num]) + suffix,
            color=color if color is not None else colour,
        )
        for i in range(0, len(text), num)
    ]
