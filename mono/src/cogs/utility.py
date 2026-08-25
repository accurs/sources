from __future__ import annotations

import array
import asyncio
import base64
import hashlib
import html
import io
import json
import os
import re
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import quote

import aiohttp
import discord
import edge_tts
import imageio_ffmpeg
from discord import app_commands
from discord.ext import commands
from src.cogs.owner import owner_clearance

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DICTIONARY_CACHE_DIR = PROJECT_ROOT / ".cache" / "dictionary"
VOICE_CACHE_VERSION = 2
WORD_OF_THE_DAY_CACHE = DICTIONARY_CACHE_DIR / "word_of_the_day.json"
WORD_OF_THE_DAY_HISTORY = DICTIONARY_CACHE_DIR / "word_of_the_day_history.json"


def _cache_key(word: str) -> str:
    return hashlib.sha256(word.strip().casefold().encode("utf-8")).hexdigest()


def _read_dictionary_cache(word: str) -> list[dict] | None:
    path = DICTIONARY_CACHE_DIR / "entries" / f"{_cache_key(word)}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, list) and data else None


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(data)
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_dictionary_cache(word: str, entries: list[dict]) -> None:
    path = DICTIONARY_CACHE_DIR / "entries" / f"{_cache_key(word)}.json"
    _atomic_write(
        path,
        json.dumps(entries, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
    )


def _plain_html(text: object) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", str(text or ""))).strip()


def _parse_word_of_the_day(page_html: str) -> dict[str, str] | None:
    match = re.search(
        r'<script\s+id="WordOfTheDayModal-props"[^>]*>(.*?)</script>',
        page_html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return None
    try:
        raw = json.loads(match.group(1))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or not raw.get("headword"):
        return None
    pronunciation = raw.get("pronunciation") or {}
    phonetic = pronunciation.get("phonetic") or {}
    return {
        "id": str(raw.get("id") or ""),
        "word": _plain_html(raw.get("headword")),
        "date": _plain_html(raw.get("displayDate")),
        "phonetic": _plain_html(phonetic.get("html")),
        "part": _plain_html(raw.get("partOfSpeech")),
        "definition": _plain_html(raw.get("definition")),
        "explanation": _plain_html(raw.get("body")),
        "example": _plain_html(raw.get("exampleSentence")),
        "url": "https://www.dictionary.com/e/word-of-the-day/"
        + quote(str(raw.get("slug") or raw.get("headword")), safe="-"),
    }


def _read_word_of_the_day_cache() -> dict[str, str] | None:
    try:
        data = json.loads(WORD_OF_THE_DAY_CACHE.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    today_id = date.today().strftime("%Y%m%d")
    return data if isinstance(data, dict) and data.get("id") == today_id else None


def _write_word_of_the_day_cache(data: dict[str, str]) -> None:
    _atomic_write(
        WORD_OF_THE_DAY_CACHE,
        json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
    )
    try:
        history = json.loads(WORD_OF_THE_DAY_HISTORY.read_text(encoding="utf-8"))
        if not isinstance(history, list): history = []
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        history = []
    history = [item for item in history if isinstance(item, dict) and item.get("id") != data.get("id")]
    history.insert(0, data)
    _atomic_write(
        WORD_OF_THE_DAY_HISTORY,
        json.dumps(history[:7], ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
    )


def _datamuse_dictionary_entries(word: str, results: object) -> list[dict]:
    """Convert Datamuse definitions into the dictionary command's usual format."""
    if not isinstance(results, list):
        return []

    part_names = {
        "n": "noun",
        "v": "verb",
        "adj": "adjective",
        "adv": "adverb",
        "u": "",
    }
    meanings: dict[str, list[dict[str, str]]] = {}
    display_word = word
    for result in results:
        if not isinstance(result, dict):
            continue
        result_word = str(result.get("word") or "").strip()
        if result_word.casefold() != word.casefold():
            continue
        display_word = result_word or word
        for raw_definition in result.get("defs") or []:
            definition = str(raw_definition).strip()
            part = ""
            if "\t" in definition:
                code, definition = definition.split("\t", 1)
                part = part_names.get(code.strip(), code.strip())
            definition = definition.strip()
            if definition:
                meanings.setdefault(part, []).append({"definition": definition})

    return [
        {
            "_source": "Datamuse",
            "word": display_word,
            "phonetic": "",
            "phonetics": [],
            "meanings": [
                {"partOfSpeech": part, "definitions": definitions}
                for part, definitions in meanings.items()
            ],
        }
    ] if meanings else []


def _read_urban_cache(term: str) -> list[dict] | None:
    path = DICTIONARY_CACHE_DIR / "urban" / f"{_cache_key(term)}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, list) and data else None


def _write_urban_cache(term: str, entries: list[dict]) -> None:
    path = DICTIONARY_CACHE_DIR / "urban" / f"{_cache_key(term)}.json"
    _atomic_write(
        path,
        json.dumps(entries, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
    )


def _format_urban_text(text: str) -> str:
    """Remove Urban link markup and neutralise links and unwanted mentions."""
    text = text.strip()
    if len(text) >= 2 and text.startswith("*") and text.endswith("*"):
        text = text[1:-1].strip()
    text = text.replace("@", "@\u200b")
    text = re.sub(r"\[([^\[\]]+)]", lambda match: match.group(1).strip(), text)
    # A zero-width separator keeps domains readable while preventing Discord
    # from turning user-submitted URLs into clickable links.
    return re.sub(r"(?<=\w)\.(?=\w)", ".\u200b", text)


def _read_voice_cache(word: str) -> tuple[bytes, float, str] | None:
    key = _cache_key(word)
    audio_path = DICTIONARY_CACHE_DIR / "voice" / f"{key}.ogg"
    metadata_path = DICTIONARY_CACHE_DIR / "voice" / f"{key}.json"
    try:
        audio = audio_path.read_bytes()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("version") != VOICE_CACHE_VERSION:
            return None
        duration = float(metadata["duration"])
        waveform = str(metadata["waveform"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
    if not audio.startswith(b"OggS") or duration <= 0 or not waveform:
        return None
    return audio, duration, waveform


def _write_voice_cache(
    word: str,
    audio: bytes,
    duration: float,
    waveform: str,
) -> None:
    key = _cache_key(word)
    directory = DICTIONARY_CACHE_DIR / "voice"
    _atomic_write(directory / f"{key}.ogg", audio)
    _atomic_write(
        directory / f"{key}.json",
        json.dumps(
            {
                "version": VOICE_CACHE_VERSION,
                "duration": duration,
                "waveform": waveform,
            },
            separators=(",", ":"),
        ).encode("utf-8"),
    )


def _read_pronunciation_cache(word: str) -> bytes | None:
    path = DICTIONARY_CACHE_DIR / "pronunciation" / f"{_cache_key(word)}.mp3"
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return data if len(data) > 1000 else None


def _write_pronunciation_cache(word: str, data: bytes) -> None:
    path = DICTIONARY_CACHE_DIR / "pronunciation" / f"{_cache_key(word)}.mp3"
    _atomic_write(path, data)


def _split_lines(lines: list[str], limit: int = 3500) -> list[str]:
    chunks: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}".strip()
        if current and len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


async def _generate_pronunciation(word: str) -> bytes:
    audio = bytearray()
    speech = edge_tts.Communicate(word, "en-US-AriaNeural")
    async for chunk in speech.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
    if not audio:
        raise RuntimeError("speech generator returned no audio")
    return bytes(audio)


def _prepare_voice_message(audio_data: bytes) -> tuple[bytes, float, str]:
    """Prepare Discord-compatible OGG/Opus audio and build its waveform."""
    with tempfile.TemporaryDirectory(prefix="dictionary-voice-") as directory:
        source_path = os.path.join(directory, "source-audio")
        voice_path = os.path.join(directory, "voice-message.ogg")
        with open(source_path, "wb") as source:
            source.write(audio_data)

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        if audio_data.startswith(b"OggS"):
            ogg_data = audio_data
        else:
            subprocess.run(
                [
                    ffmpeg,
                    "-loglevel",
                    "error",
                    "-i",
                    source_path,
                    "-ac",
                    "1",
                    "-ar",
                    "48000",
                    "-c:a",
                    "libopus",
                    "-b:a",
                    "32k",
                    "-vbr",
                    "off",
                    "-application",
                    "voip",
                    "-frame_duration",
                    "20",
                    voice_path,
                ],
                check=True,
                capture_output=True,
            )
            with open(voice_path, "rb") as voice:
                ogg_data = voice.read()
        pcm = subprocess.run(
            [
                ffmpeg,
                "-loglevel",
                "error",
                "-i",
                source_path,
                "-ac",
                "1",
                "-ar",
                "48000",
                "-f",
                "s16le",
                "pipe:1",
            ],
            check=True,
            capture_output=True,
        ).stdout
    samples = array.array("h")
    samples.frombytes(pcm)
    duration = max(len(samples) / 48000, 0.01)
    # Discord clients sample voice-message waveforms at most once per 100 ms.
    # Keeping the metadata density aligned with the clip duration avoids a
    # malformed-looking waveform on short generated speech.
    point_count = min(256, max(1, round(duration * 10)), len(samples))
    chunk_size = max(1, len(samples) // point_count)
    amplitudes = []
    for start in range(0, len(samples), chunk_size):
        chunk = samples[start : start + chunk_size]
        amplitudes.append(max(abs(value) for value in chunk))
        if len(amplitudes) == point_count:
            break
    peak = max(amplitudes, default=1) or 1
    waveform = bytes(round(value / peak * 255) for value in amplitudes)
    return ogg_data, duration, base64.b64encode(waveform).decode("ascii")


async def _send_voice_message(
    interaction: discord.Interaction,
    word: str,
) -> None:
    audio = await asyncio.to_thread(_read_pronunciation_cache, word)
    if audio is None:
        audio = await _generate_pronunciation(word)
        await asyncio.to_thread(_write_pronunciation_cache, word, audio)

    safe_word = re.sub(r"[^A-Za-z0-9_-]+", "-", word).strip("-")
    audio_file = discord.File(
        io.BytesIO(audio),
        filename=f"{safe_word or 'pronunciation'}.mp3",
    )
    is_ephemeral = bool(
        interaction.message is not None
        and interaction.message.flags.ephemeral
    )
    await interaction.followup.send(
        file=audio_file,
        ephemeral=is_ephemeral,
    )


class DictionaryView(discord.ui.LayoutView):
    actions = discord.ui.ActionRow()

    def __init__(self, *, author_id: int, pages: list[dict[str, str]]) -> None:
        super().__init__(timeout=300)
        self.author_id = author_id
        self.pages = pages
        self.index = 0
        self.pronunciation_sent = False
        self._refresh()

    def _refresh(self) -> None:
        page = self.pages[self.index]
        details = [value for value in (page["phonetic"], page["part"]) if value]
        heading = f"## {page['word']}"
        if details:
            heading += "\n-# " + " · ".join(details)
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(self.pages) - 1
        self.counter.label = f"{self.index + 1} / {len(self.pages)}"
        self.clear_items()
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(heading),
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"### Definition\n{page['definition'][:1400]}"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"### Example\n*{page['example'][:1200]}*"),
                discord.ui.Separator(),
                self.actions,
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"-# Source: {page['source']}"),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This dictionary panel belongs to someone else.",
            ephemeral=True,
        )
        return False

    @actions.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self.index -= 1
        self._refresh()
        await interaction.response.edit_message(view=self)

    @actions.button(label="1 / 1", style=discord.ButtonStyle.secondary, disabled=True)
    async def counter(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        pass

    @actions.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self.index += 1
        self._refresh()
        await interaction.response.edit_message(view=self)

    @actions.button(label="Pronounce", style=discord.ButtonStyle.primary)
    async def pronounce(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if self.pronunciation_sent:
            await interaction.response.send_message(
                "The pronunciation was already sent.",
                ephemeral=True,
            )
            return

        # Set this before the first await so simultaneous clicks cannot send
        # duplicate audio messages.
        self.pronunciation_sent = True
        self.pronounce.disabled = True
        self.pronounce.label = "Pronounced"
        await interaction.response.edit_message(view=self)
        try:
            await _send_voice_message(interaction, self.pages[self.index]["word"])
        except Exception:
            self.pronunciation_sent = False
            self.pronounce.disabled = False
            self.pronounce.label = "Pronounce"
            if interaction.message is not None:
                await interaction.message.edit(view=self)
            await interaction.followup.send(
                "I couldn't generate the voice pronunciation.",
                ephemeral=True,
            )
            return


class WordOfTheDayPronounceButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Pronounce", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, WordOfTheDayView):
            return
        self.disabled = True
        self.label = "Pronounced"
        await interaction.response.edit_message(view=view)
        try:
            await _send_voice_message(interaction, view.word)
        except Exception:
            self.disabled = False
            self.label = "Pronounce"
            if interaction.message is not None:
                await interaction.message.edit(view=view)
            await interaction.followup.send(
                "I couldn't generate the voice pronunciation.", ephemeral=True
            )


class WordOfTheDayView(discord.ui.LayoutView):
    def __init__(self, *, author_id: int, data: dict[str, str]) -> None:
        super().__init__(timeout=300)
        self.author_id = author_id
        self.word = data["word"]
        details = " · ".join(
            value for value in (data.get("phonetic"), data.get("part")) if value
        )
        heading = f"## {self.word}\n-# {data['date']}"
        if details:
            heading += f" · {details}"
        items: list[discord.ui.Item] = [
            discord.ui.TextDisplay(heading),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"### Definition\n{data['definition'][:1200]}"),
        ]
        if data.get("explanation"):
            items.extend(
                [
                    discord.ui.Separator(),
                    discord.ui.TextDisplay(
                        f"### Explanation\n{data['explanation'][:1500]}"
                    ),
                ]
            )
        if data.get("example"):
            items.extend(
                [
                    discord.ui.Separator(),
                    discord.ui.TextDisplay(f"### Example\n*{data['example'][:1000]}*"),
                ]
            )
        items.extend(
            [
                discord.ui.Separator(),
                discord.ui.ActionRow(
                    WordOfTheDayPronounceButton(),
                    discord.ui.Button(
                        label="Dictionary.com",
                        style=discord.ButtonStyle.link,
                        url=data["url"],
                    ),
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay("-# Word of the Day by Dictionary.com"),
            ]
        )
        self.add_item(discord.ui.Container(*items))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This Word of the Day panel belongs to someone else.", ephemeral=True
        )
        return False


class UrbanDictionaryView(discord.ui.LayoutView):
    actions = discord.ui.ActionRow()

    def __init__(self, *, author_id: int, pages: list[dict[str, str]]) -> None:
        super().__init__(timeout=300)
        self.author_id = author_id
        self.pages = pages
        self.index = 0
        self._refresh()

    def _refresh(self) -> None:
        page = self.pages[self.index]
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(self.pages) - 1
        self.counter.label = f"{self.index + 1} / {len(self.pages)}"
        votes = f"👍 {page['up']} · 👎 {page['down']}"
        heading = f"## {page['word']}"
        example_lines = [
            line.strip() if line.strip() else ""
            for line in page["example"].splitlines()
        ]
        while example_lines and not example_lines[0]:
            example_lines.pop(0)
        while example_lines and not example_lines[-1]:
            example_lines.pop()
        example = ">>> " + "\n".join(example_lines)
        self.clear_items()
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(heading),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"### Definition\n{page['definition'][:1600]}"
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"### Example\n{example[:1100]}"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"-# {votes}"),
                discord.ui.Separator(),
                self.actions,
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This Urban Dictionary panel belongs to someone else.",
            ephemeral=True,
        )
        return False

    @actions.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self.index -= 1
        self._refresh()
        await interaction.response.edit_message(view=self)

    @actions.button(label="1 / 1", style=discord.ButtonStyle.secondary, disabled=True)
    async def counter(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        pass

    @actions.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self.index += 1
        self._refresh()
        await interaction.response.edit_message(view=self)


class UserInfoView(discord.ui.LayoutView):
    actions = discord.ui.ActionRow()

    def __init__(
        self,
        *,
        author_id: int,
        avatar_url: str,
        banner_url: str | None,
        permissions: list[str],
        items: list[discord.ui.Item],
    ) -> None:
        super().__init__(timeout=180)
        self.author_id = author_id
        self.avatar_url = avatar_url
        self.banner_url = banner_url
        self.permissions = permissions
        self.banner.disabled = banner_url is None
        self.permissions_button.disabled = not permissions
        self.clear_items()
        self.add_item(discord.ui.Container(*items, self.actions))

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This user panel belongs to someone else.",
            ephemeral=True,
        )
        return False

    @actions.button(label="Avatar", style=discord.ButtonStyle.secondary)
    async def avatar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_message(
            f"[Open original avatar]({self.avatar_url})",
            ephemeral=True,
        )

    @actions.button(label="Banner", style=discord.ButtonStyle.secondary)
    async def banner(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if self.banner_url is None:
            await interaction.response.send_message(
                "This user does not have a banner.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"[Open original banner]({self.banner_url})",
            ephemeral=True,
        )

    @actions.button(label="Permissions", style=discord.ButtonStyle.secondary)
    async def permissions_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not self.permissions:
            await interaction.response.send_message(
                "No server permissions are available for this user.",
                ephemeral=True,
            )
            return

        chunks = _split_lines([f"• {permission}" for permission in self.permissions])
        view = discord.ui.LayoutView()
        for index, chunk in enumerate(chunks):
            heading = "## Server Permissions\n" if index == 0 else ""
            view.add_item(
                discord.ui.Container(discord.ui.TextDisplay(f"{heading}{chunk}"))
            )
        await interaction.response.send_message(view=view, ephemeral=True)


class ApplicationEmojiListView(discord.ui.LayoutView):
    navigation = discord.ui.ActionRow()

    def __init__(self, *, author_id: int, emojis: list[discord.Emoji]) -> None:
        super().__init__(timeout=180)
        self.author_id = author_id
        self.pages = [emojis[index : index + 20] for index in range(0, len(emojis), 20)]
        self.index = 0
        self._refresh()

    def _refresh(self) -> None:
        self.clear_items()
        page = self.pages[self.index]
        lines = [f"{emoji} `{emoji.name}` · `{emoji.id}`" for emoji in page]
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(self.pages) - 1
        self.counter.label = f"{self.index + 1} / {len(self.pages)}"
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"## Bot Application Emojis\n-# {sum(map(len, self.pages))} total"
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay("\n".join(lines)),
                discord.ui.Separator(),
                self.navigation,
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This emoji list belongs to someone else.", ephemeral=True
        )
        return False

    @navigation.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.index -= 1
        self._refresh()
        await interaction.response.edit_message(view=self)

    @navigation.button(label="1 / 1", style=discord.ButtonStyle.secondary, disabled=True)
    async def counter(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        pass

    @navigation.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.index += 1
        self._refresh()
        await interaction.response.edit_message(view=self)


class Utility(commands.Cog):
    application_emojis = app_commands.Group(
        name="bot-emojis",
        description="View and manage the bot's application emojis",
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._autocomplete_cache: dict[
            tuple[str, str], list[app_commands.Choice[str]]
        ] = {}

    @commands.command(name="pin", aliases=["unpin"], description="Pin or unpin the message you replied to")
    @commands.guild_only()
    @commands.bot_has_guild_permissions(manage_messages=True)
    async def pin_message(self, ctx: commands.Context) -> None:
        reference = ctx.message.reference if ctx.message else None
        message = reference.resolved if reference else None
        if not isinstance(message, discord.Message) and reference and reference.message_id:
            try:
                message = await ctx.channel.fetch_message(reference.message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                message = None
        if not isinstance(message, discord.Message):
            await ctx.send("Reply to the message you want to pin or unpin.", ephemeral=True)
            return
        try:
            if message.pinned:
                await message.unpin(reason=f"Requested by {ctx.author} ({ctx.author.id})")
                action = "Unpinned"
            else:
                await message.pin(reason=f"Requested by {ctx.author} ({ctx.author.id})")
                action = "Pinned"
        except discord.HTTPException:
            await ctx.send("I could not change that message's pin status.", ephemeral=True)
            return
        await ctx.send(f"{action} [that message]({message.jump_url}).", ephemeral=ctx.interaction is not None)

    async def _emoji_owner_check(self, interaction: discord.Interaction) -> bool:
        if await self.bot.can_use_owner_commands(interaction.user):
            return True
        await interaction.response.send_message(
            "Only the bot owner can manage application emojis.", ephemeral=True
        )
        return False

    async def _application_emoji_choices(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if not await self.bot.can_use_owner_commands(interaction.user):
            return []
        try:
            emojis = await self.bot.fetch_application_emojis()
        except discord.HTTPException:
            return []
        query = current.strip().casefold()
        matches = [emoji for emoji in emojis if query in emoji.name.casefold()]
        matches.sort(key=lambda emoji: emoji.name.casefold())
        return [
            app_commands.Choice(name=emoji.name, value=str(emoji.id))
            for emoji in matches[:25]
        ]

    async def _find_application_emoji(self, value: str) -> discord.Emoji | None:
        query = value.strip().casefold()
        emojis = await self.bot.fetch_application_emojis()
        return discord.utils.find(
            lambda emoji: str(emoji.id) == query or emoji.name.casefold() == query,
            emojis,
        )

    @application_emojis.command(name="list", description="Show all bot application emojis")
    async def application_emojis_list(
        self,
        interaction: discord.Interaction,
        ephemeral: bool = False,
    ) -> None:
        if not await self._emoji_owner_check(interaction):
            return
        await interaction.response.defer(ephemeral=ephemeral)
        try:
            emojis = await self.bot.fetch_application_emojis()
        except discord.HTTPException:
            await interaction.followup.send(
                "Discord couldn't load the bot's application emojis.", ephemeral=True
            )
            return
        emojis.sort(key=lambda emoji: emoji.name.casefold())
        if not emojis:
            await interaction.followup.send(
                "The bot does not have any application emojis yet.",
                ephemeral=ephemeral,
            )
            return
        await interaction.followup.send(
            view=ApplicationEmojiListView(
                author_id=interaction.user.id,
                emojis=emojis,
            ),
            ephemeral=ephemeral,
        )

    @application_emojis.command(name="add", description="Upload a new bot application emoji")
    @app_commands.describe(name="Emoji name", image="PNG, JPG, GIF, WebP, or AVIF")
    async def application_emojis_add(
        self,
        interaction: discord.Interaction,
        name: str,
        image: discord.Attachment,
        ephemeral: bool = False,
    ) -> None:
        if not await self._emoji_owner_check(interaction):
            return
        if not re.fullmatch(r"[A-Za-z0-9_]{2,32}", name):
            await interaction.response.send_message(
                "Emoji names must be 2–32 letters, numbers, or underscores.",
                ephemeral=True,
            )
            return
        allowed_types = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/avif"}
        if image.content_type not in allowed_types or image.size > 256 * 1024:
            await interaction.response.send_message(
                "Use a PNG, JPG, GIF, WebP, or AVIF file no larger than 256 KiB.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=ephemeral)
        try:
            created = await self.bot.create_application_emoji(
                name=name,
                image=await image.read(),
            )
        except discord.HTTPException as error:
            await interaction.followup.send(
                f"Discord couldn't create that emoji: `{error}`", ephemeral=True
            )
            return
        self.bot._application_badge_emojis = None
        await interaction.followup.send(
            f"Created {created} as `{created.name}`.", ephemeral=ephemeral
        )

    @application_emojis.command(name="rename", description="Rename a bot application emoji")
    @app_commands.describe(emoji="Emoji name or ID", new_name="The new emoji name")
    async def application_emojis_rename(
        self,
        interaction: discord.Interaction,
        emoji: str,
        new_name: str,
        ephemeral: bool = False,
    ) -> None:
        if not await self._emoji_owner_check(interaction):
            return
        if not re.fullmatch(r"[A-Za-z0-9_]{2,32}", new_name):
            await interaction.response.send_message(
                "Emoji names must be 2–32 letters, numbers, or underscores.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=ephemeral)
        try:
            selected = await self._find_application_emoji(emoji)
            if selected is None:
                await interaction.followup.send("That emoji was not found.", ephemeral=True)
                return
            old_name = selected.name
            renamed = await selected.edit(name=new_name)
        except discord.HTTPException as error:
            await interaction.followup.send(
                f"Discord couldn't rename that emoji: `{error}`", ephemeral=True
            )
            return
        self.bot._application_badge_emojis = None
        await interaction.followup.send(
            f"Renamed `{old_name}` to {renamed} `{renamed.name}`.", ephemeral=ephemeral
        )

    @application_emojis_rename.autocomplete("emoji")
    async def application_emojis_rename_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._application_emoji_choices(interaction, current)

    @application_emojis.command(name="delete", description="Delete a bot application emoji")
    @app_commands.describe(emoji="Emoji name or ID")
    async def application_emojis_delete(
        self,
        interaction: discord.Interaction,
        emoji: str,
        ephemeral: bool = False,
    ) -> None:
        if not await self._emoji_owner_check(interaction):
            return
        await interaction.response.defer(ephemeral=ephemeral)
        try:
            selected = await self._find_application_emoji(emoji)
            if selected is None:
                await interaction.followup.send("That emoji was not found.", ephemeral=True)
                return
            name = selected.name
            await selected.delete()
        except discord.HTTPException as error:
            await interaction.followup.send(
                f"Discord couldn't delete that emoji: `{error}`", ephemeral=True
            )
            return
        self.bot._application_badge_emojis = None
        await interaction.followup.send(
            f"Deleted `{name}`.", ephemeral=ephemeral
        )

    @application_emojis_delete.autocomplete("emoji")
    async def application_emojis_delete_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._application_emoji_choices(interaction, current)

    @commands.hybrid_command(name="ping", aliases=["latency"], description="Check the bot's latency")
    async def ping(
        self,
        ctx: commands.Context,
        ephemeral: bool = False,
    ) -> None:
        latency = round(self.bot.latency * 1000)

        view = discord.ui.LayoutView()
        container = discord.ui.Container(
            discord.ui.TextDisplay("### Pong!"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"Latency: `{latency}ms`"),
        )

        view.add_item(container)
        await ctx.send(view=view)

    @commands.hybrid_command(
        name="getinvite",
        aliases=["invite", "inv"],
        description="Get a server invite or an app installation link",
    )
    @app_commands.describe(invite_type="The kind of invite to create")
    @app_commands.choices(
        invite_type=[
            app_commands.Choice(name="Server", value="server"),
            app_commands.Choice(name="Guild install", value="guild"),
            app_commands.Choice(name="User install", value="user"),
        ]
    )
    async def getinvite(
        self,
        ctx: commands.Context,
        invite_type: str,
        ephemeral: bool = False,
    ) -> None:
        if invite_type not in {"server", "guild", "user"}:
            await ctx.send("Choose Server, Guild install, or User install.")
            return
        if invite_type == "server":
            if ctx.guild is None:
                await ctx.send(
                    "The Server invite option can only be used inside a server.",
                    ephemeral=True,
                )
                return
            if self.bot.get_guild(ctx.guild.id) is None:
                await ctx.send(
                    "I need to be installed in this server before I can create an "
                    "invite. Use the Guild install option first.",
                    ephemeral=True,
                )
                return
            if not isinstance(ctx.channel, discord.abc.GuildChannel):
                await ctx.send(
                    "I can't create a server invite from this type of channel.",
                    ephemeral=True,
                )
                return
            if not ctx.channel.permissions_for(ctx.author).create_instant_invite:
                await ctx.send(
                    "You don't have permission to create invites in this channel.",
                    ephemeral=True,
                )
                return
            try:
                invite = await ctx.channel.create_invite(
                    max_age=0,
                    max_uses=0,
                    unique=False,
                    reason=f"Requested through /getinvite by {ctx.author}",
                )
            except discord.Forbidden:
                await ctx.send(
                    "I don't have permission to create an invite in this channel.",
                    ephemeral=True,
                )
                return
            except discord.HTTPException:
                await ctx.send(
                    "Discord couldn't create the server invite right now.",
                    ephemeral=True,
                )
                return
            label = f"Join {ctx.guild.name}"
            url = invite.url
            description = "Share this link to invite someone to this server."
        else:
            application_id = self.bot.application_id
            if application_id is None and self.bot.user is not None:
                application_id = self.bot.user.id
            if application_id is None:
                await ctx.send(
                    "The bot's application ID isn't available yet. Try again shortly.",
                    ephemeral=ephemeral,
                )
                return
            integration_type = 0 if invite_type == "guild" else 1
            if invite_type == "guild":
                url = (
                    "https://discord.com/oauth2/authorize?"
                    f"client_id={application_id}"
                    "&scope=bot%20applications.commands"
                    "&permissions=8"
                    f"&integration_type={integration_type}"
                )
                label = "Install to a server"
                description = (
                    "Add the bot and its commands to a Discord server with "
                    "Administrator permission."
                )
            else:
                url = (
                    "https://discord.com/oauth2/authorize?"
                    f"client_id={application_id}"
                    "&scope=applications.commands"
                    f"&integration_type={integration_type}"
                )
                label = "Install to your account"
                description = (
                    "Add the app's commands to your Discord account. Discord limits "
                    "user installs to application commands."
                )

        view = discord.ui.LayoutView(timeout=180)
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## {label}\n{description}"),
                discord.ui.Separator(),
                discord.ui.ActionRow(
                    discord.ui.Button(
                        label=label,
                        style=discord.ButtonStyle.link,
                        url=url,
                    )
                ),
            )
        )
        await ctx.send(view=view, ephemeral=ephemeral)

    @commands.hybrid_command(
        name="word-of-the-day",
        aliases=["wotd"],
        description="Show today's Dictionary.com Word of the Day",
    )
    async def word_of_the_day(
        self,
        ctx: commands.Context,
        ephemeral: bool = False,
    ) -> None:
        await ctx.defer(ephemeral=ephemeral)
        data = await asyncio.to_thread(_read_word_of_the_day_cache)
        if data is None:
            timeout = aiohttp.ClientTimeout(total=12)
            headers = {"User-Agent": "Mozilla/5.0 DiscordWordOfTheDayBot/1.0"}
            try:
                async with aiohttp.ClientSession(
                    timeout=timeout, headers=headers
                ) as session:
                    async with session.get(
                        "https://www.dictionary.com/word-of-the-day"
                    ) as response:
                        response.raise_for_status()
                        page_html = await response.text()
                data = _parse_word_of_the_day(page_html)
            except (aiohttp.ClientError, TimeoutError, UnicodeError):
                data = None
            if data is None:
                await ctx.send(
                    "Dictionary.com's Word of the Day is unavailable right now. "
                    "Try again shortly."
                )
                return
            await asyncio.to_thread(_write_word_of_the_day_cache, data)

        # Also keeps a rolling seven-day history, including older cache files.
        await asyncio.to_thread(_write_word_of_the_day_cache, data)

        await ctx.send(
            view=WordOfTheDayView(author_id=ctx.author.id, data=data)
        )

    @commands.hybrid_command(
        name="dictionary",
        aliases=["define", "dict"],
        description="Look up an English word and hear its pronunciation",
    )
    @app_commands.describe(word="The English word to look up")
    async def dictionary(
        self,
        ctx: commands.Context,
        word: str,
        ephemeral: bool = False,
    ) -> None:
        query = word.strip()
        if not query or len(query) > 100:
            await ctx.send("Enter an English word between 1 and 100 characters.")
            return

        await ctx.defer(ephemeral=ephemeral)
        entries = await asyncio.to_thread(_read_dictionary_cache, query)
        # Cache files created before source labels existed cannot reliably tell
        # DictionaryAPI and Datamuse apart. Refresh each legacy entry once so
        # its footer is accurate, then save it back in the new format.
        if entries and not all(
            isinstance(entry, dict) and entry.get("_source")
            for entry in entries
        ):
            entries = None
        if entries is None:
            endpoint = "https://api.dictionaryapi.dev/api/v2/entries/en/" + quote(
                query, safe=""
            )
            timeout = aiohttp.ClientTimeout(total=12)
            headers = {"User-Agent": "DiscordDictionaryBot/1.0"}
            primary_available = True
            fallback_available = True
            async with aiohttp.ClientSession(
                timeout=timeout,
                headers=headers,
            ) as session:
                try:
                    async with session.get(endpoint) as response:
                        if response.status == 404:
                            entries = []
                        else:
                            response.raise_for_status()
                            entries = await response.json()
                            if not isinstance(entries, list):
                                raise ValueError("dictionary returned an invalid response")
                            for entry in entries:
                                if isinstance(entry, dict):
                                    entry["_source"] = "DictionaryAPI"
                except (aiohttp.ClientError, TimeoutError, ValueError):
                    primary_available = False
                    entries = []

                if not entries:
                    try:
                        async with session.get(
                            "https://api.datamuse.com/words",
                            params={"sp": query, "md": "d", "max": "5"},
                        ) as response:
                            response.raise_for_status()
                            results = await response.json()
                        entries = _datamuse_dictionary_entries(query, results)
                    except (aiohttp.ClientError, TimeoutError, ValueError):
                        fallback_available = False

            if entries:
                await asyncio.to_thread(_write_dictionary_cache, query, entries)
            elif not primary_available and not fallback_available:
                await ctx.send(
                    "Both dictionary services are unavailable right now. Try again shortly."
                )
                return
            else:
                await ctx.send(f"I couldn't find an entry for **{query}**.")
                return

        pages: list[dict[str, str]] = []
        seen_definitions = set()
        for entry in entries:
            source = str(entry.get("_source") or "DictionaryAPI")
            phonetic = str(entry.get("phonetic") or "")
            if not phonetic:
                phonetic = next(
                    (
                        str(item.get("text") or "")
                        for item in entry.get("phonetics", [])
                        if item.get("text")
                    ),
                    "",
                )
            display_word = str(entry.get("word") or query)
            for meaning in entry.get("meanings", []):
                part = str(meaning.get("partOfSpeech") or "").title()
                for definition in meaning.get("definitions", []):
                    definition_text = str(definition.get("definition") or "").strip()
                    if not definition_text:
                        continue
                    dedupe_key = (part.casefold(), definition_text.casefold())
                    if dedupe_key in seen_definitions:
                        continue
                    seen_definitions.add(dedupe_key)
                    pages.append(
                        {
                            "word": display_word,
                            "phonetic": phonetic,
                            "part": part,
                            "source": source,
                            "definition": definition_text,
                            "example": str(
                                definition.get("example")
                                or "No example was provided for this definition."
                            ),
                        }
                    )

        if not pages:
            await ctx.send(f"No usable definition was found for **{query}**.")
            return

        await ctx.send(
            view=DictionaryView(author_id=ctx.author.id, pages=pages),
        )

    @dictionary.autocomplete("word")
    async def dictionary_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        query = current.strip().casefold()
        if not query:
            return []

        cache_key = ("dictionary", query)
        if cache_key in self._autocomplete_cache:
            return self._autocomplete_cache[cache_key]

        try:
            timeout = aiohttp.ClientTimeout(total=2.25)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    "https://api.datamuse.com/sug",
                    params={"s": query, "max": "25"},
                ) as response:
                    response.raise_for_status()
                    payload = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return []

        suggestions: list[app_commands.Choice[str]] = []
        seen: set[str] = set()
        if isinstance(payload, list):
            for item in payload:
                word = str(item.get("word") or "").strip() if isinstance(item, dict) else ""
                folded = word.casefold()
                if (
                    not word
                    or len(word) > 100
                    or folded in seen
                    or re.fullmatch(r"[A-Za-z]+(?:['-][A-Za-z]+)*", word) is None
                ):
                    continue
                seen.add(folded)
                suggestions.append(app_commands.Choice(name=word, value=word))
                if len(suggestions) == 25:
                    break

        self._autocomplete_cache[cache_key] = suggestions
        return suggestions

    @commands.hybrid_command(
        name="urban",
        aliases=["ud"],
        description="Look up slang on Urban Dictionary",
    )
    @app_commands.describe(term="The slang word or phrase to look up")
    async def urban(
        self,
        ctx: commands.Context,
        term: str,
        ephemeral: bool = False,
    ) -> None:
        query = term.strip()
        if not query or len(query) > 100:
            await ctx.send("Enter a term between 1 and 100 characters.")
            return

        await ctx.defer(ephemeral=ephemeral)
        entries = await asyncio.to_thread(_read_urban_cache, query)
        if entries is None:
            endpoint = (
                "https://api.urbandictionary.com/v0/define?term="
                f"{quote(query, safe='')}"
            )
            try:
                timeout = aiohttp.ClientTimeout(total=20)
                headers = {"User-Agent": "DiscordUrbanDictionaryBot/1.0"}
                async with aiohttp.ClientSession(
                    timeout=timeout,
                    headers=headers,
                ) as session:
                    async with session.get(endpoint) as response:
                        response.raise_for_status()
                        payload = await response.json()
                entries = payload.get("list", []) if isinstance(payload, dict) else []
                if not isinstance(entries, list):
                    raise ValueError("Urban Dictionary returned an invalid response")
                if entries:
                    await asyncio.to_thread(_write_urban_cache, query, entries)
            except (aiohttp.ClientError, TimeoutError, ValueError):
                await ctx.send(
                    "Urban Dictionary is unavailable right now. Try again shortly."
                )
                return

        if not entries:
            await ctx.send(f"Urban Dictionary has no definition for **{query}**.")
            return

        pages: list[dict[str, str]] = []
        for entry in entries[:25]:
            definition = _format_urban_text(
                str(entry.get("definition") or "No definition provided.")
            )
            example = _format_urban_text(
                str(entry.get("example") or "No example was provided.")
            )
            permalink = str(entry.get("permalink") or "")
            if permalink.startswith("http://"):
                permalink = "https://" + permalink.removeprefix("http://")
            if not permalink:
                permalink = (
                    "https://www.urbandictionary.com/define.php?term=" + quote(query)
                )
            pages.append(
                {
                    "word": _format_urban_text(str(entry.get("word") or query)),
                    "definition": definition,
                    "example": example,
                    "author": _format_urban_text(str(entry.get("author") or "Unknown")),
                    "date": str(entry.get("written_on") or "Unknown date")[:10],
                    "up": str(entry.get("thumbs_up", 0)),
                    "down": str(entry.get("thumbs_down", 0)),
                    "url": permalink,
                }
            )

        await ctx.send(
            view=UrbanDictionaryView(author_id=ctx.author.id, pages=pages),
        )

    @urban.autocomplete("term")
    async def urban_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        query = current.strip().casefold()
        if not query:
            return []

        cache_key = ("urban", query)
        if cache_key in self._autocomplete_cache:
            return self._autocomplete_cache[cache_key]

        try:
            timeout = aiohttp.ClientTimeout(total=2.25)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    "https://api.urbandictionary.com/v0/autocomplete-extra",
                    params={"term": query},
                ) as response:
                    response.raise_for_status()
                    payload = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return []

        raw_results = payload.get("results", []) if isinstance(payload, dict) else payload
        suggestions: list[app_commands.Choice[str]] = []
        seen: set[str] = set()
        if isinstance(raw_results, list):
            for item in raw_results:
                if isinstance(item, dict):
                    term = str(item.get("term") or "").strip()
                else:
                    term = str(item).strip()
                folded = term.casefold()
                if not term or len(term) > 100 or folded in seen:
                    continue
                seen.add(folded)
                suggestions.append(app_commands.Choice(name=term, value=term))
                if len(suggestions) == 25:
                    break

        self._autocomplete_cache[cache_key] = suggestions
        return suggestions

    @commands.hybrid_command(
        name="userinfo",
        aliases=["ui"],
        description="Show information about a Discord user",
    )
    @app_commands.describe(user="User to inspect; leave empty to show yourself")
    @owner_clearance()
    async def userinfo(
        self,
        ctx: commands.Context,
        user: discord.User | None = None,
        ephemeral: bool = False,
    ) -> None:
        selected_user = user or ctx.author
        try:
            fetched_user = await self.bot.fetch_user(selected_user.id)
        except discord.HTTPException:
            fetched_user = selected_user

        member: discord.Member | None = None
        if ctx.guild is not None:
            member = ctx.guild.get_member(selected_user.id)
            if member is None:
                try:
                    member = await ctx.guild.fetch_member(selected_user.id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    member = None

        badges = [
            flag.name.replace("_", " ").title()
            for flag in fetched_user.public_flags.all()
        ]
        accent = (
            f"`#{fetched_user.accent_color.value:06X}`"
            if fetched_user.accent_color
            else "None"
        )
        items: list[discord.ui.Item] = [
            discord.ui.Section(
                discord.ui.TextDisplay(
                    f"## User Information\n"
                    f"**{fetched_user.display_name}** • @{fetched_user.name}"
                ),
                accessory=discord.ui.Thumbnail(
                    fetched_user.display_avatar.url,
                    description=f"{fetched_user.display_name}'s avatar",
                ),
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "### Identity\n"
                f"**User ID:** `{fetched_user.id}`\n"
                f"**Created:** <t:{int(fetched_user.created_at.timestamp())}:F>\n"
                f"**Account type:** {'Bot' if fetched_user.bot else 'User'}\n"
                f"**Accent:** {accent}\n"
                f"**Badges:** {', '.join(badges) if badges else 'None'}"
            ),
        ]

        if member is not None:
            roles = [role.mention for role in member.roles if not role.is_default()]
            roles_text = ", ".join(reversed(roles)) if roles else "None"
            joined = (
                f"<t:{int(member.joined_at.timestamp())}:F>"
                if member.joined_at
                else "Unknown"
            )
            timeout = (
                f"<t:{int(member.timed_out_until.timestamp())}:R>"
                if member.timed_out_until
                and member.timed_out_until > discord.utils.utcnow()
                else "No"
            )
            permissions = [
                name.replace("_", " ").title()
                for name, enabled in member.guild_permissions
                if enabled
            ]
            server_text = (
                "### Server Information\n"
                f"**Joined:** {joined}\n"
                f"**Nickname:** {member.nick or 'None'}\n"
                f"**Display name:** {member.display_name}\n"
                f"**Highest role:** {member.top_role.mention}\n"
                f"**Timed out:** {timeout}\n"
                f"**Roles ({len(roles)}):** {roles_text[:2200]}"
            )
        else:
            permissions = []
            server_text = (
                "### Server Information\nThis user is not a member of this server."
            )
        items.extend([discord.ui.Separator(), discord.ui.TextDisplay(server_text)])

        banner_url = fetched_user.banner.url if fetched_user.banner else None
        if banner_url:
            items.extend(
                [
                    discord.ui.Separator(),
                    discord.ui.MediaGallery(
                        discord.MediaGalleryItem(
                            banner_url,
                            description=f"{fetched_user.display_name}'s banner",
                        )
                    ),
                ]
            )
        await ctx.send(
            view=UserInfoView(
                author_id=ctx.author.id,
                avatar_url=fetched_user.display_avatar.url,
                banner_url=banner_url,
                permissions=permissions,
                items=items,
            )
        )

    @commands.hybrid_command(
        name="avatar",
        aliases=["av", "pfp"],
        description="Get a user's avatar",
    )
    @app_commands.describe(user="Leave empty to show your own avatar")
    async def avatar(
        self,
        ctx: commands.Context,
        user: discord.User | None = None,
        ephemeral: bool = False,
    ) -> None:
        selected_user = user or ctx.author
        avatar_url = selected_user.display_avatar.url

        view = discord.ui.LayoutView()
        container = discord.ui.Container(
            discord.ui.TextDisplay(f"### `{selected_user}`'s avatar"),
            discord.ui.Separator(),
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(
                    avatar_url,
                    description=f"{selected_user.display_name}'s avatar",
                )
            ),
        )

        view.add_item(container)
        await ctx.send(view=view)

    @commands.hybrid_command(
        name="banner",
        aliases=["banr"],
        description="Get a user's banner",
    )
    @app_commands.describe(user="Leave empty to show your own banner")
    async def banner(
        self,
        ctx: commands.Context,
        user: discord.User | None = None,
        ephemeral: bool = False,
    ) -> None:
        selected_user = user or ctx.author
        try:
            fetched_user = await self.bot.fetch_user(selected_user.id)
        except discord.NotFound:
            await ctx.send("No Discord user was found with that ID.")
            return
        except discord.HTTPException:
            await ctx.send("Discord could not be reached. Please try again later.")
            return

        view = discord.ui.LayoutView()
        if fetched_user.banner is None:
            view.add_item(
                discord.ui.Container(
                    discord.ui.TextDisplay(
                        f"## {fetched_user.display_name}'s Banner\n"
                        "This user does not have a profile banner."
                    )
                )
            )
            await ctx.send(view=view)
            return

        banner_url = fetched_user.banner.url
        container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(
                    f"## {fetched_user.display_name}'s Banner\n"
                    f"@{fetched_user.name} • `{fetched_user.id}`"
                ),
                accessory=discord.ui.Thumbnail(
                    fetched_user.display_avatar.url,
                    description=f"{fetched_user.display_name}'s avatar",
                ),
            ),
            discord.ui.Separator(),
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(
                    banner_url,
                    description=f"{fetched_user.display_name}'s banner",
                )
            ),
            discord.ui.TextDisplay(f"[Open original banner]({banner_url})"),
        )
        view.add_item(container)
        await ctx.send(view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Utility(bot))
