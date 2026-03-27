import aiohttp
import asyncio
import json
import io
import os, sys
import ssl
from PIL import Image
import imagehash
from dotenv import load_dotenv

load_dotenv("/root/heist-v3/heist/.env")

PROXY=f"http://{os.getenv('PROXY','')}"
USERNAME="phuogtrag"
PLACE_ID=9825515356
LOOPS=120 # keep this the same
MAX_BATCH_PARALLEL=12
MAX_HASH_PARALLEL=250

_original_path = sys.path.copy()
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append("/root/heist-v3")
from heist.framework.tools.robloxget import get_cookie_by_index
sys.path = _original_path

previous_server_thumbs = {}

def log(x):
    with open("logs.txt","a",encoding="utf-8") as f:f.write(x+"\n")
    print(x)

def write_tokens(t):
    with open("tokens.txt","w",encoding="utf-8") as f:
        for x in sorted(set(t)):f.write(x+"\n")

def write_thumbs(t):
    with open("thumbs.txt","w",encoding="utf-8") as f:
        for x in sorted(set(t)):f.write(x+"\n")

def write_details(u):
    with open("details.txt","w",encoding="utf-8") as f:f.write("TARGET_AVATAR_URL: "+u+"\n")

def write_server_thumbs(scan, server_id, thumbs):
    with open("server_thumbs_log.txt", "a", encoding="utf-8") as f:
        f.write(f"\nSCAN {scan}\nSERVER {server_id}\n")
        for t in thumbs:
            f.write(t + "\n")

def write_diff(scan, prev, curr):
    with open("diff.txt", "a", encoding="utf-8") as f:
        f.write(f"\nDIFF SCAN {scan} vs SCAN {scan-1}\n")
        for sid in curr:
            old=set(prev.get(sid,[]))
            new=set(curr.get(sid,[]))
            add=new-old
            rem=old-new
            if not add and not rem:
                f.write(f"SERVER {sid}\n(no changes)\n")
                continue
            f.write(f"SERVER {sid}\n")
            for x in add:
                f.write(f"+ {x}\n")
            for x in rem:
                f.write(f"- {x}\n")

class Client:
    def __init__(self,p):
        self.proxy=p
        self.session=None
        self.cookie=None

    async def sesh(self):
        if self.session is None or self.session.closed:
            ssl_ctx=ssl.create_default_context()
            ssl_ctx.check_hostname=False
            ssl_ctx.verify_mode=ssl.CERT_NONE
            self.session=aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=3000,ssl=ssl_ctx)
            )

    def set_cookie(self,c):
        self.cookie=c

    async def req(self,method,url,**kw):
        await self.sesh()
        h={"User-Agent":"BaszuckiLikesKids/5.0","Cookie":f".ROBLOSECURITY={self.cookie}"}
        extra=kw.pop("headers",None)
        if extra:h.update(extra)
        for _ in range(15):
            try:
                async with self.session.request(method,url,proxy=self.proxy,timeout=10,headers=h,**kw) as r:
                    try:return await r.json()
                    except:return None
            except:
                continue
        return None

client=Client(PROXY)

async def get_uid(u):
    r=await client.req("POST","https://users.roblox.com/v1/usernames/users",json={"usernames":[u]})
    try:return r["data"][0]["id"]
    except:return None

