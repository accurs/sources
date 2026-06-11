from __future__ import annotations

import asyncio
import hashlib
import os
from typing import TYPE_CHECKING

import aiohttp
import asyncpg
import uvicorn
from discord.ext.commands import Group
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

if TYPE_CHECKING:
    from bot.aerith import Aerith


LASTFM_CB_URL = "https://api.aerith.lol/lastfm/callback"
LASTFM_AUTH_URL = "https://www.last.fm/api/auth/"
LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"

EXCLUDED_EXTENSIONS = {"Jishaku", "Developer"}

PERMISSION_NAMES = {
    "add_reactions": "Add Reactions",
    "administrator": "Administrator",
    "attach_files": "Attach Files",
    "ban_members": "Ban Members",
    "change_nickname": "Change Nickname",
    "connect": "Connect",
    "create_instant_invite": "Create Invite",
    "deafen_members": "Deafen Members",
    "embed_links": "Embed Links",
    "kick_members": "Kick Members",
    "manage_channels": "Manage Channels",
    "manage_emojis": "Manage Emojis",
    "manage_emojis_and_stickers": "Manage Emojis & Stickers",
    "manage_events": "Manage Events",
    "manage_guild": "Manage Server",
    "manage_messages": "Manage Messages",
    "manage_nicknames": "Manage Nicknames",
    "manage_roles": "Manage Roles",
    "manage_threads": "Manage Threads",
    "manage_webhooks": "Manage Webhooks",
    "mention_everyone": "Mention Everyone",
    "moderate_members": "Timeout Members",
    "move_members": "Move Members",
    "mute_members": "Mute Members",
    "priority_speaker": "Priority Speaker",
    "read_message_history": "Read Message History",
    "read_messages": "Read Messages",
    "request_to_speak": "Request to Speak",
    "send_messages": "Send Messages",
    "send_messages_in_threads": "Send Messages in Threads",
    "send_tts_messages": "Send TTS Messages",
    "speak": "Speak",
    "stream": "Stream",
    "use_application_commands": "Use Application Commands",
    "use_embedded_activities": "Use Activities",
    "use_external_emojis": "Use External Emojis",
    "use_external_stickers": "Use External Stickers",
    "use_slash_commands": "Use Slash Commands",
    "use_voice_activation": "Use Voice Activity",
    "view_audit_log": "View Audit Log",
    "view_channel": "View Channel",
    "view_guild_insights": "View Server Insights",
}

REPORT_CHANNEL_ID = 1499824233885466624

class CommandIn(BaseModel):
    extension: dict[str, dict[str, dict[str, list[str]]]]

class StatusIn(BaseModel):
    shard_id: str
    latency: str
    guilds: str
    users: str

