import asyncio
from typing import Dict, Any, Optional, List
from .helpers.browser import FastBrowser
from .helpers.cache import FastCache
from .instagram import AsyncInstagramReelExtractor
from .tiktok import AsyncTikTokExtractor
from .telegram import AsyncTelegramExtractor
from .pinterest import AsyncPinterestExtractor
import os

class DataProcessingSystem:
    def __init__(self):
        self.browser = FastBrowser()
        self.cache = FastCache(max_size=50000, ttl=1800)
        self.instagram = None
        self.tiktok = None
        self.telegram = None
        self.pinterest = None
        self._initialized = False
        
    async def initialize(self):
        if self._initialized:
            return
            
        await self.browser.initialize()
        self.instagram = AsyncInstagramReelExtractor()
        self.tiktok = AsyncTikTokExtractor()
        self.pinterest = AsyncPinterestExtractor()
        
        if os.getenv('TELEGRAM_API_ID'):
            self.telegram = AsyncTelegramExtractor()
            
        self._initialized = True
        
    async def process_instagram(self, url: str, use_cache: bool = True) -> Dict[str, Any]:
        cache_key = f"instagram:{url}"
        
        if use_cache:
            cached = await self.cache.get(cache_key)
            if cached:
                return cached
                
        async with self.instagram as extractor:
            result = await extractor.extract_reel(url)
            
        if use_cache and "error" not in result:
            await self.cache.set(cache_key, result)
            
        return result
        
    async def process_instagram_trending(self) -> Dict[str, Any]:
        if not self.instagram:
            self.instagram = AsyncInstagramReelExtractor()
        async with self.instagram as extractor:
            return await extractor.get_trending_reel()
        
    async def process_tiktok(self, url: str, use_cache: bool = True) -> Dict[str, Any]:
        cache_key = f"tiktok:{url}"
        
        if use_cache:
            cached = await self.cache.get(cache_key)
            if cached:
                return cached
                
        async with self.tiktok as extractor:
            result = await extractor.extract_video(url)
            
        if use_cache and "error" not in result:
            await self.cache.set(cache_key, result)
            
        return result
        
    async def process_tiktok_user(self, username: str, use_cache: bool = True) -> Dict[str, Any]:
        cache_key = f"tiktok_user:{username}"
        
        if use_cache:
            cached = await self.cache.get(cache_key)
            if cached:
                return cached
                
        async with self.tiktok as extractor:
            result = await extractor.get_user(username)
            
        if use_cache and "error" not in result:
            await self.cache.set(cache_key, result)
            
        return result
        
    async def process_telegram_user(self, username: str, use_cache: bool = True) -> Dict[str, Any]:
        if not self.telegram:
            return {"error": "Telegram not configured"}
            
        cache_key = f"telegram_user:{username}"
        
        if use_cache:
            cached = await self.cache.get(cache_key)
            if cached:
                return cached
                
        async with self.telegram as extractor:
            result = await extractor.extract_user(username)
            
        if use_cache and "error" not in result:
            await self.cache.set(cache_key, result)
            
        return result

    async def process_pinterest_search(self, query: str, use_cache: bool = True) -> List[str]:
        cache_key = f"pinterest_search:{query}"
        
        if use_cache:
            cached = await self.cache.get(cache_key)
            if cached:
                return cached
                
        if not self.pinterest:
            self.pinterest = AsyncPinterestExtractor()
            
        async with self.pinterest as extractor:
            result = await extractor.search_images(query)
            
        if use_cache and result:
            await self.cache.set(cache_key, result)
            
        return result

    async def process_pinterest_pin(self, url: str, use_cache: bool = True) -> Dict[str, Any]:
        cache_key = f"pinterest_pin:{url}"
        
        if use_cache:
            cached = await self.cache.get(cache_key)
            if cached:
                return cached
                
        if not self.pinterest:
            self.pinterest = AsyncPinterestExtractor()
            
        async with self.pinterest as extractor:
            result = await extractor.get_pin_details(url)
            
        if use_cache and "error" not in result:
            await self.cache.set(cache_key, result)
            
        return result
        
    async def process_batch(self, urls: List[str], platform: str) -> List[Dict[str, Any]]:
        if platform == "instagram":
            async with self.instagram as extractor:
                return await extractor.extract_multiple_reels(urls)
        elif platform == "tiktok":
            async with self.tiktok as extractor:
                return await extractor.extract_multiple_videos(urls)
        elif platform == "telegram":
            if not self.telegram:
                return [{"error": "Telegram not configured", "status_code": 400} for _ in urls]
            async with self.telegram as extractor:
                return await extractor.extract_multiple_users(urls)
        elif platform == "pinterest":
            if not self.pinterest:
                self.pinterest = AsyncPinterestExtractor()
            async with self.pinterest as extractor:
                tasks = [extractor.get_pin_details(url) for url in urls]
                return await asyncio.gather(*tasks, return_exceptions=True)
        else:
            return [{"error": "Unsupported platform", "status_code": 400} for _ in urls]
            
    async def clear_cache(self):
        await self.cache.clear()
        
    async def get_cache_stats(self) -> Dict[str, Any]:
        return {
            "size": len(self.cache.cache),
            "max_size": self.cache.max_size,
            "ttl": self.cache.ttl
        }
        
    async def shutdown(self):
        await self.browser.close()
        await self.cache.clear()
        if self.telegram:
            await self.telegram.shutdown()
        
cp_system = DataProcessingSystem()