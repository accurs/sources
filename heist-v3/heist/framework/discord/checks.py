from discord.ext.commands import check
from cashews import cache
from typing import TYPE_CHECKING, Optional

from .context import Context

if TYPE_CHECKING:
    from heist.framework import heist


@cache(
    ttl="3h",
    key="blacklist:{object_id}:{object_type}",
)
async def is_blacklisted(
    bot: "heist", object_id: int, object_type: str
) -> bool:
    """
    Check if a user or guild is blacklisted.
    """
    if object_type == "user":
        query = """
        SELECT 1 FROM blacklist 
        WHERE user_id = $1
        """
    
    elif object_type == "guild":
        query = """
        SELECT 1 FROM guildblacklist 
        WHERE guild_id = $1
        """
    
    else:
        query = """
        SELECT 1 FROM blacklists 
        WHERE object_id = $1 AND object_type = $2
        """
        return bool(
            await bot.pool.fetchval(
                query, object_id, object_type
            )
        )

    return bool(await bot.pool.fetchval(query, object_id))


async def add_blacklist(
    bot: "heist", object_id: int, object_type: str, reason: str = None, moderator_id: int = None
):
    """
    Add a user or guild to the blacklist.
    """
    if object_type == "user":
        await bot.pool.execute(
            """
            INSERT INTO blacklist (user_id, information, moderator, date)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                information = $2,
                moderator = $3,
                date = NOW()
            """,
            object_id, reason or "**Breaking [Heist's Terms of Service](<https://heist.lol/terms>).**", moderator_id
        )
    elif object_type == "guild":
        await bot.pool.execute(
            """
            INSERT INTO guildblacklist (guild_id, information)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET
                information = $2
            """,
            object_id, reason or "**Breaking [Heist's Terms of Service](<https://heist.lol/terms>).**"
        )
    
    await invalidate_blacklist_cache(object_id, object_type)

async def get_blacklist_reason(bot, object_id: int, object_type: str) -> Optional[str]:
    if object_type == "user":
        row = await bot.pool.fetchrow(
            "SELECT information FROM blacklist WHERE user_id=$1",
            object_id
        )
        return row["information"] if row else None

    if object_type == "guild":
        row = await bot.pool.fetchrow(
            "SELECT information FROM guildblacklist WHERE guild_id=$1",
            object_id
        )
        return row["information"] if row else None

    return None

async def remove_blacklist(
    bot: "heist", object_id: int, object_type: str
):
    """
    Remove a user or guild from the blacklist.
    """
    if object_type == "user":
        result = await bot.pool.execute(
            "DELETE FROM blacklist WHERE user_id = $1",
            object_id
        )
    elif object_type == "guild":
        result = await bot.pool.execute(
            "DELETE FROM guildblacklist WHERE guild_id = $1",
            object_id
        )
    
    await invalidate_blacklist_cache(object_id, object_type)
    return result == "DELETE 1"


async def invalidate_blacklist_cache(
    object_id: int, object_type: str
):
    """
    Invalidate the blacklist cache for a given object.
    """
    await cache.delete(f"blacklist:{object_id}:{object_type}")