class API:
    """FastAPI application wrapping all Aerith HTTP endpoints, with helpers for pushing state to the database."""

    def __init__(self) -> None:
        self._api_key = os.getenv("api_key", "1")
        self._lastfm_key = os.getenv("lastfm", "dc7dc135149eb5b116ad20c7e1f1f4e8")
        self._lastfm_secret = os.getenv(
            "lastfm_secret", "ff75ba82e994c3126279cdc28dd2f7e5"
        )
        self._bot_token = os.getenv("token", "1")
        self._pool: asyncpg.Pool | None = None

        self.app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, title="aerith api", version="1.0.0")
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self._register_routes()

    async def start(self, pool: asyncpg.Pool) -> None:
        """Attach an existing connection pool and launch the uvicorn server as a background task."""
        self._pool = pool
        config = uvicorn.Config(self.app, host="0.0.0.0", port=5600, loop="none")
        server = uvicorn.Server(config)
        asyncio.create_task(server.serve())

    def _require_api_key(
        self, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())
    ) -> None:
        """Raise 401 if the bearer token does not match the configured API key."""
        if credentials.credentials != self._api_key:
            raise HTTPException(status_code=401, detail="Invalid API key.")

    def _lastfm_sign(self, params: dict) -> str:
        """Return an MD5 signature for a Last.fm API call."""
        sig_str = "".join(f"{k}{v}" for k, v in sorted(params.items()) if k != "format")
        sig_str += self._lastfm_secret
        return hashlib.md5(sig_str.encode("utf-8")).hexdigest()

    async def _discord_dm(self, discord_id: str, content: str) -> None:
        """Open a DM channel with a Discord user and send a message via the REST API."""
        headers = {"Authorization": f"Bot {self._bot_token}"}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://discord.com/api/v10/users/@me/channels",
                headers=headers,
                json={"recipient_id": discord_id},
            ) as resp:
                dm = await resp.json()
            await session.post(
                f"https://discord.com/api/v10/channels/{dm['id']}/messages",
                headers=headers,
                json={"content": content},
            )

    @staticmethod
    def _extract_permissions(checks) -> list[str]:
        """Walk a command's check closures and return human-readable permission names."""
        permissions = []
        for check in checks:
            closure = getattr(check, "__closure__", None)
            if not closure:
                continue
            for cell in closure:
                try:
                    contents = cell.cell_contents
                    if isinstance(contents, dict):
                        for perm in contents:
                            label = PERMISSION_NAMES.get(
                                perm, perm.replace("_", " ").title()
                            )
                            permissions.append(label)
                except ValueError:
                    continue
        return permissions

    @staticmethod
    def _collect_commands(commands) -> dict:
        """Recursively collect commands and subcommands into a flat qualified-name dict."""
        result = {}
        for command in commands:
            result[command.qualified_name] = {
                "aliases": list(command.aliases),
                "permissions": API._extract_permissions(command.checks),
            }
            if isinstance(command, Group):
                result.update(API._collect_commands(command.commands))
        return result

    @staticmethod
    def _format_report(payload: dict, status_data: list[dict]) -> str:
        """Format a push-all summary suitable for posting to a Discord channel."""
        lines = ["**api**", "", "**cmds**"]
        for ext_name, commands in payload.items():
            lines.append(f"  {ext_name} — {len(commands)} command(s)")
            for cmd_name, data in commands.items():
                parts = [f"`{cmd_name}`"]
                if data["aliases"]:
                    parts.append(f"aliases: {', '.join(data['aliases'])}")
                if data["permissions"]:
                    parts.append(f"perms: {', '.join(data['permissions'])}")
                lines.append(f"    {' · '.join(parts)}")
        lines += ["", "**status**"]
        for s in status_data:
            lines.append(
                f"  {s['shard_id']} — {s['latency']} · {s['guilds']} guilds · {s['users']} users"
            )
        return "\n".join(lines)

    async def push_commands(self, bot: Aerith) -> dict:
        """Collect commands from all non-excluded cogs and write them directly to the database."""
        payload: dict = {}
        for ext_name, ext in bot.cogs.items():
            if ext_name in EXCLUDED_EXTENSIONS:
                continue
            commands = self._collect_commands(ext.get_commands())
            if commands:
                payload[ext_name] = commands

        async with self._pool.acquire() as conn: #type: ignore
            await conn.execute("DELETE FROM api.commands")
            for extension, commands in payload.items():
                for command, data in commands.items():
                    await conn.execute(
                        "INSERT INTO api.commands (extension, command, aliases, permissions) VALUES ($1, $2, $3, $4)",
                        extension,
                        command,
                        data["aliases"],
                        data["permissions"],
                    )

        return payload

    async def push_status(self, bot: Aerith) -> list[dict]:
        """Upsert per-shard status rows directly in the database and return the written data."""
        shards = bot.shards.items() if bot.shards else [(0, None)]
        status_data = []

        async with self._pool.acquire() as conn: #type: ignore
            for shard_id, shard in shards:
                latency = shard.latency if shard is not None else bot.latency
                data = {
                    "shard_id": f"Shard {shard_id}",
                    "latency": f"{round(latency * 1000)}ms",
                    "guilds": str(sum(1 for g in bot.guilds if g.shard_id == shard_id)),
                    "users": str(
                        sum(
                            len(g.members) for g in bot.guilds if g.shard_id == shard_id
                        )
                    ),
                }
                await conn.execute(
                    """
                    INSERT INTO api.status (shard_id, latency, guilds, users, updated_at)
                    VALUES ($1, $2, $3, $4, NOW())
                    ON CONFLICT (shard_id) DO UPDATE
                        SET latency = $2, guilds = $3, users = $4, updated_at = NOW()
                    """,
                    data["shard_id"],
                    data["latency"],
                    data["guilds"],
                    data["users"],
                )
                status_data.append(data)

        return status_data

    async def push_all(self, bot: Aerith) -> None:
        """Push commands and status to the database, then post a summary to the report channel."""
        payload = await self.push_commands(bot)
        status_data = await self.push_status(bot)

        channel = bot.get_channel(REPORT_CHANNEL_ID)
        if channel:
            await channel.send(self._format_report(payload, status_data)) #type: ignore

    def _register_routes(self) -> None:
        """Bind all HTTP route handlers to the FastAPI application."""

        app = self.app

        @app.get("/")
        async def root():
            """Return basic API metadata."""
            return {"name": "Aerith API", "version": "1.0.0"}

        @app.get("/get/commands")
        async def get_commands():
            """Retrieve all registered bot commands grouped by extension."""
            async with self._pool.acquire() as conn: #type: ignore
                rows = await conn.fetch(
                    "SELECT * FROM api.commands ORDER BY created_at DESC"
                )
            result: dict = {}
            for row in rows:
                ext = row["extension"]
                cmd = row["command"]
                if ext not in result:
                    result[ext] = {}
                result[ext][cmd] = {
                    "aliases": row["aliases"],
                    "permissions": row["permissions"],
                }
            return result

        @app.post(
            "/post/commands",
            status_code=201,
            dependencies=[Depends(self._require_api_key)],
        )
        async def post_commands(payload: CommandIn):
            """Replace all stored commands with the provided payload."""
            async with self._pool.acquire() as conn: #type: ignore
                await conn.execute("DELETE FROM api.commands")
                for extension, commands in payload.extension.items():
                    for command, data in commands.items():
                        await conn.execute(
                            "INSERT INTO api.commands (extension, command, aliases, permissions) VALUES ($1, $2, $3, $4)",
                            extension,
                            command,
                            data.get("aliases", []),
                            data.get("permissions", []),
                        )
            return {"message": "ok"}

        @app.get("/get/status")
        async def get_status():
            """Retrieve the current status of all bot shards."""
            async with self._pool.acquire() as conn: #type: ignore
                rows = await conn.fetch("SELECT * FROM api.status")
            return {
                row["shard_id"]: {
                    "latency": row["latency"],
                    "guilds": row["guilds"],
                    "users": row["users"],
                }
                for row in rows
            }

        @app.post("/post/status", dependencies=[Depends(self._require_api_key)])
        async def post_status(payload: StatusIn):
            """Upsert the status for a given shard."""
            async with self._pool.acquire() as conn: # type: ignore
                await conn.execute(
                    """
                    INSERT INTO api.status (shard_id, latency, guilds, users, updated_at)
                    VALUES ($1, $2, $3, $4, NOW())
                    ON CONFLICT (shard_id) DO UPDATE
                        SET latency = $2, guilds = $3, users = $4, updated_at = NOW()
                    """,
                    payload.shard_id,
                    payload.latency,
                    payload.guilds,
                    payload.users,
                )
            return {"message": "ok"}

        @app.get("/lastfm/auth")
        async def lastfm_auth(
            discord_id: str = Query(..., description="The Discord user's ID"),
        ):
            """Redirect a Discord user to Last.fm to begin the OAuth flow."""
            cb = f"{LASTFM_CB_URL}?discord_id={discord_id}"
            return RedirectResponse(
                url=f"{LASTFM_AUTH_URL}?api_key={self._lastfm_key}&cb={cb}"
            )

        @app.get("/lastfm/callback")
        async def lastfm_callback(
            token: str = Query(...),
            discord_id: str = Query(...),
        ):
            """Exchange a Last.fm token for a session key, persist the link, and notify the user via DM."""
            params = {
                "method": "auth.getSession",
                "api_key": self._lastfm_key,
                "token": token,
            }
            params["api_sig"] = self._lastfm_sign(params)
            params["format"] = "json"

            async with aiohttp.ClientSession() as http:
                async with http.get(LASTFM_API_URL, params=params) as resp:
                    data = await resp.json()

            if "error" in data:
                return RedirectResponse(
                    url="https://aerith.lol/auth/lastfm/callback?success=false"
                )

            session_key = data["session"]["key"]
            lfm_username = data["session"]["name"]

            async with self._pool.acquire() as conn: # type: ignore
                await conn.execute(
                    """
                    INSERT INTO lastfm (discord_id, lastfm_username, session_key)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (discord_id) DO UPDATE
                        SET lastfm_username = $2,
                            session_key     = $3,
                            created_at      = NOW()
                    """,
                    discord_id,
                    lfm_username,
                    session_key,
                )

            await self._discord_dm(
                discord_id,
                f"successfully authenticated as **{lfm_username}** on lastfm",
            )

            return RedirectResponse(
                url=f"https://aerith.lol/auth/lastfm/callback?success=true&user={lfm_username}&a-18a0fbb9-1c83-4c8e-9baf-5c8c580d0a7e={session_key}"
            )

        @app.get("/lastfm/user/{discord_id}")
        async def lastfm_get_user(discord_id: str):
            """Retrieve the linked Last.fm account for a given Discord user."""
            print("route reached")
            async with self._pool.acquire() as conn: # type: ignore
                print("pool acquired")
                row = await conn.fetchrow(
                    "SELECT lastfm_username, session_key, created_at FROM lastfm WHERE discord_id = $1",
                    discord_id,
                )
                print("query executed")
            if not row:
                raise HTTPException(
                    status_code=404, detail="User has not linked their Last.fm account."
                )
            print("returning")
            return {
                "discord_id": discord_id,
                "lastfm_username": row["lastfm_username"],
                #"session_key": row["session_key"],
                "linked_at": row["created_at"],
            }

        @app.delete(
            "/lastfm/user/{discord_id}", dependencies=[Depends(self._require_api_key)]
        )
        async def lastfm_unlink(discord_id: str):
            """Unlink the Last.fm account associated with a Discord user."""
            async with self._pool.acquire() as conn: #type: ignore
                result = await conn.execute(
                    "DELETE FROM lastfm WHERE discord_id = $1", discord_id
                )
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="No linked account found.")
            return {"message": "Unlinked successfully."}
