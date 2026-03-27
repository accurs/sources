import discord
import aiohttp
import random
import time
import json
from discord.ext import commands

SHOP: dict[int, dict] = {
    1: {"name": "Fishing Rod",     "price":   500, "desc": "Required to fish",                 "type": "tool", "key": "fishrod"},
    2: {"name": "Hunting Bow",     "price":   800, "desc": "Required to hunt",                 "type": "tool", "key": "huntbow"},
    3: {"name": "Pickaxe",         "price":   700, "desc": "Required to mine",                 "type": "tool", "key": "pickaxe"},
    4: {"name": "Shield",          "price":  1200, "desc": "50% chance to block rob attempts", "type": "tool", "key": "shield"},
    5: {"name": "Laptop",          "price":  2000, "desc": "+25% bonus on work earnings",      "type": "tool", "key": "laptop"},
    6: {"name": "Bank Upgrade S",  "price":  1500, "desc": "Bank capacity +5,000 coins",       "type": "bank", "amount": 5000},
    7: {"name": "Bank Upgrade M",  "price":  4000, "desc": "Bank capacity +15,000 coins",      "type": "bank", "amount": 15000},
    8: {"name": "Bank Upgrade L",  "price": 10000, "desc": "Bank capacity +40,000 coins",      "type": "bank", "amount": 40000},
    9: {"name": "Bank Upgrade XL", "price": 25000, "desc": "Bank capacity +100,000 coins",     "type": "bank", "amount": 100000},
}

FISH_LOOT = ["Common Fish"] * 4 + ["Tropical Fish"] * 2 + ["Pufferfish", "Squid", "Lobster", "Shark", "Old Boot", "Trash"]
HUNT_LOOT = ["Rabbit"] * 3 + ["Fox", "Deer", "Boar", "Bear", "Eagle", "Mushroom", "Nothing"]
MINE_LOOT = ["Stone"] * 5 + ["Iron"] * 3 + ["Gold", "Diamond"]

LOOT_VALUE: dict[str, int] = {
    "Common Fish": 30,  "Tropical Fish": 80,  "Shark": 200,
    "Pufferfish":  60,  "Squid":         90,  "Lobster": 150,
    "Old Boot":     2,  "Trash":          1,
    "Rabbit":      40,  "Fox":          120,   "Deer": 180,
    "Boar":       220,  "Bear":         400,   "Eagle": 350,
    "Mushroom":    25,  "Nothing":        0,
    "Stone":        5,  "Iron":          50,   "Gold": 300,
    "Diamond":    500,
}

WORK_LINES = [
    ("delivered packages all day",       80,  200),
    ("wrote code for a client",         150,  350),
    ("walked the neighbour's dog",       50,  120),
    ("sold lemonade on the street",      30,   90),
    ("fixed someone's computer",        100,  280),
    ("streamed for 3 hours",            200,  500),
    ("flipped burgers all shift",        60,  140),
    ("drove people around all night",    90,  220),
    ("did freelance design work",       120,  300),
    ("tutored a student online",        110,  260),
]

CRIME_WIN = [
    ("robbed a convenience store",    300,  700),
    ("pickpocketed a tourist",        100,  400),
    ("hacked into someone's account", 500, 1200),
    ("sold knockoff goods",           200,  600),
    ("ran a pyramid scheme",          800, 2000),
    ("forged some documents",         400,  900),
]

CRIME_LOSS = [
    "got caught by the police and paid a fine",
    "slipped and fell running away",
    "your accomplice snitched on you",
    "tripped the alarm",
    "got recognized on CCTV",
    "ran straight into a cop",
]

BEG_LINES = [
    ("A kind stranger felt sorry for you",  5,  40),
    ("Someone tossed you some change",      1,  25),
    ("A rich person dropped their wallet", 10,  60),
    ("You found a coin on the ground",      1,  15),
    ("A passing developer donated to you", 20,  80),
    ("Someone felt bad and gave you coins", 5,  35),
]

CD = {
    "daily":  86400,
    "weekly": 604800,
    "work":   3600,
    "beg":    30,
    "crime":  7200,
    "fish":   1800,
    "hunt":   1800,
    "mine":   1800,
    "rob":    3600,
}

def fmt_cd(s: float) -> str:
    s = int(s)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return " ".join(parts)


