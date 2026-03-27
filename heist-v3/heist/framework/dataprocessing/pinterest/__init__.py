import asyncio
import json
import re
import urllib.parse
from typing import Dict, Optional, Any, List
import aiohttp
from bs4 import BeautifulSoup
import os
from urllib.parse import quote, urlparse

class AsyncPinterestExtractor:
    def __init__(self, max_concurrent_requests: int = 100, max_connections: int = 1000):
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
        self.max_connections = max_connections
        self.session = None
        self.cookie_jar = None
        self._setup_headers()
        
    def _setup_headers(self):
        self.headers = {
            "accept": "application/json, text/javascript, */*, q=0.01",
            "accept-language": "en-US,en;q=0.9",
            "priority": "u=1, i",
            "referer": "https://ro.pinterest.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 OPR/116.0.0.0",
            "x-app-version": "c056fb7",
            "x-pinterest-appstate": "active",
            "x-pinterest-pws-handler": "www/index.js",
            "x-requested-with": "XMLHttpRequest"
        }
        self.cookies = {
            'sessionid': os.getenv('PINTEREST_SESSION_ID', ''),
            'csrftoken': os.getenv('PINTEREST_CSRF_TOKEN', ''),
            'ds_user_id': os.getenv('PINTEREST_DS_USER_ID', ''),
            'ig_did': os.getenv('PINTEREST_IG_DID', '')
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
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def search_images(self, query: str) -> List[str]:
        async with self.semaphore:
            equery = quote(query)
            api_url = f"https://ro.pinterest.com/resource/BaseSearchResource/get/?source_url=%2Fsearch%2Fpins%2F%3Fq%3D{equery}%26rs%3Dtyped&data=%7B%22options%22%3A%7B%22applied_unified_filters%22%3Anull%2C%22appliedProductFilters%22%3A%22---%22%2C%22article%22%3Anull%2C%22auto_correction_disabled%22%3Afalse%2C%22corpus%22%3Anull%2C%22customized_rerank_type%22%3Anull%2C%22domains%22%3Anull%2C%22dynamicPageSizeExpGroup%22%3A%22enabled_350_18capped%22%2C%22filters%22%3Anull%2C%22journey_depth%22%3Anull%2C%22page_size%22%3A%229%22%2C%22query%22%3A%22{equery}%22%2C%22redux_normalize_feed%22%3Atrue%2C%22scope%22%3A%22pins%22%2C%22source_url%22%3A%22%2Fsearch%2Fpins%2F%3Fq%3D{equery}%26rs%3Dtyped%22%7D%2C%22context%22%3A%7B%7D%7D&_=1734203755445"
            
            try:
                async with self.session.get(api_url, headers=self.headers, cookies=self.cookies) as response:
                    if response.status != 200:
                        return []
                    
                    data = await response.json()
                    results = data.get("resource_response", {}).get("data", {}).get("results", [])
                    return [result["images"]["orig"]["url"] for result in results if result.get("images", {}).get("orig", {}).get("url")]
            except Exception:
                return []

    async def get_pin_details(self, url: str) -> Dict[str, Any]:
        async with self.semaphore:
            try:
                parsed = urlparse(url)
                if parsed.netloc.endswith("pinterest.com") and parsed.path.startswith("/pin/"):
                    pin_id = parsed.path.split('/')[2]
                elif parsed.netloc.endswith("pin.it"):
                    pin_id = parsed.path.lstrip('/')
                else:
                    return {"error": "Invalid Pinterest URL", "status_code": 400}

                api_url = f"https://ro.pinterest.com/resource/PinResource/get/?source_url=%2Fpin%2F{pin_id}%2Ffeedback%2F%3Finvite_code%3De39cd0819eea42a9a3f54cefda573aed%26sender_id%3D547680142093334810&data=%7B%22options%22%3A%7B%22id%22%3A%22{pin_id}%22%2C%22field_set_key%22%3A%22auth_web_main_pin%22%2C%22noCache%22%3Atrue%2C%22fetch_visual_search_objects%22%3Atrue%7D%2C%22context%22%3A%7B%7D%7D&_=1733881746715"

                async with self.session.get(api_url, headers=self.headers, cookies=self.cookies) as response:
                    if response.status != 200:
                        return {"error": f"Failed to fetch pin: {response.status}", "status_code": response.status}
                    
                    data = await response.json()
                    pin_data = data['resource_response']['data']
                    creator_data = pin_data.get('pinner') or pin_data.get('origin_pinner') or {}
                    
                    return {
                        'username': creator_data.get('username', 'unknown'),
                        'fullName': creator_data.get('full_name', 'Unknown Creator'),
                        'followerCount': creator_data.get('follower_count', 0),
                        'verifiedIdentity': creator_data.get('verified_identity', {}).get('verified', False),
                        'avatar': creator_data.get('image_medium_url', ''),
                        'title': pin_data.get('title', pin_data.get('seo_title', 'No title')),
                        'reactions': pin_data.get('reaction_counts', {}).get('1', 0),
                        'image': pin_data.get('images', {}).get('orig', {}).get('url', ''),
                        'commentsCount': pin_data.get('aggregated_pin_data', {}).get('comment_count', 0),
                        'description': pin_data.get('description', pin_data.get('seo_description', 'No description')),
                        'annotations': pin_data.get('visual_objects', []),
                        'board': {
                            'name': pin_data.get('board', {}).get('name', 'Unknown Board'),
                            'description': pin_data.get('board', {}).get('description', ''),
                            'followerCount': pin_data.get('board', {}).get('follower_count', 0),
                            'id': pin_data.get('board', {}).get('id', ''),
                            'url': f"https://www.pinterest.com{pin_data.get('board', {}).get('url', '')}" if pin_data.get('board', {}).get('url') else ''
                        },
                        'createdAt': pin_data.get('created_at', ''),
                        'link': pin_data.get('link', f"https://www.pinterest.com/pin/{pin_id}"),
                        'altText': pin_data.get('auto_alt_text', 'N/A'),
                        'repinCount': pin_data.get('repin_count', 0)
                    }

            except asyncio.TimeoutError:
                return {"error": "Request timeout", "status_code": 408}
            except Exception as e:
                return {"error": f"Extraction failed: {str(e)}", "status_code": 500}