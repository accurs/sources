# uhh this requires npm and https://github.com/YunzheZJU/youtube-po-token-generator
import asyncio, os, json
from pytubefix import YouTube

PROXY = None
TOKEN_FILE = "/root/heist-v3/heist/framework/youtube/youtubetoken.json"

async def _gen_tok():
    env = os.environ.copy()
    if PROXY:
        env["HTTPS_PROXY"] = f"http://{PROXY}"
        env["HTTP_PROXY"] = f"http://{PROXY}"
    proc = await asyncio.create_subprocess_shell(
        "youtube-po-token-generator",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    out, err = await proc.communicate()
    data = json.loads(out.decode())
    if "poToken" in data:
        data["po_token"] = data.pop("poToken")
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f)
    return data

async def _ensure_tok():
    if not os.path.exists(TOKEN_FILE):
        return await _gen_tok()
    with open(TOKEN_FILE) as f:
        return json.load(f)

def token_verifier(): # this is for testing run youtube-po-token-generator first
    po_token = "MniVhvqn-Ag6I5W6T3P5jQfCKgj5rVbyQK87uc7Ac2PvJvfHtOA-dVryZ_py6ctreGeoxuNcZkVidMfXBXrr4Oj-Z4cL2z_cUvnfKD_TsAWPXQisoIzmjPDVv4hcGtCQqGZwDFsPR5BaGtN7bUtqMpK9Lu2DsqCOaH8="
    visitor_data = "CgsxcEtOWVpCNHlTZyiumNbHBjIKCgJVUxIEGgAgEg%3D%3D"
    return visitor_data, po_token

async def get_youtube(url: str, proxy: str | None = PROXY):
    async def _new():
        await _ensure_tok()
        pc = {"http": f"http://{proxy}", "https": f"http://{proxy}"} if proxy else None
        pc2 = {"http": f"socks5://{proxy}", "https": f"socks5://{proxy}"}
        return YouTube(url, client="WEB", use_po_token=True, token_file=TOKEN_FILE) # parameter is proxies=, proxies fuck it up tho idk why lol - adrian fix plz?
        #return YouTube(url, client="WEB", use_po_token=True, po_token_verifier=token_verifier)
    try:
        return await _new()
    except:
        await _gen_tok()
        return await _new()

async def main():
    d = await _gen_tok()
    print("NEW TOKEN:", d, flush=True)

if __name__ == "__main__":
    asyncio.run(main())
