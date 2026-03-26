import aiohttp
from typing import Optional, Dict, Any
from stare.core.config import Config


async def get_uuid(username: str) -> Optional[Dict[str, Any]]:
    headers = {
        'Accept': 'application/json',
        'Authorization': Config.KEYS.RIVE
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://rocks.rive.wtf/api/minecraft/uuid?username={username}',
                headers=headers
            ) as resp:
                if resp.status != 200:
                    return None
                
                return await resp.json()
    except:
        return None


async def get_profile(uuid: str) -> Optional[Dict[str, Any]]:
    headers = {
        'Accept': 'application/json',
        'Authorization': Config.KEYS.RIVE
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://rocks.rive.wtf/api/minecraft/profile?uuid={uuid}',
                headers=headers
            ) as resp:
                if resp.status != 200:
                    return None
                
                return await resp.json()
    except:
        return None


async def get_avatar(
    uuid: str,
    size: int = 128,
    overlay: bool = True,
    service: str = "mc-heads"
) -> Optional[Dict[str, Any]]:
    headers = {
        'Accept': 'application/json',
        'Authorization': Config.KEYS.RIVE
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://rocks.rive.wtf/api/minecraft/avatar?uuid={uuid}&size={size}&overlay={str(overlay).lower()}&service={service}',
                headers=headers
            ) as resp:
                if resp.status != 200:
                    return None
                
                return await resp.json()
    except:
        return None


async def get_render(
    uuid: str,
    render_type: str = "head",
    scale: int = 4,
    overlay: bool = True,
    service: str = "mc-heads"
) -> Optional[Dict[str, Any]]:
    headers = {
        'Accept': 'application/json',
        'Authorization': Config.KEYS.RIVE
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://rocks.rive.wtf/api/minecraft/render?uuid={uuid}&type={render_type}&scale={scale}&overlay={str(overlay).lower()}&service={service}',
                headers=headers
            ) as resp:
                if resp.status != 200:
                    return None
                
                return await resp.json()
    except:
        return None


async def get_full_data(username: str) -> Optional[Dict[str, Any]]:
    headers = {
        'Accept': 'application/json',
        'Authorization': Config.KEYS.RIVE
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://rocks.rive.wtf/api/minecraft/full?username={username}',
                headers=headers
            ) as resp:
                if resp.status != 200:
                    return None
                
                return await resp.json()
    except:
        return None
