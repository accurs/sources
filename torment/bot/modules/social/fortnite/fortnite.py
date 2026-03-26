from __future__ import annotations

from json import dumps

import discord
from discord.ext import commands
from discord.utils import format_dt, utcnow

from bot.helpers.context import TormentContext, _color
from bot.helpers.paginator import Paginator

from .manager import AuthData, SessionManager
from .models import MOTD, Cosmetic, Map

session = SessionManager()

CURRENCY_TYPES = {
    "Currency:MtxComplimentary": "Epic Games & Refunds",
    "Currency:MtxGiveaway": "Battlepass & Challenges",
    "Currency:MtxPurchased": "Purchased",
}


class Fortnite(commands.Cog):
    __cog_name__ = "fortnite"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def storage(self):
        return self.bot.storage

    async def cog_load(self) -> None:
        await self.storage.pool.execute("""
            CREATE TABLE IF NOT EXISTS fortnite_accounts (
                user_id      BIGINT PRIMARY KEY,
                display_name TEXT NOT NULL,
                account_id   TEXT NOT NULL,
                device_id    TEXT NOT NULL,
                secret       TEXT NOT NULL,
                access_token TEXT NOT NULL,
                expires_at   TIMESTAMP NOT NULL
            )
        """)
        await self.storage.pool.execute("""
            CREATE TABLE IF NOT EXISTS fortnite_reminders (
                user_id   BIGINT NOT NULL,
                item_name TEXT NOT NULL,
                PRIMARY KEY (user_id, item_name)
            )
        """)

    async def _get_auth(self, ctx: TormentContext) -> AuthData:
        row = await self.storage.pool.fetchrow(
            "SELECT * FROM fortnite_accounts WHERE user_id = $1", ctx.author.id
        )
        if not row:
            raise commands.CommandError(
                "You don't have a Fortnite account linked. Use `fortnite login` to link your account."
            )
        auth = AuthData(
            user_id=row["user_id"],
            display_name=row["display_name"],
            account_id=row["account_id"],
            device_id=row["device_id"],
            secret=row["secret"],
            access_token=row["access_token"],
            expires_at=row["expires_at"],
        )
        if utcnow().replace(tzinfo=None) >= auth.expires_at:
            auth = await session.revalidate(auth)
            await self.storage.pool.execute(
                "UPDATE fortnite_accounts SET access_token=$1, expires_at=$2 WHERE user_id=$3",
                auth.access_token, auth.expires_at, ctx.author.id,
            )
        return auth

    @commands.hybrid_group(
        name="fortnite",
        invoke_without_command=True,
        help="Fortnite account and game integration commands",
        extras={"parameters": "n/a", "usage": "fortnite"},
    )
    async def fortnite(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @fortnite.command(
        name="login",
        help="Link your Epic Games account to the bot via device code authentication",
        extras={"parameters": "n/a", "usage": "fortnite login"},
    )
    async def fortnite_login(self, ctx: TormentContext) -> None:
        auth_session = await session.initiate_login()
        embed = discord.Embed(
            color=_color("EMBED_INFO_COLOR"),
            title="Fortnite Account Login",
            description=(
                f"To link your Epic Games account, visit the activation page and enter the code shown.\n\n"
                f"**Verification URL:** https://www.epicgames.com/activate\n"
                f"**Code:** `{auth_session.user_code}`\n\n"
                f"You have **4 minutes** to complete this. The bot will notify you once your account is linked."
            ),
        )
        await ctx.reply(embed=embed)
        auth_data = await session.poll_device_code(auth_session.device_code)
        if not auth_data:
            return await ctx.warn("The login attempt timed out or was cancelled. Please try again.")
        auth_data.user_id = ctx.author.id
        await self.storage.pool.execute(
            """
            INSERT INTO fortnite_accounts (user_id, display_name, account_id, device_id, secret, access_token, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (user_id) DO UPDATE SET
                display_name=EXCLUDED.display_name, account_id=EXCLUDED.account_id,
                device_id=EXCLUDED.device_id, secret=EXCLUDED.secret,
                access_token=EXCLUDED.access_token, expires_at=EXCLUDED.expires_at
            """,
            auth_data.user_id, auth_data.display_name, auth_data.account_id,
            auth_data.device_id, auth_data.secret, auth_data.access_token, auth_data.expires_at,
        )
        await ctx.success(f"Successfully linked your Epic Games account as **{auth_data.display_name}**.")

    @fortnite.command(
        name="logout",
        help="Unlink your Epic Games account from the bot",
        extras={"parameters": "n/a", "usage": "fortnite logout"},
    )
    async def fortnite_logout(self, ctx: TormentContext) -> None:
        deleted = await self.storage.pool.execute(
            "DELETE FROM fortnite_accounts WHERE user_id = $1", ctx.author.id
        )
        if deleted == "DELETE 0":
            return await ctx.warn("You don't have a Fortnite account linked.")
        await ctx.success("Successfully unlinked your Epic Games account.")

    @fortnite.command(
        name="map",
        help="View the current Fortnite map with all named locations",
        extras={"parameters": "n/a", "usage": "fortnite map"},
    )
    async def fortnite_map(self, ctx: TormentContext) -> None:
        async with ctx.typing():
            map_data = await Map.fetch()
            file = await map_data.file("pois")
        embed = discord.Embed(
            color=_color("EMBED_INFO_COLOR"),
            title="Fortnite Map",
            description=f"**Named Locations ({len(map_data.pois)}):** {', '.join(map_data.pois)}",
        )
        embed.set_image(url="attachment://map.png")
        await ctx.reply(embed=embed, file=file)

    @fortnite.command(
        name="news",
        help="View the current Fortnite Battle Royale news and MOTDs",
        extras={"parameters": "n/a", "usage": "fortnite news"},
    )
    async def fortnite_news(self, ctx: TormentContext) -> None:
        async with ctx.typing():
            motds = await MOTD.fetch()
        if not motds:
            return await ctx.warn("No news is currently available.")
        pages = []
        for i, motd in enumerate(motds):
            embed = discord.Embed(color=_color("EMBED_INFO_COLOR"), title=motd.title, description=motd.body)
            embed.set_image(url=motd.image)
            embed.set_footer(text=f"News {i+1}/{len(motds)}")
            pages.append(embed)
        await Paginator(ctx, pages).start()

    @fortnite.command(
        name="view",
        help="View detailed information about a Fortnite cosmetic item",
        extras={"parameters": "cosmetic", "usage": "fortnite view (cosmetic)"},
    )
    async def fortnite_view(self, ctx: TormentContext, *, cosmetic: Cosmetic) -> None:
        embed = discord.Embed(
            color=cosmetic.color,
            title=cosmetic.name,
            description=cosmetic.description or "No description available.",
            url=cosmetic.url,
        )
        embed.add_field(name="Type", value=cosmetic.pretty_type, inline=True)
        embed.add_field(name="Rarity", value=cosmetic.rarity.replace("_", " ").title(), inline=True)
        if cosmetic.price:
            embed.add_field(name="Price", value=f"{cosmetic.price} V-Bucks", inline=True)
        if cosmetic.history and cosmetic.history is not False:
            embed.add_field(
                name="Shop History",
                value=(
                    f"First seen: {format_dt(cosmetic.history.first_seen, 'D')}\n"
                    f"Last seen: {format_dt(cosmetic.history.last_seen, 'D')}\n"
                    f"Occurrences: {cosmetic.history.occurrences}"
                ),
                inline=False,
            )
        icon = cosmetic.images.featured or cosmetic.images.icon
        if icon and icon is not False:
            embed.set_thumbnail(url=icon)
        await ctx.reply(embed=embed)

    @fortnite.command(
        name="locker",
        help="View the V-Bucks balance and currency breakdown for your linked account",
        extras={"parameters": "n/a", "usage": "fortnite locker"},
    )
    async def fortnite_locker(self, ctx: TormentContext) -> None:
        auth = await self._get_auth(ctx)
        async with session.client.get(
            f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{auth.account_id}/client/QueryProfile",
            params={"profileId": "common_core", "rvn": -1},
            json={},
            headers={"Authorization": f"Bearer {auth.access_token}"},
        ) as resp:
            data = await resp.json()
        items = data.get("profileChanges", [{}])[0].get("profile", {}).get("items", {})
        currency_breakdown: dict[str, int] = {}
        total = 0
        for item in items.values():
            ttype = item.get("templateId", "")
            if ttype.startswith("Currency:Mtx"):
                qty = item.get("attributes", {}).get("quantity", 0)
                label = CURRENCY_TYPES.get(ttype, ttype)
                currency_breakdown[label] = currency_breakdown.get(label, 0) + qty
                total += qty
        avatar_url = await session.get_avatar(auth)
        embed = discord.Embed(
            color=_color("EMBED_INFO_COLOR"),
            title=f"{auth.display_name}'s V-Bucks",
            description=f"**Total Balance:** {total:,} V-Bucks",
        )
        embed.set_thumbnail(url=avatar_url)
        for label, amount in currency_breakdown.items():
            embed.add_field(name=label, value=f"{amount:,} V-Bucks", inline=True)
        await ctx.reply(embed=embed)

    @fortnite.command(
        name="summary",
        help="View your Fortnite Battle Royale stats and account summary",
        extras={"parameters": "n/a", "usage": "fortnite summary"},
    )
    async def fortnite_summary(self, ctx: TormentContext) -> None:
        auth = await self._get_auth(ctx)
        async with session.client.get(
            f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{auth.account_id}/client/QueryProfile",
            params={"profileId": "athena", "rvn": -1},
            json={},
            headers={"Authorization": f"Bearer {auth.access_token}"},
        ) as resp:
            data = await resp.json()
        stats = data.get("profileChanges", [{}])[0].get("profile", {}).get("stats", {}).get("attributes", {})
        avatar_url = await session.get_avatar(auth)
        embed = discord.Embed(
            color=_color("EMBED_INFO_COLOR"),
            title=f"{auth.display_name}'s Summary",
            description="Account summary for your linked Fortnite profile.",
        )
        embed.set_thumbnail(url=avatar_url)
        embed.add_field(name="Level", value=str(stats.get("level", 0)), inline=True)
        embed.add_field(name="XP", value=f"{stats.get('xp', 0):,}", inline=True)
        embed.add_field(name="Victory Crowns", value=str(stats.get("battlestars_season_total", 0)), inline=True)
        await ctx.reply(embed=embed)

    @fortnite.command(
        name="humans",
        help="View the friends list for your linked Epic Games account",
        extras={"parameters": "n/a", "usage": "fortnite humans"},
    )
    async def fortnite_humans(self, ctx: TormentContext) -> None:
        auth = await self._get_auth(ctx)
        async with session.client.get(
            f"https://friends-public-service-prod.ol.epicgames.com/friends/api/public/friends/{auth.account_id}",
            headers={"Authorization": f"Bearer {auth.access_token}"},
        ) as resp:
            friends = await resp.json()
        if not friends:
            return await ctx.warn("Your Epic Games friends list is empty.")
        account_ids = [f["accountId"] for f in friends[:100]]
        async with session.client.get(
            "https://account-public-service-prod.ol.epicgames.com/account/api/public/account",
            params=[("accountId", aid) for aid in account_ids],
            headers={"Authorization": f"Bearer {auth.access_token}"},
        ) as resp:
            accounts = await resp.json()
        names = [a.get("displayName", a["id"]) for a in accounts]
        pages = []
        for i in range(0, len(names), 20):
            chunk = names[i:i + 20]
            embed = discord.Embed(
                color=_color("EMBED_INFO_COLOR"),
                title=f"{auth.display_name}'s Friends ({len(names)} total)",
                description="\n".join(f"`{j+1+i}.` {name}" for j, name in enumerate(chunk)),
            )
            pages.append(embed)
        await Paginator(ctx, pages).start()

    @fortnite.command(
        name="unadd",
        help="Remove a friend from your Epic Games friends list by their display name",
        extras={"parameters": "username", "usage": "fortnite unadd (username)"},
    )
    async def fortnite_unadd(self, ctx: TormentContext, *, username: str) -> None:
        auth = await self._get_auth(ctx)
        async with session.client.get(
            f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/displayName/{username}",
            headers={"Authorization": f"Bearer {auth.access_token}"},
        ) as resp:
            if resp.status != 200:
                return await ctx.warn(f"No Epic Games account found with the name **{username}**.")
            target = await resp.json()
        async with session.client.delete(
            f"https://friends-public-service-prod.ol.epicgames.com/friends/api/public/friends/{auth.account_id}/{target['id']}",
            headers={"Authorization": f"Bearer {auth.access_token}"},
        ) as resp:
            if resp.status not in (204, 200):
                return await ctx.warn(f"Failed to remove **{username}** from your friends list.")
        await ctx.success(f"Successfully removed **{username}** from your Epic Games friends list.")

    @fortnite.group(
        name="spoof",
        invoke_without_command=True,
        help="Spoof your in-lobby stats visible to other party members",
        extras={"parameters": "n/a", "usage": "fortnite spoof"},
    )
    async def fortnite_spoof(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @fortnite_spoof.command(
        name="level",
        help="Spoof your displayed Battle Royale level in the party lobby",
        extras={"parameters": "level", "usage": "fortnite spoof level (level)"},
    )
    async def fortnite_spoof_level(self, ctx: TormentContext, level: int) -> None:
        if level < 1 or level > 2000:
            return await ctx.warn("Level must be between **1** and **2000**.")
        auth = await self._get_auth(ctx)
        payload = {
            "Default:AthenaBattlePassInfo_j": dumps({
                "AthenaBattlePassInfo": {
                    "bHasPurchasedPass": True,
                    "passLevel": level,
                    "selfBoostXp": 0,
                    "friendBoostXp": 0,
                }
            }),
            "Default:Location_s": "InGame",
            "Default:HasPreloadedAthena_b": "true",
        }
        await session.patch_party(auth, payload)
        await ctx.success(f"Successfully spoofed your level to **{level}** in the party lobby.")

    @fortnite_spoof.command(
        name="crowns",
        help="Spoof your displayed Victory Crown count in the party lobby",
        extras={"parameters": "crowns", "usage": "fortnite spoof crowns (crowns)"},
    )
    async def fortnite_spoof_crowns(self, ctx: TormentContext, crowns: int) -> None:
        if crowns < 0 or crowns > 9999:
            return await ctx.warn("Crown count must be between **0** and **9999**.")
        auth = await self._get_auth(ctx)
        payload = {
            "Default:RemainingTrialCount_U": str(crowns),
            "Default:Location_s": "InGame",
            "Default:HasPreloadedAthena_b": "true",
        }
        await session.patch_party(auth, payload)
        await ctx.success(f"Successfully spoofed your Victory Crown count to **{crowns}** in the party lobby.")

    @fortnite.command(
        name="equip",
        help="Equip a cosmetic item on your account in the party lobby",
        extras={"parameters": "cosmetic", "usage": "fortnite equip (cosmetic)"},
    )
    async def fortnite_equip(self, ctx: TormentContext, *, cosmetic: Cosmetic) -> None:
        auth = await self._get_auth(ctx)
        item_id = session.cosmetic_service.identifiers.get(cosmetic.name.lower()) or cosmetic.id
        ctype = cosmetic.type.lower()
        if "outfit" in ctype or "character" in ctype:
            inner_key, path_prefix, use_loadout = "characterDef", "Characters", True
        elif "backbling" in ctype or "back" in ctype:
            inner_key, path_prefix, use_loadout = "backpackDef", "Backpacks", True
        elif "pickaxe" in ctype or "harvesting" in ctype:
            inner_key, path_prefix, use_loadout = "pickaxeDef", "Pickaxes", True
        elif "glider" in ctype:
            inner_key, path_prefix, use_loadout = "glideDef", "Gliders", True
        elif "emote" in ctype or "dance" in ctype:
            use_loadout = False
        else:
            return await ctx.warn(f"Equipping **{cosmetic.pretty_type}** items is not supported.")
        if use_loadout:
            payload = {
                "Default:AthenaCosmeticLoadout_j": dumps({
                    "AthenaCosmeticLoadout": {
                        inner_key: f"/Game/Athena/Items/Cosmetics/{path_prefix}/{item_id}.{item_id}",
                        "variantChannelTags": [],
                        "itemVariants": [],
                    }
                })
            }
        else:
            payload = {
                "Default:FrontendEmote_j": dumps({
                    "FrontendEmote": {
                        "emoteItemDef": f"/Game/Athena/Items/Cosmetics/Dances/{item_id}.{item_id}",
                        "emoteSection": -1,
                    }
                })
            }
        await session.patch_party(auth, payload)
        await ctx.success(f"Successfully equipped **{cosmetic.name}** on your account in the party lobby.")

    @fortnite.group(
        name="remind",
        invoke_without_command=True,
        help="Manage shop reminders for Fortnite cosmetic items",
        extras={"parameters": "n/a", "usage": "fortnite remind"},
    )
    async def fortnite_remind(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @fortnite_remind.command(
        name="add",
        help="Add a cosmetic item to your shop reminder list",
        extras={"parameters": "item name", "usage": "fortnite remind add (item name)"},
    )
    async def fortnite_remind_add(self, ctx: TormentContext, *, item_name: str) -> None:
        existing = await self.storage.pool.fetchval(
            "SELECT 1 FROM fortnite_reminders WHERE user_id=$1 AND item_name=$2",
            ctx.author.id, item_name.lower(),
        )
        if existing:
            return await ctx.warn(f"You already have a reminder set for **{item_name}**.")
        await self.storage.pool.execute(
            "INSERT INTO fortnite_reminders (user_id, item_name) VALUES ($1, $2)",
            ctx.author.id, item_name.lower(),
        )
        await ctx.success(f"Successfully added a shop reminder for **{item_name}**.")

    @fortnite_remind.command(
        name="remove",
        help="Remove a cosmetic item from your shop reminder list",
        extras={"parameters": "item name", "usage": "fortnite remind remove (item name)"},
    )
    async def fortnite_remind_remove(self, ctx: TormentContext, *, item_name: str) -> None:
        deleted = await self.storage.pool.execute(
            "DELETE FROM fortnite_reminders WHERE user_id=$1 AND item_name=$2",
            ctx.author.id, item_name.lower(),
        )
        if deleted == "DELETE 0":
            return await ctx.warn(f"You don't have a reminder set for **{item_name}**.")
        await ctx.success(f"Successfully removed the shop reminder for **{item_name}**.")

    @fortnite_remind.command(
        name="clear",
        help="Clear all cosmetic shop reminders from your list",
        extras={"parameters": "n/a", "usage": "fortnite remind clear"},
    )
    async def fortnite_remind_clear(self, ctx: TormentContext) -> None:
        deleted = await self.storage.pool.execute(
            "DELETE FROM fortnite_reminders WHERE user_id=$1", ctx.author.id
        )
        if deleted == "DELETE 0":
            return await ctx.warn("You don't have any shop reminders set.")
        await ctx.success("Successfully cleared all your Fortnite shop reminders.")

    @fortnite_remind.command(
        name="list",
        help="View all cosmetic items you have shop reminders set for",
        extras={"parameters": "n/a", "usage": "fortnite remind list"},
    )
    async def fortnite_remind_list(self, ctx: TormentContext) -> None:
        rows = await self.storage.pool.fetch(
            "SELECT item_name FROM fortnite_reminders WHERE user_id=$1 ORDER BY item_name",
            ctx.author.id,
        )
        if not rows:
            return await ctx.warn("You don't have any shop reminders set.")
        lines = [f"`{i+1}.` {row['item_name'].title()}" for i, row in enumerate(rows)]
        pages = []
        for i in range(0, len(lines), 20):
            embed = discord.Embed(
                color=_color("EMBED_INFO_COLOR"),
                title=f"{ctx.author.display_name}'s Shop Reminders",
                description="\n".join(lines[i:i + 20]),
            )
            pages.append(embed)
        await Paginator(ctx, pages).start()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Fortnite(bot))
