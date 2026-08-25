from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_FILE = PROJECT_ROOT / "bot_settings.json"
MAX_AVATAR_SIZE = 10 * 1024 * 1024
LASTFM_USERNAME = os.getenv("LASTFM_USERNAME", "").strip()
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY", "").strip()
LASTFM_POLL_SECONDS = 10
logger = logging.getLogger(__name__)

STATUS_CHOICES = [
    app_commands.Choice(name="Online", value="online"),
    app_commands.Choice(name="Idle", value="idle"),
    app_commands.Choice(name="Do Not Disturb", value="dnd"),
    app_commands.Choice(name="Invisible", value="invisible"),
]

ACTIVITY_CHOICES = [
    app_commands.Choice(name="Playing", value="playing"),
    app_commands.Choice(name="Watching", value="watching"),
    app_commands.Choice(name="Listening", value="listening"),
    app_commands.Choice(name="Last.fm Now Playing", value="lastfm"),
    app_commands.Choice(name="Competing", value="competing"),
    app_commands.Choice(name="Streaming", value="streaming"),
    app_commands.Choice(name="Clear Activity", value="clear"),
]


class Settings(commands.Cog):
    set_group = app_commands.Group(
        name="set",
        description="Change the bot's profile and presence",
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.presence_settings = self._load_settings()
        self._lastfm_task: asyncio.Task[None] | None = None
        self._lastfm_track: tuple[str, str] | None = None

    async def cog_unload(self) -> None:
        if self._lastfm_task is not None:
            self._lastfm_task.cancel()

    @staticmethod
    def _load_settings() -> dict[str, Any]:
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    async def _save_settings(self) -> None:
        payload = json.dumps(self.presence_settings, indent=2)
        await asyncio.to_thread(SETTINGS_FILE.write_text, payload, encoding="utf-8")

    async def _owner_check(self, interaction: discord.Interaction) -> bool:
        if await self.bot.can_use_owner_commands(interaction.user):
            return True

        await interaction.response.send_message(
            "Only the bot owner can change these settings.",
            ephemeral=True,
        )
        return False

    @staticmethod
    async def _respond(
        interaction: discord.Interaction,
        title: str,
        message: str,
    ) -> None:
        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## {title}\n{message}"),
            )
        )

        if interaction.response.is_done():
            await interaction.followup.send(view=view, ephemeral=True)
        else:
            await interaction.response.send_message(view=view, ephemeral=True)

    @staticmethod
    def _make_activity(settings: dict[str, Any]) -> discord.BaseActivity | None:
        kind = settings.get("activity_type")
        name = settings.get("activity_name")
        if not kind:
            return None

        if kind == "custom":
            emoji = settings.get("activity_emoji")
            if not name and not emoji:
                return None
            parsed_emoji = discord.PartialEmoji.from_str(emoji) if emoji else None
            return discord.CustomActivity(name=name or None, emoji=parsed_emoji)
        if not name:
            return None
        if kind == "playing":
            return discord.Game(name=name)
        if kind == "streaming":
            url = settings.get("stream_url")
            return discord.Streaming(name=name, url=url) if url else None

        activity_types = {
            "watching": discord.ActivityType.watching,
            "listening": discord.ActivityType.listening,
            "competing": discord.ActivityType.competing,
        }
        activity_type = activity_types.get(kind)
        if activity_type is None:
            return None
        return discord.Activity(type=activity_type, name=name)

    async def _apply_presence(self) -> None:
        statuses = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
        }
        status = statuses.get(
            self.presence_settings.get("status"),
            discord.Status.online,
        )
        activity = self._make_activity(self.presence_settings)
        await self.bot.change_presence(status=status, activity=activity)

    async def _fetch_lastfm_track(self) -> tuple[str, str] | None:
        params = {
            "method": "user.getrecenttracks",
            "user": LASTFM_USERNAME,
            "api_key": LASTFM_API_KEY,
            "format": "json",
            "limit": "1",
        }
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://ws.audioscrobbler.com/2.0/", params=params) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)

        if "error" in payload:
            raise RuntimeError(str(payload.get("message") or "Last.fm API error"))
        tracks = payload.get("recenttracks", {}).get("track", [])
        if isinstance(tracks, dict):
            tracks = [tracks]
        if not tracks or tracks[0].get("@attr", {}).get("nowplaying") != "true":
            return None
        name = str(tracks[0].get("name") or "").strip()
        artist_data = tracks[0].get("artist", {})
        artist = str(
            artist_data.get("#text", "")
            if isinstance(artist_data, dict)
            else artist_data
        ).strip()
        return (name, artist) if name and artist else None

    async def _update_lastfm_presence(self) -> None:
        track = await self._fetch_lastfm_track()
        if track == self._lastfm_track:
            return
        self._lastfm_track = track
        activity = None
        if track is not None:
            song, artist = track
            activity = discord.Activity(
                type=discord.ActivityType.listening,
                name=f"{song} — {artist}"[:128],
            )
        statuses = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
        }
        status = statuses.get(
            self.presence_settings.get("status"),
            discord.Status.online,
        )
        await self.bot.change_presence(status=status, activity=activity)

    async def _lastfm_worker(self) -> None:
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            if self.presence_settings.get("activity_type") == "lastfm":
                try:
                    await self._update_lastfm_presence()
                except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as error:
                    logger.warning(
                        "Could not refresh Last.fm now-playing activity (%s). "
                        "Trying again automatically.",
                        type(error).__name__,
                    )
            else:
                self._lastfm_track = None
            await asyncio.sleep(LASTFM_POLL_SECONDS)

    def _ensure_lastfm_worker(self) -> None:
        if self._lastfm_task is None or self._lastfm_task.done():
            self._lastfm_task = asyncio.create_task(
                self._lastfm_worker(),
                name="lastfm-presence",
            )

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self._apply_presence()
        self._ensure_lastfm_worker()

    @set_group.command(
        name="avatar",
        description="Change or reset the bot's avatar",
    )
    @app_commands.describe(image="Image to use; leave empty to reset")
    async def set_avatar(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment | None = None,
    ) -> None:
        if not await self._owner_check(interaction):
            return
        if image is not None and (
            not image.content_type or not image.content_type.startswith("image/")
        ):
            await self._respond(
                interaction,
                "Invalid Avatar",
                "Please upload an image file.",
            )
            return
        if image is not None and image.size > MAX_AVATAR_SIZE:
            await self._respond(
                interaction,
                "Avatar Too Large",
                "Please use an image smaller than 10 MB.",
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            avatar_data = await image.read() if image is not None else None
            if self.bot.user is None:
                raise RuntimeError("The bot user is not ready.")
            await self.bot.user.edit(avatar=avatar_data)
        except (discord.HTTPException, RuntimeError) as error:
            await self._respond(
                interaction,
                "Avatar Not Changed",
                f"Discord rejected the avatar change: `{error}`",
            )
            return

        await self._respond(
            interaction,
            "Avatar Updated" if image is not None else "Avatar Reset",
            (
                "The bot's avatar was changed successfully."
                if image is not None
                else "The bot is now using its default avatar."
            ),
        )

    @set_group.command(name="username", description="Change the bot's username")
    @app_commands.describe(name="New bot username")
    async def set_username(
        self,
        interaction: discord.Interaction,
        name: app_commands.Range[str, 2, 32],
    ) -> None:
        if not await self._owner_check(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        try:
            if self.bot.user is None:
                raise RuntimeError("The bot user is not ready.")
            await self.bot.user.edit(username=name)
        except (discord.HTTPException, RuntimeError) as error:
            await self._respond(
                interaction,
                "Username Not Changed",
                f"Discord rejected the username change: `{error}`",
            )
            return

        await self._respond(
            interaction,
            "Username Updated",
            f"The bot is now named **{name}**.",
        )

    @set_group.command(
        name="bio",
        description="Change or clear the bot's bio",
    )
    @app_commands.describe(text="New bio; leave empty to clear it")
    async def set_bio(
        self,
        interaction: discord.Interaction,
        text: app_commands.Range[str, 1, 400] | None = None,
    ) -> None:
        if not await self._owner_check(interaction):
            return

        description = text.strip() if text else ""
        await interaction.response.defer(ephemeral=True)
        try:
            application = await self.bot.application_info()
            await application.edit(description=description)
        except discord.HTTPException as error:
            await self._respond(
                interaction,
                "Bio Not Changed",
                f"Discord rejected the bio change: `{error}`",
            )
            return

        await self._respond(
            interaction,
            "Bio Updated" if description else "Bio Cleared",
            (
                "The bot's profile bio was changed successfully."
                if description
                else "The bot's profile bio was removed."
            ),
        )

    @set_group.command(name="status", description="Change the bot's online status")
    @app_commands.choices(status=STATUS_CHOICES)
    @app_commands.describe(
        status="Online, idle, DND, or invisible",
        text="Optional custom status text",
    )
    async def set_status(
        self,
        interaction: discord.Interaction,
        status: app_commands.Choice[str],
        text: app_commands.Range[str, 1, 128] | None = None,
    ) -> None:
        if not await self._owner_check(interaction):
            return

        self.presence_settings["status"] = status.value
        custom_text = text.strip() if text else ""
        custom_emoji = ""
        emoji_match = re.search(
            r"<a?:[A-Za-z0-9_]{2,32}:\d{17,20}>",
            custom_text,
        )
        if emoji_match:
            custom_emoji = emoji_match.group(0)
            custom_text = (
                custom_text[: emoji_match.start()] + custom_text[emoji_match.end() :]
            ).strip()
            custom_text = re.sub(r"\s{2,}", " ", custom_text)

        if custom_text or custom_emoji:
            self.presence_settings["activity_type"] = "custom"
            self.presence_settings["activity_name"] = custom_text
            if custom_emoji:
                self.presence_settings["activity_emoji"] = custom_emoji
            else:
                self.presence_settings.pop("activity_emoji", None)
            self.presence_settings.pop("stream_url", None)
        elif self.presence_settings.get("activity_type") == "custom":
            self.presence_settings.pop("activity_type", None)
            self.presence_settings.pop("activity_name", None)
            self.presence_settings.pop("activity_emoji", None)
            self.presence_settings.pop("stream_url", None)
        await self._save_settings()
        await self._apply_presence()
        message = f"Status changed to **{status.name}**."
        if custom_text or custom_emoji:
            rendered_status = " ".join(
                part for part in (custom_emoji, custom_text) if part
            )
            message += f"\nCustom status: **{rendered_status}**"
        await self._respond(
            interaction,
            "Status Updated",
            message,
        )

    @set_group.command(name="activity", description="Change the bot's activity")
    @app_commands.choices(kind=ACTIVITY_CHOICES)
    @app_commands.describe(
        kind="Type of activity to display",
        name="Activity text; not needed for Last.fm or clearing",
        stream_url="Twitch or YouTube URL for Streaming",
    )
    async def set_activity(
        self,
        interaction: discord.Interaction,
        kind: app_commands.Choice[str],
        name: app_commands.Range[str, 1, 128] | None = None,
        stream_url: str | None = None,
    ) -> None:
        if not await self._owner_check(interaction):
            return

        if kind.value not in {"clear", "lastfm"} and name is None:
            await self._respond(
                interaction,
                "Missing Activity Name",
                "Choose an activity name, or select **Clear Activity**.",
            )
            return
        if kind.value == "lastfm" and (not LASTFM_USERNAME or not LASTFM_API_KEY):
            await self._respond(
                interaction,
                "Last.fm Not Configured",
                "Add `LASTFM_USERNAME` and `LASTFM_API_KEY` to `.env`, then restart the bot.",
            )
            return
        if kind.value == "streaming" and not stream_url:
            await self._respond(
                interaction,
                "Missing Stream URL",
                "Streaming activities require a Twitch or YouTube URL.",
            )
            return

        if kind.value == "clear":
            self.presence_settings.pop("activity_type", None)
            self.presence_settings.pop("activity_name", None)
            self.presence_settings.pop("activity_emoji", None)
            self.presence_settings.pop("stream_url", None)
            message = "The bot's activity was cleared."
        elif kind.value == "lastfm":
            self.presence_settings["activity_type"] = "lastfm"
            self.presence_settings.pop("activity_name", None)
            self.presence_settings.pop("activity_emoji", None)
            self.presence_settings.pop("stream_url", None)
            self._lastfm_track = None
            message = (
                f"Last.fm activity enabled for **{LASTFM_USERNAME}**. "
                "The activity will be empty whenever no song is playing."
            )
        else:
            self.presence_settings["activity_type"] = kind.value
            self.presence_settings["activity_name"] = name
            self.presence_settings.pop("activity_emoji", None)
            if stream_url:
                self.presence_settings["stream_url"] = stream_url
            else:
                self.presence_settings.pop("stream_url", None)
            message = f"Activity changed to **{kind.name} {name}**."

        await self._save_settings()
        await self._apply_presence()
        self._ensure_lastfm_worker()
        if kind.value == "lastfm":
            try:
                await self._update_lastfm_presence()
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as error:
                await self._respond(
                    interaction,
                    "Last.fm Connection Failed",
                    "The setting was saved, but Last.fm could not be reached. "
                    f"Error type: `{type(error).__name__}`. It will retry automatically.",
                )
                return
        await self._respond(interaction, "Activity Updated", message)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Settings(bot))
