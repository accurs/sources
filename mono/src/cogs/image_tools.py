from __future__ import annotations

import asyncio
import io
import os
import re
import subprocess
import tempfile
import unicodedata
from functools import lru_cache

import aiohttp
import discord
import imageio_ffmpeg
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps, ImageSequence, UnidentifiedImageError

from .ascii_art import _component_media_urls, _download_media_url
from src.services.media_runtime import (
    FFMPEG_THREADS,
    bytes_digest,
    map_frames,
    run_media,
)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_DIMENSION = 4096
MAX_PIXELS = 20_000_000
MAX_GIF_FRAMES = 500
MAX_STICKER_BYTES = 512 * 1024
VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}

CAPTION_FONTS = {
    "Impact": ("impact.ttf", "Impact.ttf", "DejaVuSans-Bold.ttf"),
    "Arial Bold": ("arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"),
    "Segoe UI Bold": ("segoeuib.ttf", "DejaVuSans-Bold.ttf"),
    "Comic Sans": ("comicbd.ttf", "DejaVuSans-Bold.ttf"),
    "Papyrus": ("PAPYRUS.TTF", "papyrus.ttf", "DejaVuSerif.ttf"),
    "Georgia Bold": ("georgiab.ttf", "DejaVuSerif-Bold.ttf"),
    "Times Bold": ("timesbd.ttf", "DejaVuSerif-Bold.ttf"),
    "Consolas Bold": ("consolab.ttf", "DejaVuSansMono-Bold.ttf"),
}

POSITION_CHOICES = [
    app_commands.Choice(name="Top", value="top"),
    app_commands.Choice(name="Bottom", value="bottom"),
]

ASPECT_RATIO_CHOICES = [
    app_commands.Choice(name="16:9 (Landscape)", value="16:9"),
    app_commands.Choice(name="9:16 (Portrait)", value="9:16"),
    app_commands.Choice(name="1:1 (Square)", value="1:1"),
    app_commands.Choice(name="4:3", value="4:3"),
    app_commands.Choice(name="3:4", value="3:4"),
    app_commands.Choice(name="3:2", value="3:2"),
    app_commands.Choice(name="2:3", value="2:3"),
]

CONVERT_CHOICES = [
    app_commands.Choice(name="PNG", value="png"), app_commands.Choice(name="JPG", value="jpg"),
    app_commands.Choice(name="WebP", value="webp"), app_commands.Choice(name="GIF", value="gif"),
    app_commands.Choice(name="MP4", value="mp4"),
]


def convert_media(data: bytes, suffix: str, target: str, fps: int, resolution: int) -> tuple[bytes, str]:
    source_animated = suffix == ".gif" or suffix in VIDEO_SUFFIXES
    if target in {"png", "jpg", "webp"}:
        image = load_image(data)
        output = io.BytesIO();format_name={"png":"PNG","jpg":"JPEG","webp":"WEBP"}[target]
        if target == "jpg": image = Image.new("RGB", image.size, "white"); image.paste(load_image(data), mask=load_image(data).getchannel("A"))
        image.save(output, format=format_name, quality=90);return output.getvalue(), f"converted.{target}"
    if not source_animated and target == "gif":
        image=load_image(data);output=io.BytesIO();image.save(output,format="GIF");return output.getvalue(),"converted.gif"
    with tempfile.TemporaryDirectory(prefix="discord-convert-") as directory:
        input_path=os.path.join(directory,f"input{suffix or '.bin'}");output_path=os.path.join(directory,f"converted.{target}")
        with open(input_path,"wb") as file:file.write(data)
        command=[imageio_ffmpeg.get_ffmpeg_exe(),"-hide_banner","-loglevel","error","-threads",str(FFMPEG_THREADS),"-i",input_path]
        scale=f"scale='min({resolution},iw)':-2:flags=lanczos"
        if target=="gif":command.extend(["-vf",f"fps={fps},{scale}","-loop","0",output_path])
        elif target=="mp4":command.extend(["-vf",scale,"-c:v","libx264","-threads",str(FFMPEG_THREADS),"-preset","veryfast","-crf","24","-pix_fmt","yuv420p","-movflags","+faststart","-an",output_path])
        else:raise ValueError("That conversion is not supported.")
        result=subprocess.run(command,capture_output=True,text=True,timeout=120)
        if result.returncode:raise ValueError(result.stderr.strip()[-500:] or "FFmpeg could not convert that file.")
        with open(output_path,"rb") as file:return file.read(),f"converted.{target}"


