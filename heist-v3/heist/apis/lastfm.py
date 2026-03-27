from flask import Flask, request, render_template_string
import aiohttp, asyncio, os, hashlib, asyncpg, json
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_API_SECRET = os.getenv("LASTFM_API_SECRET")
DATABASE_URL = os.getenv("DSN")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{ title }}</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 flex items-center justify-center h-screen">
  <div class="bg-white rounded-2xl shadow-lg p-8 max-w-md w-full text-center">
    {% if success %}
      <img src="https://git.cursi.ng/heist.png" alt="Heist Logo" class="w-24 h-24 mx-auto mb-4 rounded-full shadow">
      <h1 class="text-2xl font-semibold text-gray-800 mb-2">Successfully linked!</h1>
      <p class="text-gray-600">Your Last.fm account has been successfully linked to Heist. You may now close this tab.</p>
    {% else %}
      <div class="text-red-500 text-6xl mb-4">❌</div>
      <h1 class="text-2xl font-semibold text-gray-800 mb-2">Link Failed</h1>
      <p class="text-gray-600">Make a support ticket in Heist's server.</p>
    {% endif %}
  </div>
</body>
</html>
"""

async def complete_login(discord_id: int, token: str):
    print(f"[START] complete_login: discord_id={discord_id}, token={token}", flush=True)

    sig_raw = f"api_key{LASTFM_API_KEY}methodauth.getSessiontoken{token}{LASTFM_API_SECRET}"
    api_sig = hashlib.md5(sig_raw.encode()).hexdigest()
    params = {
        "method": "auth.getSession",
        "api_key": str(LASTFM_API_KEY),
        "token": str(token),
        "api_sig": str(api_sig),
        "format": "json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get("https://ws.audioscrobbler.com/2.0/", params=params) as resp:
            text = await resp.text()
            print(f"[HTTP] Response ({resp.status}): {text}", flush=True)
            try:
                data = json.loads(text)
            except Exception as e:
                print(f"[ERROR] JSON decode failed: {e}", flush=True)
                return False

    if "session" not in data:
        print(f"[ERROR] No session key in response: {data}", flush=True)
        return False

    username = data["session"]["name"]
    session_key = data["session"]["key"]
    print(f"[SUCCESS] Got username={username}, session_key={session_key}", flush=True)

    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute("""
            INSERT INTO lastfm_users (discord_id, lastfm_username, session_key)
            VALUES ($1, $2, $3)
            ON CONFLICT (discord_id)
            DO UPDATE SET lastfm_username = $2, session_key = $3;
        """, discord_id, username, session_key)
        await conn.close()
        print(f"[DB] Linked account saved for {discord_id}", flush=True)
    except Exception as e:
        print(f"[DB ERROR] {e}", flush=True)
        return False

    return True

@app.route("/lastfm")
def callback():
    print("[CALLBACK] /lastfm hit", flush=True)
    args = dict(request.args)
    print(f"[CALLBACK] Query args: {args}", flush=True)

    token = request.args.get("token")
    state = request.args.get("state")

    if not token or not state:
        print("[CALLBACK ERROR] Missing token or state", flush=True)
        return render_template_string(HTML_TEMPLATE, title="Error", success=False), 400

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        discord_id = loop.run_until_complete(fetch_discord_id_from_state(state))
        if not discord_id:
            print(f"[CALLBACK ERROR] State {state} not found in DB", flush=True)
            return render_template_string(HTML_TEMPLATE, title="Error", success=False), 403

        print(f"[CALLBACK] Found discord_id={discord_id} for state={state}", flush=True)
        loop.run_until_complete(delete_state(state))
        result = loop.run_until_complete(complete_login(int(discord_id), token))
        if result:
            return render_template_string(HTML_TEMPLATE, title="Success", success=True)
        else:
            return render_template_string(HTML_TEMPLATE, title="Failed", success=False), 500
    except Exception as e:
        print(f"[CALLBACK ERROR] Exception: {e}", flush=True)
        return render_template_string(HTML_TEMPLATE, title="Error", success=False), 500

async def fetch_discord_id_from_state(state: str):
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow("SELECT discord_id FROM lastfm_auth_state WHERE state = $1", state)
    await conn.close()
    return row["discord_id"] if row else None

async def delete_state(state: str):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("DELETE FROM lastfm_auth_state WHERE state = $1", state)
    await conn.close()

if __name__ == "__main__":
    print("[INIT] Starting Flask on port 8288", flush=True)
    app.run(host="0.0.0.0", port=8288)
