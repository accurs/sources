from dataclasses import dataclass
from typing import Optional, List, Self

from discord import (
    User,
    Member,
    Guild,
    TextChannel,
    VoiceChannel,
    StageChannel,
    ForumChannel,
    CategoryChannel,
    Thread,
)
from discord.abc import PrivateChannel


@dataclass
class UserPayload:
    id: int
    username: str
    discriminator: str
    avatar: Optional[str]
    bot: bool
    system: Optional[bool] = False

    @classmethod
    def from_user(cls, user: User) -> Self:
        return cls(
            id=user.id,
            username=user.name,
            discriminator=user.discriminator,
            avatar=str(user.avatar)
            if user.avatar
            else None,
            bot=user.bot,
            system=getattr(user, "system", False),
        )


@dataclass
class MemberPayload:
    user: UserPayload
    nick: Optional[str]
    roles: List[int]
    joined_at: Optional[str]
    pending: Optional[bool]
    premium_since: Optional[str]
    deaf: Optional[bool]
    mute: Optional[bool]
    communication_disabled_until: Optional[str]

    @classmethod
    def from_member(cls, member: Member) -> Self:
        return cls(
            user=UserPayload.from_user(member),
            nick=member.nick,
            roles=[r.id for r in member.roles],
            joined_at=member.joined_at.isoformat()
            if member.joined_at
            else None,
            pending=member.pending,
            premium_since=(
                member.premium_since.isoformat()
                if member.premium_since
                else None
            ),
            deaf=member.deaf,
            mute=member.mute,
            communication_disabled_until=(
                member.communication_disabled_until.isoformat()
                if member.communication_disabled_until
                else None
            ),
        )


@dataclass
class GuildPayload:
    id: int
    name: str
    icon: Optional[str]
    owner_id: int
    region: Optional[str]
    member_count: int
    features: List[str]
    verification_level: str
    default_message_notifications: str

    @classmethod
    def from_guild(cls, guild: Guild) -> Self:
        return cls(
            id=guild.id,
            name=guild.name,
            icon=str(guild.icon) if guild.icon else None,
            owner_id=guild.owner_id,
            region=str(guild.region)
            if hasattr(guild, "region")
            else None,
            member_count=guild.member_count,
            features=guild.features,
            verification_level=guild.verification_level.name,
            default_message_notifications=guild.default_notifications.name,
        )


@dataclass
class TextChannelPayload:
    id: int
    name: str
    position: int
    topic: Optional[str]
    nsfw: bool
    category_id: Optional[int]
    type: str
    slowmode_delay: int

    @classmethod
    def from_text_channel(
        cls, channel: TextChannel
    ) -> Self:
        return cls(
            id=channel.id,
            name=channel.name,
            position=channel.position,
            topic=channel.topic,
            nsfw=channel.nsfw,
            category_id=channel.category_id,
            type=channel.type.name,
            slowmode_delay=channel.slowmode_delay,
        )


@dataclass
class VoiceChannelPayload:
    id: int
    name: str
    position: int
    bitrate: int
    user_limit: int
    category_id: Optional[int]
    type: str

    @classmethod
    def from_voice_channel(
        cls, channel: VoiceChannel
    ) -> Self:
        return cls(
            id=channel.id,
            name=channel.name,
            position=channel.position,
            bitrate=channel.bitrate,
            user_limit=channel.user_limit,
            category_id=channel.category_id,
            type=channel.type.name,
        )


@dataclass
class StageChannelPayload:
    id: int
    name: str
    position: int
    bitrate: int
    user_limit: int
    category_id: Optional[int]
    type: str

    @classmethod
    def from_stage_channel(
        cls, channel: StageChannel
    ) -> Self:
        return cls(
            id=channel.id,
            name=channel.name,
            position=channel.position,
            bitrate=channel.bitrate,
            user_limit=channel.user_limit,
            category_id=channel.category_id,
            type=channel.type.name,
        )


@dataclass
class ForumChannelPayload:
    id: int
    name: str
    position: int
    nsfw: bool
    category_id: Optional[int]
    type: str

    @classmethod
    def from_forum_channel(
        cls, channel: ForumChannel
    ) -> Self:
        return cls(
            id=channel.id,
            name=channel.name,
            position=channel.position,
            nsfw=channel.nsfw,
            category_id=channel.category_id,
            type=channel.type.name,
        )


@dataclass
class CategoryChannelPayload:
    id: int
    name: str
    position: int
    type: str

    @classmethod
    def from_category_channel(
        cls, channel: CategoryChannel
    ) -> Self:
        return cls(
            id=channel.id,
            name=channel.name,
            position=channel.position,
            type=channel.type.name,
        )


@dataclass
class ThreadPayload:
    id: int
    name: str
    type: str
    owner_id: int
    parent_id: int
    archived: bool
    locked: bool
    auto_archive_duration: int
    rate_limit_per_user: int

    @classmethod
    def from_thread(cls, thread: Thread) -> Self:
        return cls(
            id=thread.id,
            name=thread.name,
            type=thread.type.name,
            owner_id=thread.owner_id,
            parent_id=thread.parent_id,
            archived=thread.archived,
            locked=thread.locked,
            auto_archive_duration=thread.auto_archive_duration,
            rate_limit_per_user=thread.rate_limit_per_user,
        )


@dataclass
class PrivateChannelPayload:
    id: int
    type: str
    recipients: List[UserPayload]

    @classmethod
    def from_private_channel(
        cls, channel: PrivateChannel
    ) -> Self:
        return cls(
            id=channel.id,
            type=channel.type.name,
            recipients=[
                UserPayload.from_user(u)
                for u in channel.recipients
            ],
        )
