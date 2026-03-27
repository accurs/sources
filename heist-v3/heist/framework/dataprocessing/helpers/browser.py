import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from typing import Optional, Dict, Any

class FastBrowser:
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        
    async def initialize(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--disable-gpu',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding'
            ]
        )
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        
    async def get_page(self) -> Page:
        return await self.context.new_page()
        
    async def fetch_content(self, url: str, wait_for: Optional[str] = None) -> Dict[str, Any]:
        page = await self.get_page()
        try:
            await page.goto(url, wait_until='networkidle')
            if wait_for:
                await page.wait_for_selector(wait_for)
            content = await page.content()
            return {'content': content, 'url': page.url}
        finally:
            await page.close()
            
    async def close(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()