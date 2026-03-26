import aiohttp
from typing import Optional, Dict, Any, List
from urllib.parse import quote
from stare.core.config import Config

async def get_profile(username: str) -> Optional[Dict[str, Any]]:
    headers = {
        'Authorization': Config.KEYS.RIVE
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://rocks.rive.wtf/api/roblox/{quote(username)}',
                headers=headers
            ) as resp:
                if resp.status != 200:
                    return None
                
                return await resp.json()
    except:
        return None

async def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://users.roblox.com/v1/users/search?keyword={quote(username)}&limit=1'
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if data.get('data') and len(data['data']) > 0:
                    return data['data'][0]
                return None
    except:
        return None

async def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://users.roblox.com/v1/users/{user_id}'
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
    except:
        return None

async def get_user_groups(user_id: int) -> Optional[List[Dict[str, Any]]]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://groups.roblox.com/v2/users/{user_id}/groups/roles'
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get('data', [])
    except:
        return None

async def get_user_badges(user_id: int) -> Optional[List[Dict[str, Any]]]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://badges.roblox.com/v1/users/{user_id}/badges?limit=25&sortOrder=Asc'
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get('data', [])
    except:
        return None

async def get_rolimons_data(user_id: int) -> Optional[Dict[str, Any]]:
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://api.rolimons.com/players/v1/playerassets/{user_id}',
                headers=headers
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if isinstance(data, dict) and data.get('success') is True:
                    return data
                return None
    except Exception as e:
        return None