def add_watermark(image: Image.Image, text: str, opacity: int, placement: str, color: str) -> Image.Image:
    if not text:return image
    result=image.convert("RGBA");layer=Image.new("RGBA",result.size,(0,0,0,0));draw=ImageDraw.Draw(layer);font=ImageFont.load_default(size=max(14,result.width//35))
    try:rgb=ImageColor.getrgb(color)
    except ValueError:rgb=(255,255,255)
    box=draw.textbbox((0,0),text,font=font,stroke_width=1);width,height=box[2]-box[0],box[3]-box[1];margin=max(8,result.width//50)
    x=margin if "left" in placement else result.width-width-margin;y=margin if "top" in placement else result.height-height-margin
    draw.text((x,y),text,font=font,fill=(*rgb,round(255*opacity/100)),stroke_width=1,stroke_fill=(0,0,0,round(220*opacity/100)));return Image.alpha_composite(result,layer)


def caption_studio_export(data:bytes,suffix:str,text:str,position:str,watermark:str,opacity:int,placement:str,color:str,background_color:str="#FFFFFF",text_color:str="#000000",font_name:str="Impact",text_size:int=100,fast_preview:bool=False)->tuple[bytes,str]:
    if suffix==".gif":
        captioned=caption_animated_gif(data,text,position,background_color,text_color,font_name,text_size,max_frames=24 if fast_preview else None,max_dimension=720 if fast_preview else None);source=Image.open(io.BytesIO(captioned));raw_frames=[];durations=[]
        for frame in ImageSequence.Iterator(source):raw_frames.append(frame.convert("RGBA").copy());durations.append(frame.info.get("duration",80))
        frames=map_frames(lambda frame:add_watermark(frame,watermark,opacity,placement,color),raw_frames)
        output=io.BytesIO();frames[0].save(output,format="GIF",save_all=True,append_images=frames[1:],duration=durations,loop=0,disposal=2);return output.getvalue(),"captioned.gif"
    result=meme_caption(load_image(data),text,position,background_color,text_color,font_name,text_size);result=add_watermark(result,watermark,opacity,placement,color);output=io.BytesIO();result.save(output,format="PNG");return output.getvalue(),"captioned.png"


def extract_video_frame(data: bytes, suffix: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="caption-preview-") as directory:
        input_path = os.path.join(directory, f"input{suffix or '.mp4'}")
        frame_path = os.path.join(directory, "frame.png")
        with open(input_path, "wb") as source:
            source.write(data)
        command = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-threads",
            str(FFMPEG_THREADS),
            "-i",
            input_path,
            "-frames:v",
            "1",
            frame_path,
        ]
        subprocess.run(command, check=True, capture_output=True, timeout=60)
        with open(frame_path, "rb") as frame:
            return frame.read()


def caption_video_export(
    data: bytes,
    suffix: str,
    target: str,
    text: str,
    position: str,
    watermark: str,
    opacity: int,
    placement: str,
    watermark_color: str,
    background_color: str,
    text_color: str,
    font_name: str,
    text_size: int,
) -> tuple[bytes, str]:
    with tempfile.TemporaryDirectory(prefix="caption-video-") as directory:
        input_path = os.path.join(directory, f"input{suffix or '.mp4'}")
        overlay_path = os.path.join(directory, "overlay.png")
        output_name = "captioned.gif" if target == "gif" else "captioned.mp4"
        output_path = os.path.join(directory, output_name)
        with open(input_path, "wb") as source:
            source.write(data)

        frame_data = extract_video_frame(data, suffix)
        frame = load_image(frame_data)
        captioned = meme_caption(
            frame,
            text,
            position,
            background_color,
            text_color,
            font_name,
            text_size,
        )
        band_height = captioned.height - frame.height
        overlay = Image.new("RGBA", captioned.size, (0, 0, 0, 0))
        if position == "top":
            band = captioned.crop((0, 0, captioned.width, band_height))
            overlay.paste(band, (0, 0))
        else:
            band = captioned.crop(
                (0, frame.height, captioned.width, captioned.height)
            )
            overlay.paste(band, (0, frame.height))
        overlay = add_watermark(
            overlay, watermark, opacity, placement, watermark_color
        )
        overlay.save(overlay_path, format="PNG")

        video_y = band_height if position == "top" else 0
        filters = (
            f"[0:v]pad=iw:ih+{band_height}:0:{video_y}:color=black[base];"
            "[base][1:v]overlay=0:0:format=auto:shortest=1[composed]"
        )
        if target == "gif":
            filters += (
                ";[composed]fps=12,"
                "scale='min(720,iw)':-2:flags=lanczos[out]"
            )
        else:
            filters += ";[composed]scale=trunc(iw/2)*2:trunc(ih/2)*2[out]"

        command = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-threads",
            str(FFMPEG_THREADS),
            "-i",
            input_path,
            "-loop",
            "1",
            "-i",
            overlay_path,
            "-filter_complex",
            filters,
            "-map",
            "[out]",
        ]
        if target == "gif":
            command.extend(["-an", "-shortest", output_path])
        else:
            command.extend(
                [
                    "-map",
                    "0:a?",
                    "-c:v",
                    "libx264",
                    "-threads",
                    str(FFMPEG_THREADS),
                    "-preset",
                    "veryfast",
                    "-crf",
                    "24",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-movflags",
                    "+faststart",
                    "-shortest",
                    output_path,
                ]
            )
        subprocess.run(command, check=True, capture_output=True, timeout=180)
        with open(output_path, "rb") as output:
            return output.read(), output_name


class CaptionTextModal(discord.ui.Modal,title="Caption Text"):
    text=discord.ui.TextInput(label="Caption",style=discord.TextStyle.paragraph,max_length=500)
    async def on_submit(self,i):
        view=getattr(self,"studio",None);view.text=str(self.text);await view.update_preview(i)


class WatermarkModal(discord.ui.Modal,title="Watermark"):
    text=discord.ui.TextInput(label="Watermark text",required=False,max_length=100)
    opacity=discord.ui.TextInput(label="Opacity (0-100)",default="60",max_length=3)
    color=discord.ui.TextInput(label="Color name or HEX",default="#FFFFFF",max_length=20)
    async def on_submit(self,i):
        view=getattr(self,"studio",None)
        try:value=max(0,min(100,int(str(self.opacity))))
        except ValueError:await i.response.send_message("Opacity must be from 0 to 100.",ephemeral=True);return
        view.watermark=str(self.text);view.opacity=value;view.color=str(self.color);await view.update_preview(i)


class CaptionStyleModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Caption Colors")
        self.studio = view
        self.background = discord.ui.TextInput(
            label="Background color",
            default=view.background_color,
            placeholder="#FFFFFF or white",
            max_length=20,
        )
        self.foreground = discord.ui.TextInput(
            label="Text color",
            default=view.text_color,
            placeholder="#000000 or black",
            max_length=20,
        )
        self.size = discord.ui.TextInput(
            label="Text size percentage (25-100)",
            default=str(view.text_size),
            placeholder="100",
            max_length=3,
        )
        self.add_item(self.background)
        self.add_item(self.foreground)
        self.add_item(self.size)

    async def on_submit(self, interaction):
        background = str(self.background).strip()
        foreground = str(self.foreground).strip()
        try:
            ImageColor.getrgb(background)
            ImageColor.getrgb(foreground)
            size = int(str(self.size))
        except ValueError:
            await interaction.response.send_message(
                "Use valid colors and a text size from 25 to 100.",
                ephemeral=True,
            )
            return
        if not 25 <= size <= 100:
            await interaction.response.send_message(
                "Text size must be from 25 to 100.", ephemeral=True
            )
            return
        self.studio.background_color = background
        self.studio.text_color = foreground
        self.studio.text_size = size
        await self.studio.update_preview(interaction)


class StudioFontSelect(discord.ui.Select):
    def __init__(self, selected):
        super().__init__(
            placeholder=f"Font: {selected}",
            options=[
                discord.SelectOption(label=name, value=name, default=name == selected)
                for name in CAPTION_FONTS
            ],
        )

    async def callback(self, interaction):
        view = self.view
        assert isinstance(view, CaptionStudioView)
        view.font_name = self.values[0]
        await view.update_preview(interaction)


class StudioExportSelect(discord.ui.Select):
    def __init__(self, media_kind, selected):
        choices = {
            "image": (("Image", "image"), ("GIF", "gif")),
            "gif": (("GIF", "gif"), ("Video (MP4)", "video")),
            "video": (("Video (MP4)", "video"), ("GIF", "gif")),
        }[media_kind]
        super().__init__(
            placeholder="Export format",
            options=[
                discord.SelectOption(
                    label=label, value=value, default=value == selected
                )
                for label, value in choices
            ],
        )

    async def callback(self, interaction):
        view = self.view
        assert isinstance(view, CaptionStudioView)
        view.export_format = self.values[0]
        view.render()
        await interaction.response.edit_message(view=view)


class StudioButton(discord.ui.Button):
    def __init__(self,action,label,style=discord.ButtonStyle.secondary):super().__init__(label=label,style=style);self.action=action
    async def callback(self,i):
        view=self.view;assert isinstance(view,CaptionStudioView)
        if self.action=="text":modal=CaptionTextModal();modal.studio=view;await i.response.send_modal(modal);return
        if self.action=="watermark":modal=WatermarkModal();modal.studio=view;await i.response.send_modal(modal);return
        if self.action=="style":await i.response.send_modal(CaptionStyleModal(view));return
        if self.action=="position":view.position="bottom" if view.position=="top" else "top";await view.update_preview(i);return
        if self.action=="placement":
            places=("bottom-right","bottom-left","top-left","top-right");view.placement=places[(places.index(view.placement)+1)%len(places)];await view.update_preview(i);return
        await view.export(i)


class CaptionStudioView(discord.ui.LayoutView):
    def __init__(self,user_id,data,suffix,preview_url,preview_data=None):super().__init__(timeout=300);self.user_id=user_id;self.data=data;self.suffix=suffix;self.preview_url=preview_url;self.media_kind="video" if suffix in VIDEO_SUFFIXES else "gif" if suffix==".gif" else "image";self.export_format=self.media_kind;self.preview_data=preview_data or data;self.text="Your caption";self.position="top";self.background_color="#FFFFFF";self.text_color="#000000";self.font_name="Impact";self.text_size=100;self.watermark="";self.opacity=60;self.placement="bottom-right";self.color="#FFFFFF";self.busy=asyncio.Lock();self.render()
    def render(self):
        export_label={"image":"Image","gif":"GIF","video":"Video (MP4)"}[self.export_format];self.clear_items();self.add_item(discord.ui.Container(discord.ui.TextDisplay(f"## Caption Studio\n**Caption:** {self.text}\n**Caption position:** {self.position.title()}\n**Font:** {self.font_name} · **Size:** {self.text_size}%\n**Background:** `{self.background_color}` · **Text:** `{self.text_color}`\n**Watermark:** {self.watermark or 'Off'}\n**Watermark placement:** {self.placement.replace('-',' ').title()}\n**Opacity:** {self.opacity}% · **Color:** `{self.color}`\n**Export:** {export_label}"),discord.ui.Separator(),discord.ui.MediaGallery(discord.MediaGalleryItem(self.preview_url,description="Caption preview")),discord.ui.Separator(),discord.ui.ActionRow(StudioFontSelect(self.font_name)),discord.ui.ActionRow(StudioExportSelect(self.media_kind,self.export_format)),discord.ui.ActionRow(StudioButton("text","Edit Caption"),StudioButton("position","Move Caption"),StudioButton("style","Colors & Size")),discord.ui.ActionRow(StudioButton("watermark","Watermark"),StudioButton("placement","Move Watermark"),StudioButton("export","Export",discord.ButtonStyle.success))))
    async def interaction_check(self,i):
        if i.user.id==self.user_id:return True
        await i.response.send_message("This studio belongs to someone else.",ephemeral=True);return False
    def build_preview(self):
        preview_suffix=".png" if self.media_kind=="video" else self.suffix;output,name=caption_studio_export(self.preview_data,preview_suffix,self.text,self.position,self.watermark,self.opacity,self.placement,self.color,self.background_color,self.text_color,self.font_name,self.text_size,True)
        extension=os.path.splitext(name)[1] or ".png";preview_name=f"caption-preview{extension}";return discord.File(io.BytesIO(output),filename=preview_name),preview_name
    async def update_preview(self,i):
        if self.busy.locked():await i.response.send_message("The preview is already updating.",ephemeral=True);return
        async with self.busy:
            await i.response.defer()
            preview_suffix=".png" if self.media_kind=="video" else self.suffix
            preview_key=("caption-preview",bytes_digest(self.preview_data),self.text,self.position,self.watermark,self.opacity,self.placement,self.color,self.background_color,self.text_color,self.font_name,self.text_size)
            try:
                output,name=await run_media(caption_studio_export,self.preview_data,preview_suffix,self.text,self.position,self.watermark,self.opacity,self.placement,self.color,self.background_color,self.text_color,self.font_name,self.text_size,True,cache_key=preview_key)
                extension=os.path.splitext(name)[1] or ".png";name=f"caption-preview{extension}";file=discord.File(io.BytesIO(output),filename=name)
            except (OSError,ValueError,UnidentifiedImageError) as error:await i.followup.send(f"Could not update the preview: {error}",ephemeral=True);return
            self.preview_url=f"attachment://{name}";self.render()
            await i.edit_original_response(attachments=[file],view=self)
    async def export(self,i):
        await i.response.defer(thinking=True)
        try:
            if self.media_kind=="video":output,name=await run_media(caption_video_export,self.data,self.suffix,self.export_format,self.text,self.position,self.watermark,self.opacity,self.placement,self.color,self.background_color,self.text_color,self.font_name,self.text_size)
            else:
                output,name=await run_media(caption_studio_export,self.data,self.suffix,self.text,self.position,self.watermark,self.opacity,self.placement,self.color,self.background_color,self.text_color,self.font_name,self.text_size)
                if self.export_format=="video":output,name=await run_media(convert_media,output,".gif","mp4",12,720)
                elif self.export_format=="gif" and self.media_kind=="image":output,name=await run_media(convert_media,output,".png","gif",12,720)
        except (OSError,ValueError,UnidentifiedImageError,subprocess.SubprocessError) as error:await i.followup.send(f"Could not export: {error}",ephemeral=True);return
        if len(output)>MAX_UPLOAD_BYTES:await i.followup.send("The export is larger than 25 MB.",ephemeral=True);return
        await i.followup.send(file=discord.File(io.BytesIO(output),filename=name))


def load_image(data: bytes) -> Image.Image:
    source = Image.open(io.BytesIO(data))
    source.seek(0)
    image = ImageOps.exif_transpose(source).convert("RGBA")
    if image.width * image.height > MAX_PIXELS:
        raise ValueError("That image has too many pixels.")
    return image


def make_discord_sticker(data: bytes) -> tuple[bytes, str, bool]:
    """Stretch media to Discord's exact sticker canvas without cropping."""
    source = Image.open(io.BytesIO(data))
    animated = bool(getattr(source, "is_animated", False))
    frames: list[Image.Image] = []
    durations: list[int] = []
    frame_limit = min(int(getattr(source, "n_frames", 1)), MAX_GIF_FRAMES)
    for index, frame in enumerate(ImageSequence.Iterator(source)):
        if index >= frame_limit:
            break
        rgba = frame.convert("RGBA").resize((320, 320), Image.Resampling.LANCZOS)
        frames.append(rgba)
        durations.append(max(20, int(frame.info.get("duration", 80))))
    if not frames:
        raise ValueError("That upload does not contain a usable image.")

    if not animated or len(frames) == 1:
        for colors in (0, 256, 128, 64, 32):
            output = io.BytesIO()
            image = frames[0]
            if colors:
                image = image.quantize(colors=colors, method=Image.Quantize.FASTOCTREE)
            image.save(output, format="PNG", optimize=True, compress_level=9)
            if output.tell() <= MAX_STICKER_BYTES:
                return output.getvalue(), "sticker.png", False
        raise ValueError("That image cannot be compressed below Discord's 512 KB sticker limit.")

    # APNG is Discord's supported animated sticker format. Progressively reduce
    # frame rate and color count until it fits the upload limit.
    for stride in (1, 2, 3, 4, 6, 8):
        selected = frames[::stride]
        selected_durations = [
            sum(durations[index : index + stride])
            for index in range(0, len(durations), stride)
        ]
        for colors in (256, 128, 64, 32):
            rendered = [
                frame.quantize(colors=colors, method=Image.Quantize.FASTOCTREE)
                for frame in selected
            ]
            output = io.BytesIO()
            rendered[0].save(
                output,
                format="PNG",
                save_all=True,
                append_images=rendered[1:],
                duration=selected_durations,
                loop=int(source.info.get("loop", 0)),
                optimize=True,
                compress_level=9,
            )
            if output.tell() <= MAX_STICKER_BYTES:
                return output.getvalue(), "sticker.png", True
    raise ValueError(
        "That animation is too detailed or long to fit Discord's 512 KB sticker limit."
    )


def video_to_discord_sticker(data: bytes, suffix: str) -> tuple[bytes, str, bool]:
    """Turn the first three seconds of a video into a Discord-ready APNG."""
    with tempfile.TemporaryDirectory(prefix="video-sticker-") as directory:
        input_path = os.path.join(directory, f"input{suffix or '.mp4'}")
        gif_path = os.path.join(directory, "frames.gif")
        with open(input_path, "wb") as source:
            source.write(data)
        command = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-threads",
            str(FFMPEG_THREADS),
            "-i",
            input_path,
            "-t",
            "3",
            "-vf",
            "fps=12,scale=320:320:flags=lanczos",
            "-an",
            gif_path,
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise ValueError(
                result.stderr.strip()[-500:] or "FFmpeg could not read that video."
            )
        with open(gif_path, "rb") as rendered:
            return make_discord_sticker(rendered.read())


def png_file(image: Image.Image, filename: str) -> discord.File:
    output = io.BytesIO()
    image.save(output, format="PNG", compress_level=6)
    output.seek(0)
    return discord.File(output, filename=filename)


def _transparent_gif_frame(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A")
    quantized = image.convert("RGB").quantize(
        colors=255,
        method=Image.Quantize.MEDIANCUT,
    )
    palette = quantized.getpalette()[: 255 * 3]
    paletted = quantized.point(lambda index: index + 1)
    paletted.putpalette([0, 0, 0] + palette)
    transparent_pixels = alpha.point(lambda value: 255 if value < 128 else 0)
    paletted.paste(0, mask=transparent_pixels)
    paletted.info["transparency"] = 0
    paletted.info["disposal"] = 2
    return paletted


def _resize_gif_frame(
    frame: Image.Image,
    size: tuple[int, int],
) -> Image.Image:
    return _transparent_gif_frame(
        frame.resize(size, Image.Resampling.LANCZOS)
    )


def resize_animated_gif(data: bytes, ratio: str) -> bytes:
    source = Image.open(io.BytesIO(data))
    frame_count = getattr(source, "n_frames", 1)
    if frame_count > MAX_GIF_FRAMES:
        raise ValueError(f"That GIF has more than {MAX_GIF_FRAMES} frames.")

    ratio_width, ratio_height = (int(part) for part in ratio.split(":"))
    target_width = min(
        source.width,
        MAX_DIMENSION,
        int(MAX_DIMENSION * ratio_width / ratio_height),
    )
    target_width = max(1, target_width)
    target_height = max(1, round(target_width * ratio_height / ratio_width))
    source_frames: list[Image.Image] = []
    durations: list[int] = []
    default_duration = int(source.info.get("duration", 100))

    for frame in ImageSequence.Iterator(source):
        source_frames.append(frame.convert("RGBA").copy())
        durations.append(int(frame.info.get("duration", default_duration)))

    frames = map_frames(
        lambda frame: _resize_gif_frame(
            frame,
            (target_width, target_height),
        ),
        source_frames,
    )

    output = io.BytesIO()
    frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=int(source.info.get("loop", 0)),
        disposal=2,
        transparency=0,
        optimize=False,
    )
    return output.getvalue()


def resize_animated_media(
    data: bytes,
    suffix: str,
    ratio: str,
    is_gif: bool,
) -> tuple[bytes, str]:
    if is_gif:
        return resize_animated_gif(data, ratio), "resized.gif"

    ratio_width, ratio_height = (int(part) for part in ratio.split(":"))
    target_width = (
        f"trunc(min(min(iw,{MAX_DIMENSION}),"
        f"{MAX_DIMENSION}*{ratio_width}/{ratio_height})/2)*2"
    )
    target_height = f"trunc(({target_width})*{ratio_height}/{ratio_width}/2)*2"
    scale_filter = f"scale=w='{target_width}':h='{target_height}':flags=lanczos"

    with tempfile.TemporaryDirectory(prefix="discord-resize-") as directory:
        input_path = os.path.join(directory, f"input{suffix}")
        output_name = "resized.mp4"
        output_path = os.path.join(directory, output_name)
        with open(input_path, "wb") as source:
            source.write(data)
        command = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-threads",
            str(FFMPEG_THREADS),
            "-i",
            input_path,
            "-vf",
            scale_filter,
        ]
        command.extend(
            [
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-threads",
                str(FFMPEG_THREADS),
                "-preset",
                "veryfast",
                "-crf",
                "26",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                output_path,
            ]
        )
        subprocess.run(command, check=True, capture_output=True, timeout=120)
        with open(output_path, "rb") as output:
            return output.read(), output_name


