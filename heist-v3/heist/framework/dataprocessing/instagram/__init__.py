import asyncio
import json
import re
import urllib.parse
from typing import Dict, Optional, Any
import aiohttp
from bs4 import BeautifulSoup

class AsyncInstagramReelExtractor:
    def __init__(self, max_concurrent_requests: int = 100, max_connections: int = 1000):
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
        self.max_connections = max_connections
        self.session = None
        self.cookie_jar = None
        self._setup_headers()
        
    def _setup_headers(self):
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/jxl,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "ro-RO,ro;q=0.9",
            "Cache-Control": "no-cache",
            "Dnt": "1",
            "Dpr": "1.25",
            "Pragma": "no-cache",
            "Priority": "u=0, i",
            "Sec-Ch-Prefers-Color-Scheme": "dark",
            "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126"',
            "Sec-Ch-Ua-Full-Version-List": '"Not/A)Brand";v="8.0.0.0", "Chromium";v="126.0.6478.231"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Model": '""',
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Ch-Ua-Platform-Version": '"15.0.0"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Viewport-Width": "745",
            "cookie": "csrftoken=kCfnwVuXDnq_gxMgPZW6UC"
        }

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(
            limit=self.max_connections,
            limit_per_host=500,
            keepalive_timeout=120,
            enable_cleanup_closed=True,
            ttl_dns_cache=600,
            use_dns_cache=True
        )
        
        timeout = aiohttp.ClientTimeout(total=10, connect=3)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=self.headers
        )
        
        try:
            self.cookies = self._load_cookies_manual("./insta_cookies.txt")
        except Exception:
            self.cookies = {}
            
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def _normalize_url(self, url: str) -> tuple[str, bool]:
        match = re.match(r"https?://(?:www\.)?instagram\.com/([^/]+)/reel/([^/]+)/?", url)
        if match:
            url = f"https://www.instagram.com/reels/{match.group(2)}/"

        valid_patterns = [
            "https://instagram.com/reels/",
            "https://www.instagram.com/reels/",
            "https://www.instagram.com/reel/",
            "https://instagram.com/reel/",
            "https://instagram.com/p/",
            "https://www.instagram.com/p/",
            "https://instagram.com/tv/",
            "https://www.instagram.com/tv/"
        ]
        
        is_valid = any(url.startswith(pattern) for pattern in valid_patterns) or (match and match.group(2))
        return url, is_valid

    def _find_key_recursive(self, data: Any, target_key: str) -> Optional[Any]:
        if isinstance(data, dict):
            if target_key in data:
                return data[target_key]
            for value in data.values():
                result = self._find_key_recursive(value, target_key)
                if result is not None:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = self._find_key_recursive(item, target_key)
                if result is not None:
                    return result
        return None

    def _extract_video_info(self, media_data: Dict) -> Dict:
        down_url = media_data.get("video_versions", [{}])[0].get("url")
        if down_url:
            parsed = urllib.parse.urlparse(down_url)
            query = urllib.parse.parse_qs(parsed.query)
            media_data["extra"] = {
                "video_params": query,
                "video_url": down_url,
                "video_url_no_params": f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            }
        return media_data

    async def extract_reel(self, url: str) -> Dict[str, Any]:
        async with self.semaphore:
            normalized_url, is_valid = self._normalize_url(url)
            
            if not is_valid:
                return {
                    "error": "Invalid reel/post URL",
                    "matched": False,
                    "got": url,
                    "example": "https://www.instagram.com/reels/C7VXU3_NQj9/ or https://www.instagram.com/p/C7VXU3_NQj9/",
                    "status_code": 400
                }

            try:
                cookies = self.cookies if self.cookies else None

                async with self.session.get(normalized_url, cookies=cookies, allow_redirects=True) as response:
                    if response.status != 200:
                        return {"error": "Failed to fetch the URL", "status_code": response.status}

                    html = await response.text()
                    soup = BeautifulSoup(html, "lxml")
                    scripts = soup.find_all("script", {"type": "application/json", "data-content-len": True})

                    for script in scripts:
                        if "comment_count" in script.text:
                            data = json.loads(script.text)
                            media_data = self._find_key_recursive(data, "media")
                            
                            if media_data is not None:
                                media_data["headers"] = dict(self.headers)
                                return self._extract_video_info(media_data)

                        if "data-sjs" in script.attrs:
                            try:
                                data = json.loads(script.text)
                                bbox_data = data.get("require", [])[0][3][0].get("__bbox", {})
                                relay_data = bbox_data.get("require", [])[0][3][1].get("__bbox", {})
                                result = relay_data.get("result", {}).get("data", {})
                                items = result.get("xdt_api__v1__media__shortcode__web_info", {}).get("items", [])[0]

                                if items:
                                    items["headers"] = dict(self.headers)
                                    if items.get("video_versions"):
                                        return self._extract_video_info(items)
                                    return items
                            except Exception:
                                continue

                    return {"error": "Reel data not available", "matched": True, "status_code": 404}

            except asyncio.TimeoutError:
                return {"error": "Request timeout", "status_code": 408}
            except Exception as e:
                return {"error": f"Extraction failed: {str(e)}", "status_code": 500}

    async def extract_multiple_reels(self, urls: list[str]) -> list[Dict[str, Any]]:
        tasks = [self.extract_reel(url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def get_trending_reel(self) -> Dict[str, Any]:
        async with self.semaphore:
            url = "https://www.instagram.com/reels/"
            
            try:
                cookies = self.cookies if self.cookies else None
                async with self.session.get(url, cookies=cookies, allow_redirects=True) as response:
                    if response.status != 200:
                        return {"error": "Failed to fetch trending reels", "status_code": response.status}

                    html = await response.text()
                    soup = BeautifulSoup(html, "lxml")
                    scripts = soup.find_all("script", {"type": "application/json", "data-content-len": True})

                    for script in scripts:
                        if "comment_count" in script.text:
                            data = json.loads(script.text)
                            media_data = self._find_key_recursive(data, "media")
                            
                            if media_data is not None:
                                media_data["headers"] = dict(self.headers)
                                return self._extract_video_info(media_data)

                        if "data-sjs" in script.attrs:
                            try:
                                data = json.loads(script.text)
                                
                                media_data = self._find_key_recursive(data, "media")
                                if media_data and isinstance(media_data, dict):
                                    media_data["headers"] = dict(self.headers)
                                    return self._extract_video_info(media_data)
                                
                                items = self._find_key_recursive(data, "video_versions")
                                if items:
                                    parent_media = self._find_parent_with_video(data)
                                    if parent_media:
                                        parent_media["headers"] = dict(self.headers)
                                        return self._extract_video_info(parent_media)
                                        
                            except Exception:
                                continue

                    return {"error": "No trending reel data found", "status_code": 404}

            except asyncio.TimeoutError:
                return {"error": "Request timeout", "status_code": 408}
            except Exception as e:
                return {"error": f"Trending extraction failed: {str(e)}", "status_code": 500}

    def _find_parent_with_video(self, data: Any) -> Optional[Dict]:
        if isinstance(data, dict):
            if "video_versions" in data and "user" in data:
                return data
            for value in data.values():
                result = self._find_parent_with_video(value)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = self._find_parent_with_video(item)
                if result:
                    return result
        return None

    def _load_cookies_manual(self, filepath: str) -> dict:
        cookies = {}
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            name = parts[0]
                            value = parts[1]
                            cookies[name] = value
        except Exception:
            pass
        return cookies