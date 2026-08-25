from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_FILE = PROJECT_ROOT / ".cache" / "moderation.db"


@dataclass(slots=True)
class Case:
    guild_id: int
    case_number: int
    action: str
    target_id: int | None
    moderator_id: int
    reason: str
    created_at: int
    expires_at: int | None
    active: bool
    removed: bool
    extra: dict[str, Any]


@dataclass(slots=True)
class Mute:
    guild_id: int
    user_id: int
    role_id: int
    case_number: int
    expires_at: int | None


class ModerationStore:
    """Small thread-safe SQLite store for moderation cases and active mutes."""

    def __init__(self, database: Path = DATABASE_FILE) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS moderation_cases (
                    guild_id INTEGER NOT NULL,
                    case_number INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    target_id INTEGER,
                    moderator_id INTEGER NOT NULL,
                    reason TEXT NOT NULL DEFAULT 'N/A',
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER,
                    active INTEGER NOT NULL DEFAULT 1,
                    removed INTEGER NOT NULL DEFAULT 0,
                    extra_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (guild_id, case_number)
                );
                CREATE INDEX IF NOT EXISTS moderation_cases_target
                    ON moderation_cases(guild_id, target_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS moderation_mutes (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    case_number INTEGER NOT NULL,
                    expires_at INTEGER,
                    PRIMARY KEY (guild_id, user_id)
                );
                CREATE INDEX IF NOT EXISTS moderation_mutes_expiry
                    ON moderation_mutes(expires_at);

                CREATE TABLE IF NOT EXISTS moderation_locks (
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    previous_send_messages INTEGER,
                    PRIMARY KEY (guild_id, channel_id)
                );
                """
            )

    @staticmethod
    def _case_from_row(row: sqlite3.Row) -> Case:
        try:
            extra = json.loads(row["extra_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            extra = {}
        return Case(
            guild_id=int(row["guild_id"]),
            case_number=int(row["case_number"]),
            action=str(row["action"]),
            target_id=int(row["target_id"]) if row["target_id"] is not None else None,
            moderator_id=int(row["moderator_id"]),
            reason=str(row["reason"]),
            created_at=int(row["created_at"]),
            expires_at=int(row["expires_at"]) if row["expires_at"] is not None else None,
            active=bool(row["active"]),
            removed=bool(row["removed"]),
            extra=extra if isinstance(extra, dict) else {},
        )

    def create_case(
        self,
        guild_id: int,
        action: str,
        target_id: int | None,
        moderator_id: int,
        reason: str = "N/A",
        *,
        expires_at: int | None = None,
        active: bool = True,
        extra: dict[str, Any] | None = None,
    ) -> Case:
        now = int(time.time())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            case_number = int(
                connection.execute(
                    "SELECT COALESCE(MAX(case_number), 0) + 1 FROM moderation_cases WHERE guild_id = ?",
                    (guild_id,),
                ).fetchone()[0]
            )
            connection.execute(
                """
                INSERT INTO moderation_cases (
                    guild_id, case_number, action, target_id, moderator_id,
                    reason, created_at, expires_at, active, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id, case_number, action, target_id, moderator_id,
                    reason or "N/A", now, expires_at, int(active),
                    json.dumps(extra or {}, separators=(",", ":")),
                ),
            )
            row = connection.execute(
                "SELECT * FROM moderation_cases WHERE guild_id = ? AND case_number = ?",
                (guild_id, case_number),
            ).fetchone()
        assert row is not None
        return self._case_from_row(row)

    def get_case(self, guild_id: int, case_number: int) -> Case | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM moderation_cases WHERE guild_id = ? AND case_number = ?",
                (guild_id, case_number),
            ).fetchone()
        return self._case_from_row(row) if row else None

    def list_cases(self, guild_id: int, target_id: int, limit: int = 20) -> list[Case]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM moderation_cases
                WHERE guild_id = ? AND target_id = ? AND removed = 0
                ORDER BY case_number DESC LIMIT ?
                """,
                (guild_id, target_id, limit),
            ).fetchall()
        return [self._case_from_row(row) for row in rows]

    def edit_reason(self, guild_id: int, case_number: int, reason: str) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE moderation_cases SET reason = ?
                WHERE guild_id = ? AND case_number = ? AND removed = 0
                """,
                (reason, guild_id, case_number),
            )
            return cursor.rowcount > 0

    def remove_case(self, guild_id: int, case_number: int) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE moderation_cases SET removed = 1, active = 0
                WHERE guild_id = ? AND case_number = ? AND removed = 0
                """,
                (guild_id, case_number),
            )
            return cursor.rowcount > 0

    def clear_warnings(self, guild_id: int, target_id: int) -> int:
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE moderation_cases SET active = 0
                WHERE guild_id = ? AND target_id = ? AND action = 'warn'
                    AND active = 1 AND removed = 0
                """,
                (guild_id, target_id),
            )
            return cursor.rowcount

    def moderator_stats(self, guild_id: int, moderator_id: int | None = None) -> dict[str, int]:
        """Return case counts, including removed cases, for one moderator or the guild."""
        with self._lock, self._connection() as connection:
            where = "guild_id = ?"
            params: list[int] = [guild_id]
            if moderator_id is not None:
                where += " AND moderator_id = ?"
                params.append(moderator_id)
            rows = connection.execute(
                f"""SELECT action, removed, COUNT(*) AS count
                FROM moderation_cases WHERE {where}
                GROUP BY action, removed""",
                params,
            ).fetchall()
        result = {"warn": 0, "mute": 0, "kick": 0, "ban": 0, "removed": 0}
        for row in rows:
            count = int(row["count"])
            if bool(row["removed"]):
                result["removed"] += count
            elif str(row["action"]) in result:
                result[str(row["action"])] += count
        return result

    def set_case_inactive(self, guild_id: int, case_number: int) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE moderation_cases SET active = 0 WHERE guild_id = ? AND case_number = ?",
                (guild_id, case_number),
            )

    def set_mute(
        self,
        guild_id: int,
        user_id: int,
        role_id: int,
        case_number: int,
        expires_at: int | None,
    ) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO moderation_mutes (guild_id, user_id, role_id, case_number, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    role_id = excluded.role_id,
                    case_number = excluded.case_number,
                    expires_at = excluded.expires_at
                """,
                (guild_id, user_id, role_id, case_number, expires_at),
            )

    def get_mute(self, guild_id: int, user_id: int) -> Mute | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM moderation_mutes WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
        if row is None:
            return None
        return Mute(*(int(row[key]) if row[key] is not None else None for key in row.keys()))

    def timed_mutes(self) -> list[Mute]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM moderation_mutes WHERE expires_at IS NOT NULL"
            ).fetchall()
        return [
            Mute(
                guild_id=int(row["guild_id"]), user_id=int(row["user_id"]),
                role_id=int(row["role_id"]), case_number=int(row["case_number"]),
                expires_at=int(row["expires_at"]),
            )
            for row in rows
        ]

    def remove_mute(self, guild_id: int, user_id: int) -> Mute | None:
        mute = self.get_mute(guild_id, user_id)
        if mute is None:
            return None
        with self._lock, self._connection() as connection:
            connection.execute(
                "DELETE FROM moderation_mutes WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
        self.set_case_inactive(guild_id, mute.case_number)
        return mute

    def save_lock(self, guild_id: int, channel_id: int, previous: bool | None) -> bool:
        encoded = None if previous is None else int(previous)
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO moderation_locks
                    (guild_id, channel_id, previous_send_messages)
                VALUES (?, ?, ?)
                """,
                (guild_id, channel_id, encoded),
            )
            return cursor.rowcount > 0

    def pop_lock(self, guild_id: int, channel_id: int) -> tuple[bool, bool | None]:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT previous_send_messages FROM moderation_locks WHERE guild_id = ? AND channel_id = ?",
                (guild_id, channel_id),
            ).fetchone()
            if row is None:
                return False, None
            connection.execute(
                "DELETE FROM moderation_locks WHERE guild_id = ? AND channel_id = ?",
                (guild_id, channel_id),
            )
        value = row["previous_send_messages"]
        return True, None if value is None else bool(value)


store = ModerationStore()
