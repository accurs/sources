from __future__ import annotations

import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from typing import Any

import aiohttp

TOKEN_KEY_PATTERN = re.compile(r"^USER(?:_[A-Z0-9]+)*_TOKEN$")
LINKED_REQUEST_LOCK: asyncio.Lock | None = None
LINKED_REQUEST_LOOP: asyncio.AbstractEventLoop | None = None
LINKED_REQUEST_INTERVAL = 0.4
_last_linked_request = 0.0


@asynccontextmanager
async def linked_request_slot():
    """Serialize and gently pace all linked-account HTTP requests."""
    global LINKED_REQUEST_LOCK, LINKED_REQUEST_LOOP, _last_linked_request

    loop = asyncio.get_running_loop()
    if LINKED_REQUEST_LOCK is None or LINKED_REQUEST_LOOP is not loop:
        LINKED_REQUEST_LOCK = asyncio.Lock()
        LINKED_REQUEST_LOOP = loop
        _last_linked_request = 0.0

    async with LINKED_REQUEST_LOCK:
        elapsed = loop.time() - _last_linked_request
        delay = LINKED_REQUEST_INTERVAL - elapsed
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            yield
        finally:
            _last_linked_request = loop.time()


class UserAccountClient:
    """Client that merges data from every configured linked-account token."""

    @staticmethod
    def tokens() -> list[str]:
        values: list[str] = []
        for key, value in sorted(os.environ.items()):
            if TOKEN_KEY_PATTERN.fullmatch(key):
                token = value.strip()
                if token:
                    values.append(token)

        token_list = os.getenv("USER_TOKENS", "")
        values.extend(
            token.strip() for token in re.split(r"[,;\n]", token_list) if token.strip()
        )
        return list(dict.fromkeys(values))

    @classmethod
    def token_count(cls) -> int:
        return len(cls.tokens())

    @classmethod
    def _require_tokens(cls) -> list[str]:
        tokens = cls.tokens()
        if not tokens:
            raise RuntimeError(
                "No linked-account tokens are configured. Add USER_A_TOKEN, "
                "USER_B_TOKEN, or USER_TOKENS."
            )
        return tokens

    @staticmethod
    async def _json(response: aiohttp.ClientResponse) -> Any:
        try:
            return await response.json(content_type=None)
        except (aiohttp.ContentTypeError, json.JSONDecodeError):
            return None

    async def _fetch_guilds_for_token(
        self,
        session: aiohttp.ClientSession,
        token: str,
    ) -> tuple[int, list[dict]]:
        try:
            async with (
                linked_request_slot(),
                session.get(
                    "https://discord.com/api/v9/users/@me/guilds",
                    params={"limit": "200", "with_counts": "true"},
                    headers={"Authorization": token},
                ) as response,
            ):
                data = await self._json(response)
                guilds = (
                    [item for item in data if isinstance(item, dict)]
                    if response.status == 200 and isinstance(data, list)
                    else []
                )
                return response.status, guilds
        except (aiohttp.ClientError, TimeoutError):
            return 0, []

    async def fetch_guilds(self) -> list[dict]:
        tokens = self._require_tokens()
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            results = await asyncio.gather(
                *(self._fetch_guilds_for_token(session, token) for token in tokens)
            )

        merged: dict[str, dict] = {}
        successful_tokens = 0
        for status, guilds in results:
            if status == 200:
                successful_tokens += 1
            for guild in guilds:
                guild_id = str(guild.get("id", ""))
                if guild_id:
                    merged.setdefault(guild_id, guild)

        if successful_tokens == 0:
            statuses = {status for status, _ in results}
            if statuses and statuses <= {401, 403}:
                raise RuntimeError("Every linked-account token was rejected.")
            if 429 in statuses:
                raise RuntimeError(
                    "Discord rate-limited every linked account. Try again shortly."
                )
            raise RuntimeError("Discord could not load any linked-account servers.")
        return list(merged.values())

    async def fetch_mutual_guilds(self) -> tuple[list[dict], int]:
        """Return guilds shared by every configured linked account."""
        tokens = self._require_tokens()
        if len(tokens) < 2:
            raise RuntimeError("At least two linked-account tokens are required.")

        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            results = await asyncio.gather(
                *(self._fetch_guilds_for_token(session, token) for token in tokens)
            )

        failed_statuses = [status for status, _ in results if status != 200]
        if failed_statuses:
            if all(status in {401, 403} for status in failed_statuses):
                raise RuntimeError("One or more linked-account tokens were rejected.")
            if 429 in failed_statuses:
                raise RuntimeError(
                    "Discord rate-limited a linked-account server list. "
                    "Try again shortly."
                )
            raise RuntimeError(
                "Discord could not load servers for every linked account."
            )

        guild_maps: list[dict[str, dict]] = []
        for _, guilds in results:
            guild_maps.append(
                {str(guild["id"]): guild for guild in guilds if guild.get("id")}
            )

        mutual_ids = set(guild_maps[0])
        for guild_map in guild_maps[1:]:
            mutual_ids.intersection_update(guild_map)

        mutual_guilds = [guild_maps[0][guild_id] for guild_id in mutual_ids]
        return mutual_guilds, len(tokens)

    async def _fetch_profile_for_token(
        self,
        session: aiohttp.ClientSession,
        token: str,
        user_id: int,
    ) -> tuple[int, dict | None]:
        try:
            async with (
                linked_request_slot(),
                session.get(
                    f"https://discord.com/api/v9/users/{user_id}/profile",
                    params={
                        "with_mutual_guilds": "true",
                        "with_mutual_friends": "true",
                    },
                    headers={"Authorization": token},
                ) as response,
            ):
                data = await self._json(response)
                return (
                    response.status,
                    data if isinstance(data, dict) else None,
                )
        except (aiohttp.ClientError, TimeoutError):
            return 0, None

    async def fetch_profile(self, user_id: int) -> dict:
        tokens = self._require_tokens()
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            results = await asyncio.gather(
                *(
                    self._fetch_profile_for_token(session, token, user_id)
                    for token in tokens
                )
            )

        profiles = [
            data for status, data in results if status == 200 and data is not None
        ]
        if not profiles:
            statuses = {status for status, _ in results}
            if statuses and statuses <= {401, 403}:
                raise RuntimeError("Every linked-account token was rejected.")
            if 429 in statuses:
                raise RuntimeError(
                    "Discord rate-limited every linked account. Try again shortly."
                )
            if statuses & {400, 404}:
                raise LookupError("Discord profile not accessible.")
            raise RuntimeError("Discord could not reach any linked account.")

        profile = dict(profiles[0])
        mutual_guilds: dict[str, dict] = {}
        for item in profiles:
            for guild in item.get("mutual_guilds") or []:
                if isinstance(guild, dict) and guild.get("id"):
                    mutual_guilds[str(guild["id"])] = guild
            for key in (
                "premium_since",
                "premium_type",
                "connected_accounts",
                "user_profile",
                "badges",
                "guild_badges",
                "legacy_username",
                "past_usernames",
                "previous_usernames",
                "username_history",
            ):
                if not profile.get(key) and item.get(key):
                    profile[key] = item[key]

        profile["mutual_guilds"] = list(mutual_guilds.values())
        profile["_linked_accounts_used"] = len(profiles)
        try:
            guilds = await self.fetch_guilds()
        except RuntimeError:
            guilds = []
        profile["_guild_names"] = {
            str(guild["id"]): guild["name"]
            for guild in guilds
            if guild.get("id") and guild.get("name")
        }
        return profile

    async def _fetch_relationships_for_token(
        self,
        session: aiohttp.ClientSession,
        token: str,
    ) -> tuple[int, list[dict]]:
        try:
            async with (
                linked_request_slot(),
                session.get(
                    "https://discord.com/api/v9/users/@me/relationships",
                    headers={"Authorization": token},
                ) as response,
            ):
                data = await self._json(response)
                users = []
                if response.status == 200 and isinstance(data, list):
                    for relationship in data:
                        if not isinstance(relationship, dict):
                            continue
                        user = relationship.get("user")
                        if isinstance(user, dict) and user.get("id"):
                            users.append(user)
                return response.status, users
        except (aiohttp.ClientError, TimeoutError):
            return 0, []

    async def fetch_relationship_users(self) -> list[dict]:
        tokens = self._require_tokens()
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            results = await asyncio.gather(
                *(
                    self._fetch_relationships_for_token(session, token)
                    for token in tokens
                )
            )

        users: dict[str, dict] = {}
        successful_tokens = 0
        for status, linked_users in results:
            if status == 200:
                successful_tokens += 1
            for user in linked_users:
                users[str(user["id"])] = user
        if successful_tokens == 0:
            raise RuntimeError(
                "Discord could not load relationships from any linked account."
            )
        return list(users.values())

    async def search_guild_members(self, query: str) -> list[dict]:
        """Search members in every guild visible to the linked accounts."""
        tokens = self._require_tokens()
        search_query = query.removeprefix("@").strip()
        username, separator, _ = search_query.rpartition("#")
        if separator:
            search_query = username
        if not search_query:
            return []

        requested_name = query.removeprefix("@").strip().casefold()
        timeout = aiohttp.ClientTimeout(total=30)
        successful_searches = 0
        rate_limited = False
        users: dict[str, dict] = {}

        async with aiohttp.ClientSession(timeout=timeout) as session:
            guild_results = await asyncio.gather(
                *(self._fetch_guilds_for_token(session, token) for token in tokens)
            )

            guild_tokens: dict[str, str] = {}
            for token, (status, guilds) in zip(
                tokens,
                guild_results,
                strict=True,
            ):
                if status != 200:
                    continue
                for guild in guilds:
                    guild_id = str(guild.get("id", ""))
                    if guild_id:
                        guild_tokens.setdefault(guild_id, token)

            requests = [(token, guild_id) for guild_id, token in guild_tokens.items()]

            for token, guild_id in requests:
                members: list[dict] = []
                for attempt in range(3):
                    try:
                        async with (
                            linked_request_slot(),
                            session.get(
                                f"https://discord.com/api/v9/guilds/{guild_id}/members/search",
                                params={"query": search_query, "limit": "100"},
                                headers={"Authorization": token},
                            ) as response,
                        ):
                            data = await self._json(response)
                            if response.status == 429:
                                rate_limited = True
                                retry_after = (
                                    data.get("retry_after", 1)
                                    if isinstance(data, dict)
                                    else 1
                                )
                                try:
                                    delay = min(
                                        max(float(retry_after), 0.5),
                                        30,
                                    )
                                except (TypeError, ValueError):
                                    delay = 1
                                if attempt < 2:
                                    await asyncio.sleep(delay)
                                    continue
                                break

                            if response.status != 200:
                                break

                            successful_searches += 1
                            if isinstance(data, list):
                                members = [
                                    member
                                    for member in data
                                    if isinstance(member, dict)
                                ]

                            remaining = response.headers.get("X-RateLimit-Remaining")
                            if remaining == "0":
                                try:
                                    reset_after = float(
                                        response.headers.get(
                                            "X-RateLimit-Reset-After",
                                            "0",
                                        )
                                    )
                                except ValueError:
                                    reset_after = 0
                                if reset_after > 0:
                                    await asyncio.sleep(min(reset_after, 30))
                            break
                    except (aiohttp.ClientError, TimeoutError):
                        break

                exact_users: dict[str, dict] = {}
                for member in members:
                    user = member.get("user")
                    if not isinstance(user, dict) or not user.get("id"):
                        continue
                    user_data = dict(user)
                    user_data["nick"] = member.get("nick")
                    user_id = str(user["id"])
                    users[user_id] = user_data

                    username_value = str(user.get("username") or "")
                    global_name = str(user.get("global_name") or "")
                    nickname = str(member.get("nick") or "")
                    discriminator = str(user.get("discriminator") or "0")
                    names = (
                        username_value,
                        global_name,
                        nickname,
                        f"{username_value}#{discriminator}",
                    )
                    if any(name.casefold() == requested_name for name in names if name):
                        exact_users[user_id] = user_data

                # An exact match cannot be improved by searching more guilds.
                if exact_users:
                    return list(exact_users.values())

        if requests and successful_searches == 0:
            if rate_limited:
                raise RuntimeError(
                    "Discord rate-limited linked-account member search. "
                    "Try again shortly."
                )
            raise RuntimeError(
                "Discord rejected member search for every linked-account server."
            )
        return list(users.values())
