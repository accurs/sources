from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import asyncpg
import discord
from discord import ui
from discord.ext import commands
from bot.managers.ui import embed


hexcolorre = re.compile(r"^#?([0-9A-Fa-f]{6})$")


def parse_color(value: str) -> Optional[int]:
    m = hexcolorre.match(value.strip())
    return int(m.group(1), 16) if m else None


def validate_url(value: str) -> Optional[str]:
    v = value.strip()
    try:
        parsed = urlparse(v)
        if parsed.scheme in ("http", "https") and parsed.hostname:
            return v
    except Exception:
        pass
    return None


@dataclass
class EmbedRecord:
    name: str
    title: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    thumbnail: Optional[str] = None
    image: Optional[str] = None
    authorname: Optional[str] = None
    authoricon: Optional[str] = None
    footertext: Optional[str] = None
    footericon: Optional[str] = None
    fields: list[dict] = field(default_factory=list)

    def to_discord_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=self.title,
            description=self.description,
            color=parse_color(self.color) if self.color else None,
        )
        if not any([embed.title, embed.description, self.fields, self.thumbnail, self.image]):
            embed.description = f"created an embed with the name **{self.name}**\n- you can now send this embed with `,send {'{embed:' + self.name + '}'}`\n- or edit it with `,embed edit {self.name}`\nif you encounter any issues, please contact [support](https://discord.gg/aerithbot)"
        if self.thumbnail:
            embed.set_thumbnail(url=self.thumbnail)
        if self.image:
            embed.set_image(url=self.image)
        if self.authorname:
            embed.set_author(name=self.authorname, **{"icon_url": self.authoricon} if self.authoricon else {})
        if self.footertext:
            embed.set_footer(text=self.footertext, **{"icon_url": self.footericon} if self.footericon else {})
        for f in self.fields:
            embed.add_field(name=f.get("name", ""), value=f.get("value", ""), inline=f.get("inline", True))
        
        return embed


class EmbedRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def exists(self, name: str) -> bool:
        return await self.pool.fetchrow("SELECT 1 FROM embed WHERE name = $1", name) is not None

    async def create_if_missing(self, name: str) -> None:
        await self.pool.execute(
            "INSERT INTO embed (name) VALUES ($1) ON CONFLICT (name) DO NOTHING",
            name,
        )

    async def load(self, name: str) -> Optional[EmbedRecord]:
        row = await self.pool.fetchrow("SELECT * FROM embed WHERE name = $1", name)
        if row is None:
            return None
        
        raw_fields = row["fields"]
        if raw_fields:
            fields_data = json.loads(raw_fields) if isinstance(raw_fields, str) else raw_fields
        else:
            fields_data = []

        return EmbedRecord(
            name=row["name"],
            title=row["title"],
            description=row["description"],
            color=row["color"],
            thumbnail=row["thumbnail"],
            image=row["image"],
            authorname=row["author_name"],
            authoricon=row["author_icon"],
            footertext=row["footer_text"],
            footericon=row["footer_icon"],
            fields=fields_data,
        )

    async def save(self, record: EmbedRecord) -> None:
        await self.pool.execute(
            """
            INSERT INTO embed (
                name, title, description, color, thumbnail, image,
                author_name, author_icon, footer_text, footer_icon, fields
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)
            ON CONFLICT (name) DO UPDATE SET
                title        = EXCLUDED.title,
                description  = EXCLUDED.description,
                color        = EXCLUDED.color,
                thumbnail    = EXCLUDED.thumbnail,
                image        = EXCLUDED.image,
                author_name  = EXCLUDED.author_name,
                author_icon  = EXCLUDED.author_icon,
                footer_text  = EXCLUDED.footer_text,
                footer_icon  = EXCLUDED.footer_icon,
                fields       = EXCLUDED.fields
            """,
            record.name,
            record.title,
            record.description,
            record.color,
            record.thumbnail,
            record.image,
            record.authorname,
            record.authoricon,
            record.footertext,
            record.footericon,
            json.dumps(record.fields),
        )


