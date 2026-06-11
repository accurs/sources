from asyncpg import Pool, create_pool
from json import loads, dumps
from os import getenv
from pathlib import Path
from typing import Optional, Dict, Union


class Postgres:
    async def init(self, conn):
        await conn.set_type_codec("jsonb", encoder=dumps, decoder=loads, schema="pg_catalog")
    async def create(
        self,
        schema: bool = True,
        schema_path: Optional[Path] = None,
        credentials: Optional[Union[Dict, str]] = None,
    ) -> Pool:
        if credentials:
            creds = loads(credentials) if isinstance(credentials, str) else credentials
            pool = await create_pool(**creds)
        else:
            pool = await create_pool(
                user=getenv("database.user"),
                database=getenv("database"),
                password=getenv("database.password"),
                host=getenv("database.host"),
                port=int(getenv("database.port", 5432)),
                init=self.init
            )

        if schema and schema_path:
            if not schema_path.exists():
                raise FileNotFoundError(f"Path does not exist: {schema_path}")

            if schema_path.suffix != ".sql":
                raise ValueError("Schema file must be a .sql file")

            async with pool.acquire() as conn:
                stripped = schema_path.read_text(encoding="utf-8")
                await conn.execute(stripped)

        return pool
