from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_FILE = PROJECT_ROOT / ".cache" / "prefixes.db"
DEFAULT_PREFIX = ";"


class PrefixStore:
    """Persistent guild prefixes backed by an in-memory lookup cache."""

    def __init__(self, database: Path = DATABASE_FILE) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_prefixes (
                    guild_id INTEGER PRIMARY KEY,
                    prefix TEXT NOT NULL
                )
                """
            )
            rows = connection.execute(
                "SELECT guild_id, prefix FROM guild_prefixes"
            ).fetchall()
        self._prefixes = {int(row[0]): str(row[1]) for row in rows}

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def get(self, guild_id: int) -> str:
        return self._prefixes.get(guild_id, DEFAULT_PREFIX)

    def set(self, guild_id: int, prefix: str) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO guild_prefixes (guild_id, prefix)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET prefix = excluded.prefix
                """,
                (guild_id, prefix),
            )
            self._prefixes[guild_id] = prefix

    def reset(self, guild_id: int) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "DELETE FROM guild_prefixes WHERE guild_id = ?",
                (guild_id,),
            )
            self._prefixes.pop(guild_id, None)


store = PrefixStore()
