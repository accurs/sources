from __future__ import annotations

import asyncio
import io
import logging
import math
import os
import re
import subprocess
import tempfile
from urllib.parse import urlparse

import aiohttp
import discord
import imageio_ffmpeg
import selfcord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageSequence
from rlottie_python import LottieAnimation

TOKEN_KEY_PATTERN = re.compile(r"^USER(?:_[A-Z0-9]+)*_TOKEN$")
PREVIEWABLE_EXTENSIONS = {
    ".apng",
    ".avif",
    ".gif",
    ".jpeg",
    ".jpg",
    ".mov",
    ".mp4",
    ".png",
    ".webm",
    ".webp",
}
logger = logging.getLogger(__name__)
READY_LEVEL = 25
MAX_PREVIEW_BYTES = 9_500_000


def _render_lottie_gif(data: bytes) -> bytes:
    """Render Discord's Lottie JSON sticker into an animated GIF."""
    with LottieAnimation.from_data(data.decode("utf-8")) as animation:
        source_fps = animation.lottie_animation_get_framerate()
        duration = min(animation.lottie_animation_get_duration(), 5.0)
        fps = max(1, min(round(source_fps), 20))
        frame_count = max(1, round(duration * fps))
        frames = []
        for index in range(frame_count):
            position = index / frame_count
            frame_number = animation.lottie_animation_get_frame_at_pos(position)
            frames.append(
                animation.render_pillow_frame(
                    frame_num=frame_number,
                    width=320,
                    height=320,
                ).copy()
            )

    output = io.BytesIO()
    frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=round(1000 / fps),
        disposal=2,
        loop=0,
    )
    return output.getvalue()


async def _download_url(url: str) -> tuple[bytes, str]:
    """Download preview media and return its bytes and content type."""
    timeout = aiohttp.ClientTimeout(total=20)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; DMWatch/1.0)"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            if response.content_length and response.content_length > MAX_PREVIEW_BYTES:
                raise ValueError("preview media exceeds the upload limit")
            data = await response.read()
            if len(data) > MAX_PREVIEW_BYTES:
                raise ValueError("preview media exceeds the upload limit")
            return data, response.headers.get("Content-Type", "").split(";", 1)[0]


def _media_extension(url: str, content_type: str) -> str:
    extension = os.path.splitext(urlparse(url).path)[1].lower()
    if extension in PREVIEWABLE_EXTENSIONS:
        return extension
    return {
        "image/gif": ".gif",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
    }.get(content_type, ".bin")


async def _remote_media_file(url: str, name: str) -> discord.File:
    data, content_type = await _download_url(url)
    extension = _media_extension(url, content_type)
    return discord.File(io.BytesIO(data), filename=f"{name}{extension}")


def _is_gif_embed(embed: selfcord.Embed) -> bool:
    provider = getattr(embed, "provider", None)
    provider_name = str(getattr(provider, "name", "") or "").lower()
    urls = " ".join(
        str(url or "")
        for url in (
            getattr(embed, "url", None),
            getattr(provider, "url", None),
        )
    ).lower()
    return getattr(embed, "type", None) == "gifv" or "tenor" in provider_name or "tenor." in urls


def _animated_image_to_gif(data: bytes) -> bytes:
    source = Image.open(io.BytesIO(data))
    frames = [frame.convert("RGBA") for frame in ImageSequence.Iterator(source)]
    output = io.BytesIO()
    frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=source.info.get("duration", 80),
        disposal=2,
        loop=0,
    )
    return output.getvalue()


def _video_to_gif(data: bytes, extension: str) -> bytes:
    """Convert an embed's MP4/WebM fallback into an animated GIF."""
    with tempfile.TemporaryDirectory(prefix="dm-watch-gif-") as directory:
        source_path = os.path.join(directory, f"source{extension}")
        output_path = os.path.join(directory, "preview.gif")
        with open(source_path, "wb") as source:
            source.write(data)
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-loglevel",
                "error",
                "-i",
                source_path,
                "-vf",
                "fps=15,scale='min(480,iw)':-1:flags=lanczos",
                "-loop",
                "0",
                output_path,
            ],
            check=True,
            capture_output=True,
        )
        with open(output_path, "rb") as output:
            result = output.read()
    if len(result) > MAX_PREVIEW_BYTES:
        raise ValueError("converted GIF exceeds the upload limit")
    return result


