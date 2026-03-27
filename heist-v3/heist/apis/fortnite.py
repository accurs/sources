import os
import io
import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
from fastapi import FastAPI
from fastapi.responses import FileResponse
import uvicorn
from dotenv import load_dotenv

load_dotenv("/root/heist-v3/heist/.env")
API_KEY = os.getenv("FNBR_API_KEY")

app = FastAPI()
DIR = "/root/heist-v3/temp"
PATH = f"{DIR}/fortniteshop.png"
META = f"{DIR}/fortniteshop_meta.json"

generate_lock = asyncio.Lock()

class FortniteShopItem:
    def __init__(self, name, price, icon_url, rarity):
        self.name = name
        self.price = price
        self.icon_url = icon_url
        self.rarity = rarity
        self._image_data = None

class FortniteAPI:
    def __init__(self):
        self.session = None
        self.headers = {"x-api-key": API_KEY}

    async def ensure_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def get_shop_data(self):
        await self.ensure_session()
        async with self.session.get("https://fnbr.co/api/shop", headers=self.headers) as r:
            data = await r.json()
        all_items = data["data"]["featured"] + data["data"]["daily"]
        items = []
        tasks = []
        for i in all_items:
            if not i["images"]["icon"]:
                continue
            item = FortniteShopItem(
                name=i["name"],
                price=i["price"],
                icon_url=i["images"]["icon"],
                rarity=i.get("rarity", "common"),
            )
            items.append(item)
            tasks.append(self._download_item_image(item))
        await asyncio.gather(*tasks, return_exceptions=True)
        return items, json.dumps(all_items, sort_keys=True)

    async def _download_item_image(self, item):
        await self.ensure_session()
        async with self.session.get(item.icon_url) as r:
            if r.status == 200:
                item._image_data = await r.read()

    async def generate(self):
        async with generate_lock:
            items, raw = await self.get_shop_data()
            loop = asyncio.get_event_loop()
            img = await loop.run_in_executor(None, self._render, items)
            os.makedirs(DIR, exist_ok=True)
            with open(PATH, "wb") as f:
                f.write(img)
            with open(META, "w") as f:
                f.write(raw)
            return True

    def _render(self, items):
        items_per_row = 20
        item_width = 220
        item_height = 300
        canvas_width = items_per_row * item_width
        canvas_height = ((len(items) - 1) // items_per_row + 1) * item_height
        image = Image.new("RGB", (canvas_width, canvas_height), "#2C2F33")
        draw = ImageDraw.Draw(image)
        try:
            ft = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            fp = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        except:
            ft = fp = ImageFont.load_default()
        thumb = 200
        max_width = item_width - 20

        def wrap(text, font):
            words = text.split(" ")
            lines = []
            current = ""
            for w in words:
                test = current + w + " "
                if draw.textlength(test.strip(), font=font) <= max_width:
                    current = test
                else:
                    lines.append(current.strip())
                    current = w + " "
            if current.strip():
                lines.append(current.strip())
            if len(lines) <= 2:
                return lines
            l1 = lines[0]
            l2 = lines[1]
            while draw.textlength(l2 + "...", font=font) > max_width:
                l2 = l2[:-1]
            return [l1, l2 + "..."]

        for i, item in enumerate(items):
            x = (i % items_per_row) * item_width
            y = (i // items_per_row) * item_height
            if item._image_data:
                im = Image.open(io.BytesIO(item._image_data))
                if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                    im = im.convert("RGBA")
                else:
                    im = im.convert("RGB")
                im = im.resize((thumb, thumb))
                image.paste(im, (x + 10, y + 10), im if im.mode == "RGBA" else None)
            lines = wrap(item.name, ft)
            name_text = "\n".join(lines)
            draw.multiline_text((x + 10, y + thumb + 20), name_text, font=ft, fill="white", spacing=2)
            name_height = sum(ft.getbbox(line)[3] for line in lines) + (len(lines) - 1) * 2
            price_y = y + thumb + 20 + name_height + 10
            draw.text((x + 10, price_y), f"{item.price} V-Bucks", font=fp, fill="white")

        out = io.BytesIO()
        image.save(out, format="PNG", optimize=True)
        return out.getvalue()

fort = FortniteAPI()

async def auto_refresh_shop():
    await fort.ensure_session()
    last_raw = None
    while True:
        async with fort.session.get("https://fnbr.co/api/shop", headers=fort.headers) as r:
            data = await r.json()
        new_raw = json.dumps(data["data"]["featured"] + data["data"]["daily"], sort_keys=True)
        if last_raw is None:
            if os.path.exists(META):
                last_raw = open(META).read()
            else:
                last_raw = new_raw
        if new_raw != last_raw:
            await fort.generate()
            last_raw = new_raw
        await asyncio.sleep(120)

async def midnight_refresh():
    await fort.ensure_session()
    while True:
        now = datetime.utcnow()
        next_mid = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        wait = (next_mid - now).total_seconds()
        await asyncio.sleep(wait)
        attempts = 0
        while attempts < 3:
            await fort.ensure_session()
            async with fort.session.get("https://fnbr.co/api/shop", headers=fort.headers) as r:
                data = await r.json()
            new_raw = json.dumps(data["data"]["featured"] + data["data"]["daily"], sort_keys=True)
            old_raw = open(META).read() if os.path.exists(META) else ""
            if new_raw != old_raw:
                await fort.generate()
                break
            attempts += 1
            await asyncio.sleep(10)

@app.on_event("startup")
async def startup_event():
    await fort.ensure_session()
    asyncio.create_task(auto_refresh_shop())
    asyncio.create_task(midnight_refresh())

@app.on_event("shutdown")
async def shutdown_event():
    if fort.session:
        await fort.session.close()

@app.get("/fortnite/refresh")
async def refresh():
    await fort.generate()
    return {"status": "ok"}

@app.get("/fortnite/getshop")
async def getshop():
    if not os.path.exists(PATH):
        await fort.generate()
        return FileResponse(PATH, media_type="image/png")
    await fort.ensure_session()
    async with fort.session.get("https://fnbr.co/api/shop", headers=fort.headers) as r:
        data = await r.json()
    current = json.dumps(data["data"]["featured"] + data["data"]["daily"], sort_keys=True)
    if not os.path.exists(META):
        await fort.generate()
        return FileResponse(PATH, media_type="image/png")
    old = open(META).read()
    if old != current:
        await fort.generate()
    return FileResponse(PATH, media_type="image/png")

if __name__ == "__main__":
    uvicorn.run("fortnite:app", host="0.0.0.0", port=8067)
