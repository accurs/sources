from redis.asyncio import Redis as Base, from_url
from json import loads
from os import getenv
from typing import Optional, Dict, Union


class Redis:
    async def create(self, credentials: Optional[Union[Dict, str]] = None) -> Base:
        if credentials:
            creds = loads(credentials) if isinstance(credentials, str) else credentials
            return from_url(**creds) if "url" in creds else Base(**creds)

        url = getenv("redis.url")
        if url:
            return from_url(url)

        return Base(
            host=getenv("redis.host", "127.0.0.1"),
            port=int(getenv("redis.port", 6379)),
            decode_responses=True,
        )
