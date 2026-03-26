import aiohttp
from typing import Optional, Dict, Any
from urllib.parse import quote
from stare.core.config import Config

async def get_profile(username: str, tag: str) -> Optional[Dict[str, Any]]:
    headers = {
        'Accept': 'application/json',
        'Authorization': Config.KEYS.RIVE
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://rocks.rive.wtf/api/valorant/{quote(username)}/{quote(tag)}',
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    return None
                
                return await resp.json()
    except Exception as e:
        print(f"Valorant API error: {e}")
        return None
