from dataclasses import dataclass
from typing import Optional

@dataclass
class ValorantCard:
    large: Optional[str] = None
    wide: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'ValorantCard':
        return cls(
            large=data.get('large'),
            wide=data.get('wide')
        )

@dataclass
class ValorantProfile:
    name: str
    tag: str
    region: str
    puuid: str
    account_level: int
    card: Optional[ValorantCard] = None
    rank: Optional[int] = None
    rank_rating: Optional[int] = None
    elo: Optional[int] = None
    rank_image: Optional[str] = None
    status: Optional[str] = None
    tracker_url: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'ValorantProfile':
        card = None
        if 'card' in data and isinstance(data['card'], dict):
            card = ValorantCard.from_dict(data['card'])
        
        return cls(
            name=data.get('name', ''),
            tag=data.get('tag', ''),
            region=data.get('region', ''),
            puuid=data.get('puuid', ''),
            account_level=data.get('accountLevel', 0),
            card=card,
            rank=data.get('rank'),
            rank_rating=data.get('rankRating'),
            elo=data.get('elo'),
            rank_image=data.get('rankImage'),
            status=data.get('status'),
            tracker_url=data.get('trackerUrl')
        )
