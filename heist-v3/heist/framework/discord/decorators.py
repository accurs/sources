import functools
from typing import Callable, Any
from discord.ext import commands
from discord import Interaction, Embed, app_commands
from cashews import cache
from typing import TYPE_CHECKING
import discord
import io
from heist.framework.discord.commands import CommandCache
from heist.framework.tools.separator import makeseparator

if TYPE_CHECKING:
    from heist.framework import heist

async def check_donor(bot, user_id: int) -> bool:
    redis_key = f"donor:{user_id}"
    try:
        cached = await bot.redis.get(redis_key)
        if isinstance(cached, bytes):
            cached = cached.decode()
    except Exception:
        cached = None
    if cached is not None:
        return cached == "True"
    try:
        async with bot.pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1 FROM donors WHERE user_id = $1", str(user_id))
    except Exception:
        return False
    is_donor = bool(result)
    await bot.redis.set(redis_key, str(is_donor), ex=300)
    return is_donor

async def check_famous(bot, user_id: int) -> bool:
    redis_key = f"famous:{user_id}"
    cached = await bot.redis.get(redis_key)
    if isinstance(cached, bytes):
        cached = cached.decode()
    if cached is not None:
        return cached == "True"
    async with bot.pool.acquire() as conn:
        result = await conn.fetchval("SELECT fame FROM user_data WHERE user_id = $1", str(user_id))
        is_famous = bool(result)
        await bot.redis.set(redis_key, str(is_famous), ex=300)
        return is_famous

async def check_owner(bot, user_id: int) -> bool:
    return user_id in getattr(bot, "owner_ids", [])

@cache(ttl="3h", key="blacklist:{object_id}:{object_type}")
async def check_blacklisted(bot, object_id: int, object_type: str = "user") -> bool:
    if object_type == "user":
        query = "SELECT 1 FROM blacklist WHERE user_id = $1"
        return bool(await bot.pool.fetchval(query, object_id))
    elif object_type == "guild":
        query = "SELECT 1 FROM guildblacklist WHERE guild_id = $1"
        return bool(await bot.pool.fetchval(query, object_id))
    else:
        query = "SELECT 1 FROM blacklists WHERE object_id = $1 AND object_type = $2"
        return bool(await bot.pool.fetchval(query, object_id, object_type))

async def register_user(bot, discord_id: int, username: str, displayname: str) -> None:
    redis_key = f"user:{discord_id}:exists"
    user_exists_in_cache = await bot.redis.get(redis_key)
    if not user_exists_in_cache:
        async with bot.pool.acquire() as conn:
            user_exists = await conn.fetchval("SELECT 1 FROM user_data WHERE user_id = $1", str(discord_id))
            if not user_exists:
                await conn.execute(
                    """
                    INSERT INTO user_data (user_id, username, displayname)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id) DO NOTHING
                """,
                    str(discord_id),
                    username,
                    displayname,
                )
                await bot.redis.set(f"user:{discord_id}:limited", "", ex=7 * 24 * 60 * 60)
                await bot.redis.set(f"user:{discord_id}:untrusted", "", ex=60 * 24 * 60 * 60)
                await bot.redis.set(redis_key, "1", ex=600)

async def _make_embed(bot, color, description: str, user=None):
    embed = Embed(description=description, color=color)
    if user:
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    file = None
    try:
        sep_bytes = await makeseparator(bot, user.id if user else 0)
        file = discord.File(io.BytesIO(sep_bytes), filename="separator.png")
        embed.set_image(url="attachment://separator.png")
    except Exception:
        pass
    return embed, file

def universal_check(predicate_ctx, predicate_inter):
    def decorator(func):
        return app_commands.check(predicate_inter)(commands.check(predicate_ctx)(func))
    return decorator

async def get_text(bot, text_type: str) -> str:
    if text_type == "premium":
        try:
            premiumbuy = await CommandCache.get_mention(bot, "premium buy")
        except Exception:
            premiumbuy = "/premium buy"
        return (
            f"{bot.config.emojis.context.premium} This is a **premium-only** command.\n"
            "-# **Heist Premium** is **$3.99** monthly or a one-time **$8.99** purchase - "
            f"{premiumbuy}"
        )
    if text_type == "owner":
        return f"{bot.config.emojis.context.warn} This command is only available to Heist's **owners**."
    return ""