class economy(commands.Cog):
    def __init__(self, bot):
        self.bot         = bot

    async def _exec(self, q: str, *a):
        async with self.bot.db.acquire() as c:
            await c.execute(q, *a, timeout=30)

    async def _row(self, q: str, *a):
        async with self.bot.db.acquire() as c:
            return await c.fetchrow(q, *a, timeout=30)

    async def _rows(self, q: str, *a):
        async with self.bot.db.acquire() as c:
            return await c.fetch(q, *a, timeout=30)


    async def ensure_tables(self):
        await self._exec("""
            CREATE TABLE IF NOT EXISTS economy (
                user_id   BIGINT,
                guild_id  BIGINT,
                wallet    BIGINT      DEFAULT 0,
                bank      BIGINT      DEFAULT 0,
                bank_max  BIGINT      DEFAULT 5000,
                inventory JSONB       DEFAULT '{}',
                PRIMARY KEY (user_id, guild_id)
            )
        """)
        await self._exec("""
            CREATE TABLE IF NOT EXISTS economy_cooldowns (
                user_id   BIGINT,
                guild_id  BIGINT,
                key       TEXT,
                expires   DOUBLE PRECISION,
                PRIMARY KEY (user_id, guild_id, key)
            )
        """)

    async def cog_load(self):
        await self.ensure_tables()

    async def cd_get(self, uid: int, gid: int, key: str) -> float:
        row = await self._row(
            "SELECT expires FROM economy_cooldowns WHERE user_id=$1 AND guild_id=$2 AND key=$3",
            uid, gid, key
        )
        if not row:
            return 0.0
        remaining = row["expires"] - time.time()
        return max(0.0, remaining)

    async def cd_set(self, uid: int, gid: int, key: str):
        expires = time.time() + CD[key]
        await self._exec(
            """
            INSERT INTO economy_cooldowns (user_id, guild_id, key, expires)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id, guild_id, key)
            DO UPDATE SET expires = EXCLUDED.expires
            """,
            uid, gid, key, expires
        )


    def _inv(self, raw) -> dict:
        if raw is None:             return {}
        if isinstance(raw, dict):   return raw
        if isinstance(raw, str):
            try:    return json.loads(raw)
            except: return {}
        try:    return dict(raw)
        except: return {}

    async def get_user(self, uid: int, gid: int) -> dict:
        row = await self._row(
            "SELECT * FROM economy WHERE user_id=$1 AND guild_id=$2", uid, gid
        )
        if not row:
            await self._exec(
                "INSERT INTO economy(user_id,guild_id,wallet,bank,bank_max,inventory)"
                " VALUES($1,$2,0,0,5000,'{}') ON CONFLICT DO NOTHING",
                uid, gid
            )
            return {"user_id": uid, "guild_id": gid,
                    "wallet": 0, "bank": 0, "bank_max": 5000, "inventory": {}}
        d = dict(row)
        d["inventory"] = self._inv(d.get("inventory"))
        return d

    async def _wallet(self, uid: int, gid: int, delta: int):
        await self._exec(
            "UPDATE economy SET wallet=wallet+$1 WHERE user_id=$2 AND guild_id=$3",
            delta, uid, gid
        )

    async def _bank(self, uid: int, gid: int, delta: int):
        await self._exec(
            "UPDATE economy SET bank=bank+$1 WHERE user_id=$2 AND guild_id=$3",
            delta, uid, gid
        )

    async def _save_inv(self, uid: int, gid: int, inv: dict):
        await self._exec(
            "UPDATE economy SET inventory=$1::jsonb WHERE user_id=$2 AND guild_id=$3",
            json.dumps(inv), uid, gid
        )

    async def _add_item(self, uid: int, gid: int, item: str):
        d = await self.get_user(uid, gid)
        inv = d["inventory"]
        inv[item] = int(inv.get(item, 0)) + 1
        await self._save_inv(uid, gid, inv)

    async def _sell_item(self, uid: int, gid: int, item: str, qty: int) -> int:
        """Remove qty of item from inventory, return coins earned. 0 if not enough."""
        d   = await self.get_user(uid, gid)
        inv = d["inventory"]
        have = int(inv.get(item, 0))
        if have < qty:
            return 0
        value = LOOT_VALUE.get(item, 0)
        if value == 0:
            return 0
        new_qty = have - qty
        if new_qty <= 0:
            inv.pop(item, None)
        else:
            inv[item] = new_qty
        await self._save_inv(uid, gid, inv)
        await self._wallet(uid, gid, value * qty)
        return value * qty

    def _has(self, d: dict, key: str) -> bool:
        return int((d.get("inventory") or {}).get(key, 0)) > 0


    async def _v2(self, ctx: commands.Context, content: str, *, buttons: list | None = None):
        inner: list = [{"type": 10, "content": content}]
        if buttons:
            inner += [{"type": 14}, {"type": 1, "components": buttons}]
        payload = {"flags": 32768, "components": [{"type": 17, "components": inner}]}
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://discord.com/api/v10/channels/{ctx.channel.id}/messages",
                json=payload,
                headers={"Authorization": f"Bot {self.bot.http.token}",
                         "Content-Type": "application/json"}
            ) as r:
                if r.status not in (200, 201):
                    print(f"[economy v2] {r.status}: {await r.text()}")

    async def _v2_thumb(self, ctx: commands.Context, content: str, url: str):
        payload = {
            "flags": 32768,
            "components": [{
                "type": 17,
                "components": [{
                    "type": 9,
                    "components": [{"type": 10, "content": content}],
                    "accessory": {"type": 11, "media": {"url": url}}
                }]
            }]
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://discord.com/api/v10/channels/{ctx.channel.id}/messages",
                json=payload,
                headers={"Authorization": f"Bot {self.bot.http.token}",
                         "Content-Type": "application/json"}
            ) as r:
                if r.status not in (200, 201):
                    print(f"[economy v2] {r.status}: {await r.text()}")

    def _bar(self, current: int, maximum: int) -> tuple[str, int]:
        LB = "<:1453065542092197939:1482439545579376691>"
        MB = "<:1453065576581697547:1482439552768409721>"
        RB = "<:1453065603626700830:1482439558179192892>"
        LW = "<:1453065657791807539:1482439548381303026>"
        MW = "<:1453065633393545306:1482439555876524202>"
        RW = "<:1453065683469471846:1482439543620895023>"
        filled = int((current / maximum) * 10) if maximum else 0
        filled = max(0, min(10, filled))
        pct    = current * 100 // maximum if maximum else 0
        def seg(i):
            on = i < filled
            if i == 0: return LW if on else LB
            if i == 9: return RW if on else RB
            return MW if on else MB
        return "".join(seg(i) for i in range(10)), pct

    @commands.hybrid_command(name="balance", aliases=["bal"],
        description="Check your or another user's balance", usage="[user]", help="economy")
    async def balance(self, ctx: commands.Context, user: discord.Member = None):
        user  = user or ctx.author
        d     = await self.get_user(user.id, ctx.guild.id)
        total = d["wallet"] + d["bank"]
        bar, pct = self._bar(d["bank"], d["bank_max"])
        content = (
            f"**{user.name}'s Balance**\n"
            f"\n"
            f"> **Wallet**    — {d['wallet']:,} coins\n"
            f"> **Bank**      — {d['bank']:,} / {d['bank_max']:,} coins\n"
            f"> {bar}  {pct}%\n"
            f"\n"
            f"> **Net Worth** — {total:,} coins"
        )
        await self._v2_thumb(ctx, content, str(user.display_avatar.url))

    @commands.hybrid_command(name="daily",
        description="Claim your daily coins", help="economy")
    async def daily(self, ctx: commands.Context):
        cd = await self.cd_get(ctx.author.id, ctx.guild.id, "daily")
        if cd:
            return await self._v2(ctx, f"> **Daily cooldown - come back in {fmt_cd(cd)}...**")
        await self.get_user(ctx.author.id, ctx.guild.id)
        amount = random.randint(200, 500)
        await self._wallet(ctx.author.id, ctx.guild.id, amount)
        await self.cd_set(ctx.author.id, ctx.guild.id, "daily")
        await self._v2(ctx,
            f"**Daily Reward**\n"
            f"\n"
            f"> You claimed **{amount:,} coins**\n"
            f"> Come back in **24h** for your next reward..."
        )

    @commands.hybrid_command(name="weekly",
        description="Claim your weekly coins", help="economy")
    async def weekly(self, ctx: commands.Context):
        cd = await self.cd_get(ctx.author.id, ctx.guild.id, "weekly")
        if cd:
            return await self._v2(ctx, f"> **Weekly cooldown — come back in {fmt_cd(cd)}...**")
        await self.get_user(ctx.author.id, ctx.guild.id)
        amount = random.randint(1000, 3000)
        await self._wallet(ctx.author.id, ctx.guild.id, amount)
        await self.cd_set(ctx.author.id, ctx.guild.id, "weekly")
        await self._v2(ctx,
            f"**Weekly Reward**\n"
            f"\n"
            f"> You claimed **{amount:,} coins**\n"
            f"> Come back in **7 days** for your next reward..."
        )

    @commands.hybrid_command(name="work",
        description="Work to earn some coins", help="economy")
    async def work(self, ctx: commands.Context):
        cd = await self.cd_get(ctx.author.id, ctx.guild.id, "work")
        if cd:
            return await self._v2(ctx, f"> **Still tired from your last shift — come back in {fmt_cd(cd)}...**")
        d              = await self.get_user(ctx.author.id, ctx.guild.id)
        action, lo, hi = random.choice(WORK_LINES)
        amount         = random.randint(lo, hi)
        bonus          = ""
        if self._has(d, "laptop"):
            amount = int(amount * 1.25)
            bonus  = "  **(+25% laptop bonus)**"
        await self._wallet(ctx.author.id, ctx.guild.id, amount)
        await self.cd_set(ctx.author.id, ctx.guild.id, "work")
        await self._v2(ctx,
            f"**Work**\n"
            f"\n"
            f"> You {action}\n"
            f"> Earned **{amount:,} coins**{bonus}\n"
            f"\n"
            f"-# Cooldown: 1h"
        )

    @commands.hybrid_command(name="beg",
        description="Beg for some coins", help="economy")
    async def beg(self, ctx: commands.Context):
        cd = await self.cd_get(ctx.author.id, ctx.guild.id, "beg")
        if cd:
            return await self._v2(ctx, f"> **Not so fast — come back in {fmt_cd(cd)}...**")
        await self.get_user(ctx.author.id, ctx.guild.id)
        text, lo, hi = random.choice(BEG_LINES)
        amount       = random.randint(lo, hi)
        await self._wallet(ctx.author.id, ctx.guild.id, amount)
        await self.cd_set(ctx.author.id, ctx.guild.id, "beg")
        await self._v2(ctx,
            f"**Beg**\n"
            f"\n"
            f"> {text}\n"
            f"> You received **{amount:,} coins**\n"
            f"\n"
            f"-# Cooldown: 30s"
        )

    @commands.hybrid_command(name="crime",
        description="Commit a crime for big rewards — risky", help="economy")
    async def crime(self, ctx: commands.Context):
        cd = await self.cd_get(ctx.author.id, ctx.guild.id, "crime")
        if cd:
            return await self._v2(ctx, f"> **The heat is still on — lay low for {fmt_cd(cd)}...**")
        d = await self.get_user(ctx.author.id, ctx.guild.id)
        await self.cd_set(ctx.author.id, ctx.guild.id, "crime")
        if random.random() < 0.40:
            fine   = min(random.randint(100, 500), d["wallet"])
            reason = random.choice(CRIME_LOSS)
            await self._wallet(ctx.author.id, ctx.guild.id, -fine)
            return await self._v2(ctx,
                f"**Crime — Busted**\n"
                f"\n"
                f"> You {reason}\n"
                f"> Paid a fine of **{fine:,} coins**\n"
                f"\n"
                f"-# Cooldown: 2h"
            )
        action, lo, hi = random.choice(CRIME_WIN)
        amount         = random.randint(lo, hi)
        await self._wallet(ctx.author.id, ctx.guild.id, amount)
        await self._v2(ctx,
            f"**Crime — Success**\n"
            f"\n"
            f"> You {action}\n"
            f"> Got away with **{amount:,} coins**\n"
            f"\n"
            f"-# Cooldown: 2h"
        )

    @commands.hybrid_command(name="fish",
        description="Go fishing — requires Fishing Rod", help="economy")
    async def fish(self, ctx: commands.Context):
        cd = await self.cd_get(ctx.author.id, ctx.guild.id, "fish")
        if cd:
            return await self._v2(ctx, f"> **Your line is still in the water — {fmt_cd(cd)} remaining...**")
        d = await self.get_user(ctx.author.id, ctx.guild.id)
        if not self._has(d, "fishrod"):
            return await self._v2(ctx, "> **You need a Fishing Rod to fish — buy one with `buy 1`...**")
        item  = random.choice(FISH_LOOT)
        value = LOOT_VALUE.get(item, 0)
        await self._add_item(ctx.author.id, ctx.guild.id, item)
        await self.cd_set(ctx.author.id, ctx.guild.id, "fish")
        await self._v2(ctx,
            f"**Fishing**\n"
            f"\n"
            f"> You cast your line and caught a **{item}**\n"
            f"> Worth **{value:,} coins** if sold\n"
            f"\n"
            f"-# Cooldown: 30m"
        )

    @commands.hybrid_command(name="hunt",
        description="Go hunting — requires Hunting Bow", help="economy")
    async def hunt(self, ctx: commands.Context):
        cd = await self.cd_get(ctx.author.id, ctx.guild.id, "hunt")
        if cd:
            return await self._v2(ctx, f"> **You need to wait {fmt_cd(cd)} before hunting again...**")
        d = await self.get_user(ctx.author.id, ctx.guild.id)
        if not self._has(d, "huntbow"):
            return await self._v2(ctx, "> **You need a Hunting Bow to hunt — buy one with `buy 2`...**")
        item  = random.choice(HUNT_LOOT)
        value = LOOT_VALUE.get(item, 0)
        await self._add_item(ctx.author.id, ctx.guild.id, item)
        await self.cd_set(ctx.author.id, ctx.guild.id, "hunt")
        await self._v2(ctx,
            f"**Hunting**\n"
            f"\n"
            f"> You ventured out and caught a **{item}**\n"
            f"> Worth **{value:,} coins** if sold\n"
            f"\n"
            f"-# Cooldown: 30m"
        )

    @commands.hybrid_command(name="mine",
        description="Go mining — requires Pickaxe", help="economy")
    async def mine(self, ctx: commands.Context):
        cd = await self.cd_get(ctx.author.id, ctx.guild.id, "mine")
        if cd:
            return await self._v2(ctx, f"> **Your pickaxe needs to cool down — {fmt_cd(cd)} remaining...**")
        d = await self.get_user(ctx.author.id, ctx.guild.id)
        if not self._has(d, "pickaxe"):
            return await self._v2(ctx, "> **You need a Pickaxe to mine — buy one with `buy 3`...**")
        item  = random.choice(MINE_LOOT)
        value = LOOT_VALUE.get(item, 0)
        await self._add_item(ctx.author.id, ctx.guild.id, item)
        await self.cd_set(ctx.author.id, ctx.guild.id, "mine")
        await self._v2(ctx,
            f"**Mining**\n"
            f"\n"
            f"> You swung your pickaxe and found **{item}**\n"
            f"> Worth **{value:,} coins** if sold\n"
            f"\n"
            f"-# Cooldown: 30m"
        )

    @commands.hybrid_command(name="inventory", aliases=["inv"],
        description="View your inventory", usage="[user]", help="economy")
    async def inventory(self, ctx: commands.Context, user: discord.Member = None):
        user = user or ctx.author
        d    = await self.get_user(user.id, ctx.guild.id)
        inv  = {k: v for k, v in d["inventory"].items() if int(v) > 0}
        if not inv:
            return await self._v2(ctx, f"> **{user.name}'s inventory is empty...**")

        fish_set = set(FISH_LOOT)
        hunt_set = set(HUNT_LOOT)
        mine_set = set(MINE_LOOT)

        fish_items = {k: v for k, v in inv.items() if k in fish_set}
        hunt_items = {k: v for k, v in inv.items() if k in hunt_set and k not in fish_set}
        mine_items = {k: v for k, v in inv.items() if k in mine_set and k not in fish_set and k not in hunt_set}
        tool_items = {k: v for k, v in inv.items() if k not in fish_set and k not in hunt_set and k not in mine_set}

        total_worth = sum(LOOT_VALUE.get(k, 0) * int(v) for k, v in inv.items())
        lines = [f"**{user.name}'s Inventory**\n"]

        def section(title: str, items: dict):
            if not items: return
            lines.append(f"**{title}**")
            for k, v in items.items():
                worth = LOOT_VALUE.get(k, 0)
                lines.append(f"> **{k}** ×{v}  —  {worth:,} coins each")
            lines.append("")

        section("Fish", fish_items)
        section("Hunt", hunt_items)
        section("Mine", mine_items)
        section("Tools", tool_items)
        lines.append(f"-# Total sell value: {total_worth:,} coins  ·  Use `sell <item>` or `sellall`")
        await self._v2_thumb(ctx, "\n".join(lines), str(user.display_avatar.url))

    @commands.hybrid_command(name="sell",
        description="Sell items — name, partial name, or 'all'", usage="<item|all>", help="economy")
    async def sell(self, ctx: commands.Context, *, item: str):
        item = item.strip()
        if item.lower() == "all":
            return await self.sellall(ctx)

        d   = await self.get_user(ctx.author.id, ctx.guild.id)
        inv = {k: v for k, v in d["inventory"].items() if int(v) > 0}
        if not inv:
            return await self._v2(ctx, "> **Your inventory is empty...**")

        item_lower = item.lower()
        matched = next(
            (k for k in inv if k.lower() == item_lower),
            next((k for k in inv if item_lower in k.lower()), None)
        )
        if not matched:
            names = ", ".join(f"`{k}`" for k in inv)
            return await self._v2(ctx, f"> **Item not found...**\n> You have: {names}")

        value = LOOT_VALUE.get(matched, 0)
        if value == 0:
            return await self._v2(ctx, f"> **Nobody wants your {matched}...**")

        qty    = int(inv[matched])
        earned = await self._sell_item(ctx.author.id, ctx.guild.id, matched, qty)
        await self._v2(ctx,
            f"**Sell**\n"
            f"\n"
            f"> Sold **{matched}** ×{qty}\n"
            f"> Received **{earned:,} coins**\n"
            f"\n"
            f"-# {value:,} coins each"
        )

    @commands.hybrid_command(name="sellall",
        description="Sell everything in your inventory", help="economy")
    async def sellall(self, ctx: commands.Context):
        d   = await self.get_user(ctx.author.id, ctx.guild.id)
        inv = {k: v for k, v in d["inventory"].items() if int(v) > 0}
        if not inv:
            return await self._v2(ctx, "> **Your inventory is empty...**")

        total    = 0
        sold     = []
        leftover = {}

        for k, v in inv.items():
            val = LOOT_VALUE.get(k, 0)
            qty = int(v)
            if val > 0:
                total += val * qty
                sold.append(f"> {k} ×{qty} — {val * qty:,} coins")
            else:
                leftover[k] = v

        if not sold:
            return await self._v2(ctx, "> **Nothing in your inventory is worth selling...**")

        await self._save_inv(ctx.author.id, ctx.guild.id, leftover)
        await self._wallet(ctx.author.id, ctx.guild.id, total)

        lines = ["**Sell All**", ""] + sold + ["", f"> **Total received: {total:,} coins**"]
        if leftover:
            lines.append(f"\n-# Kept {len(leftover)} worthless item(s)")
        await self._v2(ctx, "\n".join(lines))

    @commands.hybrid_command(name="deposit", aliases=["dep"],
        description="Deposit coins into your bank", usage="<amount|all>", help="economy")
    async def deposit(self, ctx: commands.Context, amount: str):
        d = await self.get_user(ctx.author.id, ctx.guild.id)
        n = d["wallet"] if amount.lower() == "all" else (int(amount) if amount.isdigit() else None)
        if n is None:
            return await self._v2(ctx, "> **Please provide a valid amount or `all`...**")
        if n <= 0:
            return await self._v2(ctx, "> **Amount must be greater than 0...**")
        if n > d["wallet"]:
            return await self._v2(ctx, f"> **You only have {d['wallet']:,} coins in your wallet...**")
        space = d["bank_max"] - d["bank"]
        if space <= 0:
            return await self._v2(ctx, "> **Your bank is full — upgrade capacity with `buy 6`...**")
        dep = min(n, space)
        await self._wallet(ctx.author.id, ctx.guild.id, -dep)
        await self._bank(ctx.author.id, ctx.guild.id, dep)
        bar, pct = self._bar(d["bank"] + dep, d["bank_max"])
        await self._v2(ctx,
            f"**Deposit**\n"
            f"\n"
            f"> Deposited **{dep:,} coins** into your bank\n"
            f"> {bar}  {pct}%\n"
            f"> **{d['bank'] + dep:,} / {d['bank_max']:,} coins**"
        )

    @commands.hybrid_command(name="withdraw", aliases=["with"],
        description="Withdraw coins from your bank", usage="<amount|all>", help="economy")
    async def withdraw(self, ctx: commands.Context, amount: str):
        d = await self.get_user(ctx.author.id, ctx.guild.id)
        n = d["bank"] if amount.lower() == "all" else (int(amount) if amount.isdigit() else None)
        if n is None:
            return await self._v2(ctx, "> **Please provide a valid amount or `all`...**")
        if n <= 0:
            return await self._v2(ctx, "> **Amount must be greater than 0...**")
        if n > d["bank"]:
            return await self._v2(ctx, f"> **You only have {d['bank']:,} coins in your bank...**")
        await self._bank(ctx.author.id, ctx.guild.id, -n)
        await self._wallet(ctx.author.id, ctx.guild.id, n)
        bar, pct = self._bar(d["bank"] - n, d["bank_max"])
        await self._v2(ctx,
            f"**Withdraw**\n"
            f"\n"
            f"> Withdrew **{n:,} coins** from your bank\n"
            f"> {bar}  {pct}%\n"
            f"> **{d['bank'] - n:,} / {d['bank_max']:,} coins**"
        )

    @commands.hybrid_command(name="pay",
        description="Send coins to another user", usage="<user> <amount>", help="economy")
    async def pay(self, ctx: commands.Context, user: discord.Member, amount: int):
        if user.id == ctx.author.id:
            return await self._v2(ctx, "> **You can't pay yourself...**")
        if user.bot:
            return await self._v2(ctx, "> **You can't pay a bot...**")
        if amount <= 0:
            return await self._v2(ctx, "> **Amount must be greater than 0...**")
        d = await self.get_user(ctx.author.id, ctx.guild.id)
        if amount > d["wallet"]:
            return await self._v2(ctx, f"> **You only have {d['wallet']:,} coins in your wallet...**")
        await self.get_user(user.id, ctx.guild.id)
        await self._wallet(ctx.author.id, ctx.guild.id, -amount)
        await self._wallet(user.id, ctx.guild.id, amount)
        await self._v2(ctx,
            f"**Pay**\n"
            f"\n"
            f"> Sent **{amount:,} coins** to **{user.name}**"
        )

    @commands.hybrid_command(name="rob",
        description="Attempt to rob another user", usage="<user>", help="economy")
    async def rob(self, ctx: commands.Context, user: discord.Member):
        if user.id == ctx.author.id:
            return await self._v2(ctx, "> **You can't rob yourself...**")
        if user.bot:
            return await self._v2(ctx, "> **You can't rob a bot...**")
        cd = await self.cd_get(ctx.author.id, ctx.guild.id, "rob")
        if cd:
            return await self._v2(ctx, f"> **Lay low for {fmt_cd(cd)} before robbing again...**")
        target = await self.get_user(user.id, ctx.guild.id)
        author = await self.get_user(ctx.author.id, ctx.guild.id)
        if target["wallet"] < 100:
            return await self._v2(ctx, f"> **{user.name} doesn't have enough coins to rob...**")
        await self.cd_set(ctx.author.id, ctx.guild.id, "rob")
        if self._has(target, "shield") and random.random() < 0.50:
            fine = min(random.randint(50, 200), author["wallet"])
            await self._wallet(ctx.author.id, ctx.guild.id, -fine)
            return await self._v2(ctx,
                f"**Rob — Blocked**\n"
                f"\n"
                f"> {user.name}'s shield blocked your attempt\n"
                f"> You paid a **{fine:,} coin** fine\n"
                f"\n"
                f"-# Cooldown: 1h"
            )
        if random.random() < 0.45:
            fine = min(random.randint(50, 300), author["wallet"])
            await self._wallet(ctx.author.id, ctx.guild.id, -fine)
            return await self._v2(ctx,
                f"**Rob — Caught**\n"
                f"\n"
                f"> You got caught trying to rob **{user.name}**\n"
                f"> Paid a **{fine:,} coin** fine\n"
                f"\n"
                f"-# Cooldown: 1h"
            )
        stolen = max(1, random.randint(
            int(target["wallet"] * 0.10),
            int(target["wallet"] * 0.40)
        ))
        await self._wallet(user.id, ctx.guild.id, -stolen)
        await self._wallet(ctx.author.id, ctx.guild.id, stolen)
        await self._v2(ctx,
            f"**Rob — Success**\n"
            f"\n"
            f"> You robbed **{user.name}** and got away with **{stolen:,} coins**\n"
            f"\n"
            f"-# Cooldown: 1h"
        )

    @commands.hybrid_command(name="coinflip", aliases=["cf"],
        description="Bet coins on a coin flip", usage="<heads|tails> <amount>", help="economy")
    async def coinflip(self, ctx: commands.Context, side: str, amount: int):
        side = side.lower()
        if side not in ("heads", "tails"):
            return await self._v2(ctx, "> **Choose `heads` or `tails`...**")
        if amount <= 0:
            return await self._v2(ctx, "> **Amount must be greater than 0...**")
        d = await self.get_user(ctx.author.id, ctx.guild.id)
        if amount > d["wallet"]:
            return await self._v2(ctx, f"> **You only have {d['wallet']:,} coins...**")
        result = random.choice(("heads", "tails"))
        if result == side:
            await self._wallet(ctx.author.id, ctx.guild.id, amount)
            await self._v2(ctx,
                f"**Coin Flip**\n\n"
                f"> Landed on **{result}** — you guessed right\n"
                f"> Won **{amount:,} coins**"
            )
        else:
            await self._wallet(ctx.author.id, ctx.guild.id, -amount)
            await self._v2(ctx,
                f"**Coin Flip**\n\n"
                f"> Landed on **{result}** — you guessed wrong\n"
                f"> Lost **{amount:,} coins**"
            )

    @commands.hybrid_command(name="slots",
        description="Play the slot machine", usage="<amount>", help="economy")
    async def slots(self, ctx: commands.Context, amount: int):
        if amount <= 0:
            return await self._v2(ctx, "> **Amount must be greater than 0...**")
        d = await self.get_user(ctx.author.id, ctx.guild.id)
        if amount > d["wallet"]:
            return await self._v2(ctx, f"> **You only have {d['wallet']:,} coins...**")
        syms  = ["A", "B", "C", "D", "E", "F"]
        wts   = [30, 25, 20, 15, 7, 3]
        reels = random.choices(syms, weights=wts, k=3)
        disp  = "  ".join(reels)
        if reels[0] == reels[1] == reels[2]:
            mult = 10 if reels[0] == "F" else 5 if reels[0] == "E" else 3
            win  = amount * mult
            await self._wallet(ctx.author.id, ctx.guild.id, win)
            note = f"Jackpot x{mult}! Won **{win:,} coins**"
        elif reels[0] == reels[1] or reels[1] == reels[2]:
            win  = int(amount * 0.5)
            await self._wallet(ctx.author.id, ctx.guild.id, win)
            note = f"Two in a row! Won back **{win:,} coins**"
        else:
            await self._wallet(ctx.author.id, ctx.guild.id, -amount)
            note = f"No match — lost **{amount:,} coins**"
        await self._v2(ctx, f"**Slots**\n\n> [ {disp} ]\n> {note}")

    @commands.hybrid_command(name="blackjack", aliases=["bj"],
        description="Play blackjack against the bot", usage="<amount>", help="economy")
    async def blackjack(self, ctx: commands.Context, amount: int):
        if amount <= 0:
            return await self._v2(ctx, "> **Amount must be greater than 0...**")
        d = await self.get_user(ctx.author.id, ctx.guild.id)
        if amount > d["wallet"]:
            return await self._v2(ctx, f"> **You only have {d['wallet']:,} coins...**")

        deck = [2,3,4,5,6,7,8,9,10,10,10,10,11] * 4
        random.shuffle(deck)

        def val(hand: list) -> int:
            t = sum(hand)
            a = hand.count(11)
            while t > 21 and a:
                t -= 10; a -= 1
            return t

        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]

        def build(reveal: bool = False, note: str = "") -> str:
            d_str = " + ".join(str(c) for c in dealer) if reveal else f"{dealer[0]} + ?"
            p_str = " + ".join(str(c) for c in player)
            lines = [
                f"**Blackjack** — Bet: {amount:,} coins",
                "",
                f"> Your hand:    {p_str}  = **{val(player)}**",
                f"> Dealer hand: {d_str}",
            ]
            if note: lines += ["", f"> {note}"]
            return "\n".join(lines)

        if val(player) == 21:
            win = int(amount * 1.5)
            await self._wallet(ctx.author.id, ctx.guild.id, win)
            return await self._v2(ctx, build(True, f"Blackjack! Won **{win:,} coins**"))

        bot_ref = self.bot
        cog_ref = self

        class BJView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.message = None

            @discord.ui.button(label="Hit", style=discord.ButtonStyle.blurple)
            async def hit(self, interaction: discord.Interaction, btn: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("> **Not your game...**", ephemeral=True)
                player.append(deck.pop())
                pv = val(player)
                if pv > 21:
                    self.stop()
                    for i in self.children: i.disabled = True
                    await cog_ref._wallet(ctx.author.id, ctx.guild.id, -amount)
                    await interaction.response.edit_message(
                        embed=discord.Embed(description=build(True, f"Bust! Lost **{amount:,} coins**"), color=bot_ref.color),
                        view=self
                    )
                elif pv == 21:
                    await self._stand(interaction)
                else:
                    await interaction.response.edit_message(
                        embed=discord.Embed(description=build(), color=bot_ref.color), view=self
                    )

            @discord.ui.button(label="Stand", style=discord.ButtonStyle.grey)
            async def stand(self, interaction: discord.Interaction, btn: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("> **Not your game...**", ephemeral=True)
                await self._stand(interaction)

            async def _stand(self, interaction: discord.Interaction):
                while val(dealer) < 17:
                    dealer.append(deck.pop())
                pv = val(player); dv = val(dealer)
                self.stop()
                for i in self.children: i.disabled = True
                if dv > 21 or pv > dv:
                    await cog_ref._wallet(ctx.author.id, ctx.guild.id, amount)
                    note = f"You win — dealer had {dv}. Won **{amount:,} coins**"
                elif pv == dv:
                    note = f"Push — dealer also had {dv}. Bet returned"
                else:
                    await cog_ref._wallet(ctx.author.id, ctx.guild.id, -amount)
                    note = f"Dealer wins with {dv}. Lost **{amount:,} coins**"
                await interaction.response.edit_message(
                    embed=discord.Embed(description=build(True, note), color=bot_ref.color),
                    view=self
                )

            async def on_timeout(self):
                try:
                    for i in self.children: i.disabled = True
                    await self.message.edit(view=self)
                except: pass

        view         = BJView()
        embed        = discord.Embed(description=build(), color=self.bot.color)
        view.message = await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="roulette",
        description="Bet on roulette", usage="<red|black|number> <amount>", help="economy")
    async def roulette(self, ctx: commands.Context, bet: str, amount: int):
        if amount <= 0:
            return await self._v2(ctx, "> **Amount must be greater than 0...**")
        d = await self.get_user(ctx.author.id, ctx.guild.id)
        if amount > d["wallet"]:
            return await self._v2(ctx, f"> **You only have {d['wallet']:,} coins...**")
        REDS   = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
        result = random.randint(0, 36)
        color  = "green" if result == 0 else ("red" if result in REDS else "black")
        bet    = bet.lower()
        try:
            n = int(bet)
            if not (0 <= n <= 36):
                return await self._v2(ctx, "> **Number must be between 0 and 36...**")
            if n == result:
                win = amount * 35
                await self._wallet(ctx.author.id, ctx.guild.id, win)
                note = f"Straight up win! +**{win:,} coins**"
            else:
                await self._wallet(ctx.author.id, ctx.guild.id, -amount)
                note = f"No luck — lost **{amount:,} coins**"
        except ValueError:
            if bet not in ("red", "black"):
                return await self._v2(ctx, "> **Bet must be `red`, `black`, or a number 0–36...**")
            if bet == color:
                await self._wallet(ctx.author.id, ctx.guild.id, amount)
                note = f"Correct color — won **{amount:,} coins**"
            else:
                await self._wallet(ctx.author.id, ctx.guild.id, -amount)
                note = f"Wrong color — lost **{amount:,} coins**"
        await self._v2(ctx,
            f"**Roulette**\n\n"
            f"> Ball landed on **{result}** ({color})\n"
            f"> {note}"
        )

    @commands.hybrid_command(name="shop",
        description="Browse the item shop", help="economy")
    async def shop(self, ctx: commands.Context):
        tools = [(sid, item) for sid, item in SHOP.items() if item["type"] == "tool"]
        banks = [(sid, item) for sid, item in SHOP.items() if item["type"] == "bank"]
        lines = ["**Shop**", ""]
        lines.append("**Tools & Equipment**")
        for sid, item in tools:
            lines.append(f"> `#{sid}`  **{item['name']}**  —  **{item['price']:,}** coins")
            lines.append(f">       *{item['desc']}*")
        lines.append("")
        lines.append("**Bank Upgrades**")
        for sid, item in banks:
            lines.append(f"> `#{sid}`  **{item['name']}**  —  **{item['price']:,}** coins")
            lines.append(f">       *{item['desc']}*")
        lines.append("")
        lines.append("-# Use `buy <id>` to purchase  ·  e.g. `buy 1` for Fishing Rod")
        await self._v2(ctx, "\n".join(lines))

    @commands.hybrid_command(name="buy",
        description="Buy an item from the shop", usage="<id>", help="economy")
    async def buy(self, ctx: commands.Context, item_id: int):
        if item_id not in SHOP:
            return await self._v2(ctx, f"> **No item with ID #{item_id} — use `shop` to browse...**")
        item = SHOP[item_id]
        d    = await self.get_user(ctx.author.id, ctx.guild.id)
        if d["wallet"] < item["price"]:
            return await self._v2(ctx,
                f"> **You need {item['price']:,} coins but only have {d['wallet']:,}...**"
            )
        if item["type"] == "bank":
            await self._exec(
                "UPDATE economy SET bank_max=bank_max+$1 WHERE user_id=$2 AND guild_id=$3",
                item["amount"], ctx.author.id, ctx.guild.id
            )
            await self._wallet(ctx.author.id, ctx.guild.id, -item["price"])
            new_cap = d["bank_max"] + item["amount"]
            bar, pct = self._bar(d["bank"], new_cap)
            return await self._v2(ctx,
                f"**Purchase — {item['name']}**\n"
                f"\n"
                f"> Paid **{item['price']:,} coins**\n"
                f"> Bank capacity is now **{new_cap:,} coins**\n"
                f"> {bar}  {pct}%"
            )
        if self._has(d, item["key"]):
            return await self._v2(ctx, f"> **You already own a {item['name']}...**")
        await self._wallet(ctx.author.id, ctx.guild.id, -item["price"])
        await self._add_item(ctx.author.id, ctx.guild.id, item["key"])
        await self._v2(ctx,
            f"**Purchase — {item['name']}**\n"
            f"\n"
            f"> Paid **{item['price']:,} coins**\n"
            f"> {item['desc']}"
        )

    @commands.hybrid_command(name="leaderboard", aliases=["lb"],
        description="View the richest users in the server", help="economy")
    async def leaderboard(self, ctx: commands.Context):
        rows = await self._rows(
            "SELECT user_id, wallet+bank AS total FROM economy"
            " WHERE guild_id=$1 ORDER BY total DESC LIMIT 10",
            ctx.guild.id
        )
        if not rows:
            return await self._v2(ctx, "> **No economy data for this server yet...**")
        medals = {1: "1st", 2: "2nd", 3: "3rd"}
        lines  = [f"**Leaderboard — {ctx.guild.name}**", ""]
        for i, row in enumerate(rows, 1):
            member = ctx.guild.get_member(row["user_id"])
            name   = member.name if member else "Unknown"
            rank   = medals.get(i, f"{i}th")
            lines.append(f"> **{rank}**  {name}  —  {row['total']:,} coins")
        await self._v2(ctx, "\n".join(lines))


async def setup(bot):
    await bot.add_cog(economy(bot))