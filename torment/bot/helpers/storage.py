from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import asyncpg


@dataclass
class Storage:
    dsn: str
    pool: asyncpg.Pool | None = None

    @classmethod
    def from_env(cls) -> "Storage":
        dsn = os.getenv("DATABASE_URL")
        if dsn is None or not dsn.strip():
            raise RuntimeError("Missing required environment variable: DATABASE_URL")
        return cls(dsn=dsn)

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def initialize(self) -> None:
        if not self.pool:
            await self.connect()
        if not self.pool:
            raise RuntimeError("database pool is not available")

        await self.pool.execute(
            """
            create table if not exists guild_config (
                guild_id bigint primary key,
                modlog_channel_id bigint,
                muted_role_id bigint,
                image_muted_role_id bigint,
                reaction_muted_role_id bigint,
                prefixes text[]
            )
            """
        )
        await self.pool.execute(
            """
            do $$
            begin
                if not exists (
                    select 1 from information_schema.columns
                    where table_name = 'guild_config' and column_name = 'prefixes'
                ) then
                    alter table guild_config add column prefixes text[];
                end if;
            end $$;
            """
        )
        await self.pool.execute(
            """
            create table if not exists cases (
                id bigserial primary key,
                guild_id bigint not null,
                action text not null,
                target_id bigint,
                target_name text not null,
                moderator_id bigint not null,
                moderator_name text not null,
                reason text,
                metadata_json text not null default '{}',
                created_at timestamptz not null default now()
            )
            """
        )
        await self.pool.execute(
            """
            create table if not exists forced_nicknames (
                guild_id bigint not null,
                user_id bigint not null,
                nickname text not null,
                moderator_id bigint not null,
                created_at timestamptz not null default now(),
                primary key (guild_id, user_id)
            )
            """
        )
        await self.pool.execute(
            """
            create table if not exists welcome_messages (
                guild_id bigint not null,
                channel_id bigint not null,
                message text not null,
                created_at timestamptz not null default now(),
                primary key (guild_id, channel_id)
            )
            """
        )
        await self.pool.execute(
            """
            create table if not exists goodbye_messages (
                guild_id bigint not null,
                channel_id bigint not null,
                message text not null,
                created_at timestamptz not null default now(),
                primary key (guild_id, channel_id)
            )
            """
        )
        await self.pool.execute(
            """
            create table if not exists boost_messages (
                guild_id bigint not null,
                channel_id bigint not null,
                message text not null,
                created_at timestamptz not null default now(),
                primary key (guild_id, channel_id)
            )
            """
        )
        await self.pool.execute(
            """
            create table if not exists antiraid (
                guild_id bigint not null,
                command text not null,
                punishment text not null,
                seconds bigint not null default 0,
                primary key (guild_id, command)
            )
            """
        )
        await self.pool.execute(
            """
            create table if not exists whitelist (
                guild_id bigint not null,
                module text not null,
                object_id bigint not null,
                mode text not null,
                primary key (guild_id, module, object_id, mode)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS afk (
                user_id BIGINT PRIMARY KEY,
                guild_id BIGINT,
                time TIMESTAMP NOT NULL DEFAULT NOW(),
                status TEXT NOT NULL DEFAULT 'AFK'
            )
            """
        )
        
        await self.pool.execute(
            """
            DO $$ 
            BEGIN 
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'afk' AND column_name = 'status'
                ) THEN
                    ALTER TABLE afk ADD COLUMN status TEXT NOT NULL DEFAULT 'AFK';
                END IF;
            END $$;
            """
        )
        
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS prefix (
                guild_id BIGINT PRIMARY KEY,
                prefix TEXT NOT NULL DEFAULT ','
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS command_disabled (
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                command TEXT NOT NULL,
                PRIMARY KEY (guild_id, channel_id, command)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS command_restricted (
                guild_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                command TEXT NOT NULL,
                PRIMARY KEY (guild_id, role_id, command)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS fake_permissions (
                guild_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                permission TEXT NOT NULL,
                PRIMARY KEY (guild_id, role_id, permission)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS autoresponder (
                guild_id BIGINT NOT NULL,
                trigger_text TEXT NOT NULL,
                response TEXT NOT NULL,
                is_embed BOOLEAN NOT NULL DEFAULT FALSE,
                strict BOOLEAN NOT NULL DEFAULT TRUE,
                self_destruct INTEGER,
                delete_trigger BOOLEAN NOT NULL DEFAULT FALSE,
                reply BOOLEAN NOT NULL DEFAULT FALSE,
                ignore_command_check BOOLEAN NOT NULL DEFAULT FALSE,
                PRIMARY KEY (guild_id, trigger_text)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS autoresponder_exclusive (
                guild_id BIGINT NOT NULL,
                trigger TEXT NOT NULL,
                object_id BIGINT NOT NULL,
                object_type TEXT NOT NULL,
                PRIMARY KEY (guild_id, trigger, object_id, object_type)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS sticky (
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                template TEXT NOT NULL,
                PRIMARY KEY (guild_id, channel_id)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS lastfm_reactions (
                guild_id BIGINT PRIMARY KEY,
                upvote TEXT NOT NULL,
                downvote TEXT NOT NULL
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS birthday_users (
                user_id BIGINT PRIMARY KEY,
                birthday TIMESTAMP NOT NULL
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS birthday_config (
                guild_id BIGINT PRIMARY KEY,
                role_id BIGINT,
                channel_id BIGINT,
                template TEXT
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                text TEXT NOT NULL,
                jump_url TEXT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await self.pool.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'reminders' 
                    AND column_name = 'expires_at'
                    AND data_type = 'timestamp without time zone'
                ) THEN
                    ALTER TABLE reminders 
                    ALTER COLUMN expires_at TYPE TIMESTAMPTZ USING expires_at AT TIME ZONE 'UTC';
                    ALTER TABLE reminders 
                    ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC';
                END IF;
            END $$;
            """
        )
        await self.pool.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reminders_expires 
            ON reminders(expires_at)
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS user_notes (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                moderator_id BIGINT NOT NULL,
                note TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await self.pool.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_notes_lookup 
            ON user_notes(guild_id, user_id)
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS autoroles (
                guild_id BIGINT NOT NULL,
                role_id  BIGINT NOT NULL,
                PRIMARY KEY (guild_id, role_id)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS roleplay_counts (
                action TEXT NOT NULL,
                author_id BIGINT NOT NULL,
                target_id BIGINT NOT NULL,
                count INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (action, author_id, target_id)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS staff_roles (
                guild_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                PRIMARY KEY (guild_id, role_id)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS joindm (
                guild_id BIGINT PRIMARY KEY,
                message TEXT NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS shutup (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS seen (
                guild_id BIGINT NOT NULL,
                user_id  BIGINT NOT NULL,
                seen_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS thread_watch (
                guild_id  BIGINT NOT NULL,
                thread_id BIGINT NOT NULL,
                user_id   BIGINT NOT NULL,
                PRIMARY KEY (guild_id, thread_id, user_id)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS reaction_roles (
                guild_id    BIGINT NOT NULL,
                channel_id  BIGINT NOT NULL,
                message_id  BIGINT NOT NULL,
                emoji       TEXT NOT NULL,
                role_id     BIGINT NOT NULL,
                PRIMARY KEY (message_id, emoji)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS nuke_schedule (
                guild_id    BIGINT NOT NULL,
                channel_id  BIGINT NOT NULL,
                interval    INTERVAL NOT NULL,
                next_trigger TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (guild_id, channel_id)
            )
            """
        )
        await self.pool.execute(
            "ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS participants BIGINT[] NOT NULL DEFAULT '{}'"
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS booster_roles (
                guild_id BIGINT NOT NULL,
                user_id  BIGINT NOT NULL,
                role_id  BIGINT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS booster_role_config (
                guild_id     BIGINT PRIMARY KEY,
                base_role_id BIGINT,
                enabled      BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS booster_role_include (
                guild_id BIGINT NOT NULL,
                role_id  BIGINT NOT NULL,
                PRIMARY KEY (guild_id, role_id)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS user_timezones (
                user_id BIGINT PRIMARY KEY,
                timezone TEXT NOT NULL
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS button_roles (
                guild_id   BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                role_id    BIGINT NOT NULL,
                style      TEXT NOT NULL DEFAULT 'blurple',
                emoji      TEXT,
                label      TEXT,
                PRIMARY KEY (message_id, role_id)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS vanity_config (
                guild_id   BIGINT PRIMARY KEY,
                substring  TEXT,
                channel_id BIGINT,
                message    TEXT
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS vanity_roles (
                guild_id BIGINT NOT NULL,
                role_id  BIGINT NOT NULL,
                PRIMARY KEY (guild_id, role_id)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS vanity_members (
                guild_id BIGINT NOT NULL,
                user_id  BIGINT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS timers (
                guild_id   BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                interval   INTERVAL NOT NULL,
                message    TEXT NOT NULL,
                next_send  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, channel_id)
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS bump_config (
                guild_id        BIGINT PRIMARY KEY,
                status          BOOLEAN NOT NULL DEFAULT TRUE,
                channel_id      BIGINT,
                last_channel_id BIGINT,
                last_user_id    BIGINT,
                next_bump       TIMESTAMPTZ,
                message         TEXT,
                thank_message   TEXT
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS bump_stats (
                guild_id BIGINT NOT NULL,
                user_id  BIGINT NOT NULL,
                bumped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        migrations = [
            ("reminders", "expires_at", "TIMESTAMPTZ", "NOW()"),
            ("reminders", "jump_url", "TEXT", "''"),
            ("reminders", "text", "TEXT", "''"),
            ("birthday_config", "role_id", "BIGINT", "NULL"),
            ("birthday_config", "channel_id", "BIGINT", "NULL"),
            ("birthday_config", "template", "TEXT", "NULL"),
            ("guild_config", "prefixes", "TEXT[]", "NULL"),
            ("autoresponder", "strict", "BOOLEAN", "TRUE"),
            ("autoresponder", "self_destruct", "INTEGER", "NULL"),
            ("autoresponder", "delete_trigger", "BOOLEAN", "FALSE"),
            ("autoresponder", "reply", "BOOLEAN", "FALSE"),
            ("autoresponder", "ignore_command_check", "BOOLEAN", "FALSE"),
            ("autoresponder", "is_embed", "BOOLEAN", "FALSE"),
            ("sticky", "message_id", "BIGINT", "0"),
            ("sticky", "template", "TEXT", "''"),
            ("joindm", "enabled", "BOOLEAN", "FALSE"),
            ("joindm", "message", "TEXT", "''"),
        ]
        for table, column, col_type, default in migrations:
            await self.pool.execute(
                f"""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = '{table}' AND column_name = '{column}'
                    ) THEN
                        ALTER TABLE {table} ADD COLUMN {column} {col_type} DEFAULT {default};
                    END IF;
                END $$;
                """
            )


        await self.pool.execute(
            """
            DO $$ BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'afk' AND column_name = 'guild_id'
                ) AND NOT EXISTS (
                    SELECT 1 FROM information_schema.key_column_usage
                    WHERE table_name = 'afk' AND column_name = 'guild_id'
                    AND constraint_name IN (
                        SELECT constraint_name FROM information_schema.table_constraints
                        WHERE table_name = 'afk' AND constraint_type = 'PRIMARY KEY'
                    )
                ) THEN
                    ALTER TABLE afk ALTER COLUMN guild_id DROP NOT NULL;
                END IF;
            END $$;
            """
        )
    def _decode_case_row(self, row: asyncpg.Record | None) -> dict[str, Any] | None:
        if not row:
            return None
        payload = dict(row)
        payload["metadata"] = json.loads(payload.pop("metadata_json") or "{}")
        return payload

    async def get_config(self, guild_id: int) -> dict[str, Any]:
        if not self.pool:
            return {
                "guild_id": guild_id,
                "modlog_channel_id": None,
                "muted_role_id": None,
                "image_muted_role_id": None,
                "reaction_muted_role_id": None,
                "prefixes": None,
            }

        row = await self.pool.fetchrow(
            "select * from guild_config where guild_id = $1",
            guild_id,
        )
        if row:
            return dict(row)
        return {
            "guild_id": guild_id,
            "modlog_channel_id": None,
            "muted_role_id": None,
            "image_muted_role_id": None,
            "reaction_muted_role_id": None,
            "prefixes": None,
        }

    async def set_config_value(self, guild_id: int, field: str, value: int | None) -> None:
        existing = await self.get_config(guild_id)
        if not self.pool:
            raise RuntimeError("database pool is not available")

        await self.pool.execute(
            """
            insert into guild_config (
                guild_id,
                modlog_channel_id,
                muted_role_id,
                image_muted_role_id,
                reaction_muted_role_id,
                prefixes
            ) values ($1, $2, $3, $4, $5, $6)
            on conflict (guild_id) do update set
                modlog_channel_id = excluded.modlog_channel_id,
                muted_role_id = excluded.muted_role_id,
                image_muted_role_id = excluded.image_muted_role_id,
                reaction_muted_role_id = excluded.reaction_muted_role_id,
                prefixes = excluded.prefixes
            """,
            guild_id,
            value if field == "modlog_channel_id" else existing["modlog_channel_id"],
            value if field == "muted_role_id" else existing["muted_role_id"],
            value if field == "image_muted_role_id" else existing["image_muted_role_id"],
            value if field == "reaction_muted_role_id" else existing["reaction_muted_role_id"],
            existing["prefixes"],
        )

    async def set_prefixes(self, guild_id: int, prefixes: list[str] | None) -> None:
        existing = await self.get_config(guild_id)
        if not self.pool:
            raise RuntimeError("database pool is not available")

        await self.pool.execute(
            """
            insert into guild_config (
                guild_id,
                modlog_channel_id,
                muted_role_id,
                image_muted_role_id,
                reaction_muted_role_id,
                prefixes
            ) values ($1, $2, $3, $4, $5, $6)
            on conflict (guild_id) do update set
                prefixes = excluded.prefixes
            """,
            guild_id,
            existing["modlog_channel_id"],
            existing["muted_role_id"],
            existing["image_muted_role_id"],
            existing["reaction_muted_role_id"],
            prefixes,
        )

    async def create_case(
        self,
        *,
        guild_id: int,
        action: str,
        target_id: int | None,
        target_name: str,
        moderator_id: int,
        moderator_name: str,
        reason: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.pool:
            raise RuntimeError("database pool is not available")

        row = await self.pool.fetchrow(
            """
            insert into cases (
                guild_id,
                action,
                target_id,
                target_name,
                moderator_id,
                moderator_name,
                reason,
                metadata_json
            ) values ($1, $2, $3, $4, $5, $6, $7, $8)
            returning *
            """,
            guild_id,
            action,
            target_id,
            target_name,
            moderator_id,
            moderator_name,
            reason,
            json.dumps(metadata or {}),
        )
        case = self._decode_case_row(row)
        if not case:
            raise RuntimeError("failed to create case")
        return case

    async def get_case(self, case_id: int) -> dict[str, Any] | None:
        if not self.pool:
            return None
        row = await self.pool.fetchrow(
            "select * from cases where id = $1",
            case_id,
        )
        return self._decode_case_row(row)

    async def list_cases(
        self,
        guild_id: int,
        *,
        target_id: int | None = None,
        action: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if not self.pool:
            return []

        if target_id is not None and action is not None:
            rows = await self.pool.fetch(
                """
                select * from cases
                where guild_id = $1 and target_id = $2 and action = $3
                order by id desc
                limit $4
                """,
                guild_id,
                target_id,
                action,
                limit,
            )
        elif target_id is not None:
            rows = await self.pool.fetch(
                """
                select * from cases
                where guild_id = $1 and target_id = $2
                order by id desc
                limit $3
                """,
                guild_id,
                target_id,
                limit,
            )
        elif action is not None:
            rows = await self.pool.fetch(
                """
                select * from cases
                where guild_id = $1 and action = $2
                order by id desc
                limit $3
                """,
                guild_id,
                action,
                limit,
            )
        else:
            rows = await self.pool.fetch(
                """
                select * from cases
                where guild_id = $1
                order by id desc
                limit $2
                """,
                guild_id,
                limit,
            )

        return [self._decode_case_row(row) for row in rows if row]

    async def update_case_reason(self, case_id: int, reason: str) -> None:
        if not self.pool:
            raise RuntimeError("database pool is not available")
        await self.pool.execute(
            "update cases set reason = $1 where id = $2",
            reason,
            case_id,
        )

    async def set_forced_nickname(self, guild_id: int, user_id: int, nickname: str, moderator_id: int) -> None:
        if not self.pool:
            raise RuntimeError("database pool is not available")
        await self.pool.execute(
            """
            insert into forced_nicknames (guild_id, user_id, nickname, moderator_id)
            values ($1, $2, $3, $4)
            on conflict (guild_id, user_id) do update set
                nickname = excluded.nickname,
                moderator_id = excluded.moderator_id,
                created_at = now()
            """,
            guild_id,
            user_id,
            nickname,
            moderator_id,
        )

    async def remove_forced_nickname(self, guild_id: int, user_id: int) -> None:
        if not self.pool:
            raise RuntimeError("database pool is not available")
        await self.pool.execute(
            "delete from forced_nicknames where guild_id = $1 and user_id = $2",
            guild_id,
            user_id,
        )

    async def get_forced_nickname(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        if not self.pool:
            return None
        row = await self.pool.fetchrow(
            """
            select * from forced_nicknames
            where guild_id = $1 and user_id = $2
            """,
            guild_id,
            user_id,
        )
        return dict(row) if row else None

    async def list_forced_nicknames(self, guild_id: int) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        rows = await self.pool.fetch(
            """
            select * from forced_nicknames
            where guild_id = $1
            order by created_at desc
            """,
            guild_id,
        )
        return [dict(row) for row in rows]

    async def add_welcome_message(self, guild_id: int, channel_id: int, message: str) -> None:
        if not self.pool:
            raise RuntimeError("database pool is not available")
        await self.pool.execute(
            """
            insert into welcome_messages (guild_id, channel_id, message)
            values ($1, $2, $3)
            on conflict (guild_id, channel_id) do update set
                message = excluded.message
            """,
            guild_id,
            channel_id,
            message,
        )

    async def remove_welcome_message(self, guild_id: int, channel_id: int) -> bool:
        if not self.pool:
            raise RuntimeError("database pool is not available")
        result = await self.pool.execute(
            "delete from welcome_messages where guild_id = $1 and channel_id = $2",
            guild_id,
            channel_id,
        )
        return result == "DELETE 1"

    async def get_welcome_messages(self, guild_id: int) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        rows = await self.pool.fetch(
            "select * from welcome_messages where guild_id = $1",
            guild_id,
        )
        return [dict(row) for row in rows]

    async def clear_welcome_messages(self, guild_id: int) -> int:
        if not self.pool:
            raise RuntimeError("database pool is not available")
        result = await self.pool.execute(
            "delete from welcome_messages where guild_id = $1",
            guild_id,
        )
        return int(result.split()[-1]) if result else 0

    async def add_goodbye_message(self, guild_id: int, channel_id: int, message: str) -> None:
        if not self.pool:
            raise RuntimeError("database pool is not available")
        await self.pool.execute(
            """
            insert into goodbye_messages (guild_id, channel_id, message)
            values ($1, $2, $3)
            on conflict (guild_id, channel_id) do update set
                message = excluded.message
            """,
            guild_id,
            channel_id,
            message,
        )

    async def remove_goodbye_message(self, guild_id: int, channel_id: int) -> bool:
        if not self.pool:
            raise RuntimeError("database pool is not available")
        result = await self.pool.execute(
            "delete from goodbye_messages where guild_id = $1 and channel_id = $2",
            guild_id,
            channel_id,
        )
        return result == "DELETE 1"

    async def get_goodbye_messages(self, guild_id: int) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        rows = await self.pool.fetch(
            "select * from goodbye_messages where guild_id = $1",
            guild_id,
        )
        return [dict(row) for row in rows]

    async def clear_goodbye_messages(self, guild_id: int) -> int:
        if not self.pool:
            raise RuntimeError("database pool is not available")
        result = await self.pool.execute(
            "delete from goodbye_messages where guild_id = $1",
            guild_id,
        )
        return int(result.split()[-1]) if result else 0

    async def add_boost_message(self, guild_id: int, channel_id: int, message: str) -> None:
        if not self.pool:
            raise RuntimeError("database pool is not available")
        await self.pool.execute(
            """
            insert into boost_messages (guild_id, channel_id, message)
            values ($1, $2, $3)
            on conflict (guild_id, channel_id) do update set
                message = excluded.message
            """,
            guild_id,
            channel_id,
            message,
        )

    async def remove_boost_message(self, guild_id: int, channel_id: int) -> bool:
        if not self.pool:
            raise RuntimeError("database pool is not available")
        result = await self.pool.execute(
            "delete from boost_messages where guild_id = $1 and channel_id = $2",
            guild_id,
            channel_id,
        )
        return result == "DELETE 1"

    async def get_boost_messages(self, guild_id: int) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        rows = await self.pool.fetch(
            "select * from boost_messages where guild_id = $1",
            guild_id,
        )
        return [dict(row) for row in rows]

    async def clear_boost_messages(self, guild_id: int) -> int:
        if not self.pool:
            raise RuntimeError("database pool is not available")
        result = await self.pool.execute(
            "delete from boost_messages where guild_id = $1",
            guild_id,
        )
        return int(result.split()[-1]) if result else 0

    async def toggle_staff_role(self, guild_id: int, role_id: int) -> bool:
        if not self.pool:
            raise RuntimeError("database pool is not available")
        existing = await self.pool.fetchrow(
            "select 1 from staff_roles where guild_id = $1 and role_id = $2",
            guild_id,
            role_id,
        )
        if existing:
            await self.pool.execute(
                "delete from staff_roles where guild_id = $1 and role_id = $2",
                guild_id,
                role_id,
            )
            return False
        else:
            await self.pool.execute(
                "insert into staff_roles (guild_id, role_id) values ($1, $2)",
                guild_id,
                role_id,
            )
            return True

    async def get_staff_roles(self, guild_id: int) -> list[int]:
        if not self.pool:
            return []
        rows = await self.pool.fetch(
            "select role_id from staff_roles where guild_id = $1",
            guild_id,
        )
        return [row["role_id"] for row in rows]

    async def is_staff_role(self, guild_id: int, role_id: int) -> bool:
        if not self.pool:
            return False
        result = await self.pool.fetchrow(
            "select 1 from staff_roles where guild_id = $1 and role_id = $2",
            guild_id,
            role_id,
        )
        return result is not None
