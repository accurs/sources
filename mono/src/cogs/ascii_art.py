from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse

import aiohttp
import discord
import imageio_ffmpeg
from discord import app_commands
from discord.ext import commands
from PIL import (
    Image,
    ImageChops,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageFont,
    ImageOps,
    UnidentifiedImageError,
)
from src.services.media_runtime import FFMPEG_THREADS, bytes_digest, run_media

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov"}
MEDIA_SUFFIXES = IMAGE_SUFFIXES | VIDEO_SUFFIXES
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_REDIRECTS = 3
MAX_GIF_PREVIEW_FRAMES = 16
MAX_GIF_EXPORT_FRAMES = 48
MAX_GIF_RENDERED_COLUMNS = 240
MAX_LIVE_RENDERED_COLUMNS = 640
BACKGROUND_ALPHA_CUTOFF = 128
GRADIENTS = (
    ("Classic", "@%#*+=-:. "),
    ("Blocks", "█▓▒░ "),
    (
        "Detailed",
        "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. ",
    ),
    ("Minimal", "#x+:. "),
)
COLOR_MODES = (
    ("Soft White", (232, 234, 238)),
    ("Terminal Green", (104, 255, 144)),
    ("Amber", (255, 190, 82)),
    ("Ice Blue", (105, 205, 255)),
    ("Pink", (255, 125, 205)),
    ("Original Colors", None),
)


def _component_media_urls(components: list[object]) -> list[str]:
    urls: list[str] = []

    def add_media(media: object | None) -> None:
        url = getattr(media, "url", None)
        if url:
            value = str(url)
            if value not in urls:
                urls.append(value)

    def walk(component: object) -> None:
        add_media(getattr(component, "media", None))
        for item in getattr(component, "items", ()) or ():
            add_media(getattr(item, "media", None))
        accessory = getattr(component, "accessory", None)
        if accessory is not None:
            walk(accessory)
        for child in getattr(component, "children", ()) or ():
            walk(child)

    for component in components:
        walk(component)
    return urls


async def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Use a complete HTTP or HTTPS image link.")
    if parsed.username or parsed.password:
        raise ValueError("Image links cannot contain login information.")

    try:
        addresses = await run_media(
            socket.getaddrinfo,
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as error:
        raise ValueError("I couldn't find that image host.") from error

    if not addresses or any(
        not ipaddress.ip_address(address[4][0]).is_global for address in addresses
    ):
        raise ValueError("That image host is not publicly accessible.")


async def _download_media_url(url: str) -> tuple[bytes, str]:
    current_url = url.strip()
    timeout = aiohttp.ClientTimeout(total=15)
    headers = {"User-Agent": "Discord ASCII Studio/1.0"}

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        for redirect_count in range(MAX_REDIRECTS + 1):
            await _validate_public_url(current_url)
            async with session.get(current_url, allow_redirects=False) as response:
                if 300 <= response.status < 400:
                    location = response.headers.get("Location")
                    if not location or redirect_count == MAX_REDIRECTS:
                        raise ValueError("That image link redirects too many times.")
                    current_url = urljoin(current_url, location)
                    continue
                if response.status != 200:
                    parsed_url = urlparse(current_url)
                    is_discord_attachment = parsed_url.hostname in {
                        "cdn.discordapp.com",
                        "media.discordapp.net",
                    } and parsed_url.path.startswith("/attachments/")
                    if response.status == 404 and is_discord_attachment:
                        raise ValueError(
                            "That Discord attachment link has expired, was "
                            "deleted, or is missing its signed query parameters. "
                            "Upload the file directly or use **Apps → Open ASCII "
                            "Studio** on the original message."
                        )
                    raise ValueError(
                        f"The image server returned HTTP {response.status}."
                    )
                content_type = response.headers.get("Content-Type", "")
                if not content_type.lower().startswith(("image/", "video/")):
                    raise ValueError(
                        "That link does not point directly to an image or video."
                    )
                content_length = response.content_length
                if content_length is not None and content_length > MAX_IMAGE_BYTES:
                    raise ValueError("That image is too large. The limit is 12 MB.")

                data = bytearray()
                async for chunk in response.content.iter_chunked(64 * 1024):
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE_BYTES:
                        raise ValueError("That image is too large. The limit is 12 MB.")
                return bytes(data), content_type

    raise ValueError("I couldn't download that image or video.")


def _video_to_gif(video_bytes: bytes, suffix: str = ".mp4") -> bytes:
    input_path: Path | None = None
    output_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=suffix if suffix in VIDEO_SUFFIXES else ".mp4",
            delete=False,
        ) as input_file:
            input_file.write(video_bytes)
            input_path = Path(input_file.name)
        with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as output_file:
            output_path = Path(output_file.name)

        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        result = subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-threads",
                str(FFMPEG_THREADS),
                "-y",
                "-i",
                str(input_path),
                "-t",
                "6",
                "-an",
                "-vf",
                "scale=480:-2:force_original_aspect_ratio=decrease,fps=8",
                str(output_path),
            ],
            capture_output=True,
            timeout=20,
            creationflags=creation_flags,
            check=False,
        )
        if result.returncode != 0 or not output_path.exists():
            raise ValueError("I couldn't decode that video.")
        return output_path.read_bytes()
    except subprocess.TimeoutExpired as error:
        raise ValueError("That video took too long to decode.") from error
    finally:
        if input_path is not None:
            input_path.unlink(missing_ok=True)
        if output_path is not None:
            output_path.unlink(missing_ok=True)


