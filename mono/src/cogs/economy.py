from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import io
import random
import re
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from functools import lru_cache
from pathlib import Path
from urllib.parse import urljoin, urlparse

import aiohttp
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFont, ImageOps, ImageSequence
import imageio_ffmpeg

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.services.economy import (
    BankCapacityError,
    EconomyError,
    InsufficientFunds,
    deposit_fee,
    store,
)
from src.services.colors import resolve_color


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BALANCE_BACKGROUNDS = PROJECT_ROOT / ".cache" / "balance_backgrounds"
BALANCE_CARD_CACHE = PROJECT_ROOT / ".cache" / "balance_cards"
CARD_SIZE = (1200, 500)
CARD_RENDER_VERSION = 2
MAX_BACKGROUND_BYTES = 25 * 1024 * 1024
HEX_COLOR = re.compile(r"^#?[0-9a-fA-F]{6}$")
AVATAR_SHAPES = {"circle", "rounded", "square", "hidden"}
GRADIENT_DIRECTIONS = {
    "top", "bottom", "left", "right",
    "top-left", "top-right", "bottom-left", "bottom-right",
}


def normalize_color(value: str) -> str:
    value = value.strip()
    if not HEX_COLOR.fullmatch(value):
        raise ValueError("Use a six-digit hex color such as `#38BDF8`.")
    return "#" + value.lstrip("#").upper()


@lru_cache(maxsize=16)
def balance_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(filename, size)
    except OSError:
        return ImageFont.load_default(size=size)


def _gradient(
    size: tuple[int, int],
    start: str,
    end: str | None,
    direction: str = "top",
) -> Image.Image:
    image = Image.new("RGB", size, start)
    if not end:
        return image
    start_rgb, end_rgb = ImageColor.getrgb(start), ImageColor.getrgb(end)
    width, height = size
    direction = direction if direction in GRADIENT_DIRECTIONS else "top"
    mask = bytearray(width * height)
    for y in range(height):
        vertical = y / max(1, height - 1)
        for x in range(width):
            horizontal = x / max(1, width - 1)
            ratio = {
                "top": vertical,
                "bottom": 1 - vertical,
                "left": horizontal,
                "right": 1 - horizontal,
                "top-left": (horizontal + vertical) / 2,
                "top-right": ((1 - horizontal) + vertical) / 2,
                "bottom-left": (horizontal + (1 - vertical)) / 2,
                "bottom-right": ((1 - horizontal) + (1 - vertical)) / 2,
            }[direction]
            mask[y * width + x] = round(ratio * 255)
    return ImageOps.colorize(Image.frombytes("L", size, bytes(mask)), start_rgb, end_rgb)


