import io
import base64
import asyncio
from PIL import Image

async def makeseparator(bot, user_id: int) -> bytes:
    color_value = await bot.get_color(user_id)
    rgb = ((color_value >> 16) & 255, (color_value >> 8) & 255, color_value & 255)

    def make_bytes():
        img = Image.new("RGB", (842, 7), rgb)
        b = io.BytesIO()
        img.save(b, format="PNG")
        b.seek(0)
        return b.getvalue()

    return await asyncio.to_thread(make_bytes)

async def maketintedlogo(bot, user_id: int) -> bytes:
    color_value = await bot.get_color(user_id)
    base_key = "heist:base_logo_png"
    tinted_key = f"heist:tinted_logo_b64:{color_value}"

    cached_tinted = await bot.redis.get(tinted_key)
    if cached_tinted:
        return base64.b64decode(cached_tinted)

    cached_base = await bot.redis.get(base_key)
    if cached_base:
        base_bytes = base64.b64decode(cached_base)
    else:
        with open("/root/heist-v3/heist/assets/heist.png", "rb") as f:
            base_bytes = f.read()
        await bot.redis.set(base_key, base64.b64encode(base_bytes).decode("ascii"))

    def tint():
        img = Image.open(io.BytesIO(base_bytes)).convert("RGBA")
        r = (color_value >> 16) & 255
        g = (color_value >> 8) & 255
        b = color_value & 255
        layer = Image.new("RGBA", img.size, (r, g, b, 255))
        rb = Image.alpha_composite(Image.new("RGBA", img.size, (0, 0, 0, 0)), img)
        blended = Image.blend(rb, layer, 0.8)
        a = img.split()[3]
        final = Image.merge("RGBA", (*blended.split()[:3], a))
        b = io.BytesIO()
        final.save(b, format="PNG")
        return b.getvalue()

    png_bytes = await asyncio.to_thread(tint)
    await bot.redis.set(tinted_key, base64.b64encode(png_bytes).decode("ascii"), ex=21600)
    return png_bytes
