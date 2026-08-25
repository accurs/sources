from __future__ import annotations

import ast
import asyncio
import math
import operator
import re
import secrets
import string
import time
import colorsys
import io
import json
import os
from datetime import datetime
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw

from src.services.colors import resolve_color


UNIT_CHOICES = [
    app_commands.Choice(name="Celsius", value="celsius"),
    app_commands.Choice(name="Fahrenheit", value="fahrenheit"),
]

COMMON_CURRENCIES = {
    "DKK": "Danish Krone", "EUR": "Euro", "USD": "US Dollar",
    "GBP": "British Pound", "SEK": "Swedish Krona", "NOK": "Norwegian Krone",
    "CHF": "Swiss Franc", "CAD": "Canadian Dollar", "AUD": "Australian Dollar",
    "NZD": "New Zealand Dollar", "JPY": "Japanese Yen", "CNY": "Chinese Yuan",
    "HKD": "Hong Kong Dollar", "SGD": "Singapore Dollar", "KRW": "South Korean Won",
    "INR": "Indian Rupee", "BRL": "Brazilian Real", "MXN": "Mexican Peso",
    "PLN": "Polish Zloty", "CZK": "Czech Koruna", "HUF": "Hungarian Forint",
    "RON": "Romanian Leu", "BGN": "Bulgarian Lev", "TRY": "Turkish Lira",
    "ZAR": "South African Rand", "AED": "UAE Dirham", "SAR": "Saudi Riyal",
    "ILS": "Israeli Shekel", "THB": "Thai Baht", "IDR": "Indonesian Rupiah",
}

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

WEATHER_CODES = {
    0: ("☀️", "Clear sky"), 1: ("🌤️", "Mainly clear"),
    2: ("⛅", "Partly cloudy"), 3: ("☁️", "Overcast"),
    45: ("🌫️", "Fog"), 48: ("🌫️", "Rime fog"),
    51: ("🌦️", "Light drizzle"), 53: ("🌦️", "Drizzle"),
    55: ("🌧️", "Heavy drizzle"), 56: ("🌧️", "Freezing drizzle"),
    57: ("🌧️", "Heavy freezing drizzle"), 61: ("🌦️", "Light rain"),
    63: ("🌧️", "Rain"), 65: ("🌧️", "Heavy rain"),
    66: ("🌧️", "Freezing rain"), 67: ("🌧️", "Heavy freezing rain"),
    71: ("🌨️", "Light snow"), 73: ("🌨️", "Snow"),
    75: ("❄️", "Heavy snow"), 77: ("❄️", "Snow grains"),
    80: ("🌦️", "Light showers"), 81: ("🌧️", "Showers"),
    82: ("⛈️", "Heavy showers"), 85: ("🌨️", "Snow showers"),
    86: ("❄️", "Heavy snow showers"), 95: ("⛈️", "Thunderstorm"),
    96: ("⛈️", "Thunderstorm with hail"), 99: ("⛈️", "Severe hailstorm"),
}

COMMON_WORDS = ("kindness", "journey", "balance", "curious", "create", "gentle", "honest", "moment", "wonder", "bright")
DIFFICULT_WORDS = ("sesquipedalian", "perspicacious", "obfuscate", "ineffable", "vicissitude", "pulchritude", "antediluvian", "circumlocution")
WOTD_HISTORY = Path(__file__).resolve().parents[2] / ".cache" / "dictionary" / "word_of_the_day_history.json"

TRANSLATION_LANGUAGES = {
    "auto": "Detect language", "ar": "Arabic", "bg": "Bulgarian", "bn": "Bengali",
    "ca": "Catalan", "cs": "Czech", "da": "Danish", "de": "German",
    "el": "Greek", "en": "English", "es": "Spanish", "et": "Estonian",
    "fa": "Persian", "fi": "Finnish", "fr": "French", "he": "Hebrew",
    "hi": "Hindi", "hr": "Croatian", "hu": "Hungarian", "id": "Indonesian",
    "it": "Italian", "ja": "Japanese", "ko": "Korean", "lt": "Lithuanian",
    "lv": "Latvian", "ms": "Malay", "nl": "Dutch", "no": "Norwegian",
    "pl": "Polish", "pt": "Portuguese", "ro": "Romanian", "ru": "Russian",
    "sk": "Slovak", "sl": "Slovenian", "sr": "Serbian", "sv": "Swedish",
    "sw": "Swahili", "ta": "Tamil", "th": "Thai", "tr": "Turkish",
    "uk": "Ukrainian", "ur": "Urdu", "vi": "Vietnamese",
    "zh-CN": "Chinese (Simplified)", "zh-TW": "Chinese (Traditional)",
}


class TranslationServiceError(Exception):
    pass


TRANSLATION_APP_LANGUAGES = (
    "en", "da", "es", "fr", "de", "it", "pt", "nl", "sv", "no",
    "fi", "pl", "ru", "uk", "tr", "ar", "hi", "ja", "ko", "zh-CN",
    "zh-TW", "id", "vi", "th", "el",
)
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
NAVY_TRANSLATION_MODEL = os.getenv(
    "NAVY_TRANSLATION_MODEL", "gpt-4.1-nano"
).strip()


