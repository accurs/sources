# HELLO I URGE YOU NOT TO EDIT ANYTHING IN HERE AS YOU WILL MOST LIKELY BREAK SHIT, THANK YOU. -COSMIN
import discord, aiohttp, datetime, secrets, string, os, asyncio, io, urllib.parse
from discord import app_commands, Embed
from discord.ext import commands
from typing import Optional, Union
from heist.framework.discord import CommandCache
from heist.framework.tools.separator import makeseparator
from heist.framework.discord.interactions import followup_warn, followup_approve
from heist.framework.discord.decorators import check_donor, check_famous, check_owner, check_blacklisted, owner_only, donor_only
from contextlib import suppress

SERVER_ID = int(os.getenv("SERVER_ID"))
ROLE_ID = int(os.getenv("ROLE_ID"))

def random_id():
    return ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(12))
def random_code(plan: str):
    prefix = "HEIST-LIFETIME-" if plan == "lifetime" else "HEIST-MONTHLY-"
    return prefix + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))
OXAPAY_KEY = os.getenv('OXAPAY_API_KEY')
PAYMENTS_WEBHOOK = os.getenv('PAYMENTS_WEBHOOK')
REDEMPTIONS_WEBHOOK = os.getenv('REDEMPTIONS_WEBHOOK')

class PremView(discord.ui.View):
    def __init__(self, *, timeout=300):
        super().__init__(timeout=timeout)
        self._orig_interaction: discord.Interaction | None = None
    def bind(self, interaction: discord.Interaction):
        self._orig_interaction = interaction
        return self
    async def on_timeout(self):
        try:
            for item in self.children:
                item.disabled = True
            if self._orig_interaction:
                try:
                    await self._orig_interaction.edit_original_response(view=self)
                except:
                    pass
        except:
            pass

