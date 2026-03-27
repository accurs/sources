import os

from json import dumps, loads
from logging import getLogger
from typing import Any, List, Optional, Union

from asyncpg import Connection, Pool
from asyncpg import Record as DefaultRecord
from asyncpg import create_pool

log = getLogger("heist/db")


def ENCODER(self: Any) -> str:
    return dumps(self)


def DECODER(self: bytes) -> Any:
    return loads(self)


class Record(DefaultRecord):
    def __getattr__(
        self: "Record", name: Union[str, Any]
    ) -> Any:
        attr: Any = self[name]
        return attr

    def __setitem__(
        self, name: Union[str, Any], value: Any
    ) -> None:
        self.__dict__[name] = value

    def to_dict(self: "Record") -> dict[str, Any]:
        return dict(self)


class Database(Pool):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._statement_cache = {}

    async def execute(
        self,
        query: str,
        *args: Any,
        timeout: Optional[float] = None,
    ) -> str:
        if query not in self._statement_cache:
            self._statement_cache[
                query
            ] = await self.prepare(query)
        stmt = self._statement_cache[query]
        return await stmt.execute(*args, timeout=timeout)

    async def fetch(
        self,
        query: str,
        *args: Any,
        timeout: Optional[float] = None,
    ) -> List[Record]: ...

    async def fetchrow(
        self,
        query: str,
        *args: Any,
        timeout: Optional[float] = None,
    ) -> Optional[Record]: ...

    async def fetchval(
        self,
        query: str,
        *args: Any,
        timeout: Optional[float] = None,
    ) -> Optional[str | int]: ...


async def init(connection: Connection):
    await connection.set_type_codec(
        "JSONB",
        schema="pg_catalog",
        encoder=ENCODER,
        decoder=DECODER,
    )

    #try:
    #    with open("heist/shared/schemas/heist.sql", "r", encoding="UTF-8") as buffer:
    #        schema = buffer.read()
    #    await connection.execute(schema)
    #except Exception as e:
    #    log.warning(f"Schema already exists or error loading: {e}")
    
    try:
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS public.prefix (
                guild_id bigint NOT NULL,
                prefix character varying(7),
                CONSTRAINT prefix_pkey PRIMARY KEY (guild_id)
            )
        """)
    except Exception as e:
        log.warning(f"Prefix table creation error: {e}")


async def connect() -> Database:
    pool = await create_pool(
        os.getenv("DSN", ""),
        statement_cache_size=0,
        record_class=Record,
        init=init,
        min_size=2,
        max_size=5,
        max_inactive_connection_lifetime=60,
        max_queries=50000,
        command_timeout=30.0,
    )
    if not pool:
        raise RuntimeError(
            "Connection to PostgreSQL server failed!"
        )

    log.debug(
        "Connection to PostgreSQL has been established."
    )
    return pool  # type: ignore


__all__ = "Database"
