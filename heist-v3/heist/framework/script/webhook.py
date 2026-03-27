import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp
import nacl.exceptions
import nacl.signing
from fastapi import FastAPI, HTTPException, Request, Response
from heist.framework.discord import CommandCache


logger = logging.getLogger("heist/WEBHOOK")


app = FastAPI()


DEFAULT_INVITE = "https://discord.gg/heistbot"
DEFAULT_EMBED_COLOR = 0xD3D6F1
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5065 # change to 5064 on release and itll work

_server_task: Optional[asyncio.Task] = None


def _get_embed_color() -> int:
    raw = os.getenv("WEBHOOK_COLOR")
    if not raw:
        return DEFAULT_EMBED_COLOR
    raw = raw.strip().lower()
    try:
        if raw.startswith("0x"):
            return int(raw, 16)
        return int(raw, 0)
    except ValueError:
        logger.warning(
            "Invalid WEBHOOK_COLOR value '%s'; falling back to default.",
            raw,
        )
        return DEFAULT_EMBED_COLOR


def _initialise_app_state(bot) -> bool:
    app.state.bot = bot
    if getattr(app.state, "initialised", False):
        return True

    public_key = os.getenv("DISCORD_PUBLIC_KEY")
    bot_token = os.getenv("TOKEN")
    webhook_url = os.getenv("AUTH_WEBHOOK")

    if not public_key or not bot_token or not webhook_url:
        logger.warning(
            "Missing configuration for Webhook server "
            "(DISCORD_PUBLIC_KEY, TOKEN, WEBHOOK_URL required)."
        )
        return False

    try:
        verify_key = nacl.signing.VerifyKey(bytes.fromhex(public_key))
    except Exception as exc:
        logger.error("Failed to derive verify key from DISCORD_PUBLIC_KEY: %s", exc)
        return False

    app.state.initialised = True
    app.state.verify_key = verify_key
    app.state.bot_token = bot_token
    app.state.webhook_url = webhook_url
    app.state.redis = getattr(bot, "redis", None)
    app.state.invite_url = os.getenv("SOCIALS_INVITE_URL", DEFAULT_INVITE)
    app.state.embed_color = _get_embed_color()
    app.state.session_timeout = aiohttp.ClientTimeout(total=10)

    if app.state.redis is None:
        logger.warning("Bot redis client not available; Webhook caching disabled.")

    logger.info(
        "Initialised Webhook server; forwarding events to Discord webhook."
    )
    return True


def ensure_webhook_server(bot) -> None:
    global _server_task

    if _server_task and not _server_task.done():
        return

    if not _initialise_app_state(bot):
        return

    loop = getattr(bot, "loop", None) or asyncio.get_event_loop()
    if loop.is_closed():
        logger.warning("Event loop is closed; cannot start Webhook server.")
        return

    _server_task = loop.create_task(_start_server(app))


