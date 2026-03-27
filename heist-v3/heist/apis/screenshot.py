from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from playwright.async_api import async_playwright
import uvloop
import asyncio
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import io, os
from dotenv import load_dotenv

load_dotenv()

PROXY = os.getenv("PROXY")

app = FastAPI()
_browser = None
_playwright = None

def parse_proxy(proxy_str):
    creds, server = proxy_str.split('@')
    username, password = creds.split(':')
    server_url = f"http://{server}"
    return {
        "server": server_url,
        "username": username,
        "password": password,
    }

async def get_browser():
    global _browser, _playwright
    if not _browser:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--disable-setuid-sandbox',
            ]
        )
    return _browser

@app.on_event("startup")
async def startup_browser():
    await get_browser()

@app.on_event("shutdown")
async def shutdown_browser():
    global _browser, _playwright
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None

@app.get("/screenshot")
async def take_screenshot(url: str = Query(...), delay: int = Query(0)):
    if delay > 15:
        raise HTTPException(status_code=400, detail="Delay cannot be more than 15 seconds.")
    proxy_config = parse_proxy(PROXY) if PROXY else None
    browser = await get_browser()
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        java_script_enabled=True,
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        proxy=proxy_config
    )
    page = await context.new_page()
    await page.goto(url, wait_until="domcontentloaded", timeout=10000)
    if delay:
        await asyncio.sleep(delay)
    screenshot_bytes = await page.screenshot(type="png", full_page=True)
    await context.close()
    return StreamingResponse(io.BytesIO(screenshot_bytes), media_type="image/png")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5008)
