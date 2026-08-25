from __future__ import annotations

import asyncio
import colorsys
import io
import re

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageColor, ImageDraw


BARE_HEX = re.compile(r"[0-9a-fA-F]{6}")
RGB = re.compile(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", re.I)
_name_cache: dict[str, tuple[tuple[int, int, int], str | None]] = {}

COLOR_RECOMMENDATIONS = {
    "Black": "#000000", "White": "#FFFFFF", "Gray": "#808080",
    "Red": "#FF0000", "Crimson": "#DC143C", "Orange": "#FFA500",
    "Gold": "#FFD700", "Yellow": "#FFFF00", "Lime": "#00FF00",
    "Green": "#008000", "Emerald": "#50C878", "Teal": "#008080",
    "Cyan": "#00FFFF", "Sky Blue": "#87CEEB", "Blue": "#0000FF",
    "Navy": "#000080", "Indigo": "#4B0082", "Purple": "#800080",
    "Violet": "#8F00FF", "Magenta": "#FF00FF", "Pink": "#FFC0CB",
    "Rose": "#FF007F", "Brown": "#A52A2A", "Beige": "#F5F5DC",
    "Slate": "#708090", "Discord Blurple": "#5865F2",
    "Pastel Blue": "#A7C7E7", "Pastel Pink": "#FFD1DC",
    "Mint": "#98FF98", "Lavender": "#E6E6FA",
}


async def resolve_color(value: str) -> tuple[tuple[int, int, int], str | None]:
    cleaned = value.strip()
    cache_key = " ".join(cleaned.casefold().split())
    cached = _name_cache.get(cache_key)
    if cached is not None:
        return cached

    rgb_match = RGB.fullmatch(cleaned)
    try:
        if rgb_match:
            rgb = tuple(map(int, rgb_match.groups()))
        else:
            local_value = f"#{cleaned}" if BARE_HEX.fullmatch(cleaned) else cleaned
            try:
                rgb = ImageColor.getrgb(local_value)
            except ValueError:
                rgb = ImageColor.getrgb(re.sub(r"[\s_-]+", "", local_value))
        if len(rgb) > 3:
            rgb = rgb[:3]
        if any(not 0 <= component <= 255 for component in rgb):
            raise ValueError
        result = ((int(rgb[0]), int(rgb[1]), int(rgb[2])), None)
        _name_cache[cache_key] = result
        return result
    except (TypeError, ValueError):
        pass

    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                "https://api.color.pizza/v1/names/",
                params={"name": cleaned, "maxResults": 1, "list": "bestOf"},
            ) as response:
                response.raise_for_status()
                payload = await response.json()
        match = payload["colors"][0]
        if float(match.get("similarity", 0)) < 0.6:
            raise ValueError
        rgb = (
            int(match["rgb"]["r"]),
            int(match["rgb"]["g"]),
            int(match["rgb"]["b"]),
        )
        result = (rgb, str(match["name"]))
        _name_cache[cache_key] = result
        return result
    except (
        aiohttp.ClientError,
        asyncio.TimeoutError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
    ):
        raise ValueError(
            "I could not match that color. Use a color name, six-digit HEX, or RGB value."
        ) from None


