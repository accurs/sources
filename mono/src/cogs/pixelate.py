from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageOps, UnidentifiedImageError

from .ascii_art import (
    MAX_IMAGE_BYTES,
    MEDIA_SUFFIXES,
    _component_media_urls,
    _download_media_url,
    _prepare_source,
)
from src.services.media_runtime import bytes_digest, map_frames, run_media

MAX_PIXELATE_FRAMES = 48
MAX_PIXELATE_EXPORT_FRAMES = 500


@dataclass
class PixelateSettings:
    block_size: int = 12


def _pixelate_frame(
    source: Image.Image,
    block_size: int,
    *,
    max_dimension: int = 1600,
) -> Image.Image:
    frame = ImageOps.exif_transpose(source.convert("RGBA"))
    frame.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    small_size = (
        max(1, round(frame.width / block_size)),
        max(1, round(frame.height / block_size)),
    )
    small = frame.resize(small_size, Image.Resampling.BOX)
    return small.resize(frame.size, Image.Resampling.NEAREST)


def _make_pixelated(
    source_bytes: bytes,
    settings: PixelateSettings,
    fast_preview: bool = True,
) -> tuple[BytesIO, str, int]:
    with Image.open(BytesIO(source_bytes)) as source:
        frame_count = getattr(source, "n_frames", 1)
        is_animated = bool(getattr(source, "is_animated", False)) and frame_count > 1
        if not is_animated:
            frame = _pixelate_frame(source, settings.block_size)
            output = BytesIO()
            frame.save(output, "PNG", optimize=True)
            output.seek(0)
            return output, "png", 1

        source_durations: list[int] = []
        for frame_index in range(frame_count):
            source.seek(frame_index)
            source_durations.append(max(20, int(source.info.get("duration", 80))))
        total_duration = sum(source_durations)
        frame_limit = (
            MAX_PIXELATE_FRAMES if fast_preview else MAX_PIXELATE_EXPORT_FRAMES
        )
        sample_count = min(frame_count, frame_limit)
        frame_indices = [
            min(frame_count - 1, index * frame_count // sample_count)
            for index in range(sample_count)
        ]
        source_frames: list[Image.Image] = []
        frame_duration, remainder = divmod(total_duration, sample_count)
        durations = [
            frame_duration + (1 if index < remainder else 0)
            for index in range(sample_count)
        ]
        loop = int(source.info.get("loop", 0))
        for frame_index in frame_indices:
            source.seek(frame_index)
            source_frames.append(source.convert("RGBA").copy())

        max_dimension = 720 if fast_preview else 1600
        frames = map_frames(
            lambda frame: _pixelate_frame(
                frame,
                settings.block_size,
                max_dimension=max_dimension,
            ),
            source_frames,
        )

        palette_frames = [
            frame.quantize(
                colors=256,
                method=Image.Quantize.FASTOCTREE,
                dither=Image.Dither.NONE,
            )
            for frame in frames
        ]
        output = BytesIO()
        palette_frames[0].save(
            output,
            "GIF",
            save_all=True,
            append_images=palette_frames[1:],
            duration=durations,
            loop=loop,
            disposal=2,
            optimize=False,
        )
        output.seek(0)
        return output, "gif", len(palette_frames)


class PixelSizeModal(discord.ui.Modal, title="Pixel size"):
    block_size = discord.ui.TextInput(
        label="Block size (2–100)",
        placeholder="12",
        min_length=1,
        max_length=3,
    )

    def __init__(self, studio: PixelateStudioView) -> None:
        super().__init__()
        self.studio = studio
        self.block_size.default = str(studio.settings.block_size)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            block_size = int(self.block_size.value)
        except ValueError:
            await interaction.response.send_message(
                "Block size must be a whole number from 2 to 100.",
                ephemeral=True,
            )
            return
        if not 2 <= block_size <= 100:
            await interaction.response.send_message(
                "Block size must be from 2 to 100.",
                ephemeral=True,
            )
            return
        self.studio.settings.block_size = block_size
        await self.studio.update_preview(interaction)


class PixelateButton(discord.ui.Button):
    def __init__(
        self,
        studio: PixelateStudioView,
        action: str,
        *,
        label: str,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
    ) -> None:
        super().__init__(label=label, style=style)
        self.studio = studio
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.action == "size":
            await interaction.response.send_modal(PixelSizeModal(self.studio))
            return
        if self.action == "reset":
            self.studio.settings = PixelateSettings()
            await self.studio.update_preview(interaction)
            return
        if self.action == "save":
            await interaction.response.defer(thinking=True)
            try:
                output, extension, _ = await run_media(
                    _make_pixelated,
                    self.studio.source_bytes,
                    self.studio.settings,
                    False,
                )
            except (OSError, ValueError, UnidentifiedImageError) as error:
                await interaction.followup.send(
                    f"Could not export the pixelated media: {error}",
                    ephemeral=True,
                )
                return
            if output.getbuffer().nbytes > 25 * 1024 * 1024:
                await interaction.followup.send(
                    "The full export is larger than 25 MB.",
                    ephemeral=True,
                )
                return
            await interaction.followup.send(
                file=discord.File(
                    BytesIO(output.getvalue()),
                    filename=f"sorrowing.pixelated.{extension}",
                )
            )


class PixelateStudioView(discord.ui.LayoutView):
    def __init__(self, owner_id: int, source_bytes: bytes) -> None:
        super().__init__(timeout=5 * 60)
        self.owner_id = owner_id
        self.source_bytes = source_bytes
        self.settings = PixelateSettings()
        self.preview_data = b""
        self.extension = "png"
        self.rendered_frames = 1
        self.message: discord.InteractionMessage | None = None
        self.busy = asyncio.Lock()
        self.expired = False
        self.rebuild_layout()

    async def build(self) -> discord.File:
        cache_key = (
            "pixelate-preview",
            bytes_digest(self.source_bytes),
            self.settings.block_size,
        )
        output, self.extension, self.rendered_frames = await run_media(
            _make_pixelated,
            self.source_bytes,
            self.settings,
            True,
            cache_key=cache_key,
        )
        self.preview_data = output.getvalue()
        self.rebuild_layout()
        return self.output_file()

    def output_file(self) -> discord.File:
        return discord.File(
            BytesIO(self.preview_data),
            filename=f"sorrowing.pixelated.{self.extension}",
        )

    def rebuild_layout(self) -> None:
        self.clear_items()
        filename = f"sorrowing.pixelated.{self.extension}"
        animation_note = (
            f" · **{self.rendered_frames} frames**"
            if self.extension == "gif"
            else ""
        )
        controls = (
            PixelateButton(
                self,
                "size",
                label=f"Pixel size: {self.settings.block_size}",
                style=discord.ButtonStyle.primary,
            ),
            PixelateButton(
                self,
                "reset",
                label="Reset",
                style=discord.ButtonStyle.danger,
            ),
            PixelateButton(
                self,
                "save",
                label=f"Save {self.extension.upper()}",
                style=discord.ButtonStyle.success,
            ),
        )
        if self.expired:
            for button in controls:
                button.disabled = True
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Pixelate Studio\n"
                    "Choose the block size and watch the image update."
                ),
                discord.ui.Separator(
                    spacing=discord.SeparatorSpacing.small,
                ),
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(
                        f"attachment://{filename}",
                        description="Live pixelated preview",
                    )
                ),
                discord.ui.TextDisplay(
                    f"`Block size` **{self.settings.block_size}px**"
                    f"{animation_note}"
                ),
                discord.ui.ActionRow(*controls),
                discord.ui.TextDisplay(
                    "-# Only the creator can use these controls · "
                    "Studio closes after 5 minutes"
                ),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            "This Pixelate Studio belongs to someone else.",
            ephemeral=True,
        )
        return False

    async def update_preview(self, interaction: discord.Interaction) -> None:
        if self.busy.locked():
            await interaction.response.send_message(
                "The preview is already updating.",
                ephemeral=True,
            )
            return
        async with self.busy:
            await interaction.response.defer()
            file = await self.build()
            await interaction.edit_original_response(
                attachments=[file],
                view=self,
            )

    async def on_timeout(self) -> None:
        self.expired = True
        self.rebuild_layout()
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class Pixelate(commands.Cog):
    """Interactive image and GIF pixelation."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.pixelate_context_menu = app_commands.ContextMenu(
            name="Open Pixelate Studio",
            callback=self.open_pixelate_studio,
        )
        self.bot.tree.add_command(self.pixelate_context_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.pixelate_context_menu.name,
            type=self.pixelate_context_menu.type,
        )

    async def open_pixelate_studio(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ) -> None:
        attachment = next(
            (
                item
                for item in message.attachments
                if (
                    item.content_type is not None
                    and item.content_type.startswith(("image/", "video/"))
                )
                or Path(item.filename).suffix.lower() in MEDIA_SUFFIXES
            ),
            None,
        )
        media_urls = _component_media_urls(list(message.components))
        for embed in message.embeds:
            for candidate in (
                embed.video.url if embed.video else None,
                embed.image.url if embed.image else None,
                embed.thumbnail.url if embed.thumbnail else None,
                embed.url,
            ):
                if candidate and str(candidate) not in media_urls:
                    media_urls.append(str(candidate))

        if attachment is None and not media_urls:
            await interaction.response.send_message(
                "That message does not contain an image, GIF, or short video.",
                ephemeral=True,
            )
            return
        if attachment is not None and attachment.size > MAX_IMAGE_BYTES:
            await interaction.response.send_message(
                "That media file is too large. Please use one under 12 MB.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)
        try:
            if attachment is not None:
                data = await attachment.read()
                source_bytes = await _prepare_source(
                    data,
                    content_type=attachment.content_type or "",
                    filename_or_url=attachment.filename,
                )
            else:
                last_error: Exception | None = None
                source_bytes = b""
                for media_url in media_urls:
                    try:
                        data, content_type = await _download_media_url(media_url)
                        source_bytes = await _prepare_source(
                            data,
                            content_type=content_type,
                            filename_or_url=media_url,
                        )
                        break
                    except (ValueError, OSError, aiohttp.ClientError) as error:
                        last_error = error
                if not source_bytes:
                    raise ValueError(
                        str(last_error) if last_error else "I couldn't read that media."
                    )
            with Image.open(BytesIO(source_bytes)) as source:
                source.verify()
            view = PixelateStudioView(interaction.user.id, source_bytes)
            file = await view.build()
        except (
            discord.HTTPException,
            OSError,
            UnidentifiedImageError,
            ValueError,
            aiohttp.ClientError,
        ) as error:
            await interaction.edit_original_response(
                content=(str(error) or "I couldn't read that media.")[:1900]
            )
            return

        view.message = await interaction.edit_original_response(
            content=None,
            attachments=[file],
            view=view,
        )

    @app_commands.command(
        name="pixelate",
        description="Open an interactive image or GIF pixelation studio",
    )
    @app_commands.describe(
        image="Upload an image or GIF",
        image_url="Or paste a direct image, GIF, or video link",
    )
    async def pixelate(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment | None = None,
        image_url: str | None = None,
    ) -> None:
        if image is None and not image_url:
            await interaction.response.send_message(
                "Upload an image/GIF or provide a direct media link.",
                ephemeral=True,
            )
            return
        if image is not None and image_url:
            await interaction.response.send_message(
                "Use either an upload or a link, not both.",
                ephemeral=True,
            )
            return
        if image is not None:
            suffix = Path(image.filename).suffix.lower()
            if (
                not (
                    image.content_type is not None
                    and image.content_type.startswith(("image/", "video/"))
                )
                and suffix not in MEDIA_SUFFIXES
            ):
                await interaction.response.send_message(
                    "That upload does not look like an image, GIF, or video.",
                    ephemeral=True,
                )
                return
            if image.size > MAX_IMAGE_BYTES:
                await interaction.response.send_message(
                    "That media is too large. Please use one under 12 MB.",
                    ephemeral=True,
                )
                return

        await interaction.response.defer(thinking=True)
        try:
            if image is not None:
                source_data = await image.read()
                source_bytes = await _prepare_source(
                    source_data,
                    content_type=image.content_type or "",
                    filename_or_url=image.filename,
                )
            else:
                source_data, content_type = await _download_media_url(
                    image_url or ""
                )
                source_bytes = await _prepare_source(
                    source_data,
                    content_type=content_type,
                    filename_or_url=image_url or "",
                )
            with Image.open(BytesIO(source_bytes)) as source:
                source.verify()
        except (
            discord.HTTPException,
            OSError,
            UnidentifiedImageError,
            ValueError,
            aiohttp.ClientError,
        ) as error:
            await interaction.edit_original_response(content=str(error))
            return

        view = PixelateStudioView(interaction.user.id, source_bytes)
        file = await view.build()
        view.message = await interaction.edit_original_response(
            attachments=[file],
            view=view,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Pixelate(bot))