def _prepare_card_avatar(
    avatar_bytes: bytes | None,
    decoration_bytes: bytes | None,
    shape: str,
) -> Image.Image | None:
    if not avatar_bytes or shape == "hidden":
        return None
    with Image.open(io.BytesIO(avatar_bytes)) as avatar_source:
        avatar = ImageOps.fit(
            avatar_source.convert("RGBA"), (82, 82), Image.Resampling.LANCZOS
        )
    mask = Image.new("L", avatar.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    if shape == "circle":
        mask_draw.ellipse((0, 0, 81, 81), fill=255)
    elif shape == "rounded":
        mask_draw.rounded_rectangle((0, 0, 81, 81), radius=15, fill=255)
    else:
        mask_draw.rectangle((0, 0, 81, 81), fill=255)
    mask = ImageChops.multiply(mask, avatar.getchannel("A"))
    avatar.putalpha(mask)
    if not decoration_bytes:
        return avatar
    with Image.open(io.BytesIO(decoration_bytes)) as decoration_source:
        decoration_source.seek(0)
        decoration = decoration_source.convert("RGBA").resize(
            (100, 100), Image.Resampling.LANCZOS
        )
    decorated_avatar = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    decorated_avatar.alpha_composite(avatar, (9, 9))
    decorated_avatar.alpha_composite(decoration)
    return decorated_avatar


def _decorate_balance_frame(
    image: Image.Image,
    display_name: str,
    account,
    ranks: dict[str, int],
    settings: dict,
    avatar: Image.Image | None,
) -> Image.Image:
    overlay_opacity = max(0, min(90, int(settings.get("fade", 45))))
    if overlay_opacity:
        overlay = Image.new(
            "RGBA",
            CARD_SIZE,
            (0, 0, 0, round(255 * overlay_opacity / 100)),
        )
        image = Image.alpha_composite(image.convert("RGBA"), overlay)
    else:
        image = image.convert("RGBA")

    draw = ImageDraw.Draw(image)
    text = settings["text_color"]
    bank_fill = (*ImageColor.getrgb(text), 235)
    shape = settings["avatar_shape"]
    content_left = 75
    name = display_name[:32]
    name_font = balance_font(60, bold=True)
    draw.text((content_left, 58), name, fill=text, font=name_font)
    if shape != "hidden" and avatar is not None:
        name_right = draw.textbbox((content_left, 58), name, font=name_font)[2]
        decoration_padding = max(0, (avatar.width - 82) // 2)
        avatar_x = min(name_right + 24, CARD_SIZE[0] - 82 - 75)
        image.alpha_composite(
            avatar,
            (avatar_x - decoration_padding, 56 - decoration_padding),
        )

    wallet_hidden = bool(settings.get("wallet_hidden"))
    wallet = "REDACTED" if wallet_hidden else f"{account.wallet:,}"
    net = "REDACTED" if wallet_hidden else f"{account.net:,}"
    wallet_label = "WALLET" if wallet_hidden else f"WALLET #{ranks['wallet']:,}"
    net_label = "NET WORTH" if wallet_hidden else f"NET WORTH #{ranks['net']:,}"
    draw.text((content_left, 165), wallet_label, fill=text, font=balance_font(26, bold=True))
    draw.text((content_left, 202), wallet, fill=text, font=balance_font(46, bold=True))
    draw.text((content_left + 320, 165), f"BANK #{ranks['bank']:,}", fill=text, font=balance_font(26, bold=True))
    draw.text((content_left + 320, 202), f"{account.bank:,}", fill=text, font=balance_font(46, bold=True))
    draw.text((content_left + 640, 165), net_label, fill=text, font=balance_font(26, bold=True))
    draw.text((content_left + 640, 202), net, fill=text, font=balance_font(46, bold=True))

    bar_width = min(950, CARD_SIZE[0] - content_left - 75)
    ratio = min(1.0, account.bank / max(1, account.bank_capacity))
    bar_track = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(bar_track).rounded_rectangle(
        (content_left, 310, content_left + bar_width, 342),
        radius=16,
        fill=(255, 255, 255, 55),
    )
    image = Image.alpha_composite(image, bar_track)
    draw = ImageDraw.Draw(image)
    if ratio:
        fill_width = max(1, round(bar_width * ratio))
        draw.rounded_rectangle(
            (content_left, 310, content_left + fill_width, 342),
            radius=min(16, fill_width // 2),
            fill=bank_fill,
        )
    draw.text((content_left, 356), f"Bank capacity  {account.bank:,} / {account.bank_capacity:,}", fill=text, font=balance_font(24))

    message = str(settings.get("message") or "")[:100]
    if message:
        draw.text((content_left, 423), message, fill=text, font=balance_font(30))
    return image


def render_balance_card(
    display_name: str,
    account,
    ranks: dict[str, int],
    settings: dict,
    avatar_bytes: bytes | None,
    decoration_bytes: bytes | None,
) -> bytes:
    avatar = _prepare_card_avatar(
        avatar_bytes,
        decoration_bytes,
        settings["avatar_shape"],
    )
    background_path = settings.get("background_path")
    if background_path and Path(background_path).is_file():
        with Image.open(background_path) as source:
            animated = bool(getattr(source, "is_animated", False) and source.n_frames > 1)
            if animated:
                frames: list[Image.Image] = []
                durations: list[int] = []
                # Keep animated cards responsive and within Discord's upload limits.
                stride = max(1, (source.n_frames + 39) // 40)
                for index, frame in enumerate(ImageSequence.Iterator(source)):
                    if index % stride:
                        continue
                    resized = frame.convert("RGB").resize(CARD_SIZE, Image.Resampling.LANCZOS)
                    decorated = _decorate_balance_frame(
                        resized, display_name, account, ranks, settings, avatar
                    )
                    frames.append(
                        decorated.convert("P", palette=Image.Palette.ADAPTIVE, colors=64)
                    )
                    durations.append(
                        max(40, int(frame.info.get("duration", source.info.get("duration", 100))) * stride)
                    )
                output = io.BytesIO()
                frames[0].save(
                    output,
                    "GIF",
                    save_all=True,
                    append_images=frames[1:],
                    duration=durations,
                    loop=int(source.info.get("loop", 0)),
                    disposal=2,
                    optimize=True,
                )
                return output.getvalue()
            image = source.convert("RGB").resize(CARD_SIZE, Image.Resampling.LANCZOS)
    else:
        image = _gradient(
            CARD_SIZE,
            settings["background_color"],
            settings.get("gradient_color"),
            settings.get("gradient_direction", "top"),
        )
    image = _decorate_balance_frame(
        image, display_name, account, ranks, settings, avatar
    )
    output = io.BytesIO()
    image.convert("RGB").save(output, "PNG", optimize=True)
    return output.getvalue()


def _persistent_card_stem(user_id: int, key: tuple) -> Path:
    digest = hashlib.sha256(repr(key).encode("utf-8")).hexdigest()[:24]
    return BALANCE_CARD_CACHE / f"{user_id}-{digest}"


def _read_persistent_card(user_id: int, key: tuple) -> bytes | None:
    stem = _persistent_card_stem(user_id, key)
    for suffix, signature in ((".png", b"\x89PNG"), (".gif", b"GIF")):
        path = stem.with_suffix(suffix)
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if data.startswith(signature):
            return data
    return None


def _write_persistent_card(user_id: int, key: tuple, data: bytes) -> None:
    BALANCE_CARD_CACHE.mkdir(parents=True, exist_ok=True)
    suffix = ".gif" if data.startswith(b"GIF") else ".png"
    destination = _persistent_card_stem(user_id, key).with_suffix(suffix)
    destination.write_bytes(data)
    for old_path in BALANCE_CARD_CACHE.glob(f"{user_id}-*"):
        if old_path != destination:
            try:
                old_path.unlink()
            except OSError:
                pass


def prepare_balance_background(
    raw: bytes,
    user_id: int,
    filename: str = "",
    content_type: str = "",
) -> Path:
    """Resize and recompress a static or animated card background."""
    BALANCE_BACKGROUNDS.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix.casefold()
    is_video = content_type.casefold().startswith("video/") or suffix in {
        ".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi",
    }
    if is_video:
        with tempfile.TemporaryDirectory(prefix="balance-video-") as directory:
            source_path = Path(directory) / f"source{suffix or '.mp4'}"
            gif_path = Path(directory) / "converted.gif"
            source_path.write_bytes(raw)
            subprocess.run(
                [
                    imageio_ffmpeg.get_ffmpeg_exe(),
                    "-loglevel", "error",
                    "-i", str(source_path),
                    "-t", "8",
                    "-vf", "fps=8,scale=1200:500:flags=lanczos",
                    "-loop", "0",
                    str(gif_path),
                ],
                check=True,
                capture_output=True,
            )
            raw = gif_path.read_bytes()
    with Image.open(io.BytesIO(raw)) as source:
        animated = bool(
            source.format == "GIF"
            and getattr(source, "is_animated", False)
            and source.n_frames > 1
        )
        if animated:
            destination = BALANCE_BACKGROUNDS / f"{user_id}.gif"
            frames: list[Image.Image] = []
            durations: list[int] = []
            stride = max(1, (source.n_frames + 39) // 40)
            for index, frame in enumerate(ImageSequence.Iterator(source)):
                if index % stride:
                    continue
                resized = frame.convert("RGB").resize(CARD_SIZE, Image.Resampling.LANCZOS)
                frames.append(
                    resized.convert("P", palette=Image.Palette.ADAPTIVE, colors=64)
                )
                durations.append(
                    max(40, int(frame.info.get("duration", source.info.get("duration", 100))) * stride)
                )
            frames[0].save(
                destination,
                "GIF",
                save_all=True,
                append_images=frames[1:],
                duration=durations,
                loop=int(source.info.get("loop", 0)),
                disposal=2,
                optimize=True,
            )
            return destination
        destination = BALANCE_BACKGROUNDS / f"{user_id}.jpg"
        prepared = source.convert("RGB").resize(CARD_SIZE, Image.Resampling.LANCZOS)
        prepared.save(destination, "JPEG", quality=84, optimize=True, progressive=True)
        return destination


async def download_balance_background(url: str) -> tuple[bytes, str, str]:
    current_url = url.strip()
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(
        timeout=timeout,
        headers={"User-Agent": "Sorrowing Balance Card/1.0"},
    ) as session:
        for redirect_count in range(4):
            parsed = urlparse(current_url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("Use a complete HTTP or HTTPS media URL.")
            if parsed.username or parsed.password:
                raise ValueError("Media URLs cannot contain login information.")
            try:
                addresses = await asyncio.to_thread(
                    socket.getaddrinfo,
                    parsed.hostname,
                    parsed.port or (443 if parsed.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
            except socket.gaierror as error:
                raise ValueError("I could not find that media host.") from error
            if not addresses or any(
                not ipaddress.ip_address(address[4][0]).is_global
                for address in addresses
            ):
                raise ValueError("That media host is not publicly accessible.")
            async with session.get(current_url, allow_redirects=False) as response:
                if 300 <= response.status < 400:
                    location = response.headers.get("Location")
                    if not location or redirect_count == 3:
                        raise ValueError("That media URL redirects too many times.")
                    current_url = urljoin(current_url, location)
                    continue
                if response.status != 200:
                    raise ValueError(
                        f"The media server returned HTTP {response.status}."
                    )
                content_type = response.headers.get("Content-Type", "")
                if not content_type.casefold().startswith(("image/", "video/")):
                    raise ValueError(
                        "That URL must point directly to an image, GIF, or video."
                    )
                if (
                    response.content_length is not None
                    and response.content_length > MAX_BACKGROUND_BYTES
                ):
                    raise ValueError("The source media must be 25 MB or smaller.")
                data = bytearray()
                async for chunk in response.content.iter_chunked(64 * 1024):
                    data.extend(chunk)
                    if len(data) > MAX_BACKGROUND_BYTES:
                        raise ValueError("The source media must be 25 MB or smaller.")
                filename = Path(urlparse(current_url).path).name or "background"
                return bytes(data), filename, content_type
    raise ValueError("I could not download that media URL.")


def money(amount: int) -> str:
    return f"{amount:,}"


def money_code(amount: int) -> str:
    return f"`{money(amount)}`"


def number_code(value: int, suffix: str = "") -> str:
    return f"`{value:,}{suffix}`"


def duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours: parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    if secs or not parts: parts.append(f"{secs}s")
    return " ".join(parts)


def card(title: str, body: str) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(discord.ui.TextDisplay(f"## {title}\n{body}")))
    return view


def structured_card(
    title: str,
    sections: list[tuple[str, str]],
    *,
    note: str | None = None,
) -> discord.ui.LayoutView:
    items: list[discord.ui.Item] = [discord.ui.TextDisplay(f"## {title}")]
    for heading, body in sections:
        items.extend(
            (
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"### {heading}\n{body}"),
            )
        )
    if note:
        items.extend((discord.ui.Separator(), discord.ui.TextDisplay(f"-# {note}")))
    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(*items))
    return view


def account_section(account) -> str:
    return (
        f"**Wallet:** {money_code(account.wallet)}\n"
        f"**Bank:** {money_code(account.bank)}\n"
        f"**Bank capacity:** {money_code(account.bank_capacity)}\n"
        f"**Net worth:** {money_code(account.net)}"
    )


def parse_amount(value: str, available: int) -> int:
    cleaned = (
        value.strip().lower().replace(",", "").replace("_", "").replace(" ", "")
    )
    if cleaned.startswith("$"):
        cleaned = cleaned[1:]
    if cleaned in {"all", "max"}:
        return available
    if cleaned.endswith("%"):
        try:
            percent = Decimal(cleaned[:-1])
        except InvalidOperation as error:
            raise ValueError from error
        if percent <= 0 or percent > 100:
            raise ValueError
        amount = int(
            (Decimal(available) * percent / Decimal(100)).to_integral_value(
                rounding=ROUND_DOWN
            )
        )
    else:
        match = re.fullmatch(r"(\d+(?:\.\d+)?)([kmbt]?)", cleaned)
        if match is None:
            raise ValueError
        multiplier = {
            "": Decimal(1),
            "k": Decimal(1_000),
            "m": Decimal(1_000_000),
            "b": Decimal(1_000_000_000),
            "t": Decimal(1_000_000_000_000),
        }[match.group(2)]
        amount = int(
            (Decimal(match.group(1)) * multiplier).to_integral_value(
                rounding=ROUND_DOWN
            )
        )
    if amount <= 0:
        raise ValueError
    return amount


def parse_giveaway_duration(value: str) -> int:
    cleaned = value.strip().lower().replace(" ", "")
    matches = re.findall(r"(\d+)([smhdw])", cleaned)
    if not matches or "".join(f"{number}{unit}" for number, unit in matches) != cleaned:
        raise ValueError
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86_400, "w": 604_800}
    seconds = sum(int(number) * multipliers[unit] for number, unit in matches)
    if not 10 <= seconds <= 30 * 86_400:
        raise ValueError
    return seconds


def transaction_detail(row) -> str:
    action = str(row["action"])
    amount = int(row["amount"])
    other = f" <@{int(row['other_user_id'])}>" if row["other_user_id"] else ""
    actor = f" by <@{int(row['actor_id'])}>" if row["actor_id"] else ""
    labels = {
        "daily": "Daily reward",
        "work": "Work payment",
        "deposit": "Bank deposit",
        "deposit_fee": "Deposit fee",
        "withdraw": "Bank withdrawal",
        "bank_upgrade": "Bank capacity upgrade",
        "admin_add": "Money added by an economy admin",
        "admin_take": "Money removed by an economy admin",
        "admin_reset": "Balance reset by an economy admin",
        "robbery": "Stolen from" + other,
        "robbed": "Stolen by" + other,
        "robbery_fine": "Failed robbery fine involving" + other,
        "giveaway_reserve": "Reserved for an economy giveaway",
        "giveaway_refund": "Refunded from an economy giveaway",
        "giveaway_prize": "Economy giveaway prize from" + other,
    }
    if action == "transfer":
        label = ("Received from" if amount > 0 else "Sent to") + other
    else:
        label = labels.get(action, action.replace("_", " ").title()) + actor
    reason = str(row["reason"]).strip() if row["reason"] else ""
    if reason:
        label += f" — {discord.utils.escape_markdown(reason)}"
    location = str(row["balance_type"]).replace("_", " ").title()
    return f"{label}\n-# {location} · <t:{int(row['created_at'])}:F> · <t:{int(row['created_at'])}:R>"


class TransactionPaginator(discord.ui.LayoutView):
    navigation = discord.ui.ActionRow()

    def __init__(
        self,
        *,
        author_id: int,
        title: str,
        account: str,
        movement: str,
        transaction_pages: list[str],
        total: int,
    ) -> None:
        super().__init__(timeout=180)
        self.author_id = author_id
        self.title = title
        self.account = account
        self.movement = movement
        self.transaction_pages = transaction_pages
        self.total = total
        self.current_page = 0
        self.message: discord.Message | None = None
        self.render_page()

    def render_page(self) -> None:
        self.clear_items()
        self.previous.disabled = self.current_page == 0
        self.next.disabled = self.current_page == len(self.transaction_pages) - 1
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## {self.title}"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"### Current Account\n{self.account}"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"### Seven-Day Movement\n{self.movement}"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"### Recent Transactions\n{self.transaction_pages[self.current_page]}"
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"-# Page {self.current_page + 1} of {len(self.transaction_pages)} · "
                    f"Showing `{self.total}` most recent record(s) retained for seven days."
                ),
                self.navigation,
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This transaction history belongs to someone else.", ephemeral=True
        )
        return False

    async def on_timeout(self) -> None:
        self.previous.disabled = True
        self.next.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @navigation.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.current_page -= 1
        self.render_page()
        await interaction.response.edit_message(view=self)

    @navigation.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.current_page += 1
        self.render_page()
        await interaction.response.edit_message(view=self)


@dataclass(frozen=True, slots=True)
class Job:
    name: str
    description: str
    difficulty: str
    sequence_length: int
    pay: int


JOBS = (
    Job("Barista", "Remember a customer's exact order", "Easy", 3, 4_000),
    Job("Dog Walker", "Keep track of every dog's route", "Easy", 3, 4_000),
    Job("Delivery Driver", "Memorize the delivery route", "Medium", 4, 6_000),
    Job("Freelance Designer", "Recall the client's design brief", "Medium", 4, 6_000),
    Job("Mechanic", "Remember the repair sequence", "Medium", 4, 6_000),
    Job("Private Chef", "Follow a precise recipe from memory", "Hard", 5, 9_000),
    Job("Stunt Performer", "Memorize the stunt choreography", "Hard", 5, 9_000),
    Job("Treasure Diver", "Recall the safe route through the wreck", "Hard", 5, 9_000),
)

WORK_SYMBOLS = ("A", "B", "C", "D")


class WorkButton(discord.ui.Button):
    def __init__(self, job: Job) -> None:
        super().__init__(label=job.name, style=discord.ButtonStyle.primary)
        self.job = job

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, WorkView)
        await view.choose(interaction, self.job)


class WorkView(discord.ui.LayoutView):
    def __init__(self, user_id: int, jobs: list[Job]) -> None:
        super().__init__(timeout=90)
        self.user_id = user_id
        self.finished = False
        items: list[discord.ui.Item] = [discord.ui.TextDisplay("## Choose a Job")]
        for job in jobs:
            items.extend((
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"### {job.name}\n"
                    f"{job.description}\n\n"
                    f"**Difficulty:** `{job.difficulty}`\n"
                    f"**Memory sequence:** {number_code(job.sequence_length, ' symbols')}\n"
                    f"**Base pay:** {money_code(job.pay)}"
                ),
            ))
        items.extend((
            discord.ui.Separator(),
            discord.ui.ActionRow(*(WorkButton(job) for job in jobs)),
        ))
        self.add_item(discord.ui.Container(*items))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message("This job menu belongs to someone else.", ephemeral=True)
        return False

    async def choose(self, interaction: discord.Interaction, job: Job) -> None:
        if self.finished:
            await interaction.response.send_message("This job has already been completed.", ephemeral=True)
            return
        self.finished = True
        sequence = tuple(random.choice(WORK_SYMBOLS) for _ in range(job.sequence_length))
        await interaction.response.edit_message(
            view=card(
                f"{job.name} — Memorize This",
                f"# {'  '.join(sequence)}\n\n-# This disappears in `4 seconds`.",
            )
        )
        await asyncio.sleep(4)
        await interaction.edit_original_response(
            view=WorkSkillView(self.user_id, job, sequence)
        )
        self.stop()