class Colors(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_group(
        name="color",
        aliases=["hex"],
        description="Inspect colors and create color transitions",
        invoke_without_command=True,
    )
    async def color(self, ctx: commands.Context, *, query: str | None = None) -> None:
        if ctx.invoked_subcommand is not None:
            return
        if query is None:
            await ctx.send(
                "Use `/color inspect`, `/color gradient`, `;color <color>`, or "
                "`;color gradient <start> <end>`.",
                ephemeral=ctx.interaction is not None,
            )
            return
        await self._send_color(ctx, query)

    @color.command(name="inspect", description="Inspect a color and get palette recommendations")
    @app_commands.describe(query="Color name, HEX value, or RGB value")
    async def color_inspect(self, ctx: commands.Context, *, query: str) -> None:
        await self._send_color(ctx, query)

    @color_inspect.autocomplete("query")
    async def color_inspect_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        query = current.strip().casefold()
        return [
            app_commands.Choice(name=f"{name} — {hex_value}", value=hex_value)
            for name, hex_value in COLOR_RECOMMENDATIONS.items()
            if not query or query in name.casefold() or query in hex_value.casefold()
        ][:25]

    async def _send_color(self, ctx: commands.Context, query: str) -> None:
        cleaned = query.strip()
        try:
            rgb, resolved_name = await resolve_color(cleaned)
        except ValueError as error:
            await ctx.send(str(error), ephemeral=ctx.interaction is not None)
            return
        red, green, blue = rgb
        hex_value = f"#{red:02X}{green:02X}{blue:02X}"
        hue, lightness, saturation = colorsys.rgb_to_hls(red / 255, green / 255, blue / 255)
        brightness = (red * 299 + green * 587 + blue * 114) / 1000
        foreground = "Black" if brightness > 150 else "White"

        def palette_hex(h: float, light: float, saturated: float) -> str:
            values = colorsys.hls_to_rgb(
                h % 1, max(0, min(1, light)), max(0, min(1, saturated))
            )
            return "#" + "".join(f"{round(value * 255):02X}" for value in values)

        recommendations = {
            "Complementary": palette_hex(hue + 0.5, lightness, saturation),
            "Analogous": palette_hex(hue + 1 / 12, lightness, saturation),
            "Lighter": palette_hex(hue, min(0.88, lightness + 0.2), saturation),
            "Darker": palette_hex(hue, max(0.12, lightness - 0.2), saturation),
        }
        swatch = io.BytesIO()
        Image.new("RGB", (256, 144), (red, green, blue)).save(swatch, format="PNG")
        swatch.seek(0)
        filename = "color-swatch.png"
        display_title = f"{resolved_name} · {hex_value}" if resolved_name else hex_value
        details = discord.ui.Section(
            discord.ui.TextDisplay(
                f"## {display_title}\n"
                f"**RGB** · `{red}, {green}, {blue}`\n"
                f"**HSL** · `{round(hue * 360)}°, {round(saturation * 100)}%, {round(lightness * 100)}%`\n"
                f"**Brightness** · `{round(brightness)}/255`\n"
                f"**Best text color** · `{foreground}`"
            ),
            accessory=discord.ui.Thumbnail(
                f"attachment://{filename}", description=f"{hex_value} color swatch"
            ),
        )
        palette = "\n".join(
            f"**{name}** · `{value}`" for name, value in recommendations.items()
        )
        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                details,
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"### Recommended Palette\n{palette}"),
                discord.ui.Separator(),
                discord.ui.TextDisplay("-# Prefix: ;color or ;hex · Slash: /color inspect"),
            )
        )
        await ctx.send(view=view, file=discord.File(swatch, filename=filename))

    @color.command(
        name="gradient",
        aliases=["palette"],
        description="Create a custom transition between two colors",
    )
    @app_commands.describe(
        start="First color", end="Last color", amount="Number of colors (2–10)"
    )
    async def color_gradient(
        self,
        ctx: commands.Context,
        start: str,
        end: str,
        amount: app_commands.Range[int, 2, 10] = 5,
    ) -> None:
        if ctx.interaction is not None and not ctx.interaction.response.is_done():
            await ctx.defer()
        try:
            start_rgb, _ = await resolve_color(start)
            end_rgb, _ = await resolve_color(end)
        except ValueError as error:
            await ctx.send(str(error), ephemeral=ctx.interaction is not None)
            return
        colors = []
        for index in range(amount):
            ratio = index / (amount - 1)
            rgb = tuple(
                round(first + (last - first) * ratio)
                for first, last in zip(start_rgb, end_rgb)
            )
            colors.append((rgb, "#" + "".join(f"{value:02X}" for value in rgb)))
        preview = Image.new("RGB", (800, 180))
        draw = ImageDraw.Draw(preview)
        for index, (rgb, _) in enumerate(colors):
            left = round(index * 800 / amount)
            right = round((index + 1) * 800 / amount)
            draw.rectangle((left, 0, right, 180), fill=rgb)
        output = io.BytesIO()
        preview.save(output, "PNG", optimize=True)
        output.seek(0)
        filename = "color-gradient.png"
        values = "  →  ".join(f"`{hex_value}`" for _, hex_value in colors)
        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## Color Gradient\n{values}"),
                discord.ui.Separator(),
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(
                        f"attachment://{filename}",
                        description=f"{amount}-color transition",
                    )
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    "-# /color gradient · ;color gradient · ;color palette"
                ),
            )
        )
        await ctx.send(view=view, file=discord.File(output, filename=filename))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Colors(bot))
