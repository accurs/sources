from __future__ import annotations
from math import ceil
from typing import TYPE_CHECKING, Any, List, Optional, TypedDict, Union, cast
from discord import ButtonStyle, Embed, HTTPException, Interaction, Message
from discord.ui import Button, View, Modal, TextInput
from discord.utils import as_chunks
from contextlib import suppress

if TYPE_CHECKING:
    from heist.framework.discord import Context

class EmbedField(TypedDict):
    name: str
    value: str
    inline: bool

Pages = Union[List[str], List[Embed]]

class NavigateModal(Modal):
    def __init__(self, paginator: "Paginator"):
        super().__init__(title="Navigate to Page")
        self.paginator = paginator
        self.page_input = TextInput(label="Page Number", placeholder=f"Enter page number (1-{len(paginator.pages)})", min_length=1, max_length=len(str(len(paginator.pages))))
        self.add_item(self.page_input)

    async def on_submit(self, interaction: Interaction):
        try:
            page_num = int(self.page_input.value)
            if not (1 <= page_num <= len(self.paginator.pages)):
                return await interaction.response.send_message(f"Invalid page number. Enter 1-{len(self.paginator.pages)}", ephemeral=True)
            if interaction.user.id == self.paginator.owner:
                await interaction.response.defer()
                self.paginator.index = page_num - 1
                self.paginator._update_buttons()
                page = self.paginator.pages[self.paginator.index]
                if self.paginator.message:
                    if isinstance(page, str):
                        await self.paginator.message.edit(content=page, view=self.paginator)
                    else:
                        await self.paginator.message.edit(embed=page, view=self.paginator)
                    await interaction.response.defer()
                else:
                    if isinstance(page, str):
                        await interaction.response.send_message(page, view=self.paginator, ephemeral=True)
                    else:
                        await interaction.response.send_message(embed=page, view=self.paginator, ephemeral=True)
                    self.paginator.message = await interaction.original_response()
            else:
                ephemeral_view = await self.paginator.create_ephemeral_copy(interaction)
                ephemeral_view.index = page_num - 1
                ephemeral_view._update_buttons()
                page = ephemeral_view.pages[ephemeral_view.index]
                if isinstance(page, str):
                    await interaction.response.send_message(page, view=ephemeral_view, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=page, view=ephemeral_view, ephemeral=True)
                ephemeral_view.message = await interaction.original_response()
        except ValueError:
            await interaction.response.send_message("Please enter a valid number", ephemeral=True)