async def _prepare_source(
    data: bytes,
    *,
    content_type: str = "",
    filename_or_url: str = "",
) -> bytes:
    suffix = Path(urlparse(filename_or_url).path).suffix.lower()
    is_video = content_type.lower().startswith("video/") or suffix in VIDEO_SUFFIXES
    if is_video:
        return await run_media(_video_to_gif, data, suffix)
    return data


@dataclass
class AsciiSettings:
    width: int = 72
    brightness: int = 100
    contrast: int = 110
    sharpness: int = 100
    gradient_index: int = 0
    inverted: bool = False
    threshold_enabled: bool = False
    threshold: int = 128
    edge_enabled: bool = True
    edge_strength: int = 1
    space_density: int = 0
    gif_fps: int = 4
    auto_enhance: bool = False
    remove_background: bool = False
    color_index: int = 0


@lru_cache(maxsize=16)
def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/cour.ttf",
        "DejaVuSansMono.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _font_cell_size(
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> tuple[int, int]:
    left, _, right, bottom = font.getbbox("M")
    return max(1, right - left), max(1, bottom + 3)


def _render_ascii_frame(
    source: Image.Image,
    settings: AsciiSettings,
    *,
    width: int | None = None,
    max_preview_dimension: int = 8192,
    crop_visible: bool = True,
) -> tuple[str, Image.Image]:
    rgba_image = ImageOps.exif_transpose(source.convert("RGBA"))
    alpha_image = rgba_image.getchannel("A")
    source_has_transparency = alpha_image.getextrema()[0] < 255
    image = rgba_image.convert("RGB")
    image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    alpha_image = alpha_image.resize(image.size, Image.Resampling.LANCZOS)
    if settings.auto_enhance:
        image = ImageOps.autocontrast(image, cutoff=1)
    image = ImageEnhance.Brightness(image).enhance(settings.brightness / 100)
    image = ImageEnhance.Contrast(image).enhance(settings.contrast / 100)
    image = ImageEnhance.Sharpness(image).enhance(settings.sharpness / 100)
    color_image = image.copy()
    image = ImageOps.grayscale(color_image)
    if settings.edge_enabled:
        image = image.filter(ImageFilter.FIND_EDGES)
        image = ImageEnhance.Contrast(image).enhance(settings.edge_strength)
    if settings.threshold_enabled:
        image = image.point(lambda value: 255 if value >= settings.threshold else 0)
    if settings.inverted:
        image = ImageOps.invert(image)
        color_image = ImageOps.invert(color_image)

    render_width = width or settings.width
    aspect = image.height / max(1, image.width)
    height = max(1, round(render_width * aspect * 0.5))
    image = image.resize((render_width, height), Image.Resampling.LANCZOS)
    color_image = color_image.resize(
        (render_width, height),
        Image.Resampling.LANCZOS,
    )
    alpha_image = alpha_image.resize(
        (render_width, height),
        Image.Resampling.LANCZOS,
    )
    foreground_pixels: list[bool] | None = None
    if settings.remove_background:
        alpha_minimum, _ = alpha_image.getextrema()
        if source_has_transparency and alpha_minimum < 255:
            clean_alpha = alpha_image.point(
                lambda value: 255 if value >= BACKGROUND_ALPHA_CUTOFF else 0
            )
            foreground_pixels = [
                value > 0 for value in clean_alpha.getdata()
            ]
        else:
            background_map = color_image.copy()
            sentinel = (255, 0, 255)
            for corner in (
                (0, 0),
                (background_map.width - 1, 0),
                (0, background_map.height - 1),
                (background_map.width - 1, background_map.height - 1),
            ):
                ImageDraw.floodfill(
                    background_map,
                    corner,
                    sentinel,
                    thresh=45,
                )
            grayscale_pixels = list(image.getdata())
            background_pixels = list(background_map.getdata())
            foreground_pixels = [
                background_pixel != sentinel
                for background_pixel in background_pixels
            ]
            image.putdata(
                [
                    255 if background_pixel == sentinel else grayscale_pixel
                    for grayscale_pixel, background_pixel in zip(
                        grayscale_pixels,
                        background_pixels,
                        strict=True,
                    )
                ]
            )

    gradient = GRADIENTS[settings.gradient_index][1]
    pixels = list(image.getdata())
    character_spacing = " " * settings.space_density
    ascii_rows: list[str] = []
    for row in range(height):
        characters: list[str] = []
        row_start = row * render_width
        for column, value in enumerate(
            pixels[row_start : row_start + render_width]
        ):
            pixel_index = row_start + column
            if (
                foreground_pixels is not None
                and not foreground_pixels[pixel_index]
            ):
                characters.append(" ")
                continue
            gradient_index = min(
                len(gradient) - 1,
                value * len(gradient) // 256,
            )
            character = gradient[gradient_index]
            if (
                character == " "
                and COLOR_MODES[settings.color_index][1] is None
            ):
                character = "."
            characters.append(character)
        ascii_rows.append(character_spacing.join(characters).rstrip())
    ascii_text = "\n".join(ascii_rows)

    padding = 28
    rendered_columns = render_width + (render_width - 1) * settings.space_density
    font = _font(16)
    cell_width = 1
    line_height = 1
    for font_size in range(16, 5, -1):
        candidate = _font(font_size)
        candidate_cell_width, candidate_line_height = _font_cell_size(candidate)
        candidate_width = rendered_columns * candidate_cell_width + padding * 2
        candidate_height = height * candidate_line_height + padding * 2
        font = candidate
        cell_width = candidate_cell_width
        line_height = candidate_line_height
        if (
            candidate_width <= max_preview_dimension
            and candidate_height <= max_preview_dimension
        ):
            break

    canvas_width = min(
        max_preview_dimension,
        rendered_columns * cell_width + padding * 2,
    )
    canvas_height = min(
        max_preview_dimension,
        height * line_height + padding * 2,
    )
    canvas = Image.new("RGB", (canvas_width, canvas_height), (12, 13, 16))

    selected_color = COLOR_MODES[settings.color_index][1]
    if selected_color is not None:
        draw = ImageDraw.Draw(canvas)
        draw.multiline_text(
            (padding, padding),
            ascii_text,
            font=font,
            fill=selected_color,
            spacing=3,
        )
    else:
        mask = Image.new("L", canvas.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.multiline_text(
            (padding, padding),
            ascii_text,
            font=font,
            fill=255,
            spacing=3,
        )
        expanded_colors = Image.new(
            "RGB",
            (rendered_columns, height),
            (12, 13, 16),
        )
        spacing_step = settings.space_density + 1
        for column in range(render_width):
            color_column = color_image.crop((column, 0, column + 1, height))
            expanded_colors.paste(
                color_column,
                (column * spacing_step, 0),
            )
        color_layer = expanded_colors.resize(
            (
                rendered_columns * cell_width,
                height * line_height,
            ),
            Image.Resampling.NEAREST,
        )
        canvas.paste(
            color_layer,
            (padding, padding),
            mask.crop(
                (
                    padding,
                    padding,
                    padding + color_layer.width,
                    padding + color_layer.height,
                )
            ),
        )
    if crop_visible:
        background = Image.new("RGB", canvas.size, (12, 13, 16))
        content_box = ImageChops.difference(canvas, background).getbbox()
        if content_box is not None:
            margin = 12
            left = max(0, content_box[0] - margin)
            top = max(0, content_box[1] - margin)
            right = min(canvas.width, content_box[2] + margin)
            bottom = min(canvas.height, content_box[3] + margin)
            canvas = canvas.crop((left, top, right, bottom))
    return ascii_text, canvas


def _make_ascii(
    source_bytes: bytes,
    settings: AsciiSettings,
    fast_preview: bool = False,
) -> tuple[str, BytesIO, str, int]:
    with Image.open(BytesIO(source_bytes)) as source:
        frame_count = getattr(source, "n_frames", 1)
        is_animated = bool(getattr(source, "is_animated", False)) and frame_count > 1
        if not is_animated:
            source.seek(0)
            preview_width = (
                min(
                    settings.width,
                    max(
                        24,
                        MAX_LIVE_RENDERED_COLUMNS // (settings.space_density + 1),
                    ),
                )
                if fast_preview
                else None
            )
            ascii_text, canvas = _render_ascii_frame(
                source,
                settings,
                width=preview_width,
                max_preview_dimension=4096 if fast_preview else 8192,
            )
            output = BytesIO()
            optimized_canvas = canvas.quantize(
                colors=256,
                method=Image.Quantize.FASTOCTREE,
                dither=Image.Dither.NONE,
            )
            optimized_canvas.save(output, "PNG", optimize=True)
            output.seek(0)
            return ascii_text, output, "png", 1

        source_durations: list[int] = []
        for frame_index in range(frame_count):
            source.seek(frame_index)
            source_durations.append(max(20, int(source.info.get("duration", 80))))
        total_duration = max(20, sum(source_durations))
        max_frames = MAX_GIF_PREVIEW_FRAMES if fast_preview else MAX_GIF_EXPORT_FRAMES
        desired_frames = max(
            1,
            round(total_duration * settings.gif_fps / 1000),
        )
        sample_count = min(max_frames, desired_frames)
        sample_interval = total_duration / sample_count
        frame_indices: list[int] = []
        source_index = 0
        source_end = source_durations[0]
        for sample_index in range(sample_count):
            sample_time = sample_index * sample_interval
            while source_index < frame_count - 1 and sample_time >= source_end:
                source_index += 1
                source_end += source_durations[source_index]
            frame_indices.append(source_index)
        animation_width = min(
            settings.width,
            max(
                24,
                MAX_GIF_RENDERED_COLUMNS // (settings.space_density + 1),
            ),
        )
        rendered_frames: list[Image.Image] = []
        durations = [round(sample_interval)] * sample_count
        durations[-1] += total_duration - sum(durations)
        ascii_text = ""
        loop = int(source.info.get("loop", 0))
        for frame_index in frame_indices:
            source.seek(frame_index)
            frame_text, canvas = _render_ascii_frame(
                source,
                settings,
                width=animation_width,
                max_preview_dimension=2048,
                crop_visible=False,
            )
            if not ascii_text:
                ascii_text = frame_text
            rendered_frames.append(canvas)
        union_box: tuple[int, int, int, int] | None = None
        background = Image.new("RGB", rendered_frames[0].size, (12, 13, 16))
        for frame in rendered_frames:
            frame_box = ImageChops.difference(frame, background).getbbox()
            if frame_box is None:
                continue
            if union_box is None:
                union_box = frame_box
            else:
                union_box = (
                    min(union_box[0], frame_box[0]),
                    min(union_box[1], frame_box[1]),
                    max(union_box[2], frame_box[2]),
                    max(union_box[3], frame_box[3]),
                )
        if union_box is not None:
            margin = 12
            union_box = (
                max(0, union_box[0] - margin),
                max(0, union_box[1] - margin),
                min(rendered_frames[0].width, union_box[2] + margin),
                min(rendered_frames[0].height, union_box[3] + margin),
            )
            rendered_frames = [frame.crop(union_box) for frame in rendered_frames]
        palette_colors = 64 if COLOR_MODES[settings.color_index][1] is None else 8
        palette_frames = [
            frame.quantize(
                colors=palette_colors,
                method=Image.Quantize.FASTOCTREE,
                dither=Image.Dither.NONE,
            )
            for frame in rendered_frames
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
        return ascii_text, output, "gif", len(rendered_frames)


class ImageSettingsModal(discord.ui.Modal, title="Image settings"):
    width = discord.ui.TextInput(
        label="Characters / detail (24–1000)",
        placeholder="72",
        max_length=4,
    )
    brightness = discord.ui.TextInput(
        label="Brightness percent (20–250)",
        placeholder="100",
        max_length=3,
    )
    contrast = discord.ui.TextInput(
        label="Contrast percent (20–250)",
        placeholder="110",
        max_length=3,
    )
    sharpness = discord.ui.TextInput(
        label="Sharpness percent (0–300)",
        placeholder="100",
        max_length=3,
    )

    def __init__(self, studio: AsciiStudioView) -> None:
        super().__init__()
        self.studio = studio
        self.width.default = str(studio.settings.width)
        self.brightness.default = str(studio.settings.brightness)
        self.contrast.default = str(studio.settings.contrast)
        self.sharpness.default = str(studio.settings.sharpness)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            width = int(self.width.value)
            brightness = int(self.brightness.value)
            contrast = int(self.contrast.value)
            sharpness = int(self.sharpness.value)
        except ValueError:
            await interaction.response.send_message(
                "Use whole numbers only.",
                ephemeral=True,
            )
            return

        ranges = (
            ("Characters / detail", width, 24, 1000),
            ("Brightness", brightness, 20, 250),
            ("Contrast", contrast, 20, 250),
            ("Sharpness", sharpness, 0, 300),
        )
        invalid = next(
            (
                f"{name} must be between {minimum} and {maximum}."
                for name, value, minimum, maximum in ranges
                if not minimum <= value <= maximum
            ),
            None,
        )
        if invalid is not None:
            await interaction.response.send_message(invalid, ephemeral=True)
            return

        self.studio.settings.width = width
        self.studio.settings.brightness = brightness
        self.studio.settings.contrast = contrast
        self.studio.settings.sharpness = sharpness
        await self.studio._update(interaction)


class EffectSettingsModal(discord.ui.Modal, title="Effect settings"):
    threshold = discord.ui.TextInput(
        label="Threshold level (0–255)",
        placeholder="128",
        max_length=3,
    )
    edge_strength = discord.ui.TextInput(
        label="Edge strength (1–5)",
        placeholder="1",
        max_length=1,
    )
    space_density = discord.ui.TextInput(
        label="Extra spaces (0–4)",
        placeholder="0",
        max_length=1,
    )
    gif_fps = discord.ui.TextInput(
        label="GIF frames per second (1–8)",
        placeholder="4",
        max_length=1,
    )

    def __init__(self, studio: AsciiStudioView) -> None:
        super().__init__()
        self.studio = studio
        self.threshold.default = str(studio.settings.threshold)
        self.edge_strength.default = str(studio.settings.edge_strength)
        self.space_density.default = str(studio.settings.space_density)
        self.gif_fps.default = str(studio.settings.gif_fps)
        if not studio.is_animated:
            self.remove_item(self.gif_fps)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            threshold = int(self.threshold.value)
            edge_strength = int(self.edge_strength.value)
            space_density = int(self.space_density.value)
            gif_fps = (
                int(self.gif_fps.value)
                if self.studio.is_animated
                else self.studio.settings.gif_fps
            )
        except ValueError:
            await interaction.response.send_message(
                "Use whole numbers only.",
                ephemeral=True,
            )
            return

        if not 0 <= threshold <= 255:
            await interaction.response.send_message(
                "Threshold must be between 0 and 255.",
                ephemeral=True,
            )
            return
        if not 1 <= edge_strength <= 5:
            await interaction.response.send_message(
                "Edge strength must be between 1 and 5.",
                ephemeral=True,
            )
            return
        if not 0 <= space_density <= 4:
            await interaction.response.send_message(
                "Extra spaces must be between 0 and 4.",
                ephemeral=True,
            )
            return
        if self.studio.is_animated and not 1 <= gif_fps <= 8:
            await interaction.response.send_message(
                "GIF FPS must be between 1 and 8.",
                ephemeral=True,
            )
            return

        self.studio.settings.threshold = threshold
        self.studio.settings.edge_strength = edge_strength
        self.studio.settings.space_density = space_density
        self.studio.settings.gif_fps = gif_fps
        await self.studio._update(interaction)


class StudioSelect(discord.ui.Select):
    def __init__(self, studio: AsciiStudioView, kind: str) -> None:
        self.studio = studio
        self.kind = kind
        choices = GRADIENTS if kind == "gradient" else COLOR_MODES
        selected_index = (
            studio.settings.gradient_index
            if kind == "gradient"
            else studio.settings.color_index
        )
        super().__init__(
            placeholder=("ASCII gradient" if kind == "gradient" else "Preview color"),
            options=[
                discord.SelectOption(
                    label=name,
                    value=str(index),
                    default=index == selected_index,
                )
                for index, (name, _) in enumerate(choices)
            ],
            disabled=studio.expired,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected_index = int(self.values[0])
        if self.kind == "gradient":
            self.studio.settings.gradient_index = selected_index
        else:
            self.studio.settings.color_index = selected_index
        await self.studio._update(interaction)


class StudioButton(discord.ui.Button):
    def __init__(
        self,
        studio: AsciiStudioView,
        action: str,
        *,
        label: str,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
        emoji: str | None = None,
    ) -> None:
        self.studio = studio
        self.action = action
        super().__init__(
            label=label,
            style=style,
            emoji=emoji,
            disabled=studio.expired,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.action == "image_values":
            await interaction.response.send_modal(ImageSettingsModal(self.studio))
            return
        if self.action == "effect_values":
            await interaction.response.send_modal(EffectSettingsModal(self.studio))
            return
        if self.action == "download_text":
            if self.studio.preview_extension == "gif":
                await interaction.response.send_message(
                    "Animated GIFs cannot be exported as TXT because text "
                    "files are static and cannot preserve animation. Use "
                    "**Save GIF** instead.",
                    ephemeral=True,
                )
                return
            is_ephemeral = bool(
                interaction.message is not None
                and interaction.message.flags.ephemeral
            )
            await interaction.response.defer(
                thinking=True,
                ephemeral=is_ephemeral,
            )
            text, _, _, _ = await run_media(
                _make_ascii,
                self.studio.source_bytes,
                self.studio.settings,
                False,
            )
            data = BytesIO(text.encode("utf-8"))
            await interaction.followup.send(
                file=discord.File(data, filename="sorrowing.ascii.txt"),
                ephemeral=is_ephemeral,
            )
            return
        if self.action == "download_preview":
            is_ephemeral = bool(
                interaction.message is not None
                and interaction.message.flags.ephemeral
            )
            await interaction.response.defer(
                thinking=True,
                ephemeral=is_ephemeral,
            )
            _, preview, extension, _ = await run_media(
                _make_ascii,
                self.studio.source_bytes,
                self.studio.settings,
                False,
            )
            await interaction.followup.send(
                file=discord.File(
                    preview,
                    filename=f"sorrowing.image.{extension}",
                ),
                ephemeral=is_ephemeral,
            )
            return
        if self.action == "reset":
            self.studio.settings = AsciiSettings()
        elif self.action == "auto_enhance":
            self.studio.settings.auto_enhance = not self.studio.settings.auto_enhance
        elif self.action == "invert":
            self.studio.settings.inverted = not self.studio.settings.inverted
        elif self.action == "threshold":
            self.studio.settings.threshold_enabled = (
                not self.studio.settings.threshold_enabled
            )
        elif self.action == "edges":
            self.studio.settings.edge_enabled = not self.studio.settings.edge_enabled
        elif self.action == "remove_background":
            self.studio.settings.remove_background = (
                not self.studio.settings.remove_background
            )
        await self.studio._update(interaction)


class AsciiStudioView(discord.ui.LayoutView):
    def __init__(self, owner_id: int, source_bytes: bytes) -> None:
        super().__init__(timeout=5 * 60)
        self.owner_id = owner_id
        self.source_bytes = source_bytes
        with Image.open(BytesIO(source_bytes)) as source:
            self.is_animated = (
                bool(getattr(source, "is_animated", False))
                and getattr(source, "n_frames", 1) > 1
            )
        self.settings = AsciiSettings()
        self.ascii_text = ""
        self.preview_data = b""
        self.preview_extension = "png"
        self.rendered_frames = 1
        self.message: discord.InteractionMessage | None = None
        self.busy = asyncio.Lock()
        self.expired = False
        self._rebuild_layout()

    async def build(self) -> discord.File:
        cache_key = (
            "ascii-preview",
            bytes_digest(self.source_bytes),
            repr(self.settings),
        )
        result = await run_media(
            _make_ascii,
            self.source_bytes,
            self.settings,
            True,
            cache_key=cache_key,
        )
        (
            self.ascii_text,
            preview,
            self.preview_extension,
            self.rendered_frames,
        ) = result
        self.preview_data = preview.getvalue()
        self._refresh_layout()
        return discord.File(
            BytesIO(self.preview_data),
            filename=f"sorrowing.image.{self.preview_extension}",
        )

    def _status_text(self) -> str:
        gradient_name = GRADIENTS[self.settings.gradient_index][0]
        color_name = COLOR_MODES[self.settings.color_index][0]
        animation_note = (
            f"\n`Animation` **{self.rendered_frames} optimized frames**　"
            f"`GIF FPS` **{self.settings.gif_fps}**"
            if self.preview_extension == "gif"
            else ""
        )
        return (
            "### Current settings\n"
            f"`Characters` **{self.settings.width}**　"
            f"`Brightness` **{self.settings.brightness}%**　"
            f"`Contrast` **{self.settings.contrast}%**　"
            f"`Sharpness` **{self.settings.sharpness}%**\n"
            f"`Gradient` **{gradient_name}**　"
            f"`Color` **{color_name}**　"
            f"`Spacing` **{self.settings.space_density}**\n"
            f"`Auto-enhance` **{'On' if self.settings.auto_enhance else 'Off'}**　"
            f"`Remove BG` **"
            f"{'On' if self.settings.remove_background else 'Off'}"
            f"**　"
            f"`Invert` **{'On' if self.settings.inverted else 'Off'}**　"
            f"`Threshold` **"
            f"{self.settings.threshold if self.settings.threshold_enabled else 'Off'}"
            f"**　`Edges` **"
            f"{self.settings.edge_strength if self.settings.edge_enabled else 'Off'}"
            f"**{animation_note}"
        )

    def _toggle_label(self, name: str, enabled: bool) -> str:
        return f"{name}: {'On' if enabled else 'Off'}"

    def _rebuild_layout(self) -> None:
        self.clear_items()
        preview_name = f"sorrowing.image.{self.preview_extension}"
        self.preview_gallery = discord.ui.MediaGallery(
            discord.MediaGalleryItem(
                f"attachment://{preview_name}",
                description="Live ASCII preview",
            )
        )
        self.status_display = discord.ui.TextDisplay(self._status_text())
        self.gradient_select = StudioSelect(self, "gradient")
        self.color_select = StudioSelect(self, "color")
        self.image_values_button = StudioButton(
            self,
            "image_values",
            label="Image values",
            style=discord.ButtonStyle.primary,
            emoji="🖼️",
        )
        self.effect_values_button = StudioButton(
            self,
            "effect_values",
            label="Effect values",
            style=discord.ButtonStyle.primary,
            emoji="🎛️",
        )
        self.auto_enhance_button = StudioButton(
            self,
            "auto_enhance",
            label=self._toggle_label(
                "Auto-enhance",
                self.settings.auto_enhance,
            ),
            emoji="✨",
        )
        self.invert_button = StudioButton(
            self,
            "invert",
            label=self._toggle_label(
                "Invert",
                self.settings.inverted,
            ),
            emoji="🔳",
        )
        self.threshold_button = StudioButton(
            self,
            "threshold",
            label=self._toggle_label(
                "Threshold",
                self.settings.threshold_enabled,
            ),
            emoji="⚫",
        )
        self.edges_button = StudioButton(
            self,
            "edges",
            label=self._toggle_label(
                "Edges",
                self.settings.edge_enabled,
            ),
            emoji="✒️",
        )
        self.remove_background_button = StudioButton(
            self,
            "remove_background",
            label=self._toggle_label(
                "Remove BG",
                self.settings.remove_background,
            ),
            emoji="🪄",
        )
        self.reset_button = StudioButton(
            self,
            "reset",
            label="Reset",
            style=discord.ButtonStyle.danger,
            emoji="🔄",
        )
        if not self.is_animated:
            self.download_text_button = StudioButton(
                self,
                "download_text",
                label="Save TXT",
                style=discord.ButtonStyle.success,
                emoji="📄",
            )
        self.download_preview_button = StudioButton(
            self,
            "download_preview",
            label=("Save GIF" if self.preview_extension == "gif" else "Save PNG"),
            style=discord.ButtonStyle.success,
            emoji="💾",
        )
        container = discord.ui.Container(
            discord.ui.TextDisplay(
                "## ✦ ASCII Studio\nFine-tune the image and watch the preview update."
            ),
            discord.ui.Separator(
                spacing=discord.SeparatorSpacing.small,
            ),
            self.preview_gallery,
            self.status_display,
            discord.ui.Separator(
                spacing=discord.SeparatorSpacing.small,
            ),
            discord.ui.TextDisplay("### Style"),
            discord.ui.ActionRow(
                self.gradient_select,
            ),
            discord.ui.ActionRow(
                self.color_select,
            ),
            discord.ui.TextDisplay("### Adjust values"),
            discord.ui.ActionRow(
                self.image_values_button,
                self.effect_values_button,
            ),
            discord.ui.TextDisplay("### Quick effects"),
            discord.ui.ActionRow(
                self.auto_enhance_button,
                self.invert_button,
                self.threshold_button,
                self.edges_button,
                self.remove_background_button,
            ),
            discord.ui.Separator(
                spacing=discord.SeparatorSpacing.small,
            ),
            discord.ui.ActionRow(
                self.reset_button,
                *(() if self.is_animated else (self.download_text_button,)),
                self.download_preview_button,
            ),
            discord.ui.TextDisplay(
                "-# Only the creator can use these controls · "
                "Live preview is speed-optimized · Studio closes after 5 minutes"
            ),
        )
        self.add_item(container)

    def _refresh_layout(self) -> None:
        preview_name = f"sorrowing.image.{self.preview_extension}"
        self.preview_gallery.clear_items()
        self.preview_gallery.add_item(
            media=f"attachment://{preview_name}",
            description="Live ASCII preview",
        )
        self.status_display.content = self._status_text()
        for option in self.gradient_select.options:
            option.default = option.value == str(self.settings.gradient_index)
        for option in self.color_select.options:
            option.default = option.value == str(self.settings.color_index)
        self.auto_enhance_button.label = self._toggle_label(
            "Auto-enhance",
            self.settings.auto_enhance,
        )
        self.invert_button.label = self._toggle_label(
            "Invert",
            self.settings.inverted,
        )
        self.threshold_button.label = self._toggle_label(
            "Threshold",
            self.settings.threshold_enabled,
        )
        self.edges_button.label = self._toggle_label(
            "Edges",
            self.settings.edge_enabled,
        )
        self.remove_background_button.label = self._toggle_label(
            "Remove BG",
            self.settings.remove_background,
        )
        self.download_preview_button.label = (
            "Save GIF" if self.preview_extension == "gif" else "Save PNG"
        )
        for item in self.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = self.expired

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            "This ASCII Studio belongs to someone else.",
            ephemeral=True,
        )
        return False

    async def _update(self, interaction: discord.Interaction) -> None:
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
        self._refresh_layout()
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class AsciiArt(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.context_menu = app_commands.ContextMenu(
            name="Open ASCII Studio",
            callback=self.open_ascii_studio,
        )
        self.bot.tree.add_command(self.context_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.context_menu.name,
            type=self.context_menu.type,
        )

    async def open_ascii_studio(
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
                    except (
                        ValueError,
                        OSError,
                        aiohttp.ClientError,
                    ) as error:
                        last_error = error
                if not source_bytes:
                    raise ValueError(
                        str(last_error)
                        if last_error is not None
                        else "I couldn't read media from those components."
                    )
        except (
            ValueError,
            UnidentifiedImageError,
            OSError,
            aiohttp.ClientError,
        ) as error:
            await interaction.edit_original_response(
                content=(str(error) or "I couldn't read that media.")[:1900],
            )
            return

        await self._send_studio(interaction, source_bytes)

    @app_commands.command(
        name="ascii",
        description="Open ASCII Studio with an upload or image link",
    )
    @app_commands.describe(
        image="Upload an image, GIF, or short video",
        image_url="Or paste a direct image/GIF/video link",
    )
    async def ascii_command(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment | None = None,
        image_url: str | None = None,
    ) -> None:
        if image is None and not image_url:
            await interaction.response.send_message(
                "Upload an image or paste a direct image link.",
                ephemeral=True,
            )
            return
        if image is not None and image_url:
            await interaction.response.send_message(
                "Choose either an uploaded image or an image link, not both.",
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
                    "That image is too large. Please use one under 12 MB.",
                    ephemeral=True,
                )
                return

        await interaction.response.defer(thinking=True)
        try:
            if image is not None:
                data = await image.read()
                source_bytes = await _prepare_source(
                    data,
                    content_type=image.content_type or "",
                    filename_or_url=image.filename,
                )
            else:
                data, content_type = await _download_media_url(image_url or "")
                source_bytes = await _prepare_source(
                    data,
                    content_type=content_type,
                    filename_or_url=image_url or "",
                )
        except (
            ValueError,
            UnidentifiedImageError,
            OSError,
            aiohttp.ClientError,
        ) as error:
            message = str(error) or "I couldn't read that image."
            await interaction.edit_original_response(content=message[:1900])
            return

        await self._send_studio(interaction, source_bytes)

    async def _send_studio(
        self,
        interaction: discord.Interaction,
        source_bytes: bytes,
    ) -> None:
        try:
            view = AsciiStudioView(interaction.user.id, source_bytes)
            file = await view.build()
        except (UnidentifiedImageError, OSError):
            await interaction.edit_original_response(
                content="I couldn't read that image format.",
            )
            return

        view.message = await interaction.edit_original_response(
            content=None,
            attachments=[file],
            view=view,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AsciiArt(bot))
