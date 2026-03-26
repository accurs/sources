import aiohttp
from typing import Optional, Dict, Any
from stare.core.config import Config

async def get_verse(translation: str = "web") -> Optional[Dict[str, Any]]:
    headers = {
        'Accept': 'application/json',
        'Authorization': Config.KEYS.RIVE
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://rocks.rive.wtf/api/bible?translation={translation}',
                headers=headers
            ) as resp:
                if resp.status != 200:
                    return None
                
                return await resp.json()
    except:
        return None