class TranslateLanguageSelect(discord.ui.Select):
    def __init__(self, translation: TranslateMessageView) -> None:
        self.translation = translation
        super().__init__(
            placeholder="Choose the translation language",
            options=[
                discord.SelectOption(
                    label=TRANSLATION_LANGUAGES[code],
                    value=code,
                    description=code,
                    default=code == translation.target,
                )
                for code in TRANSLATION_APP_LANGUAGES
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        target = self.values[0]
        await interaction.response.defer()
        try:
            translated, provider, detected_source = await self.translation.cog._translate_result(
                self.translation.text,
                "auto",
                target,
            )
        except (
            aiohttp.ClientError,
            asyncio.TimeoutError,
            TranslationServiceError,
            ValueError,
        ):
            await interaction.followup.send(
                "The translation services are unavailable right now. Try again shortly.",
                ephemeral=True,
            )
            return
        self.translation.target = target
        self.translation.translated = translated
        self.translation.provider = provider
        self.translation.detected_source = detected_source
        self.translation.render()
        await interaction.edit_original_response(view=self.translation)


class TranslateMessageView(discord.ui.LayoutView):
    def __init__(
        self,
        cog: EverydayTools,
        text: str,
        author_id: int,
        translated: str,
        provider: str,
        detected_source: str | None,
    ) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.text = text
        self.author_id = author_id
        self.target = "en"
        self.translated = translated
        self.provider = provider
        self.detected_source = detected_source
        self.render()

    def render(self) -> None:
        self.clear_items()
        target_name = TRANSLATION_LANGUAGES[self.target]
        source_name = self.cog._language_name(self.detected_source)
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## {source_name} → {target_name}"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(self.translated),
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"-# Translated with {self.provider}"),
                discord.ui.ActionRow(TranslateLanguageSelect(self)),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "This translation menu belongs to someone else.", ephemeral=True
        )
        return False

class WOTDHistorySelect(discord.ui.Select):
    def __init__(self, history: list[dict], current: int) -> None:
        super().__init__(placeholder="Choose a day",options=[discord.SelectOption(label=str(item.get("date") or item.get("word"))[:100],value=str(index),default=index==current) for index,item in enumerate(history)])
    async def callback(self,i):
        view=self.view;assert isinstance(view,WOTDHistoryView);view.current=int(self.values[0]);view.render();await i.response.edit_message(view=view)


class WOTDHistoryView(discord.ui.LayoutView):
    def __init__(self,history:list[dict],author_id:int):super().__init__(timeout=180);self.history=history;self.author_id=author_id;self.current=0;self.render()
    def render(self):
        self.clear_items();item=self.history[self.current];body=f"## {item.get('word','Unknown')}\n**{item.get('part','Word')}** · {item.get('phonetic','')}\n{item.get('definition','No definition available.')}"
        if item.get("explanation"):body+=f"\n\n{item['explanation']}"
        if item.get("example"):body+=f"\n\n*{item['example']}*"
        self.add_item(discord.ui.Container(discord.ui.TextDisplay(body),discord.ui.Separator(),discord.ui.TextDisplay(f"-# {item.get('date','')} · Dictionary.com · {self.current+1}/{len(self.history)}"),discord.ui.ActionRow(WOTDHistorySelect(self.history,self.current))))
    async def interaction_check(self,i):
        if i.user.id==self.author_id:return True
        await i.response.send_message("This history menu belongs to someone else.",ephemeral=True);return False


