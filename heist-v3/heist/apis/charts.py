import os
import io
import asyncio
import aiohttp
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import datetime as dt
from fastapi import FastAPI, Response
from redis.asyncio import Redis
from dotenv import load_dotenv
import ujson as json

load_dotenv("/root/heist-v3/heist/.env")

app = FastAPI()
redis = Redis(host="localhost", port=6379, db=0)

PROXY = os.getenv("PROXY")

session: aiohttp.ClientSession = None

@app.on_event("startup")
async def startup():
    global session
    session = aiohttp.ClientSession()

@app.on_event("shutdown")
async def shutdown():
    await session.close()

async def fetch(url, params=None):
    async with session.get(url, params=params) as r:
        if r.status == 429:
            async with session.get(url, params=params, proxy=f"http://{PROXY}") as r2:
                return await r2.json()
        return await r.json()

def build_chart_sync(prices):
    x = np.array([dt.datetime.fromtimestamp(p[0] / 1000) for p in prices])
    y = np.array([p[1] for p in prices])
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(10.5, 4.1), dpi=300)
    ax.set_facecolor("#0f141c")
    fig.patch.set_facecolor("#0f141c")
    xmin, xmax = x[0], x[-1]
    xticks = np.linspace(xmin, xmax, 10)
    ax.set_xticks(xticks)
    ax.set_xlim(xmin, xmax)
    true_min = y.min()
    true_max = y.max()
    padding = (true_max - true_min) * 0.10
    ax.set_ylim(true_min - padding, true_max + padding)
    yticks = np.linspace(true_min, true_max, 8)
    ax.set_yticks(yticks)
    ax.grid(which="both", linestyle=":", color="#263043", linewidth=0.6)
    ax.plot(x, y, color="#3e82ff", linewidth=2)
    idx = np.linspace(0, len(x) - 1, 25, dtype=int)
    ax.scatter(x[idx], y[idx], color="#ffffff", edgecolors="#3e82ff", s=18, zorder=5, clip_on=False)
    ax.scatter(x[-1], y[-1], color="#ff9d2a", s=40, zorder=6, clip_on=False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(axis='x', colors="#b7c1d6", labelsize=8)
    ax.tick_params(axis='y', colors="#b7c1d6", labelsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.text(0.99, 0.97, "Heist", transform=ax.transAxes, ha="right", va="top", fontsize=12, color="#b7c1d6")
    buf = io.BytesIO()
    plt.savefig(buf, dpi=350, bbox_inches="tight", pad_inches=0.22, format="png")
    plt.close()
    buf.seek(0)
    return buf.read()

async def build_chart(prices):
    return await asyncio.to_thread(build_chart_sync, prices)

async def get_cached(key):
    v = await redis.get(key)
    if v:
        return json.loads(v)
    return None

async def set_cached(key, data):
    await redis.set(key, json.dumps(data), ex=30)

async def handle_coin(coin_id, cache_key):
    cached = await get_cached(cache_key)
    if cached:
        return Response(content=json.dumps(cached), media_type="application/json")

    chart_data = await fetch(f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
                             {"vs_currency": "usd", "days": 1})
    info = await fetch(f"https://api.coingecko.com/api/v3/coins/{coin_id}",
                       {"localization": "false", "tickers": "false", "market_data": "true",
                        "community_data": "false", "developer_data": "false", "sparkline": "false"})

    prices = chart_data["prices"]
    img = await build_chart(prices)

    market = info["market_data"]
    price = market["current_price"]["usd"]
    change = market["price_change_24h"]
    change_pct = market["price_change_percentage_24h"]
    high = market["high_24h"]["usd"]
    low = market["low_24h"]["usd"]

    if change > 0:
        icon = "<:chartup:1439421600821674055>"
    elif change < 0:
        icon = "<:chartdown:1439421599013929040>"
    else:
        icon = ""

    stats = {
        "price_usd": price,
        "change_24h": change,
        "change_24h_pct": change_pct,
        "high_24h": high,
        "low_24h": low,
        "formatted": (
            f"**Price:** {price:.2f} USD | "
            f"**24H Change:** {change:+.2f} ({change_pct:+.2f}%) {icon} | "
            f"**24H High:** {high:.2f} USD | "
            f"**24H Low:** {low:.2f} USD"
        )
    }

    payload = {"stats": stats, "image": img.hex()}
    await set_cached(cache_key, payload)

    return Response(content=json.dumps(payload), media_type="application/json")

@app.get("/eth")
async def eth():
    return await handle_coin("ethereum", "eth_cache")

@app.get("/btc")
async def btc():
    return await handle_coin("bitcoin", "btc_cache")

@app.get("/ltc")
async def ltc():
    return await handle_coin("litecoin", "ltc_cache")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("charts:app", host="0.0.0.0", port=7685)