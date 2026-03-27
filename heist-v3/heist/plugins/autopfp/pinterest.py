import aiohttp
import asyncio
import random
import json
from typing import List, Optional
from urllib.parse import quote

class PinterestScraper:
    def __init__(self, config):
        self.session = None
        self.config = config

    async def get_session(self):
        if not self.session or self.session.closed:
            if self.session:
                await self.session.close()
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            )
        return self.session

    async def get_headers(self):
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://ro.pinterest.com/"
        }
    
    async def fetch_page(self, guild_id: int, user_id: int, keyword: str) -> Optional[str]:
        pagination = await self.config.get_pagination(guild_id, user_id, keyword)
        bookmark = pagination['bookmark'] if pagination else None
        page_num = pagination['page_number'] if pagination else 0
        
        session = await self.get_session()
        headers = await self.get_headers()
        
        data_params = {
            "query": keyword,
            "scope": "pins",
            "page_size": 25,
            "rs": "typed"
        }
        
        if bookmark:
            data_params["bookmarks"] = [bookmark]
        
        data_json = json.dumps({"options": data_params, "context": {}})
        timestamp = random.randint(1000000000000, 9999999999999)
        
        api_url = f"https://ro.pinterest.com/resource/BaseSearchResource/get/?source_url=%2Fsearch%2Fpins%2F%3Fq%3D{quote(keyword)}%26rs%3Dtyped&data={quote(data_json)}&_={timestamp}"
        
        try:
            async with session.get(api_url, headers=headers) as response:
                if response.status != 200:
                    return None
                    
                data = await response.json()
                resource_data = data.get('resource_response', {}).get('data', {})
                results = resource_data.get('results', [])
                new_bookmark = resource_data.get('bookmark')
                
                used_images = await self.config.pool.fetch(
                    "SELECT image_url FROM autopfp.used_images WHERE guild_id = $1 AND user_id = $2 AND keyword = $3",
                    guild_id, user_id, keyword
                )
                used_urls = {row['image_url'] for row in used_images}
                
                for result in results:
                    if result.get('is_promoted'):
                        continue
                        
                    images = result.get('images', {})
                    for size in ['orig', '736x', '564x']:
                        if size in images and 'url' in images[size]:
                            url = images[size]['url']
                            if url.startswith('https://i.pinimg.com/') and url not in used_urls:
                                await self.config.update_pagination(guild_id, user_id, keyword, new_bookmark, page_num + 1)
                                return url
                
                if new_bookmark:
                    await self.config.update_pagination(guild_id, user_id, keyword, new_bookmark, page_num + 1)
                    return await self.fetch_page(guild_id, user_id, keyword)
                    
        except Exception as e:
            print(f"[SCRAPER] Error: {e}")
            
        return None

    async def get_next_image(self, guild_id: int, user_id: int, keyword: str) -> Optional[str]:
        return await self.fetch_page(guild_id, user_id, keyword)

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None