async def _start_server(fastapi_app: FastAPI) -> None:
    host = os.getenv("WEBHOOK_HOST", DEFAULT_HOST)
    port = int(os.getenv("WEBHOOK_PORT", DEFAULT_PORT))

    logger.info("Starting Webhook server on %s:%s", host, port)

    import uvicorn

    config = uvicorn.Config(
        fastapi_app,
        host=host,
        port=port,
        log_level="info",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    try:
        await server.serve()
    except Exception:
        logger.exception("Webhook server encountered an error")
    finally:
        logger.info("Webhook server stopped.")


def _format_discord_timestamp(iso_timestamp: Optional[str]) -> str:
    if not iso_timestamp:
        return "Unknown Time"
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        return f"<t:{int(dt.timestamp())}:R>"
    except (ValueError, TypeError):
        return "Unknown Time"


async def _send_dm_to_user(user_id: str, embed: Dict[str, Any], bot_token: str) -> bool:
    headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession(timeout=app.state.session_timeout) as session:
        url = "https://discord.com/api/v10/users/@me/channels"
        payload = {"recipient_id": user_id}
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                logger.warning(
                    "Failed to create DM channel for %s (status %s)",
                    user_id,
                    response.status,
                )
                return False
            data = await response.json()
            channel_id = data.get("id")
            if not channel_id:
                logger.warning("DM channel response missing id for user %s", user_id)
                return False

        message_url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        message_payload = {"embeds": [embed]}
        async with session.post(message_url, headers=headers, json=message_payload) as response:
            if response.status != 200:
                logger.warning(
                    "Failed to send DM message to %s (status %s)",
                    user_id,
                    response.status,
                )
                return False
    return True


async def _format_event_message(event_type: str, event_data: Dict[str, Any]) -> Optional[Dict[str, Any] | str]:
    redis_client = getattr(app.state, "redis", None)
    bot_token: str = app.state.bot_token
    invite_url: str = app.state.invite_url
    color: int = app.state.embed_color

    if event_type == "APPLICATION_AUTHORIZED":
        data = event_data.get("data", {})
        user = data.get("user", {})
        username = user.get("username", "Unknown")
        user_id = user.get("id", "Unknown")
        app_id = data.get("application_id", "Unknown")
        integration_type = (
            "Server"
            if event_data.get("data", {}).get("integration_type") == 0
            else "User Account"
        )
        scopes = data.get("scopes", [])
        scopes_str = ", ".join(scopes) if scopes else "None"
        timestamp = _format_discord_timestamp(event_data.get("timestamp"))
        bot = app.state.bot
        settings = await CommandCache.get_mention(bot, "settings")

        if user_id != "Unknown" and integration_type == "User Account" and redis_client:
            redis_key_dm = f"heist:auth_dm_sent:{user_id}"
            already_sent_dm = await redis_client.get(redis_key_dm)
            if not already_sent_dm:
                embed = {
                    "description": (
                        "We aim at enhancing your Discord experience.\n\n"
                        "[Commands](https://heist.lol/commands) · "
                        "[Premium](https://heist.lol/premium) · "
                        f"[Support]({invite_url})\n"
                        f"-# You can use {settings} to manage your preferences."
                    ),
                    "author": {"name": "Thank you for choosing Heist!"},
                    "color": color,
                    "thumbnail": {"url": "https://git.cursi.ng/heist.png?v2"},
                    "image": {"url": "https://git.cursi.ng/separator.png"},
                }
                try:
                    if await _send_dm_to_user(user_id, embed, bot_token):
                        await redis_client.set(redis_key_dm, "1", ex=86400)
                        logger.info("Sent authorisation DM to %s", username)
                except Exception:
                    logger.exception("Failed to send DM to %s", user_id)

        redis_key_embed = f"heist:auth_embed_sent:{user_id}"
        already_sent_embed = await redis_client.get(redis_key_embed) if redis_client else None
        if not already_sent_embed:
            try:
                avatar = user.get("avatar")
                default_index = 0
                try:
                    default_index = int(user_id) % 5
                except (ValueError, TypeError):
                    default_index = 0
                embed = {
                    "title": f"{integration_type} Auth",
                    "description": (
                        f"User: [@{username}](discord://-/users/{user_id}) ({user_id})\n"
                        f"Authorized Scopes: **`{scopes_str}`**\n"
                        f"Application ID: `{app_id}`\n"
                        f"Time: {timestamp}"
                    ),
                    "color": color,
                    "thumbnail": {
                        "url": (
                            f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png"
                            if avatar
                            else f"https://cdn.discordapp.com/embed/avatars/{default_index}.png"
                        )
                    },
                }
            except Exception:
                logger.exception("Failed to build authorisation embed.")
                return None
            if redis_client:
                await redis_client.set(redis_key_embed, "1", ex=86400)
            return embed
        return None

    if event_type == "ENTITLEMENT_CREATE":
        data = event_data.get("data", {})
        sku_id = data.get("sku_id", "Unknown")
        user_id = data.get("user_id", "Unknown")
        return (
            "💎 **New Entitlement Created**\n"
            f"User: <@{user_id}>\n"
            f"SKU ID: `{sku_id}`\n"
            f"Time: {_format_discord_timestamp(event_data.get('timestamp'))}"
        )

    if event_type == "QUEST_USER_ENROLLMENT":
        data = event_data.get("data", {})
        user_id = data.get("user_id", "Unknown")
        quest_id = data.get("quest_id", "Unknown")
        return (
            "🎯 **New Quest Enrollment**\n"
            f"User: <@{user_id}>\n"
            f"Quest ID: `{quest_id}`\n"
            f"Time: {_format_discord_timestamp(event_data.get('timestamp'))}"
        )

    return (
        f"📨 **New Event: {event_type}**\n"
        f"Time: {_format_discord_timestamp(event_data.get('timestamp'))}\n"
        f"```json\n{json.dumps(event_data, indent=2)}\n```"
    )


def _verify_signature(signature: str, timestamp: str, body: str) -> bool:
    verify_key: nacl.signing.VerifyKey = app.state.verify_key
    try:
        verify_key.verify(
            timestamp.encode() + body.encode(),
            bytes.fromhex(signature),
        )
        return True
    except (nacl.exceptions.BadSignatureError, ValueError):
        return False


@app.post("/webhook", include_in_schema=False)
async def handle_webhook(request: Request) -> Response:
    signature = request.headers.get("X-Signature-Ed25519")
    timestamp = request.headers.get("X-Signature-Timestamp")
    if not signature or not timestamp:
        raise HTTPException(status_code=401, detail="Missing security headers")

    body_bytes = await request.body()
    body_str = body_bytes.decode()

    if not _verify_signature(signature, timestamp, body_str):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body_str)

    if payload.get("type") == 1 and "event" not in payload:
        return Response(status_code=204)

    event = payload.get("event", {})
    event_type = event.get("type")
    if not event_type:
        return Response(status_code=204)

    message = await _format_event_message(event_type, event)
    if message is None:
        return Response(status_code=204)

    outgoing = {"embeds": [message]} if isinstance(message, dict) else {"content": str(message)}

    headers = {"Content-Type": "application/json"}
    async with aiohttp.ClientSession(timeout=app.state.session_timeout) as session:
        async with session.post(app.state.webhook_url, json=outgoing, headers=headers) as response:
            if response.status not in {200, 204}:
                logger.error(
                    "Failed to forward Webhook payload (status %s)",
                    response.status,
                )
                raise HTTPException(status_code=500, detail="Failed to forward to Discord webhook")

    return Response(status_code=204)


__all__ = ("ensure_webhook_server", "app")
