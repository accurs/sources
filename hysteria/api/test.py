import asyncio
from playwright.async_api import async_playwright
import aiohttp

async def get_tokens(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url)
        msToken = await page.evaluate("window.__INIT_PROPS__?.msToken || ''")
        verifyFp = await page.evaluate("window.__INIT_PROPS__?.verifyFp || ''")
        x_bogus = await page.evaluate("""() => {
            let req = performance.getEntriesByType('resource').find(r => r.name.includes('/webcast/feed'));
            return req ? req.name.match(/X-Bogus=([^&]+)/)?.[1] || '' : '';
        }""")
        device_id = await page.evaluate("window.device_id || ''")
        cookies = await page.context.cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        await browser.close()
        return msToken, verifyFp, x_bogus, device_id, cookie_str

async def fetch_stories(msToken, verifyFp, x_bogus, device_id, cookie_str):
    url = "https://webcast.tiktok.com/webcast/feed/"
    params = {
        "channel_id": "42",
        "content_type": "1",
        "device_id": device_id,
        "msToken": msToken,
        "verifyFp": verifyFp,
        "X-Bogus": x_bogus
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "Referer": url,
        "Cookie": cookie_str
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers) as resp:
            return await resp.json()

async def main():
    msToken, verifyFp, x_bogus, device_id, cookie_str = await get_tokens("https://www.tiktok.com/@csynholic")
    stories = await fetch_stories(msToken, verifyFp, x_bogus, device_id, cookie_str)
    print(stories)

asyncio.run(main())