class WorkSymbolButton(discord.ui.Button):
    def __init__(self, symbol: str) -> None:
        super().__init__(label=symbol, style=discord.ButtonStyle.primary)
        self.symbol = symbol

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, WorkSkillView)
        await view.enter(interaction, self.symbol)


class WorkSkillView(discord.ui.LayoutView):
    def __init__(self, user_id: int, job: Job, sequence: tuple[str, ...]) -> None:
        super().__init__(timeout=60)
        self.user_id = user_id
        self.job = job
        self.sequence = sequence
        self.entered: list[str] = []
        self.finished = False
        self.render()

    def render(self) -> None:
        self.clear_items()
        progress = " ".join(self.entered + ["•"] * (len(self.sequence) - len(self.entered)))
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"## {self.job.name} — Skill Check\n"
                    f"Enter the {number_code(len(self.sequence), '-symbol')} sequence in order.\n\n"
                    f"# {progress}"
                ),
                discord.ui.ActionRow(*(WorkSymbolButton(symbol) for symbol in WORK_SYMBOLS)),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message("This skill check belongs to someone else.", ephemeral=True)
        return False

    async def enter(self, interaction: discord.Interaction, symbol: str) -> None:
        if self.finished:
            return
        self.entered.append(symbol)
        if len(self.entered) < len(self.sequence):
            self.render()
            await interaction.response.edit_message(view=self)
            return

        self.finished = True
        success = tuple(self.entered) == self.sequence
        try:
            account, reward = await asyncio.to_thread(
                store.complete_work,
                self.user_id,
                success=success,
                base_pay=self.job.pay,
                job=self.job.name,
            )
        except EconomyError as error:
            await interaction.response.edit_message(
                view=structured_card(
                    "Work Cooldown",
                    [("Available Again", f"`{duration(int(str(error)))}`")],
                )
            )
            self.stop()
            return

        if success:
            title = "Shift Complete"
            result_view = structured_card(title, [
                ("Result", f"Correct sequence: `{' '.join(self.sequence)}`"),
                ("Payment", f"You earned {money_code(reward)} as a **{self.job.name}**."),
                ("Current Streak", number_code(account.work_streak, " successful shift(s)")),
            ])
        else:
            title = "Skill Check Failed"
            result_view = structured_card(title, [
                ("Sequence", f"**Entered:** `{' '.join(self.entered)}`\n**Correct:** `{' '.join(self.sequence)}`"),
                ("Payment", money_code(0)),
                ("Current Streak", number_code(account.work_streak, " successful shift(s)")),
            ])
        await interaction.response.edit_message(view=result_view)
        self.stop()


class RobButton(discord.ui.Button):
    def __init__(self, position: int) -> None:
        super().__init__(label="?", style=discord.ButtonStyle.secondary, row=position // 5)
        self.position = position

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, RobView)
        await view.reveal(interaction, self.position)


class RobView(discord.ui.View):
    def __init__(self, robber: discord.abc.User, target: discord.abc.User) -> None:
        super().__init__(timeout=60)
        self.robber = robber
        self.target = target
        self.done = False
        # Low rewards deliberately appear more often than high rewards.
        values = [2, 2, 3, 3, 4, 4, 5, 5, 6, 8, 10, 12, 15, 20, 25, 30, 3, 5, 8, 10]
        random.shuffle(values)
        self.values = values
        for index in range(20):
            self.add_item(RobButton(index))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.robber.id:
            return True
        await interaction.response.send_message("This robbery belongs to someone else.", ephemeral=True)
        return False

    async def reveal(self, interaction: discord.Interaction, position: int) -> None:
        if self.done:
            return
        self.done = True
        failed = random.random() < .15
        percentage = self.values[position]
        try:
            result, robber_account, _ = await asyncio.to_thread(
                store.finish_robbery, self.robber.id, self.target.id, percentage, failed
            )
        except (EconomyError, InsufficientFunds):
            await interaction.response.edit_message(
                content="The robbery can no longer be completed.", view=None
            )
            self.stop(); return
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
                if isinstance(item, RobButton) and item.position == position:
                    item.label = f"{percentage}%"
                    item.style = discord.ButtonStyle.danger if failed else discord.ButtonStyle.success
        if failed:
            content = (
                "## Robbery Failed\n"
                f"{self.robber.mention} was caught trying to rob {self.target.mention}.\n\n"
                f"**Fine paid:** {money_code(abs(result))}\n"
                f"**Wallet remaining:** {money_code(robber_account.wallet)}"
            )
        else:
            content = (
                "## Robbery Successful\n"
                f"**Target:** {self.target.mention}\n"
                f"**Tile selected:** {number_code(percentage, '%')}\n"
                f"**Amount stolen:** {money_code(result)}\n\n"
                f"**Wallet after robbery:** {money_code(robber_account.wallet)}"
            )
        await interaction.response.edit_message(content=content, view=self)
        self.stop()


def giveaway_view(
    cog: "Economy",
    row,
    entries: int,
) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay(
                "## Economy Giveaway\n"
                f"**Prize pool:** {money_code(int(row['amount']))}\n"
                f"**Winners:** {number_code(int(row['winner_count']))}\n"
                f"**Hosted by:** <@{int(row['host_id'])}>\n"
                f"**Ends:** <t:{int(row['ends_at'])}:R>\n"
                f"**Entries:** {number_code(entries)}"
            ),
            discord.ui.Separator(),
            discord.ui.ActionRow(GiveawayEnterButton(cog, int(row["id"]))),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "-# The full prize is already reserved from the host's wallet."
            ),
        )
    )
    return view


class GiveawayEnterButton(discord.ui.Button):
    def __init__(self, cog: "Economy", giveaway_id: int) -> None:
        super().__init__(
            label="Enter Giveaway",
            style=discord.ButtonStyle.success,
            custom_id=f"economy:giveaway:enter:{giveaway_id}",
        )
        self.cog = cog
        self.giveaway_id = giveaway_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.bot:
            await interaction.response.send_message(
                "Bots cannot enter giveaways.", ephemeral=True
            )
            return
        try:
            added, entries = await asyncio.to_thread(
                store.enter_giveaway, self.giveaway_id, interaction.user.id
            )
        except EconomyError as error:
            message = (
                "You cannot enter your own giveaway."
                if str(error) == "host"
                else "This giveaway has already ended."
            )
            await interaction.response.send_message(message, ephemeral=True)
            return
        if not added:
            await interaction.response.send_message(
                "You are already entered in this giveaway.", ephemeral=True
            )
            return
        row = await asyncio.to_thread(store.giveaway, self.giveaway_id)
        if row is None:
            await interaction.response.send_message(
                "This giveaway is no longer available.", ephemeral=True
            )
            return
        await interaction.response.edit_message(view=giveaway_view(self.cog, row, entries))


class DepositChoiceButton(discord.ui.Button):
    def __init__(self, accept: bool) -> None:
        super().__init__(
            label="Accept" if accept else "Cancel",
            style=(
                discord.ButtonStyle.success
                if accept
                else discord.ButtonStyle.secondary
            ),
        )
        self.accept = accept

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if isinstance(view, DepositConfirmView):
            await view.choose(interaction, self.accept)


class DepositConfirmView(discord.ui.LayoutView):
    def __init__(self, author_id: int, amount: int, wallet_balance: int) -> None:
        super().__init__(timeout=60)
        self.author_id = author_id
        self.amount = amount
        self.wallet_balance = wallet_balance
        self.message: discord.Message | None = None
        self.finished = False
        self.render()

    def render(self, result: str | None = None) -> None:
        self.clear_items()
        if result is not None:
            self.add_item(discord.ui.Container(discord.ui.TextDisplay(result)))
            return
        fee = deposit_fee(self.amount)
        selected_percent = self.amount / max(1, self.wallet_balance) * 100
        percent_text = f"{selected_percent:.2f}".rstrip("0").rstrip(".")
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Confirm Deposit\n"
                    f"**Selected:** {money_code(self.amount)} ({percent_text}% of your wallet)\n"
                    f"**Fee charged:** 5% = {money_code(fee)}\n"
                    f"**Bank receives:** 95% = {money_code(self.amount - fee)}"
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    "-# Deposits permanently lose 5% of the selected amount."
                ),
                discord.ui.ActionRow(
                    DepositChoiceButton(True), DepositChoiceButton(False)
                ),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "Only the person making this deposit can use these buttons.",
            ephemeral=True,
        )
        return False

    async def choose(self, interaction: discord.Interaction, accept: bool) -> None:
        if self.finished:
            await interaction.response.send_message(
                "This deposit confirmation is no longer active.", ephemeral=True
            )
            return
        self.finished = True
        self.stop()
        if not accept:
            self.render("## Deposit Cancelled\nNo money was moved.")
            await interaction.response.edit_message(view=self)
            return
        await interaction.response.defer()
        try:
            updated, fee = await asyncio.to_thread(
                store.deposit, self.author_id, self.amount
            )
        except InsufficientFunds:
            result = "## Deposit Failed\nYou no longer have enough wallet money."
        except BankCapacityError:
            result = (
                "## Deposit Failed\nThat deposit would now exceed your bank capacity."
            )
        except ValueError:
            result = "## Deposit Failed\nThe amount is too small after the 5% fee."
        else:
            result = (
                "## Deposit Complete\n"
                f"**Taken from wallet:** {money_code(self.amount)}\n"
                f"**5% fee:** {money_code(fee)}\n"
                f"**Added to bank:** {money_code(self.amount - fee)}\n"
                f"**Bank:** {money_code(updated.bank)} / {money_code(updated.bank_capacity)}\n"
                f"**Wallet remaining:** {money_code(updated.wallet)}"
            )
        self.render(result)
        await interaction.edit_original_response(view=self)

    async def on_timeout(self) -> None:
        if self.finished:
            return
        self.finished = True
        self.render("## Deposit Expired\nNo money was moved.")
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class BackgroundColorChoiceButton(discord.ui.Button):
    def __init__(self, accept: bool) -> None:
        super().__init__(
            label="Remove Image" if accept else "Cancel",
            style=(
                discord.ButtonStyle.danger
                if accept
                else discord.ButtonStyle.secondary
            ),
        )
        self.accept = accept

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if isinstance(view, BackgroundColorConfirmView):
            await view.choose(interaction, self.accept)


