from __future__ import annotations
from typing import List, Mapping, Optional, Sequence, Union

import discord
from discord import MediaGalleryItem, ui
from .entries import AuthorEntry, FooterEntry, FieldEntry
from .normalizers import DataNormalizer, DescriptionCompiler


class Embed(ui.LayoutView):
    """
    A custom layout view that translates standard Discord embed structures into
    the modern LayoutView UI components.

    This class provides a familiar interface (similar to discord.Embed) for
    building complex message layouts using cv2/the modern LayoutView UI components.
    .set_author or .set_footer or any other reconstructive method will trigger
    a re-render of the entire layout, allowing for dynamic updates to the content.

    Attributes:
        container (ui.Container): The primary UI container holding the rendered components.

    Args:
        description (Optional[str]): The main body text. Supports
            "{separator.small}" and "{separator.large}" tokens for spacing.
        title (Optional[str]): The header title of the layout.
        thumbnail (Optional[str]): URL for a thumbnail image. If present,
            the first few text elements are wrapped in a ui.Section with
            this thumbnail as an accessory.
        main_image (Optional[str]): URL for a large image displayed via
            ui.MediaGallery.
        url (Optional[str]): A URL to hyperlink the title.
        fields (Optional[Union[Mapping[str, str], Sequence[FieldEntry]]]):
            A collection of header/body text pairs.
        components (Optional[Union[List[discord.ui.Item], discord.ui.View]]):
            UI items (Buttons, Selects) to be appended to the bottom.
        timeout (int): Duration in seconds before the view stops
            listening for interactions. Defaults to 180.
    """

    def __init__(
        self,
        *,
        description: Optional[str] = None,
        title: Optional[str] = None,
        thumbnail: Optional[str] = None,
        main_image: Optional[str] = None,
        url: Optional[str] = None,
        fields: Optional[Union[Mapping[str, str], Sequence[FieldEntry]]] = None,
        components: Optional[Union[List[discord.ui.Item], discord.ui.View]] = None,
        timeout: int = 180,
    ):
        self._title = title
        self._thumbnail = thumbnail
        self._main_image = main_image
        self._url = url
        self._author: Optional[AuthorEntry] = None
        self._footer: Optional[FooterEntry] = None
        self._field_entries: List[FieldEntry] = list(DataNormalizer.fields(fields))
        self._components = self._extract_components(components)
        self._description = description
        self._timeout = timeout if timeout >= 1 else 180

        super().__init__(timeout=self._timeout)
        self.container: Optional[ui.Container] = None
        self._rebuild()

    def _extract_components(
        self, components: Optional[Union[List[discord.ui.Item], discord.ui.View]]
    ) -> List[discord.ui.Item]:
        if not components:
            return []
        items = (
            components.children
            if isinstance(components, discord.ui.View)
            else components
        )
        return [item for item in items if isinstance(item, discord.ui.Item)]

    def _rebuild(self):
        self.clear_items()

        items: List[ui.Item] = []
        compiler = DescriptionCompiler()

        if norm_author := DataNormalizer.author(self._author):
            items.append(ui.TextDisplay(content=f"**{norm_author.name}**"))

        if norm_title := DataNormalizer.text(self._title):
            header = (
                f"## [{norm_title}]({self._url})" if self._url else f"## {norm_title}"
            )
            items.append(ui.TextDisplay(content=header))

        desc = DataNormalizer.text(self._description) or None
        items.extend(compiler.compile(desc if desc else ""))

        for field in self._field_entries:
            if field.name:
                items.append(ui.TextDisplay(content=f"**{field.name}**"))
            if field.value:
                items.append(ui.TextDisplay(content=field.value))

        if self._main_image:
            items.append(ui.MediaGallery(MediaGalleryItem(self._main_image)))

        if self._thumbnail:
            text_items = [i for i in items if isinstance(i, ui.TextDisplay)]
            if text_items:
                section = ui.Section(
                    *text_items[:3], accessory=ui.Thumbnail(self._thumbnail)
                )
                replaced = 0
                new_items = []
                for item in items:
                    if isinstance(item, ui.TextDisplay) and replaced < 3:
                        if replaced == 0:
                            new_items.append(section)
                        replaced += 1
                    else:
                        new_items.append(item)
                items = new_items

        if self._components:
            current_row = ui.ActionRow()
            for comp in self._components:
                try:
                    current_row.add_item(comp)
                except ValueError:
                    items.append(current_row)
                    current_row = ui.ActionRow()
                    current_row.add_item(comp)
            items.append(current_row)

        if self._footer and (f_text := DataNormalizer.text(self._footer.text)):
            if f_text.startswith(";;"):
                items.append(ui.Separator(spacing=discord.SeparatorSpacing.large))
                f_text = f_text[2:].lstrip()
            elif f_text.startswith(";"):
                items.append(ui.Separator(spacing=discord.SeparatorSpacing.small))
                f_text = f_text[1:].lstrip()
            items.append(ui.TextDisplay(content=f"-# {f_text}"))

        self.container = ui.Container(*items)
        self.add_item(self.container)

    def set_author(
        self, name: str, icon_url: Optional[str] = None, url: Optional[str] = None
    ):
        self._author = AuthorEntry(name=name, icon_url=icon_url, url=url)
        self._rebuild()

    def set_footer(self, text: str, icon_url: Optional[str] = None):
        self._footer = FooterEntry(text=text, icon_url=icon_url)
        self._rebuild()

    def add_field(self, name: str, value: str, inline: bool = False):
        self._field_entries.append(FieldEntry(name=name, value=value, inline=inline))
        self._rebuild()
