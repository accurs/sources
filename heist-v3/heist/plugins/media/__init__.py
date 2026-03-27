import io
import os
import aiohttp
import asyncio
import discord
from PIL import Image, ImageSequence, ImageChops, ImageFilter, ImageEnhance, ImageOps
from discord.ext import commands
from discord import app_commands
from discord.ext.commands import Cog

class Media(Cog):
    def __init__(self, bot):
        self.bot = bot

    def _is_image(self, attachment: discord.Attachment):
        return attachment.content_type and attachment.content_type.startswith("image/")

    async def _get_image_from_ctx(self, ctx):
        if ctx.message.attachments:
            a = ctx.message.attachments[0]
            if a.content_type and a.content_type.startswith("image/"):
                return a
        if ctx.message.reference:
            try:
                m = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                if m.attachments:
                    a = m.attachments[0]
                    if a.content_type and a.content_type.startswith("image/"):
                        return a
            except:
                pass
        return None

    media_group = app_commands.Group(name="media", description="Image manipulation & processing", allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True), allowed_installs=app_commands.AppInstallationType(guild=True, user=True))

    @media_group.command(name="imagetogif", description="Convert an image to GIF")
    @app_commands.describe(image="Image to convert")
    async def slash_imagetogif(self, interaction: discord.Interaction, image: discord.Attachment):
        await interaction.response.defer()
        await self._convert_image_to_gif(interaction, image)

    @commands.command(name="imagetogif", aliases=["img2gif","togif","image2gif"], description="Convert an image to GIF")
    async def cmd_imagetogif(self, ctx: commands.Context):
        image = await self._get_image_from_ctx(ctx)
        await self._convert_image_to_gif(ctx, image)

    async def _convert_image_to_gif(self, ctx, image):
        if not image or not self._is_image(image):
            return await ctx.warn("No image provided or replied to.")
        if image.filename.lower().endswith(".gif"):
            return await ctx.warn("Already a GIF.")
        d = await image.read()
        n = image.filename.rsplit(".",1)[0]+".gif"
        if isinstance(ctx, discord.Interaction):
            await ctx.followup.send(file=discord.File(io.BytesIO(d),n))
        else:
            await ctx.send(file=discord.File(io.BytesIO(d),n))

    @media_group.command(name="speechbubble", description="Add speech bubble")
    @app_commands.describe(image="Image", togif="Make GIF?")
    @app_commands.choices(togif=[
        app_commands.Choice(name="No", value="false"),
        app_commands.Choice(name="Yes", value="true")
    ])
    async def slash_speechbubble(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
        togif: app_commands.Choice[str] = None
    ):
        await interaction.response.defer()
        togif_bool = (togif.value == "true") if togif else False
        await self._speechbubble(interaction, image, togif_bool)

    @commands.command(name="speechbubble", aliases=["bubble"], description="Add speech bubble to an image")
    async def cmd_speechbubble(self, ctx: commands.Context, togif: bool=False):
        image = await self._get_image_from_ctx(ctx)
        await self._speechbubble(ctx, image, togif)

    async def _speechbubble(self, ctx, image, togif):
        if not image or not self._is_image(image):
            return await ctx.warn("No image provided or replied to.")
        d = await image.read()
        img = await asyncio.to_thread(Image.open, io.BytesIO(d))
        f = img.format
        g = f=="GIF"
        if g:
            fr = await asyncio.to_thread(lambda:[x.copy().convert("RGBA") for x in ImageSequence.Iterator(img)])
            du = await asyncio.to_thread(lambda:[x.info.get("duration",100) for x in ImageSequence.Iterator(img)])
        else:
            fr = [await asyncio.to_thread(img.convert,"RGBA")]
        b = await asyncio.to_thread(Image.open,"/root/heist-v3/heist/assets/speech_bubble.png")
        b = await asyncio.to_thread(b.convert,"RGBA")
        out=[]
        for x in fr:
            rb = await asyncio.to_thread(lambda:b.resize(x.size,Image.Resampling.LANCZOS))
            m = rb.split()[3]
            o = Image.new("RGBA",x.size,(0,0,0,0))
            o.paste(x,(0,0))
            o.putalpha(ImageChops.subtract(o.split()[3],m))
            out.append(o)
        buf=io.BytesIO()
        if g or (togif and len(out)>1):
            out[0].save(buf,format="GIF",save_all=True,append_images=out[1:],duration=du if g else 100,loop=0)
            e="gif"
        else:
            sf="PNG" if f=="JPEG" else f
            out[0].save(buf,format=sf)
            e="gif" if togif else sf.lower()
        buf.seek(0)
        if isinstance(ctx, discord.Interaction):
            await ctx.followup.send(file=discord.File(buf,f"heist.{e}"))
        else:
            await ctx.send(file=discord.File(buf,f"heist.{e}"))

    @media_group.command(name="caption", description="Add caption to an image")
    @app_commands.describe(image="Image", caption="Caption", togif="Make GIF?")
    @app_commands.choices(togif=[
        app_commands.Choice(name="No", value="no"),
        app_commands.Choice(name="Yes", value="yes")
    ])
    async def slash_caption(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
        caption: str,
        togif: app_commands.Choice[str] = None
    ):
        await interaction.response.defer()
        togif_value = togif.value if togif else "no"
        await self._caption(interaction, image, caption, togif_value)

    @commands.command(name="caption", aliases=["addcaption","cc"], description="Add caption to an image")
    async def cmd_caption(self, ctx: commands.Context, *, caption: str=None):
        image = await self._get_image_from_ctx(ctx)
        await self._caption(ctx, image, caption, "no")

    async def _caption(self, ctx, image, caption, togif):
        if not image or not self._is_image(image):
            return await ctx.warn("No image provided or replied to.")
        if not caption:
            return await ctx.warn("No caption provided.")
        d = await image.read()
        if len(d) > 10*1024*1024:
            return await ctx.warn("Image too large.")
        f = aiohttp.FormData()
        f.add_field('image',d,filename='image.png',content_type=image.content_type)
        f.add_field('caption',caption)
        f.add_field('togif',togif)
        async with aiohttp.ClientSession() as s:
            async with s.post("http://localhost:3636/caption",data=f) as r:
                if r.status==200:
                    o=await r.read()
                    ex='gif' if togif=="yes" or image.content_type.endswith('gif') else image.filename.split('.')[-1]
                    if isinstance(ctx, discord.Interaction):
                        await ctx.followup.send(file=discord.File(io.BytesIO(o),f"heist.{ex}"))
                    else:
                        await ctx.send(file=discord.File(io.BytesIO(o),f"heist.{ex}"))
                else:
                    await ctx.warn(await r.text())

    @media_group.command(name="blackandwhite", description="Convert an image to black & white")
    @app_commands.describe(image="Image to process")
    async def slash_blackandwhite(self, interaction: discord.Interaction, image: discord.Attachment):
        await interaction.response.defer()
        await self._blackandwhite(interaction, image)

    @commands.command(name="blackandwhite", aliases=["bw","greyscale","grayscale"], description="Convert an image to black & white")
    async def cmd_blackandwhite(self, ctx: commands.Context):
        image = await self._get_image_from_ctx(ctx)
        await self._blackandwhite(ctx, image)

    async def _blackandwhite(self, ctx, image):
        if not image or not self._is_image(image):
            return await ctx.warn("No image provided or replied to.")
        d = await image.read()
        img = await asyncio.to_thread(Image.open, io.BytesIO(d))
        fmt = img.format
        is_gif = fmt == "GIF"

        if is_gif:
            frames = await asyncio.to_thread(lambda:[f.copy().convert("RGB").convert("L").convert("RGBA") for f in ImageSequence.Iterator(img)])
            durations = await asyncio.to_thread(lambda:[f.info.get("duration",100) for f in ImageSequence.Iterator(img)])
        else:
            f = await asyncio.to_thread(img.convert, "RGB")
            f = await asyncio.to_thread(f.convert, "L")
            f = await asyncio.to_thread(f.convert, "RGBA")
            frames = [f]

        out = io.BytesIO()
        if is_gif:
            frames[0].save(out, format="GIF", save_all=True, append_images=frames[1:], duration=durations, loop=0)
            ext = "gif"
        else:
            frames[0].save(out, format="PNG")
            ext = "png"
        out.seek(0)

        if isinstance(ctx, discord.Interaction):
            await ctx.followup.send(file=discord.File(out, f"heist.{ext}"))
        else:
            await ctx.send(file=discord.File(out, f"heist.{ext}"))

    @media_group.command(name="pixelate", description="Pixelate an image")
    @app_commands.describe(image="Image to pixelate")
    @app_commands.choices(size=[
        app_commands.Choice(name="Small", value="small"),
        app_commands.Choice(name="Medium", value="medium"),
        app_commands.Choice(name="Large", value="large")
    ])
    async def slash_pixelate(self, interaction: discord.Interaction, image: discord.Attachment, size: app_commands.Choice[str]):
        await interaction.response.defer()
        await self._pixelate(interaction, image, size.value)

    @commands.command(name="pixelate", description="Pixelate an image")
    async def cmd_pixelate(self, ctx: commands.Context, size: str = "medium"):
        image = await self._get_image_from_ctx(ctx)
        await self._pixelate(ctx, image, size)

    async def _pixelate(self, ctx, image, size):
        if not image or not self._is_image(image):
            return await ctx.warn("No image provided or replied to.")
        d = await image.read()
        img = await asyncio.to_thread(Image.open, io.BytesIO(d))
        fmt = img.format
        is_gif = fmt == "GIF"
        size = (size or "medium").lower()
        if size == "small":
            block = 8
        elif size == "large":
            block = 32
        else:
            block = 16
        if is_gif:
            frames = await asyncio.to_thread(lambda:[f.copy().convert("RGBA") for f in ImageSequence.Iterator(img)])
            durations = await asyncio.to_thread(lambda:[f.info.get("duration",100) for f in ImageSequence.Iterator(img)])
        else:
            frames = [await asyncio.to_thread(img.convert, "RGBA")]
            durations = None
        processed = []
        for f in frames:
            w, h = f.size
            nw = max(1, w // block)
            nh = max(1, h // block)
            small = await asyncio.to_thread(lambda: f.resize((nw, nh), Image.Resampling.NEAREST))
            big = await asyncio.to_thread(lambda: small.resize((w, h), Image.Resampling.NEAREST))
            processed.append(big)
        out = io.BytesIO()
        if is_gif:
            processed[0].save(out, format="GIF", save_all=True, append_images=processed[1:], duration=durations, loop=0)
            ext = "gif"
        else:
            processed[0].save(out, format="PNG")
            ext = "png"
        out.seek(0)
        if isinstance(ctx, discord.Interaction):
            await ctx.followup.send(file=discord.File(out, f"heist.{ext}"))
        else:
            await ctx.send(file=discord.File(out, f"heist.{ext}"))

    @media_group.command(name="invert", description="Invert image colors")
    @app_commands.describe(image="Image to invert")
    async def slash_invert(self, interaction: discord.Interaction, image: discord.Attachment):
        await interaction.response.defer()
        await self._invert(interaction, image)

    @commands.command(name="invert", description="Invert image colors")
    async def cmd_invert(self, ctx: commands.Context):
        image = await self._get_image_from_ctx(ctx)
        await self._invert(ctx, image)

    async def _invert(self, ctx, image):
        if not image or not self._is_image(image):
            return await ctx.warn("No image provided or replied to.")
        d = await image.read()
        img = await asyncio.to_thread(Image.open, io.BytesIO(d))
        fmt = img.format
        is_gif = fmt == "GIF"
        if is_gif:
            frames = await asyncio.to_thread(lambda:[f.copy().convert("RGBA") for f in ImageSequence.Iterator(img)])
            durations = await asyncio.to_thread(lambda:[f.info.get("duration",100) for f in ImageSequence.Iterator(img)])
        else:
            frames = [await asyncio.to_thread(img.convert, "RGBA")]
            durations = None
        processed = []
        for f in frames:
            rgb = await asyncio.to_thread(f.convert, "RGB")
            inv = await asyncio.to_thread(ImageOps.invert, rgb)
            pf = await asyncio.to_thread(inv.convert, "RGBA")
            processed.append(pf)
        out = io.BytesIO()
        if is_gif:
            processed[0].save(out, format="GIF", save_all=True, append_images=processed[1:], duration=durations, loop=0)
            ext = "gif"
        else:
            processed[0].save(out, format="PNG")
            ext = "png"
        out.seek(0)
        if isinstance(ctx, discord.Interaction):
            await ctx.followup.send(file=discord.File(out, f"heist.{ext}"))
        else:
            await ctx.send(file=discord.File(out, f"heist.{ext}"))

    @media_group.command(name="deepfry", description="Deepfry an image")
    @app_commands.describe(image="Image to deepfry")
    async def slash_deepfry(self, interaction: discord.Interaction, image: discord.Attachment):
        await interaction.response.defer()
        await self._deepfry(interaction, image)

    @commands.command(name="deepfry", description="Deepfry an image")
    async def cmd_deepfry(self, ctx: commands.Context):
        image = await self._get_image_from_ctx(ctx)
        await self._deepfry(ctx, image)

    async def _deepfry(self, ctx, image):
        if not image or not self._is_image(image):
            return await ctx.warn("No image provided or replied to.")
        d = await image.read()
        img = await asyncio.to_thread(Image.open, io.BytesIO(d))
        fmt = img.format
        is_gif = fmt == "GIF"
        if is_gif:
            frames = await asyncio.to_thread(lambda:[f.copy().convert("RGB") for f in ImageSequence.Iterator(img)])
            durations = await asyncio.to_thread(lambda:[f.info.get("duration",100) for f in ImageSequence.Iterator(img)])
        else:
            frames = [await asyncio.to_thread(img.convert, "RGB")]
            durations = None
        processed = []
        for f in frames:
            f1 = await asyncio.to_thread(lambda: ImageEnhance.Sharpness(f).enhance(5.0))
            f2 = await asyncio.to_thread(lambda: ImageEnhance.Contrast(f1).enhance(2.0))
            f3 = await asyncio.to_thread(lambda: ImageEnhance.Color(f2).enhance(3.0))
            noise = await asyncio.to_thread(lambda: Image.effect_noise(f3.size, 64))
            noise = await asyncio.to_thread(noise.convert, "L")
            colored = await asyncio.to_thread(ImageOps.colorize, noise, (255,255,0), (255,0,0))
            colored = await asyncio.to_thread(colored.convert, "RGBA")
            base_rgba = await asyncio.to_thread(f3.convert, "RGBA")
            pf = await asyncio.to_thread(lambda: Image.blend(base_rgba, colored, 0.3))
            processed.append(pf)
        out = io.BytesIO()
        if is_gif:
            processed[0].save(out, format="GIF", save_all=True, append_images=processed[1:], duration=durations, loop=0)
            ext = "gif"
        else:
            processed[0].save(out, format="PNG")
            ext = "png"
        out.seek(0)
        if isinstance(ctx, discord.Interaction):
            await ctx.followup.send(file=discord.File(out, f"heist.{ext}"))
        else:
            await ctx.send(file=discord.File(out, f"heist.{ext}"))

    @media_group.command(name="stretch", description="Stretch an image horizontally")
    @app_commands.describe(image="Image to stretch", amount="Stretch factor (0.5-2.0)")
    async def slash_stretch(self, interaction: discord.Interaction, image: discord.Attachment, amount: float = 1.3):
        await interaction.response.defer()
        await self._stretch(interaction, image, amount)

    @commands.command(name="stretch", description="Stretch an image horizontally")
    async def cmd_stretch(self, ctx: commands.Context, amount: float = 1.3):
        image = await self._get_image_from_ctx(ctx)
        await self._stretch(ctx, image, amount)

    async def _stretch(self, ctx, image, amount):
        if not image or not self._is_image(image):
            return await ctx.warn("No image provided or replied to.")
        try:
            amount = float(amount)
        except:
            amount = 1.3
        amount = max(0.5, min(2.0, amount))
        d = await image.read()
        img = await asyncio.to_thread(Image.open, io.BytesIO(d))
        fmt = img.format
        is_gif = fmt == "GIF"
        if is_gif:
            frames = await asyncio.to_thread(lambda:[f.copy().convert("RGBA") for f in ImageSequence.Iterator(img)])
            durations = await asyncio.to_thread(lambda:[f.info.get("duration",100) for f in ImageSequence.Iterator(img)])
        else:
            frames = [await asyncio.to_thread(img.convert, "RGBA")]
            durations = None
        processed = []
        for f in frames:
            w, h = f.size
            new_w = max(1, int(w * amount))
            stretched = await asyncio.to_thread(lambda: f.resize((new_w, h), Image.Resampling.BICUBIC))
            if amount >= 1.0:
                left = (new_w - w) // 2
                right = left + w
                cropped = await asyncio.to_thread(lambda: stretched.crop((left, 0, right, h)))
                processed.append(cropped)
            else:
                canvas = Image.new("RGBA", (w, h), (0,0,0,0))
                x = (w - new_w) // 2
                canvas.paste(stretched, (x, 0))
                processed.append(canvas)
        out = io.BytesIO()
        if is_gif:
            processed[0].save(out, format="GIF", save_all=True, append_images=processed[1:], duration=durations, loop=0)
            ext = "gif"
        else:
            processed[0].save(out, format="PNG")
            ext = "png"
        out.seek(0)
        if isinstance(ctx, discord.Interaction):
            await ctx.followup.send(file=discord.File(out, f"heist.{ext}"))
        else:
            await ctx.send(file=discord.File(out, f"heist.{ext}"))

    @media_group.command(name="saturate", description="Saturate an image")
    @app_commands.describe(image="Image to saturate", amount="Saturation factor (0.0-3.0)")
    async def slash_saturate(self, interaction: discord.Interaction, image: discord.Attachment, amount: float = 1.5):
        await interaction.response.defer()
        await self._saturate(interaction, image, amount)

    @commands.command(name="saturate", description="Saturate an image")
    async def cmd_saturate(self, ctx: commands.Context, amount: float = 1.5):
        image = await self._get_image_from_ctx(ctx)
        await self._saturate(ctx, image, amount)

    async def _saturate(self, ctx, image, amount):
        if not image or not self._is_image(image):
            return await ctx.warn("No image provided or replied to.")
        try:
            amount = float(amount)
        except:
            amount = 1.0
        amount = max(0.0, min(3.0, amount))
        d = await image.read()
        img = await asyncio.to_thread(Image.open, io.BytesIO(d))
        fmt = img.format
        is_gif = fmt == "GIF"
        if is_gif:
            frames = await asyncio.to_thread(lambda:[f.copy().convert("RGB") for f in ImageSequence.Iterator(img)])
            durations = await asyncio.to_thread(lambda:[f.info.get("duration",100) for f in ImageSequence.Iterator(img)])
        else:
            frames = [await asyncio.to_thread(img.convert, "RGB")]
            durations = None
        processed = []
        for f in frames:
            pf = await asyncio.to_thread(lambda: ImageEnhance.Color(f).enhance(amount))
            pf = await asyncio.to_thread(pf.convert, "RGBA")
            processed.append(pf)
        out = io.BytesIO()
        if is_gif:
            processed[0].save(out, format="GIF", save_all=True, append_images=processed[1:], duration=durations, loop=0)
            ext = "gif"
        else:
            processed[0].save(out, format="PNG")
            ext = "png"
        out.seek(0)
        if isinstance(ctx, discord.Interaction):
            await ctx.followup.send(file=discord.File(out, f"heist.{ext}"))
        else:
            await ctx.send(file=discord.File(out, f"heist.{ext}"))

    @media_group.command(name="overlay", description="Overlay one image on another")
    @app_commands.describe(base="Base image", overlay="Overlay image", opacity="Overlay opacity (0-100)")
    async def slash_overlay(self, interaction: discord.Interaction, base: discord.Attachment, overlay: discord.Attachment, opacity: int = 70):
        await interaction.response.defer()
        await self._overlay(interaction, base, overlay, opacity)

    @commands.command(name="overlay", description="Overlay one image on another")
    async def cmd_overlay(self, ctx: commands.Context, opacity: int = 70):
        attachments = ctx.message.attachments
        base = None
        overlay = None
        if len(attachments) >= 2:
            base = attachments[0]
            overlay = attachments[1]
        elif len(attachments) == 1 and ctx.message.reference:
            try:
                m = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                if m.attachments:
                    base = attachments[0]
                    overlay = m.attachments[0]
                else:
                    base = None
            except:
                base = None
        if not base or not overlay:
            return await ctx.warn("Attach two images or attach one and reply to another.")
        await self._overlay(ctx, base, overlay, opacity)

    async def _overlay(self, ctx, base, overlay, opacity):
        if not base or not overlay:
            return await ctx.warn("Missing images.")
        if not self._is_image(base) or not self._is_image(overlay):
            return await ctx.warn("One of the files is not an image.")
        try:
            opacity = int(opacity)
        except:
            opacity = 70
        opacity = max(0, min(100, opacity))
        bd = await base.read()
        od = await overlay.read()
        bimg = await asyncio.to_thread(Image.open, io.BytesIO(bd))
        oimg = await asyncio.to_thread(Image.open, io.BytesIO(od))
        if bimg.format == "GIF" or oimg.format == "GIF":
            return await ctx.warn("GIFs are not supported for overlay yet.")
        b_rgba = await asyncio.to_thread(bimg.convert, "RGBA")
        o_rgba = await asyncio.to_thread(oimg.convert, "RGBA")
        o_rgba = await asyncio.to_thread(lambda: o_rgba.resize(b_rgba.size, Image.Resampling.LANCZOS))
        alpha_val = int(255 * (opacity / 100.0))
        if o_rgba.mode != "RGBA":
            o_rgba = await asyncio.to_thread(o_rgba.convert, "RGBA")
        oa = o_rgba.split()[3]
        mask = Image.new("L", o_rgba.size, alpha_val)
        combined_alpha = await asyncio.to_thread(ImageChops.multiply, oa, mask)
        o_rgba.putalpha(combined_alpha)
        out_img = await asyncio.to_thread(Image.alpha_composite, b_rgba, o_rgba)
        out = io.BytesIO()
        out_img.save(out, format="PNG")
        out.seek(0)
        if isinstance(ctx, discord.Interaction):
            await ctx.followup.send(file=discord.File(out, "heist.png"))
        else:
            await ctx.send(file=discord.File(out, "heist.png"))

    @media_group.command(name="flip", description="Flip an image")
    @app_commands.describe(image="Image to flip")
    @app_commands.choices(direction=[
        app_commands.Choice(name="Left", value="left"),
        app_commands.Choice(name="Right", value="right"),
        app_commands.Choice(name="Up", value="up"),
        app_commands.Choice(name="Down", value="down")
    ])
    async def slash_flip(self, interaction: discord.Interaction, image: discord.Attachment, direction: app_commands.Choice[str]):
        await interaction.response.defer()
        await self._flip(interaction, image, direction.value)

    @commands.command(name="flip", description="Flip an image")
    async def cmd_flip(self, ctx: commands.Context, direction: str = "left"):
        image = await self._get_image_from_ctx(ctx)
        await self._flip(ctx, image, direction)

    async def _flip(self, ctx, image, direction):
        if not image or not self._is_image(image):
            return await ctx.warn("No image provided or replied to.")
        d = await image.read()
        img = await asyncio.to_thread(Image.open, io.BytesIO(d))
        fmt = img.format
        is_gif = fmt == "GIF"
        direction = (direction or "left").lower()
        if is_gif:
            frames = await asyncio.to_thread(lambda:[f.copy().convert("RGBA") for f in ImageSequence.Iterator(img)])
            durations = await asyncio.to_thread(lambda:[f.info.get("duration",100) for f in ImageSequence.Iterator(img)])
        else:
            frames = [await asyncio.to_thread(img.convert, "RGBA")]
            durations = None
        processed = []
        for f in frames:
            if direction in ("left","right","horizontal"):
                pf = await asyncio.to_thread(ImageOps.mirror, f)
            else:
                pf = await asyncio.to_thread(ImageOps.flip, f)
            processed.append(pf)
        out = io.BytesIO()
        if is_gif:
            processed[0].save(out, format="GIF", save_all=True, append_images=processed[1:], duration=durations, loop=0)
            ext = "gif"
        else:
            processed[0].save(out, format="PNG")
            ext = "png"
        out.seek(0)
        if isinstance(ctx, discord.Interaction):
            await ctx.followup.send(file=discord.File(out, f"heist.{ext}"))
        else:
            await ctx.send(file=discord.File(out, f"heist.{ext}"))

async def setup(bot):
    await bot.add_cog(Media(bot))