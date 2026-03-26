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
                f'https://rocks.rive.wtf/api/instagram/profile?username={username}',
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    return None
                
                response = await resp.json()
                
                if 'data' in response and 'user' in response['data']:
                    return response['data']['user']
                
                return None
    except Exception as e:
        print(f"Instagram API error: {e}")
        return None
