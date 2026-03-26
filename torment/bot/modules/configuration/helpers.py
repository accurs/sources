from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, overload
from datetime import datetime, UTC

from aiohttp import ClientSession
from discord import Asset, Attachment, Member, User, Embed
from discord.http import Route

if TYPE_CHECKING:
    from discord.ext.commands import Bot


@dataclass(frozen=True, slots=True)
class Profile:
    guild_avatar: Asset | None
    guild_banner: Asset | None
    bio: str | None


@dataclass(frozen=True, slots=True)
class ProfileEdit:
    actor: User
    profile: Profile
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ProfileReset:
    actor: User
    guild_id: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class AssetChange:
    actor: User
    member: Member
    old_asset: Asset | None
    new_asset: Asset | None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    reason: str | None = None


class ProfileManager:
    __slots__ = ("_bot",)

    def __init__(self, bot: "Bot") -> None:
        self._bot = bot

    async def get_profile(self, guild_id: int, member_id: int) -> Profile:
        route = Route("GET", f"/guilds/{guild_id}/members/{member_id}", guild_id=guild_id, member_id=member_id)
        _data = await self._bot.http.request(route)
        
        avatar_hash = _data.get("avatar")
        banner_hash = _data.get("banner")
        
        guild_avatar = (
            Asset._from_guild_avatar(self._bot._connection, guild_id, member_id, avatar_hash)
            if avatar_hash
            else None
        )
        guild_banner = (
            Asset._from_guild_banner(self._bot._connection, guild_id, member_id, banner_hash)
            if banner_hash
            else None
        )
        
        return Profile(
            guild_avatar=guild_avatar,
            guild_banner=guild_banner,
            bio=_data.get("bio") or None
        )

    @overload
    async def update_profile(
        self,
        guild_id: int,
        *,
        avatar: bytes | Attachment | str,
        banner: bytes | Attachment | str | None = None,
        bio: str | None = None,
    ) -> None: ...

    async def update_profile(self, guild_id: int, **fields: Any) -> None:
        processed_fields = {}
        for key, value in fields.items():
            if key in ("avatar", "banner"):
                processed_fields[key] = await self._process_image(value)
            elif key == "bio":
                processed_fields[key] = value or ""
            else:
                processed_fields[key] = value
        
        if processed_fields:
            await self._bot.http.edit_my_member(guild_id, **processed_fields)

    async def reset_profile(self, guild_id: int) -> None:
        await self._bot.http.edit_my_member(guild_id, avatar=None, banner=None, bio=None)

    async def create_profile_embed(self, ctx, profile: Profile) -> Embed | None:
        from bot.helpers.context import _color
        
        embed = Embed(
            title=f"{ctx.guild.name} Profile",
            color=_color("EMBED_INFO_COLOR")
        )
        
        has_customization = False
        
        if profile.guild_avatar:
            embed.add_field(
                name="Guild Avatar",
                value=f"[View Avatar]({profile.guild_avatar.url})",
                inline=True
            )
            embed.set_thumbnail(url=profile.guild_avatar.url)
            has_customization = True
        else:
            embed.add_field(name="Guild Avatar", value="Not set", inline=True)
        
        if profile.guild_banner:
            embed.add_field(
                name="Guild Banner",
                value=f"[View Banner]({profile.guild_banner.url})",
                inline=True
            )
            embed.set_image(url=profile.guild_banner.url)
            has_customization = True
        else:
            embed.add_field(name="Guild Banner", value="Not set", inline=True)
        
        if profile.bio:
            embed.add_field(name="Bio", value=profile.bio, inline=False)
            has_customization = True
        
        if ctx.guild.me.nick:
            embed.add_field(name="Nickname", value=ctx.guild.me.nick, inline=True)
            has_customization = True
        
        if not has_customization:
            await ctx.warn("No customizations are currently set for this server!")
            return None
        
        return embed

    async def _process_image(self, value: Any) -> str | None:
        if isinstance(value, Attachment):
            data = await value.read()
            return self._from_bytes(data)
        elif isinstance(value, bytes):
            return self._from_bytes(value)
        elif isinstance(value, str):
            if not value or not value.strip():
                return None
            async with ClientSession() as session:
                async with session.get(value) as img_resp:
                    if img_resp.status != 200:
                        raise Exception(f"Failed to fetch image from URL: {img_resp.status}")
                    data = await img_resp.read()
                    return self._from_bytes(data)
        else:
            return value

    @staticmethod
    def _from_bytes(data: bytes) -> str:
        b64 = base64.b64encode(data).decode("utf-8")
        return f"data:image/png;base64,{b64}"