class BackgroundColorConfirmView(discord.ui.LayoutView):
    def __init__(
        self,
        cog: "Economy",
        author_id: int,
        old_background: str,
        values: dict[str, object],
    ) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.author_id = author_id
        self.old_background = old_background
        self.values = values
        self.message: discord.Message | None = None
        self.finished = False
        self.render()

    def render(self, result: str | None = None) -> None:
        self.clear_items()
        if result is not None:
            self.add_item(discord.ui.Container(discord.ui.TextDisplay(result)))
            return
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Replace Background Image?\n"
                    "Your current image, GIF, or video background must be removed "
                    "before the color background can be shown."
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    "-# Removing the uploaded background cannot be undone."
                ),
                discord.ui.ActionRow(
                    BackgroundColorChoiceButton(True),
                    BackgroundColorChoiceButton(False),
                ),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "Only the person changing this card can use these buttons.",
            ephemeral=True,
        )
        return False

    async def choose(self, interaction: discord.Interaction, accept: bool) -> None:
        if self.finished:
            await interaction.response.send_message(
                "This confirmation is no longer active.", ephemeral=True
            )
            return
        self.finished = True
        self.stop()
        if not accept:
            self.render("## Background Change Cancelled\nYour current image was kept.")
            await interaction.response.edit_message(view=self)
            return
        await interaction.response.defer()
        values = dict(self.values)
        values["background_path"] = None
        await asyncio.to_thread(store.update_balance_card, self.author_id, **values)
        try:
            Path(self.old_background).unlink(missing_ok=True)
        except OSError:
            pass
        self.cog._clear_balance_cache(self.author_id)
        self.render("## Background Updated\nThe image was removed and the color background is now active.")
        await interaction.edit_original_response(view=self)

    async def on_timeout(self) -> None:
        if self.finished:
            return
        self.finished = True
        self.render("## Confirmation Expired\nYour current image was kept.")
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class BalanceStudioValueModal(discord.ui.Modal):
    def __init__(self, studio: "BalanceStudioView", setting: str) -> None:
        titles = {
            "background_color": "Background Color",
            "gradient_color": "Gradient Color",
            "text_color": "Text Color",
            "message": "Card Message",
        }
        super().__init__(title=titles[setting])
        self.studio = studio
        self.setting = setting
        current = studio.settings.get(setting) or ""
        placeholder = (
            "#38BDF8"
            if setting.endswith("color")
            else "Use - to clear the message"
        )
        self.value_input = discord.ui.TextInput(
            label=titles[setting],
            default=str(current)[:100] or None,
            placeholder=placeholder,
            max_length=100 if setting == "message" else 7,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = str(self.value_input.value).strip()
        try:
            if self.setting == "message":
                value: object = "" if raw == "-" else raw[:100]
            elif self.setting == "gradient_color" and raw.casefold() in {
                "none", "off", "clear", "-",
            }:
                value = None
            else:
                value = normalize_color(raw)
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        await self.studio.save(interaction, **{self.setting: value})


class BalanceStudioFeatureSelect(discord.ui.Select):
    def __init__(self, studio: "BalanceStudioView") -> None:
        self.studio = studio
        super().__init__(
            placeholder="Edit colors or message",
            options=[
                discord.SelectOption(label="Background color", value="background_color"),
                discord.SelectOption(label="Gradient color", value="gradient_color"),
                discord.SelectOption(label="Text color", value="text_color"),
                discord.SelectOption(label="Custom message", value="message"),
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            BalanceStudioValueModal(self.studio, self.values[0])
        )


class BalanceStudioSettingSelect(discord.ui.Select):
    def __init__(
        self,
        studio: "BalanceStudioView",
        setting: str,
        placeholder: str,
        options: list[tuple[str, str]],
    ) -> None:
        self.studio = studio
        self.setting = setting
        current = str(studio.settings.get(setting, ""))
        super().__init__(
            placeholder=placeholder,
            options=[
                discord.SelectOption(
                    label=label,
                    value=value,
                    default=value == current,
                )
                for label, value in options
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        value: object = self.values[0]
        if self.setting == "fade":
            value = int(value)
        await self.studio.save(interaction, **{self.setting: value})


class BalanceStudioButton(discord.ui.Button):
    def __init__(
        self,
        action: str,
        label: str,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
    ) -> None:
        super().__init__(label=label, style=style)
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        studio = self.view
        if isinstance(studio, BalanceStudioView):
            await studio.action(interaction, self.action)


class BalanceStudioView(discord.ui.LayoutView):
    def __init__(
        self,
        cog: "Economy",
        author_id: int,
        settings: dict[str, object],
    ) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = author_id
        self.settings = settings
        self.preview_filename = "balance-studio-preview.png"
        self.message: discord.Message | None = None
        self.render()

    def render(self, status: str | None = None) -> None:
        self.clear_items()
        media = "Uploaded" if self.settings.get("background_path") else "None"
        privacy = "Hidden" if self.settings.get("wallet_hidden") else "Visible"
        summary = (
            f"**Background:** `{self.settings.get('background_color')}` → "
            f"`{self.settings.get('gradient_color') or 'None'}`\n"
            f"**Gradient starts:** `{self.settings.get('gradient_direction', 'top')}`\n"
            f"**Text:** `{self.settings.get('text_color')}` · "
            f"**Avatar:** `{self.settings.get('avatar_shape')}`\n"
            f"**Opacity:** `{self.settings.get('fade', 45)}%` · "
            f"**Wallet:** `{privacy}` · **Media:** `{media}`\n"
            f"**Message:** {self.settings.get('message') or 'None'}"
        )
        if status:
            summary += f"\n\n-# {status}"
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("## Balance Card Studio\n" + summary),
                discord.ui.Separator(),
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(
                        f"attachment://{self.preview_filename}",
                        description="Live balance card preview",
                    )
                ),
                discord.ui.Separator(),
                discord.ui.ActionRow(BalanceStudioFeatureSelect(self)),
                discord.ui.ActionRow(
                    BalanceStudioSettingSelect(
                        self,
                        "avatar_shape",
                        "Avatar shape",
                        [(value.replace("-", " ").title(), value) for value in sorted(AVATAR_SHAPES)],
                    )
                ),
                discord.ui.ActionRow(
                    BalanceStudioSettingSelect(
                        self,
                        "gradient_direction",
                        "Gradient starting position",
                        [(value.replace("-", " ").title(), value) for value in GRADIENT_DIRECTIONS],
                    )
                ),
                discord.ui.ActionRow(
                    BalanceStudioSettingSelect(
                        self,
                        "fade",
                        "Overlay opacity",
                        [(f"{value}%", str(value)) for value in range(0, 91, 10)],
                    )
                ),
                discord.ui.ActionRow(
                    BalanceStudioButton("privacy", "Toggle Privacy"),
                    BalanceStudioButton("preview", "Preview", discord.ButtonStyle.primary),
                    BalanceStudioButton("remove", "Remove Media", discord.ButtonStyle.danger),
                    BalanceStudioButton("reset", "Reset", discord.ButtonStyle.danger),
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    "-# To upload media, reply to an image, GIF, or video with "
                    "`;balance edit background`."
                ),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This balance studio belongs to someone else.", ephemeral=True
        )
        return False

    async def save(self, interaction: discord.Interaction, **values: object) -> None:
        color_change = any(
            key in values for key in ("background_color", "gradient_color")
        )
        if color_change and self.settings.get("background_path"):
            await interaction.response.send_message(
                "Remove the current media background first, then apply colors.",
                ephemeral=True,
            )
            return
        self.settings = await asyncio.to_thread(
            store.update_balance_card, self.author_id, **values
        )
        self.cog._clear_balance_cache(self.author_id)
        await interaction.response.defer()
        account = await asyncio.to_thread(store.get_account, self.author_id)
        preview = await self.cog._balance_card_bytes(interaction.user, account)
        self.preview_filename = "balance-studio-preview.gif" if preview.startswith(b"GIF") else "balance-studio-preview.png"
        self.render("Setting saved.")
        await interaction.edit_original_response(
            view=self,
            attachments=[discord.File(io.BytesIO(preview), filename=self.preview_filename)],
        )

    async def action(self, interaction: discord.Interaction, action: str) -> None:
        if action == "privacy":
            await self.save(
                interaction,
                wallet_hidden=int(not bool(self.settings.get("wallet_hidden"))),
            )
            return
        if action == "preview":
            await interaction.response.defer(ephemeral=True)
            account = await asyncio.to_thread(store.get_account, self.author_id)
            image = await self.cog._balance_card_bytes(interaction.user, account)
            extension = "gif" if image.startswith(b"GIF") else "png"
            await interaction.followup.send(
                file=discord.File(io.BytesIO(image), filename=f"balance-preview.{extension}"),
                ephemeral=True,
            )
            return
        old_background = self.settings.get("background_path")
        if action == "remove":
            if not old_background:
                await interaction.response.send_message(
                    "There is no uploaded background to remove.", ephemeral=True
                )
                return
            self.settings = await asyncio.to_thread(
                store.update_balance_card, self.author_id, background_path=None
            )
            try:
                Path(str(old_background)).unlink(missing_ok=True)
            except OSError:
                pass
            status = "Uploaded media removed."
        else:
            await asyncio.to_thread(store.reset_balance_card, self.author_id)
            if old_background:
                try:
                    Path(str(old_background)).unlink(missing_ok=True)
                except OSError:
                    pass
            self.settings = await asyncio.to_thread(
                store.balance_card_settings, self.author_id
            )
            status = "All settings reset."
        self.cog._clear_balance_cache(self.author_id)
        await interaction.response.defer()
        account = await asyncio.to_thread(store.get_account, self.author_id)
        preview = await self.cog._balance_card_bytes(interaction.user, account)
        self.preview_filename = "balance-studio-preview.gif" if preview.startswith(b"GIF") else "balance-studio-preview.png"
        self.render(status)
        await interaction.edit_original_response(
            view=self,
            attachments=[discord.File(io.BytesIO(preview), filename=self.preview_filename)],
        )

    async def on_timeout(self) -> None:
        self.clear_items()
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("## Balance Card Studio\n-# This studio expired.")
            )
        )
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


SCOPE_CHOICES = [
    app_commands.Choice(name="Global", value="global"),
    app_commands.Choice(name="Server", value="server"),
]
RANKING_CHOICES = [
    app_commands.Choice(name="Net worth", value="net"),
    app_commands.Choice(name="Cash only", value="cash"),
    app_commands.Choice(name="Bank only", value="bank"),
]
RESET_CHOICES = [
    app_commands.Choice(name="Wallet", value="wallet"),
    app_commands.Choice(name="Bank", value="bank"),
    app_commands.Choice(name="Both", value="both"),
]