async def _gif_embed_file(embed: selfcord.Embed, name: str) -> discord.File:
    """Resolve a GIF embed to one actual animated GIF attachment."""
    candidates = []
    for media in (embed.video, embed.image, embed.thumbnail):
        url = getattr(media, "url", None)
        if not url:
            continue
        url = str(url)
        gif_url = re.sub(r"\.(?:mp4|webm)(?=\?|$)", ".gif", url, flags=re.I)
        if gif_url != url:
            candidates.append(gif_url)
        candidates.append(url)

    seen = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        try:
            data, content_type = await _download_url(url)
        except Exception:
            continue
        extension = _media_extension(url, content_type)
        if content_type == "image/gif" or extension == ".gif":
            return discord.File(io.BytesIO(data), filename=f"{name}.gif")
        if content_type in {"image/webp", "image/png"}:
            try:
                gif_data = await asyncio.to_thread(_animated_image_to_gif, data)
            except Exception:
                continue
            return discord.File(io.BytesIO(gif_data), filename=f"{name}.gif")
        if content_type in {"video/mp4", "video/webm"}:
            try:
                gif_data = await asyncio.to_thread(
                    _video_to_gif,
                    data,
                    ".webm" if content_type == "video/webm" else ".mp4",
                )
            except Exception:
                continue
            return discord.File(io.BytesIO(gif_data), filename=f"{name}.gif")

    raise ValueError("GIF embed did not expose downloadable GIF media")


async def _sticker_file(sticker: selfcord.StickerItem) -> discord.File:
    """Download a sticker into an attachment Discord can reliably preview."""
    format_name = getattr(getattr(sticker, "format", None), "name", "")
    if format_name == "lottie":
        data = await sticker.read()
        data = await asyncio.to_thread(_render_lottie_gif, data)
        extension = "gif"
    else:
        data = await sticker.read()
        extension = "gif" if format_name == "gif" else "png"

    return discord.File(
        io.BytesIO(data),
        filename=f"sticker-{sticker.id}.{extension}",
    )