async def get_avatar(uid):
    r=await client.req("GET",f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={uid}&size=150x150&format=png")
    try:return r["data"][0]["imageUrl"]
    except:return None

async def fetch_page(pid,c):
    if c:url=f"https://games.roblox.com/v1/games/{pid}/servers/Public?cursor={c}"
    else:url=f"https://games.roblox.com/v1/games/{pid}/servers/Public"
    return await client.req("GET",url)

async def fast_hash_bytes(b):
    try:
        im=Image.open(io.BytesIO(b)).convert("RGB").resize((32,32))
        return imagehash.average_hash(im)
    except:
        return None

async def full_hash_bytes(b):
    try:
        im=Image.open(io.BytesIO(b)).convert("RGB")
        return imagehash.average_hash(im)
    except:
        return None

async def download_image(url):
    for _ in range(10):
        try:
            await client.sesh()
            async with client.session.get(url,proxy=client.proxy,timeout=8) as r:
                return await r.read()
        except:
            await asyncio.sleep(0.02)
    return None

async def batch(tokens):
    chunks=[]
    for i in range(0,len(tokens),100):
        req=[]
        for t in tokens[i:i+100]:
            req.append({
                "requestId":f"0:{t}:AvatarHeadshot:150x150:png:regular",
                "type":"AvatarHeadShot",
                "targetId":0,
                "token":t,
                "format":"png",
                "size":"150x150"
            })
        chunks.append(req)
    sem=asyncio.Semaphore(MAX_BATCH_PARALLEL)
    async def do(req):
        async with sem:
            for _ in range(10):
                r=await client.req("POST","https://thumbnails.roblox.com/v1/batch",json=req)
                if r and "data" in r:return r["data"]
                r=await client.req("POST","https://thumbnails.roproxy.com/v1/batch",json=req)
                if r and "data" in r:return r["data"]
            return []
    tasks=[asyncio.create_task(do(c)) for c in chunks]
    out=[]
    for t in asyncio.as_completed(tasks):
        r=await t
        if r:out.extend(r)
    return out

async def scan_once(pid,target_fast,target_full):
    cursor=None
    servers=[]
    while True:
        r=await fetch_page(pid,cursor)
        if not r:break
        d=r.get("data",[])
        if not d:break
        servers.extend(d)
        cursor=r.get("nextPageCursor")
        if not cursor:break
    token_map={}
    all_tokens=[]
    for s in servers:
        pts=s.get("playerTokens",[])
        for t in pts:
            all_tokens.append(t)
            if t not in token_map:token_map[t]=[]
            token_map[t].append(s)
    thumbs=await batch(all_tokens)
    all_thumbs=[]
    sem=asyncio.Semaphore(MAX_HASH_PARALLEL)

    async def process(ent):
        async with sem:
            u=ent.get("imageUrl")
            if not u:return None
            all_thumbs.append(u)
            b=await download_image(u)
            if not b:return None
            h1=await fast_hash_bytes(b)
            if h1 is None:return None
            if target_fast-h1<=1:
                h2=await full_hash_bytes(b)
                if h2 and target_full-h2<=2:
                    tok=ent["requestId"].split(":")[1]
                    sv=token_map.get(tok,[])
                    if sv:return {"server":sv[0],"token":tok}
        return None

    tasks=[asyncio.create_task(process(ent)) for ent in thumbs]
    for t in asyncio.as_completed(tasks):
        r=await t
        if r:
            return {"server":r["server"],"token":r["token"],"tokens":all_tokens,"thumbs":all_thumbs}

    server_thumbs={}
    for s in servers:
        server_thumbs[s["id"]]=[]

    for ent in thumbs:
        u=ent.get("imageUrl")
        if not u:continue
        tok=ent["requestId"].split(":")[1]
        if tok in token_map:
            s=token_map[tok][0]
            server_thumbs[s["id"]].append(u)

    return {"server":None,"token":None,"tokens":all_tokens,"thumbs":all_thumbs,"server_thumbs":server_thumbs}

async def confirm(pid,token,sid):
    cursor=None
    while True:
        r=await fetch_page(pid,cursor)
        if not r:return None
        d=r.get("data",[])
        for s in d:
            if s["id"]==sid:
                if token in s.get("playerTokens",[]):return s
                return None
        cursor=r.get("nextPageCursor")
        if not cursor:return None

async def run():
    global previous_server_thumbs
    for f in ["tokens.txt","thumbs.txt","details.txt","logs.txt","server_thumbs_log.txt","diff.txt"]:
        if os.path.exists(f):os.remove(f)

    log("START")

    client.set_cookie(get_cookie_by_index(0))
    uid=await get_uid(USERNAME)
    if not uid:
        log("User not found")
        return
    avatar=await get_avatar(uid)
    if not avatar:
        log("Avatar not found")
        return

    write_details(avatar)
    target_fast=None
    target_full=None

    for _ in range(10):
        b=await download_image(avatar)
        if b:
            target_fast=await fast_hash_bytes(b)
            target_full=await full_hash_bytes(b)
            break

    if target_fast is None or target_full is None:
        log("Hash failed")
        return

    all_tokens=[]
    all_thumbs=[]

    for scan in range(1,LOOPS+1):
        client.set_cookie(get_cookie_by_index(scan-1))
        log(f"SCAN {scan}/{LOOPS}")
        r=await scan_once(PLACE_ID,target_fast,target_full)
        all_tokens.extend(r["tokens"])
        all_thumbs.extend(r["thumbs"])

        if "server_thumbs" in r:
            curr=r["server_thumbs"]
            if scan>1:
                write_diff(scan, previous_server_thumbs, curr)
            for sid,lst in curr.items():
                write_server_thumbs(scan,sid,lst)
            previous_server_thumbs=curr

        if r["server"]:
            sv=r["server"]
            tok=r["token"]
            c=await confirm(PLACE_ID,tok,sv["id"])
            write_tokens(all_tokens)
            write_thumbs(all_thumbs)
            if c:
                log("FOUND")
                log(f"Server: {c['id']}")
                log(f"Join: https://www.roblox.com/games/start?placeId={PLACE_ID}&gameInstanceId={c['id']}")
                log("END")
                await client.session.close()
                return

        await asyncio.sleep(0.05)

    write_tokens(all_tokens)
    write_thumbs(all_thumbs)
    log("NOT FOUND")
    log("END")
    await client.session.close()

if __name__=="__main__":
    asyncio.run(run())