class Premium(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.OXAPAY_KEY = OXAPAY_KEY
        self.PAYMENTS_WEBHOOK = PAYMENTS_WEBHOOK
        self.REDEMPTIONS_WEBHOOK = REDEMPTIONS_WEBHOOK

    premium = app_commands.Group(name="premium", description="Premium related commands", allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True), allowed_installs=app_commands.AppInstallationType(guild=True, user=True))
    gifts = app_commands.Group(name="gifts", description="Manage your Heist Premium gifts", parent=premium)

    async def cog_load(self):
        async with self.bot.pool.acquire() as conn:
            await conn.execute("""CREATE TABLE IF NOT EXISTS premium_gifts (gift_id TEXT PRIMARY KEY,user_id BIGINT,created_by BIGINT,plan TEXT,code TEXT,created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW())""")
            await conn.execute("""CREATE TABLE IF NOT EXISTS premium_gift_logs (id BIGSERIAL PRIMARY KEY,gift_id TEXT NOT NULL,action TEXT NOT NULL,actor_id BIGINT,target_user_id BIGINT,code TEXT,created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW())""")
        self.bot.add_listener(self.on_entitlement_create, "on_entitlement_create")

    @commands.Cog.listener()
    async def on_ready(self):
        if not hasattr(self.bot, "premium_sync"):
            self.bot.premium_sync = True
            self.bot.loop.create_task(self.sync_premium_ttls())
        if not hasattr(self.bot, "premium_expiry_listener"):
            self.bot.premium_expiry_listener = self.bot.loop.create_task(self.listen_premium_expiry())

    async def sync_premium_ttls(self):
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch("SELECT user_id, expires_at FROM donors WHERE expires_at IS NOT NULL")
        now = datetime.datetime.now(datetime.timezone.utc)
        for r in rows:
            uid = int(r["user_id"])
            expires_at = r["expires_at"]
            if expires_at <= now:
                await self.update_user_status(uid, "premium", "remove")
            else:
                ttl = int((expires_at - now).total_seconds())
                await self.bot.redis.setex(f"premium_expiry:{uid}", ttl, "1")

    async def listen_premium_expiry(self):
        await self.bot.wait_until_ready()
        redis = self.bot.redis
        pubsub = redis.pubsub()
        await pubsub.psubscribe("__keyevent@0__:expired")

        async for msg in pubsub.listen():
            if not msg or msg.get("type") != "pmessage":
                continue

            expired_key = msg["data"]
            if isinstance(expired_key, bytes):
                expired_key = expired_key.decode()

            if not expired_key.startswith("premium_expiry:"):
                continue

            user_id = int(expired_key.split("premium_expiry:")[1])

            await asyncio.sleep(2.5)

            donor = await self.bot.pool.fetchrow(
                "SELECT subscription_type, expires_at, updated_at FROM donors WHERE user_id=$1",
                str(user_id)
            )

            if not donor:
                continue

            if donor["subscription_type"] == "lifetime":
                continue

            expires_at = donor["expires_at"]
            updated_at = donor["updated_at"]

            now = datetime.datetime.now(datetime.timezone.utc)

            if updated_at and updated_at > (now - datetime.timedelta(seconds=3)):
                continue

            if expires_at and expires_at > now:
                continue

            await self.update_user_status(user_id, "premium", "remove")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id != SERVER_ID:
            return
        donor = await self.bot.redis.get(f"donor:{member.id}")
        if not donor or donor.decode().lower() != "true":
            return
        role = member.guild.get_role(ROLE_ID)
        if role:
            with suppress(Exception):
                await member.add_roles(role, reason="Heist Premium")

    async def send_purchase_log(self, title: str, description: str, user: discord.User | None = None):
        if not self.PAYMENTS_WEBHOOK:
            return
        try:
            embed = discord.Embed(title=title, description=description, color=self.bot.config.colors.information)
            if user:
                embed.set_thumbnail(url=user.display_avatar.url)
            async with aiohttp.ClientSession() as session:
                await session.post(self.PAYMENTS_WEBHOOK, json={"embeds": [embed.to_dict()]})
        except:
            pass

    async def send_redeem_log(self, user: discord.User, plan: str, code: str, gifted_by: int | None, expires_at: datetime.datetime | None):
        if not self.REDEMPTIONS_WEBHOOK:
            return
        try:
            giver = None
            if gifted_by:
                try:
                    giver = await self.bot.fetch_user(gifted_by)
                except:
                    pass

            desc = (
                f"**User:** <@{user.id}> (`{user.id}`)\n"
                f"**Plan:** **{plan.capitalize()}**\n"
                f"**Code:** `{code}`\n"
            )

            if plan == "monthly" and expires_at:
                ts = int(expires_at.timestamp())
                desc += f"**Expires On:** <t:{ts}:F> (<t:{ts}:R>)\n"

            if giver:
                desc += f"**Gifted By:** <@{giver.id}> (`{giver.id}`)\n"
            else:
                desc += f"**Gifted By:** *Unknown*\n"

            embed = discord.Embed(
                title=f"{self.bot.config.emojis.context.premium} Gift Redeemed",
                description=desc,
                color=self.bot.config.colors.information
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text="heist.lol", icon_url="https://git.cursi.ng/heist.png?a")
            embed.set_image(url="https://git.cursi.ng/separator.png")

            async with aiohttp.ClientSession() as session:
                await session.post(self.REDEMPTIONS_WEBHOOK, json={"embeds": [embed.to_dict()]})
        except:
            pass

    async def send_premium_dm(
        self, 
        user_id: int, 
        subscription_type: str, 
        purchase: bool, 
        code: str | None = None, 
        gifted_by: int | None = None
    ):
        bot = self.bot
        emoji = bot.config.emojis.context.premium
        color = await bot.get_color(user_id)

        if purchase:
            extra = "\n-# Your subscription will renew every month." if subscription_type == "Monthly" else ""
            desc = (
                f"You have been given **Premium {subscription_type}** on Heist.\n"
                f"Thank you for your purchase!\n\n"
                f"Make sure to join our [**Support server**](https://discord.gg/heistbot).{extra}"
            )
        else:
            gb = f"<@{gifted_by}>" if gifted_by is not None else "`Unknown`"
            desc = (
                f"You have been given **Premium {subscription_type}** on Heist.\n"
                f"Used code: **`{code}`** (Gifted by {gb})\n\n"
                f"Make sure to join our [**Support server**](https://discord.gg/heistbot)."
            )

        embed = discord.Embed(
            title=f"{emoji} Notice",
            description=desc,
            color=color
        )
        embed.set_thumbnail(url="https://git.cursi.ng/heist.png?a")
        embed.set_footer(text="heist.lol", icon_url="https://git.cursi.ng/heist.png?a")
        embed.set_image(url="https://git.cursi.ng/separator.png")

        try:
            user = await bot.fetch_user(int(user_id))
            await user.send(embed=embed)
        except Exception:
            pass

    async def on_entitlement_create(self, entitlement):
        try:
            lifetime_sku_id = 1430265452197707826
            monthly_sku_id = 1430265627691581666

            lifetime_gift_sku_id = 1438663198659055677
            monthly_gift_sku_id = 1438662919343571024

            user_id = entitlement.user.id
            user = await self.bot.fetch_user(user_id)
            sku = entitlement.sku_id

            if sku in (lifetime_gift_sku_id, monthly_gift_sku_id):
                gift_plan = "lifetime" if sku == lifetime_gift_sku_id else "monthly"
                gid = random_id()

                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO premium_gifts (gift_id, user_id, created_by, plan, code) VALUES ($1,$2,$3,$4,$5)",
                        gid, user_id, user_id, gift_plan, None
                    )
                    await conn.execute(
                        "INSERT INTO premium_gift_logs (gift_id, action, actor_id, target_user_id, code) VALUES ($1,$2,$3,$4,$5)",
                        gid, "created", user_id, user_id, None
                    )

                giftslist = await CommandCache.get_mention(self.bot, "premium gifts list")

                desc = (
                    f"You have been given a **Premium {gift_plan.capitalize()} gift** on Heist.\n"
                    f"You can view your gifts with {giftslist}.\n\n"
                    f"Make sure to join our [**Support server**](https://discord.gg/heistbot)."
                )

                embed = discord.Embed(
                    title=f"{self.bot.config.emojis.context.premium} Notice",
                    description=desc,
                    color=await self.bot.get_color(user_id)
                )
                embed.set_thumbnail(url="https://git.cursi.ng/heist.png?a")
                embed.set_footer(text="heist.lol", icon_url="https://git.cursi.ng/heist.png?a")
                embed.set_image(url="https://git.cursi.ng/separator.png")

                try:
                    u = await self.bot.fetch_user(user_id)
                    await u.send(embed=embed)
                except:
                    pass

                await self.send_purchase_log(
                    f"Purchase - Premium {gift_plan.capitalize()} Gift",
                    f"@{user.name} ({user.id}) just bought a **Premium {gift_plan.capitalize()} Gift** via Discord SKU.",
                    user
                )
                return

            if sku == lifetime_sku_id:
                sub = "lifetime"
                label = "Premium Lifetime"
            elif sku == monthly_sku_id:
                sub = "temporary"
                label = "Premium Monthly"
            else:
                sub = "temporary"
                label = "Premium Monthly"

            now = datetime.datetime.now(datetime.timezone.utc)
            existing = await self.bot.pool.fetchrow(
                "SELECT subscription_type, expires_at FROM donors WHERE user_id=$1",
                str(user_id)
            )

            if existing:
                current_type = existing["subscription_type"]
                current_exp = existing["expires_at"]

                if current_type == "lifetime":
                    gift_plan = "lifetime" if sub == "lifetime" else "monthly"
                    gid = random_id()
                    async with self.bot.pool.acquire() as conn:
                        await conn.execute(
                            "INSERT INTO premium_gifts (gift_id, user_id, created_by, plan, code) VALUES ($1,$2,$3,$4,$5)",
                            gid, user_id, user_id, gift_plan, None
                        )
                        await conn.execute(
                            "INSERT INTO premium_gift_logs (gift_id, action, actor_id, target_user_id, code) VALUES ($1,$2,$3,$4,$5)",
                            gid, "created", user_id, user_id, None
                        )

                    giftslist = await CommandCache.get_mention(self.bot, "premium gifts list")
                    try:
                        embed = discord.Embed(
                            title=f"{self.bot.config.emojis.context.premium} Notice",
                            description=(
                                f"You purchased **{label}**, but you already have **Premium Lifetime**.\n"
                                f"We have converted it into a **gift** for you.\n"
                                f"You can view your gifts with {giftslist}.\n\n"
                                "Make sure to join our [**Support server**](https://discord.gg/heistbot)."
                            ),
                            color=await self.bot.get_color(user_id)
                        )
                        embed.set_thumbnail(url="https://git.cursi.ng/heist.png?a")
                        embed.set_footer(text="heist.lol", icon_url="https://git.cursi.ng/heist.png?a")
                        embed.set_image(url="https://git.cursi.ng/separator.png")
                        await user.send(embed=embed)
                    except:
                        pass

                    await self.send_purchase_log(
                        "Purchase - Premium Auto-Converted (Had Lifetime)",
                        f"@{user.name} ({user.id}) purchased **{label}**, but already had Lifetime — converted to a gift.",
                        user
                    )
                    return

                if (
                    current_type == "temporary"
                    and current_exp is not None
                    and current_exp > now
                    and sub == "temporary"
                ):
                    gift_plan = "monthly"
                    gid = random_id()
                    async with self.bot.pool.acquire() as conn:
                        await conn.execute(
                            "INSERT INTO premium_gifts (gift_id, user_id, created_by, plan, code) VALUES ($1,$2,$3,$4,$5)",
                            gid, user_id, user_id, gift_plan, None
                        )
                        await conn.execute(
                            "INSERT INTO premium_gift_logs (gift_id, action, actor_id, target_user_id, code) VALUES ($1,$2,$3,$4,$5)",
                            gid, "created", user_id, user_id, None
                        )

                    giftslist = await CommandCache.get_mention(self.bot, "premium gifts list")
                    try:
                        embed = discord.Embed(
                            title=f"{self.bot.config.emojis.context.premium} Notice",
                            description=(
                                "You already have an active **Premium Monthly** subscription.\n\n"
                                "Your new purchase has been converted into a **Premium Monthly gift** instead.\n"
                                f"You can view your gifts with {giftslist}.\n\n"
                                "Make sure to join our [**Support server**](https://discord.gg/heistbot)."
                            ),
                            color=await self.bot.get_color(user_id)
                        )
                        embed.set_thumbnail(url="https://git.cursi.ng/heist.png?a")
                        embed.set_footer(text="heist.lol", icon_url="https://git.cursi.ng/heist.png?a")
                        embed.set_image(url="https://git.cursi.ng/separator.png")
                        await user.send(embed=embed)
                    except:
                        pass

                    await self.send_purchase_log(
                        "Purchase - Premium Auto-Converted (Had Monthly)",
                        f"@{user.name} ({user.id}) purchased **{label}**, but already had an active Monthly — converted to a gift.",
                        user
                    )
                    return

            expires_at = None if sub == "lifetime" else datetime.datetime.utcnow() + datetime.timedelta(days=30)

            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO donors (user_id, donor_status, subscription_type, expires_at)
                    VALUES ($1, 1, $2, $3)
                    ON CONFLICT (user_id)
                    DO UPDATE SET donor_status=1, subscription_type=$2, expires_at=$3, updated_at=NOW()
                    """,
                    str(user_id),
                    sub,
                    expires_at
                )

            await self.bot.redis.setex(f"donor:{user_id}", 300, "True")

            guild = self.bot.get_guild(SERVER_ID)
            if guild:
                role = guild.get_role(ROLE_ID)
                member = guild.get_member(int(user_id))
                if role and member:
                    with suppress(Exception):
                        await member.add_roles(role, reason="Premium purchased (Discord SKU)")

            await self.send_premium_dm(user_id, "Lifetime" if sub == "lifetime" else "Monthly", True)
            await self.send_purchase_log(
                f"Purchase - {label}",
                f"@{user.name} ({user.id}) just bought **{label}** via Discord SKU.",
                user
            )

        except Exception:
            pass

    async def update_user_status(
        self, 
        user_id, 
        status_type="premium", 
        action="add", 
        expires_at=None, 
        code=None, 
        gifted_by=None, 
        redeem_notice=False,
        skip_expiry_dm=False
    ):
        uid = str(user_id)
        if status_type == "premium":
            if action == "add":
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO donors (user_id, donor_status, subscription_type, expires_at)
                        VALUES ($1, 1, $2, $3)
                        ON CONFLICT (user_id)
                        DO UPDATE SET donor_status = 1, subscription_type = EXCLUDED.subscription_type,
                        expires_at = EXCLUDED.expires_at, updated_at = NOW()
                        """,
                        uid,
                        "lifetime" if expires_at is None else "temporary",
                        expires_at
                    )
                await self.bot.redis.setex(f"donor:{uid}", 300, "True")

                if expires_at is not None:
                    ttl = max(1, int((expires_at - datetime.datetime.now(datetime.timezone.utc)).total_seconds()))
                    await self.bot.redis.setex(f"premium_expiry:{uid}", ttl, "1")

                if redeem_notice:
                    sub_type = "Monthly" if expires_at is not None else "Lifetime"
                    await self.send_premium_dm(
                        int(user_id),
                        sub_type,
                        purchase=False,
                        code=code,
                        gifted_by=gifted_by
                    )
                else:
                    await self.send_premium_dm(
                        int(user_id),
                        "Monthly" if expires_at is not None else "Lifetime",
                        purchase=True
                    )

            elif action == "remove":
                async with self.bot.pool.acquire() as conn:
                    await conn.execute("DELETE FROM donors WHERE user_id = $1", uid)

                await self.bot.redis.setex(f"donor:{uid}", 300, "False")
                await self.bot.redis.delete(f"premium_expiry:{uid}")

                guild = self.bot.get_guild(SERVER_ID)
                if guild:
                    role = guild.get_role(ROLE_ID)
                    member = guild.get_member(int(user_id))
                    if role and member:
                        with suppress(Exception):
                            await member.remove_roles(role, reason="Premium expired")

                if not skip_expiry_dm:
                    try:
                        user = await self.bot.fetch_user(int(user_id))
                        premiumbuy = await CommandCache.get_mention(self.bot, "premium buy")
                        embed = Embed(
                            title=f"{self.bot.config.emojis.context.premium} Notice",
                            description=f"Your **Heist Premium** has expired.\n\nIf this was unexpected, you can renew anytime with {premiumbuy}.",
                            color=self.bot.config.colors.information
                        )
                        embed.set_thumbnail(url="https://git.cursi.ng/heist.png?a")
                        embed.set_footer(text="heist.lol", icon_url="https://git.cursi.ng/heist.png?a")
                        embed.set_image(url="https://git.cursi.ng/separator.png")
                        await user.send(embed=embed)
                    except:
                        pass

    @premium.command(name="syncrole", description="✨ Sync your Premium role on the Discord server")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @donor_only()
    async def syncrole(self, interaction: discord.Interaction):
        key = f"heist:syncrole:{interaction.user.id}"
        if await self.bot.redis.get(key):
            return await interaction.warn("Slow down. Try again in a moment.", ephemeral=True)
        await self.bot.redis.set(key, "1", ex=20)
        try:
            await interaction.response.defer(ephemeral=True)
            guild = self.bot.get_guild(SERVER_ID)
            if not guild:
                return await interaction.warn("The server is unavailable.")
            member = guild.get_member(interaction.user.id)
            if not member:
                return await interaction.warn("You are not in the Discord server.")
            role = guild.get_role(ROLE_ID)
            if not role:
                return await interaction.warn("Premium role not found.")
            if role in member.roles:
                return await interaction.warn("You already have the Premium role.", ephemeral=True)
            try:
                await member.add_roles(role, reason="Heist Premium")
                await interaction.approve("Your Premium role has been synced.")
            except:
                await interaction.warn("Failed to sync your role.")
        except Exception as e:
            await interaction.warn(e)

    @premium.command(description="Discover the perks of Heist Premium")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def perks(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        embed_color = await self.bot.get_color(ctx.author.id)
        class InitialView(PremView):
            def __init__(self, ctx, cog_instance, embed_color):
                super().__init__(timeout=300)
                self.ctx = ctx
                self.user = ctx.author
                self.cog = cog_instance
                self.embed_color = embed_color
            @discord.ui.button(label="Get Premium", emoji=discord.PartialEmoji.from_str("<:premstar:1311062009055285289>"), style=discord.ButtonStyle.secondary)
            async def get_premium_button(self, interaction2: discord.Interaction, button: discord.ui.Button):
                await self.cog.prem_purchase_ctx(interaction2)
            @discord.ui.button(label="View Perks", emoji=discord.PartialEmoji.from_str("<:sparkles2:1299136124991705219>"), style=discord.ButtonStyle.secondary)
            async def view_perks_button(self, interaction2: discord.Interaction, button: discord.ui.Button):
                embeds = []
                for page in range(1,8):
                    if page == 1:
                        tagscreate = await CommandCache.get_mention(self.cog.bot, "tags create")
                        roastuser = await CommandCache.get_mention(self.cog.bot, "roast")
                        rizzuser = await CommandCache.get_mention(self.cog.bot, "rizz")
                        embed = discord.Embed(title="Reduced cooldowns and limits!", description=("With [**`Heist Premium`**](https://heist.lol/premium), you will have your limits reduced as follows:\n\n"+f"* {tagscreate}:\n"+"> Max tags: **`5`** to **`20`**.\n"+"* **Transcribe VM (Menu)**:\n"+"> Transcription limit (Per VM): **`30s`** to **`2m30s`**.\n"+"> Daily usage limit: **`30`** to **`50`**.\n"+f"* {roastuser} / {rizzuser}:\n"+"> Hourly usage limit: **`25`** to **`unlimited`**."), color=self.embed_color)
                    elif page == 2:
                        deepgeolocate = await CommandCache.get_mention(self.cog.bot, "ai deepgeolocate")
                        embed = discord.Embed(title=f"{deepgeolocate}", description="Locate any image you wish, with the power of **AI**.", color=self.embed_color)
                        embed.set_image(url="https://images.guns.lol/TvZo8wkHHl.png")
                    elif page == 3:
                        aicustombuild = await CommandCache.get_mention(self.cog.bot, "custom ai build")
                        aicustomchat = await CommandCache.get_mention(self.cog.bot, "custom ai chat")
                        embed = discord.Embed(title=f"{aicustombuild} & {aicustomchat}", description="Create and speak to your own AI, with a range of models to choose from.", color=self.embed_color)
                        embed.set_image(url="https://images.guns.lol/0aCDOcljc9.png")
                    elif page == 4:
                        aiimagine = await CommandCache.get_mention(self.cog.bot, "ai imagine")
                        embed = discord.Embed(title=f"{aiimagine}", description="Generate anything your heart desires, with the power of **AI**.", color=self.embed_color)
                        embed.set_image(url="https://images.guns.lol/YvvjwJqA5L.png")
                    elif page == 5:
                        discord2roblox = await CommandCache.get_mention(self.cog.bot, "discord2roblox")
                        roblox2discord = await CommandCache.get_mention(self.cog.bot, "roblox2discord")
                        embed = discord.Embed(title=f"{discord2roblox} & {roblox2discord}", description="Find someone's [**`Roblox`**](https://roblox.com) thru Discord and vice versa.", color=self.embed_color)
                        embed.set_image(url="https://images.guns.lol/f7fpTOO3ne.png")
                    elif page == 6:
                        cryptotrack = await CommandCache.get_mention(self.cog.bot, "crypto track")
                        embed = discord.Embed(title=f"{cryptotrack}", description="Track cryptocurrency confirmations in **real-time**.", color=self.embed_color)
                        embed.set_image(url="https://images.guns.lol/e3425831e184d2ccea6b3e347d4ac53b32baf9b7/N5ArsAPKSD.png")
                    elif page == 7:
                        embed = discord.Embed(title="And even more!", description="Discover all of Heist's features on [heist.lol](https://heist.lol/commands)..\nWho knows, there might even be hidden perks.", color=self.embed_color)
                    embed.set_author(name=self.user.name, icon_url=self.user.avatar.url if self.user.avatar else None)
                    embed.set_thumbnail(url="https://git.cursi.ng/sparkles.png")
                    embed.set_footer(text=f"Page {page}/7 - heist.lol", icon_url="https://git.cursi.ng/heist.png?a")
                    embeds.append(embed)
                await interaction2.response.send_message(embed=embeds[0], ephemeral=True)
                msg = await interaction2.original_response()
                ctx_local = self.ctx
                ctx_local.config = self.cog.bot.config
                from heist.framework.pagination import Paginator
                paginator = Paginator(ctx_local, embeds, embed=True, hide_footer=True, message=msg)
                await paginator.start()
        initial_embed = discord.Embed(title="Premium Perks", description=("> Get access to **exclusive benefits** with [**`Heist Premium`**](https://heist.lol/premium)!\n"+"> From **deep AI integrations** and **economy perks** to other **powerful features**.\n"+"> Discover all the perks below."), color=embed_color)
        initial_embed.set_thumbnail(url="https://git.cursi.ng/premium2.gif")
        initial_embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        initial_embed.set_footer(text="heist.lol", icon_url="https://git.cursi.ng/heist.png?a?c")
        view = InitialView(ctx, self, embed_color).bind(interaction)
        await ctx.send(embed=initial_embed, view=view)

    @premium.command()
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def buy(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await self.prem_purchase(ctx)

    async def prem_purchase_ctx(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        await self.prem_purchase(ctx)

    async def prem_purchase(self, ctx: commands.Context):
        try:
            sixseven = await self.bot.get_color(ctx.author.id)
            embed = discord.Embed(title="Heist Premium", url="https://heist.lol/premium", description="Get Heist's **Premium** plan and unlock a variety of new features.\n\n-# **Product Unavailable?** Use Discord on PC or the [Web](https://discord.com/app) version on mobile.", color=sixseven)
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            embed.set_author(name=f"{ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            prem1 = discord.ui.Button(style=discord.ButtonStyle.premium, sku_id=1430265452197707826)
            prem2 = discord.ui.Button(style=discord.ButtonStyle.premium, sku_id=1430265627691581666)
            crypto_button = discord.ui.Button(style=discord.ButtonStyle.secondary, label="Crypto", emoji="<:crypto:1324215914702569572>")
            async def crypto_button_callback(interaction: discord.Interaction):
                class PremiumSelect(discord.ui.Select):
                    def __init__(self, parent_cog, bot):
                        self.parent_cog = parent_cog
                        self.bot = bot
                        options = [discord.SelectOption(label="Lifetime ($7.99)", value="lifetime", description="One-time payment"), discord.SelectOption(label="Monthly ($3.99)", value="monthly", description="Recurring payment")]
                        super().__init__(placeholder="Select Premium type...", options=options)
                    async def callback(self, select_interaction: discord.Interaction):
                        if select_interaction.user.id != interaction.user.id:
                            await select_interaction.response.warn("This is not your purchase.", ephemeral=True)
                            return
                        cooldown_key = f"invoice_cooldown:premium:{interaction.user.id}"
                        if await self.bot.redis.get(cooldown_key):
                            await select_interaction.response.warn("You recently created an invoice. Please wait before creating another.", ephemeral=True)
                            return
                        await select_interaction.response.defer(ephemeral=True)
                        plan = self.values[0]
                        amount = 7.99 if plan == "lifetime" else 3.99
                        redis_key = f"active_{plan}_invoice:{interaction.user.id}"
                        existing_invoice = await self.bot.redis.get(redis_key)
                        if existing_invoice:
                            await select_interaction.followup.send("Complete the existing invoice sent to your DMs.", ephemeral=True)
                            return
                        try:
                            async with aiohttp.ClientSession() as session:
                                async with session.post("https://api.oxapay.com/merchants/request", json={"merchant": self.parent_cog.OXAPAY_KEY, "amount": amount, "currency": "USD", "lifeTime": 60, "feePaidByPayer": 0, "underPaidCover": amount * 0.5, "returnUrl": "https://heist.lol", "description": f"Heist Premium ({plan})", "orderId": f"ORD-{interaction.user.id}-{plan}", "email": "admin@ignore.me"}) as response:
                                    data = await response.json()
                            if data.get('result') not in [0, 100]:
                                await select_interaction.followup.send("Error creating invoice.", ephemeral=True)
                                return
                            track_id = data.get('trackId')
                            pay_link = data.get('payLink')
                            expires_on = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=60)
                            expiration = int(expires_on.timestamp())
                            await self.bot.redis.setex(f"active_{plan}_invoice:{interaction.user.id}", 120, track_id)
                            await self.bot.redis.setex(cooldown_key, 120, "1")
                            dm_embed = discord.Embed(title=f"Heist Premium ({plan.capitalize()})", url=pay_link, description=f"* Payment Details:\n  * Amount: **{amount} USD**\n  * Status: **Waiting**\n-# Expires on <t:{expiration}:f> (<t:{expiration}:R>)\n\n-# [Additional Support](https://discord.gg/heistbot)", color=0xfbab74)
                            dm_embed.set_thumbnail(url=interaction.user.display_avatar.url)
                            pay_button = discord.ui.Button(label="Pay", url=pay_link)
                            check_button = discord.ui.Button(label="Check Payment", style=discord.ButtonStyle.green, emoji="<a:loading:1392217668383408148>")
                            other_button = discord.ui.Button(label="PayPal/Other", style=discord.ButtonStyle.blurple, emoji="<:paypal:1269644635236466758>")
                            view = discord.ui.View(timeout=7200)
                            view.user_id = str(interaction.user.id)
                            view.expiration = expiration
                            view.plan = plan
                            view.embed = dm_embed
                            view.track_id = track_id
                            view.add_item(pay_button)
                            view.add_item(check_button)
                            view.add_item(other_button)
                            async def check_payment_callback(check_interaction: discord.Interaction):
                                try:
                                    if str(check_interaction.user.id) != view.user_id:
                                        await check_interaction.response.warn("You cannot interact with someone else's payment.", ephemeral=True)
                                        return

                                    lock_key = f"payment_lock:{view.track_id}"
                                    got_lock = await self.bot.redis.setnx(lock_key, "1")
                                    if not got_lock:
                                        await check_interaction.response.warn("Processing your payment.. try again in a moment.", ephemeral=True)
                                        return
                                    await self.bot.redis.expire(lock_key, 20)

                                    invoice_done = f"invoice_complete:{view.track_id}"
                                    if await self.bot.redis.get(invoice_done):
                                        await check_interaction.response.warn("This payment is already processed.", ephemeral=True)
                                        await self.bot.redis.delete(lock_key)
                                        return

                                    await check_interaction.response.defer()
                                    embed_obj = view.embed
                                    now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

                                    if now_ts > view.expiration:
                                        pay_button.disabled = True
                                        check_button.disabled = True
                                        other_button.disabled = True
                                        embed_obj.description = (
                                            f"* Payment Details:\n"
                                            f"  * Amount: **{amount} USD**\n"
                                            f"  * Status: **Expired**\n"
                                            f"-# Expired on <t:{view.expiration}:f>\n\n"
                                            f"-# [Additional Support](https://discord.gg/heistbot)"
                                        )
                                        await check_interaction.edit_original_response(embed=embed_obj, view=view)
                                        await self.bot.redis.delete(f"active_{view.plan}_invoice:{check_interaction.user.id}")
                                        await self.bot.redis.delete(lock_key)
                                        return

                                    async with aiohttp.ClientSession() as session:
                                        async with session.post(
                                            "https://api.oxapay.com/merchants/inquiry",
                                            json={"merchant": self.parent_cog.OXAPAY_KEY, "trackId": view.track_id}
                                        ) as response:
                                            payment_data = await response.json()

                                    if payment_data.get("result") == 100:
                                        payment_status = (payment_data.get("status") or "").lower()

                                        if payment_status == "paid":
                                            processing_key = f"invoice_processing:{view.track_id}"
                                            already_processing = await self.bot.redis.setnx(processing_key, "1")
                                            if not already_processing:
                                                await check_interaction.followup.send("Payment is already being processed.", ephemeral=True)
                                                await self.bot.redis.delete(lock_key)
                                                return
                                            await self.bot.redis.expire(processing_key, 300)

                                            await self.bot.redis.setex(invoice_done, 86400, "1")

                                            try:
                                                await self.parent_cog.send_purchase_log(
                                                    f"Purchase - Premium {view.plan.capitalize()} (Crypto)",
                                                    f"User: <@{check_interaction.user.id}> (`{check_interaction.user.id}`)\n"
                                                    f"Plan: **{view.plan.capitalize()}**\n"
                                                    f"Amount: **${amount}**\n"
                                                    f"Track ID: `{view.track_id}`",
                                                    check_interaction.user
                                                )
                                            except Exception:
                                                pass

                                            user = check_interaction.user
                                            donor = await self.parent_cog.bot.pool.fetchrow(
                                                "SELECT subscription_type FROM donors WHERE user_id=$1",
                                                str(user.id)
                                            )
                                            converted = False

                                            if donor and donor["subscription_type"] == "lifetime":
                                                gift_plan = "lifetime" if view.plan == "lifetime" else "monthly"
                                                gid = random_id()
                                                async with self.parent_cog.bot.pool.acquire() as conn:
                                                    await conn.execute(
                                                        "INSERT INTO premium_gifts (gift_id, user_id, created_by, plan, code) VALUES ($1,$2,$3,$4,$5)",
                                                        gid, user.id, user.id, gift_plan, None
                                                    )
                                                    await conn.execute(
                                                        "INSERT INTO premium_gift_logs (gift_id, action, actor_id, target_user_id, code) VALUES ($1,$2,$3,$4,$5)",
                                                        gid, "created", user.id, user.id, None
                                                    )
                                                converted = True

                                            elif donor and donor["subscription_type"] == "temporary" and view.plan == "monthly":
                                                gid = random_id()
                                                async with self.parent_cog.bot.pool.acquire() as conn:
                                                    await conn.execute(
                                                        "INSERT INTO premium_gifts (gift_id, user_id, created_by, plan, code) VALUES ($1,$2,$3,$4,$5)",
                                                        gid, user.id, user.id, "monthly", None
                                                    )
                                                    await conn.execute(
                                                        "INSERT INTO premium_gift_logs (gift_id, action, actor_id, target_user_id, code) VALUES ($1,$2,$3,$4,$5)",
                                                        gid, "created", user.id, user.id, None
                                                    )
                                                converted = True

                                            else:
                                                expires_at = None if view.plan == "lifetime" else (datetime.datetime.utcnow() + datetime.timedelta(days=30))
                                                await self.parent_cog.update_user_status(user.id, "premium", "add", expires_at)

                                                guild = self.parent_cog.bot.get_guild(SERVER_ID)
                                                if guild:
                                                    role = guild.get_role(ROLE_ID)
                                                    member = guild.get_member(user.id)
                                                    if role and member:
                                                        with suppress(Exception):
                                                            await member.add_roles(role, reason="Premium purchased (Crypto)")

                                            await self.bot.redis.delete(f"active_{view.plan}_invoice:{check_interaction.user.id}")
                                            await self.bot.redis.delete(lock_key)

                                            pay_button.disabled = True
                                            check_button.disabled = True
                                            other_button.disabled = True

                                            msg = "Payment completed (converted to gift)" if converted else "Payment completed"
                                            embed_obj.description = (
                                                f"* Payment Details:\n"
                                                f"  * Amount: **{amount} USD**\n"
                                                f"  * Status: **{msg}**\n"
                                                f"-# Expires on <t:{view.expiration}:f> (<t:{view.expiration}:R>)\n\n"
                                                f"-# [Additional Support](https://discord.gg/heistbot)"
                                            )
                                            await check_interaction.edit_original_response(embed=embed_obj, view=view)
                                            return

                                        if payment_status == "expired":
                                            pay_button.disabled = True
                                            check_button.disabled = True
                                            other_button.disabled = True
                                            embed_obj.description = (
                                                f"* Payment Details:\n"
                                                f"  * Amount: **{amount} USD**\n"
                                                f"  * Status: **Expired**\n"
                                                f"-# Expired on <t:{view.expiration}:f>\n\n"
                                                f"-# [Additional Support](https://discord.gg/heistbot)"
                                            )
                                            await self.bot.redis.delete(f"active_{view.plan}_invoice:{check_interaction.user.id}")
                                            await self.bot.redis.delete(lock_key)
                                            await check_interaction.edit_original_response(embed=embed_obj, view=view)
                                            return

                                        msg = "Confirming payment" if payment_status == "confirming" else "Awaiting payment"
                                        embed_obj.description = (
                                            f"* Payment Details:\n"
                                            f"  * Amount: **{amount} USD**\n"
                                            f"  * Status: **{msg}**\n"
                                            f"-# Expires on <t:{view.expiration}:f> (<t:{view.expiration}:R>)\n\n"
                                            f"-# [Additional Support](https://discord.gg/heistbot)"
                                        )
                                        await check_interaction.edit_original_response(embed=embed_obj, view=view)
                                        await self.bot.redis.delete(lock_key)
                                        return

                                    await check_interaction.followup.send("Failed to check payment status. Make a ticket at https://discord.gg/heistbot.", ephemeral=True)
                                    await self.bot.redis.delete(lock_key)

                                except:
                                    try:
                                        await check_interaction.followup.send("An error occurred while checking payment.", ephemeral=True)
                                    except:
                                        pass
                                    await self.bot.redis.delete(f"payment_lock:{view.track_id}")
                            check_button.callback = check_payment_callback
                            async def other_button_callback(other_interaction: discord.Interaction):
                                await other_interaction.response.send_message("To purchase via PayPal or other methods, please make a ticket in https://discord.gg/heistbot", ephemeral=True)
                            other_button.callback = other_button_callback
                            try:
                                await interaction.user.send(embed=dm_embed, view=view)
                                await select_interaction.followup.send("Check your DMs for the payment details.", ephemeral=True)
                            except:
                                await select_interaction.followup.send("Could not send payment details to your DMs. Please enable DMs and try again.", ephemeral=True)
                        except:
                            await select_interaction.followup.send("An error occurred.", ephemeral=True)
                select_view = PremView(timeout=300).bind(interaction)
                select_view.add_item(PremiumSelect(self, self.bot))
                await interaction.response.send_message("To continue to your Heist premium purchase:", view=select_view, ephemeral=True)
            crypto_button.callback = crypto_button_callback
            view = PremView(timeout=500)
            view.add_item(prem1)
            view.add_item(prem2)
            view.add_item(crypto_button)
            await ctx.send(embed=embed, view=view)
        except:
            await ctx.warn("An error occurred while processing your request.")

    @gifts.command(name="buy", description="Gift your friends Heist Premium")
    async def gifts_buy(self, interaction: discord.Interaction):
        color = await self.bot.get_color(interaction.user.id)
        embed = discord.Embed(title="Gift Heist Premium", description="Gift your friends Heist Premium.\n\nChoose a plan below.", color=color)
        embed.set_thumbnail(url="https://git.cursi.ng/gift.png")
        select = discord.ui.Select(
            placeholder="Select a gift plan..",
            options=[
                discord.SelectOption(label="Heist Premium Lifetime ($7.99)", value="lifetime"),
                discord.SelectOption(label="Heist Premium Monthly ($3.99)", value="monthly")
            ]
        )
        async def select_callback(inter2: discord.Interaction):
            if inter2.user.id != interaction.user.id:
                await inter2.response.warn("This is not your selection.", ephemeral=True)
                return
            new_embed = discord.Embed(title=f"${'7.99' if select.values[0]=='lifetime' else '3.99'} - 1x Premium {select.values[0].capitalize()} gift", description="Choose payment method below.", color=color)
            new_embed.set_thumbnail(url=interaction.user.display_avatar.url)
            crypto_button = discord.ui.Button(style=discord.ButtonStyle.secondary, label="Crypto", emoji="<:crypto:1324215914702569572>")
            async def crypto_button_callback(i3: discord.Interaction):
                if i3.user.id != interaction.user.id:
                    await i3.response.warn("This is not your purchase.", ephemeral=True)
                    return
                await self.crypto_payment_gift(i3, select.values[0])
            crypto_button.callback = crypto_button_callback
            v = PremView(timeout=300).bind(inter2)
            v.add_item(crypto_button)
            await inter2.response.edit_message(embed=new_embed, view=v)
        select.callback = select_callback
        view = PremView(timeout=120).bind(interaction)
        view.add_item(select)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def crypto_payment_gift(self, interaction: discord.Interaction, plan: str):
        amount = 7.99 if plan == "lifetime" else 3.99
        redis_key = f"active_gift_invoice:{interaction.user.id}"
        cooldown_key = f"invoice_cooldown:gift:{interaction.user.id}"
        if await self.bot.redis.get(cooldown_key):
            await interaction.response.warn("You recently created an invoice. Please wait before creating another.", ephemeral=True)
            return
        if await self.bot.redis.get(redis_key):
            await interaction.response.warn("Complete the existing invoice sent to your DMs.", ephemeral=True)
            return
        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.oxapay.com/merchants/request", json={"merchant": self.OXAPAY_KEY, "amount": amount, "currency": "USD", "lifeTime": 60, "feePaidByPayer": 0, "underPaidCover": amount * 0.5, "returnUrl": "https://heist.lol", "description": f"Heist Premium ({plan})", "orderId": f"ORD-{interaction.user.id}-gift-{plan}", "email": "admin@ignore.me"}) as response:
                data = await response.json()
        if data.get('result') not in [0, 100]:
            await interaction.response.warn("Error creating invoice.", ephemeral=True)
            return
        track_id = data.get('trackId')
        pay_link = data.get('payLink')
        expires_on = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=60)
        expiration = int(expires_on.timestamp())
        await self.bot.redis.setex(redis_key, 3600, track_id)
        await self.bot.redis.setex(cooldown_key, 120, "1")
        dm_embed = discord.Embed(title=f"Heist Premium Gift ({plan.capitalize()})", url=pay_link, description=f"* Payment Details:\n  * Amount: **{amount} USD**\n  * Status: **Waiting**\n-# Expires on <t:{expiration}:f> (<t:{expiration}:R>)\n\n-# After payment is confirmed, a gift will be added to your inventory.\n-# [Additional Support](https://discord.gg/heistbot)", color=0xfbab74)
        dm_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        pay_button = discord.ui.Button(label="Pay", url=pay_link)
        check_button = discord.ui.Button(label="Check Payment", style=discord.ButtonStyle.green, emoji="<a:loading:1392217668383408148>")
        other_button = discord.ui.Button(label="PayPal/Other", style=discord.ButtonStyle.blurple, emoji="<:paypal:1269644635236466758>")
        v = discord.ui.View(timeout=7200)
        v.user_id = str(interaction.user.id)
        v.expiration = expiration
        v.embed = dm_embed
        v.track_id = track_id
        v.plan = plan
        v.add_item(pay_button)
        v.add_item(check_button)
        v.add_item(other_button)
        async def check_payment_callback(check_interaction: discord.Interaction):
            try:
                if str(check_interaction.user.id) != v.user_id:
                    await check_interaction.response.warn("You cannot interact with someone else's payment.", ephemeral=True)
                    return

                lock_key = f"payment_lock:{v.track_id}"
                got_lock = await self.bot.redis.setnx(lock_key, "1")
                if not got_lock:
                    await check_interaction.response.warn("Processing your payment.. try again in a moment.", ephemeral=True)
                    return
                await self.bot.redis.expire(lock_key, 20)

                invoice_done = f"invoice_complete:{v.track_id}"
                if await self.bot.redis.get(invoice_done):
                    await check_interaction.response.warn("This payment is already processed.", ephemeral=True)
                    await self.bot.redis.delete(lock_key)
                    return

                await check_interaction.response.defer()
                embed_obj = v.embed
                now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

                if now_ts > v.expiration:
                    pay_button.disabled = True
                    check_button.disabled = True
                    other_button.disabled = True
                    embed_obj.description = (
                        f"* Payment Details:\n"
                        f"  * Amount: **{amount} USD**\n"
                        f"  * Status: **Expired**\n"
                        f"-# Expired on <t:{v.expiration}:f>\n\n"
                        f"-# [Additional Support](https://discord.gg/heistbot)"
                    )
                    await check_interaction.edit_original_response(embed=embed_obj, view=v)
                    await self.bot.redis.delete(redis_key)
                    await self.bot.redis.delete(lock_key)
                    return

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.oxapay.com/merchants/inquiry",
                        json={"merchant": self.OXAPAY_KEY, "trackId": v.track_id}
                    ) as response:
                        payment_data = await response.json()

                if payment_data.get("result") == 100:
                    status = (payment_data.get("status") or "").lower()

                    if status == "paid":
                        processing_key = f"invoice_processing:{v.track_id}"
                        already_processing = await self.bot.redis.setnx(processing_key, "1")
                        if not already_processing:
                            await check_interaction.followup.send("Payment is already being processed.", ephemeral=True)
                            await self.bot.redis.delete(lock_key)
                            return
                        await self.bot.redis.expire(processing_key, 300)

                        await self.bot.redis.setex(invoice_done, 86400, "1")

                        try:
                            await self.send_purchase_log(
                                f"Purchase - Premium {v.plan.capitalize()} Gift (Crypto)",
                                f"User: <@{check_interaction.user.id}> (`{check_interaction.user.id}`)\n"
                                f"Gift Plan: **{v.plan.capitalize()}**\n"
                                f"Amount: **${amount}**\n"
                                f"Track ID: `{v.track_id}`",
                                check_interaction.user
                            )
                        except Exception:
                            pass

                        gid = random_id()
                        async with self.bot.pool.acquire() as conn:
                            await conn.execute(
                                "INSERT INTO premium_gifts (gift_id, user_id, created_by, plan, code) VALUES ($1,$2,$3,$4,$5)",
                                gid, check_interaction.user.id, check_interaction.user.id, v.plan, None
                            )
                            await conn.execute(
                                "INSERT INTO premium_gift_logs (gift_id, action, actor_id, target_user_id, code) VALUES ($1,$2,$3,$4,$5)",
                                gid, "created", check_interaction.user.id, check_interaction.user.id, None
                            )

                        await self.bot.redis.delete(redis_key)
                        await self.bot.redis.delete(lock_key)

                        pay_button.disabled = True
                        check_button.disabled = True
                        other_button.disabled = True

                        embed_obj.description = (
                            f"* Payment Details:\n"
                            f"  * Amount: **{amount} USD**\n"
                            f"  * Status: **Payment completed**\n"
                            f"-# Expires on <t:{v.expiration}:f> (<t:{v.expiration}:R>)\n\n"
                            f"-# A gift has been added to your inventory.\n"
                            f"-# [Additional Support](https://discord.gg/heistbot)"
                        )
                        await check_interaction.edit_original_response(embed=embed_obj, view=v)
                        return

                    if status == "expired":
                        await self.bot.redis.delete(redis_key)
                        await self.bot.redis.delete(lock_key)

                        pay_button.disabled = True
                        check_button.disabled = True
                        other_button.disabled = True

                        embed_obj.description = (
                            f"* Payment Details:\n"
                            f"  * Amount: **{amount} USD**\n"
                            f"  * Status: **Expired**\n"
                            f"-# Expired on <t:{v.expiration}:f>\n\n"
                            f"-# [Additional Support](https://discord.gg/heistbot)"
                        )
                        await check_interaction.edit_original_response(embed=embed_obj, view=v)
                        return

                    msg = "Confirming payment" if status == "confirming" else "Awaiting payment"
                    embed_obj.description = (
                        f"* Payment Details:\n"
                        f"  * Amount: **{amount} USD**\n"
                        f"  * Status: **{msg}**\n"
                        f"-# Expires on <t:{v.expiration}:f> (<t:{v.expiration}:R>)\n\n"
                        f"-# [Additional Support](https://discord.gg/heistbot)"
                    )
                    await check_interaction.edit_original_response(embed=embed_obj, view=v)
                    await self.bot.redis.delete(lock_key)
                    return

                await check_interaction.followup.send("Failed to check payment status. Make a ticket at https://discord.gg/heistbot.", ephemeral=True)
                await self.bot.redis.delete(lock_key)

            except:
                try:
                    await check_interaction.followup.send("An error occurred while checking payment.", ephemeral=True)
                except:
                    pass
                await self.bot.redis.delete(f"payment_lock:{v.track_id}")
        check_button.callback = check_payment_callback
        async def other_button_callback(other_interaction: discord.Interaction):
            await other_interaction.response.send_message("To purchase via PayPal or other methods, please open a ticket.", ephemeral=True)
        other_button.callback = other_button_callback
        try:
            await interaction.user.send(embed=dm_embed, view=v)
            await interaction.response.send_message("Check your DMs for invoice details.", ephemeral=True)
        except:
            await interaction.response.warn("Could not send details to your DMs. Enable DMs and try again.", ephemeral=True)

    @gifts.command(name="list", description="View your Heist Premium gifts")
    async def gifts_list(self, interaction: discord.Interaction):
        async def build(page_index: int = 0):
            async with self.bot.pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM premium_gifts WHERE user_id=$1 AND status NOT IN ('revoked','redeemed') ORDER BY created_at DESC",
                    interaction.user.id
                )
            color = await self.bot.get_color(interaction.user.id)
            if not rows:
                return [], [], color, 0
            lines = []
            for r in rows:
                suffix = " (code)" if r["status"] == "code_generated" else ""
                lines.append(f"**Premium {r['plan'].capitalize()}** - **`{r['gift_id']}`**{suffix}")
            pages = [lines[i:i + 10] for i in range(0, len(lines), 10)]
            embeds = []
            for i, group in enumerate(pages, 1):
                e = discord.Embed(
                    title=f"{interaction.user.name}'s Heist Gifts",
                    description="\n".join(group),
                    color=color
                )
                e.set_thumbnail(url=interaction.user.display_avatar.url)
                e.set_footer(text=f"Page {i}/{len(pages)} • {len(lines)} gifts")
                embeds.append(e)
            start = page_index * 10
            end = start + 10
            visible_rows = rows[start:end]
            options = [discord.SelectOption(label=r['gift_id'], value=r['gift_id']) for r in visible_rows]
            return embeds, options, color, len(pages)

        embeds, options, color, _ = await build(0)
        if not embeds:
            await interaction.response.warn("You have no gifts available.", ephemeral=True)
            return

        select = discord.ui.Select(placeholder="View gift..", options=options)
        ctx = await commands.Context.from_interaction(interaction)
        from heist.framework.pagination import Paginator

        async def select_callback(inter):
            if inter.user.id != interaction.user.id:
                await inter.response.warn("This is not your inventory.", ephemeral=True)
                return
            gid = select.values[0]
            row = await self.bot.pool.fetchrow(
                "SELECT * FROM premium_gifts WHERE gift_id=$1 AND user_id=$2",
                gid, inter.user.id
            )
            if not row:
                await inter.response.warn("Gift not found.", ephemeral=True)
                return
            if row["status"] == "redeemed":
                await inter.response.warn("This gift has already been redeemed.", ephemeral=True)
                return
            c = await self.bot.get_color(inter.user.id)
            em = discord.Embed(description=f"Gift: Premium {row['plan'].capitalize()} - {gid}", color=c)

            if row["status"] == "code_generated":
                em.description = f"**`{row['code']}`**"
                revoke_button = discord.ui.Button(label="Revoke", style=discord.ButtonStyle.danger)

                async def revoke(inter2):
                    if inter2.user.id != inter.user.id:
                        await inter2.response.warn("This is not your gift.", ephemeral=True)
                        return
                    await self.bot.pool.execute(
                        "UPDATE premium_gifts SET code=NULL, status='active' WHERE gift_id=$1",
                        gid
                    )
                    em.description = "This gift was revoked."
                    embeds2, options2, _, _ = await build(paginator.index)
                    select.options = options2
                    paginator.pages = embeds2
                    paginator.add_persistent_item(select)
                    page = paginator.pages[paginator.index]
                    await paginator.message.edit(embed=page, view=paginator)
                    await inter2.response.edit_message(embed=em, view=PremView(timeout=1))

                revoke_button.callback = revoke
                v = PremView(timeout=300).bind(inter)
                v.add_item(revoke_button)
                await inter.response.send_message(embed=em, view=v, ephemeral=True)

            else:
                gen_button = discord.ui.Button(label="Generate", style=discord.ButtonStyle.success)

                async def gen(inter2):
                    if inter2.user.id != inter.user.id:
                        await inter2.response.warn("This is not your gift.", ephemeral=True)
                        return
                    code = random_code(row["plan"])
                    await self.bot.pool.execute(
                        "UPDATE premium_gifts SET code=$1, status='code_generated' WHERE gift_id=$2",
                        code, gid
                    )
                    em.description = f"**`{code}`**"
                    revoke_button = discord.ui.Button(label="Revoke", style=discord.ButtonStyle.danger)

                    async def revoke2(i3):
                        if i3.user.id != inter.user.id:
                            await i3.response.warn("This is not your gift.", ephemeral=True)
                            return
                        await self.bot.pool.execute(
                            "UPDATE premium_gifts SET code=NULL, status='active' WHERE gift_id=$1",
                            gid
                        )
                        em.description = "This gift was revoked."
                        embeds2, options2, _, _ = await build(paginator.index)
                        select.options = options2
                        paginator.pages = embeds2
                        paginator.add_persistent_item(select)
                        page = paginator.pages[paginator.index]
                        await paginator.message.edit(embed=page, view=paginator)
                        await i3.response.edit_message(embed=em, view=PremView(timeout=1))

                    revoke_button.callback = revoke2

                    embeds2, options2, _, _ = await build(paginator.index)
                    select.options = options2
                    paginator.pages = embeds2
                    paginator.add_persistent_item(select)
                    page = paginator.pages[paginator.index]
                    await paginator.message.edit(embed=page, view=paginator)

                    v2 = PremView(timeout=300).bind(inter2)
                    v2.add_item(revoke_button)
                    await inter2.response.edit_message(embed=em, view=v2)

                gen_button.callback = gen
                v = PremView(timeout=300).bind(inter)
                v.add_item(gen_button)
                await inter.response.send_message(embed=em, view=v, ephemeral=True)

        select.callback = select_callback

        async def on_page_switch(p):
            embeds2, options2, _, _ = await build(p.index)
            select.options = options2
            p.pages = embeds2
            p.add_persistent_item(select)
            page = p.pages[p.index]
            await p.message.edit(embed=page, view=p)

        paginator = Paginator(ctx, embeds, embed=True, hide_nav=False, hide_footer=True, message=None, on_page_switch=on_page_switch)
        paginator.add_persistent_item(select)
        await interaction.response.send_message(embed=embeds[0], view=paginator, ephemeral=True)
        paginator.message = await interaction.original_response()
        paginator.ctx = ctx

    @gifts.command(name="redeem", description="Redeem a Heist Premium gift code")
    @app_commands.describe(code="The code to redeem")
    async def gifts_redeem(self, interaction: discord.Interaction, code: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        giftslist = await CommandCache.get_mention(self.bot, "premium gifts list")

        if len(code) == 12 and code.isalnum():
            async with self.bot.pool.acquire() as conn:
                maybe_gift_id = await conn.fetchrow(
                    "SELECT gift_id FROM premium_gifts WHERE gift_id=$1",
                    code
                )

            if maybe_gift_id:
                await followup_warn(
                    interaction,
                    f"This is a **Gift ID**, not an actual gift code.\n"
                    f"-# You can use {giftslist} to activate gifts and retrieve their codes.",
                    ephemeral=True
                )
                return
            
        async with self.bot.pool.acquire() as conn:
            gift = await conn.fetchrow(
                "SELECT * FROM premium_gifts WHERE code=$1 AND status='code_generated'",
                code
            )

        if not gift:
            await followup_warn(interaction, "Invalid or expired code.", ephemeral=True)
            return

        donor = await self.bot.pool.fetchrow(
            "SELECT subscription_type, expires_at FROM donors WHERE user_id=$1",
            str(interaction.user.id)
        )

        if donor:
            if donor["subscription_type"] == "lifetime":
                await followup_warn(interaction, "You already have **Premium Lifetime**.", ephemeral=True)
                return

            if donor["subscription_type"] == "temporary":
                if gift["plan"] == "monthly":
                    await followup_warn(interaction,
                        "You already have an active **Premium Monthly** subscription.\n"
                        "You can only redeem **Premium Lifetime** codes to upgrade.",
                        ephemeral=True
                    )
                    return

                await self.update_user_status(interaction.user.id, "premium", "remove")
                await self.bot.redis.delete(f"premium_expiry:{interaction.user.id}")
                donor = None

        expires_at = None
        if gift["plan"] == "monthly":
            expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)

        async with self.bot.pool.acquire() as conn:
            redeemed = await conn.fetchrow(
                "UPDATE premium_gifts "
                "SET status='redeemed', user_id=$1, redeemed_at=NOW() "
                "WHERE gift_id=$2 AND code=$3 AND status='code_generated' "
                "RETURNING *",
                interaction.user.id, gift["gift_id"], code
            )

        if not redeemed:
            await followup_warn(interaction, "Invalid or expired code.", ephemeral=True)
            return

        await self.update_user_status(
            interaction.user.id,
            "premium",
            "add",
            expires_at,
            code=gift["code"],
            gifted_by=gift["user_id"],
            redeem_notice=True
        )

        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO premium_gift_logs (gift_id, action, actor_id, target_user_id, code) "
                "VALUES ($1,$2,$3,$4,$5)",
                gift["gift_id"], "redeemed",
                gift["user_id"],
                interaction.user.id,
                gift["code"]
            )

        await followup_approve(interaction,
            f"You have redeemed **Premium {gift['plan'].capitalize()}**.",
            ephemeral=True
        )

        await self.send_redeem_log(
            interaction.user,
            gift["plan"],
            gift["code"],
            gift["user_id"],
            expires_at
        )


async def setup(bot):
    await bot.add_cog(Premium(bot))
