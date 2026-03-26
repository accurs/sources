from dataclasses import dataclass
from typing import Optional

@dataclass
class EdgeCount:
    count: int

@dataclass
class EdgeOwnerToTimelineMedia:
    count: int

@dataclass
class InstagramProfile:
    id: str
    username: str
    full_name: str
    profile_pic_url: str
    profile_pic_url_hd: Optional[str] = None
    biography: Optional[str] = None
    edge_followed_by: Optional[EdgeCount] = None
    edge_follow: Optional[EdgeCount] = None
    edge_owner_to_timeline_media: Optional[EdgeOwnerToTimelineMedia] = None
    is_private: bool = False
    is_verified: bool = False
    is_business_account: bool = False
    is_professional_account: bool = False
    external_url: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'InstagramProfile':
        edge_followed_by = None
        if 'edge_followed_by' in data and isinstance(data['edge_followed_by'], dict):
            edge_followed_by = EdgeCount(count=data['edge_followed_by'].get('count', 0))
        
        edge_follow = None
        if 'edge_follow' in data and isinstance(data['edge_follow'], dict):
            edge_follow = EdgeCount(count=data['edge_follow'].get('count', 0))
        
        edge_owner_to_timeline_media = None
        if 'edge_owner_to_timeline_media' in data and isinstance(data['edge_owner_to_timeline_media'], dict):
            edge_owner_to_timeline_media = EdgeOwnerToTimelineMedia(
                count=data['edge_owner_to_timeline_media'].get('count', 0)
            )
        
        return cls(
            id=str(data.get('id', '')),
            username=data.get('username', ''),
            full_name=data.get('full_name', ''),
            profile_pic_url=data.get('profile_pic_url', ''),
            profile_pic_url_hd=data.get('profile_pic_url_hd'),
            biography=data.get('biography'),
            edge_followed_by=edge_followed_by,
            edge_follow=edge_follow,
            edge_owner_to_timeline_media=edge_owner_to_timeline_media,
            is_private=data.get('is_private', False),
            is_verified=data.get('is_verified', False),
            is_business_account=data.get('is_business_account', False),
            is_professional_account=data.get('is_professional_account', False),
            external_url=data.get('external_url')
        )

