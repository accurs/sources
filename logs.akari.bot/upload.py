from typing import Any, Dict, List, Optional

import aiohttp
import discord
from discord import DMChannel, Member, Message, TextChannel
from orjson import dumps as dump
from orjson import loads as load
from pydantic import BaseModel
from xxhash import xxh3_64_hexdigest as hash


class LogAuthor(BaseModel):
    id: str
    name: str
    discriminator: str
    avatar_url: str
    mod: bool


class LogAttachment(BaseModel):
    id: int
    filename: str
    is_image: bool
    size: int
    url: str


class LogEntry(BaseModel):
    timestamp: str
    message_id: int
    author: LogAuthor
    content: str
    type: str
    attachments: Optional[List[LogAttachment]]


class TicketAuthor(BaseModel):
    id: int
    name: str
    discriminator: str
    avatar_url: str


class TicketLogs(BaseModel):
    guild_id: int
    channel_id: int
    author: TicketAuthor
    logs: list[LogEntry]


class Logs:
    def __init__(self, bot):
        self.bot = bot
        self.logs = {}
        self.base_url = f"https://logs.pretend.cc/logs/"

    def serialize_message(self, message: discord.Message) -> LogEntry:
        data = {
            "timestamp": str(message.created_at),
            "message_id": message.id,
            "author": {
                "id": str(message.author.id),
                "name": message.author.name,
                "discriminator": message.author.discriminator,
                "avatar_url": message.author.display_avatar.url,
                "mod": not isinstance(message.channel, DMChannel),
            },
            "content": message.content,
            "type": "thread_message",
            "attachments": [
                {
                    "id": a.id,
                    "filename": a.filename,
                    "is_image": a.width is not None,
                    "size": a.size,
                    "url": a.url,
                }
                for a in message.attachments
            ],
        }
        return LogEntry(**data)

    async def upload(
        self, channel: discord.TextChannel, ticketauthor: TicketAuthor
    ) -> str:
        messages = [
            self.serialize_message(a)
            async for a in channel.history(limit=None)
            if a.author.id != self.bot.user.id
        ]
        data = {
            "guild_id": channel.guild.id,
            "channel_id": channel.id,
            "author": ticketauthor,
            "logs": messages,
        }
        logs = TicketLogs(**data)
        key = hash(f"{channel.guild.id}-{channel.id}")
        await self.bot.db.execute(
            """INSERT INTO logs (key, guild_id, channel_id, author, logs) VALUES ($1, $2, $3, $4, $5)""",
            key,
            channel.guild.id,
            channel.id,
            ticketauthor.json(),
            logs.json(),
        )
        return f"{self.base_url}{key}"

    async def delete(self, key: str):
        await self.bot.db.execute("""DELETE FROM logs WHERE key = $1""", key)
        return True

    async def clear(self, guild_id: Optional[int] = None):
        if guild_id:
            await self.bot.db.execute(
                """DELETE FROM logs WHERE guild_id = $1""", guild_id
            )
        else:
            await self.bot.db.execute("""DELETE FROM logs""")
        return True

    async def get(self, key: str) -> Optional[str]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}{key}") as resp:
                    if resp.status == 200:
                        return resp.url
                    else:
                        return None
        except:
            return None
