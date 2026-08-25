from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class MemberCache:
    """Persistent SQLite identity and linked-server membership cache."""

    def __init__(self, database: Path) -> None:
        self.database = database
        database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL,
                    global_name TEXT,
                    last_nickname TEXT,
                    discriminator TEXT NOT NULL DEFAULT '0',
                    username_key TEXT NOT NULL,
                    global_name_key TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS users_username_key
                    ON users(username_key);
                CREATE INDEX IF NOT EXISTS users_global_name_key
                    ON users(global_name_key);
                CREATE INDEX IF NOT EXISTS users_username_length
                    ON users(LENGTH(username));

                CREATE TABLE IF NOT EXISTS guild_members (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    nickname TEXT,
                    nickname_key TEXT NOT NULL DEFAULT '',
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, user_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS guild_members_nickname_key
                    ON guild_members(nickname_key);
                CREATE INDEX IF NOT EXISTS guild_members_user_id
                    ON guild_members(user_id);

                CREATE TABLE IF NOT EXISTS cache_runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    servers_total INTEGER NOT NULL DEFAULT 0,
                    servers_processed INTEGER NOT NULL DEFAULT 0,
                    servers_failed INTEGER NOT NULL DEFAULT 0,
                    users_updated INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'running'
                );
                CREATE TABLE IF NOT EXISTS cache_failures (
                    guild_id INTEGER PRIMARY KEY,
                    guild_name TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    visible_members INTEGER NOT NULL DEFAULT 0,
                    failed_at TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS user_search USING fts5(
                    user_id UNINDEXED,
                    search_text,
                    tokenize='trigram'
                );
                """
            )
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(users)")
            }
            if "last_nickname" not in columns:
                connection.execute(
                    "ALTER TABLE users ADD COLUMN last_nickname TEXT"
                )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def load_users(self) -> dict[str, dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT u.user_id, u.username, u.global_name, u.discriminator,
                       COALESCE((SELECT gm.nickname FROM guild_members AS gm
                        WHERE gm.user_id = u.user_id AND gm.nickname IS NOT NULL
                        ORDER BY gm.last_seen_at DESC LIMIT 1), u.last_nickname) AS nickname
                FROM users AS u
                """
            ).fetchall()
        return {
            str(row["user_id"]): {
                "id": str(row["user_id"]),
                "username": row["username"],
                "global_name": row["global_name"],
                "nick": row["nickname"],
                "discriminator": row["discriminator"],
            }
            for row in rows
        }

    def upsert_users(self, records: Iterable[dict]) -> int:
        now = self._now()
        values = []
        bot_ids: list[int] = []
        for record in records:
            user_id = str(record.get("id") or "")
            username = str(record.get("username") or "").strip()
            if not user_id.isdigit() or not username:
                continue
            if bool(record.get("bot", False)):
                bot_ids.append(int(user_id))
                continue
            global_name = record.get("global_name")
            global_name = str(global_name) if global_name else None
            values.append(
                (
                    int(user_id), username, global_name, record.get("nick"),
                    str(record.get("discriminator") or "0"),
                    username.casefold(), (global_name or "").casefold(), now,
                )
            )
        if not values and not bot_ids:
            return 0
        with self._connect() as connection:
            before = connection.total_changes
            if bot_ids:
                connection.executemany(
                    "DELETE FROM users WHERE user_id = ?",
                    ((user_id,) for user_id in bot_ids),
                )
            connection.executemany(
                """
                INSERT INTO users (
                    user_id, username, global_name, last_nickname, discriminator,
                    username_key, global_name_key, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username,
                    global_name=excluded.global_name,
                    last_nickname=COALESCE(excluded.last_nickname, users.last_nickname),
                    discriminator=excluded.discriminator,
                    username_key=excluded.username_key,
                    global_name_key=excluded.global_name_key,
                    updated_at=excluded.updated_at
                WHERE username IS NOT excluded.username
                   OR global_name IS NOT excluded.global_name
                   OR (excluded.last_nickname IS NOT NULL
                       AND last_nickname IS NOT excluded.last_nickname)
                   OR discriminator IS NOT excluded.discriminator
                """,
                values,
            )
            return connection.total_changes - before

    def upsert_guild_members(self, guild_id: int, records: list[dict]) -> int:
        updated = self.upsert_users(records)
        now = self._now()
        memberships = []
        for record in records:
            user_id = str(record.get("id") or "")
            if not user_id.isdigit() or bool(record.get("bot", False)):
                continue
            nickname = record.get("nick")
            nickname = str(nickname) if nickname else None
            memberships.append(
                (guild_id, int(user_id), nickname, (nickname or "").casefold(), now)
            )
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO guild_members (
                    guild_id, user_id, nickname, nickname_key, last_seen_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    nickname=excluded.nickname,
                    nickname_key=excluded.nickname_key,
                    last_seen_at=excluded.last_seen_at
                """,
                memberships,
            )
        return updated

    def replace_failures(
        self,
        failures: Iterable[tuple[str, int, str, int]],
    ) -> None:
        """Store only the servers that failed during the latest cache attempt."""
        now = self._now()
        values = [
            (int(guild_id), str(name), str(reason), int(visible_members), now)
            for name, guild_id, reason, visible_members in failures
        ]
        with self._connect() as connection:
            connection.execute("DELETE FROM cache_failures")
            connection.executemany(
                """
                INSERT INTO cache_failures (
                    guild_id, guild_name, reason, visible_members, failed_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                values,
            )

    def load_failures(self) -> list[tuple[str, int, str, int]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT guild_name, guild_id, reason, visible_members
                FROM cache_failures
                ORDER BY guild_name COLLATE NOCASE, guild_id
                """
            ).fetchall()
        return [
            (
                str(row["guild_name"]),
                int(row["guild_id"]),
                str(row["reason"]),
                int(row["visible_members"]),
            )
            for row in rows
        ]

    def search_users(
        self,
        query: str,
        limit: int = 25,
        *,
        include_contains: bool = True,
    ) -> list[dict]:
        key = query.removeprefix("@").strip().casefold()
        upper = f"{key}\U0010ffff"
        with self._connect() as connection:
            rows = list(
                connection.execute(
                    """
                    SELECT u.user_id, u.username, u.global_name,
                           u.discriminator, u.last_nickname AS nickname
                    FROM users AS u
                    WHERE ? = ''
                       OR u.username_key = ?
                       OR (u.username_key >= ? AND u.username_key < ?)
                       OR (u.global_name_key >= ? AND u.global_name_key < ?)
                    ORDER BY
                        CASE WHEN u.username_key = ? THEN 0
                             WHEN u.username_key >= ? AND u.username_key < ? THEN 1
                             ELSE 2 END,
                        u.username_key
                    LIMIT ?
                    """,
                    (key, key, key, upper, key, upper, key, key, upper, limit),
                ).fetchall()
            )
            seen = {int(row["user_id"]) for row in rows}

            if key and len(rows) < limit:
                nickname_rows = connection.execute(
                    """
                    SELECT u.user_id, u.username, u.global_name,
                           u.discriminator, gm.nickname
                    FROM guild_members AS gm
                    JOIN users AS u ON u.user_id = gm.user_id
                    WHERE gm.nickname_key >= ? AND gm.nickname_key < ?
                    ORDER BY gm.nickname_key
                    LIMIT ?
                    """,
                    (key, upper, limit - len(rows)),
                ).fetchall()
                for row in nickname_rows:
                    if int(row["user_id"]) not in seen:
                        rows.append(row)
                        seen.add(int(row["user_id"]))

            # Substring matching is much more expensive than indexed prefix
            # matching. Only use it as a fallback when no prefix exists.
            if key and include_contains and not rows:
                contains = f"%{key}%"
                fallback_rows = connection.execute(
                """
                SELECT u.user_id, u.username, u.global_name,
                       u.discriminator, u.last_nickname AS nickname
                FROM users AS u
                WHERE u.username_key LIKE ?
                   OR u.global_name_key LIKE ?
                   OR LOWER(u.last_nickname) LIKE ?
                ORDER BY
                    CASE WHEN u.username_key = ? THEN 0
                         WHEN u.username_key >= ? AND u.username_key < ? THEN 1
                         ELSE 2 END,
                    u.username_key
                LIMIT ?
                """,
                    (contains, contains, contains, key, key, upper, limit),
                ).fetchall()
                rows.extend(fallback_rows)
        return [
            {
                "id": str(row["user_id"]),
                "username": row["username"],
                "global_name": row["global_name"],
                "nick": row["nickname"],
                "discriminator": row["discriminator"],
            }
            for row in rows
        ]

    def rebuild_search_index(self, *, force: bool = False) -> int:
        """Build the partial-name index when it is missing or out of date."""
        with self._connect() as connection:
            user_count = int(
                connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            )
            indexed_count = int(
                connection.execute("SELECT COUNT(*) FROM user_search").fetchone()[0]
            )
            if not force and indexed_count == user_count:
                return indexed_count
            connection.execute("DELETE FROM user_search")
            connection.execute(
                """
                INSERT INTO user_search (user_id, search_text)
                SELECT user_id,
                       username_key || ' ' || global_name_key || ' ' ||
                       LOWER(COALESCE(last_nickname, ''))
                FROM users
                """
            )
            return user_count

    def autocomplete_users(self, query: str, limit: int = 25) -> list[dict]:
        """Return indexed username suggestions without full-table scans."""
        key = query.removeprefix("@").strip().casefold()
        if len(key) < 2:
            return []
        upper = f"{key}\U0010ffff"
        with self._connect() as connection:
            rows = list(
                connection.execute(
                    """
                    SELECT user_id, username, global_name, discriminator,
                           last_nickname AS nickname
                    FROM users INDEXED BY users_username_key
                    WHERE username_key >= ? AND username_key < ?
                    ORDER BY username_key
                    LIMIT ?
                    """,
                    (key, upper, limit),
                ).fetchall()
            )
            seen = {int(row["user_id"]) for row in rows}

            if len(rows) < limit:
                global_rows = connection.execute(
                    """
                    SELECT user_id, username, global_name, discriminator,
                           last_nickname AS nickname
                    FROM users INDEXED BY users_global_name_key
                    WHERE global_name_key >= ? AND global_name_key < ?
                    ORDER BY global_name_key
                    LIMIT ?
                    """,
                    (key, upper, limit - len(rows)),
                ).fetchall()
                for row in global_rows:
                    if int(row["user_id"]) not in seen:
                        rows.append(row)
                        seen.add(int(row["user_id"]))

            if len(key) >= 3 and len(rows) < limit:
                phrase = f'"{key.replace(chr(34), chr(34) * 2)}"'
                try:
                    contains_rows = connection.execute(
                        """
                        SELECT u.user_id, u.username, u.global_name,
                               u.discriminator, u.last_nickname AS nickname
                        FROM user_search AS search
                        JOIN users AS u ON u.user_id = CAST(search.user_id AS INTEGER)
                        WHERE user_search MATCH ?
                        LIMIT ?
                        """,
                        (phrase, limit - len(rows)),
                    ).fetchall()
                except sqlite3.OperationalError:
                    contains_rows = []
                for row in contains_rows:
                    if int(row["user_id"]) not in seen:
                        rows.append(row)
                        seen.add(int(row["user_id"]))

        return [
            {
                "id": str(row["user_id"]),
                "username": row["username"],
                "global_name": row["global_name"],
                "nick": row["nickname"],
                "discriminator": row["discriminator"],
            }
            for row in rows[:limit]
        ]

    def count_users(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def count_usernames_by_length(self, minimum: int, maximum: int) -> int:
        """Count cached accounts whose actual username fits the length range."""
        with self._connect() as connection:
            return int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM users
                    WHERE LENGTH(username) BETWEEN ? AND ?
                    """,
                    (minimum, maximum),
                ).fetchone()[0]
            )

    def usernames_by_length(
        self,
        minimum: int,
        maximum: int,
        *,
        limit: int = 15,
        offset: int = 0,
    ) -> list[dict]:
        """Return one alphabetized page of cached usernames in a length range."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT user_id, username, global_name,
                       (SELECT COUNT(*) FROM guild_members AS gm
                        WHERE gm.user_id = users.user_id) AS shared_servers
                FROM users
                WHERE LENGTH(username) BETWEEN ? AND ?
                ORDER BY LENGTH(username), username_key, user_id
                LIMIT ? OFFSET ?
                """,
                (minimum, maximum, limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict:
        """Return cache totals and the most recent refresh run."""
        with self._connect() as connection:
            users = int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
            memberships = int(
                connection.execute("SELECT COUNT(*) FROM guild_members").fetchone()[0]
            )
            servers = int(
                connection.execute(
                    "SELECT COUNT(DISTINCT guild_id) FROM guild_members"
                ).fetchone()[0]
            )
            latest = connection.execute(
                """
                SELECT started_at, finished_at, servers_total, servers_processed,
                       servers_failed, users_updated, status
                FROM cache_runs
                ORDER BY run_id DESC
                LIMIT 1
                """
            ).fetchone()
        return {
            "users": users,
            "memberships": memberships,
            "servers": servers,
            "latest_run": dict(latest) if latest is not None else None,
        }

    def start_run(self, servers_total: int) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO cache_runs (started_at, servers_total) VALUES (?, ?)",
                (self._now(), servers_total),
            )
            return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        processed: int,
        failed: int,
        updated: int,
        status: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE cache_runs
                SET finished_at=?, servers_processed=?, servers_failed=?,
                    users_updated=?, status=?
                WHERE run_id=?
                """,
                (self._now(), processed, failed, updated, status, run_id),
            )
