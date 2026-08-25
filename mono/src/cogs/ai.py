from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import re
import sqlite3
import subprocess
import tempfile
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import aiohttp
import discord
import imageio_ffmpeg
from discord import app_commands
from discord.ext import commands
from discord.http import Route
from discord.interactions import InteractionResponseType
from discord.webhook.async_ import async_context, interaction_message_response_params

from src.cogs.utility import _prepare_voice_message


logger = logging.getLogger(__name__)

def _load_navy_api_keys() -> tuple[str, ...]:
    names = ["NAVY_API_KEY"]
    names.extend(
        sorted(
            (
                name
                for name in os.environ
                if name.startswith("NAVY_API_KEY_")
                and name.removeprefix("NAVY_API_KEY_").isdigit()
            ),
            key=lambda name: int(name.removeprefix("NAVY_API_KEY_")),
        )
    )
    return tuple(
        dict.fromkeys(
            value
            for name in names
            if (value := os.getenv(name, "").strip())
        )
    )


NAVY_API_KEYS = _load_navy_api_keys()
NAVY_CASUAL_MODEL = os.getenv(
    "NAVY_CASUAL_MODEL",
    "gpt-5.4-mini",
).strip()
NAVY_SONAR_MODEL = os.getenv("NAVY_SONAR_MODEL", "sonar").strip()
NAVY_IMAGE_MODEL = "z-image"
NAVY_TTS_MODEL = os.getenv("NAVY_TTS_MODEL", "gpt-4o-mini-tts").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip()
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICES = (
    {"id": "JBFqnCBsd6RMkjVDRZzb", "name": "George", "navy": "onyx"},
    {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel", "navy": "nova"},
    {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam", "navy": "echo"},
    {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella", "navy": "shimmer"},
    {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni", "navy": "fable"},
    {"id": "TxGEqnHWrfWFTfGW9XjX", "name": "Josh", "navy": "ash"},
)

SYSTEM_PROMPT = (
    "You are a helpful AI assistant inside a Discord bot. Give clear, accurate, "
    "natural answers. Prefer concise answers unless the user asks for detail. "
    "Use Discord-friendly Markdown and never ping users, roles, or everyone."
)
AI_MODELS = {
    "casual": (
        "Casual",
        NAVY_CASUAL_MODEL,
        "Talk like a real person having a relaxed one-on-one conversation. Match the "
        "user's tone, vocabulary, message length, and energy without awkwardly copying "
        "them or forcing slang. Use contractions and natural conversational rhythm. "
        "React naturally when it fits, but do not overdo enthusiasm, emojis, jokes, or "
        "the user's name. Avoid canned assistant phrases, formal introductions, constant "
        "disclaimers, unnecessary headings, repetitive summaries, and repeating the "
        "question. Answer directly and only explain further when it is actually useful.",
    ),
    "schizo": (
        "Schizo",
        "schizogpt",
        "Use a chaotic, surreal, unpredictable conversational style while still answering the user.",
    ),
    "devious": (
        "Devious",
        "devious-uncensored",
        "Use a mischievous, witty, devious tone while remaining genuinely helpful.",
    ),
}
MODEL_TITLES = {
    "gpt-5.4-mini": "GPT-5.4 Mini",
    "gpt-4.1-nano": "GPT-4.1 Nano",
    "schizogpt": "SchizoGPT",
    "devious-uncensored": "Devious Uncensored",
    "llama-3.3-70b-versatile": "Llama 3.3 70B",
    "openrouter/free": "OpenRouter Free Model",
    "whisper-1": "Whisper-1",
    "sonar": "Perplexity Sonar",
}
CHATGPT_ICON_PATH = Path(__file__).resolve().parents[2] / "assets" / "chatgpt.png"
NAVY_ICON_PATH = Path(__file__).resolve().parents[2] / "assets" / "navy.png"
AI_EMOJI_ASSETS = {
    "chatgpt": ("ai_chatgpt", CHATGPT_ICON_PATH),
    "navy": ("ai_navy", NAVY_ICON_PATH),
}
MAX_PROMPT_LENGTH = 4_000
MAX_TTS_LENGTH = 1_000
MAX_TRANSCRIPTION_BYTES = 25 * 1024 * 1024
USER_COOLDOWN_SECONDS = 5.0
AI_USAGE_DB = Path(__file__).resolve().parents[2] / ".cache" / "ai_usage.db"


def _extract_prefix_choice(
    text: str,
    choices: dict[str, str],
    default: str,
) -> tuple[str, str]:
    """Remove standalone --flags from prefix text and return the last choice."""
    selected = default
    flag_pattern = re.compile(
        r"(?<!\S)(--(?:" + "|".join(map(re.escape, choices)) + r"))(?!\S)",
        re.IGNORECASE,
    )

    def replace(match: re.Match[str]) -> str:
        nonlocal selected
        selected = choices[match.group(1)[2:].casefold()]
        return ""

    cleaned = " ".join(flag_pattern.sub(replace, text).split())
    return cleaned, selected


def _audio_to_transcription_mp3(audio: bytes, suffix: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="ai-transcription-") as directory:
        source = Path(directory) / f"source{suffix or '.audio'}"
        output = Path(directory) / "transcription.mp3"
        source.write_bytes(audio)
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "64k",
                str(output),
            ],
            check=True,
            capture_output=True,
        )
        return output.read_bytes()


class AIServiceUnavailable(RuntimeError):
    pass


class UploadedVoiceAttachment:
    def __init__(
        self,
        uploaded_filename: str,
        *,
        duration_secs: float,
        waveform: str,
    ) -> None:
        self.uploaded_filename = uploaded_filename
        self.duration_secs = duration_secs
        self.waveform = waveform

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": "0",
            "filename": "voice-message.ogg",
            "uploaded_filename": self.uploaded_filename,
            "duration_secs": self.duration_secs,
            "waveform": self.waveform,
        }


class CasualContinueModal(discord.ui.Modal, title="Continue conversation"):
    prompt = discord.ui.TextInput(
        label="Message",
        style=discord.TextStyle.paragraph,
        placeholder="What do you want to say next?",
        max_length=MAX_PROMPT_LENGTH,
    )

    def __init__(self, conversation: CasualConversationView) -> None:
        super().__init__()
        self.conversation = conversation

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.conversation.continue_chat(interaction, str(self.prompt))


class CasualConversationView(discord.ui.LayoutView):
    def __init__(
        self,
        *,
        cog: AI,
        author_id: int,
        messages: list[dict[str, str]],
        request_count: int,
        content: str,
        provider: str,
        model: str,
        prompt_preview: str | None = None,
    ) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = author_id
        self.messages = messages
        self.request_count = request_count
        self.content = content
        self.provider = provider
        self.model = model
        self.prompt_preview = prompt_preview
        self.message: discord.Message | None = None
        self.processing = False
        self.continue_button = discord.ui.Button(
            label="Continue · 1/3",
            style=discord.ButtonStyle.primary,
        )
        self.continue_button.callback = self._continue_button_callback
        self.controls = discord.ui.ActionRow(self.continue_button)
        self.render()

    def render(self) -> None:
        self.clear_items()
        self.continue_button.label = f"Continue · {self.request_count}/3"
        self.continue_button.disabled = self.processing or self.request_count >= 3
        self.cog._build_response_card(
            self,
            self.content,
            self.provider,
            self.model,
            prompt_preview=self.prompt_preview,
            controls=self.controls,
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This AI conversation belongs to someone else.",
            ephemeral=True,
        )
        return False

    async def on_timeout(self) -> None:
        self.continue_button.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def continue_chat(
        self,
        interaction: discord.Interaction,
        prompt: str,
    ) -> None:
        await self.cog._continue_casual_conversation(self, interaction, prompt)

    async def _continue_button_callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if self.request_count >= 3:
            await interaction.response.send_message(
                "This conversation has reached its three-request limit.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(CasualContinueModal(self))


class AIUsageStore:
    def __init__(self, database: Path) -> None:
        self.database = database
        database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_usage (
                    user_id INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    requests INTEGER NOT NULL DEFAULT 0,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, provider)
                )
                """
            )

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def record(
        self,
        user_id: int,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ai_usage (
                    user_id, provider, requests, input_tokens,
                    output_tokens, total_tokens
                ) VALUES (?, ?, 1, ?, ?, ?)
                ON CONFLICT(user_id, provider) DO UPDATE SET
                    requests=requests + 1,
                    input_tokens=input_tokens + excluded.input_tokens,
                    output_tokens=output_tokens + excluded.output_tokens,
                    total_tokens=total_tokens + excluded.total_tokens
                """,
                (user_id, provider, input_tokens, output_tokens, total_tokens),
            )

    def stats(self, user_id: int | None = None) -> list[dict[str, int | str]]:
        with self._connect() as connection:
            if user_id is None:
                rows = connection.execute(
                    """
                    SELECT provider, SUM(requests) AS requests,
                           SUM(input_tokens) AS input_tokens,
                           SUM(output_tokens) AS output_tokens,
                           SUM(total_tokens) AS total_tokens
                    FROM ai_usage
                    GROUP BY provider
                    ORDER BY requests DESC, provider ASC
                    """
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT provider, requests, input_tokens,
                           output_tokens, total_tokens
                    FROM ai_usage
                    WHERE user_id = ?
                    ORDER BY requests DESC, provider ASC
                    """,
                    (user_id,),
                ).fetchall()
        return [dict(row) for row in rows]


usage_store = AIUsageStore(AI_USAGE_DB)


class AI(commands.Cog):
    """Allowlisted AI chat commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._session: aiohttp.ClientSession | None = None
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_request: dict[int, float] = {}
        self._ai_emojis: dict[str, str] = {}
        self.tts_context_menu = app_commands.ContextMenu(
            name="Audio Tools",
            callback=self.audio_tools_message,
        )
        self.bot.tree.add_command(self.tts_context_menu)

    async def cog_load(self) -> None:
        try:
            existing = {
                emoji.name: emoji
                for emoji in await self.bot.fetch_application_emojis()
            }
        except discord.HTTPException:
            logger.warning("Could not load application AI emojis", exc_info=True)
            return

        for key, (name, path) in AI_EMOJI_ASSETS.items():
            emoji = existing.get(name)
            if emoji is None and path.is_file():
                try:
                    emoji = await self.bot.create_application_emoji(
                        name=name,
                        image=path.read_bytes(),
                    )
                except discord.HTTPException:
                    logger.warning(
                        "Could not create application AI emoji %s",
                        name,
                        exc_info=True,
                    )
                    continue
                logger.info("Created application AI emoji %s", name)
            if emoji is not None:
                self._ai_emojis[key] = str(emoji)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.tts_context_menu.name,
            type=self.tts_context_menu.type,
        )
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def _can_use_ai(self, user: discord.abc.User) -> bool:
        return await self.bot.can_use_ai(user)

    async def _deny(self, ctx: commands.Context) -> None:
        await ctx.send(
            "You do not have access to AI commands. Ask the bot owner to add "
            "you with `/o core allow`.",
            ephemeral=ctx.interaction is not None,
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=75),
            )
        return self._session

    async def _get_elevenlabs_voices(self) -> list[dict[str, str]]:
        return [dict(voice) for voice in ELEVENLABS_VOICES]

    async def _generate_elevenlabs_speech(
        self,
        text: str,
        voice_id: str,
        *,
        output_format: str = "mp3_44100_128",
    ) -> bytes:
        content_type = "audio/ogg" if output_format.startswith("opus_") else "audio/mpeg"
        session = await self._get_session()
        async with session.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": content_type,
            },
            params={"output_format": output_format},
            json={"text": text, "model_id": "eleven_multilingual_v2"},
            timeout=aiohttp.ClientTimeout(total=75),
        ) as response:
            if response.status != 200:
                logger.warning("ElevenLabs TTS failed with HTTP %s", response.status)
                raise AIServiceUnavailable(
                    f"ElevenLabs returned HTTP {response.status}"
                )
            audio = await response.read()
        if len(audio) < 1_000:
            raise AIServiceUnavailable("ElevenLabs returned invalid audio")
        return audio

    async def _generate_navy_speech(
        self,
        text: str,
        voice: str,
        *,
        response_format: str = "mp3",
    ) -> bytes:
        if not NAVY_API_KEYS:
            raise AIServiceUnavailable("Navy TTS is not configured")
        session = await self._get_session()
        for key_number, api_key in enumerate(NAVY_API_KEYS, start=1):
            try:
                async with session.post(
                    "https://api.navy/v1/audio/speech",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": NAVY_TTS_MODEL,
                        "voice": voice.casefold(),
                        "input": text,
                        "response_format": response_format,
                    },
                    timeout=aiohttp.ClientTimeout(total=75),
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            "Navy TTS key %s failed with HTTP %s",
                            key_number,
                            response.status,
                        )
                        continue
                    audio = await response.read()
            except (aiohttp.ClientError, asyncio.TimeoutError):
                logger.warning("Navy TTS key %s failed", key_number)
                continue
            if len(audio) >= 1_000:
                return audio
        raise AIServiceUnavailable("Every Navy TTS key failed")

    async def _generate_speech_with_fallback(
        self,
        text: str,
        voice: dict[str, str],
        *,
        native_voice_note: bool,
    ) -> bytes:
        try:
            navy_audio = await self._generate_navy_speech(
                text,
                voice["navy"],
                response_format="mp3",
            )
            if native_voice_note:
                return (await asyncio.to_thread(_prepare_voice_message, navy_audio))[0]
            return navy_audio
        except (AIServiceUnavailable, aiohttp.ClientError, asyncio.TimeoutError):
            if not ELEVENLABS_API_KEY:
                raise AIServiceUnavailable("Every TTS provider failed")
        return await self._generate_elevenlabs_speech(
            text,
            voice["id"],
            output_format="opus_48000_32" if native_voice_note else "mp3_44100_128",
        )

    async def _generate_navy_image(self, prompt: str, aspect_ratio: str) -> bytes:
        if not NAVY_API_KEYS:
            raise AIServiceUnavailable("Navy image generation is not configured")
        session = await self._get_session()
        for key_number, api_key in enumerate(NAVY_API_KEYS, start=1):
            try:
                async with session.post(
                    "https://api.navy/v1/images/generations",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": NAVY_IMAGE_MODEL,
                        "prompt": prompt,
                        "aspect_ratio": aspect_ratio,
                        "response_format": "b64_json",
                    },
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            "Navy image key %s failed with HTTP %s",
                            key_number,
                            response.status,
                        )
                        continue
                    payload = await response.json(content_type=None)
                item = payload["data"][0]
                encoded = item.get("b64_json") if isinstance(item, dict) else None
                if isinstance(encoded, str) and encoded:
                    if encoded.startswith("data:") and "," in encoded:
                        encoded = encoded.split(",", 1)[1]
                    try:
                        return base64.b64decode(encoded, validate=True)
                    except ValueError:
                        pass
                image_url = item.get("url") if isinstance(item, dict) else None
                if not isinstance(image_url, str) or not image_url.startswith("https://"):
                    continue
                async with session.get(
                    image_url,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response:
                    response.raise_for_status()
                    image = await response.read()
                if image:
                    return image
            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
                KeyError,
                IndexError,
                TypeError,
            ):
                logger.warning("Navy image key %s failed", key_number)
                continue
        raise AIServiceUnavailable("Every Navy image key failed")

    @staticmethod
    def _audio_attachment(message: discord.Message) -> discord.Attachment | None:
        audio_suffixes = {
            ".aac", ".flac", ".m4a", ".mp3", ".mp4", ".mpeg",
            ".mpga", ".ogg", ".opus", ".wav", ".webm",
        }
        for attachment in message.attachments:
            content_type = (attachment.content_type or "").casefold()
            if content_type.startswith("audio/"):
                return attachment
            if Path(attachment.filename).suffix.casefold() in audio_suffixes:
                return attachment
        return None

    async def _transcribe_attachment(self, attachment: discord.Attachment) -> str:
        if not NAVY_API_KEYS:
            raise AIServiceUnavailable("Navy transcription is not configured")
        if attachment.size > MAX_TRANSCRIPTION_BYTES:
            raise ValueError("Audio files can be at most 25 MB")
        audio = await attachment.read(use_cached=True)
        if not audio or len(audio) > MAX_TRANSCRIPTION_BYTES:
            raise ValueError("Audio files can be at most 25 MB")
        converted = await asyncio.to_thread(
            _audio_to_transcription_mp3,
            audio,
            Path(attachment.filename).suffix.casefold(),
        )
        session = await self._get_session()
        for key_number, api_key in enumerate(NAVY_API_KEYS, start=1):
            form = aiohttp.FormData()
            form.add_field("model", "whisper-1")
            form.add_field("response_format", "json")
            form.add_field(
                "file",
                converted,
                filename="transcription.mp3",
                content_type="audio/mpeg",
            )
            try:
                async with session.post(
                    "https://api.navy/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    data=form,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            "Navy transcription key %s failed with HTTP %s",
                            key_number,
                            response.status,
                        )
                        continue
                    payload = await response.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError):
                logger.warning("Navy transcription key %s failed", key_number)
                continue
            transcript = payload.get("text") if isinstance(payload, dict) else None
            if isinstance(transcript, str) and transcript.strip():
                return transcript.strip()
        raise AIServiceUnavailable("Every Navy transcription key failed")

    async def _send_transcript_to_interaction(
        self,
        interaction: discord.Interaction,
        attachment: discord.Attachment,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            transcript = await self._transcribe_attachment(attachment)
        except ValueError as error:
            try:
                await interaction.delete_original_response()
            except discord.HTTPException:
                pass
            await interaction.followup.send(str(error), ephemeral=True)
            return
        except (
            AIServiceUnavailable,
            aiohttp.ClientError,
            asyncio.TimeoutError,
            OSError,
            subprocess.SubprocessError,
        ):
            try:
                await interaction.delete_original_response()
            except discord.HTTPException:
                pass
            await interaction.followup.send(
                "The transcription service is unavailable right now. Try again shortly.",
                ephemeral=True,
            )
            return
        await asyncio.to_thread(
            usage_store.record, interaction.user.id, "Navy Transcription", 0, 0, 0
        )
        chunks = self._split_response(transcript, limit=3_500)
        await interaction.edit_original_response(
            content=None,
            view=self._response_card(chunks[0], "Navy", "whisper-1"),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        for chunk in chunks[1:]:
            await interaction.followup.send(
                view=self._response_card(chunk, "Navy", "whisper-1"),
                allowed_mentions=discord.AllowedMentions.none(),
            )

    async def _create_initial_voice_response(
        self,
        interaction: discord.Interaction,
        attachment: UploadedVoiceAttachment,
    ) -> None:
        params = interaction_message_response_params(
            type=InteractionResponseType.channel_message.value,
            attachments=[attachment],
            flags=discord.MessageFlags(voice=True),
            allowed_mentions=discord.AllowedMentions.none(),
            previous_allowed_mentions=interaction._state.allowed_mentions,
        )
        adapter = async_context.get()
        http = interaction._state.http
        with params:
            await adapter.create_interaction_response(
                interaction.id,
                interaction.token,
                session=interaction._session,
                proxy=http.proxy,
                proxy_auth=http.proxy_auth,
                params=params,
            )
        interaction.response._response_type = InteractionResponseType.channel_message

    async def _upload_voice_attachment(
        self,
        channel_id: int,
        audio: bytes,
        *,
        duration_secs: float,
        waveform: str,
    ) -> UploadedVoiceAttachment:
        upload = await self.bot.http.request(
            Route(
                "POST",
                "/channels/{channel_id}/attachments",
                channel_id=channel_id,
            ),
            json={
                "files": [
                    {
                        "id": "0",
                        "filename": "voice-message.ogg",
                        "file_size": len(audio),
                    }
                ]
            },
        )
        slot = upload["attachments"][0]
        session = await self._get_session()
        async with session.put(
            slot["upload_url"],
            data=audio,
            headers={"Content-Type": "audio/ogg"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            if response.status not in {200, 201, 204}:
                raise AIServiceUnavailable(
                    f"Discord attachment upload returned HTTP {response.status}"
                )
        return UploadedVoiceAttachment(
            slot["upload_filename"],
            duration_secs=duration_secs,
            waveform=waveform,
        )

    async def _send_uploaded_voice_message(
        self,
        channel_id: int,
        attachment: UploadedVoiceAttachment,
    ) -> None:
        await self.bot.http.request(
            Route(
                "POST",
                "/channels/{channel_id}/messages",
                channel_id=channel_id,
            ),
            json={
                "flags": discord.MessageFlags(voice=True).value,
                "attachments": [attachment.to_dict()],
                "allowed_mentions": {"parse": []},
            },
        )

    @staticmethod
    def _providers(
        navy_model: str = NAVY_CASUAL_MODEL,
    ) -> list[tuple[str, str, str, str]]:
        providers: list[tuple[str, str, str, str]] = []
        for api_key in NAVY_API_KEYS:
            providers.append(
                (
                    "Navy",
                    "https://api.navy/v1/chat/completions",
                    api_key,
                    navy_model,
                )
            )
        if GROQ_API_KEY:
            providers.append(
                (
                    "Groq",
                    "https://api.groq.com/openai/v1/chat/completions",
                    GROQ_API_KEY,
                    GROQ_MODEL,
                )
            )
        if OPENROUTER_API_KEY:
            providers.append(
                (
                    "OpenRouter",
                    "https://openrouter.ai/api/v1/chat/completions",
                    OPENROUTER_API_KEY,
                    OPENROUTER_MODEL,
                )
            )
        return providers

    async def _request_provider(
        self,
        provider: tuple[str, str, str, str],
        messages: list[dict[str, str]],
    ) -> tuple[str, str, int, int, int]:
        name, url, api_key, model = provider
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if name == "OpenRouter":
            headers["X-Title"] = "Discord Bot"
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": 1_200,
            "temperature": 0.7,
        }
        session = await self._get_session()
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status >= 400:
                logger.warning("%s AI request failed with HTTP %s", name, response.status)
                raise AIServiceUnavailable(f"{name} returned HTTP {response.status}")
            try:
                data = await response.json()
                content = data["choices"][0]["message"]["content"]
            except (aiohttp.ContentTypeError, KeyError, IndexError, TypeError):
                logger.warning("%s AI response had an unexpected format", name)
                raise AIServiceUnavailable(
                    f"{name} returned an unexpected response"
                ) from None
        if not isinstance(content, str) or not content.strip():
            raise AIServiceUnavailable(f"{name} returned an empty response")
        usage = data.get("usage") or {}
        input_tokens = int(
            usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0
        )
        output_tokens = int(
            usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
        )
        total_tokens = int(
            usage.get("total_tokens", input_tokens + output_tokens) or 0
        )
        resolved_model = str(data.get("model") or model)
        return (
            content.strip(),
            resolved_model,
            input_tokens,
            output_tokens,
            total_tokens,
        )

    @staticmethod
    def _sonar_sources(data: dict[str, Any]) -> list[tuple[str, str]]:
        """Collect citation URLs from Perplexity and OpenAI-style responses."""
        sources: list[tuple[str, str]] = []
        seen: set[str] = set()

        def add(url: Any, title: Any = None) -> None:
            url_text = str(url or "").strip()
            if not url_text.startswith(("https://", "http://")) or url_text in seen:
                return
            seen.add(url_text)
            title_text = str(title or "").strip() or f"Source {len(sources) + 1}"
            sources.append((title_text, url_text))

        for citation in data.get("citations") or ():
            if isinstance(citation, str):
                add(citation)
            elif isinstance(citation, dict):
                add(citation.get("url"), citation.get("title"))

        for result in data.get("search_results") or ():
            if isinstance(result, dict):
                add(result.get("url"), result.get("title"))

        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            message = {}
        if isinstance(message, dict):
            for citation in message.get("citations") or ():
                if isinstance(citation, str):
                    add(citation)
                elif isinstance(citation, dict):
                    add(citation.get("url"), citation.get("title"))
            for annotation in message.get("annotations") or ():
                if not isinstance(annotation, dict):
                    continue
                citation = annotation.get("url_citation") or annotation
                if isinstance(citation, dict):
                    add(citation.get("url"), citation.get("title"))
        return sources

    async def _search_with_sonar(
        self,
        query: str,
    ) -> tuple[str, list[tuple[str, str]], int, int, int]:
        if not NAVY_API_KEYS:
            raise AIServiceUnavailable("No Navy API key is configured")

        session = await self._get_session()
        payload = {
            "model": NAVY_SONAR_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Answer using current web information. Be concise but complete. "
                        "Preserve inline source citations and never invent sources. Use "
                        "Discord-friendly Markdown."
                    ),
                },
                {"role": "user", "content": query},
            ],
            "max_tokens": 1_500,
            "temperature": 0.2,
        }
        for key_number, api_key in enumerate(NAVY_API_KEYS, start=1):
            try:
                async with session.post(
                    "https://api.navy/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=90),
                ) as response:
                    if response.status >= 400:
                        logger.warning(
                            "Navy key %d Sonar request failed with HTTP %s",
                            key_number,
                            response.status,
                        )
                        continue
                    data = await response.json(content_type=None)
                content = data["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise KeyError("empty Sonar response")
                usage = data.get("usage") or {}
                input_tokens = int(
                    usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0
                )
                output_tokens = int(
                    usage.get(
                        "completion_tokens",
                        usage.get("output_tokens", 0),
                    ) or 0
                )
                total_tokens = int(
                    usage.get("total_tokens", input_tokens + output_tokens) or 0
                )
                return (
                    content.strip(),
                    self._sonar_sources(data),
                    input_tokens,
                    output_tokens,
                    total_tokens,
                )
            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
                aiohttp.ContentTypeError,
                KeyError,
                IndexError,
                TypeError,
                ValueError,
            ):
                logger.warning(
                    "Navy key %d returned an unusable Sonar response",
                    key_number,
                    exc_info=True,
                )
        raise AIServiceUnavailable("Every Navy key failed for Sonar")

    async def _complete(
        self,
        messages: list[dict[str, str]],
        navy_model: str,
    ) -> tuple[str, str, str, int, int, int]:
        providers = self._providers(navy_model)
        if not providers:
            raise AIServiceUnavailable("No AI provider is configured")

        for provider in providers:
            try:
                response, resolved_model, input_tokens, output_tokens, total_tokens = (
                    await self._request_provider(provider, messages)
                )
            except (AIServiceUnavailable, aiohttp.ClientError, asyncio.TimeoutError):
                continue
            return (
                response,
                provider[0],
                resolved_model,
                input_tokens,
                output_tokens,
                total_tokens,
            )
        raise AIServiceUnavailable("Every configured AI provider failed")

    async def _provider_allowances(self) -> list[str]:
        session = await self._get_session()
        total_remaining = 0
        total_allowance = 0
        reset_times: list[int] = []
        available_keys = 0

        for api_key in NAVY_API_KEYS:
            try:
                async with session.get(
                    "https://api.navy/v1/usage",
                    headers={"Authorization": f"Bearer {api_key}"},
                ) as response:
                    response.raise_for_status()
                    data = await response.json(content_type=None)
                    usage = data["usage"]
                    remaining = int(usage["tokens_remaining_today"])
                    used = int(usage["tokens_used_today"])
                    reset_ms = max(int(usage.get("resets_in_ms", 0)), 0)
                    reset_at = int(time.time() + reset_ms / 1_000)
                    total_remaining += remaining
                    total_allowance += remaining + used
                    reset_times.append(reset_at)
                    available_keys += 1
            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
                KeyError,
                TypeError,
                ValueError,
            ):
                continue

        if not available_keys:
            return ["**Navy** — Tokens left: `N/A` · Reset: `N/A`"]
        next_reset = min(reset_times)
        return [
            f"**Navy** — `{total_remaining:,}` / `{total_allowance:,}` tokens left · "
            f"next reset <t:{next_reset}:R>"
        ]

    @staticmethod
    def _split_response(content: str, limit: int = 1_900) -> list[str]:
        chunks: list[str] = []
        remaining = content
        while len(remaining) > limit:
            split_at = max(
                remaining.rfind("\n", 0, limit),
                remaining.rfind(" ", 0, limit),
            )
            if split_at < limit // 2:
                split_at = limit
            chunks.append(remaining[:split_at].rstrip())
            remaining = remaining[split_at:].lstrip()
        if remaining:
            chunks.append(remaining)
        return chunks

    @staticmethod
    def _system_content(
        model_key: str,
        personality: str,
        username: str,
    ) -> str:
        identity = ""
        if model_key in {"casual", "schizo"}:
            identity = (
                f" The user's exact Discord username is {username!r}. This is private "
                "conversation context, not part of their message and not your own name. "
                "Only use it when a name is genuinely useful or natural; otherwise do "
                "not mention it. Never invent a different name, repeatedly address them "
                "by name, or format the username as a Discord mention."
            )
        return f"{SYSTEM_PROMPT} {personality}{identity}"

    def _model_emoji(self, provider: str, model: str) -> str:
        if model.startswith("gpt-"):
            return self._ai_emojis.get("chatgpt", "")
        if provider == "Navy" or model in {"schizogpt", "devious-uncensored"}:
            return self._ai_emojis.get("navy", "")
        return ""

    @staticmethod
    def _model_title(model: str) -> str:
        title = MODEL_TITLES.get(model)
        if title is not None:
            return title
        if model.startswith("gpt-5.4-mini"):
            return "ChatGPT 5.4 Mini"
        return model.replace("-", " ").replace("/", " / ").title()

    def _build_response_card(
        self,
        view: discord.ui.LayoutView,
        content: str,
        provider: str,
        model: str,
        *,
        prompt_preview: str | None = None,
        controls: discord.ui.Item | None = None,
    ) -> None:
        title = self._model_title(model)
        emoji = self._model_emoji(provider, model)
        heading = discord.ui.TextDisplay(
            f"### {emoji + ' ' if emoji else ''}{title}"
        )

        items: list[discord.ui.Item] = [
            heading,
            discord.ui.Separator(),
        ]
        if prompt_preview:
            items.extend(
                (
                    discord.ui.TextDisplay(f"-# **You:** {prompt_preview}"),
                    discord.ui.Separator(),
                )
            )
        items.extend(
            (
                discord.ui.TextDisplay(content),
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"-# API: {provider}"),
            )
        )
        if controls is not None:
            items.extend((discord.ui.Separator(), controls))
        view.add_item(discord.ui.Container(*items))

    def _response_card(
        self,
        content: str,
        provider: str,
        model: str,
    ) -> discord.ui.LayoutView:
        view = discord.ui.LayoutView()
        self._build_response_card(
            view,
            content,
            provider,
            model,
        )
        return view

    def _sonar_response_card(
        self,
        content: str,
        sources: list[tuple[str, str]],
    ) -> discord.ui.LayoutView:
        items: list[discord.ui.Item] = [
            discord.ui.TextDisplay("### Perplexity Sonar"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(content),
        ]
        if sources:
            source_lines = []
            for index, (title, url) in enumerate(sources[:8], start=1):
                safe_title = discord.utils.escape_markdown(
                    title.replace("[", "").replace("]", "")
                )
                safe_url = url.replace(")", "%29")
                source_lines.append(f"`{index}.` [{safe_title}]({safe_url})")
            items.extend(
                (
                    discord.ui.Separator(),
                    discord.ui.TextDisplay(
                        "### Sources\n" + "\n".join(source_lines)
                    ),
                )
            )
        items.extend(
            (
                discord.ui.Separator(),
                discord.ui.TextDisplay("-# API: Navy · Search: Perplexity"),
            )
        )
        view = discord.ui.LayoutView()
        view.add_item(discord.ui.Container(*items))
        return view

    @staticmethod
    def _prompt_preview(prompt: str, limit: int = 180) -> str:
        preview = " ".join(prompt.split())
        if len(preview) > limit:
            preview = preview[: limit - 1].rstrip() + "…"
        return discord.utils.escape_markdown(preview)

    async def _continue_casual_conversation(
        self,
        conversation: CasualConversationView,
        interaction: discord.Interaction,
        prompt: str,
    ) -> None:
        prompt = prompt.strip()
        if not prompt or conversation.request_count >= 3:
            await interaction.response.send_message(
                "This conversation cannot be continued.",
                ephemeral=True,
            )
            return
        if not await self._can_use_ai(interaction.user):
            await interaction.response.send_message(
                "You no longer have access to AI commands.",
                ephemeral=True,
            )
            return

        if conversation.processing:
            await interaction.response.send_message(
                "That reply is already being generated.",
                ephemeral=True,
            )
            return

        conversation.processing = True
        conversation.render()
        try:
            # Modal submissions can update the message that opened the modal. Doing
            # that here avoids creating a separate, permanently loading response.
            await interaction.response.edit_message(view=conversation)
        except discord.HTTPException:
            conversation.processing = False
            conversation.render()
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "I couldn't update this conversation. Please start a new one.",
                    ephemeral=True,
                )
            return

        _, navy_model, _ = AI_MODELS["casual"]
        messages = [*conversation.messages, {"role": "user", "content": prompt}]
        async with self._locks[interaction.user.id]:
            try:
                (
                    response,
                    provider,
                    response_model,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                ) = await self._complete(messages, navy_model)
            except AIServiceUnavailable:
                conversation.processing = False
                conversation.render()
                if conversation.message is not None:
                    try:
                        await conversation.message.edit(view=conversation)
                    except discord.HTTPException:
                        pass
                await interaction.followup.send(
                    "The AI services are unavailable right now. Try again shortly.",
                    ephemeral=True,
                )
                return
            await asyncio.to_thread(
                usage_store.record,
                interaction.user.id,
                provider,
                input_tokens,
                output_tokens,
                total_tokens,
            )

        messages.extend(({"role": "assistant", "content": response},))
        request_count = conversation.request_count + 1
        chunks = self._split_response(response)
        for chunk in chunks[:-1]:
            send_kwargs: dict[str, Any] = {
                "view": self._response_card(chunk, provider, response_model),
                "allowed_mentions": discord.AllowedMentions.none(),
            }
            await interaction.followup.send(**send_kwargs)
        next_view = CasualConversationView(
            cog=self,
            author_id=interaction.user.id,
            messages=messages,
            request_count=request_count,
            content=chunks[-1],
            provider=provider,
            model=response_model,
            prompt_preview=self._prompt_preview(prompt),
        )
        final_kwargs: dict[str, Any] = {
            "view": next_view,
            "allowed_mentions": discord.AllowedMentions.none(),
            "wait": True,
        }
        next_view.message = await interaction.followup.send(**final_kwargs)
        conversation.stop()

    @commands.hybrid_group(
        name="ai",
        description="Chat with the bot's AI",
        invoke_without_command=True,
    )
    async def ai(self, ctx: commands.Context) -> None:
        if not await self._can_use_ai(ctx.author):
            await self._deny(ctx)
            return
        await ctx.send(
            "Use `/ai chat`, `/ai devious`, `/ai schizo`, or `/ai search`."
        )

    async def _run_ai_chat(
        self,
        ctx: commands.Context,
        model_key: str,
        prompt: str,
    ) -> None:
        if not await self._can_use_ai(ctx.author):
            await self._deny(ctx)
            return

        prompt = prompt.strip()
        if not prompt:
            await ctx.send("Enter a message for the AI.")
            return
        if len(prompt) > MAX_PROMPT_LENGTH:
            await ctx.send(
                f"Your message can be at most `{MAX_PROMPT_LENGTH:,}` characters."
            )
            return
        _, navy_model, personality = AI_MODELS[model_key]

        now = time.monotonic()
        retry_after = USER_COOLDOWN_SECONDS - (
            now - self._last_request.get(ctx.author.id, 0.0)
        )
        if retry_after > 0:
            await ctx.send(f"Wait `{retry_after:.1f}` seconds before asking again.")
            return
        self._last_request[ctx.author.id] = now

        if ctx.interaction is not None and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)

        async with self._locks[ctx.author.id]:
            messages = [
                {
                    "role": "system",
                    "content": self._system_content(
                        model_key,
                        personality,
                        ctx.author.name,
                    ),
                },
                {"role": "user", "content": prompt},
            ]
            try:
                (
                    response,
                    provider,
                    response_model,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                ) = await self._complete(messages, navy_model)
            except AIServiceUnavailable:
                await ctx.send(
                    "The AI services are unavailable right now. Try again shortly."
                )
                return
            await asyncio.to_thread(
                usage_store.record,
                ctx.author.id,
                provider,
                input_tokens,
                output_tokens,
                total_tokens,
            )

        chunks = self._split_response(response)
        for chunk in chunks[:-1]:
            send_kwargs: dict[str, Any] = {
                "view": self._response_card(chunk, provider, response_model),
                "allowed_mentions": discord.AllowedMentions.none(),
            }
            await ctx.send(**send_kwargs)
        if model_key == "casual":
            messages.append({"role": "assistant", "content": response})
            view = CasualConversationView(
                cog=self,
                author_id=ctx.author.id,
                messages=messages,
                request_count=1,
                content=chunks[-1],
                provider=provider,
                model=response_model,
            )
        else:
            view = self._response_card(chunks[-1], provider, response_model)
        final_kwargs: dict[str, Any] = {
            "view": view,
            "allowed_mentions": discord.AllowedMentions.none(),
        }
        view.message = await ctx.send(**final_kwargs)

    @ai.command(name="chat", description="Chat casually with the AI")
    @app_commands.describe(prompt="What you want to say or ask")
    async def chat(self, ctx: commands.Context, *, prompt: str) -> None:
        await self._run_ai_chat(ctx, "casual", prompt)

    @ai.command(name="devious", description="Chat with the devious AI")
    @app_commands.describe(prompt="What you want to say or ask")
    async def devious(self, ctx: commands.Context, *, prompt: str) -> None:
        await self._run_ai_chat(ctx, "devious", prompt)

    @ai.command(name="schizo", description="Chat with the schizo AI")
    @app_commands.describe(prompt="What you want to say or ask")
    async def schizo(self, ctx: commands.Context, *, prompt: str) -> None:
        await self._run_ai_chat(ctx, "schizo", prompt)

    @ai.command(
        name="search",
        description="Search the live web with Perplexity Sonar",
    )
    @app_commands.describe(query="What you want Sonar to research")
    async def sonar_search(self, ctx: commands.Context, *, query: str) -> None:
        if not await self._can_use_ai(ctx.author):
            await self._deny(ctx)
            return

        query = query.strip()
        error_ephemeral = ctx.interaction is not None
        if not query:
            await ctx.send("Enter something to search for.", ephemeral=error_ephemeral)
            return
        if len(query) > MAX_PROMPT_LENGTH:
            await ctx.send(
                f"Your search can be at most `{MAX_PROMPT_LENGTH:,}` characters.",
                ephemeral=error_ephemeral,
            )
            return

        now = time.monotonic()
        retry_after = USER_COOLDOWN_SECONDS - (
            now - self._last_request.get(ctx.author.id, 0.0)
        )
        if retry_after > 0:
            await ctx.send(
                f"Wait `{retry_after:.1f}` seconds before searching again.",
                ephemeral=error_ephemeral,
            )
            return
        self._last_request[ctx.author.id] = now

        if ctx.interaction is not None and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)

        async with self._locks[ctx.author.id]:
            try:
                content, sources, input_tokens, output_tokens, total_tokens = (
                    await self._search_with_sonar(query)
                )
            except AIServiceUnavailable:
                if ctx.interaction is not None:
                    try:
                        await ctx.interaction.delete_original_response()
                    except discord.HTTPException:
                        pass
                    await ctx.interaction.followup.send(
                        "Sonar is unavailable right now. Try again shortly.",
                        ephemeral=True,
                    )
                else:
                    await ctx.send(
                        "Sonar is unavailable right now. Try again shortly."
                    )
                return
            await asyncio.to_thread(
                usage_store.record,
                ctx.author.id,
                "Navy",
                input_tokens,
                output_tokens,
                total_tokens,
            )

        chunks = self._split_response(content)
        for chunk in chunks[:-1]:
            await ctx.send(
                view=self._sonar_response_card(chunk, []),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        await ctx.send(
            view=self._sonar_response_card(chunks[-1], sources),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @ai.command(name="fact-check", description="Fact-check a claim with Sonar and cited evidence")
    @app_commands.describe(claim="The claim you want checked")
    async def fact_check(self, ctx: commands.Context, *, claim: str) -> None:
        query = (
            "Fact-check the following claim. Start with a verdict (True, Mostly true, "
            "Misleading, Mostly false, False, or Unverified), explain the key evidence, "
            "and cite reliable current sources for every important factual statement: "
            + claim
        )
        await self.sonar_search(ctx, query=query)

    @ai.command(name="models", description="Show Navy models, multipliers, availability and capabilities")
    async def navy_models(self, ctx: commands.Context) -> None:
        if not await self._can_use_ai(ctx.author):
            await self._deny(ctx)
            return
        if not NAVY_API_KEYS:
            await ctx.send("No Navy API key is configured.")
            return
        if ctx.interaction is not None and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)
        try:
            session = await self._get_session()
            async with session.get(
                "https://api.navy/v1/models",
                headers={"Authorization": f"Bearer {NAVY_API_KEYS[0]}"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
            models = payload.get("data", payload.get("models", [])) if isinstance(payload, dict) else []
            lines = []
            for model in models:
                if not isinstance(model, dict):
                    continue
                name = str(model.get("name") or model.get("id") or "Unknown")
                multiplier = model.get("multiplier", model.get("token_multiplier", "1x"))
                multiplier = str(multiplier)
                if not multiplier.endswith("x"): multiplier += "x"
                available = model.get("available", model.get("enabled", True))
                capabilities = model.get("capabilities") or model.get("modalities") or []
                if isinstance(capabilities, dict): capabilities = [key for key, value in capabilities.items() if value]
                if isinstance(capabilities, str): capabilities = [capabilities]
                cap_text = ", ".join(map(str, capabilities)) or "chat"
                lines.append(f"**{name}** — `{multiplier}` · {'Available' if available else 'Unavailable'}\n-# {cap_text}")
            if not lines:
                raise KeyError("No models returned")
            for chunk in self._split_response("\n\n".join(lines)):
                await ctx.send(view=self._response_card(chunk, "Navy", "Navy Models"))
        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, TypeError, ValueError):
            await ctx.send("Navy's model catalogue is unavailable right now.")

    @ai.command(name="usage", description="Show user or overall AI usage")
    @app_commands.describe(
        scope="Show one user's usage or totals for everyone",
        user="The user to inspect; defaults to you",
    )
    @app_commands.choices(
        scope=[
            app_commands.Choice(name="User", value="user"),
            app_commands.Choice(name="Overall", value="overall"),
        ]
    )
    async def ai_usage(
        self,
        ctx: commands.Context,
        scope: str = "user",
        user: discord.User | None = None,
    ) -> None:
        if not await self._can_use_ai(ctx.author):
            await self._deny(ctx)
            return
        scope = scope.casefold()
        if scope not in {"user", "overall"}:
            await ctx.send("Choose `User` or `Overall`.")
            return
        target = user or ctx.author
        overall = scope == "overall"
        rows = await asyncio.to_thread(
            usage_store.stats,
            None if overall else target.id,
        )
        rows = [row for row in rows if row["provider"] == "Navy"]
        if not rows:
            await ctx.send(
                "No Navy usage has been recorded yet."
                if overall
                else f"{target.display_name} has no recorded Navy usage yet."
            )
            return

        requests = sum(int(row["requests"]) for row in rows)
        input_tokens = sum(int(row["input_tokens"]) for row in rows)
        output_tokens = sum(int(row["output_tokens"]) for row in rows)
        total_tokens = sum(int(row["total_tokens"]) for row in rows)
        allowance_lines = await self._provider_allowances()
        title = "Overall Navy Usage" if overall else f"{target.display_name}'s Navy Usage"
        navy_emoji = self._ai_emojis.get("navy", "")
        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"## {navy_emoji + ' ' if navy_emoji else ''}{title}"
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    "### Local Chat Activity\n"
                    f"**Chat requests:** `{requests:,}`\n"
                    f"**Raw input tokens:** `{input_tokens:,}`\n"
                    f"**Raw output tokens:** `{output_tokens:,}`\n"
                    f"**Raw chat tokens:** `{total_tokens:,}`"
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    "### Current Navy Allowance\n"
                    + "\n".join(allowance_lines)
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    "-# Local lifetime chat totals exclude model multipliers, images, "
                    "translation, and audio. Prompts and responses are never stored."
                ),
            )
        )
        await ctx.send(view=view)

    @ai.command(
        name="image",
        description="Generate an image with Navy AI",
        usage=";ai image <prompt> [--square|--landscape|--portrait]",
    )
    @app_commands.describe(
        prompt="Describe the image to generate",
        aspect_ratio="Choose the image shape",
    )
    @app_commands.choices(
        aspect_ratio=[
            app_commands.Choice(name="Square (1:1)", value="1:1"),
            app_commands.Choice(name="Landscape (16:9)", value="16:9"),
            app_commands.Choice(name="Portrait (9:16)", value="9:16"),
        ]
    )
    async def image(
        self,
        ctx: commands.Context,
        *,
        prompt: str,
        aspect_ratio: str = "1:1",
    ) -> None:
        if not await self._can_use_ai(ctx.author):
            await self._deny(ctx)
            return
        if ctx.interaction is None:
            prompt, aspect_ratio = _extract_prefix_choice(
                prompt,
                {
                    "square": "1:1",
                    "landscape": "16:9",
                    "portrait": "9:16",
                },
                "1:1",
            )
        prompt = prompt.strip()
        if not prompt:
            await ctx.send("Enter an image description.", ephemeral=ctx.interaction is not None)
            return
        if len(prompt) > MAX_PROMPT_LENGTH:
            await ctx.send(
                f"Your prompt can be at most `{MAX_PROMPT_LENGTH:,}` characters.",
                ephemeral=ctx.interaction is not None,
            )
            return
        if aspect_ratio not in {"1:1", "16:9", "9:16"}:
            await ctx.send("Choose `1:1`, `16:9`, or `9:16`.", ephemeral=True)
            return
        if ctx.interaction is not None and not ctx.interaction.response.is_done():
            await ctx.interaction.response.defer(thinking=True)
        try:
            image = await self._generate_navy_image(prompt, aspect_ratio)
        except (AIServiceUnavailable, aiohttp.ClientError, asyncio.TimeoutError):
            await ctx.send(
                "The image generation service is unavailable right now. Try again shortly.",
                ephemeral=ctx.interaction is not None,
            )
            return
        await asyncio.to_thread(usage_store.record, ctx.author.id, "Navy Images", 0, 0, 0)
        await ctx.send(
            file=discord.File(io.BytesIO(image), filename="generated-image.png"),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _run_tts(
        self,
        interaction: discord.Interaction,
        text: str,
        voice: str | None,
        output: str,
    ) -> None:
        text = text.strip()
        if not text:
            await interaction.response.send_message(
                "Enter some text to speak.", ephemeral=True
            )
            return
        if len(text) > MAX_TTS_LENGTH:
            await interaction.response.send_message(
                f"TTS text can be at most `{MAX_TTS_LENGTH:,}` characters.",
                ephemeral=True,
            )
            return
        if not NAVY_API_KEYS and not ELEVENLABS_API_KEY:
            await interaction.response.send_message(
                "Text-to-speech has not been configured by the bot owner.",
                ephemeral=True,
            )
            return

        async def send_private_error(message: str) -> None:
            if interaction.response.is_done():
                try:
                    await interaction.delete_original_response()
                except discord.HTTPException:
                    pass
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)

        channel = interaction.channel
        if output != "mp3" and interaction.guild is not None and channel is not None:
            bot_member = interaction.guild.me
            if bot_member is not None and hasattr(channel, "permissions_for"):
                permissions = channel.permissions_for(bot_member)
                if not permissions.send_voice_messages:
                    await send_private_error(
                        "I need the **Send Voice Messages** permission in this "
                        "channel to post a native voice note."
                    )
                    return

        voices = await self._get_elevenlabs_voices()
        selected = next(
            (
                item
                for item in voices
                if voice
                and voice.casefold()
                in {item["id"].casefold(), item["name"].casefold()}
            ),
            voices[0] if not voice else None,
        )
        if selected is None:
            await send_private_error(
                "That ElevenLabs voice is not available. Choose one from the suggestions."
            )
            return

        dm_audio_attachment = output != "mp3" and interaction.guild is None

        async def generate() -> bytes | tuple[bytes, float, str]:
            if output == "mp3" or dm_audio_attachment:
                return await self._generate_speech_with_fallback(
                    text,
                    selected,
                    native_voice_note=False,
                )
            audio = await self._generate_speech_with_fallback(
                text,
                selected,
                native_voice_note=True,
            )
            return await asyncio.to_thread(_prepare_voice_message, audio)

        generation = asyncio.create_task(generate())
        done, _ = await asyncio.wait({generation}, timeout=2.2)
        if not done:
            await interaction.response.defer(thinking=True)

        try:
            generated = await generation
        except (AIServiceUnavailable, aiohttp.ClientError, asyncio.TimeoutError):
            await send_private_error(
                "The text-to-speech service is unavailable right now. Try again shortly."
            )
            return
        except (OSError, RuntimeError):
            await send_private_error(
                "The voice note could not be prepared. Try the MP3 output instead."
            )
            return

        if output == "mp3" or dm_audio_attachment:
            file = discord.File(io.BytesIO(generated), filename="speech.mp3")
            try:
                if interaction.response.is_done():
                    await interaction.edit_original_response(
                        attachments=[file],
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                else:
                    await interaction.response.send_message(
                        file=file,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
            except discord.HTTPException:
                await send_private_error(
                    "The generated audio could not be sent in this channel."
                )
            return

        ogg, duration, waveform = generated
        if (
            not interaction.response.is_done()
            and (discord.utils.utcnow() - interaction.created_at).total_seconds() >= 2.0
        ):
            await interaction.response.defer(thinking=True)

        try:
            attachment = await self._upload_voice_attachment(
                interaction.channel_id,
                ogg,
                duration_secs=duration,
                waveform=waveform,
            )
        except (discord.HTTPException, aiohttp.ClientError, AIServiceUnavailable):
            await send_private_error(
                "The generated voice message could not be uploaded to Discord."
            )
            return
        if not interaction.response.is_done():
            try:
                await self._create_initial_voice_response(interaction, attachment)
                return
            except discord.HTTPException as error:
                logger.warning(
                    "Discord rejected initial TTS voice response: "
                    "status=%s code=%s text=%s",
                    error.status,
                    error.code,
                    error.text,
                )
                await send_private_error(
                    "The generated voice message could not be sent in this channel."
                )
                return

        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            pass
        try:
            await self._send_uploaded_voice_message(
                interaction.channel_id,
                attachment,
            )
        except discord.HTTPException as error:
            logger.warning(
                "Discord rejected native TTS voice message: status=%s code=%s text=%s",
                error.status,
                error.code,
                error.text,
            )
            await interaction.followup.send(
                "The generated voice message could not be sent in this channel.",
                ephemeral=True,
            )

    async def _run_prefix_tts(
        self,
        ctx: commands.Context,
        text: str,
        output: str,
    ) -> None:
        text = text.strip()
        if not text:
            await ctx.send("Enter some text to speak.")
            return
        if len(text) > MAX_TTS_LENGTH:
            await ctx.send(
                f"TTS text can be at most `{MAX_TTS_LENGTH:,}` characters."
            )
            return
        if not NAVY_API_KEYS and not ELEVENLABS_API_KEY:
            await ctx.send("Text-to-speech has not been configured by the bot owner.")
            return

        voices = await self._get_elevenlabs_voices()
        selected = voices[0]
        try:
            if output == "mp3" or ctx.guild is None:
                audio = await self._generate_speech_with_fallback(
                    text,
                    selected,
                    native_voice_note=False,
                )
                await ctx.send(
                    file=discord.File(io.BytesIO(audio), filename="speech.mp3")
                )
                return

            audio = await self._generate_speech_with_fallback(
                text,
                selected,
                native_voice_note=True,
            )
            prepared = await asyncio.to_thread(_prepare_voice_message, audio)
            voice_audio, duration_secs, waveform = prepared
            attachment = await self._upload_voice_attachment(
                ctx.channel.id,
                voice_audio,
                duration_secs=duration_secs,
                waveform=waveform,
            )
            await self._send_uploaded_voice_message(ctx.channel.id, attachment)
        except (AIServiceUnavailable, aiohttp.ClientError, asyncio.TimeoutError):
            await ctx.send(
                "The text-to-speech service is unavailable right now. Try again shortly."
            )
        except (discord.HTTPException, OSError, RuntimeError):
            await ctx.send("The generated voice message could not be sent here.")

    @ai.command(
        name="tts",
        description="Turn text into speech",
        usage=";ai tts <text> [--mp3|--voicemessage]",
    )
    @app_commands.describe(
        text="Text to speak",
        voice="ElevenLabs voice; leave empty to use the first available voice",
        output="Send compact voice audio or a downloadable MP3",
    )
    @app_commands.choices(
        output=[
            app_commands.Choice(name="Voice note", value="voice_note"),
            app_commands.Choice(name="MP3", value="mp3"),
        ]
    )
    async def tts(
        self,
        ctx: commands.Context,
        *,
        text: str,
        voice: str | None = None,
        output: str = "voice_note",
    ) -> None:
        if not await self._can_use_ai(ctx.author):
            await self._deny(ctx)
            return
        if ctx.interaction is None:
            text, output = _extract_prefix_choice(
                text,
                {
                    "mp3": "mp3",
                    "voicemessage": "voice_note",
                    "voice-message": "voice_note",
                    "voicenote": "voice_note",
                    "voice-note": "voice_note",
                },
                "voice_note",
            )
            await self._run_prefix_tts(ctx, text, output)
            return
        await self._run_tts(ctx.interaction, text, voice, output)

    async def tts_message(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ) -> None:
        if not await self._can_use_ai(interaction.user):
            await interaction.response.send_message(
                "You do not have access to AI commands.", ephemeral=True
            )
            return
        await self._run_tts(interaction, message.content, None, "voice_note")

    async def transcribe_message(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ) -> None:
        if not await self._can_use_ai(interaction.user):
            await interaction.response.send_message(
                "You do not have access to AI commands.", ephemeral=True
            )
            return
        attachment = self._audio_attachment(message)
        if attachment is None:
            await interaction.response.send_message(
                "That message does not contain a voice message or supported audio file.",
                ephemeral=True,
            )
            return
        await self._send_transcript_to_interaction(interaction, attachment)

    async def audio_tools_message(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ) -> None:
        if self._audio_attachment(message) is not None:
            await self.transcribe_message(interaction, message)
            return
        await self.tts_message(interaction, message)

    @commands.command(
        name="transcribe",
        description="Reply to a voice message or audio file to transcribe it",
    )
    @commands.guild_only()
    async def transcribe(self, ctx: commands.Context) -> None:
        if not await self._can_use_ai(ctx.author):
            await self._deny(ctx)
            return
        reference = ctx.message.reference
        if reference is None or reference.message_id is None:
            await ctx.send("Reply to a voice message or audio file with this command.")
            return
        replied = reference.resolved
        if not isinstance(replied, discord.Message):
            try:
                replied = await ctx.channel.fetch_message(reference.message_id)
            except (discord.HTTPException, AttributeError):
                await ctx.send("I could not access the message you replied to.")
                return
        attachment = self._audio_attachment(replied)
        if attachment is None:
            await ctx.send(
                "The message you replied to does not contain a voice message or supported audio file."
            )
            return
        async with ctx.typing():
            try:
                transcript = await self._transcribe_attachment(attachment)
            except ValueError as error:
                await ctx.send(str(error))
                return
            except (
                AIServiceUnavailable,
                aiohttp.ClientError,
                asyncio.TimeoutError,
                OSError,
                subprocess.SubprocessError,
            ):
                await ctx.send(
                    "The transcription service is unavailable right now. Try again shortly."
                )
                return
        await asyncio.to_thread(
            usage_store.record, ctx.author.id, "Navy Transcription", 0, 0, 0
        )
        for chunk in self._split_response(transcript, limit=3_500):
            await ctx.send(
                view=self._response_card(chunk, "Navy", "whisper-1"),
                allowed_mentions=discord.AllowedMentions.none(),
            )

    @tts.autocomplete("voice")
    async def tts_voice_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if (
            not await self._can_use_ai(interaction.user)
            or (not NAVY_API_KEYS and not ELEVENLABS_API_KEY)
        ):
            return []
        try:
            voices = await self._get_elevenlabs_voices()
        except (AIServiceUnavailable, aiohttp.ClientError, asyncio.TimeoutError):
            return []
        query = current.strip().casefold()
        return [
            app_commands.Choice(name=voice["name"][:100], value=voice["id"])
            for voice in voices
            if not query or query in voice["name"].casefold()
        ][:25]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AI(bot))
