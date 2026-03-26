from dataclasses import dataclass
from typing import Optional

@dataclass
class CashAppResponse:
    url: str
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CashAppResponse':
        return cls(
            url=data.get('url', '')
        )