class Economy(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.giveaway_tasks: dict[int, asyncio.Task] = {}
        self.giveaway_views: dict[int, discord.ui.LayoutView] = {}
        self.balance_card_cache: dict[tuple, tuple[float, bytes]] = {}
        self.balance_card_fast_cache: dict[int, tuple[float, tuple, bytes]] = {}
        self.transaction_cleanup.start()
        self.lottery_scheduler.start()

    def cog_unload(self) -> None:
        self.transaction_cleanup.cancel()
        self.lottery_scheduler.cancel()
        for task in self.giveaway_tasks.values():
            task.cancel()
        for view in self.giveaway_views.values():
            self.bot.remove_view(view)

    async def cog_load(self) -> None:
        rows = await asyncio.to_thread(store.active_giveaways)
        for row in rows:
            giveaway_id = int(row["id"])
            if row["message_id"]:
                view = giveaway_view(self, row, int(row["entries"]))
                self.giveaway_views[giveaway_id] = view
                self.bot.add_view(view, message_id=int(row["message_id"]))
            self.giveaway_tasks[giveaway_id] = asyncio.create_task(
                self._finish_giveaway_at(giveaway_id, int(row["ends_at"]))
            )

    async def _finish_giveaway_at(self, giveaway_id: int, ends_at: int) -> None:
        try:
            await asyncio.sleep(max(0, ends_at - int(time.time())))
            result = await asyncio.to_thread(store.finish_giveaway, giveaway_id)
            if result is None:
                return
            row, payouts = result
            if payouts:
                winners = "\n".join(
                    f"<@{user_id}> — {money_code(amount)}" for user_id, amount in payouts
                )
                body = (
                    "## Giveaway Ended\n"
                    f"### Winners\n{winners}\n\n"
                    f"**Prize pool:** {money_code(int(row['amount']))}\n"
                    f"**Hosted by:** <@{int(row['host_id'])}>"
                )
            else:
                body = (
                    "## Giveaway Ended\n"
                    "Nobody entered, so the reserved prize was returned to "
                    f"<@{int(row['host_id'])}>."
                )
            ended_view = discord.ui.LayoutView()
            ended_view.add_item(discord.ui.Container(discord.ui.TextDisplay(body)))
            try:
                channel = self.bot.get_channel(int(row["channel_id"]))
                if channel is None:
                    channel = await self.bot.fetch_channel(int(row["channel_id"]))
                message = await channel.fetch_message(int(row["message_id"]))
                await message.edit(view=ended_view)
                if payouts:
                    mentions = " ".join(f"<@{user_id}>" for user_id, _ in payouts)
                    await message.reply(f"Congratulations {mentions}!", mention_author=False)
            except (discord.HTTPException, AttributeError, TypeError):
                pass
        except asyncio.CancelledError:
            raise
        finally:
            old_view = self.giveaway_views.pop(giveaway_id, None)
            if old_view is not None:
                self.bot.remove_view(old_view)
            self.giveaway_tasks.pop(giveaway_id, None)

    @tasks.loop(hours=24)
    async def transaction_cleanup(self) -> None:
        await asyncio.to_thread(store.transactions, 1)

    @transaction_cleanup.before_loop
    async def before_cleanup(self) -> None:
        await self.bot.wait_until_ready()

    async def _lottery_channel(self, channel_id: int):
        channel = self.bot.get_channel(channel_id)
        if channel is not None:
            return channel
        try:
            return await self.bot.fetch_channel(channel_id)
        except discord.HTTPException:
            return None

    @tasks.loop(minutes=1)
    async def lottery_scheduler(self) -> None:
        status = await asyncio.to_thread(store.lottery_status)
        if not status["channel_id"] or not status["ends_at"] or int(time.time()) < status["ends_at"]:
            return
        channel = await self._lottery_channel(status["channel_id"])
        result = await asyncio.to_thread(store.draw_lottery)
        if result is None:
            next_round = await asyncio.to_thread(store.extend_lottery_round)
            if channel is not None:
                await channel.send(
                    f"## Lottery Extended\nNo tickets were entered, so the **{money_code(status['pool'])}** "
                    f"pool carries over.\n**New draw:** <t:{next_round['ends_at']}:F> · <t:{next_round['ends_at']}:R>\n"
                    "Use `/lottery enter` to join."
                )
            return
        winner_id, pool, round_id = result
        next_round = await asyncio.to_thread(store.lottery_status)
        if channel is not None:
            await channel.send(
                f"## Lottery Winner\n<@{winner_id}> won **{money_code(pool)}** in round `{round_id}`!\n\n"
                f"Round `{next_round['round']}` is now open and draws <t:{next_round['ends_at']}:R>. "
                "Use `/lottery enter` to buy tickets."
            )

    @lottery_scheduler.before_loop
    async def before_lottery_scheduler(self) -> None:
        await self.bot.wait_until_ready()

    async def require_admin(self, ctx: commands.Context) -> bool:
        if await self.bot.is_primary_owner(ctx.author) or await asyncio.to_thread(store.is_admin, ctx.author.id):
            return True
        await ctx.send("Only an economy admin can use this command.", ephemeral=True)
        return False

    async def resolve_user(self, user_id: int) -> discord.User | discord.Member | None:
        user = self.bot.get_user(user_id)
        if user is not None: return user
        try: return await self.bot.fetch_user(user_id)
        except discord.HTTPException: return None

    def _clear_balance_cache(self, user_id: int) -> None:
        self.balance_card_fast_cache.pop(user_id, None)
        self.balance_card_cache = {
            key: value for key, value in self.balance_card_cache.items()
            if key[0] != user_id
        }
        if BALANCE_CARD_CACHE.is_dir():
            for cached_path in BALANCE_CARD_CACHE.glob(f"{user_id}-*"):
                try:
                    cached_path.unlink()
                except OSError:
                    pass

    async def _balance_ranks(self, user_id: int) -> dict[str, int]:
        rank_loader = getattr(store, "balance_ranks", None)
        if rank_loader is not None:
            return await asyncio.to_thread(rank_loader, user_id)
        # A cog can be hot-reloaded while its already-imported service module
        # remains in memory. Fall back to the older public ranking API so the
        # command keeps working until the next full restart.
        wallet, bank, net = await asyncio.gather(
            asyncio.to_thread(store.leaderboard_rank, user_id, None, "cash"),
            asyncio.to_thread(store.leaderboard_rank, user_id, None, "bank"),
            asyncio.to_thread(store.leaderboard_rank, user_id, None, "net"),
        )
        return {
            "wallet": wallet[0] if wallet else 1,
            "bank": bank[0] if bank else 1,
            "net": net[0] if net else 1,
        }

    async def _replied_attachment(
        self, ctx: commands.Context
    ) -> discord.Attachment | str | None:
        if ctx.interaction is not None or ctx.message is None:
            return None
        reference = ctx.message.reference
        if reference is None:
            return None
        resolved = reference.resolved
        message = resolved if isinstance(resolved, discord.Message) else None
        if message is None and reference.message_id is not None:
            try:
                message = await ctx.channel.fetch_message(reference.message_id)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                return None
        if not message:
            return None
        if message.attachments:
            return message.attachments[0]
        for embed in message.embeds:
            for candidate in (embed.image.url, embed.thumbnail.url, embed.url):
                if candidate and candidate.startswith(("http://", "https://")):
                    return candidate
        return None

    async def _balance_card_bytes(self, target: discord.User | discord.Member, account) -> bytes:
        avatar_key = str(getattr(target.display_avatar, "key", ""))
        decoration = getattr(target, "avatar_decoration", None)
        decoration_key = str(getattr(decoration, "key", ""))
        fast_key = (
            account.wallet,
            account.bank,
            account.bank_capacity,
            target.display_name,
            avatar_key,
            decoration_key,
        )
        fast_cached = self.balance_card_fast_cache.get(target.id)
        if (
            fast_cached
            and fast_cached[1] == fast_key
            and time.monotonic() - fast_cached[0] < 60
        ):
            return fast_cached[2]
        settings, ranks = await asyncio.gather(
            asyncio.to_thread(store.balance_card_settings, target.id),
            self._balance_ranks(target.id),
        )
        background_path = settings.get("background_path")
        background_stamp = 0
        if background_path:
            try:
                background_stamp = Path(background_path).stat().st_mtime_ns
            except OSError:
                pass
        key = (
            target.id, CARD_RENDER_VERSION,
            account.wallet, account.bank, account.bank_capacity,
            tuple(sorted(ranks.items())), tuple(sorted(settings.items())),
            avatar_key, decoration_key, background_stamp,
        )
        cached = self.balance_card_cache.get(key)
        if cached and time.monotonic() - cached[0] < 300:
            self.balance_card_fast_cache[target.id] = (
                time.monotonic(), fast_key, cached[1]
            )
            return cached[1]
        persistent = await asyncio.to_thread(
            _read_persistent_card, target.id, key
        )
        if persistent is not None:
            self.balance_card_cache[key] = (time.monotonic(), persistent)
            self.balance_card_fast_cache[target.id] = (
                time.monotonic(), fast_key, persistent
            )
            return persistent
        try:
            avatar_bytes = await target.display_avatar.with_size(512).read()
        except discord.HTTPException:
            avatar_bytes = None
        if decoration is not None:
            try:
                decoration_bytes = await decoration.with_static_format("png").read()
            except discord.HTTPException:
                decoration_bytes = None
        else:
            decoration_bytes = None
        result = await asyncio.to_thread(
            render_balance_card,
            target.display_name,
            account,
            ranks,
            settings,
            avatar_bytes,
            decoration_bytes,
        )
        if len(self.balance_card_cache) >= 128:
            oldest = min(self.balance_card_cache, key=lambda item: self.balance_card_cache[item][0])
            self.balance_card_cache.pop(oldest, None)
        self.balance_card_cache[key] = (time.monotonic(), result)
        self.balance_card_fast_cache[target.id] = (
            time.monotonic(), fast_key, result
        )
        await asyncio.to_thread(_write_persistent_card, target.id, key, result)
        return result

    async def _send_balance_card(
        self, ctx: commands.Context, target: discord.User | discord.Member
    ) -> None:
        account = await asyncio.to_thread(store.get_account, target.id)
        if ctx.interaction is not None and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)
        image = await self._balance_card_bytes(target, account)
        extension = "gif" if image.startswith(b"GIF") else "png"
        await ctx.send(file=discord.File(io.BytesIO(image), filename=f"balance-card.{extension}"))

    async def _finish_balance_customization(
        self, ctx: commands.Context, **values: object
    ) -> None:
        await asyncio.to_thread(store.update_balance_card, ctx.author.id, **values)
        self._clear_balance_cache(ctx.author.id)
        account = await asyncio.to_thread(store.get_account, ctx.author.id)
        preview = await self._balance_card_bytes(ctx.author, account)
        extension = "gif" if preview.startswith(b"GIF") else "png"
        await ctx.send(
            "Balance card updated.",
            file=discord.File(io.BytesIO(preview), filename=f"balance-card-preview.{extension}"),
            ephemeral=ctx.interaction is not None,
        )

    @commands.hybrid_command(
        name="balance",
        aliases=["bal", "wallet"],
        description="Show a user's balance card",
    )
    @app_commands.describe(user="User whose balance card you want to see")
    async def balance(
        self, ctx: commands.Context, user: discord.User | None = None
    ) -> None:
        await self._send_balance_card(ctx, user or ctx.author)

    @commands.hybrid_group(
        name="balance-edit",
        aliases=["bal-edit", "balance-customize"],
        description="Customize your balance card",
        invoke_without_command=True,
    )
    async def balance_customize(self, ctx: commands.Context) -> None:
        if ctx.invoked_subcommand is None:
            await ctx.send(
                "Use `balance-edit background`, `text-color`, `avatar`, "
                "`message`, `privacy`, `opacity`, or `reset`."
            )

    @balance_customize.command(
        name="background",
        aliases=["bg", "img", "image"],
        description="Change the card background",
    )
    @app_commands.describe(
        color="Solid color or top gradient color, such as #111827",
        gradient="Bottom gradient color, or 'none' to disable it",
        direction="Where the first gradient color starts",
        image="Image, GIF, or small video to stretch to the card dimensions",
        url="Direct image, GIF, or small video URL",
        remove_image="Remove the uploaded image and use colors instead",
    )
    async def balance_customize_background(
        self,
        ctx: commands.Context,
        color: str | None = None,
        gradient: str | None = None,
        direction: str | None = None,
        image: discord.Attachment | None = None,
        url: str | None = None,
        remove_image: bool = False,
    ) -> None:
        if ctx.interaction is not None and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True, ephemeral=True)
        if color is not None and color.casefold() in {
            "remove",
            "remove_image",
            "remove-image",
        }:
            color = None
            remove_image = True
        values: dict[str, object] = {}
        try:
            if color is not None:
                resolved,_=await resolve_color(color)
                values["background_color"]="#"+"".join(f"{value:02X}" for value in resolved)
            if gradient is not None:
                if gradient.casefold() in {"none", "off", "clear"}:
                    values["gradient_color"] = None
                else:
                    resolved,_=await resolve_color(gradient)
                    values["gradient_color"]="#"+"".join(f"{value:02X}" for value in resolved)
        except ValueError as error:
            await ctx.send(str(error), ephemeral=ctx.interaction is not None)
            return
        if direction is not None:
            direction = direction.casefold().replace("_", "-")
            if direction not in GRADIENT_DIRECTIONS:
                await ctx.send(
                    "Direction must be `top`, `bottom`, `left`, `right`, "
                    "`top-left`, `top-right`, `bottom-left`, or `bottom-right`.",
                    ephemeral=ctx.interaction is not None,
                )
                return
            values["gradient_direction"] = direction
        current = await asyncio.to_thread(store.balance_card_settings, ctx.author.id)
        old_background = current.get("background_path")
        if image is None:
            image = await self._replied_attachment(ctx)
        if isinstance(image, str):
            if url:
                await ctx.send("Choose either a replied image or a URL, not both.", ephemeral=ctx.interaction is not None)
                return
            url, image = image, None
        if image is not None and url:
            await ctx.send(
                "Choose either an upload or a URL, not both.",
                ephemeral=ctx.interaction is not None,
            )
            return
        raw: bytes | None = None
        filename = ""
        content_type = ""
        if url:
            try:
                raw, filename, content_type = await download_balance_background(url)
            except (ValueError, aiohttp.ClientError, asyncio.TimeoutError) as error:
                await ctx.send(str(error), ephemeral=ctx.interaction is not None)
                return
        elif image is not None:
            if image.size > MAX_BACKGROUND_BYTES:
                await ctx.send("The source image must be `25 MB` or smaller.", ephemeral=ctx.interaction is not None)
                return
            try:
                raw = await image.read()
                filename = image.filename
                content_type = image.content_type or ""
            except discord.HTTPException:
                await ctx.send(
                    "I could not download that attachment.",
                    ephemeral=ctx.interaction is not None,
                )
                return
        if raw is not None:
            try:
                destination = await asyncio.to_thread(
                    prepare_balance_background,
                    raw,
                    ctx.author.id,
                    filename,
                    content_type,
                )
                if old_background and Path(old_background) != destination:
                    Path(old_background).unlink(missing_ok=True)
                values["background_path"] = str(destination)
            except (
                OSError,
                ValueError,
                subprocess.SubprocessError,
            ):
                await ctx.send(
                    "I could not process that media. Use a valid PNG, JPG, "
                    "WebP, GIF, AVIF, MP4, MOV, WebM, MKV, or AVI file.",
                    ephemeral=ctx.interaction is not None,
                )
                return
        elif remove_image:
            values["background_path"] = None
            if old_background:
                try:
                    Path(old_background).unlink(missing_ok=True)
                except OSError:
                    pass
        elif old_background and any(
            key in values for key in ("background_color", "gradient_color")
        ):
            view = BackgroundColorConfirmView(
                self,
                ctx.author.id,
                str(old_background),
                values,
            )
            view.message = await ctx.send(
                view=view,
                ephemeral=ctx.interaction is not None,
            )
            return
        if not values:
            await ctx.send("Choose a color, gradient, image, URL, or `remove_image`.", ephemeral=ctx.interaction is not None)
            return
        await self._finish_balance_customization(ctx, **values)

    @balance_customize.command(
        name="text-color",
        aliases=["text", "color", "textcolor"],
        description="Change the card text color",
    )
    @app_commands.describe(color="Six-digit hex color, such as #F8FAFC")
    async def balance_customize_text_color(self, ctx: commands.Context, color: str) -> None:
        try:
            color = normalize_color(color)
        except ValueError as error:
            await ctx.send(str(error), ephemeral=ctx.interaction is not None)
            return
        await self._finish_balance_customization(ctx, text_color=color)

    @balance_customize.command(
        name="avatar",
        aliases=["av", "pfp"],
        description="Change the avatar shape",
    )
    @app_commands.describe(shape="Circle, rounded, square, or hidden")
    @app_commands.choices(shape=[
        app_commands.Choice(name="Circle", value="circle"),
        app_commands.Choice(name="Rounded", value="rounded"),
        app_commands.Choice(name="Square", value="square"),
        app_commands.Choice(name="Hidden", value="hidden"),
    ])
    async def balance_customize_avatar(self, ctx: commands.Context, shape: str) -> None:
        shape = shape.casefold()
        if shape not in AVATAR_SHAPES:
            await ctx.send("Shape must be `circle`, `rounded`, `square`, or `hidden`.", ephemeral=ctx.interaction is not None)
            return
        await self._finish_balance_customization(ctx, avatar_shape=shape)

    @balance_customize.command(
        name="message",
        aliases=["msg"],
        description="Set or clear the card message",
    )
    @app_commands.describe(text="Message up to 100 characters; use '-' to clear it")
    async def balance_customize_message(self, ctx: commands.Context, *, text: str) -> None:
        await self._finish_balance_customization(
            ctx, message="" if text == "-" else text.strip()[:100]
        )

    @balance_customize.command(
        name="privacy",
        aliases=["private", "hide"],
        description="Show or hide wallet and net worth",
    )
    @app_commands.describe(hide_wallet="Hide wallet and net worth when enabled")
    async def balance_customize_privacy(self, ctx: commands.Context, hide_wallet: bool) -> None:
        await self._finish_balance_customization(ctx, wallet_hidden=int(hide_wallet))

    @balance_customize.command(
        name="opacity",
        aliases=["fade", "dim", "overlay"],
        description="Change the dark overlay opacity",
    )
    @app_commands.describe(amount="Dark overlay opacity from 0 to 90 percent")
    async def balance_customize_opacity(self, ctx: commands.Context, amount: int) -> None:
        if not 0 <= amount <= 90:
            await ctx.send("Opacity must be between `0` and `90`.", ephemeral=ctx.interaction is not None)
            return
        await self._finish_balance_customization(ctx, fade=amount)

    @balance_customize.command(
        name="studio",
        aliases=["menu", "settings"],
        description="Open the interactive balance-card studio",
    )
    async def balance_customize_studio(self, ctx: commands.Context) -> None:
        settings = await asyncio.to_thread(
            store.balance_card_settings, ctx.author.id
        )
        view = BalanceStudioView(self, ctx.author.id, settings)
        account = await asyncio.to_thread(store.get_account, ctx.author.id)
        preview = await self._balance_card_bytes(ctx.author, account)
        view.preview_filename = "balance-studio-preview.gif" if preview.startswith(b"GIF") else "balance-studio-preview.png"
        view.render()
        view.message = await ctx.send(
            view=view,
            file=discord.File(io.BytesIO(preview), filename=view.preview_filename),
            ephemeral=ctx.interaction is not None,
        )

    @balance_customize.command(
        name="reset",
        aliases=["clear", "default"],
        description="Reset every balance-card setting",
    )
    async def balance_customize_reset(self, ctx: commands.Context) -> None:
        current = await asyncio.to_thread(store.balance_card_settings, ctx.author.id)
        old_background = current.get("background_path")
        await asyncio.to_thread(store.reset_balance_card, ctx.author.id)
        if old_background:
            try:
                Path(old_background).unlink(missing_ok=True)
            except OSError:
                pass
        self._clear_balance_cache(ctx.author.id)
        await ctx.send("Your balance card was reset.", ephemeral=ctx.interaction is not None)

    @commands.hybrid_command(name="daily", description="Claim your daily economy reward")
    async def daily(self, ctx: commands.Context) -> None:
        try:
            _, reward, streak = await asyncio.to_thread(store.claim_daily, ctx.author.id)
        except EconomyError as error:
            await ctx.send(view=structured_card(
                "Daily Already Claimed",
                [("Available Again", f"`{duration(int(str(error)))}`")],
            ))
            return
        await ctx.send(view=structured_card(
            "Daily Reward",
            [
                ("Reward", money_code(reward)),
                ("Daily Streak", number_code(streak, " day(s)")),
            ],
            note="The reward increases with your streak until day 30.",
        ))

    @commands.hybrid_command(name="cooldowns", aliases=["cds"], description="Show your active economy cooldowns")
    async def cooldowns(self, ctx: commands.Context) -> None:
        values = await asyncio.to_thread(store.cooldowns, ctx.author.id)

        def status(seconds: int) -> str:
            return f"`{duration(seconds)}`" if seconds else "`Ready`"

        core = (
            f"**Daily:** {status(values.get('daily', 0))}\n"
            f"**Work:** {status(values.get('work', 0))}\n"
            f"**Rob:** {status(values.get('rob', 0))}"
        )
        rewards = []
        for key, seconds in sorted(values.items()):
            if not key.startswith("reward:") or seconds <= 0:
                continue
            game = key.removeprefix("reward:").replace("_", " ").title()
            rewards.append(f"**{game}:** {status(seconds)}")
        sections = [("Economy", core)]
        if rewards:
            sections.append(("Game Reward Cooldowns", "\n".join(rewards)))
        await ctx.send(
            view=structured_card(
                f"{ctx.author.display_name}'s Cooldowns",
                sections,
                note="Reward cooldowns do not stop you from playing the games.",
            )
        )

    @commands.hybrid_command(name="work", description="Choose a job and earn money")
    async def work(self, ctx: commands.Context) -> None:
        account = await asyncio.to_thread(store.get_account, ctx.author.id)
        if account.work_last and int(time.time()) - account.work_last < 43_200:
            await ctx.send(view=structured_card(
                "Work Cooldown",
                [("Available Again", f"`{duration(43_200 - (int(time.time()) - account.work_last))}`")],
            )); return
        jobs = [
            random.choice([job for job in JOBS if job.difficulty == difficulty])
            for difficulty in ("Easy", "Medium", "Hard")
        ]
        await ctx.send(view=WorkView(ctx.author.id, jobs))

    @commands.hybrid_command(name="transfer", aliases=["pay", "send"], description="Send wallet money to another user")
    async def transfer(self, ctx: commands.Context, user: discord.User, amount: int) -> None:
        if user.id == ctx.author.id or user.bot or amount <= 0:
            await ctx.send("Choose another real user and a positive amount."); return
        try:
            sender, _ = await asyncio.to_thread(store.transfer, ctx.author.id, user.id, amount)
        except InsufficientFunds:
            await ctx.send("You don't have enough money in your wallet."); return
        await ctx.send(view=structured_card(
            "Transfer Complete",
            [
                ("Transfer", f"**Recipient:** {user.mention}\n**Amount sent:** {money_code(amount)}"),
                ("Remaining Wallet", money_code(sender.wallet)),
            ],
        ))

    @commands.hybrid_command(name="deposit", aliases=["dep"], description="Deposit wallet money into your bank")
    @app_commands.describe(amount="Amount such as 25000, 25k, 50%, or all")
    async def deposit(self, ctx: commands.Context, amount: str) -> None:
        account = await asyncio.to_thread(store.get_account, ctx.author.id)
        try:
            value = parse_amount(amount, account.wallet)
        except ValueError:
            await ctx.send("Enter an amount such as `25000`, `25k`, `50%`, or `all`."); return
        if value > account.wallet:
            await ctx.send("You don't have that much in your wallet."); return
        fee = deposit_fee(value)
        if value - fee <= 0:
            await ctx.send("That amount is too small after the 5% deposit fee."); return
        if account.bank + value - fee > account.bank_capacity:
            await ctx.send("That would exceed your bank capacity. Use `/bank expand` or `;bank expand`."); return
        view = DepositConfirmView(ctx.author.id, value, account.wallet)
        view.message = await ctx.send(view=view)

    @commands.hybrid_group(name="lottery", description="View or enter the rolling economy lottery", invoke_without_command=True)
    async def lottery(self, ctx: commands.Context) -> None:
        status = await asyncio.to_thread(store.lottery_status, ctx.author.id)
        chance = status["user_tickets"] / status["tickets"] * 100 if status["tickets"] else 0
        await ctx.send(
            f"## Lottery — Round {status['round']}\n**Pool:** {money_code(status['pool'])}\n"
            f"**Tickets sold:** `{status['tickets']:,}`\n**Your tickets:** `{status['user_tickets']:,}` "
            f"({chance:.2f}% chance)\n"
            + (f"**Draw:** <t:{status['ends_at']}:F> · <t:{status['ends_at']}:R>\n" if status["ends_at"] else "**Draw:** Not scheduled yet\n")
            + "\nTickets cost **2,500** each. Deposit fees also fund the pool. "
            "Use `;lottery enter <amount>` or `/lottery enter`."
        )

    @lottery.command(name="set-channel", description="Choose the lottery announcement channel")
    @commands.guild_only()
    @app_commands.describe(channel="Channel for lottery announcements; defaults to this channel")
    async def lottery_set_channel(
        self, ctx: commands.Context, channel: discord.TextChannel | None = None
    ) -> None:
        if not await self.require_admin(ctx):
            return
        selected = channel or ctx.channel
        if not isinstance(selected, discord.TextChannel):
            await ctx.send("Choose a server text channel.", ephemeral=True)
            return
        permissions = selected.permissions_for(ctx.guild.me)
        if not permissions.send_messages or not permissions.view_channel:
            await ctx.send("I cannot view or send messages in that channel.", ephemeral=True)
            return
        status = await asyncio.to_thread(store.set_lottery_channel, selected.id)
        await selected.send(
            f"## Lottery Round {status['round']} Is Open\n"
            f"**Current pool:** {money_code(status['pool'])}\n"
            f"**Ticket price:** {money_code(2_500)}\n"
            f"**Draw:** <t:{status['ends_at']}:F> · <t:{status['ends_at']}:R>\n\n"
            "Deposit fees grow the prize pool. Buy multiple tickets with `/lottery enter`."
        )
        await ctx.send(
            f"Lottery announcements will be sent in {selected.mention}. The 36-hour round has started.",
            ephemeral=ctx.interaction is not None,
        )

    @lottery.command(name="enter", description="Buy one or more lottery tickets")
    async def lottery_enter(self, ctx: commands.Context, tickets: app_commands.Range[int, 1, 100] = 1) -> None:
        try:
            account, status = await asyncio.to_thread(store.buy_lottery_tickets, ctx.author.id, tickets)
        except (InsufficientFunds, ValueError):
            await ctx.send(f"You need {money_code(tickets * 2_500)} in your wallet for that.", ephemeral=True)
            return
        await ctx.send(
            f"Bought **{tickets:,}** ticket{'s' if tickets != 1 else ''} for {money_code(tickets * 2_500)}.\n"
            f"**Pool:** {money_code(status['pool'])} · **Your tickets:** `{status['user_tickets']:,}` · "
            f"**Wallet:** {money_code(account.wallet)}"
        )

    @lottery.command(name="draw", description="Draw the lottery (economy admins only)")
    async def lottery_draw(self, ctx: commands.Context) -> None:
        if not await self.require_admin(ctx):
            return
        result = await asyncio.to_thread(store.draw_lottery)
        if result is None:
            await ctx.send("The lottery needs a funded pool and at least one ticket.", ephemeral=True)
            return
        winner_id, pool, round_id = result
        await ctx.send(f"## Lottery Winner\n<@{winner_id}> won **{money_code(pool)}** in round `{round_id}`!")

    @commands.hybrid_command(name="withdraw", aliases=["wd"], description="Withdraw money from your bank")
    @app_commands.describe(amount="Amount such as 25000, 25k, 50%, or all")
    async def withdraw(self, ctx: commands.Context, amount: str) -> None:
        account = await asyncio.to_thread(store.get_account, ctx.author.id)
        try:
            value = parse_amount(amount, account.bank)
            updated = await asyncio.to_thread(store.withdraw, ctx.author.id, value)
        except ValueError:
            await ctx.send("Enter an amount such as `25000`, `25k`, `50%`, or `all`."); return
        except InsufficientFunds:
            await ctx.send("You don't have that much in your bank."); return
        await ctx.send(view=structured_card(
            "Withdrawal Complete",
            [
                ("Withdrawal", money_code(value)),
                ("Updated Balances", f"**Wallet:** {money_code(updated.wallet)}\n**Bank:** {money_code(updated.bank)}"),
            ],
        ))

    @commands.hybrid_group(name="bank", description="Manage your bank", invoke_without_command=True)
    async def bank(self, ctx: commands.Context) -> None:
        if ctx.invoked_subcommand is None:
            account = await asyncio.to_thread(store.get_account, ctx.author.id)
            cost = store.bank_upgrade_cost(account.bank_level)
            await ctx.send(view=structured_card(
                "Your Bank",
                [
                    ("Current Bank", f"**Stored:** {money_code(account.bank)}\n**Capacity:** {money_code(account.bank_capacity)}\n**Level:** {number_code(account.bank_level)}"),
                    ("Next Expansion", f"**Cost:** {money_code(cost)}\nUse `/bank expand` to purchase it."),
                ],
            ))

    @bank.command(name="expand", description="Buy more bank capacity")
    async def bank_expand(self, ctx: commands.Context) -> None:
        before = await asyncio.to_thread(store.get_account, ctx.author.id)
        cost = store.bank_upgrade_cost(before.bank_level)
        try: updated, _ = await asyncio.to_thread(store.expand_bank, ctx.author.id)
        except InsufficientFunds:
            await ctx.send(view=structured_card(
                "Bank Expansion Unavailable",
                [
                    ("Upgrade Cost", money_code(cost)),
                    ("Your Wallet", money_code(before.wallet)),
                    ("Still Needed", money_code(max(0, cost-before.wallet))),
                ],
            )); return
        await ctx.send(view=structured_card(
            "Bank Expanded",
            [
                ("Upgrade", f"**Price paid:** {money_code(cost)}\n**New level:** {number_code(updated.bank_level)}"),
                ("New Capacity", money_code(updated.bank_capacity)),
                ("Wallet Remaining", money_code(updated.wallet)),
            ],
        ))

    @commands.hybrid_command(name="eco-profile", aliases=["ecoprof"], description="Show a user's economy profile")
    async def eco_profile(self, ctx: commands.Context, user: discord.User | None = None) -> None:
        target = user or ctx.author; account = await asyncio.to_thread(store.get_account, target.id)
        await ctx.send(view=structured_card(
            f"{target.display_name}'s Economy Profile",
            [
                ("Balances", account_section(account)),
                ("Streaks", f"**Daily streak:** {number_code(account.daily_streak, ' day(s)')}\n**Work streak:** {number_code(account.work_streak, ' successful shift(s)')}"),
                ("Activity", f"**Jobs attempted:** {number_code(account.work_count)}\n**Economy joined:** <t:{account.created_at}:D>"),
            ],
        ))

    @commands.hybrid_command(name="leaderboard", aliases=["lb", "top"], description="Show the richest economy users")
    @app_commands.choices(scope=SCOPE_CHOICES, ranking=RANKING_CHOICES)
    async def leaderboard(self, ctx: commands.Context, scope: str = "global", ranking: str = "net") -> None:
        scope_value = scope.lower(); rank_value = ranking.lower()
        if scope_value not in {"global", "server"} or rank_value not in {"net", "cash", "bank"}:
            await ctx.send("Scope must be `global` or `server`; ranking must be `net`, `cash`, or `bank`."); return
        if scope_value == "server" and ctx.guild is None:
            await ctx.send("The server leaderboard can only be used in a server.", ephemeral=True); return
        user_ids = [member.id for member in ctx.guild.members if not member.bot] if scope_value == "server" and ctx.guild else None
        rows = await asyncio.to_thread(store.leaderboard, user_ids, rank_value)
        if not rows:
            await ctx.send("There are no economy accounts on this leaderboard yet."); return
        lines = []
        for index, row in enumerate(rows, 1):
            user = await self.resolve_user(int(row["user_id"])); name = discord.utils.escape_markdown(user.display_name) if user else f"User {row['user_id']}"
            lines.append(f"**{index}. {name}**\n{money_code(int(row['score']))}")
        own_rank = await asyncio.to_thread(
            store.leaderboard_rank, ctx.author.id, user_ids, rank_value
        )
        own_note = (
            f"Your rank: #{own_rank[0]:,} · {money(own_rank[1])}"
            if own_rank
            else "Your rank: N/A"
        )
        await ctx.send(view=structured_card(
            f"{scope_value.title()} {rank_value.title()} Leaderboard",
            [("Rankings", "\n\n".join(lines))],
            note=f"{own_note} · Ranking by {rank_value} · {scope_value} scope",
        ))

    @commands.hybrid_command(
        name="giveaway",
        aliases=["gaw"],
        description="Start an economy-funded giveaway",
    )
    @commands.guild_only()
    @app_commands.guild_only()
    @app_commands.describe(
        amount="Total wallet amount to reserve as the prize pool",
        winners="Number of winners (1-20)",
        duration="Duration such as 30s, 10m, 2h, or 1d",
    )
    async def giveaway(
        self,
        ctx: commands.Context,
        amount: int,
        winners: int,
        duration: str,
    ) -> None:
        if amount <= 0:
            await ctx.send("Enter a positive prize amount.", ephemeral=True)
            return
        if not 1 <= winners <= 20:
            await ctx.send("Choose between 1 and 20 winners.", ephemeral=True)
            return
        if amount < winners:
            await ctx.send(
                "The prize pool must contain at least one unit per winner.",
                ephemeral=True,
            )
            return
        try:
            seconds = parse_giveaway_duration(duration)
        except ValueError:
            await ctx.send(
                "Use a duration from 10 seconds to 30 days, such as `30s`, `10m`, `2h`, or `1d`.",
                ephemeral=True,
            )
            return
        assert ctx.guild is not None and ctx.channel is not None
        ends_at = int(time.time()) + seconds
        try:
            giveaway_id = await asyncio.to_thread(
                store.create_giveaway,
                ctx.guild.id,
                ctx.channel.id,
                ctx.author.id,
                amount,
                winners,
                ends_at,
            )
        except InsufficientFunds:
            await ctx.send(
                "You do not have enough money in your wallet to reserve that prize.",
                ephemeral=True,
            )
            return
        row = await asyncio.to_thread(store.giveaway, giveaway_id)
        assert row is not None
        view = giveaway_view(self, row, 0)
        try:
            message = await ctx.send(view=view)
        except discord.HTTPException:
            await asyncio.to_thread(store.finish_giveaway, giveaway_id)
            raise
        await asyncio.to_thread(store.set_giveaway_message, giveaway_id, message.id)
        self.giveaway_views[giveaway_id] = view
        self.giveaway_tasks[giveaway_id] = asyncio.create_task(
            self._finish_giveaway_at(giveaway_id, ends_at)
        )

    @commands.hybrid_command(name="rob", aliases=["steal"], description="Attempt to steal money from another user's wallet")
    async def rob(self, ctx: commands.Context, user: discord.User) -> None:
        if user.bot or user.id == ctx.author.id:
            await ctx.send("Choose another real user to rob."); return
        robber_cd, shield, robber, target = await asyncio.to_thread(store.robbery_status, ctx.author.id, user.id)
        if robber_cd:
            await ctx.send(view=structured_card("Robbery Cooldown", [("Available Again", f"`{duration(robber_cd)}`")])); return
        if shield:
            await ctx.send(view=structured_card("Target Protected", [("Protection Remaining", f"`{duration(shield)}`")])); return
        if target.wallet < 1_000:
            await ctx.send("That user doesn't have enough wallet money to rob."); return
        if robber.net <= 0:
            await ctx.send("You need some money before risking a robbery fine."); return
        await ctx.send(
            "## Robbery\n"
            f"**Target:** {user.mention}\n"
            f"**Target wallet:** {money_code(target.wallet)}\n\n"
            f"**Maximum steal:** {number_code(30, '%')}\n"
            f"**Chance of being caught:** {number_code(15, '%')}\n\n"
            "Choose one hidden tile below.",
            view=RobView(ctx.author, user),
        )

    @commands.hybrid_group(name="economy", aliases=["eco"], description="Economy administration", invoke_without_command=True)
    async def economy(self, ctx: commands.Context) -> None:
        if ctx.invoked_subcommand is None:
            await ctx.send(view=card(
                "Economy Administration",
                "**Admins**\n"
                "`/economy admins list` · `/economy admins add` · `/economy admins remove`\n\n"
                "**Users**\n"
                "`/economy users add` · `/economy users take` · "
                "`/economy users reset` · `/economy users transactions`",
            ))

    @economy.group(name="admins", description="Manage economy administrators", invoke_without_command=True)
    async def economy_admins(self, ctx: commands.Context) -> None:
        if ctx.invoked_subcommand is None:
            await ctx.send(view=card(
                "Economy Administrators",
                "`/economy admins list` · `/economy admins add` · `/economy admins remove`",
            ))

    @economy_admins.command(name="list", description="List the bot's economy administrators")
    async def admin_list(self, ctx: commands.Context) -> None:
        if not await self.require_admin(ctx): return
        rows = await asyncio.to_thread(store.list_admins)
        items: list[discord.ui.Item] = [discord.ui.TextDisplay("## Economy Administrators")]
        application = await self.bot.application_info()
        owner = application.owner
        if isinstance(owner, discord.Team):
            owner = owner.owner
        if isinstance(owner, discord.abc.User):
            items.extend((
                discord.ui.Separator(),
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        f"**{discord.utils.escape_markdown(owner.display_name)}** · Owner\n"
                        f"**User ID:** `{owner.id}`"
                    ),
                    accessory=discord.ui.Thumbnail(owner.display_avatar.url),
                ),
            ))
        for row in rows:
            user_id = int(row["user_id"])
            user = await self.resolve_user(user_id)
            if user is None:
                name = "Unknown user"
                avatar_url = f"https://cdn.discordapp.com/embed/avatars/{(user_id >> 22) % 6}.png"
            else:
                name = discord.utils.escape_markdown(user.display_name)
                avatar_url = user.display_avatar.url
            items.extend((
                discord.ui.Separator(),
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        f"**{name}**\n**User ID:** `{user_id}`\n"
                        f"**Added:** <t:{int(row['added_at'])}:F> · <t:{int(row['added_at'])}:R>"
                    ),
                    accessory=discord.ui.Thumbnail(avatar_url),
                ),
            ))
        if not rows:
            items.extend((discord.ui.Separator(), discord.ui.TextDisplay("No additional economy admins.")))
        view = discord.ui.LayoutView()
        view.add_item(discord.ui.Container(*items))
        await ctx.send(view=view)

    @economy_admins.command(name="add", description="Add an economy administrator")
    async def admin_add(self, ctx: commands.Context, user: discord.User) -> None:
        if not await self.bot.can_use_owner_commands(ctx.author):
            await ctx.send("Only the bot owner can add economy admins.", ephemeral=True); return
        if user.bot:
            await ctx.send("Bots cannot be economy admins."); return
        added = await asyncio.to_thread(store.add_admin, user.id, ctx.author.id)
        await ctx.send(view=structured_card(
            "Economy Admin Updated",
            [("User", f"{user.mention}\n**User ID:** `{user.id}`"),
             ("Status", "`Added`" if added else "`Already an economy admin`")],
        ))

    @economy_admins.command(name="remove", description="Remove an economy administrator")
    async def admin_remove(self, ctx: commands.Context, user: discord.User) -> None:
        if not await self.bot.can_use_owner_commands(ctx.author):
            await ctx.send("Only the bot owner can remove economy admins.", ephemeral=True); return
        removed = await asyncio.to_thread(store.remove_admin, user.id)
        await ctx.send(view=structured_card(
            "Economy Admin Updated",
            [("User", f"{user.mention}\n**User ID:** `{user.id}`"),
             ("Status", "`Removed`" if removed else "`Was not an economy admin`")],
        ))

    @economy.group(name="users", description="Manage users' economy accounts", invoke_without_command=True)
    async def economy_users(self, ctx: commands.Context) -> None:
        if ctx.invoked_subcommand is None:
            await ctx.send(view=card(
                "Economy User Management",
                "`/economy users add` · `/economy users take` · "
                "`/economy users reset` · `/economy users transactions`",
            ))

    @economy_users.command(name="add", description="Add money to a user's wallet")
    async def economy_add(self, ctx: commands.Context, user: discord.User, amount: int, *, reason: str) -> None:
        if not await self.require_admin(ctx): return
        if amount <= 0:
            await ctx.send("Amount must be positive."); return
        account = await asyncio.to_thread(store.admin_change, user.id, amount, ctx.author.id, reason)
        await ctx.send(view=structured_card(
            "Money Added",
            [
                ("User", f"{user.mention}\n**User ID:** `{user.id}`"),
                ("Adjustment", f"**Amount added:** {money_code(amount)}\n**Reason:** {discord.utils.escape_markdown(reason)}"),
                ("Updated Account", account_section(account)),
            ],
        ))

    @economy_users.command(name="take", description="Remove money from a user's wallet")
    async def economy_take(self, ctx: commands.Context, user: discord.User, amount: int, *, reason: str) -> None:
        if not await self.require_admin(ctx): return
        if amount <= 0:
            await ctx.send("Amount must be positive."); return
        before = await asyncio.to_thread(store.get_account, user.id)
        account = await asyncio.to_thread(store.admin_change, user.id, amount, ctx.author.id, reason, take=True)
        removed = before.wallet - account.wallet
        await ctx.send(view=structured_card(
            "Money Removed",
            [
                ("User", f"{user.mention}\n**User ID:** `{user.id}`"),
                ("Adjustment", f"**Requested:** {money_code(amount)}\n**Actually removed:** {money_code(removed)}\n**Reason:** {discord.utils.escape_markdown(reason)}"),
                ("Updated Account", account_section(account)),
            ],
        ))

    @economy_users.command(name="reset", description="Reset a user's wallet, bank, or both")
    @app_commands.choices(location=RESET_CHOICES)
    async def economy_reset(self, ctx: commands.Context, user: discord.User, location: str, confirm: bool, *, reason: str) -> None:
        if not await self.require_admin(ctx): return
        location = location.lower()
        if location not in {"wallet", "bank", "both"}:
            await ctx.send("Location must be `wallet`, `bank`, or `both`."); return
        if not confirm:
            await ctx.send("Reset cancelled. Set `confirm` to true when you are certain."); return
        account = await asyncio.to_thread(store.reset, user.id, location, ctx.author.id, reason)
        await ctx.send(view=structured_card(
            "Economy Account Reset",
            [
                ("User", f"{user.mention}\n**User ID:** `{user.id}`"),
                ("Reset Details", f"**Area reset:** `{location.title()}`\n**Reason:** {discord.utils.escape_markdown(reason)}"),
                ("Updated Account", account_section(account)),
            ],
        ))

    @economy_users.command(name="transactions", description="Show a user's money history from the last seven days")
    @app_commands.describe(user="Another user to inspect; defaults to you")
    async def transactions(self, ctx: commands.Context, user: discord.User | None = None) -> None:
        target = user or ctx.author
        if target.id != ctx.author.id and not await self.require_admin(ctx): return
        rows = await asyncio.to_thread(store.transactions, 20, user_id=target.id)
        account = await asyncio.to_thread(store.get_account, target.id)
        if not rows:
            await ctx.send(view=structured_card(
                f"{target.display_name}'s Transactions",
                [
                    ("Current Account", account_section(account)),
                    ("History", "No recorded transactions in the last seven days."),
                ],
            )); return
        incoming = sum(int(row["amount"]) for row in rows if int(row["amount"]) > 0)
        outgoing = sum(-int(row["amount"]) for row in rows if int(row["amount"]) < 0)
        lines = []
        for row in rows:
            sign = "+" if int(row["amount"]) >= 0 else ""
            lines.append(
                f"### `{sign}{int(row['amount']):,}`\n{transaction_detail(row)}"
            )
        pages = ["\n\n".join(lines[index:index + 5]) for index in range(0, len(lines), 5)]
        view = TransactionPaginator(
            author_id=ctx.author.id,
            title=f"{target.display_name}'s Transactions",
            account=account_section(account),
            movement=f"**Money in:** {money_code(incoming)}\n**Money out:** {money_code(outgoing)}\n**Difference:** {money_code(incoming-outgoing)}",
            transaction_pages=pages,
            total=len(rows),
        )
        view.message = await ctx.send(view=view)

    @commands.hybrid_command(
        name="eco-history",
        description="Show your balance graph for the last seven days",
    )
    @app_commands.describe(user="Another user to inspect; defaults to you")
    async def eco_history(
        self, ctx: commands.Context, user: discord.User | None = None
    ) -> None:
        target = user or ctx.author
        if target.id != ctx.author.id and not await self.require_admin(ctx):
            return
        points = await asyncio.to_thread(store.daily_balance_history, target.id, 7)
        width, height = 900, 460
        image = Image.new("RGB", (width, height), "#111827")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=18)
        small = ImageFont.load_default(size=14)
        left, top, right, bottom = 80, 70, width - 35, height - 65
        values = [value for _, value in points]
        low, high = min(values), max(values)
        span = max(1, high - low)
        draw.text((35, 22), f"{target.display_name}'s 7-day balance", fill="#f9fafb", font=font)
        for step in range(5):
            y = top + (bottom - top) * step / 4
            value = high - span * step / 4
            draw.line((left, y, right, y), fill="#334155", width=1)
            draw.text((8, y - 8), f"{int(value):,}", fill="#94a3b8", font=small)
        coords = []
        for index, (timestamp, value) in enumerate(points):
            x = left + (right - left) * index / max(1, len(points) - 1)
            y = bottom - (bottom - top) * (value - low) / span
            coords.append((x, y))
            label = time.strftime("%a", time.localtime(timestamp))
            draw.text((x - 12, bottom + 14), label, fill="#94a3b8", font=small)
        if len(coords) > 1:
            draw.line(coords, fill="#60a5fa", width=5, joint="curve")
        for (x, y), value in zip(coords, values):
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill="#93c5fd")
            draw.text((x - 20, y - 27), f"{value:,}", fill="#e0f2fe", font=small)
        output = io.BytesIO()
        image.save(output, "PNG")
        output.seek(0)
        await ctx.send(file=discord.File(output, filename="economy-history.png"))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Economy(bot))