class SafeCalculator:
    OPERATORS = {
        ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod, ast.Pow: operator.pow,
        ast.UAdd: operator.pos, ast.USub: operator.neg,
    }
    FUNCTIONS = {
        "abs": abs, "round": round, "sqrt": math.sqrt,
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "log": math.log, "min": min, "max": max,
    }
    CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}

    @classmethod
    def evaluate(cls, expression: str) -> int | float:
        tree = ast.parse(expression, mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 60:
            raise ValueError("Expression is too complicated")
        result = cls._node(tree.body)
        if isinstance(result, complex) or not math.isfinite(float(result)):
            raise ValueError("Result is not a finite number")
        return result

    @classmethod
    def _node(cls, node: ast.AST):
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            return node.value
        if isinstance(node, ast.Name) and node.id in cls.CONSTANTS:
            return cls.CONSTANTS[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in cls.OPERATORS:
            left, right = cls._node(node.left), cls._node(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("Exponent is too large")
            return cls.OPERATORS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in cls.OPERATORS:
            return cls.OPERATORS[type(node.op)](cls._node(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            function = cls.FUNCTIONS.get(node.func.id)
            if function is not None and not node.keywords and len(node.args) <= 10:
                return function(*(cls._node(argument) for argument in node.args))
        raise ValueError("Unsupported expression")


def emoji_count_and_positions(text: str) -> tuple[int, set[int]]:
    """Count common Unicode and Discord custom emoji as whole sequences."""
    covered: set[int] = set()
    count = 0
    for match in re.finditer(r"<a?:[A-Za-z0-9_]+:\d+>", text):
        covered.update(range(match.start(), match.end()))
        count += 1

    def is_base(character: str) -> bool:
        code = ord(character)
        return (
            0x1F1E6 <= code <= 0x1F1FF
            or 0x1F300 <= code <= 0x1FAFF
            or 0x2600 <= code <= 0x27BF
        )

    index = 0
    while index < len(text):
        if index in covered:
            index += 1
            continue
        start = index
        character = text[index]
        code = ord(character)

        if character in "#*0123456789":
            end = index + 1
            if end < len(text) and ord(text[end]) == 0xFE0F:
                end += 1
            if end < len(text) and ord(text[end]) == 0x20E3:
                covered.update(range(start, end + 1))
                count += 1
                index = end + 1
                continue

        if 0x1F1E6 <= code <= 0x1F1FF:
            end = index + 1
            if end < len(text) and 0x1F1E6 <= ord(text[end]) <= 0x1F1FF:
                end += 1
            covered.update(range(start, end))
            count += 1
            index = end
            continue

        if not is_base(character):
            index += 1
            continue

        end = index + 1
        while end < len(text) and ord(text[end]) in range(0xFE00, 0xFE10):
            end += 1
        if end < len(text) and 0x1F3FB <= ord(text[end]) <= 0x1F3FF:
            end += 1
        while end + 1 < len(text) and ord(text[end]) == 0x200D:
            end += 2
            while end < len(text) and (
                ord(text[end]) in range(0xFE00, 0xFE10)
                or 0x1F3FB <= ord(text[end]) <= 0x1F3FF
            ):
                end += 1
        covered.update(range(start, end))
        count += 1
        index = end
    return count, covered


class EverydayTools(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._weather_location_cache: dict[str, tuple[float, list[dict]]] = {}
        self._currency_cache: dict[tuple[str, str], tuple[float, float, str]] = {}
        self.translate_context_menu = app_commands.ContextMenu(
            name="Translate Message",
            callback=self.translate_message,
        )
        self.bot.tree.add_command(self.translate_context_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.translate_context_menu.name,
            type=self.translate_context_menu.type,
        )

    @staticmethod
    def _language_code(value: str, *, allow_auto: bool) -> str | None:
        cleaned = " ".join(value.strip().split()).casefold()
        for code, name in TRANSLATION_LANGUAGES.items():
            if cleaned in {code.casefold(), name.casefold()}:
                return code if allow_auto or code != "auto" else None
        return None

    @staticmethod
    def _language_name(code: str | None) -> str:
        if not code:
            return "Detected language"
        return TRANSLATION_LANGUAGES.get(code, code.upper())

    async def _translate_mymemory(
        self, text: str, source: str, target: str
    ) -> tuple[str, str | None]:
        if len(text.encode("utf-8")) > 500:
            raise TranslationServiceError("MyMemory accepts at most 500 bytes")
        mymemory_source = "autodetect" if source == "auto" else source
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                "https://api.mymemory.translated.net/get",
                params={"q": text, "langpair": f"{mymemory_source}|{target}"},
            ) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        data = payload.get("responseData") if isinstance(payload, dict) else None
        translation = data.get("translatedText") if isinstance(data, dict) else None
        detected = data.get("detectedLanguage") if isinstance(data, dict) else None
        if not isinstance(detected, str) or not detected.strip():
            detected = source if source != "auto" else None
        status = payload.get("responseStatus") if isinstance(payload, dict) else None
        detail = payload.get("responseDetails") if isinstance(payload, dict) else None
        if (
            str(status) == "403"
            and "distinct languages" in str(detail).casefold()
            and isinstance(translation, str)
            and translation.strip()
        ):
            # Auto-detection found that the message is already written in the
            # selected target language. MyMemory returns the original text but
            # labels that perfectly valid result as HTTP-style status 403.
            return translation.strip(), detected
        if str(status) != "200" or not isinstance(translation, str) or not translation.strip():
            raise TranslationServiceError(str(detail or "MyMemory returned no translation"))
        return translation.strip(), detected

    async def _translate_navy(
        self, text: str, source: str, target: str
    ) -> tuple[str, str | None]:
        if not NAVY_API_KEYS:
            raise TranslationServiceError("Navy is not configured")
        source_instruction = (
            "Detect the source language" if source == "auto" else f"The source language is {source}"
        )
        timeout = aiohttp.ClientTimeout(total=30)
        request_data = {
            "model": NAVY_TRANSLATION_MODEL,
            "temperature": 0,
            "max_tokens": 1_200,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Translate the entire text naturally for a native speaker. "
                        "Preserve its meaning, tone, slang, humor, punctuation, and "
                        "formatting instead of translating mechanically word by word. "
                        "Do not leave ordinary words or phrases untranslated; only "
                        "retain proper names and expressions that native speakers would "
                        "normally keep. Do not explain, censor, or summarize. Return only JSON "
                        "with string fields translation and source_language. "
                        "source_language must be an ISO 639-1 language code."
                    ),
                },
                {
                    "role": "user",
                    "content": f"{source_instruction}. Translate into {target}.\n\n{text}",
                },
            ],
        }
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for api_key in NAVY_API_KEYS:
                try:
                    async with session.post(
                        "https://api.navy/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json=request_data,
                    ) as response:
                        if response.status != 200:
                            continue
                        payload = await response.json(content_type=None)
                    content = payload["choices"][0]["message"]["content"]
                    result = json.loads(content)
                    translated = result["translation"].strip()
                    detected = result.get("source_language")
                except (
                    aiohttp.ClientError,
                    asyncio.TimeoutError,
                    KeyError,
                    IndexError,
                    TypeError,
                    ValueError,
                    json.JSONDecodeError,
                ):
                    continue
                if not translated:
                    continue
                if isinstance(detected, str):
                    detected = detected.strip().split("-", 1)[0].casefold() or None
                else:
                    detected = source if source != "auto" else None
                return translated, detected
        raise TranslationServiceError("Every Navy key failed")

    async def _translate_result(
        self, text: str, source: str, target: str
    ) -> tuple[str, str, str | None]:
        for provider, translator in (
            ("Navy", self._translate_navy),
            ("MyMemory", self._translate_mymemory),
        ):
            try:
                translated, detected = await translator(text, source, target)
                return translated, provider, detected
            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
                TranslationServiceError,
                ValueError,
            ):
                continue
        raise TranslationServiceError("No translation provider is available")

    async def _send_translation(
        self,
        interaction: discord.Interaction,
        text: str,
        target: str,
        source: str,
        *,
        ephemeral: bool,
    ) -> None:
        text = text.strip()
        if not text:
            await interaction.response.send_message(
                "That message does not contain any text to translate.", ephemeral=True
            )
            return
        byte_length = len(text.encode("utf-8"))
        if byte_length > 500:
            await interaction.response.send_message(
                "Translation text can be at most `500` UTF-8 bytes.",
                ephemeral=True,
            )
            return
        source_code = self._language_code(source, allow_auto=True)
        target_code = self._language_code(target, allow_auto=False)
        if source_code is None or target_code is None:
            await interaction.response.send_message(
                "Choose a supported language name or code.", ephemeral=True
            )
            return
        if source_code == target_code:
            await interaction.response.send_message(
                "The source and target languages must be different.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=ephemeral)
        try:
            translated, provider, detected_source = await self._translate_result(
                text, source_code, target_code
            )
        except TranslationServiceError:
            try:
                await interaction.delete_original_response()
            except discord.HTTPException:
                pass
            await interaction.followup.send(
                "The translation services are unavailable right now. Try again shortly.",
                ephemeral=True,
            )
            return

        source_name = self._language_name(
            detected_source if source_code == "auto" else source_code
        )
        target_name = TRANSLATION_LANGUAGES[target_code]
        view = discord.ui.LayoutView(timeout=180)
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## {source_name} → {target_name}"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(translated),
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"-# Translated with {provider}"),
            )
        )
        await interaction.followup.send(
            view=view,
            ephemeral=ephemeral,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @staticmethod
    def _weather_location_label(place: dict) -> str:
        parts = [
            str(place.get(key) or "").strip()
            for key in ("name", "admin2", "admin1", "country")
        ]
        return ", ".join(dict.fromkeys(part for part in parts if part))

    async def _weather_locations(self, query: str, count: int = 10) -> list[dict]:
        raw = " ".join(query.strip().split())
        cache_key = raw.casefold()
        cached = self._weather_location_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < 300:
            return cached[1][:count]

        country_code = None
        cleaned = raw
        country_patterns = (
            (r"\b(?:united\s+kingdom|great\s+britain|england|uk|gb)\b", "GB"),
            (r"\b(?:united\s+states|usa|us)\b", "US"),
        )
        for pattern, code in country_patterns:
            if re.search(pattern, cleaned, flags=re.IGNORECASE):
                country_code = code
                cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
                break
        cleaned = " ".join(cleaned.replace(",", " ").split())
        terms = [cleaned]
        if " " in cleaned:
            terms.append(cleaned.split()[0])

        places: list[dict] = []
        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for term in dict.fromkeys(term for term in terms if len(term) >= 2):
                params = {
                    "name": term,
                    "count": 20,
                    "language": "en",
                    "format": "json",
                }
                if country_code:
                    params["countryCode"] = country_code
                async with session.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params=params,
                ) as response:
                    response.raise_for_status()
                    results = (await response.json()).get("results", [])
                if results:
                    qualifiers = set(cleaned.casefold().split()[1:])
                    places = sorted(
                        (place for place in results if isinstance(place, dict)),
                        key=lambda place: sum(
                            qualifier in self._weather_location_label(place).casefold()
                            for qualifier in qualifiers
                        ),
                        reverse=True,
                    )
                    break
        self._weather_location_cache[cache_key] = (time.monotonic(), places)
        return places[:count]

    @app_commands.command(name="calculate", description="Safely calculate an expression")
    @app_commands.describe(
        expression="Example: (12 + 8) * 3 or sqrt(144)",
        ephemeral="Only show the result to you",
    )
    async def calculate(
        self,
        interaction: discord.Interaction,
        expression: app_commands.Range[str, 1, 200],
        ephemeral: bool = False,
    ) -> None:
        try:
            result = SafeCalculator.evaluate(expression)
        except (ValueError, TypeError, ZeroDivisionError, OverflowError) as error:
            await interaction.response.send_message(
                f"I couldn't calculate that: {error}", ephemeral=True
            )
            return
        rendered = f"{result:.12g}" if isinstance(result, float) else str(result)
        await interaction.response.send_message(
            f"`{expression}` = `{rendered}`", ephemeral=ephemeral
        )

    @app_commands.command(name="characters", description="Count characters and text statistics")
    @app_commands.describe(
        text="Text to analyse",
        ephemeral="Only show the results to you",
    )
    async def characters(
        self,
        interaction: discord.Interaction,
        text: app_commands.Range[str, 1, 4000],
        ephemeral: bool = False,
    ) -> None:
        total = len(text)
        words = len(re.findall(r"\S+", text))
        numbers = sum(character.isdigit() for character in text)
        emojis, emoji_positions = emoji_count_and_positions(text)
        special_characters = sum(
            not character.isalnum()
            and not character.isspace()
            and index not in emoji_positions
            for index, character in enumerate(text)
        )
        view = discord.ui.LayoutView(timeout=180)
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("## Text Statistics"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"**Characters:** {total:,}\n"
                    f"**Characters without spaces:** {len(text.replace(' ', '')):,}\n"
                    f"**Words:** {words:,}\n"
                    f"**Special characters:** {special_characters:,}\n"
                    f"**Emojis:** {emojis:,}\n"
                    f"**Numbers:** {numbers:,}"
                ),
            )
        )
        await interaction.response.send_message(view=view, ephemeral=ephemeral)

    @app_commands.command(name="translate", description="Translate text into another language")
    @app_commands.describe(
        text="Text to translate",
        target="Target language name or code",
        source="Source language name or code (automatically detected by default)",
        ephemeral="Only show the translation to you",
    )
    async def translate(
        self,
        interaction: discord.Interaction,
        text: app_commands.Range[str, 1, 1000],
        target: app_commands.Range[str, 2, 40],
        source: app_commands.Range[str, 2, 40] = "auto",
        ephemeral: bool = False,
    ) -> None:
        await self._send_translation(
            interaction,
            text,
            target,
            source,
            ephemeral=ephemeral,
        )

    async def translate_message(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ) -> None:
        text = message.content.strip()
        if not text:
            await interaction.response.send_message(
                "That message does not contain any text to translate.", ephemeral=True
            )
            return
        if len(text.encode("utf-8")) > 500:
            await interaction.response.send_message(
                "Translation text can be at most `500` UTF-8 bytes.", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True)
        try:
            translated, provider, detected_source = await self._translate_result(
                text, "auto", "en"
            )
        except TranslationServiceError:
            try:
                await interaction.delete_original_response()
            except discord.HTTPException:
                pass
            await interaction.followup.send(
                "The translation services are unavailable right now. Try again shortly.",
                ephemeral=True,
            )
            return
        await interaction.edit_original_response(
            content=None,
            view=TranslateMessageView(
                self,
                text,
                interaction.user.id,
                translated,
                provider,
                detected_source,
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @translate.autocomplete("source")
    async def translate_source_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return self._translation_language_choices(current, allow_auto=True)

    @translate.autocomplete("target")
    async def translate_target_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return self._translation_language_choices(current, allow_auto=False)

    @staticmethod
    def _translation_language_choices(
        current: str, *, allow_auto: bool
    ) -> list[app_commands.Choice[str]]:
        query = current.strip().casefold()
        return [
            app_commands.Choice(name=f"{name} ({code})", value=code)
            for code, name in TRANSLATION_LANGUAGES.items()
            if (allow_auto or code != "auto")
            and (not query or query in name.casefold() or query in code.casefold())
        ][:25]

    @app_commands.command(name="weather", description="Show current weather and a 3-day forecast")
    @app_commands.choices(units=UNIT_CHOICES)
    @app_commands.describe(
        location="City, town, or postal code",
        units="Celsius or Fahrenheit",
        ephemeral="Only show the forecast to you",
    )
    async def weather(
        self,
        interaction: discord.Interaction,
        location: app_commands.Range[str, 2, 100],
        units: app_commands.Choice[str] | None = None,
        ephemeral: bool = False,
    ) -> None:
        await interaction.response.defer(ephemeral=ephemeral)
        unit = units.value if units else "celsius"
        try:
            if location.startswith("geo:"):
                _, latitude, longitude, label = location.split(":", 3)
                place = {
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "name": label,
                }
            else:
                places = await self._weather_locations(location, count=10)
                if not places:
                    await interaction.followup.send(
                        "I couldn't find that location. Try selecting one of the suggestions.",
                        ephemeral=ephemeral,
                    )
                    return
                place = places[0]
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": place["latitude"], "longitude": place["longitude"],
                        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
                        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                        "temperature_unit": "fahrenheit" if unit == "fahrenheit" else "celsius",
                        "wind_speed_unit": "mph" if unit == "fahrenheit" else "kmh",
                        "timezone": "auto", "forecast_days": 3,
                    },
                ) as response:
                    response.raise_for_status()
                    forecast = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, ValueError):
            await interaction.followup.send(
                "The weather service is unavailable right now. Try again shortly.",
                ephemeral=ephemeral,
            )
            return

        current, daily = forecast["current"], forecast["daily"]
        symbol, condition = WEATHER_CODES.get(current["weather_code"], ("🌡️", "Unknown"))
        degree = "°F" if unit == "fahrenheit" else "°C"
        wind_unit = "mph" if unit == "fahrenheit" else "km/h"
        place_name = ", ".join(filter(None, (place.get("name"), place.get("admin1"), place.get("country"))))
        forecast_lines = []
        for index, date_value in enumerate(daily["time"]):
            day_symbol, day_condition = WEATHER_CODES.get(daily["weather_code"][index], ("🌡️", "Unknown"))
            day_name = datetime.fromisoformat(date_value).strftime("%A, %d %B")
            forecast_lines.append(
                f"**{day_symbol} {day_name}**\n"
                f"{day_condition} • "
                f"{daily['temperature_2m_min'][index]}–"
                f"{daily['temperature_2m_max'][index]}{degree} • "
                f"Rain {daily['precipitation_probability_max'][index]}%"
            )
        view = discord.ui.LayoutView(timeout=180)
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## {symbol} Weather in {place_name}"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    f"### {condition} • {current['temperature_2m']}{degree}\n"
                    f"**Feels like:** {current['apparent_temperature']}{degree}\n"
                    f"**Humidity:** {current['relative_humidity_2m']}%\n"
                    f"**Wind:** {current['wind_speed_10m']} {wind_unit}"
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    "### 3-Day Forecast\n" + "\n\n".join(forecast_lines)
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay("-# Weather data provided by Open-Meteo"),
            )
        )
        await interaction.followup.send(view=view, ephemeral=ephemeral)

    @weather.autocomplete("location")
    async def weather_location_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if len(current.strip()) < 2:
            return []
        try:
            places = await self._weather_locations(current, count=10)
        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, ValueError):
            return []

        choices = []
        for place in places:
            label = self._weather_location_label(place) or "Unknown location"
            value = (
                f"geo:{place['latitude']}:{place['longitude']}:"
                f"{label[:60]}"
            )
            choices.append(
                app_commands.Choice(name=label[:100], value=value[:100])
            )
        return choices

    @app_commands.command(name="exchange", description="Convert one currency into up to ten others")
    @app_commands.describe(
        amount="Amount to convert",
        from_currency="Currency to convert from, such as USD",
        to_currencies="Currencies to convert to, separated by spaces or commas",
        amount_2="Optional second amount",
        amount_3="Optional third amount",
        amount_4="Optional fourth amount",
        amount_5="Optional fifth amount",
    )
    async def exchange(
        self,
        interaction: discord.Interaction,
        amount: float,
        from_currency: str,
        to_currencies: str,
        amount_2: float | None = None,
        amount_3: float | None = None,
        amount_4: float | None = None,
        amount_5: float | None = None,
    ) -> None:
        amounts = [amount] + [
            value for value in (amount_2, amount_3, amount_4, amount_5)
            if value is not None
        ]
        if any(not math.isfinite(value) or value <= 0 for value in amounts):
            await interaction.response.send_message("Every amount must be a positive number.", ephemeral=True); return
        source = from_currency.upper().strip()
        targets = list(dict.fromkeys(part for part in re.split(r"[\s,]+", to_currencies.upper().strip()) if part))
        if not re.fullmatch(r"[A-Z]{3}", source) or not targets or any(not re.fullmatch(r"[A-Z]{3}", target) for target in targets):
            await interaction.response.send_message("Use three-letter currency codes such as `USD`, `GBP`, or `EUR`.", ephemeral=True); return
        if len(targets) > 10:
            await interaction.response.send_message("Choose up to 10 currencies to convert to.", ephemeral=True); return
        await interaction.response.defer()
        now=time.monotonic();rates={};dates={};stale=False
        missing=[]
        for target in targets:
            if target == source:
                rates[target]=1.0
                continue
            cached=self._currency_cache.get((source,target))
            if cached and now-cached[0]<3600:
                _,rates[target],dates[target]=cached
            else:
                missing.append(target)
        try:
            if missing:
                timeout=aiohttp.ClientTimeout(total=12)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get("https://api.frankfurter.dev/v2/rates",params={"base":source,"quotes":",".join(missing)}) as response:
                        response.raise_for_status();data=await response.json()
                loaded={str(item["quote"]):(float(item["rate"]),str(item["date"])) for item in data}
                if any(target not in loaded for target in missing):raise KeyError
                for target in missing:
                    rates[target],dates[target]=loaded[target]
                    self._currency_cache[(source,target)]=(now,rates[target],dates[target])
        except (aiohttp.ClientError,asyncio.TimeoutError,KeyError,TypeError,ValueError):
            fallback={target:self._currency_cache.get((source,target)) for target in missing}
            if any(value is None for value in fallback.values()):
                await interaction.followup.send("Exchange rates are unavailable right now.",ephemeral=True);return
            for target,cached in fallback.items():
                assert cached is not None
                _,rates[target],dates[target]=cached
            stale=True
        update_dates=sorted(set(dates.values()))
        updated=update_dates[0] if len(update_dates)==1 else ", ".join(update_dates) if update_dates else "N/A"
        if len(amounts) == 1:
            exchange_text = (
                f"**From**\n`{amount:,.2f} {source}`\n\n**Converted**\n"
                + "\n".join(f"`{amount*rates[target]:,.2f} {target}`" for target in targets)
            )
        else:
            sections = []
            for value in amounts:
                converted = "\n".join(
                    f"`{value*rates[target]:,.2f} {target}`" for target in targets
                )
                sections.append(f"### {value:,.2f} {source}\n{converted}")
            exchange_text = "\n\n".join(sections)
        view=discord.ui.LayoutView();view.add_item(discord.ui.Container(
            discord.ui.TextDisplay(f"## Exchange\n{exchange_text}\n\n**Updated:** {updated}"),
            discord.ui.Separator(),discord.ui.TextDisplay(f"-# Central-bank reference rates{' · cached fallback' if stale else ''}")
        ));await interaction.followup.send(view=view)

    @exchange.autocomplete("from_currency")
    async def exchange_from_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        query = current.strip().casefold()
        return [
            app_commands.Choice(name=f"{code} — {name}", value=code)
            for code, name in COMMON_CURRENCIES.items()
            if not query or query in code.casefold() or query in name.casefold()
        ][:25]

    @exchange.autocomplete("to_currencies")
    async def exchange_to_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        parts = [part for part in re.split(r"[\s,]+", current.upper().strip()) if part]
        ends_with_separator = bool(current) and bool(re.search(r"[\s,]$", current))
        completed = parts if ends_with_separator else parts[:-1]
        query = "" if ends_with_separator or not parts else parts[-1].casefold()
        source = str(getattr(interaction.namespace, "from_currency", "") or "").upper().strip()
        excluded = set(completed)
        if source:
            excluded.add(source)
        choices: list[app_commands.Choice[str]] = []
        for code, name in COMMON_CURRENCIES.items():
            if code in excluded:
                continue
            if query and query not in code.casefold() and query not in name.casefold():
                continue
            value = " ".join((*completed, code))
            choices.append(app_commands.Choice(name=f"{code} — {name}", value=value))
        return choices[:25]

    @app_commands.command(name="password", description="Securely generate up to five passwords")
    async def password(self, interaction: discord.Interaction, length: app_commands.Range[int,8,100]=20, numbers: bool=True, symbols: bool=True, uppercase: bool=True, avoid_confusing: bool=True, count: app_commands.Range[int,1,5]=1) -> None:
        alphabet=string.ascii_lowercase
        if uppercase:alphabet+=string.ascii_uppercase
        if numbers:alphabet+=string.digits
        if symbols:alphabet+="!@#$%^&*()-_=+"
        if avoid_confusing:alphabet="".join(c for c in alphabet if c not in "Il1O0o|`")
        generated=["".join(secrets.choice(alphabet) for _ in range(length)) for _ in range(count)]
        view=discord.ui.LayoutView();view.add_item(discord.ui.Container(discord.ui.TextDisplay("## Generated Passwords\n"+"\n".join(f"`{value}`" for value in generated)),discord.ui.Separator(),discord.ui.TextDisplay("-# Generated securely · Never saved")))
        await interaction.response.send_message(view=view,ephemeral=True)

    @commands.hybrid_group(
        name="color",
        aliases=["hex"],
        description="Inspect colors and create color transitions",
        invoke_without_command=True,
    )
    async def color(self,ctx:commands.Context,*,query:str|None=None)->None:
        if ctx.invoked_subcommand is not None:return
        if query is None:
            await ctx.send("Use `/color inspect`, `/color gradient`, `;color <color>`, or `;color gradient <start> <end>`.",ephemeral=ctx.interaction is not None);return
        await self._send_color(ctx,query)

    @color.command(name="inspect",description="Inspect a color and get palette recommendations")
    @app_commands.describe(query="Color name, HEX value, or RGB value")
    async def color_inspect(self,ctx:commands.Context,*,query:str)->None:
        await self._send_color(ctx,query)

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
        cleaned=query.strip()
        try:
            rgb,resolved_name=await resolve_color(cleaned)
        except ValueError as error:
            await ctx.send(str(error),ephemeral=ctx.interaction is not None);return
        red,green,blue=rgb;hex_value=f"#{red:02X}{green:02X}{blue:02X}";h,l,s=colorsys.rgb_to_hls(red/255,green/255,blue/255);brightness=(red*299+green*587+blue*114)/1000;foreground="Black" if brightness>150 else "White"
        def palette_hex(hue: float, lightness: float, saturation: float) -> str:
            values=colorsys.hls_to_rgb(hue%1,max(0,min(1,lightness)),max(0,min(1,saturation)))
            return "#"+"".join(f"{round(value*255):02X}" for value in values)
        recommendations={
            "Complementary":palette_hex(h+.5,l,s),
            "Analogous":palette_hex(h+1/12,l,s),
            "Lighter":palette_hex(h,min(.88,l+.2),s),
            "Darker":palette_hex(h,max(.12,l-.2),s),
        }
        swatch=io.BytesIO();Image.new("RGB",(256,144),(red,green,blue)).save(swatch,format="PNG");swatch.seek(0)
        filename="color-swatch.png"
        display_title=f"{resolved_name} · {hex_value}" if resolved_name else hex_value
        details=discord.ui.Section(
            discord.ui.TextDisplay(f"## {display_title}\n**RGB** · `{red}, {green}, {blue}`\n**HSL** · `{round(h*360)}°, {round(s*100)}%, {round(l*100)}%`\n**Brightness** · `{round(brightness)}/255`\n**Best text color** · `{foreground}`"),
            accessory=discord.ui.Thumbnail(f"attachment://{filename}",description=f"{hex_value} color swatch"),
        )
        palette="\n".join(f"**{name}** · `{value}`" for name,value in recommendations.items())
        view=discord.ui.LayoutView();view.add_item(discord.ui.Container(
            details,
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"### Recommended Palette\n{palette}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay("-# Prefix: ;color or ;hex · Slash: /color inspect"),
        ))
        await ctx.send(view=view,file=discord.File(swatch,filename=filename))

    @color.command(
        name="gradient",
        aliases=["palette"],
        description="Create a custom transition between two colors",
    )
    @app_commands.describe(start="First color",end="Last color",amount="Number of colors (2–10)")
    async def color_gradient(self,ctx:commands.Context,start:str,end:str,amount:app_commands.Range[int,2,10]=5)->None:
        if ctx.interaction is not None and not ctx.interaction.response.is_done():await ctx.defer()
        try:
            start_rgb,_=await resolve_color(start);end_rgb,_=await resolve_color(end)
        except ValueError as error:
            await ctx.send(str(error),ephemeral=ctx.interaction is not None);return
        colors=[]
        for index in range(amount):
            ratio=index/(amount-1)
            rgb=tuple(round(first+(last-first)*ratio) for first,last in zip(start_rgb,end_rgb))
            colors.append((rgb,"#"+"".join(f"{value:02X}" for value in rgb)))
        preview=Image.new("RGB",(800,180));draw=ImageDraw.Draw(preview)
        for index,(rgb,_) in enumerate(colors):
            left=round(index*800/amount);right=round((index+1)*800/amount)
            draw.rectangle((left,0,right,180),fill=rgb)
        output=io.BytesIO();preview.save(output,"PNG",optimize=True);output.seek(0);filename="color-gradient.png"
        values="  →  ".join(f"`{hex_value}`" for _,hex_value in colors)
        view=discord.ui.LayoutView();view.add_item(discord.ui.Container(
            discord.ui.TextDisplay(f"## Color Gradient\n{values}"),
            discord.ui.Separator(),
            discord.ui.MediaGallery(discord.MediaGalleryItem(f"attachment://{filename}",description=f"{amount}-color transition")),
            discord.ui.Separator(),discord.ui.TextDisplay("-# /color gradient · ;color gradient · ;color palette"),
        ))
        await ctx.send(view=view,file=discord.File(output,filename=filename))

    @app_commands.command(name="define-random", description="Get a random word in a chosen mode")
    @app_commands.choices(mode=[app_commands.Choice(name="Random",value="random"),app_commands.Choice(name="Common",value="common"),app_commands.Choice(name="Difficult",value="difficult"),app_commands.Choice(name="Word of the Day history",value="wotd")])
    async def define_random(self, interaction: discord.Interaction, mode: app_commands.Choice[str]|None=None) -> None:
        selected=mode.value if mode else "random"
        pool=COMMON_WORDS if selected=="common" else DIFFICULT_WORDS if selected=="difficult" else COMMON_WORDS+DIFFICULT_WORDS
        if selected=="wotd":
            try:history=json.loads(WOTD_HISTORY.read_text(encoding="utf-8"))
            except (OSError,ValueError,TypeError,json.JSONDecodeError):history=[]
            history=[item for item in history if isinstance(item,dict)][:7]
            if not history:await interaction.response.send_message("Use `/word-of-the-day` once to begin the rolling seven-day history.");return
            await interaction.response.send_message(view=WOTDHistoryView(history,interaction.user.id));return
        word=secrets.choice(pool);await interaction.response.defer()
        try:
            timeout=aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}") as response:
                    response.raise_for_status();data=await response.json()
            meaning=data[0]["meanings"][0];definition=meaning["definitions"][0];body=f"**{meaning.get('partOfSpeech','Word').title()}**\n{definition['definition']}"+(f"\n\n*{definition['example']}*" if definition.get('example') else "")
        except (aiohttp.ClientError,asyncio.TimeoutError,KeyError,IndexError,ValueError):body="A definition could not be loaded right now."
        view=discord.ui.LayoutView();view.add_item(discord.ui.Container(discord.ui.TextDisplay(f"## {word}\n{body}"),discord.ui.Separator(),discord.ui.TextDisplay("-# DictionaryAPI")));await interaction.followup.send(view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EverydayTools(bot))
