import aiohttp
from typing import Optional, Dict, Any
from stare.core.config import Config

async def get_profile(username: str) -> Optional[Dict[str, Any]]:
    username = username.lstrip('@')
    
    headers = {
        'Authorization': Config.KEYS.RIVE
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://rocks.rive.wtf/api/tiktok/profile?username={username}',
                headers=headers
            ) as resp:
                if resp.status != 200:
                    return None
                
                response = await resp.json()
                
                if not response.get('success') or not response.get('data'):
                    return None
                
                return response['data']
    except:
        return None

