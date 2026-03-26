from dataclasses import dataclass
from typing import Optional, List

@dataclass
class TikTokUser:
    id: str
    unique_id: str
    nickname: str
    signature: Optional[str] = None
    avatar_larger: Optional[str] = None
    avatar_medium: Optional[str] = None
    avatar_thumb: Optional[str] = None
    verified: bool = False
    sec_uid: Optional[str] = None
    create_time: Optional[int] = None
    private_account: bool = False
    secret: bool = False
    language: Optional[str] = None
    is_embed_banned: bool = False
    can_exp_playlist: bool = False
    profile_embed_permission: Optional[int] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'TikTokUser':
        return cls(
            id=str(data.get('id', '')),
            unique_id=data.get('uniqueId', ''),
            nickname=data.get('nickname', ''),
            signature=data.get('signature'),
            avatar_larger=data.get('avatarLarger'),
            avatar_medium=data.get('avatarMedium'),
            avatar_thumb=data.get('avatarThumb'),
            verified=data.get('verified', False),
            sec_uid=data.get('secUid'),
            create_time=data.get('createTime'),
            private_account=data.get('privateAccount', False),
            secret=data.get('secret', False),
            language=data.get('language'),
            is_embed_banned=data.get('isEmbedBanned', False),
            can_exp_playlist=data.get('canExpPlaylist', False),
            profile_embed_permission=data.get('profileEmbedPermission')
        )

@dataclass
class TikTokStats:
    follower_count: int = 0
    following_count: int = 0
    heart: int = 0
    heart_count: int = 0
    video_count: int = 0
    digg_count: int = 0
    friend_count: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> 'TikTokStats':
        return cls(
            follower_count=data.get('followerCount', 0),
            following_count=data.get('followingCount', 0),
            heart=data.get('heart', 0),
            heart_count=data.get('heartCount', 0),
            video_count=data.get('videoCount', 0),
            digg_count=data.get('diggCount', 0),
            friend_count=data.get('friendCount', 0)
        )

@dataclass
class TikTokShareMeta:
    title: Optional[str] = None
    desc: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'TikTokShareMeta':
        return cls(
            title=data.get('title'),
            desc=data.get('desc')
        )

@dataclass
class TikTokProfile:
    user: TikTokUser
    stats: TikTokStats
    social_links: Optional[List[str]] = None
    region: Optional[str] = None
    share_meta: Optional[TikTokShareMeta] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'TikTokProfile':
        user = TikTokUser.from_dict(data.get('user', {}))
        stats = TikTokStats.from_dict(data.get('stats', {}))
        
        share_meta = None
        if 'shareMeta' in data and isinstance(data['shareMeta'], dict):
            share_meta = TikTokShareMeta.from_dict(data['shareMeta'])
        
        return cls(
            user=user,
            stats=stats,
            social_links=data.get('social_links', []),
            region=data.get('region'),
            share_meta=share_meta
        )