class DMWatch(commands.Cog):
    """DMs the bot's primary owner when anyone DMs the linked user accounts."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._owner: discord.User | None = None
        self._user_clients: list[selfcord.Client] = []
        self._user_client_tasks: list[asyncio.Task] = []

    @staticmethod
    def _get_user_tokens() -> list[str]:
        """Get all user tokens from environment variables."""
        values: list[str] = []
        for key, value in sorted(os.environ.items()):
            if TOKEN_KEY_PATTERN.fullmatch(key):
                token = value.strip()
                if token:
                    values.append(token)

        if values:
            logger.info("Found %d linked-account token(s) for DM watching.", len(values))
        return values

    async def _get_owner(self) -> discord.User | None:
        """Resolve and cache the bot's primary owner user object."""
        if self._owner is not None:
            return self._owner
        try:
            application = await self.bot.application_info()
        except discord.HTTPException:
            logger.warning("Could not fetch application info for DM alerts.")
            return None
        self._owner = application.owner
        if isinstance(self._owner, discord.Team):
            team_owner = getattr(self._owner, "owner", None)
            if isinstance(team_owner, discord.User):
                logger.info(
                    "Application owned by team %s; forwarding alerts to team owner %s.",
                    self._owner.name,
                    team_owner,
                )
                self._owner = team_owner
        return self._owner

    def _create_user_client(self, token: str) -> selfcord.Client:
        """Create a separate Discord client for a linked user token."""
        # DM watching does not need a full member scrape at login. Lookup
        # requests matching members on demand, avoiding startup chunk timeouts.
        client = selfcord.Client(chunk_guilds_at_startup=False)

        @client.event
        async def on_ready() -> None:
            logger.log(READY_LEVEL, "Linked account connected: %s", client.user)

        @client.event
        async def on_message(message: selfcord.Message) -> None:
            logger.debug(
                "User client %s received message from %s in %s",
                client.user,
                message.author,
                message.channel,
            )
            await self._handle_user_dm(message, client)

        return client

    async def _start_user_clients(self) -> None:
        """Start separate Discord clients for each user token."""
        tokens = self._get_user_tokens()
        if not tokens:
            logger.warning("No user tokens found for DM watching.")
            return

        logger.info(
            "Starting DM watch for %d linked user client(s)",
            len(tokens),
        )

        for token in tokens:
            client = self._create_user_client(token)
            self._user_clients.append(client)
            task = asyncio.create_task(self._run_user_client(client, token))
            self._user_client_tasks.append(task)

    async def _run_user_client(
        self,
        client: selfcord.Client,
        token: str,
    ) -> None:
        try:
            await client.start(token)
        except asyncio.CancelledError:
            raise
        except selfcord.errors.LoginFailure:
            logger.warning(
                "Linked user token ending %s failed to login.",
                token[-8:],
            )
        except Exception:
            logger.exception(
                "Linked user client failed for token ending %s",
                token[-8:],
            )

    async def _handle_user_dm(
        self,
        message: selfcord.Message,
        client: selfcord.Client,
    ) -> None:
        """Handle DM messages received by a user client."""
        # Only direct messages, from a human.
        if not isinstance(message.channel, selfcord.DMChannel):
            return
        if message.author.bot or message.author == client.user:
            return

        owner = await self._get_owner()
        if owner is None:
            bot_owner_id = getattr(self.bot, "owner_id", None)
            if bot_owner_id is not None:
                owner = self.bot.get_user(bot_owner_id)
                if owner is None:
                    try:
                        owner = await self.bot.fetch_user(bot_owner_id)
                    except discord.HTTPException:
                        owner = None
            if owner is None:
                logger.warning("Owner not resolved; skipping watched DM from %s", message.author)
                return
        if message.author.id == owner.id:
            return

        author = message.author
        content = (message.content or "").strip()[:3000]
        gif_embeds = [embed for embed in message.embeds if _is_gif_embed(embed)]
        if gif_embeds and re.fullmatch(r"https?://\S+", content):
            # Discord includes the pasted Tenor URL as ordinary message text.
            # The uploaded GIF below is the useful representation of it.
            content = ""
        user_account = client.user
        stickers = list(getattr(message, "stickers", ()))
        snapshots = list(getattr(message, "message_snapshots", ()))
        sticker_sources = [("Sticker", sticker) for sticker in stickers]
        for snapshot in snapshots:
            sticker_sources.extend(
                ("Forwarded sticker", sticker) for sticker in snapshot.stickers
            )
        sticker_previews: list[tuple[str, selfcord.StickerItem, discord.File]] = []
        for label, sticker in sticker_sources[:3]:
            try:
                sticker_previews.append(
                    (label, sticker, await _sticker_file(sticker))
                )
            except Exception:
                logger.warning(
                    "Could not download sticker %s (%s) for DM preview.",
                    sticker.name,
                    sticker.id,
                    exc_info=True,
                )
        previewable_attachments = []
        file_links = []
        for attachment in message.attachments:
            filename = attachment.filename
            content_type = getattr(attachment, "content_type", None) or ""
            extension = os.path.splitext(filename)[1].lower()
            if (
                content_type.startswith(("image/", "video/"))
                or extension in PREVIEWABLE_EXTENSIONS
            ):
                previewable_attachments.append(attachment)
            else:
                safe_filename = filename.replace("[", "\\[").replace("]", "\\]")
                file_links.append(f"[{safe_filename}]({attachment.url})")

        uploaded_files = [sticker_file for _, _, sticker_file in sticker_previews]
        attachment_previews: list[tuple[selfcord.Attachment, discord.File]] = []
        for index, attachment in enumerate(previewable_attachments):
            if len(uploaded_files) >= 10:
                break
            try:
                preview = await _remote_media_file(
                    str(attachment.url),
                    f"attachment-{message.id}-{index}",
                )
                attachment_previews.append((attachment, preview))
                uploaded_files.append(preview)
            except Exception:
                logger.warning(
                    "Could not download DM attachment %s for preview.",
                    attachment.filename,
                    exc_info=True,
                )

        view = discord.ui.LayoutView()
        container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(
                    "## New DM Received\n"
                    f"**{author.display_name}**"
                ),
                accessory=discord.ui.Thumbnail(
                    author.display_avatar.url,
                    description=f"{author.display_name}'s avatar",
                ),
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "### Identity\n"
                f"**Username:** {author.name}\n"
                f"**Display name:** {author.display_name}\n"
                f"**User ID:** `{author.id}`"
            ),
        )

        text_remaining = 3500

        def add_text_section(title: str, body: str) -> None:
            nonlocal text_remaining
            body = body.strip()
            if not body or text_remaining <= len(title) + 6:
                return
            body = body[: max(0, text_remaining - len(title) - 6)]
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(f"### {title}\n{body}"))
            text_remaining -= len(title) + len(body) + 6

        if content:
            add_text_section("Message", content)

        reference = getattr(message, "reference", None)
        reference_type = getattr(getattr(reference, "type", None), "name", "")
        resolved = getattr(reference, "resolved", None)
        if reference_type in {"reply", "default"} and isinstance(
            resolved, selfcord.Message
        ):
            reply_content = (resolved.content or "").strip()
            reply_body = f"**{resolved.author}:**"
            if reply_content:
                reply_body += f"\n{reply_content[:1200]}"
            add_text_section("Replying to", reply_body)

        for snapshot in snapshots[:1]:
            forwarded_parts = [f"**Sent:** <t:{int(snapshot.created_at.timestamp())}:f>"]
            if snapshot.content.strip():
                forwarded_parts.append(snapshot.content.strip()[:2200])
            for embed in snapshot.embeds[:3]:
                embed_text = "\n".join(
                    part for part in (embed.title, embed.description) if part
                )
                if embed_text:
                    forwarded_parts.append(f"**Embed:**\n{embed_text[:1200]}")
            add_text_section("Forwarded message", "\n\n".join(forwarded_parts))

            forwarded_media = [
                attachment
                for attachment in snapshot.attachments
                if (
                    (getattr(attachment, "content_type", None) or "").startswith(
                        ("image/", "video/")
                    )
                    or os.path.splitext(attachment.filename)[1].lower()
                    in PREVIEWABLE_EXTENSIONS
                )
            ]
            forwarded_media.extend(
                media
                for embed in snapshot.embeds
                for media in (embed.video, embed.image, embed.thumbnail)
                if getattr(media, "url", None)
            )
            if forwarded_media:
                gallery = discord.ui.MediaGallery()
                for index, media in enumerate(forwarded_media):
                    if len(uploaded_files) >= 10:
                        break
                    url = getattr(media, "proxy_url", None) or media.url
                    try:
                        preview = await _remote_media_file(
                            str(url), f"forwarded-{message.id}-{index}"
                        )
                    except Exception:
                        logger.warning(
                            "Could not download forwarded media preview %s.",
                            url,
                            exc_info=True,
                        )
                        continue
                    uploaded_files.append(preview)
                    gallery.add_item(
                        media=preview,
                        description=(
                            getattr(media, "filename", None)
                            or "Forwarded media"
                        )[:256],
                    )
                if gallery.items:
                    container.add_item(gallery)

            forwarded_files = [
                attachment
                for attachment in snapshot.attachments
                if attachment not in forwarded_media
            ]
            if forwarded_files:
                links = [
                    f"[{attachment.filename}]({attachment.url})"
                    for attachment in forwarded_files
                ]
                add_text_section("Forwarded files", "\n".join(links))

        if message.embeds:
            embed_parts = []
            embed_media = []
            for embed in message.embeds[:5]:
                if _is_gif_embed(embed):
                    continue
                text = "\n".join(
                    part for part in (embed.title, embed.description) if part
                )
                if text:
                    embed_parts.append(text[:1200])
                embed_media.extend(
                    media
                    for media in (embed.video, embed.image, embed.thumbnail)
                    if getattr(media, "url", None)
                )
            if embed_parts:
                add_text_section("Embedded content", "\n\n".join(embed_parts))
            if gif_embeds and len(uploaded_files) < 10:
                gallery = discord.ui.MediaGallery()
                for index, embed in enumerate(gif_embeds):
                    if len(uploaded_files) >= 10:
                        break
                    try:
                        preview = await _gif_embed_file(
                            embed, f"gif-{message.id}-{index}"
                        )
                    except Exception:
                        logger.warning(
                            "Could not resolve GIF embed %s to an animated GIF.",
                            getattr(embed, "url", None),
                            exc_info=True,
                        )
                        continue
                    uploaded_files.append(preview)
                    gallery.add_item(media=preview, description="GIF")
                if gallery.items:
                    container.add_item(gallery)
            if embed_media:
                gallery = discord.ui.MediaGallery()
                seen_urls = set()
                for index, media in enumerate(embed_media):
                    if len(uploaded_files) >= 10:
                        break
                    url = str(getattr(media, "proxy_url", None) or media.url)
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    try:
                        preview = await _remote_media_file(
                            url, f"embed-{message.id}-{index}"
                        )
                    except Exception:
                        logger.warning(
                            "Could not download embedded media preview %s.",
                            url,
                            exc_info=True,
                        )
                        continue
                    uploaded_files.append(preview)
                    gallery.add_item(media=preview, description="Embedded media")
                if gallery.items:
                    container.add_item(gallery)

        poll = getattr(message, "poll", None)
        if poll is not None:
            answers = "\n".join(
                f"• {answer.text} — {answer.vote_count} vote(s)"
                for answer in poll.answers
            )
            add_text_section("Poll", f"**{poll.question}**\n{answers}")

        if stickers or any(snapshot.stickers for snapshot in snapshots):
            sticker_gallery = discord.ui.MediaGallery()
            for label, sticker, sticker_file in sticker_previews:
                sticker_gallery.add_item(
                    media=sticker_file,
                    description=f"{label}: {sticker.name}"[:256],
                )
            add_text_section(
                "Stickers",
                ", ".join(sticker.name for _, sticker in sticker_sources[:10]),
            )
            if sticker_previews:
                container.add_item(sticker_gallery)
        if previewable_attachments:
            gallery = discord.ui.MediaGallery()
            for attachment, preview in attachment_previews:
                gallery.add_item(
                    media=preview,
                    description=attachment.filename[:256],
                    spoiler=attachment.filename.startswith("SPOILER_"),
                )
            add_text_section(
                "Attachments",
                ", ".join(attachment.filename for attachment in previewable_attachments),
            )
            if gallery.items:
                container.add_item(gallery)
        if file_links:
            add_text_section("Attached files", "\n".join(file_links))
        container.add_item(discord.ui.Separator())
        container.add_item(
            discord.ui.TextDisplay(
                f"**Sent to:** "
                f"{user_account.display_name if user_account else 'Unknown'}"
            )
        )
        view.add_item(container)

        try:
            # LayoutView uses Discord Components V2, which cannot be combined
            # with ordinary message content.
            await owner.send(
                view=view,
                files=uploaded_files,
            )
            logger.info(
                "Forwarded DM from %s to bot owner via %s",
                author,
                user_account,
            )
        except discord.HTTPException:
            logger.warning(
                "Could not deliver a watched-DM alert to the bot owner.",
                exc_info=True,
            )

    @app_commands.command(
        name="linked-status",
        description="Show linked-account and DM Watch connection health",
    )
    @app_commands.describe(
        ephemeral="Only show the status panel to you",
        show_identity="Show linked usernames and profile pictures",
    )
    async def linked_status(
        self,
        interaction: discord.Interaction,
        ephemeral: bool = False,
        show_identity: bool = False,
    ) -> None:
        if not await self.bot.can_use_owner_commands(interaction.user):
            await interaction.response.send_message(
                "Only the bot owner can view linked-account status.",
                ephemeral=True,
            )
            return

        clients = list(self._user_clients)
        active_tasks = sum(not task.done() for task in self._user_client_tasks)
        ready_count = sum(client.is_ready() for client in clients)
        items: list[discord.ui.Item] = [
            discord.ui.TextDisplay(
                "## Linked Account Status\n"
                f"**DM Watch:** {'Running' if active_tasks else 'Stopped'}\n"
                f"**Connections:** {ready_count}/{len(clients)} ready\n"
                f"**Client tasks:** {active_tasks}/{len(self._user_client_tasks)} active"
            )
        ]

        for index, client in enumerate(clients, start=1):
            items.append(discord.ui.Separator())
            user = client.user
            if client.is_ready():
                state = "Ready"
            elif client.is_closed():
                state = "Closed"
            else:
                state = "Connecting"

            latency = client.latency
            latency_text = (
                f"{round(latency * 1000)} ms"
                if math.isfinite(latency)
                else "Unavailable"
            )
            rate_limit = "Waiting" if client.is_ws_ratelimited() else "Clear"
            if user is None:
                account_item: discord.ui.Item = discord.ui.TextDisplay(
                    f"### Linked Account {index}\n"
                    f"**State:** {state}\n"
                    f"**Gateway latency:** {latency_text}\n"
                    f"**Gateway rate limit:** {rate_limit}"
                )
            elif show_identity:
                display_name = getattr(user, "global_name", None) or user.name
                account_item = discord.ui.Section(
                    discord.ui.TextDisplay(
                        f"### {discord.utils.escape_markdown(display_name)}\n"
                        f"**Username:** {discord.utils.escape_markdown(user.name)}\n"
                        f"**User ID:** `{user.id}`\n"
                        f"**State:** {state}\n"
                        f"**Servers:** {len(client.guilds):,}\n"
                        f"**Gateway latency:** {latency_text}\n"
                        f"**Gateway rate limit:** {rate_limit}"
                    ),
                    accessory=discord.ui.Thumbnail(
                        user.display_avatar.url,
                        description=f"{user.name}'s profile picture",
                    ),
                )
            else:
                account_item = discord.ui.TextDisplay(
                    f"### Linked Account {index}\n"
                    f"**Identity:** Redacted\n"
                    f"**User ID:** `{user.id}`\n"
                    f"**State:** {state}\n"
                    f"**Servers:** {len(client.guilds):,}\n"
                    f"**Gateway latency:** {latency_text}\n"
                    f"**Gateway rate limit:** {rate_limit}"
                )
            items.append(account_item)

        if not clients:
            items.extend(
                (
                    discord.ui.Separator(),
                    discord.ui.TextDisplay(
                        "No linked-account clients are configured or running."
                    ),
                )
            )

        view = discord.ui.LayoutView()
        view.add_item(discord.ui.Container(*items))
        await interaction.response.send_message(view=view, ephemeral=ephemeral)

    async def cog_unload(self) -> None:
        """Clean up user clients when cog is unloaded."""
        for client in self._user_clients:
            await client.close()
        for task in self._user_client_tasks:
            task.cancel()
        self._user_clients.clear()
        self._user_client_tasks.clear()


async def setup(bot: commands.Bot) -> None:
    cog = DMWatch(bot)
    await bot.add_cog(cog)
    await cog._start_user_clients()
