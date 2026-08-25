from __future__ import annotations

import sqlite3
import threading
import time
import random
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_FILE = PROJECT_ROOT / ".cache" / "economy.db"
BASE_BANK_CAPACITY = 100_000
TRANSACTION_RETENTION_SECONDS = 7 * 24 * 60 * 60
DEPOSIT_FEE_RATE = 0.05
LOTTERY_TICKET_PRICE = 2_500


def deposit_fee(amount: int) -> int:
    return max(1, round(amount * DEPOSIT_FEE_RATE))


@dataclass(slots=True)
class Account:
    user_id: int
    wallet: int
    bank: int
    bank_level: int
    bank_capacity: int
    daily_streak: int
    work_streak: int
    work_count: int
    daily_last: int | None
    work_last: int | None
    created_at: int

    @property
    def net(self) -> int:
        return self.wallet + self.bank


class EconomyError(Exception):
    pass


class InsufficientFunds(EconomyError):
    pass


class BankCapacityError(EconomyError):
    pass


class EconomyStore:
    """Thread-safe SQLite storage shared by Economy, Gambling, and Fun."""

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
                CREATE TABLE IF NOT EXISTS economy_accounts (
                    user_id INTEGER PRIMARY KEY,
                    wallet INTEGER NOT NULL DEFAULT 0 CHECK(wallet >= 0),
                    bank INTEGER NOT NULL DEFAULT 0 CHECK(bank >= 0),
                    bank_level INTEGER NOT NULL DEFAULT 0 CHECK(bank_level >= 0),
                    daily_streak INTEGER NOT NULL DEFAULT 0 CHECK(daily_streak >= 0),
                    work_streak INTEGER NOT NULL DEFAULT 0 CHECK(work_streak >= 0),
                    work_count INTEGER NOT NULL DEFAULT 0 CHECK(work_count >= 0),
                    daily_last INTEGER,
                    work_last INTEGER,
                    robbed_protected_until INTEGER NOT NULL DEFAULT 0,
                    robber_cooldown_until INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS economy_admins (
                    user_id INTEGER PRIMARY KEY,
                    added_by INTEGER NOT NULL,
                    added_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS economy_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    balance_type TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor_id INTEGER,
                    other_user_id INTEGER,
                    reason TEXT,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS economy_transactions_time
                    ON economy_transactions(created_at DESC);
                CREATE INDEX IF NOT EXISTS economy_transactions_user
                    ON economy_transactions(user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS gambling_stats (
                    user_id INTEGER NOT NULL,
                    game TEXT NOT NULL,
                    games INTEGER NOT NULL DEFAULT 0,
                    wagered INTEGER NOT NULL DEFAULT 0,
                    returned INTEGER NOT NULL DEFAULT 0,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    pushes INTEGER NOT NULL DEFAULT 0,
                    current_streak INTEGER NOT NULL DEFAULT 0,
                    best_streak INTEGER NOT NULL DEFAULT 0,
                    biggest_win INTEGER NOT NULL DEFAULT 0,
                    biggest_loss INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, game)
                );
                CREATE TABLE IF NOT EXISTS game_reward_cooldowns (
                    user_id INTEGER NOT NULL,
                    game TEXT NOT NULL,
                    available_at INTEGER NOT NULL,
                    PRIMARY KEY (user_id, game)
                );

                CREATE TABLE IF NOT EXISTS economy_giveaways (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER,
                    host_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL CHECK(amount > 0),
                    winner_count INTEGER NOT NULL CHECK(winner_count > 0),
                    ends_at INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS economy_giveaways_active
                    ON economy_giveaways(status, ends_at);
                CREATE TABLE IF NOT EXISTS economy_giveaway_entries (
                    giveaway_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    entered_at INTEGER NOT NULL,
                    PRIMARY KEY (giveaway_id, user_id),
                    FOREIGN KEY (giveaway_id) REFERENCES economy_giveaways(id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS economy_balance_cards (
                    user_id INTEGER PRIMARY KEY,
                    background_color TEXT NOT NULL DEFAULT '#111827',
                    gradient_color TEXT,
                    gradient_direction TEXT NOT NULL DEFAULT 'top',
                    text_color TEXT NOT NULL DEFAULT '#F8FAFC',
                    avatar_shape TEXT NOT NULL DEFAULT 'circle',
                    wallet_hidden INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    fade INTEGER NOT NULL DEFAULT 45,
                    background_path TEXT
                );

                CREATE TABLE IF NOT EXISTS economy_lottery (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    pool INTEGER NOT NULL DEFAULT 0 CHECK(pool >= 0),
                    round INTEGER NOT NULL DEFAULT 1,
                    channel_id INTEGER,
                    ends_at INTEGER NOT NULL DEFAULT 0
                );
                INSERT OR IGNORE INTO economy_lottery(id) VALUES (1);
                CREATE TABLE IF NOT EXISTS economy_lottery_entries (
                    round INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    tickets INTEGER NOT NULL DEFAULT 0 CHECK(tickets > 0),
                    PRIMARY KEY (round, user_id)
                );
                """
            )
            balance_columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(economy_balance_cards)"
                ).fetchall()
            }
            if "gradient_direction" not in balance_columns:
                connection.execute(
                    "ALTER TABLE economy_balance_cards ADD COLUMN "
                    "gradient_direction TEXT NOT NULL DEFAULT 'top'"
                )
            lottery_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(economy_lottery)").fetchall()
            }
            if "channel_id" not in lottery_columns:
                connection.execute("ALTER TABLE economy_lottery ADD COLUMN channel_id INTEGER")
            if "ends_at" not in lottery_columns:
                connection.execute(
                    "ALTER TABLE economy_lottery ADD COLUMN ends_at INTEGER NOT NULL DEFAULT 0"
                )

    @staticmethod
    def bank_capacity(level: int) -> int:
        return BASE_BANK_CAPACITY * (2 ** max(0, level))

    @staticmethod
    def bank_upgrade_cost(level: int) -> int:
        return 50_000 * (2 ** max(0, level))

    def _ensure_account(self, connection: sqlite3.Connection, user_id: int) -> None:
        now = int(time.time())
        connection.execute(
            """
            INSERT OR IGNORE INTO economy_accounts (user_id, created_at, updated_at)
            VALUES (?, ?, ?)
            """,
            (user_id, now, now),
        )

    def _account_from_row(self, row: sqlite3.Row) -> Account:
        level = int(row["bank_level"])
        return Account(
            user_id=int(row["user_id"]), wallet=int(row["wallet"]),
            bank=int(row["bank"]), bank_level=level,
            bank_capacity=self.bank_capacity(level),
            daily_streak=int(row["daily_streak"]),
            work_streak=int(row["work_streak"]), work_count=int(row["work_count"]),
            daily_last=row["daily_last"], work_last=row["work_last"],
            created_at=int(row["created_at"]),
        )

    def get_account(self, user_id: int) -> Account:
        with self._lock, self._connection() as connection:
            self._ensure_account(connection, user_id)
            row = connection.execute(
                "SELECT * FROM economy_accounts WHERE user_id = ?", (user_id,)
            ).fetchone()
            assert row is not None
            return self._account_from_row(row)

    def balance_card_settings(self, user_id: int) -> dict[str, Any]:
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO economy_balance_cards(user_id) VALUES (?)",
                (user_id,),
            )
            row = connection.execute(
                "SELECT * FROM economy_balance_cards WHERE user_id=?", (user_id,)
            ).fetchone()
        assert row is not None
        return dict(row)

    def update_balance_card(self, user_id: int, **values: Any) -> dict[str, Any]:
        allowed = {
            "background_color", "gradient_color", "gradient_direction",
            "text_color", "avatar_shape",
            "wallet_hidden", "message", "fade", "background_path",
        }
        values = {key: value for key, value in values.items() if key in allowed}
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO economy_balance_cards(user_id) VALUES (?)",
                (user_id,),
            )
            if values:
                assignments = ", ".join(f"{key}=?" for key in values)
                connection.execute(
                    f"UPDATE economy_balance_cards SET {assignments} WHERE user_id=?",
                    (*values.values(), user_id),
                )
            row = connection.execute(
                "SELECT * FROM economy_balance_cards WHERE user_id=?", (user_id,)
            ).fetchone()
        assert row is not None
        return dict(row)

    def reset_balance_card(self, user_id: int) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "DELETE FROM economy_balance_cards WHERE user_id=?", (user_id,)
            )

    def _transaction(
        self, connection: sqlite3.Connection, user_id: int, amount: int,
        balance_type: str, action: str, *, actor_id: int | None = None,
        other_user_id: int | None = None, reason: str | None = None,
    ) -> None:
        connection.execute(
            """INSERT INTO economy_transactions
            (user_id, amount, balance_type, action, actor_id, other_user_id, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, amount, balance_type, action, actor_id, other_user_id, reason, int(time.time())),
        )

    def claim_daily(self, user_id: int) -> tuple[Account, int, int]:
        now = int(time.time())
        cooldown = 24 * 60 * 60
        grace = 48 * 60 * 60
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_account(connection, user_id)
            row = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (user_id,)).fetchone()
            assert row is not None
            last = row["daily_last"]
            if last is not None and now - int(last) < cooldown:
                raise EconomyError(str(cooldown - (now - int(last))))
            streak = int(row["daily_streak"]) + 1 if last and now - int(last) < grace else 1
            capped_streak = min(streak, 30)
            # Constant compound growth from 2,500 on day 1 to 25,000 on day 30.
            raw_reward = 2_500 * (10 ** ((capped_streak - 1) / 29))
            reward = round(raw_reward / 50) * 50
            connection.execute(
                "UPDATE economy_accounts SET wallet=wallet+?, daily_streak=?, daily_last=?, updated_at=? WHERE user_id=?",
                (reward, streak, now, now, user_id),
            )
            self._transaction(connection, user_id, reward, "wallet", "daily")
            row = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (user_id,)).fetchone()
            return self._account_from_row(row), reward, streak

    def complete_work(self, user_id: int, *, success: bool, base_pay: int, job: str) -> tuple[Account, int]:
        now = int(time.time())
        cooldown = 12 * 60 * 60
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_account(connection, user_id)
            row = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (user_id,)).fetchone()
            assert row is not None
            last = row["work_last"]
            if last is not None and now - int(last) < cooldown:
                raise EconomyError(str(cooldown - (now - int(last))))
            old_streak = int(row["work_streak"])
            streak = old_streak + 1 if success else max(0, old_streak - 2)
            reward = round(base_pay * (1 + min(streak, 30) * 0.025)) if success else 0
            connection.execute(
                """UPDATE economy_accounts SET wallet=wallet+?, work_streak=?, work_count=work_count+1,
                work_last=?, updated_at=? WHERE user_id=?""",
                (reward, streak, now, now, user_id),
            )
            if reward:
                self._transaction(connection, user_id, reward, "wallet", "work", reason=job)
            row = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (user_id,)).fetchone()
            return self._account_from_row(row), reward

    def transfer(self, sender_id: int, recipient_id: int, amount: int) -> tuple[Account, Account]:
        if amount <= 0:
            raise ValueError("Amount must be positive")
        now = int(time.time())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_account(connection, sender_id); self._ensure_account(connection, recipient_id)
            sender = connection.execute("SELECT wallet FROM economy_accounts WHERE user_id=?", (sender_id,)).fetchone()
            if int(sender["wallet"]) < amount:
                raise InsufficientFunds
            connection.execute("UPDATE economy_accounts SET wallet=wallet-?, updated_at=? WHERE user_id=?", (amount, now, sender_id))
            connection.execute("UPDATE economy_accounts SET wallet=wallet+?, updated_at=? WHERE user_id=?", (amount, now, recipient_id))
            self._transaction(connection, sender_id, -amount, "wallet", "transfer", other_user_id=recipient_id)
            self._transaction(connection, recipient_id, amount, "wallet", "transfer", other_user_id=sender_id)
            rows = [connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (uid,)).fetchone() for uid in (sender_id, recipient_id)]
            return self._account_from_row(rows[0]), self._account_from_row(rows[1])

    def deposit(self, user_id: int, amount: int) -> tuple[Account, int]:
        if amount <= 0: raise ValueError
        fee = deposit_fee(amount); deposited = amount - fee
        if deposited <= 0: raise ValueError
        now = int(time.time())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE"); self._ensure_account(connection, user_id)
            row = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (user_id,)).fetchone()
            if int(row["wallet"]) < amount: raise InsufficientFunds
            if int(row["bank"]) + deposited > self.bank_capacity(int(row["bank_level"])): raise BankCapacityError
            connection.execute("UPDATE economy_accounts SET wallet=wallet-?, bank=bank+?, updated_at=? WHERE user_id=?", (amount, deposited, now, user_id))
            connection.execute("UPDATE economy_lottery SET pool=pool+? WHERE id=1", (fee,))
            self._transaction(connection, user_id, -amount, "wallet", "deposit")
            self._transaction(connection, user_id, deposited, "bank", "deposit")
            self._transaction(connection, user_id, -fee, "fee", "deposit_fee")
            row = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (user_id,)).fetchone()
            return self._account_from_row(row), fee

    def lottery_status(self, user_id: int | None = None) -> dict[str, int]:
        with self._lock, self._connection() as connection:
            lottery = connection.execute(
                "SELECT pool,round,channel_id,ends_at FROM economy_lottery WHERE id=1"
            ).fetchone()
            total = connection.execute(
                "SELECT COALESCE(SUM(tickets),0) AS tickets FROM economy_lottery_entries WHERE round=?",
                (lottery["round"],),
            ).fetchone()
            mine = 0
            if user_id is not None:
                row = connection.execute(
                    "SELECT tickets FROM economy_lottery_entries WHERE round=? AND user_id=?",
                    (lottery["round"], user_id),
                ).fetchone()
                mine = int(row["tickets"]) if row else 0
            return {"pool": int(lottery["pool"]), "round": int(lottery["round"]),
                    "tickets": int(total["tickets"]), "user_tickets": mine,
                    "channel_id": int(lottery["channel_id"] or 0),
                    "ends_at": int(lottery["ends_at"] or 0)}

    def set_lottery_channel(self, channel_id: int) -> dict[str, int]:
        ends_at = int(time.time()) + 36 * 60 * 60
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE economy_lottery SET channel_id=?,ends_at=? WHERE id=1",
                (channel_id, ends_at),
            )
        return self.lottery_status()

    def extend_lottery_round(self) -> dict[str, int]:
        ends_at = int(time.time()) + 36 * 60 * 60
        with self._lock, self._connection() as connection:
            connection.execute("UPDATE economy_lottery SET ends_at=? WHERE id=1", (ends_at,))
        return self.lottery_status()

    def buy_lottery_tickets(self, user_id: int, tickets: int) -> tuple[Account, dict[str, int]]:
        if tickets < 1 or tickets > 100:
            raise ValueError("Tickets must be between 1 and 100")
        cost = tickets * LOTTERY_TICKET_PRICE
        now = int(time.time())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_account(connection, user_id)
            account = connection.execute(
                "SELECT wallet FROM economy_accounts WHERE user_id=?", (user_id,)
            ).fetchone()
            if int(account["wallet"]) < cost:
                raise InsufficientFunds
            lottery = connection.execute("SELECT round FROM economy_lottery WHERE id=1").fetchone()
            round_id = int(lottery["round"])
            connection.execute(
                "UPDATE economy_accounts SET wallet=wallet-?,updated_at=? WHERE user_id=?",
                (cost, now, user_id),
            )
            connection.execute("UPDATE economy_lottery SET pool=pool+? WHERE id=1", (cost,))
            connection.execute(
                """INSERT INTO economy_lottery_entries(round,user_id,tickets) VALUES (?,?,?)
                   ON CONFLICT(round,user_id) DO UPDATE SET tickets=tickets+excluded.tickets""",
                (round_id, user_id, tickets),
            )
            self._transaction(connection, user_id, -cost, "wallet", "lottery_tickets")
            row = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (user_id,)).fetchone()
        return self._account_from_row(row), self.lottery_status(user_id)

    def draw_lottery(self) -> tuple[int, int, int] | None:
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            lottery = connection.execute("SELECT pool,round FROM economy_lottery WHERE id=1").fetchone()
            pool, round_id = int(lottery["pool"]), int(lottery["round"])
            entries = connection.execute(
                "SELECT user_id,tickets FROM economy_lottery_entries WHERE round=?", (round_id,)
            ).fetchall()
            if pool <= 0 or not entries:
                return None
            winner_id = random.choices(
                [int(row["user_id"]) for row in entries],
                weights=[int(row["tickets"]) for row in entries], k=1,
            )[0]
            self._ensure_account(connection, winner_id)
            now = int(time.time())
            connection.execute(
                "UPDATE economy_accounts SET wallet=wallet+?,updated_at=? WHERE user_id=?",
                (pool, now, winner_id),
            )
            connection.execute(
                "UPDATE economy_lottery SET pool=0,round=round+1,ends_at=? WHERE id=1",
                (now + 36 * 60 * 60,),
            )
            self._transaction(connection, winner_id, pool, "wallet", "lottery_win")
            return winner_id, pool, round_id

    def withdraw(self, user_id: int, amount: int) -> Account:
        if amount <= 0: raise ValueError
        now = int(time.time())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE"); self._ensure_account(connection, user_id)
            row = connection.execute("SELECT bank FROM economy_accounts WHERE user_id=?", (user_id,)).fetchone()
            if int(row["bank"]) < amount: raise InsufficientFunds
            connection.execute("UPDATE economy_accounts SET bank=bank-?, wallet=wallet+?, updated_at=? WHERE user_id=?", (amount, amount, now, user_id))
            self._transaction(connection, user_id, -amount, "bank", "withdraw")
            self._transaction(connection, user_id, amount, "wallet", "withdraw")
            row = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (user_id,)).fetchone()
            return self._account_from_row(row)

    def expand_bank(self, user_id: int) -> tuple[Account, int]:
        now = int(time.time())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE"); self._ensure_account(connection, user_id)
            row = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (user_id,)).fetchone()
            cost = self.bank_upgrade_cost(int(row["bank_level"]))
            if int(row["wallet"]) < cost: raise InsufficientFunds
            connection.execute("UPDATE economy_accounts SET wallet=wallet-?, bank_level=bank_level+1, updated_at=? WHERE user_id=?", (cost, now, user_id))
            self._transaction(connection, user_id, -cost, "wallet", "bank_upgrade")
            row = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (user_id,)).fetchone()
            return self._account_from_row(row), cost

    def leaderboard(self, user_ids: list[int] | None, ranking: str, limit: int = 10) -> list[sqlite3.Row]:
        expression = {"net": "wallet + bank", "cash": "wallet", "bank": "bank"}[ranking]
        with self._lock, self._connection() as connection:
            if user_ids is not None:
                if not user_ids: return []
                placeholders = ",".join("?" for _ in user_ids)
                query = f"SELECT user_id,wallet,bank,{expression} AS score FROM economy_accounts WHERE user_id IN ({placeholders}) ORDER BY score DESC, user_id LIMIT ?"
                return connection.execute(query, (*user_ids, limit)).fetchall()
            return connection.execute(f"SELECT user_id,wallet,bank,{expression} AS score FROM economy_accounts ORDER BY score DESC, user_id LIMIT ?", (limit,)).fetchall()

    def leaderboard_rank(
        self,
        user_id: int,
        user_ids: list[int] | None,
        ranking: str,
    ) -> tuple[int, int] | None:
        expression = {"net": "wallet + bank", "cash": "wallet", "bank": "bank"}[ranking]
        with self._lock, self._connection() as connection:
            self._ensure_account(connection, user_id)
            if user_ids is not None and user_id not in user_ids:
                return None
            row = connection.execute(
                f"SELECT {expression} AS score FROM economy_accounts WHERE user_id=?",
                (user_id,),
            ).fetchone()
            if row is None:
                return None
            score = int(row["score"])
            params: list[Any] = [score, score, user_id]
            membership = ""
            if user_ids is not None:
                if not user_ids:
                    return None
                placeholders = ",".join("?" for _ in user_ids)
                membership = f" AND user_id IN ({placeholders})"
                params.extend(user_ids)
            higher = connection.execute(
                f"""SELECT COUNT(*) AS count FROM economy_accounts
                WHERE ({expression} > ? OR ({expression} = ? AND user_id < ?)){membership}""",
                params,
            ).fetchone()
            return int(higher["count"]) + 1, score

    def balance_ranks(self, user_id: int) -> dict[str, int]:
        """Calculate wallet, bank, and net-worth positions in one query."""
        with self._lock, self._connection() as connection:
            self._ensure_account(connection, user_id)
            row = connection.execute(
                """SELECT
                    1 + (SELECT COUNT(*) FROM economy_accounts other
                         WHERE other.wallet > mine.wallet OR
                         (other.wallet = mine.wallet AND other.user_id < mine.user_id)) AS wallet_rank,
                    1 + (SELECT COUNT(*) FROM economy_accounts other
                         WHERE other.bank > mine.bank OR
                         (other.bank = mine.bank AND other.user_id < mine.user_id)) AS bank_rank,
                    1 + (SELECT COUNT(*) FROM economy_accounts other
                         WHERE (other.wallet + other.bank) > (mine.wallet + mine.bank) OR
                         ((other.wallet + other.bank) = (mine.wallet + mine.bank)
                          AND other.user_id < mine.user_id)) AS net_rank
                FROM economy_accounts mine WHERE mine.user_id=?""",
                (user_id,),
            ).fetchone()
        assert row is not None
        return {
            "wallet": int(row["wallet_rank"]),
            "bank": int(row["bank_rank"]),
            "net": int(row["net_rank"]),
        }

    def cooldowns(self, user_id: int) -> dict[str, int]:
        now = int(time.time())
        with self._lock, self._connection() as connection:
            self._ensure_account(connection, user_id)
            account = connection.execute(
                "SELECT daily_last,work_last,robber_cooldown_until FROM economy_accounts WHERE user_id=?",
                (user_id,),
            ).fetchone()
            result = {
                "daily": max(0, int(account["daily_last"] or 0) + 86_400 - now),
                "work": max(0, int(account["work_last"] or 0) + 43_200 - now),
                "rob": max(0, int(account["robber_cooldown_until"] or 0) - now),
            }
            rows = connection.execute(
                "SELECT game,available_at FROM game_reward_cooldowns WHERE user_id=?",
                (user_id,),
            ).fetchall()
            for row in rows:
                result[f"reward:{row['game']}"] = max(0, int(row["available_at"]) - now)
            return result

    def create_giveaway(
        self,
        guild_id: int,
        channel_id: int,
        host_id: int,
        amount: int,
        winner_count: int,
        ends_at: int,
    ) -> int:
        if amount <= 0 or winner_count <= 0 or amount < winner_count or ends_at <= int(time.time()):
            raise ValueError
        now = int(time.time())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_account(connection, host_id)
            account = connection.execute(
                "SELECT wallet FROM economy_accounts WHERE user_id=?", (host_id,)
            ).fetchone()
            if int(account["wallet"]) < amount:
                raise InsufficientFunds
            connection.execute(
                "UPDATE economy_accounts SET wallet=wallet-?,updated_at=? WHERE user_id=?",
                (amount, now, host_id),
            )
            cursor = connection.execute(
                """INSERT INTO economy_giveaways
                (guild_id,channel_id,host_id,amount,winner_count,ends_at,created_at)
                VALUES (?,?,?,?,?,?,?)""",
                (guild_id, channel_id, host_id, amount, winner_count, ends_at, now),
            )
            giveaway_id = int(cursor.lastrowid)
            self._transaction(
                connection,
                host_id,
                -amount,
                "wallet",
                "giveaway_reserve",
                reason=f"Giveaway #{giveaway_id}",
            )
            return giveaway_id

    def set_giveaway_message(self, giveaway_id: int, message_id: int) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "UPDATE economy_giveaways SET message_id=? WHERE id=? AND status='active'",
                (message_id, giveaway_id),
            )

    def active_giveaways(self) -> list[sqlite3.Row]:
        with self._lock, self._connection() as connection:
            return connection.execute(
                """SELECT g.*,COUNT(e.user_id) AS entries
                FROM economy_giveaways g
                LEFT JOIN economy_giveaway_entries e ON e.giveaway_id=g.id
                WHERE g.status='active' GROUP BY g.id ORDER BY g.ends_at"""
            ).fetchall()

    def giveaway(self, giveaway_id: int) -> sqlite3.Row | None:
        with self._lock, self._connection() as connection:
            return connection.execute(
                """SELECT g.*,COUNT(e.user_id) AS entries
                FROM economy_giveaways g
                LEFT JOIN economy_giveaway_entries e ON e.giveaway_id=g.id
                WHERE g.id=? GROUP BY g.id""",
                (giveaway_id,),
            ).fetchone()

    def enter_giveaway(self, giveaway_id: int, user_id: int) -> tuple[bool, int]:
        now = int(time.time())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            giveaway = connection.execute(
                "SELECT host_id,status,ends_at FROM economy_giveaways WHERE id=?",
                (giveaway_id,),
            ).fetchone()
            if giveaway is None or giveaway["status"] != "active" or int(giveaway["ends_at"]) <= now:
                raise EconomyError("ended")
            if int(giveaway["host_id"]) == user_id:
                raise EconomyError("host")
            cursor = connection.execute(
                "INSERT OR IGNORE INTO economy_giveaway_entries VALUES (?,?,?)",
                (giveaway_id, user_id, now),
            )
            count = connection.execute(
                "SELECT COUNT(*) AS count FROM economy_giveaway_entries WHERE giveaway_id=?",
                (giveaway_id,),
            ).fetchone()
            return cursor.rowcount > 0, int(count["count"])

    def finish_giveaway(self, giveaway_id: int) -> tuple[sqlite3.Row, list[tuple[int, int]]] | None:
        now = int(time.time())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            giveaway = connection.execute(
                "SELECT * FROM economy_giveaways WHERE id=?", (giveaway_id,)
            ).fetchone()
            if giveaway is None or giveaway["status"] != "active":
                return None
            connection.execute(
                "UPDATE economy_giveaways SET status='ended' WHERE id=?", (giveaway_id,)
            )
            entrants = [
                int(row["user_id"])
                for row in connection.execute(
                    "SELECT user_id FROM economy_giveaway_entries WHERE giveaway_id=?",
                    (giveaway_id,),
                ).fetchall()
            ]
            amount = int(giveaway["amount"])
            host_id = int(giveaway["host_id"])
            if not entrants:
                connection.execute(
                    "UPDATE economy_accounts SET wallet=wallet+?,updated_at=? WHERE user_id=?",
                    (amount, now, host_id),
                )
                self._transaction(
                    connection, host_id, amount, "wallet", "giveaway_refund",
                    reason=f"Giveaway #{giveaway_id} had no entries",
                )
                return giveaway, []
            winner_ids = random.sample(entrants, min(int(giveaway["winner_count"]), len(entrants)))
            base, remainder = divmod(amount, len(winner_ids))
            payouts: list[tuple[int, int]] = []
            for index, winner_id in enumerate(winner_ids):
                payout = base + (1 if index < remainder else 0)
                self._ensure_account(connection, winner_id)
                connection.execute(
                    "UPDATE economy_accounts SET wallet=wallet+?,updated_at=? WHERE user_id=?",
                    (payout, now, winner_id),
                )
                self._transaction(
                    connection, winner_id, payout, "wallet", "giveaway_prize",
                    other_user_id=host_id, reason=f"Giveaway #{giveaway_id}",
                )
                payouts.append((winner_id, payout))
            return giveaway, payouts

    def is_admin(self, user_id: int) -> bool:
        with self._lock, self._connection() as connection:
            return connection.execute("SELECT 1 FROM economy_admins WHERE user_id=?", (user_id,)).fetchone() is not None

    def list_admins(self) -> list[sqlite3.Row]:
        with self._lock, self._connection() as connection:
            return connection.execute("SELECT * FROM economy_admins ORDER BY added_at").fetchall()

    def add_admin(self, user_id: int, added_by: int) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute("INSERT OR IGNORE INTO economy_admins VALUES (?,?,?)", (user_id, added_by, int(time.time())))
            return cursor.rowcount > 0

    def remove_admin(self, user_id: int) -> bool:
        with self._lock, self._connection() as connection:
            return connection.execute("DELETE FROM economy_admins WHERE user_id=?", (user_id,)).rowcount > 0

    def admin_change(self, user_id: int, amount: int, actor_id: int, reason: str, *, take: bool = False) -> Account:
        if amount <= 0: raise ValueError
        now = int(time.time())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE"); self._ensure_account(connection, user_id)
            row = connection.execute("SELECT wallet FROM economy_accounts WHERE user_id=?", (user_id,)).fetchone()
            change = -min(amount, int(row["wallet"])) if take else amount
            connection.execute("UPDATE economy_accounts SET wallet=wallet+?, updated_at=? WHERE user_id=?", (change, now, user_id))
            self._transaction(connection, user_id, change, "wallet", "admin_take" if take else "admin_add", actor_id=actor_id, reason=reason)
            row = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (user_id,)).fetchone()
            return self._account_from_row(row)

    def reset(self, user_id: int, location: str, actor_id: int, reason: str) -> Account:
        now = int(time.time())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE"); self._ensure_account(connection, user_id)
            row = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (user_id,)).fetchone()
            wallet, bank = int(row["wallet"]), int(row["bank"])
            if location in {"wallet", "both"} and wallet: self._transaction(connection, user_id, -wallet, "wallet", "admin_reset", actor_id=actor_id, reason=reason)
            if location in {"bank", "both"} and bank: self._transaction(connection, user_id, -bank, "bank", "admin_reset", actor_id=actor_id, reason=reason)
            assignments = {"wallet": "wallet=0", "bank": "bank=0", "both": "wallet=0, bank=0"}[location]
            connection.execute(f"UPDATE economy_accounts SET {assignments}, updated_at=? WHERE user_id=?", (now, user_id))
            row = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (user_id,)).fetchone()
            return self._account_from_row(row)

    def transactions(
        self,
        limit: int = 50,
        *,
        user_id: int | None = None,
    ) -> list[sqlite3.Row]:
        cutoff = int(time.time()) - TRANSACTION_RETENTION_SECONDS
        with self._lock, self._connection() as connection:
            connection.execute("DELETE FROM economy_transactions WHERE created_at < ?", (cutoff,))
            if user_id is None:
                return connection.execute(
                    "SELECT * FROM economy_transactions ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return connection.execute(
                """SELECT * FROM economy_transactions
                WHERE user_id = ? ORDER BY created_at DESC LIMIT ?""",
                (user_id, limit),
            ).fetchall()

    def daily_balance_history(self, user_id: int, days: int = 7) -> list[tuple[int, int]]:
        """Reconstruct end-of-day net balances from retained transaction deltas."""
        now = int(time.time())
        day = 86_400
        account = self.get_account(user_id)
        start = now - days * day
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                """SELECT amount, created_at FROM economy_transactions
                WHERE user_id = ? AND created_at >= ? AND balance_type != 'fee'
                ORDER BY created_at DESC""",
                (user_id, start),
            ).fetchall()
        current = account.net
        points: list[tuple[int, int]] = []
        for offset in range(days - 1, -1, -1):
            boundary = now - offset * day
            later_delta = sum(int(row["amount"]) for row in rows if int(row["created_at"]) > boundary)
            points.append((boundary, current - later_delta))
        return points

    def robbery_status(self, robber_id: int, target_id: int) -> tuple[int, int, Account, Account]:
        now = int(time.time())
        with self._lock, self._connection() as connection:
            self._ensure_account(connection, robber_id); self._ensure_account(connection, target_id)
            robber_row = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (robber_id,)).fetchone()
            target_row = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (target_id,)).fetchone()
            return max(0, int(robber_row["robber_cooldown_until"])-now), max(0, int(target_row["robbed_protected_until"])-now), self._account_from_row(robber_row), self._account_from_row(target_row)

    def finish_robbery(self, robber_id: int, target_id: int, percentage: int, failed: bool) -> tuple[int, Account, Account]:
        now = int(time.time())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE"); self._ensure_account(connection, robber_id); self._ensure_account(connection, target_id)
            robber = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (robber_id,)).fetchone()
            target = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (target_id,)).fetchone()
            if int(robber["robber_cooldown_until"]) > now or int(target["robbed_protected_until"]) > now: raise EconomyError("cooldown")
            if int(target["wallet"]) < 1_000: raise InsufficientFunds
            if failed:
                fine = max(1, round((int(robber["wallet"]) + int(robber["bank"])) * .05))
                wallet_fine = min(fine, int(robber["wallet"])); bank_fine = min(fine-wallet_fine, int(robber["bank"]))
                connection.execute("UPDATE economy_accounts SET wallet=wallet-?, bank=bank-?, robber_cooldown_until=?, updated_at=? WHERE user_id=?", (wallet_fine, bank_fine, now+1800, now, robber_id))
                self._transaction(connection, robber_id, -fine, "net", "robbery_fine", other_user_id=target_id)
                result = -fine
            else:
                stolen = max(1, min(int(target["wallet"]), round(int(target["wallet"]) * min(percentage, 30) / 100)))
                connection.execute("UPDATE economy_accounts SET wallet=wallet+?, robber_cooldown_until=?, updated_at=? WHERE user_id=?", (stolen, now+1800, now, robber_id))
                connection.execute("UPDATE economy_accounts SET wallet=wallet-?, robbed_protected_until=?, updated_at=? WHERE user_id=?", (stolen, now+900, now, target_id))
                self._transaction(connection, robber_id, stolen, "wallet", "robbery", other_user_id=target_id)
                self._transaction(connection, target_id, -stolen, "wallet", "robbed", other_user_id=robber_id)
                result = stolen
            robber = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (robber_id,)).fetchone(); target = connection.execute("SELECT * FROM economy_accounts WHERE user_id=?", (target_id,)).fetchone()
            return result, self._account_from_row(robber), self._account_from_row(target)

    def start_bet(self, user_id: int, game: str, bet: int) -> Account:
        if bet <= 0:
            raise ValueError("Bet must be positive")
        now = int(time.time())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_account(connection, user_id)
            row = connection.execute(
                "SELECT wallet FROM economy_accounts WHERE user_id=?", (user_id,)
            ).fetchone()
            if int(row["wallet"]) < bet:
                raise InsufficientFunds
            connection.execute(
                "UPDATE economy_accounts SET wallet=wallet-?, updated_at=? WHERE user_id=?",
                (bet, now, user_id),
            )
            connection.execute(
                """INSERT INTO gambling_stats (user_id, game, games, wagered)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(user_id, game) DO UPDATE SET
                games=games+1, wagered=wagered+excluded.wagered""",
                (user_id, game, bet),
            )
            self._transaction(connection, user_id, -bet, "wallet", f"{game}_bet")
            row = connection.execute(
                "SELECT * FROM economy_accounts WHERE user_id=?", (user_id,)
            ).fetchone()
            return self._account_from_row(row)

    def settle_bet(
        self,
        user_id: int,
        game: str,
        bet: int,
        returned: int,
        outcome: str,
    ) -> Account:
        returned = max(0, int(returned))
        profit = returned - bet
        now = int(time.time())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_account(connection, user_id)
            if returned:
                connection.execute(
                    "UPDATE economy_accounts SET wallet=wallet+?, updated_at=? WHERE user_id=?",
                    (returned, now, user_id),
                )
                self._transaction(
                    connection, user_id, returned, "wallet", f"{game}_payout"
                )
            win = int(outcome == "win")
            loss = int(outcome == "loss")
            push = int(outcome == "push")
            connection.execute(
                """UPDATE gambling_stats SET
                returned=returned+?, wins=wins+?, losses=losses+?, pushes=pushes+?,
                current_streak=CASE WHEN ? THEN current_streak+1 WHEN ? THEN 0 ELSE current_streak END,
                best_streak=CASE WHEN ? THEN MAX(best_streak,current_streak+1) ELSE best_streak END,
                biggest_win=MAX(biggest_win,?), biggest_loss=MAX(biggest_loss,?)
                WHERE user_id=? AND game=?""",
                (returned, win, loss, push, win, loss, win, max(0, profit), max(0, -profit), user_id, game),
            )
            row = connection.execute(
                "SELECT * FROM economy_accounts WHERE user_id=?", (user_id,)
            ).fetchone()
            return self._account_from_row(row)

    def gambling_stats(self, user_id: int) -> list[sqlite3.Row]:
        with self._lock, self._connection() as connection:
            return connection.execute(
                "SELECT * FROM gambling_stats WHERE user_id=? ORDER BY games DESC, game",
                (user_id,),
            ).fetchall()

    def award_game_reward(
        self, user_id: int, game: str, amount: int, cooldown: int = 300
    ) -> int:
        """Award silently; returns zero while that game's reward is cooling down."""
        if amount <= 0:
            return 0
        now = int(time.time())
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_account(connection, user_id)
            row = connection.execute(
                "SELECT available_at FROM game_reward_cooldowns WHERE user_id=? AND game=?",
                (user_id, game),
            ).fetchone()
            if row and int(row["available_at"]) > now:
                return 0
            connection.execute(
                """INSERT INTO game_reward_cooldowns VALUES (?,?,?)
                ON CONFLICT(user_id,game) DO UPDATE SET available_at=excluded.available_at""",
                (user_id, game, now + cooldown),
            )
            connection.execute(
                "UPDATE economy_accounts SET wallet=wallet+?, updated_at=? WHERE user_id=?",
                (amount, now, user_id),
            )
            self._transaction(connection, user_id, amount, "wallet", f"{game}_reward")
            return amount


store = EconomyStore()
