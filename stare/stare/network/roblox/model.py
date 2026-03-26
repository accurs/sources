from dataclasses import dataclass
from typing import Optional

@dataclass
class RobloxProfile:
    id: int
    name: str
    display_name: str
    avatar: str
    created: str
    has_verified_badge: bool = False
    presence: Optional[str] = None
    friends: Optional[int] = None
    followers: Optional[int] = None
    items: Optional[int] = None
    rap: Optional[int] = None
    value: Optional[int] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'RobloxProfile':
        return cls(
            id=int(data.get('id', 0)),
            name=data.get('name', ''),
            display_name=data.get('displayName', ''),
            avatar=data.get('avatar', ''),
            created=data.get('created', ''),
            has_verified_badge=data.get('hasVerifiedBadge', False),
            presence=data.get('presence'),
            friends=data.get('friends'),
            followers=data.get('followers'),
            items=data.get('items'),
            rap=data.get('rap'),
            value=data.get('value')
        )