class Paginator(View):
    def __init__(
        self,
        ctx: Context,
        pages: Pages | List[EmbedField],
        embed: Optional[Embed] = None,
        per_page: int = 10,
        counter: bool = True,
        show_entries: bool = False,
        delete_after: Optional[float] = None,
        message: Optional[Message] = None,
        hide_footer: bool = False,
        hide_nav: bool = False,
        owner=None,
        _is_ephemeral_copy=False,
        on_page_switch=None,
        arrows_only: bool = False,
        only_for_owner: bool = False,
        disable_cancel_button: bool = False
    ):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.message = message
        self.show_entries = show_entries
        self.total_entries = len(pages)
        self.pages = self._format_pages(pages, embed, per_page, counter, hide_footer)
        self.index = 0
        self.delete_after = delete_after
        self.hide_nav = hide_nav
        self.owner = owner or ctx.author.id
        self._is_ephemeral_copy = _is_ephemeral_copy
        self.persistent_items = []
        self.on_page_switch = on_page_switch
        self.arrows_only = arrows_only
        self.only_for_owner = only_for_owner
        self.disable_cancel_button = disable_cancel_button
        if not hide_nav and len(self.pages) > 1:
            for button in self.buttons:
                if self.arrows_only and button.custom_id not in ("paginator:previous", "paginator:next"):
                    continue
                if self._is_ephemeral_copy and button.custom_id == "paginator:cancel":
                    continue
                if self.disable_cancel_button and button.custom_id == "paginator:cancel":
                    continue
                button.callback = self.callback
                self.add_item(button)
        self._update_buttons()

    async def on_timeout(self) -> None:
        if self.message and not getattr(self, "_is_ephemeral_copy", False):
            for child in self.children:
                if isinstance(child, Button) and child.url is None:
                    child.disabled = True
            with suppress(HTTPException):
                page = self.pages[self.index]
                if isinstance(page, str):
                    await self.message.edit(content=page, view=self)
                else:
                    await self.message.edit(embed=page, view=self)
        self.stop()

    async def create_ephemeral_copy(self, interaction: Interaction) -> Paginator:
        ephemeral_view = Paginator(
            ctx=self.ctx,
            pages=self.pages,
            embed=None,
            per_page=10,
            counter=False,
            show_entries=self.show_entries,
            delete_after=None,
            message=None,
            hide_footer=True,
            hide_nav=self.hide_nav,
            owner=interaction.user.id,
            _is_ephemeral_copy=True,
            on_page_switch=self.on_page_switch,
            arrows_only=self.arrows_only,
            only_for_owner=self.only_for_owner
        )
        ephemeral_view.index = self.index
        ephemeral_view._update_buttons()
        for item in self.persistent_items:
            ephemeral_view.add_persistent_item(item)
        return ephemeral_view

    @property
    def buttons(self):
        emojis = getattr(getattr(self.ctx, "config", None), "emojis", getattr(self.ctx.bot.config, "emojis", None)).paginator
        base = [
            Button(custom_id="paginator:previous", style=ButtonStyle.primary, emoji=emojis.previous),
            Button(custom_id="paginator:next", style=ButtonStyle.primary, emoji=emojis.next),
            Button(custom_id="paginator:navigate", style=ButtonStyle.secondary, emoji=emojis.navigate),
        ]
        if not self.disable_cancel_button:
            base.append(Button(custom_id="paginator:cancel", style=ButtonStyle.danger, emoji=emojis.cancel))
        return base

    def _format_pages(self, pages: Pages | List[EmbedField], embed: Optional[Embed], per_page: int, counter: bool, hide_footer: bool) -> Pages:
        compiled: List = []
        if not embed:
            if all(isinstance(page, str) for page in pages):
                pages = cast(List[str], pages)
                for index, page in enumerate(pages, start=1):
                    if "page" not in page and counter and not hide_footer:
                        page = f"({index}/{len(pages)}) {page}"
                    compiled.append(page)
            elif all(isinstance(page, Embed) for page in pages):
                pages = cast(List[Embed], pages)
                for index, page in enumerate(pages, start=1):
                    if counter and not hide_footer:
                        self._add_footer(page, index, len(pages))
                    compiled.append(page)
        elif all(isinstance(page, dict) for page in pages):
            pages = cast(List[EmbedField], pages)
            total_pages = ceil(len(pages) / per_page)
            for chunk in as_chunks(pages, per_page):
                prepared = embed.copy()
                for field in chunk:
                    field["inline"] = field.get("inline", False)
                    prepared.add_field(**field)
                if not hide_footer:
                    self._add_footer(prepared, len(compiled) + 1, total_pages)
                compiled.append(prepared)
        elif all(isinstance(page, Embed) for page in pages):
            pages = cast(List[Embed], pages)
            total_pages = len(pages)
            for index, page in enumerate(pages, start=1):
                if counter and not hide_footer:
                    self._add_footer(page, index, total_pages)
                compiled.append(page)
        if not compiled and embed:
            compiled = [embed]
        return compiled

    def _update_buttons(self) -> None:
        if len(self.pages) <= 1:
            return
        prev_button = next((b for b in self.children if getattr(b, "custom_id", None) == "paginator:previous"), None)
        next_button = next((b for b in self.children if getattr(b, "custom_id", None) == "paginator:next"), None)
        if prev_button:
            prev_button.disabled = self.index == 0
        if next_button:
            next_button.disabled = self.index == len(self.pages) - 1

    def _add_footer(self, embed: Embed, page: int, pages: int) -> None:
        if pages == 1:
            return
        to_add: List[str] = []
        if embed.footer.text:
            to_add.append(embed.footer.text)
        footer_text = f"{page}/{pages}"
        if self.show_entries:
            footer_text += f" ({self.total_entries:,} entries)"
        to_add.append(footer_text)
        embed.set_footer(text=" • ".join(to_add), icon_url=embed.footer.icon_url)

    async def start(self, **kwargs: Any) -> Message:
        if not self.pages:
            raise ValueError("No pages to paginate")
        delete_after = self.delete_after or cast(float, kwargs.pop("delete_after", 0))
        page = self.pages[self.index]
        if self.message:
            if isinstance(page, str):
                await self.message.edit(content=page, view=self)
            else:
                await self.message.edit(embed=page, view=self)
        else:
            self._update_buttons()
            if isinstance(page, str):
                self.message = await self.ctx.send(content=page, view=self, **kwargs)
            else:
                self.message = await self.ctx.send(embed=page, view=self, **kwargs)
        if delete_after and not self._is_ephemeral_copy:
            with suppress(HTTPException):
                if self.ctx.message:
                    await self.ctx.message.delete(delay=delete_after)
            with suppress(HTTPException):
                if self.message:
                    await self.message.delete(delay=delete_after)
        return self.message

    async def interaction_check(self, interaction: Interaction) -> bool:
        if self.only_for_owner and interaction.user.id != self.owner:
            embed = Embed(description="You cannot interact with this **menu**.", color=self.ctx.bot.config.colors.information)
            try:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except:
                pass
            return False
        return True

    async def callback(self, interaction: Interaction) -> None:
        custom_id = interaction.data["custom_id"]
        if custom_id == "paginator:navigate" and not self.arrows_only:
            await self.wait_for_page(interaction)
            return
        if custom_id == "paginator:cancel" and not self.arrows_only:
            if interaction.user.id != self.owner:
                embed = Embed(description="You cannot interact with this **menu**.", color=self.ctx.bot.config.colors.information)
                return await interaction.response.send_message(embed=embed, ephemeral=True)
            await interaction.response.defer()
            with suppress(HTTPException):
                if self.message:
                    await self.message.delete()
            with suppress(HTTPException):
                if self.ctx.message:
                    await self.ctx.message.delete()
            return self.stop()
        if interaction.user.id == self.owner:
            await interaction.response.defer()
            await self._change_index(custom_id)
            return
        if getattr(self, "_is_ephemeral_copy", False):
            await interaction.response.defer()
            await self._change_index(custom_id)
            return
        if not self.only_for_owner:
            ephemeral_view = await self.create_ephemeral_copy(interaction)
            await ephemeral_view._change_index(custom_id)
            page = ephemeral_view.pages[ephemeral_view.index]
            if isinstance(page, str):
                await interaction.response.send_message(page, view=ephemeral_view, ephemeral=True)
            else:
                await interaction.response.send_message(embed=page, view=ephemeral_view, ephemeral=True)
            ephemeral_view.message = await interaction.original_response()

    async def _change_index(self, custom_id):
        if custom_id == "paginator:previous":
            self.index = max(self.index - 1, 0) if self.index != 0 else len(self.pages) - 1
        elif custom_id == "paginator:next":
            self.index = min(self.index + 1, len(self.pages) - 1) if self.index != len(self.pages) - 1 else 0
        self._update_buttons()
        if self.on_page_switch:
            await self.on_page_switch(self)
        page = self.pages[self.index]
        if self.message:
            if isinstance(page, str):
                await self.message.edit(content=page, view=self)
            else:
                await self.message.edit(embed=page, view=self)

    async def wait_for_page(self, interaction: Interaction) -> None:
        modal = NavigateModal(self)
        await interaction.response.send_modal(modal)

    def add_link_button(self, url: str, emoji: Optional[str] = None, persist: bool = False, disabled: bool = False):
        button = Button(style=ButtonStyle.link, url=url, emoji=emoji, disabled=disabled)
        if persist:
            self.add_persistent_item(button)
        else:
            self.add_item(button)

    def add_custom_button(self, callback, emoji: Optional[str] = None, style: ButtonStyle = ButtonStyle.secondary, disabled: bool = False, custom_id: Optional[str] = None, persist: bool = False):
        button = Button(style=style, emoji=emoji, custom_id=custom_id, disabled=disabled)
        async def wrapped_callback(interaction: Interaction):
            await callback(interaction, self)
        button.callback = wrapped_callback
        self.add_item(button)
        if persist:
            self.add_persistent_item(button)

    def add_persistent_item(self, item):
        if item not in self.persistent_items:
            self.persistent_items.append(item)
            self.add_item(item)
