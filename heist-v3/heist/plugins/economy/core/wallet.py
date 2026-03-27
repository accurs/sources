import asyncio
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from heist.framework.discord.decorators import check_donor
import aiohttp, os, time
import base64

FONT_BIG_BASE = ImageFont.truetype("/root/heist-v3/heist/fonts/novus bold.otf", 70)
FONT_SMALL_BASE = ImageFont.truetype("/root/heist-v3/heist/fonts/novus regular.otf", 46)
FONT_LABEL_BASE = ImageFont.truetype("/root/heist-v3/heist/fonts/novus regular.otf", 36)
FONT_USER_BASE = ImageFont.truetype("/root/heist-v3/heist/fonts/novus regular.otf", 24)
ELLIPSES_BASE = ImageFont.truetype("/root/heist-v3/heist/fonts/gg sans medium.ttf", 44)

WALLET_ICON_BASE = Image.open("/root/heist-v3/heist/assets/cash.png").convert("RGBA")
BANK_ICON_BASE = Image.open("/root/heist-v3/heist/assets/bank.png").convert("RGBA")
STARS_ICON_BASE = Image.open("/root/heist-v3/heist/assets/stars.png").convert("RGBA")
HEIST_LOGO_BASE = Image.open("/root/heist-v3/heist/assets/heist.png").convert("RGBA")

async def generate_wallet(bot, user, money, bank):
    async with bot.pool.acquire() as conn:
        bank_limit = await conn.fetchval("SELECT bank_limit FROM economy WHERE user_id=$1", user.id) or 0
        row = await conn.fetchrow("SELECT primary_color, secondary_color FROM wallet_colors WHERE user_id=$1", user.id)

    donor = await check_donor(bot, user.id)

    redis_key = f"heist:avatar:{user.id}"
    cached = await bot.redis.get(redis_key)
    if cached:
        avatar_bytes = base64.b64decode(cached)
    else:
        async with aiohttp.ClientSession() as session:
            async with session.get(user.display_avatar.url) as resp:
                avatar_bytes = await resp.read()
        await bot.redis.set(redis_key, base64.b64encode(avatar_bytes).decode(), ex=30)

    def _generate_sync():
        scale = 2
        cwidth, cheight = 381, 249

        if row:
            start_color = row["primary_color"] or 0x0a50f0
            end_color = row["secondary_color"] or 0x3278fa
        else:
            start_color, end_color = ((0x0a50f0, 0x3278fa) if not donor else (0x0f0f0f, 0x2a2a2a))

        sr, sg, sb = (start_color >> 16) & 255, (start_color >> 8) & 255, start_color & 255
        er, eg, eb = (end_color >> 16) & 255, (end_color >> 8) & 255, end_color & 255

        w, h = int(cwidth * scale), int(cheight * scale)
        grad = Image.new("RGBA", (w, h))
        gdraw = ImageDraw.Draw(grad)

        for y in range(h):
            r = int(sr + (er - sr) * (y / h))
            g = int(sg + (eg - sg) * (y / h))
            b = int(sb + (eb - sb) * (y / h))
            gdraw.line([(0, y), (w, y)], fill=(r, g, b))

        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=int(26 * scale), fill=255)
        card = Image.composite(grad, Image.new("RGBA", (w, h)), mask)

        font_big = FONT_BIG_BASE.font_variant(size=int(35 * scale))
        font_small = FONT_SMALL_BASE.font_variant(size=int(23 * scale))
        font_label = FONT_LABEL_BASE.font_variant(size=int(18 * scale))
        font_user = FONT_USER_BASE.font_variant(size=int(12 * scale))
        ellipses_font = ELLIPSES_BASE.font_variant(size=int(22 * scale))

        draw = ImageDraw.Draw(card)

        avg_brightness = (sum([sr + sg + sb, er + eg + eb]) / 6) / 255
        light_theme = avg_brightness > 0.55
        text_color = (30, 30, 30) if light_theme else (255, 255, 255)

        draw.text((int(20 * scale), int(20 * scale)), "heist.", font=font_big, fill=text_color)

        title = "premium" if donor else "standard"
        title_w = font_small.getbbox(title)[2]
        draw.text((w - title_w - int(20 * scale), int(20 * scale)), title, font=font_small, fill=text_color)

        heist_img = HEIST_LOGO_BASE
        r, g, b, a = heist_img.split()
        adj = ImageEnhance.Brightness(Image.merge("RGB", (r, g, b))).enhance(0.6 if light_theme else 1.2)
        heist_img = Image.merge("RGBA", (*adj.split(), a))
        ratio = min((127 * scale) / heist_img.width, (97 * scale) / heist_img.height)
        heist_img = heist_img.resize((int(heist_img.width * ratio), int(heist_img.height * ratio)), Image.BILINEAR)
        card.paste(heist_img, (int(w - heist_img.width - 4 * scale), int(62 * scale)), heist_img)

        def icon(img):
            icon = img.resize((int(16 * scale), int(16 * scale)), Image.BILINEAR)
            if light_theme:
                r, g, b, a = icon.split()
                dark = ImageEnhance.Brightness(Image.merge("RGB", (r, g, b))).enhance(0.25)
                icon = Image.merge("RGBA", (*dark.split(), a))
            return icon

        wallet_icon = icon(WALLET_ICON_BASE)
        bank_icon = icon(BANK_ICON_BASE)
        stars_icon = icon(STARS_ICON_BASE)

        icon_y_offset = int(2 * scale)
        y1 = int(90 * scale + icon_y_offset)
        y2 = int(120 * scale + icon_y_offset)
        y3 = int(150 * scale + icon_y_offset)

        card.paste(wallet_icon, (int(20 * scale), y1), wallet_icon)
        draw.text((int(44 * scale), y1), f"${money:,}", font=font_label, fill=text_color)

        card.paste(bank_icon, (int(20 * scale), y2), bank_icon)
        draw.text((int(44 * scale), y2), f"${bank:,} / ${bank_limit:,}", font=font_label, fill=text_color)

        card.paste(stars_icon, (int(20 * scale), y3), stars_icon)
        draw.text((int(44 * scale), y3), "0 ⭐", font=font_label, fill=text_color)

        avatar_size = int(29 * scale)
        avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA").resize((avatar_size, avatar_size), Image.BILINEAR)
        mask_avatar = Image.new("L", (avatar_size, avatar_size), 0)
        ImageDraw.Draw(mask_avatar).ellipse((0, 0, avatar_size, avatar_size), fill=255)

        avatar_x, avatar_y = int(17 * scale), int(cheight * scale - 44 * scale)
        card.paste(avatar, (avatar_x, avatar_y), mask_avatar)

        draw.text((int(avatar_x + 38 * scale), int(avatar_y + 8 * scale)), user.name.upper(), font=font_user, fill=text_color)

        ellipses_text = ". . . ."
        ewidth = ellipses_font.getbbox(ellipses_text)[2]
        draw.text((int(w - ewidth - 27 * scale), int(cheight * scale - 47 * scale)), ellipses_text, font=ellipses_font, fill=text_color)

        card = card.resize((cwidth, cheight), Image.BILINEAR)

        buf = BytesIO()
        card.save(buf, "PNG")
        buf.seek(0)
        return buf

    return await asyncio.to_thread(_generate_sync)
