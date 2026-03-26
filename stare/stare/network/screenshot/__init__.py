import aiohttp
import asyncio
from typing import Optional, Dict, Any
from stare.core.config import Config

async def capture_screenshot(
    url: str,
    width: int = 1920,
    height: int = 1080,
    fullpage: bool = False,
    format: str = "png"
) -> Optional[Dict[str, Any]]:
  
    params = {
        'access_key': 'd24a3f9bc82346618e86dea8453e841c',
        'url': url,
        'width': width,
        'height': height,
        'format': format,
        'full_page': 'true' if fullpage else 'false'
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                'https://api.apiflash.com/v1/urltoimage',
                params=params,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"Screenshot API error: {resp.status} - {error_text}")
                    return None
                
                image_bytes = await resp.read()
                
                if not image_bytes or len(image_bytes) == 0:
                    print("Screenshot API returned empty response")
                    return None
                
                return {
                    'url': url,
                    'screenshot': image_bytes,
                    'width': str(width),
                    'height': str(height),
                    'format': format
                }
    except asyncio.TimeoutError:
        print("Screenshot API timeout")
        return None
    except Exception as e:
        print(f"Screenshot API exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
