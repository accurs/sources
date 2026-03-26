from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import List, Literal, Optional, Union

from aiohttp import ClientSession
from discord import Color, File
from discord.ext.commands import CommandError
from pydantic import BaseModel, Field
from yarl import URL

FNBR_API = URL.build(scheme="https", host="fnbr.co", path="/api")

RARITY_COLORS = {
    "frozen": 0xC4DFF7,
    "lava": 0xD19635,
    "legendary": 0xE67E22,
    "dark": 0xFF42E7,
    "marvel": 0x761B1B,
    "dc": 0x243461,
    "star_wars": 0x081737,
    "gaming_legends": 0x312497,
    "icon_series": 0x3FB8C7,
}


class MOTD(BaseModel):
    id: str
    title: str
    body: str
    image: str

    @classmethod
    async def fetch(cls) -> List[MOTD]:
        async with ClientSession() as session:
            async with session.get(
                URL.build(scheme="https", host="fortnite-api.com", path="/v2/news/br")
            ) as response:
                data = await response.json()
                return [cls(**motd) for motd in data["data"]["motds"]]


class Map(BaseModel):
    image: str
    blank_image: str
    pois: List[str]

    async def file(self, style: Literal["blank", "pois"] = "pois") -> File:
        url = self.blank_image if style == "blank" else self.image
        async with ClientSession() as session:
            async with session.get(url) as response:
                return File(BytesIO(await response.read()), filename="map.png")

    @classmethod
    async def fetch(cls) -> Map:
        async with ClientSession() as session:
            async with session.get(
                URL.build(scheme="https", host="fortnite-api.com", path="/v1/map")
            ) as response:
                data = (await response.json())["data"]
                return cls(
                    image=data["images"]["pois"],
                    blank_image=data["images"]["blank"],
                    pois=[poi.get("name") or poi["id"] for poi in data["pois"]],
                )


class CosmeticImages(BaseModel):
    icon: Optional[str] = None
    gallery: Optional[Union[str, Literal[False]]] = None
    featured: Optional[Union[str, Literal[False]]] = None
    resize_available: Optional[bool] = Field(False, alias="resizeAvailable")

    model_config = {"populate_by_name": True}


class CosmeticHistory(BaseModel):
    occurrences: int
    first_seen: datetime = Field(alias="firstSeen")
    last_seen: datetime = Field(alias="lastSeen")
    dates: List[datetime]

    model_config = {"populate_by_name": True}


class Cosmetic(BaseModel):
    id: str
    name: str
    description: Union[str, Literal[False]]
    type: str
    rarity: str
    price: str
    images: CosmeticImages
    history: Union[Literal[False], CosmeticHistory]
    price_icon: Union[Literal[False], str] = Field(alias="priceIcon")
    price_icon_url: Optional[Union[str, Literal[False]]] = Field(alias="priceIconLink")

    model_config = {"populate_by_name": True}

    def __str__(self) -> str:
        return f"[**{self.name}**]({self.url}) ({self.pretty_type})"

    def is_lego(self) -> bool:
        return self.type.startswith("lego")

    @property
    def url(self) -> str:
        return f"https://fnbr.co/cosmetics/{self.id}"

    @property
    def pretty_type(self) -> str:
        return self.type.replace("_", " ").title()

    @property
    def color(self) -> Color:
        try:
            return Color(RARITY_COLORS[self.rarity])
        except KeyError:
            return Color.dark_embed()

    @classmethod
    async def convert(cls, ctx, argument: str) -> Cosmetic:
        if ctx.command and ctx.command.name == "equip":
            data = await cls.fetch_fnapi(argument)
        else:
            data = await cls.fetch_fnbr(argument)
        if not data:
            raise CommandError(f"No cosmetics were found for `{argument}`")
        return data[0]

    @classmethod
    async def fetch_fnbr(cls, argument: str, api_key: str = "") -> List[Cosmetic]:
        async with ClientSession() as session:
            headers = {"x-api-key": api_key} if api_key else {}
            async with session.get(
                FNBR_API / "images",
                params={"search": argument, "limit": 5},
                headers=headers,
            ) as response:
                data = (await response.json()).get("data", [])
                return [c for c in [cls(**item) for item in data] if not c.is_lego()]

    @classmethod
    async def fetch_fnapi(cls, argument: str) -> List[Cosmetic]:
        argument = argument.replace("purple", "").replace("pink", "").strip()
        async with ClientSession() as session:
            async with session.get(
                URL.build(scheme="https", host="fortnite-api.com", path="/v2/cosmetics/br/search"),
                params={"name": argument},
            ) as response:
                data = await response.json()
                if data.get("status") != 200:
                    return []
                item = data["data"]
                return [cls(
                    id=item["id"],
                    name=item["name"],
                    description=item.get("description", ""),
                    type=item["type"]["displayValue"],
                    rarity=item["rarity"]["value"],
                    price="",
                    images=CosmeticImages(
                        icon=item["images"]["icon"],
                        gallery=False,
                        featured=False,
                        resizeAvailable=False,
                    ),
                    history=False,
                    priceIcon=False,
                    priceIconLink=False,
                )]


class Shop(BaseModel):
    date: datetime
    cosmetics: List[Cosmetic]
    cosmetic_ids: List[str]

    @classmethod
    async def fetch(cls, api_key: str = "") -> Shop:
        async with ClientSession() as session:
            headers = {"x-api-key": api_key} if api_key else {}
            async with session.get(FNBR_API / "shop", headers=headers) as response:
                if not response.ok:
                    raise ValueError(f"Fortnite API returned {response.status}")
                data = (await response.json())["data"]
                return cls(
                    date=data["date"],
                    cosmetics=data["featured"] + data["daily"],
                    cosmetic_ids=[
                        item_id
                        for section in data["sections"]
                        for item_id in section["items"]
                    ],
                )