def fit_to_aspect_ratio(image: Image.Image, ratio: str) -> Image.Image:
    ratio_width, ratio_height = (int(part) for part in ratio.split(":"))
    target_ratio = ratio_width / ratio_height
    target_width = image.width
    target_height = max(1, round(target_width / target_ratio))
    if max(target_width, target_height) > MAX_DIMENSION:
        scale = MAX_DIMENSION / max(target_width, target_height)
        target_width = max(1, round(target_width * scale))
        target_height = max(1, round(target_height * scale))
    return image.resize((target_width, target_height), Image.Resampling.LANCZOS)


def resize_static_image(data: bytes, ratio: str) -> bytes:
    result = fit_to_aspect_ratio(load_image(data), ratio)
    output = io.BytesIO()
    result.save(output, format="PNG", compress_level=6)
    return output.getvalue()


def caption_static_image(data: bytes, text: str, position: str) -> bytes:
    result = meme_caption(load_image(data), text, position)
    output = io.BytesIO()
    result.save(output, format="PNG", compress_level=6)
    return output.getvalue()


@lru_cache(maxsize=128)
def get_font(size: int, font_name: str = "Impact") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = CAPTION_FONTS.get(font_name, CAPTION_FONTS["Impact"])
    font_directory = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
    for name in candidates:
        try:
            path = os.path.join(font_directory, name)
            return ImageFont.truetype(path if os.path.isfile(path) else name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


@lru_cache(maxsize=64)
def get_emoji_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_directory = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
    for name in ("seguiemj.ttf", "NotoColorEmoji.ttf", "NotoEmoji-Regular.ttf"):
        try:
            path = os.path.join(font_directory, name)
            return ImageFont.truetype(path if os.path.isfile(path) else name, size=size)
        except OSError:
            continue
    return get_font(size, "Segoe UI Bold")


def split_graphemes(text: str) -> list[str]:
    """Keep common emoji modifiers and joined sequences together."""
    clusters: list[str] = []
    join_next = False
    for character in text:
        codepoint = ord(character)
        modifier = (
            character in {"\ufe0e", "\ufe0f", "\u200d", "\u20e3"}
            or 0x1F3FB <= codepoint <= 0x1F3FF
            or 0xE0020 <= codepoint <= 0xE007F
            or unicodedata.category(character).startswith("M")
        )
        regional = 0x1F1E6 <= codepoint <= 0x1F1FF
        previous_regional = bool(
            clusters
            and clusters[-1]
            and 0x1F1E6 <= ord(clusters[-1][0]) <= 0x1F1FF
            and len(clusters[-1]) == 1
        )
        if clusters and (modifier or join_next or (regional and previous_regional)):
            clusters[-1] += character
        else:
            clusters.append(character)
        join_next = character == "\u200d"
    return clusters


def is_emoji_cluster(cluster: str) -> bool:
    for character in cluster:
        codepoint = ord(character)
        if (
            0x1F000 <= codepoint <= 0x1FAFF
            or 0x2600 <= codepoint <= 0x27BF
            or 0x1F1E6 <= codepoint <= 0x1F1FF
            or codepoint in {0x231A, 0x231B, 0x23F0, 0x23F3, 0x2B50, 0x2B55, 0x3030, 0x303D, 0x3297, 0x3299}
            or "\u20e3" in cluster
        ):
            return True
    return False


def mixed_text_width(draw, text: str, font, emoji_font) -> float:
    return sum(
        draw.textlength(
            cluster,
            font=emoji_font if is_emoji_cluster(cluster) else font,
        )
        for cluster in split_graphemes(text)
    )


def mixed_text_height(draw, text: str, font, emoji_font) -> int:
    heights = []
    for cluster in split_graphemes(text):
        selected_font = emoji_font if is_emoji_cluster(cluster) else font
        box = draw.textbbox((0, 0), cluster, font=selected_font, anchor="lt")
        heights.append(box[3] - box[1])
    return max(heights, default=0)


def draw_mixed_text(draw, position, text: str, font, emoji_font, fill) -> None:
    x, y = position
    for cluster in split_graphemes(text):
        emoji = is_emoji_cluster(cluster)
        selected_font = emoji_font if emoji else font
        kwargs = {"font": selected_font, "anchor": "lt"}
        if emoji:
            kwargs["embedded_color"] = True
        else:
            kwargs["fill"] = fill
        draw.text((x, y), cluster, **kwargs)
        x += draw.textlength(cluster, font=selected_font)


def wrap_caption(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    max_width: int,
    stroke_width: int = 2,
    emoji_font=None,
) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        width = (
            mixed_text_width(draw, candidate, font, emoji_font)
            if emoji_font is not None
            else draw.textbbox(
                (0, 0), candidate, font=font, stroke_width=stroke_width
            )[2]
        )
        if current and width > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def meme_caption(
    image: Image.Image,
    text: str,
    position: str,
    background_color: str = "#FFFFFF",
    text_color: str = "#000000",
    font_name: str = "Impact",
    text_size: int = 100,
) -> Image.Image:
    measuring = ImageDraw.Draw(image)
    caption = " ".join(text.upper().split())
    horizontal_margin = max(4, round(image.width * 0.055))
    max_width = max(40, image.width - horizontal_margin * 2)
    max_height = image.height * 0.6

    chosen = None
    automatic_size = max(8, round(image.width * 0.08))
    start_size = max(8, round(automatic_size * text_size / 100))
    for font_size in range(start_size, 7, -1):
        font = get_font(font_size, font_name)
        emoji_font = get_emoji_font(font_size)
        lines = wrap_caption(measuring, caption, font, max_width, 0, emoji_font)
        line_height = font_size + max(2, round(font_size * 0.14))
        if lines and len(lines) * line_height <= max_height:
            chosen = font, emoji_font, lines, line_height
            break
    if chosen is None:
        raise ValueError("That caption is too long for this image.")

    font, emoji_font, lines, line_height = chosen
    vertical_margin = max(4, round(image.width * 0.018))
    visual_line_heights = [
        mixed_text_height(measuring, line, font, emoji_font) for line in lines
    ]
    visual_block_height = max(
        index * line_height + height
        for index, height in enumerate(visual_line_heights)
    )
    block_height = len(lines) * line_height
    band_height = block_height + vertical_margin * 2
    result = Image.new(
        "RGBA", (image.width, image.height + band_height), (0, 0, 0, 0)
    )
    image_y = band_height if position == "top" else 0
    result.paste(image, (0, image_y), image)
    draw = ImageDraw.Draw(result)
    band_y = 0 if position == "top" else image.height
    draw.rectangle(
        (0, band_y, result.width, band_y + band_height),
        fill=background_color,
    )
    # Center the actual visible glyphs, not the font's nominal line box. Fonts
    # carry invisible ascender/descender space, which previously made captions
    # appear too high inside the band.
    start_y = band_y + round((band_height - visual_block_height) / 2)
    for index, line in enumerate(lines):
        width = mixed_text_width(draw, line, font, emoji_font)
        x = round((result.width - width) / 2)
        draw_mixed_text(
            draw,
            (x, start_y + index * line_height),
            line,
            font,
            emoji_font,
            text_color,
        )
    return result


def caption_animated_gif(
    data: bytes,
    text: str,
    position: str,
    background_color: str = "#FFFFFF",
    text_color: str = "#000000",
    font_name: str = "Impact",
    text_size: int = 100,
    max_frames: int | None = None,
    max_dimension: int | None = None,
) -> bytes:
    source = Image.open(io.BytesIO(data))
    frame_count = getattr(source, "n_frames", 1)
    if frame_count > MAX_GIF_FRAMES:
        raise ValueError(f"That GIF has more than {MAX_GIF_FRAMES} frames.")

    source_frames: list[Image.Image] = []
    durations: list[int] = []
    default_duration = int(source.info.get("duration", 100))
    frame_indices = list(range(frame_count))
    if max_frames is not None and frame_count > max_frames:
        frame_indices = [
            min(frame_count - 1, index * frame_count // max_frames)
            for index in range(max_frames)
        ]
    for frame_index in frame_indices:
        source.seek(frame_index)
        frame = source.copy()
        rgba = frame.convert("RGBA")
        if max_dimension is not None:
            rgba.thumbnail(
                (max_dimension, max_dimension),
                Image.Resampling.LANCZOS,
            )
        if rgba.width * rgba.height > MAX_PIXELS:
            raise ValueError("That GIF has too many pixels per frame.")
        source_frames.append(rgba.copy())
        durations.append(int(frame.info.get("duration", default_duration)))

    def render(frame: Image.Image) -> Image.Image:
        return _transparent_gif_frame(
            meme_caption(
                frame,
                text,
                position,
                background_color,
                text_color,
                font_name,
                text_size,
            )
        )

    frames = map_frames(render, source_frames)

    output = io.BytesIO()
    frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=int(source.info.get("loop", 0)),
        disposal=2,
        transparency=0,
        optimize=False,
    )
    return output.getvalue()


class ImageTools(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.caption_context_menu = app_commands.ContextMenu(
            name="Open Caption Studio",
            callback=self.open_caption_studio,
        )
        self.bot.tree.add_command(self.caption_context_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.caption_context_menu.name,
            type=self.caption_context_menu.type,
        )

    async def _send_caption_studio(
        self,
        interaction: discord.Interaction,
        data: bytes,
        suffix: str,
    ) -> None:
        try:
            view, file, name = await self.build_caption_studio(
                interaction.user.id, data, suffix
            )
        except (
            OSError,
            ValueError,
            UnidentifiedImageError,
            subprocess.SubprocessError,
        ) as error:
            await interaction.followup.send(
                f"Could not build the preview: {error}", ephemeral=True
            )
            return
        await interaction.followup.send(view=view, file=file)

    @staticmethod
    async def build_caption_studio(
        user_id: int,
        data: bytes,
        suffix: str,
    ) -> tuple[CaptionStudioView, discord.File, str]:
        preview_data = (
            await run_media(extract_video_frame, data, suffix)
            if suffix in VIDEO_SUFFIXES
            else data
        )
        view = CaptionStudioView(user_id, data, suffix, "", preview_data)
        file, name = await run_media(view.build_preview)
        view.preview_url = f"attachment://{name}"
        view.render()
        return view, file, name

    async def open_caption_studio(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ) -> None:
        media_suffixes = {
            ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", *VIDEO_SUFFIXES
        }
        attachment = next(
            (
                item
                for item in message.attachments
                if (
                    item.content_type is not None
                    and item.content_type.startswith(("image/", "video/"))
                )
                or os.path.splitext(item.filename)[1].lower() in media_suffixes
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
                "That message does not contain an image, GIF, or video.", ephemeral=True
            )
            return
        if attachment is not None and attachment.size > MAX_UPLOAD_BYTES:
            await interaction.response.send_message(
                "Please use a file smaller than 25 MB.", ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)
        try:
            if attachment is not None:
                data = await attachment.read()
                suffix = os.path.splitext(attachment.filename)[1].lower()
                content_type = attachment.content_type or ""
                if content_type.startswith("video/") and suffix not in VIDEO_SUFFIXES:
                    suffix = ".mp4"
                elif content_type == "image/gif":
                    suffix = ".gif"
            else:
                last_error: Exception | None = None
                data = b""
                for media_url in media_urls:
                    try:
                        candidate_data, content_type = await _download_media_url(
                            media_url
                        )
                        if content_type.startswith(("image/", "video/")):
                            data = candidate_data
                            downloaded_content_type = content_type
                            break
                    except (OSError, ValueError, aiohttp.ClientError) as error:
                        last_error = error
                if not data:
                    raise ValueError(
                        str(last_error) if last_error else "I couldn't read that image."
                    )
                if len(data) > MAX_UPLOAD_BYTES:
                    raise ValueError("Please use a file smaller than 25 MB.")
                if downloaded_content_type.startswith("video/"):
                    suffix = ".mp4"
                else:
                    with Image.open(io.BytesIO(data)) as source:
                        suffix = ".gif" if source.format == "GIF" else ".png"
            if suffix not in VIDEO_SUFFIXES:
                with Image.open(io.BytesIO(data)) as source:
                    source.verify()
        except (
            discord.HTTPException,
            OSError,
            ValueError,
            UnidentifiedImageError,
            aiohttp.ClientError,
        ) as error:
            await interaction.followup.send(
                str(error) or "I couldn't read that image.", ephemeral=True
            )
            return

        await self._send_caption_studio(interaction, data, suffix)

    @staticmethod
    async def validate_upload(
        interaction: discord.Interaction,
        image: discord.Attachment,
        allow_gif: bool = False,
        allow_video: bool = False,
    ) -> bool:
        if image.size > MAX_UPLOAD_BYTES:
            await interaction.response.send_message(
                "Please use a file smaller than 25 MB.", ephemeral=True
            )
            return False
        content_type = image.content_type or ""
        suffix = os.path.splitext(image.filename)[1].lower()
        is_gif = content_type == "image/gif" or suffix == ".gif"
        allowed = (
            (content_type.startswith("image/") and (allow_gif or not is_gif))
            or (allow_video and content_type.startswith("video/"))
        )
        if content_type and not allowed:
            if allow_video:
                supported = "an image, GIF, or video"
            elif allow_gif:
                supported = "an image or GIF"
            else:
                supported = "a static image"
            await interaction.response.send_message(
                f"That upload does not look like {supported}.",
                ephemeral=True,
            )
            return False
        return True

    @staticmethod
    async def reply_attachment(
        ctx: commands.Context,
        attachment: discord.Attachment | None = None,
    ) -> discord.Attachment | None:
        if attachment is not None:
            return attachment
        if ctx.message.attachments:
            return ctx.message.attachments[0]
        reference = ctx.message.reference
        if reference is None:
            return None
        resolved = reference.resolved
        if not isinstance(resolved, discord.Message) and reference.message_id:
            try:
                resolved = await ctx.channel.fetch_message(reference.message_id)
            except (discord.HTTPException, AttributeError):
                return None
        if isinstance(resolved, discord.Message) and resolved.attachments:
            return resolved.attachments[0]
        return None

    @staticmethod
    def attachment_kind(attachment: discord.Attachment) -> tuple[str, bool, bool]:
        content_type = attachment.content_type or ""
        suffix = os.path.splitext(attachment.filename)[1].lower() or ".bin"
        is_gif = content_type == "image/gif" or suffix == ".gif"
        is_video = content_type.startswith("video/") or suffix in VIDEO_SUFFIXES
        if is_video and suffix not in VIDEO_SUFFIXES:
            suffix = ".mp4"
        return suffix, is_gif, is_video

    async def make_sticker_file(
        self,
        attachment: discord.Attachment,
    ) -> tuple[discord.File, str]:
        if attachment.size > MAX_UPLOAD_BYTES:
            raise ValueError("Please use a file smaller than 25 MB.")
        suffix, _, is_video = self.attachment_kind(attachment)
        content_type = attachment.content_type or ""
        if content_type and not content_type.startswith(("image/", "video/")):
            raise ValueError("That upload does not look like an image, GIF, or video.")
        data = await attachment.read()
        if is_video:
            output, filename, animated = await run_media(
                video_to_discord_sticker,
                data,
                suffix,
                cache_key=("discord-video-sticker", bytes_digest(data), suffix),
            )
        else:
            output, filename, animated = await run_media(
                make_discord_sticker,
                data,
                cache_key=("discord-sticker", bytes_digest(data)),
            )
        kind = "Animated APNG" if animated else "Static PNG"
        return discord.File(io.BytesIO(output), filename=filename), (
            f"{kind} · `320 × 320` · `{len(output) / 1024:.1f} KB`"
        )

    async def make_caption_file(
        self,
        attachment: discord.Attachment,
        text: str,
        position: str,
    ) -> discord.File:
        if attachment.size > MAX_UPLOAD_BYTES:
            raise ValueError("Please use a file smaller than 25 MB.")
        suffix, is_gif, is_video = self.attachment_kind(attachment)
        content_type = attachment.content_type or ""
        if content_type and not content_type.startswith(("image/", "video/")):
            raise ValueError("That upload does not look like an image, GIF, or video.")
        data = await attachment.read()
        if is_video:
            output, filename = await run_media(
                caption_video_export,
                data,
                suffix,
                "video",
                text,
                position,
                "",
                60,
                "bottom-right",
                "#FFFFFF",
                "#FFFFFF",
                "#000000",
                "Impact",
                100,
                cache_key=("caption-video", bytes_digest(data), suffix, text, position),
            )
            if len(output) > MAX_UPLOAD_BYTES:
                raise ValueError(
                    "The captioned video is larger than 25 MB. Try a shorter or smaller video."
                )
        elif is_gif:
            output = await run_media(
                caption_animated_gif,
                data,
                text,
                position,
                cache_key=("caption-gif", bytes_digest(data), text, position),
            )
            filename = "captioned.gif"
            if len(output) > MAX_UPLOAD_BYTES:
                raise ValueError(
                    "The captioned GIF is larger than 25 MB. Try a shorter GIF."
                )
        else:
            output = await run_media(
                caption_static_image,
                data,
                text,
                position,
                cache_key=("caption-image", bytes_digest(data), text, position),
            )
            filename = "captioned.png"
        return discord.File(io.BytesIO(output), filename=filename)

    async def make_resize_file(
        self,
        attachment: discord.Attachment,
        aspect_ratio: str,
    ) -> tuple[discord.File, str]:
        if aspect_ratio not in {choice.value for choice in ASPECT_RATIO_CHOICES}:
            raise ValueError("Choose one of: `16:9`, `9:16`, `1:1`, `4:3`, `3:4`, `3:2`, or `2:3`.")
        if attachment.size > MAX_UPLOAD_BYTES:
            raise ValueError("Please use a file smaller than 25 MB.")
        suffix, is_gif, is_video = self.attachment_kind(attachment)
        content_type = attachment.content_type or ""
        if content_type and not content_type.startswith(("image/", "video/")):
            raise ValueError("That upload does not look like an image, GIF, or video.")
        data = await attachment.read()
        if is_gif or is_video:
            output, filename = await run_media(
                resize_animated_media,
                data,
                suffix,
                aspect_ratio,
                is_gif,
                cache_key=(
                    "resize-animated",
                    bytes_digest(data),
                    suffix,
                    aspect_ratio,
                    is_gif,
                ),
            )
            if len(output) > MAX_UPLOAD_BYTES:
                raise ValueError(
                    "The resized file is still larger than 25 MB."
                )
            return (
                discord.File(io.BytesIO(output), filename=filename),
                f"{len(output) / 1024 / 1024:.1f} MB",
            )
        output = await run_media(
            resize_static_image,
            data,
            aspect_ratio,
            cache_key=("resize-image", bytes_digest(data), aspect_ratio),
        )
        with Image.open(io.BytesIO(output)) as result:
            size = f"{result.width} x {result.height} pixels"
        return discord.File(io.BytesIO(output), filename="resized.png"), size

    @app_commands.command(name="caption-studio", description="Interactively caption and watermark an image, GIF, or video")
    async def caption_studio(self, interaction: discord.Interaction, media: discord.Attachment) -> None:
        if not await self.validate_upload(interaction,media,allow_gif=True,allow_video=True):return
        await interaction.response.defer(thinking=True)
        try:data=await media.read()
        except discord.HTTPException:await interaction.followup.send("I couldn't download that upload.",ephemeral=True);return
        suffix=os.path.splitext(media.filename)[1].lower()
        if (media.content_type or "").startswith("video/") and suffix not in VIDEO_SUFFIXES:suffix=".mp4"
        elif media.content_type=="image/gif":suffix=".gif"
        await self._send_caption_studio(interaction, data, suffix)

    @commands.command(
        name="caption-studio",
        description="Reply to media and open the interactive caption studio",
    )
    async def caption_studio_prefix(self, ctx: commands.Context) -> None:
        media = await self.reply_attachment(ctx)
        if media is None:
            await ctx.send("Reply to a message containing an image, GIF, or video.")
            return
        if media.size > MAX_UPLOAD_BYTES:
            await ctx.send("Please use a file smaller than 25 MB.")
            return
        suffix, _, _ = self.attachment_kind(media)
        content_type = media.content_type or ""
        if content_type and not content_type.startswith(("image/", "video/")):
            await ctx.send("That upload does not look like an image, GIF, or video.")
            return
        async with ctx.typing():
            try:
                data = await media.read()
                view, file, _ = await self.build_caption_studio(
                    ctx.author.id, data, suffix
                )
            except (
                discord.HTTPException,
                OSError,
                subprocess.SubprocessError,
                UnidentifiedImageError,
                ValueError,
            ) as error:
                await ctx.send(f"Could not build the preview: {error}")
                return
        await ctx.send(view=view, file=file)

    @app_commands.command(name="convert", description="Convert an image, GIF, or video")
    @app_commands.choices(target=CONVERT_CHOICES)
    async def convert(
        self,
        interaction: discord.Interaction,
        media: discord.Attachment,
        target: app_commands.Choice[str],
        fps: app_commands.Range[int, 5, 30] = 12,
        resolution: app_commands.Range[int, 240, 1920] = 720,
        ephemeral: bool = False,
    ) -> None:
        if not await self.validate_upload(interaction, media, allow_gif=True, allow_video=True): return
        await interaction.response.defer(thinking=True, ephemeral=ephemeral)
        try:
            data=await media.read();suffix=os.path.splitext(media.filename)[1].lower()
            output,filename=await run_media(convert_media,data,suffix,target.value,fps,resolution,cache_key=("convert",bytes_digest(data),suffix,target.value,fps,resolution))
            if len(output)>MAX_UPLOAD_BYTES:raise ValueError("The converted file is larger than 25 MB. Try a lower resolution or FPS.")
        except (discord.HTTPException,OSError,subprocess.SubprocessError,UnidentifiedImageError,ValueError) as error:
            await interaction.followup.send(f"Could not convert that file: {error}",ephemeral=True);return
        await interaction.followup.send(file=discord.File(io.BytesIO(output),filename=filename),ephemeral=ephemeral)

    @app_commands.command(name="resize", description="Resize an image, GIF, or video")
    @app_commands.choices(aspect_ratio=ASPECT_RATIO_CHOICES)
    @app_commands.describe(
        media="Image, animated GIF, or video to resize",
        aspect_ratio="Stretch the image to this ratio without cropping",
        ephemeral="Only show the result to you",
    )
    async def resize(
        self,
        interaction: discord.Interaction,
        media: discord.Attachment,
        aspect_ratio: app_commands.Choice[str],
        ephemeral: bool = False,
    ) -> None:
        if not await self.validate_upload(
            interaction, media, allow_gif=True, allow_video=True
        ):
            return
        await interaction.response.defer(thinking=True, ephemeral=ephemeral)
        try:
            file, result_size = await self.make_resize_file(
                media, aspect_ratio.value
            )
        except (
            discord.HTTPException,
            OSError,
            subprocess.SubprocessError,
            UnidentifiedImageError,
            ValueError,
        ) as error:
            await interaction.followup.send(f"Could not resize that file: {error}", ephemeral=True)
            return
        await interaction.followup.send(
            f"Resized successfully (**{result_size}**).",
            file=file,
            ephemeral=ephemeral,
        )

    @commands.command(
        name="resize",
        description="Reply to an image, GIF, or video and resize its aspect ratio",
        usage="resize <16:9|9:16|1:1|4:3|3:4|3:2|2:3>",
    )
    async def resize_prefix(self, ctx: commands.Context, aspect_ratio: str) -> None:
        media = await self.reply_attachment(ctx)
        if media is None:
            await ctx.send("Reply to a message containing an image, GIF, or video.")
            return
        async with ctx.typing():
            try:
                file, result_size = await self.make_resize_file(media, aspect_ratio)
            except (
                discord.HTTPException,
                OSError,
                subprocess.SubprocessError,
                UnidentifiedImageError,
                ValueError,
            ) as error:
                await ctx.send(f"Could not resize that media: {error}")
                return
        await ctx.send(f"Resized successfully (**{result_size}**).", file=file)

    @app_commands.command(name="sticker", description="Prepare an image, GIF, or video as a Discord sticker")
    @app_commands.describe(image="Image, GIF, or video to turn into a 320 x 320 sticker")
    async def sticker(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
        ephemeral: bool = False,
    ) -> None:
        if not await self.validate_upload(
            interaction, image, allow_gif=True, allow_video=True
        ):
            return
        await interaction.response.defer(thinking=True, ephemeral=ephemeral)
        try:
            file, details = await self.make_sticker_file(image)
        except (
            discord.HTTPException,
            OSError,
            subprocess.SubprocessError,
            UnidentifiedImageError,
            ValueError,
        ) as error:
            await interaction.followup.send(
                f"Could not prepare that sticker: {error}", ephemeral=True
            )
            return
        await interaction.followup.send(
            details,
            file=file,
            ephemeral=ephemeral,
        )

    @commands.command(
        name="sticker",
        description="Reply to an image, GIF, or video and prepare it as a Discord sticker",
    )
    async def sticker_prefix(
        self,
        ctx: commands.Context,
        attachment: discord.Attachment | None = None,
    ) -> None:
        media = await self.reply_attachment(ctx, attachment)
        if media is None:
            await ctx.send("Reply to a message containing an image, GIF, or video.")
            return
        async with ctx.typing():
            try:
                file, details = await self.make_sticker_file(media)
            except (
                discord.HTTPException,
                OSError,
                subprocess.SubprocessError,
                UnidentifiedImageError,
                ValueError,
            ) as error:
                await ctx.send(f"Could not prepare that sticker: {error}")
                return
        await ctx.send(details, file=file)

    @app_commands.command(name="caption", description="Add a meme caption to an image, GIF, or video")
    @app_commands.choices(position=POSITION_CHOICES)
    @app_commands.describe(
        media="Image, animated GIF, or video to caption",
        text="Caption text",
        position="Place the white caption section at the top or bottom (default: top)",
        ephemeral="Only show the result to you",
    )
    async def caption(
        self,
        interaction: discord.Interaction,
        media: discord.Attachment,
        text: app_commands.Range[str, 1, 500],
        position: app_commands.Choice[str] | None = None,
        ephemeral: bool = False,
    ) -> None:
        if not await self.validate_upload(
            interaction,
            media,
            allow_gif=True,
            allow_video=True,
        ):
            return
        await interaction.response.defer(thinking=True, ephemeral=ephemeral)
        try:
            caption_position = position.value if position else "top"
            file = await self.make_caption_file(media, text, caption_position)
        except (
            discord.HTTPException,
            OSError,
            subprocess.SubprocessError,
            UnidentifiedImageError,
            ValueError,
        ) as error:
            await interaction.followup.send(f"Could not caption that media: {error}", ephemeral=True)
            return
        await interaction.followup.send(file=file, ephemeral=ephemeral)

    @commands.command(
        name="caption",
        description="Reply to an image, GIF, or video and add a meme caption",
        usage="caption <text> [--top|--bottom]",
    )
    async def caption_prefix(self, ctx: commands.Context, *, text: str) -> None:
        position = "bottom" if "--bottom" in text.casefold().split() else "top"
        text = re.sub(r"(?i)(?:^|\s)--(?:top|bottom)(?=\s|$)", " ", text).strip()
        if not text:
            await ctx.send("Add the caption text after `caption`.")
            return
        media = await self.reply_attachment(ctx)
        if media is None:
            await ctx.send("Reply to a message containing an image, GIF, or video.")
            return
        async with ctx.typing():
            try:
                file = await self.make_caption_file(media, text[:500], position)
            except (
                discord.HTTPException,
                OSError,
                subprocess.SubprocessError,
                UnidentifiedImageError,
                ValueError,
            ) as error:
                await ctx.send(f"Could not caption that media: {error}")
                return
        await ctx.send(file=file)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ImageTools(bot))
