import aiohttp
from typing import Optional, Dict, Any, Union
from dataclasses import dataclass
from stare.core.config import Config


@dataclass
class CashAppResponse:
    url: str
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CashAppResponse':
        return cls(
            url=data.get('url', '')
        )


async def get_cashapp(username: str) -> Optional[Dict[str, Any]]:
    """Get CashApp URL as JSON"""
    headers = {
        'Accept': 'application/json',
        'Authorization': Config.KEYS.RIVE
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://rocks.rive.wtf/api/cashapp?username={username}',
                headers=headers
            ) as resp:
                if resp.status != 200:
                    return None
                
                return await resp.json()
    except:
        return None


async def get_cashapp_qr(username: str) -> Optional[bytes]:
    """Get CashApp QR code as PNG bytes"""
    headers = {
        'Accept': 'image/png',
        'Authorization': Config.KEYS.RIVE
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://rocks.rive.wtf/api/cashapp?username={username}&format=png',
                headers=headers
            ) as resp:
                if resp.status != 200:
                    return None
                
                content_type = resp.headers.get('Content-Type', '')
                if 'image' not in content_type:
                    return None
                
                return await resp.read()
    except:
        return None
