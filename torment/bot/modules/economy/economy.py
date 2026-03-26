from __future__ import annotations

import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord.ext import commands

from bot.helpers.context import TormentContext


def _color(name: str) -> discord.Color:
    raw = os.getenv(name, "").lower().lstrip("#")
    try:
        return discord.Color(int(raw, 16))
    except ValueError:
        return discord.Color.blurple()


DAILY_AMOUNT = 500
WEEKLY_AMOUNT = 2500
WORK_MIN = 100
WORK_MAX = 400
ROB_MIN_BALANCE = 200
ROB_SUCCESS_CHANCE = 0.45
ROB_MIN_PCT = 0.10
ROB_MAX_PCT = 0.35
SLOTS_COST = 50
COINFLIP_MIN = 10

SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "⭐", "💎"]
SLOT_PAYOUTS = {
    "💎": 20,
    "⭐": 10,
    "🍇": 6,
    "🍊": 4,
    "🍋": 3,
    "🍒": 2,
}

WORK_JOBS = [
    "delivered packages",
    "fixed computers",
    "walked dogs",
    "wrote code",
    "drove for a rideshare",
    "sold lemonade",
    "tutored students",
    "mowed lawns",
    "flipped burgers",
    "streamed on Twitch",
]


class Economy(commands.Cog):
    __cog_name__ = "Economy"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def storage(self):
        return self.bot.storage

    async def cog_load(self) -> None:
        pool = self.bot.storage.pool
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS economy_wallets (
                guild_id BIGINT NOT NULL,
                user_id  BIGINT NOT NULL,
                balance  BIGINT NOT NULL DEFAULT 0,
                bank     BIGINT NOT NULL DEFAULT 0,
                bank_cap BIGINT NOT NULL DEFAULT 10000,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS economy_cooldowns (
                guild_id   BIGINT NOT NULL,
                user_id    BIGINT NOT NULL,
                action     TEXT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (guild_id, user_id, action)
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS economy_transactions (
                id         BIGSERIAL PRIMARY KEY,
                guild_id   BIGINT NOT NULL,
                user_id    BIGINT NOT NULL,
                action     TEXT NOT NULL,
                amount     BIGINT NOT NULL,
                note       TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS economy_items (
                guild_id    BIGINT NOT NULL,
                item_id     BIGSERIAL,
                name        TEXT NOT NULL,
                description TEXT,
                price       BIGINT NOT NULL,
                role_id     BIGINT,
                PRIMARY KEY (guild_id, item_id)
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS economy_inventory (
                guild_id BIGINT NOT NULL,
                user_id  BIGINT NOT NULL,
                item_id  BIGINT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (guild_id, user_id, item_id)
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS economy_lottery (
                guild_id BIGINT NOT NULL,
                user_id  BIGINT NOT NULL,
                tickets  INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS economy_pets (
                guild_id  BIGINT NOT NULL,
                user_id   BIGINT NOT NULL,
                pet_type  TEXT NOT NULL,
                name      TEXT NOT NULL,
                hunger    INTEGER NOT NULL DEFAULT 100,
                happiness INTEGER NOT NULL DEFAULT 100,
                level     INTEGER NOT NULL DEFAULT 1,
                xp        INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )


    async def _get_wallet(self, guild_id: int, user_id: int) -> dict[str, Any]:
        row = await self.storage.pool.fetchrow(
            "SELECT * FROM economy_wallets WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )
        if row:
            return dict(row)
        await self.storage.pool.execute(
            "INSERT INTO economy_wallets (guild_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            guild_id, user_id,
        )
        return {"guild_id": guild_id, "user_id": user_id, "balance": 0, "bank": 0, "bank_cap": 10000}

    async def _add_balance(self, guild_id: int, user_id: int, amount: int) -> None:
        await self.storage.pool.execute(
            """
            INSERT INTO economy_wallets (guild_id, user_id, balance)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, user_id) DO UPDATE
            SET balance = economy_wallets.balance + $3
            """,
            guild_id, user_id, amount,
        )

    async def _remove_balance(self, guild_id: int, user_id: int, amount: int) -> bool:
        wallet = await self._get_wallet(guild_id, user_id)
        if wallet["balance"] < amount:
            return False
        await self.storage.pool.execute(
            "UPDATE economy_wallets SET balance = balance - $3 WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id, amount,
        )
        return True

    async def _get_cooldown(self, guild_id: int, user_id: int, action: str) -> datetime | None:
        row = await self.storage.pool.fetchrow(
            "SELECT expires_at FROM economy_cooldowns WHERE guild_id = $1 AND user_id = $2 AND action = $3",
            guild_id, user_id, action,
        )
        if row and row["expires_at"] > datetime.now(timezone.utc):
            return row["expires_at"]
        return None

    async def _set_cooldown(self, guild_id: int, user_id: int, action: str, seconds: int) -> None:
        expires = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        await self.storage.pool.execute(
            """
            INSERT INTO economy_cooldowns (guild_id, user_id, action, expires_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, user_id, action) DO UPDATE SET expires_at = $4
            """,
            guild_id, user_id, action, expires,
        )

    async def _log_transaction(self, guild_id: int, user_id: int, action: str, amount: int, note: str | None = None) -> None:
        await self.storage.pool.execute(
            "INSERT INTO economy_transactions (guild_id, user_id, action, amount, note) VALUES ($1, $2, $3, $4, $5)",
            guild_id, user_id, action, amount, note,
        )

    def _format_cd(self, expires: datetime) -> str:
        remaining = expires - datetime.now(timezone.utc)
        total = int(remaining.total_seconds())
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h {m}m {s}s"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"


    @commands.hybrid_command(
        name="balance",
        aliases=["bal", "wallet"],
        help="View your or another member's wallet and bank balance.",
        extras={"category": "Economy"},
    )
    async def balance(self, ctx: TormentContext, *, member: discord.Member = None) -> None:
        target = member or ctx.author
        wallet = await self._get_wallet(ctx.guild.id, target.id)
        embed = discord.Embed(
            title=f"{target.display_name}'s balance",
            color=_color("EMBED_COLOR"),
        )
        embed.add_field(name="Wallet", value=f"**{wallet['balance']:,}** coins", inline=True)
        embed.add_field(name="Bank", value=f"**{wallet['bank']:,}** / **{wallet['bank_cap']:,}** coins", inline=True)
        embed.add_field(name="Net Worth", value=f"**{wallet['balance'] + wallet['bank']:,}** coins", inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="daily",
        help="Claim your daily coin reward. Resets every 24 hours.",
        extras={"category": "Economy"},
    )
    async def daily(self, ctx: TormentContext) -> None:
        cd = await self._get_cooldown(ctx.guild.id, ctx.author.id, "daily")
        if cd:
            return await ctx.warn(f"You already claimed your daily. Come back in **{self._format_cd(cd)}**.")
        await self._add_balance(ctx.guild.id, ctx.author.id, DAILY_AMOUNT)
        await self._set_cooldown(ctx.guild.id, ctx.author.id, "daily", 86400)
        await self._log_transaction(ctx.guild.id, ctx.author.id, "daily", DAILY_AMOUNT)
        await ctx.success(f"Successfully claimed your daily reward of **{DAILY_AMOUNT:,}** coins.")

    @commands.hybrid_command(
        name="weekly",
        help="Claim your weekly coin reward. Resets every 7 days.",
        extras={"category": "Economy"},
    )
    async def weekly(self, ctx: TormentContext) -> None:
        cd = await self._get_cooldown(ctx.guild.id, ctx.author.id, "weekly")
        if cd:
            return await ctx.warn(f"You already claimed your weekly. Come back in **{self._format_cd(cd)}**.")
        await self._add_balance(ctx.guild.id, ctx.author.id, WEEKLY_AMOUNT)
        await self._set_cooldown(ctx.guild.id, ctx.author.id, "weekly", 604800)
        await self._log_transaction(ctx.guild.id, ctx.author.id, "weekly", WEEKLY_AMOUNT)
        await ctx.success(f"Successfully claimed your weekly reward of **{WEEKLY_AMOUNT:,}** coins.")

    @commands.hybrid_command(
        name="work",
        help="Work a job to earn coins. Has a 1 hour cooldown.",
        extras={"category": "Economy"},
    )
    async def work(self, ctx: TormentContext) -> None:
        cd = await self._get_cooldown(ctx.guild.id, ctx.author.id, "work")
        if cd:
            return await ctx.warn(f"You're still tired from your last shift. Rest for **{self._format_cd(cd)}**.")
        amount = random.randint(WORK_MIN, WORK_MAX)
        job = random.choice(WORK_JOBS)
        await self._add_balance(ctx.guild.id, ctx.author.id, amount)
        await self._set_cooldown(ctx.guild.id, ctx.author.id, "work", 3600)
        await self._log_transaction(ctx.guild.id, ctx.author.id, "work", amount, job)
        embed = discord.Embed(
            description=f"You {job} and earned **{amount:,}** coins.",
            color=_color("EMBED_SUCCESS_COLOR"),
        )
        await ctx.send(embed=embed)


    @commands.hybrid_command(
        name="deposit",
        aliases=["dep"],
        help="Deposit coins from your wallet into your bank.",
        extras={"category": "Economy"},
    )
    async def deposit(self, ctx: TormentContext, amount: str) -> None:
        wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        if amount.lower() == "all":
            amt = wallet["balance"]
        else:
            try:
                amt = int(amount)
            except ValueError:
                return await ctx.warn("Provide a valid amount or `all`.")
        if amt <= 0:
            return await ctx.warn("Amount must be greater than 0.")
        if wallet["balance"] < amt:
            return await ctx.warn(f"You only have **{wallet['balance']:,}** coins in your wallet.")
        space = wallet["bank_cap"] - wallet["bank"]
        if space <= 0:
            return await ctx.warn("Your bank is full. Upgrade your bank cap first.")
        deposited = min(amt, space)
        await self.storage.pool.execute(
            "UPDATE economy_wallets SET balance = balance - $3, bank = bank + $3 WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id, deposited,
        )
        await ctx.success(f"Successfully deposited **{deposited:,}** coins into your bank.")

    @commands.hybrid_command(
        name="withdraw",
        help="Withdraw coins from your bank into your wallet.",
        extras={"category": "Economy"},
    )
    async def withdraw(self, ctx: TormentContext, amount: str) -> None:
        wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        if amount.lower() == "all":
            amt = wallet["bank"]
        else:
            try:
                amt = int(amount)
            except ValueError:
                return await ctx.warn("Provide a valid amount or `all`.")
        if amt <= 0:
            return await ctx.warn("Amount must be greater than 0.")
        if wallet["bank"] < amt:
            return await ctx.warn(f"You only have **{wallet['bank']:,}** coins in your bank.")
        await self.storage.pool.execute(
            "UPDATE economy_wallets SET balance = balance + $3, bank = bank - $3 WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id, amt,
        )
        await ctx.success(f"Successfully withdrew **{amt:,}** coins from your bank.")

    @commands.hybrid_command(
        name="pay",
        aliases=["give"],
        help="Send coins from your wallet to another member.",
        extras={"category": "Economy"},
    )
    async def pay(self, ctx: TormentContext, member: discord.Member, amount: int) -> None:
        if member.id == ctx.author.id:
            return await ctx.warn("You can't pay yourself.")
        if member.bot:
            return await ctx.warn("You can't pay bots.")
        if amount <= 0:
            return await ctx.warn("Amount must be greater than 0.")
        removed = await self._remove_balance(ctx.guild.id, ctx.author.id, amount)
        if not removed:
            wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
            return await ctx.warn(f"You only have **{wallet['balance']:,}** coins in your wallet.")
        await self._add_balance(ctx.guild.id, member.id, amount)
        await self._log_transaction(ctx.guild.id, ctx.author.id, "pay_out", amount, f"to {member.id}")
        await self._log_transaction(ctx.guild.id, member.id, "pay_in", amount, f"from {ctx.author.id}")
        await ctx.success(f"Successfully sent **{amount:,}** coins to {member.mention}.")


    @commands.hybrid_command(
        name="rob",
        help="Attempt to rob coins from another member's wallet. Has a 10 minute cooldown.",
        extras={"category": "Economy"},
    )
    async def rob(self, ctx: TormentContext, *, member: discord.Member) -> None:
        if member.id == ctx.author.id:
            return await ctx.warn("You can't rob yourself.")
        if member.bot:
            return await ctx.warn("You can't rob bots.")
        cd = await self._get_cooldown(ctx.guild.id, ctx.author.id, "rob")
        if cd:
            return await ctx.warn(f"You're laying low after your last heist. Wait **{self._format_cd(cd)}**.")
        target_wallet = await self._get_wallet(ctx.guild.id, member.id)
        if target_wallet["balance"] < ROB_MIN_BALANCE:
            return await ctx.warn(f"{member.mention} doesn't have enough coins to rob (minimum **{ROB_MIN_BALANCE:,}**).")
        await self._set_cooldown(ctx.guild.id, ctx.author.id, "rob", 600)
        if random.random() < ROB_SUCCESS_CHANCE:
            pct = random.uniform(ROB_MIN_PCT, ROB_MAX_PCT)
            stolen = int(target_wallet["balance"] * pct)
            stolen = max(1, stolen)
            await self._remove_balance(ctx.guild.id, member.id, stolen)
            await self._add_balance(ctx.guild.id, ctx.author.id, stolen)
            await self._log_transaction(ctx.guild.id, ctx.author.id, "rob_success", stolen, f"from {member.id}")
            embed = discord.Embed(
                description=f"You successfully robbed **{stolen:,}** coins from {member.mention}.",
                color=_color("EMBED_SUCCESS_COLOR"),
            )
        else:
            fine = random.randint(50, 200)
            await self._remove_balance(ctx.guild.id, ctx.author.id, fine)
            await self._log_transaction(ctx.guild.id, ctx.author.id, "rob_fail", -fine, f"caught robbing {member.id}")
            embed = discord.Embed(
                description=f"You got caught trying to rob {member.mention} and paid a **{fine:,}** coin fine.",
                color=_color("EMBED_DENY_COLOR"),
            )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="slots",
        help=f"Spin the slot machine. Costs {SLOTS_COST} coins per spin.",
        extras={"category": "Economy"},
    )
    async def slots(self, ctx: TormentContext, bet: int = SLOTS_COST) -> None:
        if bet < SLOTS_COST:
            return await ctx.warn(f"Minimum bet is **{SLOTS_COST:,}** coins.")
        removed = await self._remove_balance(ctx.guild.id, ctx.author.id, bet)
        if not removed:
            wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
            return await ctx.warn(f"You only have **{wallet['balance']:,}** coins in your wallet.")
        reels = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
        display = " | ".join(reels)
        if reels[0] == reels[1] == reels[2]:
            multiplier = SLOT_PAYOUTS.get(reels[0], 2)
            winnings = bet * multiplier
            await self._add_balance(ctx.guild.id, ctx.author.id, winnings)
            await self._log_transaction(ctx.guild.id, ctx.author.id, "slots_win", winnings - bet)
            embed = discord.Embed(
                title="🎰 Slot Machine",
                description=f"[ {display} ]\n\nJackpot! You won **{winnings:,}** coins! (x{multiplier})",
                color=_color("EMBED_SUCCESS_COLOR"),
            )
        elif reels[0] == reels[1] or reels[1] == reels[2]:
            winnings = int(bet * 1.5)
            await self._add_balance(ctx.guild.id, ctx.author.id, winnings)
            await self._log_transaction(ctx.guild.id, ctx.author.id, "slots_partial", winnings - bet)
            embed = discord.Embed(
                title="🎰 Slot Machine",
                description=f"[ {display} ]\n\nTwo of a kind! You won **{winnings:,}** coins.",
                color=_color("EMBED_INFO_COLOR"),
            )
        else:
            await self._log_transaction(ctx.guild.id, ctx.author.id, "slots_loss", -bet)
            embed = discord.Embed(
                title="🎰 Slot Machine",
                description=f"[ {display} ]\n\nNo match. You lost **{bet:,}** coins.",
                color=_color("EMBED_DENY_COLOR"),
            )
        await ctx.send(embed=embed)


    @commands.hybrid_command(
        name="coinflip",
        aliases=["cf"],
        help="Flip a coin and bet on heads or tails.",
        extras={"category": "Economy"},
    )
    async def coinflip(self, ctx: TormentContext, side: str, bet: int) -> None:
        side = side.lower()
        if side not in ("heads", "tails", "h", "t"):
            return await ctx.warn("Choose `heads` or `tails`.")
        if bet < COINFLIP_MIN:
            return await ctx.warn(f"Minimum bet is **{COINFLIP_MIN:,}** coins.")
        removed = await self._remove_balance(ctx.guild.id, ctx.author.id, bet)
        if not removed:
            wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
            return await ctx.warn(f"You only have **{wallet['balance']:,}** coins in your wallet.")
        result = random.choice(["heads", "tails"])
        chosen = "heads" if side in ("heads", "h") else "tails"
        coin_emoji = "🪙"
        if chosen == result:
            await self._add_balance(ctx.guild.id, ctx.author.id, bet * 2)
            await self._log_transaction(ctx.guild.id, ctx.author.id, "coinflip_win", bet)
            embed = discord.Embed(
                description=f"{coin_emoji} The coin landed on **{result}**. You won **{bet:,}** coins.",
                color=_color("EMBED_SUCCESS_COLOR"),
            )
        else:
            await self._log_transaction(ctx.guild.id, ctx.author.id, "coinflip_loss", -bet)
            embed = discord.Embed(
                description=f"{coin_emoji} The coin landed on **{result}**. You lost **{bet:,}** coins.",
                color=_color("EMBED_DENY_COLOR"),
            )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="leaderboard",
        aliases=["lb", "rich"],
        help="View the richest members in the server.",
        extras={"category": "Economy"},
    )
    async def leaderboard(self, ctx: TormentContext) -> None:
        rows = await self.storage.pool.fetch(
            """
            SELECT user_id, balance, bank
            FROM economy_wallets
            WHERE guild_id = $1
            ORDER BY (balance + bank) DESC
            LIMIT 15
            """,
            ctx.guild.id,
        )
        if not rows:
            return await ctx.warn("No economy data found for this server yet.")
        lines = []
        for i, row in enumerate(rows, 1):
            member = ctx.guild.get_member(row["user_id"])
            name = member.display_name if member else f"<@{row['user_id']}>"
            net = row["balance"] + row["bank"]
            lines.append(f"`{i}.` **{name}** — {net:,} coins")
        embed = discord.Embed(
            title=f"💰 {ctx.guild.name} Richest Members",
            description="\n".join(lines),
            color=_color("EMBED_COLOR"),
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="transactions",
        help="View your recent transaction history.",
        extras={"category": "Economy"},
    )
    async def transactions(self, ctx: TormentContext, *, member: discord.Member = None) -> None:
        target = member or ctx.author
        rows = await self.storage.pool.fetch(
            """
            SELECT action, amount, note, created_at
            FROM economy_transactions
            WHERE guild_id = $1 AND user_id = $2
            ORDER BY created_at DESC
            LIMIT 20
            """,
            ctx.guild.id, target.id,
        )
        if not rows:
            return await ctx.warn(f"No transaction history found for {target.mention}.")
        lines = []
        for row in rows:
            sign = "+" if row["amount"] >= 0 else ""
            ts = row["created_at"].strftime("%m/%d %H:%M")
            note = f" ({row['note']})" if row["note"] else ""
            lines.append(f"`{ts}` **{row['action']}**{note}: {sign}{row['amount']:,}")
        embed = discord.Embed(
            title=f"{target.display_name}'s Transactions",
            description="\n".join(lines),
            color=_color("EMBED_COLOR"),
        )
        await ctx.send(embed=embed)


    @commands.group(
        name="shop",
        invoke_without_command=True,
        help="Browse the server shop.",
        extras={"category": "Economy"},
    )
    async def shop(self, ctx: TormentContext) -> None:
        rows = await self.storage.pool.fetch(
            "SELECT * FROM economy_items WHERE guild_id = $1 ORDER BY price ASC",
            ctx.guild.id,
        )
        if not rows:
            return await ctx.warn("The shop is empty. Admins can add items with `shop add`.")
        lines = []
        for row in rows:
            role_text = ""
            if row["role_id"]:
                role = ctx.guild.get_role(row["role_id"])
                role_text = f" → {role.mention}" if role else ""
            desc = f" — *{row['description']}*" if row["description"] else ""
            lines.append(f"`#{row['item_id']}` **{row['name']}**{desc} — **{row['price']:,}** coins{role_text}")
        embed = discord.Embed(
            title=f"🛒 {ctx.guild.name} Shop",
            description="\n".join(lines),
            color=_color("EMBED_COLOR"),
        )
        embed.set_footer(text="Use 'buy <item id>' to purchase an item.")
        await ctx.send(embed=embed)

    @shop.command(
        name="add",
        help="Add an item to the shop.",
        extras={"category": "Economy"},
    )
    @commands.has_permissions(manage_guild=True)
    async def shop_add(self, ctx: TormentContext, price: int, role: discord.Role = None, *, name: str) -> None:
        if price <= 0:
            return await ctx.warn("Price must be greater than 0.")
        row = await self.storage.pool.fetchrow(
            """
            INSERT INTO economy_items (guild_id, name, price, role_id)
            VALUES ($1, $2, $3, $4)
            RETURNING item_id
            """,
            ctx.guild.id, name, price, role.id if role else None,
        )
        await ctx.success(f"Successfully added **{name}** to the shop for **{price:,}** coins (ID: `{row['item_id']}`).")

    @shop.command(
        name="remove",
        help="Remove an item from the shop.",
        extras={"category": "Economy"},
    )
    @commands.has_permissions(manage_guild=True)
    async def shop_remove(self, ctx: TormentContext, item_id: int) -> None:
        result = await self.storage.pool.execute(
            "DELETE FROM economy_items WHERE guild_id = $1 AND item_id = $2",
            ctx.guild.id, item_id,
        )
        if result == "DELETE 0":
            return await ctx.warn(f"No item with ID `{item_id}` found in the shop.")
        await self.storage.pool.execute(
            "DELETE FROM economy_inventory WHERE guild_id = $1 AND item_id = $2",
            ctx.guild.id, item_id,
        )
        await ctx.success(f"Successfully removed item `{item_id}` from the shop.")

    @commands.hybrid_command(
        name="buy",
        help="Purchase an item from the shop.",
        extras={"category": "Economy"},
    )
    async def buy(self, ctx: TormentContext, item_id: int) -> None:
        item = await self.storage.pool.fetchrow(
            "SELECT * FROM economy_items WHERE guild_id = $1 AND item_id = $2",
            ctx.guild.id, item_id,
        )
        if not item:
            return await ctx.warn(f"No item with ID `{item_id}` found in the shop.")
        removed = await self._remove_balance(ctx.guild.id, ctx.author.id, item["price"])
        if not removed:
            wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
            return await ctx.warn(f"You need **{item['price']:,}** coins but only have **{wallet['balance']:,}**.")
        await self.storage.pool.execute(
            """
            INSERT INTO economy_inventory (guild_id, user_id, item_id, quantity)
            VALUES ($1, $2, $3, 1)
            ON CONFLICT (guild_id, user_id, item_id) DO UPDATE SET quantity = economy_inventory.quantity + 1
            """,
            ctx.guild.id, ctx.author.id, item_id,
        )
        await self._log_transaction(ctx.guild.id, ctx.author.id, "buy", -item["price"], item["name"])
        if item["role_id"]:
            role = ctx.guild.get_role(item["role_id"])
            if role:
                try:
                    await ctx.author.add_roles(role, reason=f"Purchased {item['name']} from shop")
                except discord.HTTPException:
                    pass
        await ctx.success(f"Successfully purchased **{item['name']}** for **{item['price']:,}** coins.")


    @commands.hybrid_command(
        name="inventory",
        help="View your or another member's inventory.",
        extras={"category": "Economy"},
    )
    async def inventory(self, ctx: TormentContext, *, member: discord.Member = None) -> None:
        target = member or ctx.author
        rows = await self.storage.pool.fetch(
            """
            SELECT i.item_id, i.name, i.description, inv.quantity
            FROM economy_inventory inv
            JOIN economy_items i ON i.item_id = inv.item_id AND i.guild_id = inv.guild_id
            WHERE inv.guild_id = $1 AND inv.user_id = $2
            ORDER BY i.name
            """,
            ctx.guild.id, target.id,
        )
        if not rows:
            return await ctx.warn(f"{target.mention} has no items in their inventory.")
        lines = []
        for row in rows:
            desc = f" — *{row['description']}*" if row["description"] else ""
            lines.append(f"`#{row['item_id']}` **{row['name']}**{desc} x{row['quantity']}")
        embed = discord.Embed(
            title=f"{target.display_name}'s Inventory",
            description="\n".join(lines),
            color=_color("EMBED_COLOR"),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.group(
        name="eco",
        invoke_without_command=True,
        help="Economy admin commands.",
        extras={"category": "Economy"},
    )
    @commands.has_permissions(manage_guild=True)
    async def eco(self, ctx: TormentContext) -> None:
        await ctx.send_help(ctx.command)

    @eco.command(
        name="give",
        help="Give coins to a member.",
        extras={"category": "Economy"},
    )
    @commands.has_permissions(manage_guild=True)
    async def eco_give(self, ctx: TormentContext, member: discord.Member, amount: int) -> None:
        if amount <= 0:
            return await ctx.warn("Amount must be greater than 0.")
        await self._add_balance(ctx.guild.id, member.id, amount)
        await self._log_transaction(ctx.guild.id, member.id, "admin_give", amount, f"by {ctx.author.id}")
        await ctx.success(f"Successfully gave **{amount:,}** coins to {member.mention}.")

    @eco.command(
        name="take",
        help="Remove coins from a member's wallet.",
        extras={"category": "Economy"},
    )
    @commands.has_permissions(manage_guild=True)
    async def eco_take(self, ctx: TormentContext, member: discord.Member, amount: int) -> None:
        if amount <= 0:
            return await ctx.warn("Amount must be greater than 0.")
        wallet = await self._get_wallet(ctx.guild.id, member.id)
        actual = min(amount, wallet["balance"])
        if actual <= 0:
            return await ctx.warn(f"{member.mention} has no coins in their wallet.")
        await self._remove_balance(ctx.guild.id, member.id, actual)
        await self._log_transaction(ctx.guild.id, member.id, "admin_take", -actual, f"by {ctx.author.id}")
        await ctx.success(f"Successfully removed **{actual:,}** coins from {member.mention}.")

    @eco.command(
        name="set",
        help="Set a member's wallet balance to a specific amount.",
        extras={"category": "Economy"},
    )
    @commands.has_permissions(manage_guild=True)
    async def eco_set(self, ctx: TormentContext, member: discord.Member, amount: int) -> None:
        if amount < 0:
            return await ctx.warn("Amount cannot be negative.")
        await self.storage.pool.execute(
            """
            INSERT INTO economy_wallets (guild_id, user_id, balance)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET balance = $3
            """,
            ctx.guild.id, member.id, amount,
        )
        await ctx.success(f"Successfully set {member.mention}'s wallet balance to **{amount:,}** coins.")

    @eco.command(
        name="reset",
        help="Reset a member's entire economy data.",
        extras={"category": "Economy"},
    )
    @commands.has_permissions(manage_guild=True)
    async def eco_reset(self, ctx: TormentContext, *, member: discord.Member) -> None:
        confirmed = await ctx.confirm(f"Are you sure you want to reset all economy data for {member.mention}?")
        if not confirmed:
            return await ctx.warn("Reset cancelled.")
        await self.storage.pool.execute(
            "DELETE FROM economy_wallets WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id,
        )
        await self.storage.pool.execute(
            "DELETE FROM economy_cooldowns WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id,
        )
        await self.storage.pool.execute(
            "DELETE FROM economy_inventory WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id,
        )
        await ctx.success(f"Successfully reset all economy data for {member.mention}.")


    # ── helpers ──────────────────────────────────────────────────────────────

    def _parse_bet(self, amount_str: str, balance: int) -> int | None:
        if amount_str.lower() == "all":
            return balance
        try:
            return int(amount_str.replace(",", ""))
        except ValueError:
            return None

    # ── bank ─────────────────────────────────────────────────────────────────

    @commands.group(
        name="bank",
        invoke_without_command=True,
        help="View your bank account details.",
        extras={"category": "Economy"},
    )
    async def bank(self, ctx: TormentContext) -> None:
        wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        cd = await self._get_cooldown(ctx.guild.id, ctx.author.id, "interest")
        interest_status = f"Available in **{self._format_cd(cd)}**" if cd else "**Available now!**"
        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Bank Account",
            description=(
                f":credit_card: Balance: **{wallet['bank']:,}** / **{wallet['bank_cap']:,}** coins\n"
                f":euro: Wallet: **{wallet['balance']:,}** coins\n"
                f":bar_chart: Interest Status: {interest_status}"
            ),
            color=_color("EMBED_COLOR"),
        )
        await ctx.send(embed=embed)

    @bank.command(
        name="interest",
        aliases=["claim"],
        help="Claim your daily 1% bank interest.",
        extras={"category": "Economy"},
    )
    async def bank_interest(self, ctx: TormentContext) -> None:
        cd = await self._get_cooldown(ctx.guild.id, ctx.author.id, "interest")
        if cd:
            return await ctx.warn(f"You can claim interest again in **{self._format_cd(cd)}**.")
        wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        if wallet["bank"] <= 0:
            return await ctx.warn("You need coins in your bank to earn interest.")
        interest = max(1, int(wallet["bank"] * 0.01))
        await self._add_balance(ctx.guild.id, ctx.author.id, interest)
        await self._set_cooldown(ctx.guild.id, ctx.author.id, "interest", 86400)
        await self._log_transaction(ctx.guild.id, ctx.author.id, "interest", interest)
        await ctx.success(f"Successfully claimed **{interest:,}** coins in bank interest.")

    @bank.command(
        name="upgrade",
        help="Upgrade your bank capacity (costs 20% of current cap).",
        extras={"category": "Economy"},
    )
    async def bank_upgrade(self, ctx: TormentContext) -> None:
        wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        upgrade_cost = int(wallet["bank_cap"] * 0.2)
        new_cap = int(wallet["bank_cap"] * 1.5)
        if wallet["balance"] < upgrade_cost:
            return await ctx.warn(f"You need **{upgrade_cost:,}** coins to upgrade your bank capacity.")
        confirmed = await ctx.confirm(
            f"Upgrade bank capacity to **{new_cap:,}** coins for **{upgrade_cost:,}** coins?"
        )
        if not confirmed:
            return await ctx.warn("Upgrade cancelled.")
        await self._remove_balance(ctx.guild.id, ctx.author.id, upgrade_cost)
        await self.storage.pool.execute(
            "UPDATE economy_wallets SET bank_cap = $1 WHERE guild_id = $2 AND user_id = $3",
            new_cap, ctx.guild.id, ctx.author.id,
        )
        await ctx.success(f"Successfully upgraded your bank capacity to **{new_cap:,}** coins.")


    # ── gamble ────────────────────────────────────────────────────────────────

    @commands.hybrid_group(
        name="gamble",
        invoke_without_command=True,
        help="View available gambling games.",
        extras={"category": "Economy"},
    )
    async def gamble(self, ctx: TormentContext) -> None:
        embed = discord.Embed(
            title="🎰 Game Center",
            description=(
                "**:game_die: Dice:** `gamble dice normal` | `gamble dice higher` | `gamble dice match`\n"
                "**:coin: Coinflip:** `coinflip` — 2x payout\n"
                "**:slot_machine: Slots:** `slots` — multi-line wins\n"
                "**:ferris_wheel: Wheel:** `gamble wheel` — spin to win\n"
                "**:game_die: Roulette:** `gamble roulette` — bet & win\n"
                "**:chart_with_upwards_trend: Crash:** `gamble crash` — cash out in time\n"
                "**:arrow_up_down: Over/Under:** `gamble overunder` — guess high or low\n"
                "**:tickets: Scratch:** `gamble scratch` — reveal to win\n"
                "**:spades: Poker Dice:** `gamble poker` — poker hands\n"
                "**:horse_racing: Horse Race:** `gamble race` — bet on winners\n"
                "**:ladder: Ladder:** `gamble ladder` — climb for multipliers\n"
                "**:bomb: Mines:** `gamble mines` — avoid explosions\n"
            ),
            color=_color("EMBED_COLOR"),
        )
        await ctx.send(embed=embed)

    @gamble.group(
        name="dice",
        invoke_without_command=True,
        help="Dice gambling games.",
        extras={"category": "Economy"},
    )
    async def gamble_dice(self, ctx: TormentContext) -> None:
        embed = discord.Embed(
            title="🎲 Dice Games",
            description=(
                "`gamble dice normal <amount>` — roll 1-6, win on 4+ (2x)\n"
                "`gamble dice higher <amount>` — bet if next roll is higher (2x)\n"
                "`gamble dice match <number> <amount>` — exact match (5x)"
            ),
            color=_color("EMBED_COLOR"),
        )
        await ctx.send(embed=embed)

    @gamble_dice.command(
        name="normal",
        help="Roll a die. Win on 4 or higher (2x).",
        extras={"category": "Economy"},
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def dice_normal(self, ctx: TormentContext, amount: str) -> None:
        import asyncio
        wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        bet = self._parse_bet(amount, wallet["balance"])
        if bet is None or bet < 100:
            return await ctx.warn("Minimum bet is **100** coins.")
        if wallet["balance"] < bet:
            return await ctx.warn(f"You only have **{wallet['balance']:,}** coins.")
        await self._remove_balance(ctx.guild.id, ctx.author.id, bet)
        embed = discord.Embed(title="🎲 Dice Roll", color=_color("EMBED_COLOR"))
        embed.add_field(name="Your Bet", value=f"**{bet:,}** coins")
        msg = await ctx.send(embed=embed)
        for _ in range(3):
            embed.description = f"Rolling... **{random.randint(1, 6)}**!"
            await msg.edit(embed=embed)
            await asyncio.sleep(0.5)
        won = random.random() < 0.45
        final_roll = random.randint(4, 6) if won else random.randint(1, 3)
        if won:
            await self._add_balance(ctx.guild.id, ctx.author.id, bet * 2)
            await self._log_transaction(ctx.guild.id, ctx.author.id, "dice_win", bet)
        else:
            await self._log_transaction(ctx.guild.id, ctx.author.id, "dice_loss", -bet)
        embed.description = (
            f"🎲 You rolled a **{final_roll}**!\n\n"
            f"{'🎉 You won' if won else '😢 You lost'} **{bet:,}** coins!"
        )
        embed.color = _color("EMBED_SUCCESS_COLOR") if won else _color("EMBED_DENY_COLOR")
        await msg.edit(embed=embed)

    @gamble_dice.command(
        name="match",
        help="Match the exact number for 5x payout.",
        extras={"category": "Economy"},
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def dice_match(self, ctx: TormentContext, number: int, amount: str) -> None:
        import asyncio
        if not 1 <= number <= 6:
            return await ctx.warn("Choose a number between 1 and 6.")
        wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        bet = self._parse_bet(amount, wallet["balance"])
        if bet is None or bet < 100:
            return await ctx.warn("Minimum bet is **100** coins.")
        if wallet["balance"] < bet:
            return await ctx.warn(f"You only have **{wallet['balance']:,}** coins.")
        await self._remove_balance(ctx.guild.id, ctx.author.id, bet)
        embed = discord.Embed(title="🎲 Dice Match", color=_color("EMBED_COLOR"))
        embed.add_field(name="Your Bet", value=f"**{bet:,}** coins on **{number}**")
        msg = await ctx.send(embed=embed)
        for _ in range(3):
            embed.description = f"Rolling... **{random.randint(1, 6)}**!"
            await msg.edit(embed=embed)
            await asyncio.sleep(0.5)
        won = random.random() < 0.15
        final_roll = number if won else random.choice([x for x in range(1, 7) if x != number])
        if won:
            await self._add_balance(ctx.guild.id, ctx.author.id, bet * 5)
            await self._log_transaction(ctx.guild.id, ctx.author.id, "dice_match_win", bet * 4)
        else:
            await self._log_transaction(ctx.guild.id, ctx.author.id, "dice_match_loss", -bet)
        embed.description = (
            f"🎲 You rolled a **{final_roll}**!\n\n"
            f"{'🎉 You won' if won else '😢 You lost'} **{bet:,}** coins!"
            + (" (5x payout)" if won else "")
        )
        embed.color = _color("EMBED_SUCCESS_COLOR") if won else _color("EMBED_DENY_COLOR")
        await msg.edit(embed=embed)

    @gamble_dice.command(
        name="higher",
        help="Bet whether the next dice roll will be higher than the first.",
        extras={"category": "Economy"},
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def dice_higher(self, ctx: TormentContext, amount: str) -> None:
        import asyncio
        wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        bet = self._parse_bet(amount, wallet["balance"])
        if bet is None or bet < 100:
            return await ctx.warn("Minimum bet is **100** coins.")
        if wallet["balance"] < bet:
            return await ctx.warn(f"You only have **{wallet['balance']:,}** coins.")
        first_roll = random.randint(1, 6)
        embed = discord.Embed(
            title="🎲 Higher or Lower",
            description=f"First roll: **{first_roll}**\nWill the next roll be higher? React 👍 yes / 👎 no",
            color=_color("EMBED_COLOR"),
        )
        embed.add_field(name="Your Bet", value=f"**{bet:,}** coins")
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")
        try:
            reaction, _ = await ctx.bot.wait_for(
                "reaction_add",
                timeout=15.0,
                check=lambda r, u: u == ctx.author and str(r.emoji) in ["👍", "👎"] and r.message.id == msg.id,
            )
            bet_higher = str(reaction.emoji) == "👍"
        except asyncio.TimeoutError:
            return await ctx.warn("Time's up! Bet cancelled.")
        await self._remove_balance(ctx.guild.id, ctx.author.id, bet)
        await asyncio.sleep(0.5)
        final_roll = random.randint(1, 6)
        won = (bet_higher and final_roll > first_roll) or (not bet_higher and final_roll < first_roll)
        if won:
            await self._add_balance(ctx.guild.id, ctx.author.id, bet * 2)
            await self._log_transaction(ctx.guild.id, ctx.author.id, "dice_higher_win", bet)
        else:
            await self._log_transaction(ctx.guild.id, ctx.author.id, "dice_higher_loss", -bet)
        embed.description = (
            f"First roll: **{first_roll}** → Final roll: **{final_roll}**\n\n"
            f"{'🎉 You won' if won else '😢 You lost'} **{bet:,}** coins!"
        )
        embed.color = _color("EMBED_SUCCESS_COLOR") if won else _color("EMBED_DENY_COLOR")
        await msg.edit(embed=embed)


    @gamble.command(
        name="wheel",
        help="Spin the wheel of fortune.",
        extras={"category": "Economy"},
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def gamble_wheel(self, ctx: TormentContext, amount: str) -> None:
        import asyncio
        wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        bet = self._parse_bet(amount, wallet["balance"])
        if bet is None or bet < 100:
            return await ctx.warn("Minimum bet is **100** coins.")
        if wallet["balance"] < bet:
            return await ctx.warn(f"You only have **{wallet['balance']:,}** coins.")
        await self._remove_balance(ctx.guild.id, ctx.author.id, bet)
        segments = [
            {"multiplier": 0.0, "weight": 30, "emoji": "💀"},
            {"multiplier": 0.5, "weight": 25, "emoji": "😢"},
            {"multiplier": 1.0, "weight": 20, "emoji": "🔄"},
            {"multiplier": 2.0, "weight": 15, "emoji": "💰"},
            {"multiplier": 3.0, "weight": 8,  "emoji": "🎉"},
            {"multiplier": 5.0, "weight": 2,  "emoji": "💎"},
        ]
        embed = discord.Embed(title="🎡 Wheel of Fortune", color=_color("EMBED_COLOR"))
        embed.add_field(name="Your Bet", value=f"**{bet:,}** coins")
        msg = await ctx.send(embed=embed)
        for _ in range(3):
            seg = random.choice(segments)
            embed.description = f"Spinning... {seg['emoji']} **{seg['multiplier']}x**"
            await msg.edit(embed=embed)
            await asyncio.sleep(0.7)
        final = random.choices(segments, weights=[s["weight"] for s in segments])[0]
        win_amount = int(bet * final["multiplier"])
        if win_amount > 0:
            await self._add_balance(ctx.guild.id, ctx.author.id, win_amount)
        net = win_amount - bet
        await self._log_transaction(ctx.guild.id, ctx.author.id, "wheel", net)
        embed.description = f"Landed on: {final['emoji']} **{final['multiplier']}x**\n\n"
        if win_amount > bet:
            embed.description += f"🎉 You won **{win_amount:,}** coins!"
            embed.color = _color("EMBED_SUCCESS_COLOR")
        elif win_amount == bet:
            embed.description += "🔄 You got your money back!"
        elif win_amount > 0:
            embed.description += f"😢 You lost **{bet - win_amount:,}** coins."
            embed.color = _color("EMBED_DENY_COLOR")
        else:
            embed.description += f"💀 You lost **{bet:,}** coins."
            embed.color = _color("EMBED_DENY_COLOR")
        await msg.edit(embed=embed)

    @gamble.command(
        name="roulette",
        help="Play roulette. Bet on red/black, even/odd, 1st/2nd/3rd dozen, or a number 0-36.",
        extras={"category": "Economy"},
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def gamble_roulette(self, ctx: TormentContext, bet_type: str, amount: str) -> None:
        import asyncio
        wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        bet = self._parse_bet(amount, wallet["balance"])
        if bet is None or bet < 100:
            return await ctx.warn("Minimum bet is **100** coins.")
        if wallet["balance"] < bet:
            return await ctx.warn(f"You only have **{wallet['balance']:,}** coins.")
        red_numbers = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
        numbers = {
            n: {
                "color": "green" if n == 0 else ("red" if n in red_numbers else "black"),
                "dozen": None if n == 0 else ("1st" if n <= 12 else "2nd" if n <= 24 else "3rd"),
                "even": n % 2 == 0 and n != 0,
            }
            for n in range(37)
        }
        bt = bet_type.lower()
        if bt in ("red", "black"):
            multiplier = 2
            valid = [n for n, p in numbers.items() if p["color"] == bt]
        elif bt in ("even", "odd"):
            multiplier = 2
            valid = [n for n, p in numbers.items() if (p["even"] == (bt == "even")) and n != 0]
        elif bt in ("1st", "2nd", "3rd"):
            multiplier = 3
            valid = [n for n, p in numbers.items() if p["dozen"] == bt]
        else:
            try:
                num = int(bt)
                if not 0 <= num <= 36:
                    raise ValueError
                multiplier = 35
                valid = [num]
            except ValueError:
                return await ctx.warn("Invalid bet. Choose: red/black, even/odd, 1st/2nd/3rd, or a number 0-36.")
        await self._remove_balance(ctx.guild.id, ctx.author.id, bet)
        embed = discord.Embed(title="🎰 Roulette", color=_color("EMBED_COLOR"))
        embed.add_field(name="Your Bet", value=f"**{bet:,}** coins on **{bet_type}**")
        msg = await ctx.send(embed=embed)
        for _ in range(3):
            n = random.randint(0, 36)
            embed.description = f"Spinning... **{n}** {numbers[n]['color']}!"
            await msg.edit(embed=embed)
            await asyncio.sleep(0.7)
        won = random.random() < (len(valid) / 38)
        final = random.choice(valid) if won else random.choice([n for n in range(37) if n not in valid])
        if won:
            await self._add_balance(ctx.guild.id, ctx.author.id, bet * multiplier)
            await self._log_transaction(ctx.guild.id, ctx.author.id, "roulette_win", bet * (multiplier - 1))
        else:
            await self._log_transaction(ctx.guild.id, ctx.author.id, "roulette_loss", -bet)
        embed.description = (
            f"Ball landed on **{final}** {numbers[final]['color']}!\n\n"
            f"{'🎉 You won' if won else '😢 You lost'} **{bet:,}** coins!"
            + (f" ({multiplier}x)" if won else "")
        )
        embed.color = _color("EMBED_SUCCESS_COLOR") if won else _color("EMBED_DENY_COLOR")
        await msg.edit(embed=embed)

    @gamble.command(
        name="crash",
        help="Multiplier rises until it crashes. Cash out before it does! Max payout: 20,000 coins.",
        extras={"category": "Economy"},
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def gamble_crash(self, ctx: TormentContext, amount: str) -> None:
        import asyncio
        wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        bet = self._parse_bet(amount, wallet["balance"])
        if bet is None or bet < 100:
            return await ctx.warn("Minimum bet is **100** coins.")
        if wallet["balance"] < bet:
            return await ctx.warn(f"You only have **{wallet['balance']:,}** coins.")
        await self._remove_balance(ctx.guild.id, ctx.author.id, bet)
        crash_point = random.uniform(1.0, 10.0)

        class CrashView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=30)
                self.cashed_out = False

            @discord.ui.button(label="Cash Out 💰", style=discord.ButtonStyle.green)
            async def cash_out(self, interaction: discord.Interaction, _: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("This isn't your game!", ephemeral=True)
                self.cashed_out = True
                self.stop()
                await interaction.response.defer()

        view = CrashView()
        embed = discord.Embed(title="📈 Crash Game", color=_color("EMBED_COLOR"))
        embed.add_field(name="Your Bet", value=f"**{bet:,}** coins")
        msg = await ctx.send(embed=embed, view=view)
        multiplier = 1.0
        while multiplier < crash_point and not view.cashed_out:
            embed.description = f"📈 Multiplier: **{multiplier:.2f}x**\nClick the button to cash out!"
            await msg.edit(embed=embed)
            await asyncio.sleep(0.5)
            multiplier = round(multiplier + 0.2, 2)
        view.children[0].disabled = True
        await msg.edit(view=view)
        if view.cashed_out:
            win_amount = min(int(bet * multiplier), 20000)
            await self._add_balance(ctx.guild.id, ctx.author.id, win_amount)
            await self._log_transaction(ctx.guild.id, ctx.author.id, "crash_win", win_amount - bet)
            embed.description = f"💰 Cashed out at **{multiplier:.2f}x**!\nYou won **{win_amount:,}** coins!"
            if win_amount == 20000:
                embed.description += "\n⚠️ Maximum payout reached!"
            embed.color = _color("EMBED_SUCCESS_COLOR")
        else:
            await self._log_transaction(ctx.guild.id, ctx.author.id, "crash_loss", -bet)
            embed.description = f"💥 Crashed at **{crash_point:.2f}x**!\nYou lost **{bet:,}** coins."
            embed.color = _color("EMBED_DENY_COLOR")
        await msg.edit(embed=embed)


    @gamble.command(
        name="overunder",
        help="Guess if the next number (1-10) will be over or under 5.",
        extras={"category": "Economy"},
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def gamble_overunder(self, ctx: TormentContext, choice: str, amount: str) -> None:
        choice = choice.lower()
        if choice not in ("over", "under"):
            return await ctx.warn("Choose `over` or `under`.")
        wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        bet = self._parse_bet(amount, wallet["balance"])
        if bet is None or bet < 100:
            return await ctx.warn("Minimum bet is **100** coins.")
        if wallet["balance"] < bet:
            return await ctx.warn(f"You only have **{wallet['balance']:,}** coins.")
        await self._remove_balance(ctx.guild.id, ctx.author.id, bet)
        roll = random.randint(1, 10)
        won = (choice == "over" and roll > 5) or (choice == "under" and roll < 5)
        if roll == 5:
            won = False
        if won:
            await self._add_balance(ctx.guild.id, ctx.author.id, bet * 2)
            await self._log_transaction(ctx.guild.id, ctx.author.id, "overunder_win", bet)
        else:
            await self._log_transaction(ctx.guild.id, ctx.author.id, "overunder_loss", -bet)
        embed = discord.Embed(
            title="🔢 Over/Under",
            description=(
                f"You bet **{choice}** 5 with **{bet:,}** coins.\n"
                f"The number was **{roll}**!\n\n"
                f"{'🎉 You won' if won else '😢 You lost'} **{bet:,}** coins!"
            ),
            color=_color("EMBED_SUCCESS_COLOR") if won else _color("EMBED_DENY_COLOR"),
        )
        await ctx.send(embed=embed)

    @gamble.command(
        name="scratch",
        help="Buy a scratch card and reveal your prize.",
        extras={"category": "Economy"},
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def gamble_scratch(self, ctx: TormentContext, amount: str) -> None:
        wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        bet = self._parse_bet(amount, wallet["balance"])
        if bet is None or bet < 100:
            return await ctx.warn("Minimum bet is **100** coins.")
        if wallet["balance"] < bet:
            return await ctx.warn(f"You only have **{wallet['balance']:,}** coins.")
        await self._remove_balance(ctx.guild.id, ctx.author.id, bet)
        symbols = ["🍒", "🍋", "🍊", "⭐", "💎", "🎰"]
        grid = [[random.choice(symbols) for _ in range(3)] for _ in range(3)]
        # count matches in rows
        winnings = 0
        for row in grid:
            if row[0] == row[1] == row[2]:
                payouts = {"💎": 10, "⭐": 7, "🎰": 5, "🍊": 3, "🍋": 2, "🍒": 1.5}
                winnings += int(bet * payouts.get(row[0], 1))
        if winnings > 0:
            await self._add_balance(ctx.guild.id, ctx.author.id, winnings)
            await self._log_transaction(ctx.guild.id, ctx.author.id, "scratch_win", winnings - bet)
        else:
            await self._log_transaction(ctx.guild.id, ctx.author.id, "scratch_loss", -bet)
        grid_str = "\n".join(" | ".join(row) for row in grid)
        embed = discord.Embed(
            title="🎟️ Scratch Card",
            description=f"```\n{grid_str}\n```\n",
            color=_color("EMBED_SUCCESS_COLOR") if winnings > bet else _color("EMBED_DENY_COLOR"),
        )
        if winnings > bet:
            embed.description += f"🎉 You won **{winnings:,}** coins!"
        elif winnings > 0:
            embed.description += f"😢 Partial win: **{winnings:,}** coins back."
        else:
            embed.description += f"No match. You lost **{bet:,}** coins."
        await ctx.send(embed=embed)

    @gamble.command(
        name="poker",
        help="Roll 5 dice and win based on poker hands.",
        extras={"category": "Economy"},
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def gamble_poker(self, ctx: TormentContext, amount: str) -> None:
        from collections import Counter
        wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        bet = self._parse_bet(amount, wallet["balance"])
        if bet is None or bet < 100:
            return await ctx.warn("Minimum bet is **100** coins.")
        if wallet["balance"] < bet:
            return await ctx.warn(f"You only have **{wallet['balance']:,}** coins.")
        await self._remove_balance(ctx.guild.id, ctx.author.id, bet)
        dice = [random.randint(1, 6) for _ in range(5)]
        counts = Counter(dice)
        freq = sorted(counts.values(), reverse=True)
        dice_str = " ".join(f"[{d}]" for d in dice)
        if freq[0] == 5:
            hand, mult = "Five of a Kind! 🎯", 10
        elif freq[0] == 4:
            hand, mult = "Four of a Kind! 🔥", 5
        elif freq[0] == 3 and freq[1] == 2:
            hand, mult = "Full House! 🏠", 4
        elif freq[0] == 3:
            hand, mult = "Three of a Kind! 🎲", 3
        elif freq[0] == 2 and freq[1] == 2:
            hand, mult = "Two Pair! ✌️", 2
        elif freq[0] == 2:
            hand, mult = "One Pair 👍", 0
            mult = 0
        else:
            hand, mult = "High Card 😐", 0
        if mult > 0:
            winnings = bet * mult
            await self._add_balance(ctx.guild.id, ctx.author.id, winnings)
            await self._log_transaction(ctx.guild.id, ctx.author.id, "poker_win", winnings - bet)
            result = f"🎉 **{hand}** — You won **{winnings:,}** coins! ({mult}x)"
            color = _color("EMBED_SUCCESS_COLOR")
        else:
            await self._log_transaction(ctx.guild.id, ctx.author.id, "poker_loss", -bet)
            result = f"😢 **{hand}** — You lost **{bet:,}** coins."
            color = _color("EMBED_DENY_COLOR")
        embed = discord.Embed(
            title="🎲 Poker Dice",
            description=f"**{dice_str}**\n\n{result}",
            color=color,
        )
        await ctx.send(embed=embed)

    @gamble.command(
        name="race",
        help="Bet on a horse in a 5-horse race.",
        extras={"category": "Economy"},
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def gamble_race(self, ctx: TormentContext, horse: int, amount: str) -> None:
        import asyncio
        if not 1 <= horse <= 5:
            return await ctx.warn("Choose a horse between 1 and 5.")
        wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        bet = self._parse_bet(amount, wallet["balance"])
        if bet is None or bet < 100:
            return await ctx.warn("Minimum bet is **100** coins.")
        if wallet["balance"] < bet:
            return await ctx.warn(f"You only have **{wallet['balance']:,}** coins.")
        await self._remove_balance(ctx.guild.id, ctx.author.id, bet)
        horses = ["🐴", "🦄", "🐎", "🏇", "🐖"]
        positions = [0] * 5
        finish_line = 10
        embed = discord.Embed(title="🏇 Horse Race", color=_color("EMBED_COLOR"))
        embed.add_field(name="Your Bet", value=f"Horse #{horse} {horses[horse-1]} — **{bet:,}** coins")
        msg = await ctx.send(embed=embed)
        winner = None
        while winner is None:
            for i in range(5):
                positions[i] += random.randint(0, 2)
                if positions[i] >= finish_line and winner is None:
                    winner = i + 1
            track = ""
            for i, (h, p) in enumerate(zip(horses, positions), 1):
                bar = "▓" * min(p, finish_line) + "░" * max(0, finish_line - p)
                track += f"`{i}` {h} {bar}\n"
            embed.description = track
            await msg.edit(embed=embed)
            await asyncio.sleep(0.8)
        won = winner == horse
        if won:
            await self._add_balance(ctx.guild.id, ctx.author.id, bet * 4)
            await self._log_transaction(ctx.guild.id, ctx.author.id, "race_win", bet * 3)
        else:
            await self._log_transaction(ctx.guild.id, ctx.author.id, "race_loss", -bet)
        embed.description += f"\n\n🏆 Winner: Horse #{winner} {horses[winner-1]}\n"
        embed.description += f"{'🎉 You won **' + str(bet * 4) + ':,** coins!' if won else '😢 You lost **' + str(bet) + ':,** coins.'}"
        embed.color = _color("EMBED_SUCCESS_COLOR") if won else _color("EMBED_DENY_COLOR")
        await msg.edit(embed=embed)


    @gamble.command(
        name="ladder",
        help="Climb the ladder for increasing multipliers. Stop anytime or fall!",
        extras={"category": "Economy"},
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def gamble_ladder(self, ctx: TormentContext, amount: str) -> None:
        import asyncio
        wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        bet = self._parse_bet(amount, wallet["balance"])
        if bet is None or bet < 100:
            return await ctx.warn("Minimum bet is **100** coins.")
        if wallet["balance"] < bet:
            return await ctx.warn(f"You only have **{wallet['balance']:,}** coins.")
        await self._remove_balance(ctx.guild.id, ctx.author.id, bet)
        rungs = [
            (1.2, 0.80), (1.5, 0.70), (2.0, 0.60),
            (3.0, 0.50), (5.0, 0.40), (10.0, 0.30),
        ]
        current_mult = 1.0
        rung = 0

        class LadderView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=20)
                self.action = None

            @discord.ui.button(label="Climb 🪜", style=discord.ButtonStyle.green)
            async def climb(self, interaction: discord.Interaction, _: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("Not your game!", ephemeral=True)
                self.action = "climb"
                self.stop()
                await interaction.response.defer()

            @discord.ui.button(label="Cash Out 💰", style=discord.ButtonStyle.blurple)
            async def cash_out(self, interaction: discord.Interaction, _: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("Not your game!", ephemeral=True)
                self.action = "cash"
                self.stop()
                await interaction.response.defer()

        while rung < len(rungs):
            mult_next, chance = rungs[rung]
            view = LadderView()
            embed = discord.Embed(
                title="🪜 Ladder Game",
                description=(
                    f"Current multiplier: **{current_mult}x** → **{mult_next}x**\n"
                    f"Chance of success: **{int(chance * 100)}%**\n"
                    f"Current value: **{int(bet * current_mult):,}** coins\n\n"
                    "Climb for more or cash out now?"
                ),
                color=_color("EMBED_COLOR"),
            )
            msg = await ctx.send(embed=embed, view=view)
            await view.wait()
            if view.action == "cash" or view.action is None:
                break
            if random.random() < chance:
                current_mult = mult_next
                rung += 1
            else:
                current_mult = 0.0
                break

        for child in view.children:
            child.disabled = True
        await msg.edit(view=view)

        win_amount = int(bet * current_mult)
        if win_amount > 0:
            await self._add_balance(ctx.guild.id, ctx.author.id, win_amount)
            await self._log_transaction(ctx.guild.id, ctx.author.id, "ladder_win", win_amount - bet)
            embed.description = f"🎉 Cashed out at **{current_mult}x**!\nYou won **{win_amount:,}** coins!"
            embed.color = _color("EMBED_SUCCESS_COLOR")
        else:
            await self._log_transaction(ctx.guild.id, ctx.author.id, "ladder_loss", -bet)
            embed.description = f"💥 You fell off the ladder!\nYou lost **{bet:,}** coins."
            embed.color = _color("EMBED_DENY_COLOR")
        await msg.edit(embed=embed)

    @gamble.command(
        name="mines",
        help="Pick tiles to reveal coins. Avoid the mines!",
        extras={"category": "Economy"},
    )
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def gamble_mines(self, ctx: TormentContext, amount: str, mines: int = 3) -> None:
        import asyncio
        if not 1 <= mines <= 8:
            return await ctx.warn("Choose between 1 and 8 mines.")
        wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        bet = self._parse_bet(amount, wallet["balance"])
        if bet is None or bet < 100:
            return await ctx.warn("Minimum bet is **100** coins.")
        if wallet["balance"] < bet:
            return await ctx.warn(f"You only have **{wallet['balance']:,}** coins.")
        await self._remove_balance(ctx.guild.id, ctx.author.id, bet)
        grid_size = 9
        mine_positions = set(random.sample(range(grid_size), mines))
        revealed = set()
        safe_count = grid_size - mines
        multiplier = 1.0

        def get_grid_str():
            rows = []
            for i in range(0, grid_size, 3):
                row = []
                for j in range(3):
                    idx = i + j
                    if idx in revealed:
                        row.append("💎" if idx not in mine_positions else "💣")
                    else:
                        row.append("⬜")
                rows.append(" ".join(row))
            return "\n".join(rows)

        class MinesView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.picked = None
                self.cashed = False
                for i in range(grid_size):
                    btn = discord.ui.Button(label=str(i + 1), style=discord.ButtonStyle.secondary, row=i // 3)
                    btn.callback = self._make_callback(i)
                    self.add_item(btn)
                cash_btn = discord.ui.Button(label="Cash Out 💰", style=discord.ButtonStyle.green, row=3)
                cash_btn.callback = self._cash_callback
                self.add_item(cash_btn)

            def _make_callback(self, idx):
                async def callback(interaction: discord.Interaction):
                    if interaction.user.id != ctx.author.id:
                        return await interaction.response.send_message("Not your game!", ephemeral=True)
                    self.picked = idx
                    self.stop()
                    await interaction.response.defer()
                return callback

            async def _cash_callback(self, interaction: discord.Interaction):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("Not your game!", ephemeral=True)
                self.cashed = True
                self.stop()
                await interaction.response.defer()

        embed = discord.Embed(
            title="💣 Mines",
            description=f"{get_grid_str()}\n\nPick a tile! Mines: **{mines}**\nCurrent: **{multiplier:.2f}x**",
            color=_color("EMBED_COLOR"),
        )
        embed.add_field(name="Bet", value=f"**{bet:,}** coins")
        msg = await ctx.send(embed=embed, view=MinesView())
        game_over = False
        while not game_over:
            view = MinesView()
            for child in view.children:
                if hasattr(child, "label") and child.label and child.label.isdigit():
                    idx = int(child.label) - 1
                    if idx in revealed:
                        child.disabled = True
            await msg.edit(view=view)
            await view.wait()
            if view.cashed or view.picked is None:
                break
            idx = view.picked
            if idx in revealed:
                continue
            revealed.add(idx)
            if idx in mine_positions:
                game_over = True
            else:
                safe_revealed = len([r for r in revealed if r not in mine_positions])
                multiplier = round(1.0 + (safe_revealed * (mines / safe_count)), 2)
                if safe_revealed == safe_count:
                    break
            embed.description = f"{get_grid_str()}\n\nMines: **{mines}** | Current: **{multiplier:.2f}x**"
            await msg.edit(embed=embed)
            if game_over:
                break

        for child in view.children:
            child.disabled = True
        await msg.edit(view=view)

        if game_over:
            await self._log_transaction(ctx.guild.id, ctx.author.id, "mines_loss", -bet)
            embed.description = f"{get_grid_str()}\n\n💥 **BOOM!** You hit a mine!\nYou lost **{bet:,}** coins."
            embed.color = _color("EMBED_DENY_COLOR")
        else:
            win_amount = int(bet * multiplier)
            await self._add_balance(ctx.guild.id, ctx.author.id, win_amount)
            await self._log_transaction(ctx.guild.id, ctx.author.id, "mines_win", win_amount - bet)
            embed.description = f"{get_grid_str()}\n\n💰 Cashed out at **{multiplier:.2f}x**!\nYou won **{win_amount:,}** coins!"
            embed.color = _color("EMBED_SUCCESS_COLOR")
        await msg.edit(embed=embed)


    # ── lottery ───────────────────────────────────────────────────────────────

    @commands.group(
        name="lottery",
        invoke_without_command=True,
        help="View the current lottery pot.",
        extras={"category": "Economy"},
    )
    async def lottery(self, ctx: TormentContext) -> None:
        row = await self.storage.pool.fetchrow(
            "SELECT SUM(tickets) as total_tickets, COUNT(*) as players FROM economy_lottery WHERE guild_id = $1",
            ctx.guild.id,
        )
        pot = (row["total_tickets"] or 0) * 100
        players = row["players"] or 0
        embed = discord.Embed(
            title="🎟️ Lottery",
            description=(
                f"**Pot:** {pot:,} coins\n"
                f"**Players:** {players}\n"
                f"**Ticket Price:** 100 coins\n\n"
                "Use `lottery buy <amount>` to enter!\n"
                "The lottery is drawn with `lottery draw` (admin only)."
            ),
            color=_color("EMBED_COLOR"),
        )
        await ctx.send(embed=embed)

    @lottery.command(
        name="buy",
        help="Buy lottery tickets (100 coins each).",
        extras={"category": "Economy"},
    )
    async def lottery_buy(self, ctx: TormentContext, amount: int = 1) -> None:
        if amount < 1:
            return await ctx.warn("Buy at least 1 ticket.")
        cost = amount * 100
        removed = await self._remove_balance(ctx.guild.id, ctx.author.id, cost)
        if not removed:
            wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
            return await ctx.warn(f"You need **{cost:,}** coins but only have **{wallet['balance']:,}**.")
        await self.storage.pool.execute(
            """
            INSERT INTO economy_lottery (guild_id, user_id, tickets)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET tickets = economy_lottery.tickets + $3
            """,
            ctx.guild.id, ctx.author.id, amount,
        )
        await self._log_transaction(ctx.guild.id, ctx.author.id, "lottery_buy", -cost, f"{amount} tickets")
        await ctx.success(f"Successfully bought **{amount}** lottery ticket(s) for **{cost:,}** coins.")

    @lottery.command(
        name="draw",
        help="Draw the lottery and pick a winner.",
        extras={"category": "Economy"},
    )
    @commands.has_permissions(manage_guild=True)
    async def lottery_draw(self, ctx: TormentContext) -> None:
        rows = await self.storage.pool.fetch(
            "SELECT user_id, tickets FROM economy_lottery WHERE guild_id = $1",
            ctx.guild.id,
        )
        if not rows:
            return await ctx.warn("No one has entered the lottery yet.")
        pool_entries = []
        for row in rows:
            pool_entries.extend([row["user_id"]] * row["tickets"])
        winner_id = random.choice(pool_entries)
        pot = len(pool_entries) * 100
        await self._add_balance(ctx.guild.id, winner_id, pot)
        await self._log_transaction(ctx.guild.id, winner_id, "lottery_win", pot)
        await self.storage.pool.execute(
            "DELETE FROM economy_lottery WHERE guild_id = $1", ctx.guild.id
        )
        winner = ctx.guild.get_member(winner_id)
        name = winner.mention if winner else f"<@{winner_id}>"
        embed = discord.Embed(
            title="🎟️ Lottery Draw!",
            description=f"🎉 {name} won the lottery and took home **{pot:,}** coins!",
            color=_color("EMBED_SUCCESS_COLOR"),
        )
        await ctx.send(embed=embed)

    @lottery.command(
        name="tickets",
        help="Check how many lottery tickets you have.",
        extras={"category": "Economy"},
    )
    async def lottery_tickets(self, ctx: TormentContext, *, member: discord.Member = None) -> None:
        target = member or ctx.author
        row = await self.storage.pool.fetchrow(
            "SELECT tickets FROM economy_lottery WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, target.id,
        )
        tickets = row["tickets"] if row else 0
        await ctx.send(
            embed=discord.Embed(
                description=f"{target.mention} has **{tickets}** lottery ticket(s).",
                color=_color("EMBED_COLOR"),
            )
        )


    # ── arena / duel ──────────────────────────────────────────────────────────

    @commands.group(
        name="arena",
        invoke_without_command=True,
        help="Challenge others to duels.",
        extras={"category": "Economy"},
    )
    async def arena(self, ctx: TormentContext) -> None:
        await ctx.send_help(ctx.command)

    @arena.command(
        name="duel",
        help="Challenge a member to a coin duel.",
        extras={"category": "Economy"},
    )
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def arena_duel(self, ctx: TormentContext, member: discord.Member, amount: str) -> None:
        import asyncio
        if member.id == ctx.author.id:
            return await ctx.warn("You can't duel yourself.")
        if member.bot:
            return await ctx.warn("You can't duel bots.")
        challenger_wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
        bet = self._parse_bet(amount, challenger_wallet["balance"])
        if bet is None or bet < 100:
            return await ctx.warn("Minimum duel bet is **100** coins.")
        if challenger_wallet["balance"] < bet:
            return await ctx.warn(f"You only have **{challenger_wallet['balance']:,}** coins.")
        target_wallet = await self._get_wallet(ctx.guild.id, member.id)
        if target_wallet["balance"] < bet:
            return await ctx.warn(f"{member.mention} doesn't have enough coins for this duel.")

        class DuelView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=30)
                self.accepted = None

            @discord.ui.button(label="Accept ⚔️", style=discord.ButtonStyle.green)
            async def accept(self, interaction: discord.Interaction, _: discord.ui.Button):
                if interaction.user.id != member.id:
                    return await interaction.response.send_message("This duel isn't for you!", ephemeral=True)
                self.accepted = True
                self.stop()
                await interaction.response.defer()

            @discord.ui.button(label="Decline ❌", style=discord.ButtonStyle.red)
            async def decline(self, interaction: discord.Interaction, _: discord.ui.Button):
                if interaction.user.id != member.id:
                    return await interaction.response.send_message("This duel isn't for you!", ephemeral=True)
                self.accepted = False
                self.stop()
                await interaction.response.defer()

        view = DuelView()
        embed = discord.Embed(
            title="⚔️ Duel Challenge",
            description=(
                f"{ctx.author.mention} challenges {member.mention} to a duel!\n"
                f"**Bet:** {bet:,} coins each\n\n"
                f"{member.mention}, do you accept?"
            ),
            color=_color("EMBED_COLOR"),
        )
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        for child in view.children:
            child.disabled = True
        await msg.edit(view=view)
        if not view.accepted:
            embed.description = f"{member.mention} declined the duel."
            embed.color = _color("EMBED_DENY_COLOR")
            return await msg.edit(embed=embed)
        # Both pay in
        await self._remove_balance(ctx.guild.id, ctx.author.id, bet)
        await self._remove_balance(ctx.guild.id, member.id, bet)
        # Animate the fight
        fighters = [ctx.author, member]
        hp = {ctx.author.id: 100, member.id: 100}
        log = []
        for _ in range(6):
            attacker, defender = random.sample(fighters, 2)
            dmg = random.randint(10, 35)
            hp[defender.id] = max(0, hp[defender.id] - dmg)
            log.append(f"⚔️ {attacker.display_name} hits {defender.display_name} for **{dmg}** damage!")
            if hp[defender.id] == 0:
                break
        winner = ctx.author if hp[member.id] <= hp[ctx.author.id] else member
        loser = member if winner == ctx.author else ctx.author
        prize = bet * 2
        await self._add_balance(ctx.guild.id, winner.id, prize)
        await self._log_transaction(ctx.guild.id, winner.id, "duel_win", bet, f"vs {loser.id}")
        await self._log_transaction(ctx.guild.id, loser.id, "duel_loss", -bet, f"vs {winner.id}")
        embed.description = (
            "\n".join(log[-4:]) + f"\n\n"
            f"❤️ {ctx.author.display_name}: **{hp[ctx.author.id]}** HP\n"
            f"❤️ {member.display_name}: **{hp[member.id]}** HP\n\n"
            f"🏆 **{winner.mention}** wins **{prize:,}** coins!"
        )
        embed.color = _color("EMBED_SUCCESS_COLOR")
        await msg.edit(embed=embed)


    # ── pet system ────────────────────────────────────────────────────────────

    PET_TYPES = {
        "dog":    {"emoji": "🐶", "base_income": 50,  "feed_cost": 30},
        "cat":    {"emoji": "🐱", "base_income": 40,  "feed_cost": 20},
        "dragon": {"emoji": "🐉", "base_income": 200, "feed_cost": 150},
        "fox":    {"emoji": "🦊", "base_income": 80,  "feed_cost": 60},
        "bunny":  {"emoji": "🐰", "base_income": 35,  "feed_cost": 15},
        "parrot": {"emoji": "🦜", "base_income": 60,  "feed_cost": 40},
    }
    PET_PRICES = {"dog": 500, "cat": 400, "dragon": 5000, "fox": 1200, "bunny": 300, "parrot": 800}

    @commands.group(
        name="pet",
        invoke_without_command=True,
        help="View your pet.",
        extras={"category": "Economy"},
    )
    async def pet(self, ctx: TormentContext) -> None:
        row = await self.storage.pool.fetchrow(
            "SELECT * FROM economy_pets WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        if not row:
            types_str = ", ".join(f"`{k}` ({v:,} coins)" for k, v in self.PET_PRICES.items())
            return await ctx.warn(f"You don't have a pet! Buy one with `pet buy <type>`.\nAvailable: {types_str}")
        pet_info = self.PET_TYPES[row["pet_type"]]
        hunger = row["hunger"]
        happiness = row["happiness"]
        level = row["level"]
        income = int(pet_info["base_income"] * (1 + level * 0.1))
        hunger_bar = "🟩" * (hunger // 10) + "⬜" * (10 - hunger // 10)
        happy_bar = "💛" * (happiness // 10) + "⬜" * (10 - happiness // 10)
        embed = discord.Embed(
            title=f"{pet_info['emoji']} {row['name']}",
            description=(
                f"**Type:** {row['pet_type'].title()}\n"
                f"**Level:** {level}\n"
                f"**Hunger:** {hunger_bar} ({hunger}/100)\n"
                f"**Happiness:** {happy_bar} ({happiness}/100)\n"
                f"**Income:** {income:,} coins/collect\n\n"
                "Commands: `pet feed`, `pet play`, `pet collect`, `pet rename`"
            ),
            color=_color("EMBED_COLOR"),
        )
        await ctx.send(embed=embed)

    @pet.command(
        name="buy",
        help="Buy a pet.",
        extras={"category": "Economy"},
    )
    async def pet_buy(self, ctx: TormentContext, pet_type: str) -> None:
        pet_type = pet_type.lower()
        if pet_type not in self.PET_TYPES:
            types = ", ".join(self.PET_TYPES.keys())
            return await ctx.warn(f"Invalid pet type. Choose: {types}")
        existing = await self.storage.pool.fetchrow(
            "SELECT pet_type FROM economy_pets WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        if existing:
            return await ctx.warn("You already have a pet! Use `pet release` first.")
        price = self.PET_PRICES[pet_type]
        removed = await self._remove_balance(ctx.guild.id, ctx.author.id, price)
        if not removed:
            wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
            return await ctx.warn(f"You need **{price:,}** coins but only have **{wallet['balance']:,}**.")
        pet_info = self.PET_TYPES[pet_type]
        default_name = f"My {pet_type.title()}"
        await self.storage.pool.execute(
            """
            INSERT INTO economy_pets (guild_id, user_id, pet_type, name, hunger, happiness, level, xp)
            VALUES ($1, $2, $3, $4, 100, 100, 1, 0)
            """,
            ctx.guild.id, ctx.author.id, pet_type, default_name,
        )
        await self._log_transaction(ctx.guild.id, ctx.author.id, "pet_buy", -price, pet_type)
        await ctx.success(f"Successfully bought a {pet_info['emoji']} **{default_name}** for **{price:,}** coins! Use `pet rename` to name it.")

    @pet.command(
        name="feed",
        help="Feed your pet to restore hunger.",
        extras={"category": "Economy"},
    )
    async def pet_feed(self, ctx: TormentContext) -> None:
        row = await self.storage.pool.fetchrow(
            "SELECT * FROM economy_pets WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        if not row:
            return await ctx.warn("You don't have a pet!")
        if row["hunger"] >= 100:
            return await ctx.warn("Your pet is already full!")
        feed_cost = self.PET_TYPES[row["pet_type"]]["feed_cost"]
        removed = await self._remove_balance(ctx.guild.id, ctx.author.id, feed_cost)
        if not removed:
            wallet = await self._get_wallet(ctx.guild.id, ctx.author.id)
            return await ctx.warn(f"You need **{feed_cost:,}** coins to feed your pet.")
        new_hunger = min(100, row["hunger"] + 40)
        await self.storage.pool.execute(
            "UPDATE economy_pets SET hunger = $1 WHERE guild_id = $2 AND user_id = $3",
            new_hunger, ctx.guild.id, ctx.author.id,
        )
        pet_info = self.PET_TYPES[row["pet_type"]]
        await ctx.success(f"{pet_info['emoji']} **{row['name']}** has been fed! Hunger: **{new_hunger}/100**")

    @pet.command(
        name="play",
        help="Play with your pet to boost happiness.",
        extras={"category": "Economy"},
    )
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def pet_play(self, ctx: TormentContext) -> None:
        row = await self.storage.pool.fetchrow(
            "SELECT * FROM economy_pets WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        if not row:
            return await ctx.warn("You don't have a pet!")
        new_happiness = min(100, row["happiness"] + 30)
        new_xp = row["xp"] + 10
        new_level = row["level"]
        if new_xp >= new_level * 100:
            new_xp -= new_level * 100
            new_level += 1
        await self.storage.pool.execute(
            "UPDATE economy_pets SET happiness = $1, xp = $2, level = $3 WHERE guild_id = $4 AND user_id = $5",
            new_happiness, new_xp, new_level, ctx.guild.id, ctx.author.id,
        )
        pet_info = self.PET_TYPES[row["pet_type"]]
        msg = f"{pet_info['emoji']} You played with **{row['name']}**! Happiness: **{new_happiness}/100**"
        if new_level > row["level"]:
            msg += f"\n🎉 **{row['name']}** leveled up to **Level {new_level}**!"
        await ctx.success(msg)

    @pet.command(
        name="collect",
        help="Collect income from your pet.",
        extras={"category": "Economy"},
    )
    async def pet_collect(self, ctx: TormentContext) -> None:
        row = await self.storage.pool.fetchrow(
            "SELECT * FROM economy_pets WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        if not row:
            return await ctx.warn("You don't have a pet!")
        cd = await self._get_cooldown(ctx.guild.id, ctx.author.id, "pet_collect")
        if cd:
            return await ctx.warn(f"You can collect again in **{self._format_cd(cd)}**.")
        pet_info = self.PET_TYPES[row["pet_type"]]
        # Income scales with level and is reduced by low hunger/happiness
        base = int(pet_info["base_income"] * (1 + row["level"] * 0.1))
        mood_mult = ((row["hunger"] + row["happiness"]) / 200)
        income = max(1, int(base * mood_mult))
        # Pets get hungrier and less happy over time
        new_hunger = max(0, row["hunger"] - 15)
        new_happiness = max(0, row["happiness"] - 10)
        await self.storage.pool.execute(
            "UPDATE economy_pets SET hunger = $1, happiness = $2 WHERE guild_id = $3 AND user_id = $4",
            new_hunger, new_happiness, ctx.guild.id, ctx.author.id,
        )
        await self._add_balance(ctx.guild.id, ctx.author.id, income)
        await self._set_cooldown(ctx.guild.id, ctx.author.id, "pet_collect", 14400)
        await self._log_transaction(ctx.guild.id, ctx.author.id, "pet_collect", income)
        await ctx.success(
            f"{pet_info['emoji']} **{row['name']}** earned you **{income:,}** coins!\n"
            f"Hunger: **{new_hunger}/100** | Happiness: **{new_happiness}/100**"
        )

    @pet.command(
        name="rename",
        help="Rename your pet.",
        extras={"category": "Economy"},
    )
    async def pet_rename(self, ctx: TormentContext, *, name: str) -> None:
        if len(name) > 32:
            return await ctx.warn("Pet name must be 32 characters or less.")
        row = await self.storage.pool.fetchrow(
            "SELECT pet_type FROM economy_pets WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        if not row:
            return await ctx.warn("You don't have a pet!")
        await self.storage.pool.execute(
            "UPDATE economy_pets SET name = $1 WHERE guild_id = $2 AND user_id = $3",
            name, ctx.guild.id, ctx.author.id,
        )
        pet_info = self.PET_TYPES[row["pet_type"]]
        await ctx.success(f"{pet_info['emoji']} Your pet has been renamed to **{name}**.")

    @pet.command(
        name="release",
        help="Release your pet (cannot be undone).",
        extras={"category": "Economy"},
    )
    async def pet_release(self, ctx: TormentContext) -> None:
        row = await self.storage.pool.fetchrow(
            "SELECT * FROM economy_pets WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        if not row:
            return await ctx.warn("You don't have a pet!")
        confirmed = await ctx.confirm(f"Are you sure you want to release **{row['name']}**? This cannot be undone.")
        if not confirmed:
            return await ctx.warn("Release cancelled.")
        await self.storage.pool.execute(
            "DELETE FROM economy_pets WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        pet_info = self.PET_TYPES[row["pet_type"]]
        await ctx.success(f"{pet_info['emoji']} You released **{row['name']}** into the wild. Goodbye!")



async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Economy(bot))