class BasicConfigModal(ui.Modal, title="edit basic config"):
    titleinput = ui.TextInput(label="title", style=discord.TextStyle.short, required=False, max_length=256)
    descriptioninput = ui.TextInput(label="description", style=discord.TextStyle.long, required=False, max_length=400)
    colorinput = ui.TextInput(label="hex color", style=discord.TextStyle.short, required=False, max_length=7, placeholder="#ffffff")

    def __init__(self, repo: EmbedRepository, record: EmbedRecord, previewmessage: discord.Message) -> None:
        super().__init__()
        self.repo = repo
        self.name = record.name
        self.previewmessage = previewmessage
        
        self.titleinput.default = record.title
        self.descriptioninput.default = record.description
        self.colorinput.default = record.color

    async def on_submit(self, interaction: discord.Interaction) -> None:
        record = await self.repo.load(self.name)
        if record is None:
            await interaction.response.send_message("embed not found.", ephemeral=True)
            return
        record.title = self.titleinput.value.strip() or None
        record.description = self.descriptioninput.value.strip() or None
        if raw := self.colorinput.value.strip():
            if parse_color(raw) is None:
                await interaction.response.send_message("invalid hex color.", ephemeral=True)
                return
            record.color = raw if raw.startswith("#") else f"#{raw}"
        else:
            record.color = None
        try:
            await self.repo.save(record)
        except Exception:
            await interaction.response.send_message("database error while saving.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            await self.previewmessage.edit(embed=record.to_discord_embed())
        except (discord.NotFound, discord.HTTPException):
            pass


class AuthorModal(ui.Modal, title="edit author"):
    authornameinput = ui.TextInput(label="author name", style=discord.TextStyle.short, required=False, max_length=256)
    authoriconinput = ui.TextInput(label="author icon url", style=discord.TextStyle.short, required=False)

    def __init__(self, repo: EmbedRepository, record: EmbedRecord, previewmessage: discord.Message) -> None:
        super().__init__()
        self.repo = repo
        self.name = record.name
        self.previewmessage = previewmessage
        
        self.authornameinput.default = record.authorname
        self.authoriconinput.default = record.authoricon

    async def on_submit(self, interaction: discord.Interaction) -> None:
        record = await self.repo.load(self.name)
        if record is None:
            await interaction.response.send_message("embed not found.", ephemeral=True)
            return
        record.authorname = self.authornameinput.value.strip() or None
        if raw := self.authoriconinput.value.strip():
            if validate_url(raw) is None:
                await interaction.response.send_message("invalid author icon url.", ephemeral=True)
                return
            record.authoricon = raw
        else:
            record.authoricon = None
        try:
            await self.repo.save(record)
        except Exception:
            await interaction.response.send_message("database error while saving.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            await self.previewmessage.edit(embed=record.to_discord_embed())
        except (discord.NotFound, discord.HTTPException):
            pass


class FooterModal(ui.Modal, title="edit footer"):
    footertextinput = ui.TextInput(label="footer text", style=discord.TextStyle.short, required=False, max_length=2048)
    footericoninput = ui.TextInput(label="footer icon url", style=discord.TextStyle.short, required=False)

    def __init__(self, repo: EmbedRepository, record: EmbedRecord, previewmessage: discord.Message) -> None:
        super().__init__()
        self.repo = repo
        self.name = record.name
        self.previewmessage = previewmessage

        self.footertextinput.default = record.footertext
        self.footericoninput.default = record.footericon

    async def on_submit(self, interaction: discord.Interaction) -> None:
        record = await self.repo.load(self.name)
        if record is None:
            await interaction.response.send_message("embed not found.", ephemeral=True)
            return
        record.footertext = self.footertextinput.value.strip() or None
        if raw := self.footericoninput.value.strip():
            if validate_url(raw) is None:
                await interaction.response.send_message("invalid footer icon url.", ephemeral=True)
                return
            record.footericon = raw
        else:
            record.footericon = None
        try:
            await self.repo.save(record)
        except Exception:
            await interaction.response.send_message("database error while saving.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            await self.previewmessage.edit(embed=record.to_discord_embed())
        except (discord.NotFound, discord.HTTPException):
            pass


class ImagesModal(ui.Modal, title="edit images"):
    thumbinput = ui.TextInput(label="thumbnail url", style=discord.TextStyle.short, required=False)
    imageinput = ui.TextInput(label="image url", style=discord.TextStyle.short, required=False)

    def __init__(self, repo: EmbedRepository, record: EmbedRecord, previewmessage: discord.Message) -> None:
        super().__init__()
        self.repo = repo
        self.name = record.name
        self.previewmessage = previewmessage
        
        self.thumbinput.default = record.thumbnail
        self.imageinput.default = record.image

    async def on_submit(self, interaction: discord.Interaction) -> None:
        record = await self.repo.load(self.name)
        if record is None:
            await interaction.response.send_message("embed not found.", ephemeral=True)
            return
        if raw := self.thumbinput.value.strip():
            if validate_url(raw) is None:
                await interaction.response.send_message("invalid thumbnail url.", ephemeral=True)
                return
            record.thumbnail = raw
        else:
            record.thumbnail = None
        if raw := self.imageinput.value.strip():
            if validate_url(raw) is None:
                await interaction.response.send_message("invalid image url.", ephemeral=True)
                return
            record.image = raw
        else:
            record.image = None
        try:
            await self.repo.save(record)
        except Exception:
            await interaction.response.send_message("database error while saving.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            await self.previewmessage.edit(embed=record.to_discord_embed())
        except (discord.NotFound, discord.HTTPException):
            pass


class AddFieldModal(ui.Modal, title="add a field"):
    name_input = ui.TextInput(
        label="name",
        style=discord.TextStyle.short,
        custom_id="35ca4f89c1314682852d1988509e5091",
        required=True,
        max_length=256,
    )
    value_input = ui.TextInput(
        label="value",
        style=discord.TextStyle.long,
        custom_id="f961a80a75514f70897e418384d64c8d",
        required=True,
        max_length=1024,
    )
    inline_select_label = ui.Label(
        text="inline",
        description="Choose whether the field is inline",
        component=ui.Select(
            custom_id="feca0659dfec4e99865ed7e8510a2ff2",
            options=[
                discord.SelectOption(
                    label="true",
                    value="bf1d8b0872dd4855bd438ced809c341d",
                    description="other fields with this property will be in the same line as this one",
                    default=True,
                ),
                discord.SelectOption(
                    label="false",
                    value="b3b581d8d9804215b8967b5de8795e39",
                    description="other fields will NOT appear in the same line as this field",
                ),
            ],
        ),
    )

    def __init__(self, repo: EmbedRepository, name: str, previewmessage: discord.Message) -> None:
        super().__init__()
        self.repo = repo
        self.name = name
        self.previewmessage = previewmessage

    async def on_submit(self, interaction: discord.Interaction) -> None:
        values = self.inline_select_label.component.values # type: ignore
        inline = (not values) or values[0] == "bf1d8b0872dd4855bd438ced809c341d"
        record = await self.repo.load(self.name)
        if record is None:
            await interaction.response.send_message("embed not found.", ephemeral=True)
            return
        record.fields.append({
            "name": self.name_input.value.strip(),
            "value": self.value_input.value.strip(),
            "inline": inline,
        })
        try:
            await self.repo.save(record)
        except Exception:
            await interaction.response.send_message("database error while saving.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            await self.previewmessage.edit(embed=record.to_discord_embed())
        except (discord.NotFound, discord.HTTPException):
            pass


class EditFieldModal(ui.Modal, title="edit field"):
    name_input = ui.TextInput(
        label="name",
        style=discord.TextStyle.short,
        required=True,
        max_length=256,
    )
    value_input = ui.TextInput(
        label="value",
        style=discord.TextStyle.long,
        required=True,
        max_length=1024,
    )
    inline_select_label = ui.Label(
        text="inline",
        description="Choose whether the field is inline",
        component=ui.Select(
            custom_id="edit_field_inline_select",
            options=[
                discord.SelectOption(
                    label="true",
                    value="inline_true",
                    description="other fields with this property will be in the same line as this one",
                ),
                discord.SelectOption(
                    label="false",
                    value="inline_false",
                    description="other fields will NOT appear in the same line as this field",
                ),
            ],
        ),
    )

    def __init__(
        self,
        repo: EmbedRepository,
        embed_name: str,
        field_index: int,
        existing_field: dict,
        previewmessage: discord.Message,
    ) -> None:
        super().__init__()
        self.repo = repo
        self.embed_name = embed_name
        self.field_index = field_index
        self.previewmessage = previewmessage

        self.name_input.default = existing_field.get("name", "")
        self.value_input.default = existing_field.get("value", "")

        # pre-select the current inline value in the select menu
        currently_inline = existing_field.get("inline", True)
        for opt in self.inline_select_label.component.options: # type: ignore
            opt.default = (opt.value == "inline_true") if currently_inline else (opt.value == "inline_false")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        record = await self.repo.load(self.embed_name)
        if record is None:
            await interaction.response.send_message("embed not found.", ephemeral=True)
            return
        if self.field_index >= len(record.fields):
            await interaction.response.send_message("field no longer exists.", ephemeral=True)
            return

        values = self.inline_select_label.component.values # type: ignore
        inline = (not values) or values[0] == "inline_true"

        record.fields[self.field_index] = {
            "name": self.name_input.value.strip(),
            "value": self.value_input.value.strip(),
            "inline": inline,
        }
        try:
            await self.repo.save(record)
        except Exception:
            await interaction.response.send_message("database error while saving.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            await self.previewmessage.edit(embed=record.to_discord_embed())
        except (discord.NotFound, discord.HTTPException):
            pass


class EditComponentsModal(ui.Modal, title="edit components"):
    def __init__(
        self,
        repo: EmbedRepository,
        record: EmbedRecord,
        previewmessage: discord.Message,
    ) -> None:
        super().__init__()
        self.repo = repo
        self.embed_name = record.name
        self.previewmessage = previewmessage

        # build field options — truncate label/description to Discord limits
        field_options = [
            discord.SelectOption(
                label=f"field {i + 1}: {f.get('name', '') or '(unnamed)'}"[:100],
                value=str(i),
                description=f.get("value", "")[:100] or None,
            )
            for i, f in enumerate(record.fields)
        ] or [discord.SelectOption(label="no fields", value="none", default=True)]

        self.field_select_label = ui.Label(
            text="field",
            description="Choose a field to modify",
            component=ui.Select(
                custom_id="edit_components_field_select",
                placeholder="select a field…",
                options=field_options,
                disabled=not record.fields,
            ),
        )
        self.action_select_label = ui.Label(
            text="action",
            description="Choose what to do with the selected field",
            component=ui.Select(
                custom_id="edit_components_action_select",
                placeholder="select an action…",
                options=[
                    discord.SelectOption(
                        label="edit",
                        value="edit",
                        description="open a modal to edit the field's name, value, and inline setting",
                        default=True,
                    ),
                    discord.SelectOption(
                        label="delete",
                        value="delete",
                        description="permanently remove the field from this embed",
                    ),
                ],
            ),
        )
        self.add_item(self.field_select_label)
        self.add_item(self.action_select_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        field_values = self.field_select_label.component.values # type: ignore
        action_values = self.action_select_label.component.values # type: ignore

        if not field_values or field_values[0] == "none":
            await interaction.response.send_message("no fields to edit.", ephemeral=True)
            return

        field_index = int(field_values[0])
        action = action_values[0] if action_values else "edit"

        record = await self.repo.load(self.embed_name)
        if record is None:
            await interaction.response.send_message("embed not found.", ephemeral=True)
            return
        if field_index >= len(record.fields):
            await interaction.response.send_message("that field no longer exists.", ephemeral=True)
            return

        if action == "delete":
            record.fields.pop(field_index)
            try:
                await self.repo.save(record)
            except Exception:
                await interaction.response.send_message("database error while saving.", ephemeral=True)
                return
            await interaction.response.defer()
            try:
                await self.previewmessage.edit(embed=record.to_discord_embed())
            except (discord.NotFound, discord.HTTPException):
                pass

        else:  # edit
            existing_field = record.fields[field_index]
            await interaction.response.send_modal(
                EditFieldModal(self.repo, self.embed_name, field_index, existing_field, self.previewmessage)
            )


class OverwriteConfirmView(ui.View):
    """Sent when `create=True` but an embed with that name already exists.
    The single button lets the original author open the builder anyway,
    without creating a new record (equivalent to send(ctx, create=False))."""

    def __init__(self, builder: "EmbedBuilderView", ctx: commands.Context) -> None:
        super().__init__(timeout=60)
        self.builder = builder
        self.ctx = ctx

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.builder.authorid:
            await interaction.response.send_message("only the command author can use this.", ephemeral=True)
            return False
        return True

    @ui.button(label="edit existing embed", style=discord.ButtonStyle.secondary)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer()
        await interaction.message.delete() # type: ignore
        await self.builder.send(self.ctx, create=False)
        self.stop()

    async def on_timeout(self) -> None:
        try:
            # disable the button once the window closes
            for item in self.children:
                item.disabled = True  # type: ignore
        except Exception:
            pass


class EmbedBuilderView(ui.View):
    def __init__(self, pool: asyncpg.Pool, name: str, authorid: int) -> None:
        super().__init__(timeout=None)
        self.repo = EmbedRepository(pool)
        self.name = name
        self.authorid = authorid
        self.previewmessage: discord.Message

    async def send(self, ctx: commands.Context, *, create: bool = True) -> Optional[discord.Message]:
        if create and await self.repo.exists(self.name):
            warning = embed.Embed(  # type: ignore
                description=f"an embed named **{self.name}** already exists. press the button below to open it in the editor instead.",
                components=OverwriteConfirmView(self, ctx),
            )
            await ctx.send(view=warning)
            return None

        if create:
            await self.repo.create_if_missing(self.name)
        record = await self.repo.load(self.name)
        if record is None:
            await ctx.send("embed not found.")
            return None
        self.previewmessage = await ctx.send(embed=record.to_discord_embed(), view=self)
        return self.previewmessage

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.authorid:
            await interaction.response.send_message("only the command author can use this.", ephemeral=True)
            return False
        return True

    @ui.button(label="edit basic config", style=discord.ButtonStyle.secondary, custom_id="embed_builder:edit_basic")
    async def edit_basic(self, interaction: discord.Interaction, button: ui.Button) -> None:
        record = await self.repo.load(self.name)
        if record is None:
            await interaction.response.send_message("embed not found.", ephemeral=True)
            return
        await interaction.response.send_modal(BasicConfigModal(self.repo, record, self.previewmessage))

    @ui.button(label="edit author", style=discord.ButtonStyle.secondary, custom_id="embed_builder:edit_author")
    async def edit_author(self, interaction: discord.Interaction, button: ui.Button) -> None:
        record = await self.repo.load(self.name)
        if record is None:
            await interaction.response.send_message("embed not found.", ephemeral=True)
            return
        await interaction.response.send_modal(AuthorModal(self.repo, record, self.previewmessage))

    @ui.button(label="edit footer", style=discord.ButtonStyle.secondary, custom_id="embed_builder:edit_footer")
    async def edit_footer(self, interaction: discord.Interaction, button: ui.Button) -> None:
        record = await self.repo.load(self.name)
        if record is None:
            await interaction.response.send_message("embed not found.", ephemeral=True)
            return
        await interaction.response.send_modal(FooterModal(self.repo, record, self.previewmessage))

    @ui.button(label="edit images", style=discord.ButtonStyle.secondary, custom_id="embed_builder:edit_images")
    async def edit_images(self, interaction: discord.Interaction, button: ui.Button) -> None:
        record = await self.repo.load(self.name)
        if record is None:
            await interaction.response.send_message("embed not found.", ephemeral=True)
            return
        await interaction.response.send_modal(ImagesModal(self.repo, record, self.previewmessage))

    @ui.button(label="add a field", style=discord.ButtonStyle.secondary, custom_id="embed_builder:add_field")
    async def add_field(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.send_modal(AddFieldModal(self.repo, self.name, self.previewmessage))

    @ui.button(label="edit components", style=discord.ButtonStyle.secondary, custom_id="embed_builder:edit_components")
    async def edit_components(self, interaction: discord.Interaction, button: ui.Button) -> None:
        record = await self.repo.load(self.name)
        if record is None:
            await interaction.response.send_message("embed not found.", ephemeral=True)
            return
        if not record.fields:
            await interaction.response.send_message("this embed has no fields to edit.", ephemeral=True)
            return
        await interaction.response.send_modal(EditComponentsModal(self.repo, record, self.previewmessage))