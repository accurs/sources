import asyncio
import hashlib
from fastapi import FastAPI, File, UploadFile, HTTPException
from playwright.async_api import async_playwright
from aiocache import cached
from aiocache.serializers import JsonSerializer

app = FastAPI()

def generate_cache_key(image_data: bytes) -> str:
    return hashlib.md5(image_data).hexdigest()

@cached(ttl=3600, serializer=JsonSerializer())
async def scrape_picarta_bytes(image_data: bytes, cache_key: str):
    retries = 2
    for attempt in range(retries):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto('https://picarta.ai', timeout=60000)
                await page.click('#upload-btn')
                await page.set_input_files('input[type="file"]', files=[{
                    'name': 'image.png',
                    'mimeType': 'image/png',
                    'buffer': image_data
                }])
                await page.wait_for_selector('#find-location-globally-button span.common-btn.classify-btn', state='visible')
                await page.click('#find-location-globally-button span.common-btn.classify-btn')
                try:
                    await page.wait_for_function(
                        '''() => {
                            const msg = document.querySelector("#no-quota-message");
                            return msg && window.getComputedStyle(msg).display !== "none";
                        }''',
                        timeout=35000,
                        polling=500
                    )
                except Exception:
                    if attempt < retries - 1:
                        await browser.close()
                        continue
                    else:
                        await browser.close()
                        return {"error": "Failed to extract predictions after retries"}

                predictions_text = await page.evaluate('() => document.querySelector("#predictions")?.innerText || ""')
                await browser.close()
                if not predictions_text:
                    return {"error": "No prediction text found"}

                location = predictions_text.split('GPS location around:')[0].strip()
                if location.startswith('1. '):
                    location = location[3:]
                location = location.replace('-', ',').replace('\n', ' ').replace('\r', '').strip(' ,.\n')

                confidence = None
                if 'Confidence:' in predictions_text:
                    try:
                        confidence_raw = predictions_text.split('Confidence: ')[1].split('%')[0].strip()
                        if confidence_raw and confidence_raw != '0':
                            confidence = confidence_raw + '%'
                    except:
                        confidence = None

                if confidence:
                    return {"result": location, "confidence": confidence}
                else:
                    return {"result": location}
        except Exception as e:
            if attempt == retries - 1:
                return {"error": str(e)}
            await asyncio.sleep(5)

@app.post("/locate")
async def scrape(file: UploadFile = File(...)):
    try:
        image_data = await file.read()
        cache_key = generate_cache_key(image_data)
        result = await scrape_picarta_bytes(image_data, cache_key)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8889)