def donor_only():
    async def ctx_check(ctx: commands.Context):
        is_donor = await check_donor(ctx.bot, ctx.author.id)
        if not is_donor:
            text = await get_text(ctx.bot, "premium")
            embed, file = await _make_embed(ctx.bot, await ctx.bot.get_color(ctx.author.id), text, ctx.author)
            await ctx.send(embed=embed, file=file)
            return False
        return True

    async def inter_check(inter: Interaction):
        is_donor = await check_donor(inter.client, inter.user.id)
        if not is_donor:
            text = await get_text(inter.client, "premium")
            embed, file = await _make_embed(inter.client, await inter.client.get_color(inter.user.id), text, inter.user)
            if inter.response.is_done():
                await inter.followup.send(embed=embed, file=file, ephemeral=True)
            else:
                await inter.response.send_message(embed=embed, file=file, ephemeral=True)
            raise app_commands.CheckFailure()
        return True

    return universal_check(ctx_check, inter_check)

def famous_only():
    async def ctx_check(ctx: commands.Context):
        is_famous = await check_famous(ctx.bot, ctx.author.id)
        if not is_famous:
            embed, file = await _make_embed(ctx.bot, await ctx.bot.get_color(ctx.author.id), "This command is only available to famous users.", ctx.author)
            await ctx.send(embed=embed, file=file)
            return False
        return True

    async def inter_check(inter: Interaction):
        is_famous = await check_famous(inter.client, inter.user.id)
        if not is_famous:
            embed, file = await _make_embed(inter.client, await inter.client.get_color(inter.user.id), "This command is only available to famous users.", inter.user)
            if inter.response.is_done():
                await inter.followup.send(embed=embed, file=file, ephemeral=True)
            else:
                await inter.response.send_message(embed=embed, file=file, ephemeral=True)
            raise app_commands.CheckFailure()
        return True

    return universal_check(ctx_check, inter_check)

def owner_only():
    async def ctx_check(ctx: commands.Context):
        is_owner = await check_owner(ctx.bot, ctx.author.id)
        if not is_owner:
            text = await get_text(ctx.bot, "owner")
            embed, file = await _make_embed(ctx.bot, await ctx.bot.get_color(ctx.author.id), text, ctx.author)
            await ctx.send(embed=embed, file=file)
            return False
        return True

    async def inter_check(inter: Interaction):
        is_owner = await check_owner(inter.client, inter.user.id)
        if not is_owner:
            text = await get_text(inter.client, "owner")
            embed, file = await _make_embed(inter.client, await inter.client.get_color(inter.user.id), text, inter.user)
            if inter.response.is_done():
                await inter.followup.send(embed=embed, file=file, ephemeral=True)
            else:
                await inter.response.send_message(embed=embed, file=file, ephemeral=True)
            raise app_commands.CheckFailure()
        return True

    return universal_check(ctx_check, inter_check)

def disabled():
    async def ctx_check(ctx: commands.Context):
        embed, file = await _make_embed(ctx.bot, await ctx.bot.get_color(ctx.author.id), f"{ctx.bot.config.emojis.context.warn} Command has been temporarily disabled.", ctx.author)
        await ctx.send(embed=embed, file=file)
        return False

    async def inter_check(inter: Interaction):
        embed, file = await _make_embed(inter.client, await inter.client.get_color(inter.user.id), f"{inter.client.config.emojis.context.warn} Command has been temporarily disabled so we can make it even better for you.", inter.user)
        if inter.response.is_done():
            await inter.followup.send(embed=embed, file=file, ephemeral=True)
        else:
            await inter.response.send_message(embed=embed, file=file, ephemeral=True)
        raise app_commands.CheckFailure()

    return universal_check(ctx_check, inter_check)

async def reset_cache(user_id: int, bot) -> None:
    keys = [
        f"owner:{user_id}",
        f"blacklist:{user_id}:user",
        f"donor:{user_id}",
        f"booster:{user_id}",
        f"famous:{user_id}",
        f"premium_tokens:{user_id}",
    ]
    try:
        await bot.redis.delete(*keys)
    except Exception:
        for key in keys:
            try:
                await bot.redis.delete(key)
            except Exception:
                continue

__all__ = (
    "check_donor",
    "check_famous",
    "check_owner",
    "check_blacklisted",
    "register_user",
    "donor_only",
    "famous_only",
    "owner_only",
    "reset_cache",
)
