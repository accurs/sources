from __future__ import annotations

import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
import discord
from discord.ext import commands, tasks

from bot.helpers.context import TormentContext


def _color(name: str) -> discord.Color:
    raw = os.getenv(name, "").lower().lstrip("#")
    try:
        return discord.Color(int(raw, 16))
    except ValueError:
        return discord.Color.blurple()


API_BASE = "https://db.ygoprodeck.com/api/v7"

RARITY_COLORS = {
    "Common": discord.Color.light_grey(),
    "Rare": discord.Color.blue(),
    "Super Rare": discord.Color.purple(),
    "Ultra Rare": discord.Color.gold(),
}

RARITY_VALUES = {
    "Common": 100,
    "Rare": 250,
    "Super Rare": 500,
    "Ultra Rare": 1000,
}

PACKS = {
    "starter": {"price": 1000, "cards": 5, "weights": [60, 30, 8, 2]},
    "premium": {"price": 2500, "cards": 5, "weights": [0, 60, 30, 10]},
    "ultimate": {"price": 5000, "cards": 5, "weights": [0, 0, 50, 50]},
}

RARITIES = ["Common", "Rare", "Super Rare", "Ultra Rare"]
DROP_WEIGHTS = [60, 25, 10, 5]


class Cards(commands.Cog):
    __cog_name__ = "Cards"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None
        self.active_drops: dict[int, dict] = {}

    @property
    def storage(self):
        return self.bot.storage

    async def cog_load(self) -> None:
        self.session = aiohttp.ClientSession()
        pool = self.bot.storage.pool
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS card_collection (
                guild_id  BIGINT NOT NULL,
                user_id   BIGINT NOT NULL,
                card_id   TEXT NOT NULL,
                card_name TEXT NOT NULL,
                rarity    TEXT NOT NULL,
                quantity  INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (guild_id, user_id, card_id)
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS card_drop_channels (
                guild_id   BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                PRIMARY KEY (guild_id, channel_id)
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS card_daily (
                user_id    BIGINT PRIMARY KEY,
                claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS card_market (
                listing_id BIGSERIAL PRIMARY KEY,
                guild_id   BIGINT NOT NULL,
                seller_id  BIGINT NOT NULL,
                card_id    TEXT NOT NULL,
                card_name  TEXT NOT NULL,
                rarity     TEXT NOT NULL,
                price      BIGINT NOT NULL,
                listed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        self.card_drops.start()

    async def cog_unload(self) -> None:
        self.card_drops.cancel()
        if self.session:
            await self.session.close()

    async def _fetch_card(self, rarity: str | None = None, name: str | None = None, card_id: str | None = None) -> dict | None:
        if not self.session:
            return None
        params: dict[str, Any] = {}
        if name:
            params["fname"] = name
        elif card_id:
            params["id"] = card_id
        else:
            params["num"] = 1
            params["offset"] = random.randint(0, 200)
            params["sort"] = "random"
        try:
            async with self.session.get(f"{API_BASE}/cardinfo.php", params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                cards = data.get("data", [])
                if not cards:
                    return None
                return cards[0]
        except Exception:
            return None

    def _determine_rarity(self, card: dict) -> str:
        card_type = card.get("type", "")
        level = card.get("level", 0)
        if "Link" in card_type or "Synchro" in card_type:
            return "Ultra Rare"
        if "Fusion" in card_type or "XYZ" in card_type:
            return "Super Rare"
        if "Effect" in card_type or level >= 7:
            return "Rare"
        return "Common"

    def _card_embed(self, card: dict, rarity: str) -> discord.Embed:
        embed = discord.Embed(
            title=card["name"],
            description=card.get("desc", "")[:300],
            color=RARITY_COLORS.get(rarity, discord.Color.blurple()),
        )
        stats = []
        if card.get("type"):
            stats.append(f"Type: {card['type']}")
        if card.get("race"):
            stats.append(f"Race: {card['race']}")
        if card.get("attribute"):
            stats.append(f"Attribute: {card['attribute']}")
        if card.get("atk") is not None:
            stats.append(f"ATK/DEF: {card['atk']}/{card.get('def', '?')}")
        if card.get("level"):
            stats.append(f"Level: {'⭐' * card['level']}")
        if stats:
            embed.add_field(name="Stats", value="\n".join(stats), inline=False)
        embed.add_field(name="Rarity", value=rarity, inline=True)
        images = card.get("card_images", [])
        if images:
            embed.set_image(url=images[0]["image_url"])
        return embed


    @tasks.loop(minutes=30)
    async def card_drops(self) -> None:
        rows = await self.storage.pool.fetch("SELECT guild_id, channel_id FROM card_drop_channels")
        for row in rows:
            channel = self.bot.get_channel(row["channel_id"])
            if not channel or row["channel_id"] in self.active_drops:
                continue
            rarity = random.choices(RARITIES, weights=DROP_WEIGHTS)[0]
            card = await self._fetch_card(rarity=rarity)
            if not card:
                continue
            embed = discord.Embed(
                title="⚔️ A Wild Yu-Gi-Oh! Card Appeared!",
                description=f"Rarity: **{rarity}**\nReact with ⚔️ to claim this card!",
                color=RARITY_COLORS.get(rarity, discord.Color.blurple()),
            )
            images = card.get("card_images", [])
            if images:
                embed.set_image(url=images[0]["image_url"])
            try:
                msg = await channel.send(embed=embed)
                await msg.add_reaction("⚔️")
                self.active_drops[row["channel_id"]] = {
                    "message_id": msg.id,
                    "card": card,
                    "rarity": rarity,
                    "guild_id": row["guild_id"],
                }
            except discord.HTTPException:
                pass

    @card_drops.before_loop
    async def _before_drops(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User) -> None:
        if user.bot or str(reaction.emoji) != "⚔️":
            return
        channel_id = reaction.message.channel.id
        drop = self.active_drops.get(channel_id)
        if not drop or drop["message_id"] != reaction.message.id:
            return
        self.active_drops.pop(channel_id, None)
        card = drop["card"]
        rarity = drop["rarity"]
        guild_id = drop["guild_id"]
        await self.storage.pool.execute(
            """
            INSERT INTO card_collection (guild_id, user_id, card_id, card_name, rarity, quantity)
            VALUES ($1, $2, $3, $4, $5, 1)
            ON CONFLICT (guild_id, user_id, card_id) DO UPDATE SET quantity = card_collection.quantity + 1
            """,
            guild_id, user.id, str(card["id"]), card["name"], rarity,
        )
        embed = self._card_embed(card, rarity)
        embed.set_footer(text=f"Claimed by {user.display_name}")
        try:
            await reaction.message.edit(embed=embed)
        except discord.HTTPException:
            pass


    @commands.hybrid_group(
        name="cards",
        invoke_without_command=True,
        help="Yu-Gi-Oh! card collection commands.",
        extras={"category": "Cards"},
    )
    async def cards(self, ctx: TormentContext) -> None:
        await ctx.send_help(ctx.command)

    @cards.command(
        name="search",
        help="Search for a Yu-Gi-Oh! card by name.",
        extras={"category": "Cards"},
    )
    async def cards_search(self, ctx: TormentContext, *, query: str) -> None:
        if not self.session:
            return await ctx.warn("Card service is unavailable right now.")
        try:
            async with self.session.get(f"{API_BASE}/cardinfo.php", params={"fname": query}) as resp:
                if resp.status != 200:
                    return await ctx.warn("No cards found matching that query.")
                data = await resp.json()
        except Exception:
            return await ctx.warn("Failed to reach the card API. Try again later.")
        results = data.get("data", [])
        if not results:
            return await ctx.warn("No cards found matching that query.")
        embed = discord.Embed(
            title=f"Search Results: {query}",
            color=_color("EMBED_COLOR"),
        )
        first = results[0]
        images = first.get("card_images", [])
        if images:
            embed.set_thumbnail(url=images[0]["image_url"])
        for card in results[:10]:
            desc = card.get("desc", "")
            short = desc[:200] + "..." if len(desc) > 200 else desc
            val = f"Type: {card.get('type', 'N/A')}"
            if card.get("atk") is not None:
                val += f" | ATK/DEF: {card['atk']}/{card.get('def', '?')}"
            val += f"\n{short}"
            embed.add_field(name=card["name"], value=val, inline=False)
        embed.set_footer(text="Use 'cards view <name>' for full details.")
        await ctx.send(embed=embed)

    @cards.command(
        name="view",
        help="View detailed information about a specific card.",
        extras={"category": "Cards"},
    )
    async def cards_view(self, ctx: TormentContext, *, card_name: str) -> None:
        card = await self._fetch_card(name=card_name)
        if not card:
            return await ctx.warn(f"Could not find a card named **{card_name}**.")
        rarity = self._determine_rarity(card)
        embed = self._card_embed(card, rarity)
        prices = card.get("card_prices", [])
        if prices:
            p = prices[0]
            embed.add_field(
                name="Market Prices",
                value=f"TCGPlayer: ${p.get('tcgplayer_price', 'N/A')}\nCardMarket: €{p.get('cardmarket_price', 'N/A')}",
                inline=False,
            )
        await ctx.send(embed=embed)

    @cards.command(
        name="collection",
        help="View your or another member's card collection.",
        extras={"category": "Cards"},
    )
    async def cards_collection(self, ctx: TormentContext, *, member: discord.Member = None) -> None:
        target = member or ctx.author
        rows = await self.storage.pool.fetch(
            "SELECT card_id, card_name, rarity, quantity FROM card_collection WHERE guild_id = $1 AND user_id = $2 ORDER BY rarity, card_name",
            ctx.guild.id, target.id,
        )
        if not rows:
            return await ctx.warn(f"{'You have' if target == ctx.author else f'{target.display_name} has'} no cards yet.")
        pages = []
        chunk = 8
        chunks = [rows[i:i+chunk] for i in range(0, len(rows), chunk)]
        total = len(chunks)
        for idx, group in enumerate(chunks, 1):
            embed = discord.Embed(
                title=f"{target.display_name}'s Collection",
                color=_color("EMBED_COLOR"),
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            for row in group:
                embed.add_field(
                    name=f"{row['card_name']} x{row['quantity']}",
                    value=f"Rarity: {row['rarity']}",
                    inline=True,
                )
            embed.set_footer(text=f"Page {idx}/{total} | {len(rows)} total cards")
            pages.append(embed)
        await ctx.paginate(pages)

    @cards.command(
        name="stats",
        help="View card collection statistics for yourself or another member.",
        extras={"category": "Cards"},
    )
    async def cards_stats(self, ctx: TormentContext, *, member: discord.Member = None) -> None:
        target = member or ctx.author
        row = await self.storage.pool.fetchrow(
            """
            SELECT
                COUNT(DISTINCT card_id) AS unique_cards,
                SUM(quantity) AS total_cards,
                SUM(CASE WHEN rarity = 'Common' THEN quantity ELSE 0 END) AS common,
                SUM(CASE WHEN rarity = 'Rare' THEN quantity ELSE 0 END) AS rare,
                SUM(CASE WHEN rarity = 'Super Rare' THEN quantity ELSE 0 END) AS super_rare,
                SUM(CASE WHEN rarity = 'Ultra Rare' THEN quantity ELSE 0 END) AS ultra_rare
            FROM card_collection
            WHERE guild_id = $1 AND user_id = $2
            """,
            ctx.guild.id, target.id,
        )
        if not row or not row["total_cards"]:
            return await ctx.warn(f"{'You have' if target == ctx.author else f'{target.display_name} has'} no cards yet.")
        value = (
            (row["common"] or 0) * RARITY_VALUES["Common"]
            + (row["rare"] or 0) * RARITY_VALUES["Rare"]
            + (row["super_rare"] or 0) * RARITY_VALUES["Super Rare"]
            + (row["ultra_rare"] or 0) * RARITY_VALUES["Ultra Rare"]
        )
        embed = discord.Embed(
            title=f"{target.display_name}'s Card Stats",
            color=_color("EMBED_COLOR"),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Unique Cards", value=f"{row['unique_cards']:,}", inline=True)
        embed.add_field(name="Total Cards", value=f"{row['total_cards']:,}", inline=True)
        embed.add_field(name="Collection Value", value=f"{value:,} coins", inline=True)
        embed.add_field(name="Common", value=f"{row['common'] or 0:,}", inline=True)
        embed.add_field(name="Rare", value=f"{row['rare'] or 0:,}", inline=True)
        embed.add_field(name="Super Rare", value=f"{row['super_rare'] or 0:,}", inline=True)
        embed.add_field(name="Ultra Rare", value=f"{row['ultra_rare'] or 0:,}", inline=True)
        await ctx.send(embed=embed)


    @cards.command(
        name="daily",
        help="Claim a free random card once every 24 hours.",
        extras={"category": "Cards"},
    )
    async def cards_daily(self, ctx: TormentContext) -> None:
        row = await self.storage.pool.fetchrow(
            "SELECT claimed_at FROM card_daily WHERE user_id = $1", ctx.author.id
        )
        if row:
            next_claim = row["claimed_at"] + timedelta(hours=24)
            if datetime.now(timezone.utc) < next_claim:
                remaining = next_claim - datetime.now(timezone.utc)
                h, rem = divmod(int(remaining.total_seconds()), 3600)
                m, s = divmod(rem, 60)
                return await ctx.warn(f"You already claimed your daily card. Come back in **{h}h {m}m {s}s**.")
        rarity = random.choices(RARITIES, weights=[70, 20, 8, 2])[0]
        card = await self._fetch_card(rarity=rarity)
        if not card:
            return await ctx.warn("Failed to fetch a card right now. Try again in a moment.")
        await self.storage.pool.execute(
            """
            INSERT INTO card_collection (guild_id, user_id, card_id, card_name, rarity, quantity)
            VALUES ($1, $2, $3, $4, $5, 1)
            ON CONFLICT (guild_id, user_id, card_id) DO UPDATE SET quantity = card_collection.quantity + 1
            """,
            ctx.guild.id, ctx.author.id, str(card["id"]), card["name"], rarity,
        )
        await self.storage.pool.execute(
            """
            INSERT INTO card_daily (user_id, claimed_at) VALUES ($1, NOW())
            ON CONFLICT (user_id) DO UPDATE SET claimed_at = NOW()
            """,
            ctx.author.id,
        )
        embed = self._card_embed(card, rarity)
        embed.title = f"🎁 Daily Card — {card['name']}"
        await ctx.send(embed=embed)

    @cards.command(
        name="gift",
        help="Gift one of your cards to another member.",
        extras={"category": "Cards"},
    )
    async def cards_gift(self, ctx: TormentContext, member: discord.Member, *, card_name: str) -> None:
        if member.bot:
            return await ctx.warn("You can't gift cards to bots.")
        if member.id == ctx.author.id:
            return await ctx.warn("You can't gift cards to yourself.")
        row = await self.storage.pool.fetchrow(
            "SELECT card_id, rarity, quantity FROM card_collection WHERE guild_id = $1 AND user_id = $2 AND LOWER(card_name) = LOWER($3)",
            ctx.guild.id, ctx.author.id, card_name,
        )
        if not row:
            return await ctx.warn(f"You don't have a card named **{card_name}**.")
        if row["quantity"] < 2:
            return await ctx.warn("You only have one copy of that card and can't give away your last one.")
        confirmed = await ctx.confirm(f"Gift **{card_name}** to {member.mention}?")
        if not confirmed:
            return await ctx.warn("Gift cancelled.")
        await self.storage.pool.execute(
            "UPDATE card_collection SET quantity = quantity - 1 WHERE guild_id = $1 AND user_id = $2 AND card_id = $3",
            ctx.guild.id, ctx.author.id, row["card_id"],
        )
        await self.storage.pool.execute(
            """
            INSERT INTO card_collection (guild_id, user_id, card_id, card_name, rarity, quantity)
            VALUES ($1, $2, $3, $4, $5, 1)
            ON CONFLICT (guild_id, user_id, card_id) DO UPDATE SET quantity = card_collection.quantity + 1
            """,
            ctx.guild.id, member.id, row["card_id"], card_name, row["rarity"],
        )
        await ctx.success(f"Successfully gifted **{card_name}** to {member.mention}.")

    @cards.command(
        name="sell",
        help="Sell copies of a card for coins.",
        extras={"category": "Cards"},
    )
    async def cards_sell(self, ctx: TormentContext, amount: int, *, card_name: str) -> None:
        if amount < 1:
            return await ctx.warn("Amount must be at least 1.")
        row = await self.storage.pool.fetchrow(
            "SELECT card_id, rarity, quantity FROM card_collection WHERE guild_id = $1 AND user_id = $2 AND LOWER(card_name) = LOWER($3)",
            ctx.guild.id, ctx.author.id, card_name,
        )
        if not row:
            return await ctx.warn(f"You don't have a card named **{card_name}**.")
        if row["quantity"] < amount:
            return await ctx.warn(f"You only have **{row['quantity']}** copies of that card.")
        value = RARITY_VALUES.get(row["rarity"], 100) * amount
        confirmed = await ctx.confirm(f"Sell **{amount}x {card_name}** for **{value:,}** coins?")
        if not confirmed:
            return await ctx.warn("Sale cancelled.")
        if row["quantity"] == amount:
            await self.storage.pool.execute(
                "DELETE FROM card_collection WHERE guild_id = $1 AND user_id = $2 AND card_id = $3",
                ctx.guild.id, ctx.author.id, row["card_id"],
            )
        else:
            await self.storage.pool.execute(
                "UPDATE card_collection SET quantity = quantity - $1 WHERE guild_id = $2 AND user_id = $3 AND card_id = $4",
                amount, ctx.guild.id, ctx.author.id, row["card_id"],
            )
        await self.storage.pool.execute(
            """
            INSERT INTO economy_wallets (guild_id, user_id, balance)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET balance = economy_wallets.balance + $3
            """,
            ctx.guild.id, ctx.author.id, value,
        )
        await ctx.success(f"Successfully sold **{amount}x {card_name}** for **{value:,}** coins.")

    @cards.command(
        name="top",
        help="View the card collection leaderboard.",
        extras={"category": "Cards"},
    )
    async def cards_top(self, ctx: TormentContext, category: str = "total") -> None:
        category = category.lower()
        if category not in ("total", "unique"):
            return await ctx.warn("Choose `total` or `unique`.")
        if category == "total":
            rows = await self.storage.pool.fetch(
                "SELECT user_id, SUM(quantity) AS count FROM card_collection WHERE guild_id = $1 GROUP BY user_id ORDER BY count DESC LIMIT 10",
                ctx.guild.id,
            )
        else:
            rows = await self.storage.pool.fetch(
                "SELECT user_id, COUNT(DISTINCT card_id) AS count FROM card_collection WHERE guild_id = $1 GROUP BY user_id ORDER BY count DESC LIMIT 10",
                ctx.guild.id,
            )
        if not rows:
            return await ctx.warn("No card data found for this server yet.")
        lines = []
        for i, row in enumerate(rows, 1):
            member = ctx.guild.get_member(row["user_id"])
            name = member.display_name if member else f"<@{row['user_id']}>"
            lines.append(f"`{i}.` **{name}** — {row['count']:,} {category} cards")
        embed = discord.Embed(
            title=f"🃏 Card Leaderboard — {category.title()}",
            description="\n".join(lines),
            color=_color("EMBED_COLOR"),
        )
        await ctx.send(embed=embed)


    @cards.group(
        name="packs",
        invoke_without_command=True,
        help="View and open card packs.",
        extras={"category": "Cards"},
    )
    async def cards_packs(self, ctx: TormentContext) -> None:
        embed = discord.Embed(
            title="🎴 Card Packs",
            description="Use `cards packs open <name>` to open a pack.",
            color=_color("EMBED_COLOR"),
        )
        rarity_labels = {
            "starter": "Guaranteed Rare+",
            "premium": "Guaranteed Super Rare+",
            "ultimate": "Guaranteed Ultra Rare",
        }
        for name, info in PACKS.items():
            embed.add_field(
                name=f"{name.title()} Pack",
                value=f"Price: **{info['price']:,}** coins\nCards: **{info['cards']}**\n{rarity_labels[name]}",
                inline=True,
            )
        await ctx.send(embed=embed)

    @cards_packs.command(
        name="open",
        help="Open a card pack (starter / premium / ultimate).",
        extras={"category": "Cards"},
    )
    async def cards_packs_open(self, ctx: TormentContext, *, pack_name: str) -> None:
        pack_name = pack_name.lower()
        pack = PACKS.get(pack_name)
        if not pack:
            return await ctx.warn(f"Unknown pack. Choose from: {', '.join(PACKS)}.")
        wallet_row = await self.storage.pool.fetchrow(
            "SELECT balance FROM economy_wallets WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        balance = wallet_row["balance"] if wallet_row else 0
        if balance < pack["price"]:
            return await ctx.warn(f"You need **{pack['price']:,}** coins to open this pack but only have **{balance:,}**.")
        await self.storage.pool.execute(
            "UPDATE economy_wallets SET balance = balance - $1 WHERE guild_id = $2 AND user_id = $3",
            pack["price"], ctx.guild.id, ctx.author.id,
        )
        status_msg = await ctx.send(
            embed=discord.Embed(description="Opening your pack...", color=_color("EMBED_INFO_COLOR"))
        )
        pulled: list[tuple[dict, str]] = []
        for _ in range(pack["cards"]):
            rarity = random.choices(RARITIES, weights=pack["weights"])[0]
            card = await self._fetch_card(rarity=rarity)
            if card:
                pulled.append((card, rarity))
        if not pulled:
            await self.storage.pool.execute(
                "UPDATE economy_wallets SET balance = balance + $1 WHERE guild_id = $2 AND user_id = $3",
                pack["price"], ctx.guild.id, ctx.author.id,
            )
            return await status_msg.edit(
                embed=discord.Embed(description="Failed to fetch cards. Your coins have been refunded.", color=_color("EMBED_DENY_COLOR"))
            )
        for card, rarity in pulled:
            await self.storage.pool.execute(
                """
                INSERT INTO card_collection (guild_id, user_id, card_id, card_name, rarity, quantity)
                VALUES ($1, $2, $3, $4, $5, 1)
                ON CONFLICT (guild_id, user_id, card_id) DO UPDATE SET quantity = card_collection.quantity + 1
                """,
                ctx.guild.id, ctx.author.id, str(card["id"]), card["name"], rarity,
            )
        await status_msg.delete()
        view = PackRevealView(ctx, pulled)
        first_embed = view.make_embed()
        view.message = await ctx.send(embed=first_embed, view=view)


    @cards.group(
        name="market",
        invoke_without_command=True,
        help="Browse the card market.",
        extras={"category": "Cards"},
    )
    async def cards_market(self, ctx: TormentContext) -> None:
        rows = await self.storage.pool.fetch(
            "SELECT * FROM card_market WHERE guild_id = $1 ORDER BY listed_at DESC LIMIT 15",
            ctx.guild.id,
        )
        if not rows:
            return await ctx.warn("No cards are listed on the market right now.")
        embed = discord.Embed(
            title="🏪 Card Market",
            description="Use `cards market buy <listing id>` to purchase.",
            color=_color("EMBED_COLOR"),
        )
        for row in rows:
            seller = ctx.guild.get_member(row["seller_id"])
            seller_name = seller.display_name if seller else f"<@{row['seller_id']}>"
            embed.add_field(
                name=f"#{row['listing_id']} — {row['card_name']}",
                value=f"Rarity: {row['rarity']}\nPrice: **{row['price']:,}** coins\nSeller: {seller_name}",
                inline=False,
            )
        await ctx.send(embed=embed)

    @cards_market.command(
        name="list",
        help="List one of your cards on the market.",
        extras={"category": "Cards"},
    )
    async def cards_market_list(self, ctx: TormentContext, price: int, *, card_name: str) -> None:
        if price < 1:
            return await ctx.warn("Price must be at least 1 coin.")
        row = await self.storage.pool.fetchrow(
            "SELECT card_id, rarity, quantity FROM card_collection WHERE guild_id = $1 AND user_id = $2 AND LOWER(card_name) = LOWER($3)",
            ctx.guild.id, ctx.author.id, card_name,
        )
        if not row:
            return await ctx.warn(f"You don't have a card named **{card_name}**.")
        if row["quantity"] < 2:
            return await ctx.warn("You only have one copy of that card and can't list your last one.")
        await self.storage.pool.execute(
            "UPDATE card_collection SET quantity = quantity - 1 WHERE guild_id = $1 AND user_id = $2 AND card_id = $3",
            ctx.guild.id, ctx.author.id, row["card_id"],
        )
        await self.storage.pool.execute(
            "INSERT INTO card_market (guild_id, seller_id, card_id, card_name, rarity, price) VALUES ($1, $2, $3, $4, $5, $6)",
            ctx.guild.id, ctx.author.id, row["card_id"], card_name, row["rarity"], price,
        )
        await ctx.success(f"Successfully listed **{card_name}** on the market for **{price:,}** coins.")

    @cards_market.command(
        name="buy",
        help="Buy a card from the market by listing ID.",
        extras={"category": "Cards"},
    )
    async def cards_market_buy(self, ctx: TormentContext, listing_id: int) -> None:
        listing = await self.storage.pool.fetchrow(
            "SELECT * FROM card_market WHERE listing_id = $1 AND guild_id = $2",
            listing_id, ctx.guild.id,
        )
        if not listing:
            return await ctx.warn(f"No listing found with ID `{listing_id}`.")
        if listing["seller_id"] == ctx.author.id:
            return await ctx.warn("You can't buy your own listing.")
        wallet_row = await self.storage.pool.fetchrow(
            "SELECT balance FROM economy_wallets WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id,
        )
        balance = wallet_row["balance"] if wallet_row else 0
        if balance < listing["price"]:
            return await ctx.warn(f"You need **{listing['price']:,}** coins but only have **{balance:,}**.")
        await self.storage.pool.execute(
            "DELETE FROM card_market WHERE listing_id = $1", listing_id
        )
        await self.storage.pool.execute(
            "UPDATE economy_wallets SET balance = balance - $1 WHERE guild_id = $2 AND user_id = $3",
            listing["price"], ctx.guild.id, ctx.author.id,
        )
        await self.storage.pool.execute(
            """
            INSERT INTO economy_wallets (guild_id, user_id, balance)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET balance = economy_wallets.balance + $3
            """,
            ctx.guild.id, listing["seller_id"], listing["price"],
        )
        await self.storage.pool.execute(
            """
            INSERT INTO card_collection (guild_id, user_id, card_id, card_name, rarity, quantity)
            VALUES ($1, $2, $3, $4, $5, 1)
            ON CONFLICT (guild_id, user_id, card_id) DO UPDATE SET quantity = card_collection.quantity + 1
            """,
            ctx.guild.id, ctx.author.id, listing["card_id"], listing["card_name"], listing["rarity"],
        )
        await ctx.success(f"Successfully purchased **{listing['card_name']}** for **{listing['price']:,}** coins.")

    @cards_market.command(
        name="unlist",
        help="Remove your listing from the market.",
        extras={"category": "Cards"},
    )
    async def cards_market_unlist(self, ctx: TormentContext, listing_id: int) -> None:
        listing = await self.storage.pool.fetchrow(
            "SELECT * FROM card_market WHERE listing_id = $1 AND guild_id = $2 AND seller_id = $3",
            listing_id, ctx.guild.id, ctx.author.id,
        )
        if not listing:
            return await ctx.warn(f"No listing found with ID `{listing_id}` that belongs to you.")
        await self.storage.pool.execute("DELETE FROM card_market WHERE listing_id = $1", listing_id)
        await self.storage.pool.execute(
            """
            INSERT INTO card_collection (guild_id, user_id, card_id, card_name, rarity, quantity)
            VALUES ($1, $2, $3, $4, $5, 1)
            ON CONFLICT (guild_id, user_id, card_id) DO UPDATE SET quantity = card_collection.quantity + 1
            """,
            ctx.guild.id, ctx.author.id, listing["card_id"], listing["card_name"], listing["rarity"],
        )
        await ctx.success(f"Successfully removed **{listing['card_name']}** from the market.")


    @cards.command(
        name="trade",
        help="Offer a card trade with another member.",
        extras={"category": "Cards"},
    )
    async def cards_trade(self, ctx: TormentContext, member: discord.Member, your_card: str, *, their_card: str) -> None:
        if member.bot or member.id == ctx.author.id:
            return await ctx.warn("You can't trade with that user.")
        your_row = await self.storage.pool.fetchrow(
            "SELECT card_id, rarity, quantity FROM card_collection WHERE guild_id = $1 AND user_id = $2 AND LOWER(card_name) = LOWER($3)",
            ctx.guild.id, ctx.author.id, your_card,
        )
        if not your_row:
            return await ctx.warn(f"You don't have a card named **{your_card}**.")
        if your_row["quantity"] < 2:
            return await ctx.warn("You only have one copy of that card and can't trade your last one.")
        their_row = await self.storage.pool.fetchrow(
            "SELECT card_id, rarity, quantity FROM card_collection WHERE guild_id = $1 AND user_id = $2 AND LOWER(card_name) = LOWER($3)",
            ctx.guild.id, member.id, their_card,
        )
        if not their_row:
            return await ctx.warn(f"{member.display_name} doesn't have a card named **{their_card}**.")
        if their_row["quantity"] < 2:
            return await ctx.warn(f"{member.display_name} only has one copy of that card.")
        embed = discord.Embed(
            title="🔄 Card Trade Request",
            description=(
                f"{ctx.author.mention} wants to trade:\n"
                f"**{your_card}** ({your_row['rarity']}) → **{their_card}** ({their_row['rarity']})\n\n"
                f"{member.mention}, do you accept?"
            ),
            color=_color("EMBED_WARN_COLOR"),
        )
        confirmed = await ctx.confirm(embed.description, user=member)
        if not confirmed:
            return await ctx.warn("Trade declined.")
        await self.storage.pool.execute(
            "UPDATE card_collection SET quantity = quantity - 1 WHERE guild_id = $1 AND user_id = $2 AND card_id = $3",
            ctx.guild.id, ctx.author.id, your_row["card_id"],
        )
        await self.storage.pool.execute(
            "UPDATE card_collection SET quantity = quantity - 1 WHERE guild_id = $1 AND user_id = $2 AND card_id = $3",
            ctx.guild.id, member.id, their_row["card_id"],
        )
        await self.storage.pool.execute(
            """
            INSERT INTO card_collection (guild_id, user_id, card_id, card_name, rarity, quantity)
            VALUES ($1, $2, $3, $4, $5, 1)
            ON CONFLICT (guild_id, user_id, card_id) DO UPDATE SET quantity = card_collection.quantity + 1
            """,
            ctx.guild.id, member.id, your_row["card_id"], your_card, your_row["rarity"],
        )
        await self.storage.pool.execute(
            """
            INSERT INTO card_collection (guild_id, user_id, card_id, card_name, rarity, quantity)
            VALUES ($1, $2, $3, $4, $5, 1)
            ON CONFLICT (guild_id, user_id, card_id) DO UPDATE SET quantity = card_collection.quantity + 1
            """,
            ctx.guild.id, ctx.author.id, their_row["card_id"], their_card, their_row["rarity"],
        )
        await ctx.success(f"Successfully traded **{your_card}** with {member.mention} for **{their_card}**.")

    @commands.command(
        name="cardchannel",
        help="Set or unset a channel for automatic card drops.",
        extras={"category": "Cards"},
    )
    @commands.has_permissions(manage_channels=True)
    async def cardchannel(self, ctx: TormentContext, channel: discord.TextChannel = None) -> None:
        target = channel or ctx.channel
        existing = await self.storage.pool.fetchrow(
            "SELECT 1 FROM card_drop_channels WHERE guild_id = $1 AND channel_id = $2",
            ctx.guild.id, target.id,
        )
        if existing:
            await self.storage.pool.execute(
                "DELETE FROM card_drop_channels WHERE guild_id = $1 AND channel_id = $2",
                ctx.guild.id, target.id,
            )
            return await ctx.success(f"Successfully removed {target.mention} as a card drop channel.")
        await self.storage.pool.execute(
            "INSERT INTO card_drop_channels (guild_id, channel_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            ctx.guild.id, target.id,
        )
        await ctx.success(f"Successfully set {target.mention} as a card drop channel.")


class PackRevealView(discord.ui.View):
    def __init__(self, ctx: TormentContext, cards: list[tuple[dict, str]]) -> None:
        super().__init__(timeout=120)
        self.ctx = ctx
        self.cards = cards
        self.index = 0
        self.message: discord.Message | None = None
        # Apply nav emojis from env
        left = os.getenv("EMOJI_LEFT", "◀")
        right = os.getenv("EMOJI_RIGHT", "▶")
        self.btn_prev.emoji = discord.PartialEmoji.from_str(left)
        self.btn_prev.label = None
        self.btn_next.emoji = discord.PartialEmoji.from_str(right)
        self.btn_next.label = None
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.btn_prev.disabled = self.index == 0
        self.btn_next.disabled = self.index >= len(self.cards) - 1

    def make_embed(self) -> discord.Embed:
        card, rarity = self.cards[self.index]
        embed = discord.Embed(
            title=f"📦 Pack Opening — Card {self.index + 1}/{len(self.cards)}",
            description=card.get("desc", "")[:200],
            color=RARITY_COLORS.get(rarity, discord.Color.blurple()),
        )
        embed.add_field(name="Name", value=card["name"], inline=True)
        embed.add_field(name="Rarity", value=rarity, inline=True)
        if card.get("type"):
            embed.add_field(name="Type", value=card["type"], inline=True)
        if card.get("atk") is not None:
            embed.add_field(name="ATK/DEF", value=f"{card['atk']}/{card.get('def', '?')}", inline=True)
        images = card.get("card_images", [])
        if images:
            embed.set_image(url=images[0]["image_url"])
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message("This pack isn't yours.", ephemeral=True)
        return False

    async def on_timeout(self) -> None:
        if self.message:
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def btn_prev(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.index -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def btn_next(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.index += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label="Summary", style=discord.ButtonStyle.primary)
    async def btn_summary(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        embed = discord.Embed(
            title="🎉 Pack Summary",
            color=discord.Color.gold(),
        )
        for card, rarity in self.cards:
            embed.add_field(name=card["name"], value=rarity, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Cards(bot))
