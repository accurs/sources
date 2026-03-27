import discord
import asyncio
import aiohttp
import io
import re
import secrets
import importlib
import pkgutil
import sys
from io import BytesIO
from datetime import timedelta
import datetime
from typing import Optional, Union, List
from discord import app_commands, File, Embed, Attachment, User, Interaction
from discord.errors import Forbidden
from discord.ui import View, Button
from discord.ext import commands
from discord.ext.commands import Cog
from pathlib import Path
import pkgutil
import heist.plugins as heist_plugins
from heist.framework.discord.decorators import owner_only, check_owner, reset_cache
from heist.framework.discord.checks import is_blacklisted, get_blacklist_reason
from heist.framework.tools.separator import makeseparator
from heist.framework.discord.commands import CommandCache
from contextlib import suppress
from dotenv import load_dotenv
from os import getenv

load_dotenv()

SERVER_ID = int(getenv("SERVER_ID"))
ROLE_ID = int(getenv("ROLE_ID"))
CLOUDFLARE_KEY = getenv("CLOUDFLARE_API_KEY")
CLOUDFLARE_HEISTLOL_ID = getenv("CLOUDFLARE_HEISTLOL_ID")
CLOUDFLARE_CURSING_ID = getenv("CLOUDFLARE_CURSING_ID")

class ConfirmView(View):
    def __init__(self, ctx, callback):
        super().__init__(timeout=240)
        self.ctx = ctx
        self.callback_func = callback

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.user:
            return await interaction.response.send_message("You cannot use this.", ephemeral=True)
        await self.callback_func(True)
        self.disable_all_items()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.user:
            return await interaction.response.send_message("You cannot use this.", ephemeral=True)
        await self.callback_func(False)
        self.disable_all_items()
        await interaction.response.edit_message(view=self)

class Staff(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        await self.session.close()

    admin = app_commands.Group(
        name="o",
        description="Staff only commands",
        allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=False, private_channel=True),
        allowed_installs=app_commands.AppInstallationType(guild=True, user=True)
    )

    eco = app_commands.Group(
        name="eco",
        description="Economy admin controls",
        parent=admin
    )

    gifts = app_commands.Group(
        name="gifting",
        description="Premium gifts admin controls",
        parent=admin
    )

    async def confirm_action(self, interaction, description, func):
        color = await self.bot.get_color(interaction.user.id)
        embed = discord.Embed(description=description, color=color)
        async def callback(approved):
            if approved:
                await func()
                await interaction.followup.send("Action confirmed.", ephemeral=True)
            else:
                await interaction.followup.send("Action cancelled.", ephemeral=True)
        view = ConfirmView(interaction, callback)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def update_user_status(self, user_id, status_type, action, expires_at=None):
        uid_str = str(user_id)
        uid_int = int(user_id)

        if status_type == "premium":
            if action == "add":
                if expires_at is None:
                    await self.bot.redis.delete(f"premium_expiry:{uid_str}")

                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO donors (user_id, donor_status, subscription_type, expires_at)
                        VALUES ($1, 1, $2, $3)
                        ON CONFLICT (user_id)
                        DO UPDATE SET donor_status = 1,
                                    subscription_type = EXCLUDED.subscription_type,
                                    expires_at = EXCLUDED.expires_at,
                                    updated_at = NOW()
                        """,
                        uid_str,
                        "lifetime" if expires_at is None else "temporary",
                        expires_at
                    )

                await self.bot.redis.setex(f"donor:{uid_str}", 300, "True")

                if expires_at is not None:
                    ttl = max(1, int((expires_at - datetime.datetime.now(datetime.timezone.utc)).total_seconds()))
                    await self.bot.redis.setex(f"premium_expiry:{uid_str}", ttl, "1")

            elif action == "remove":
                async with self.bot.pool.acquire() as conn:
                    await conn.execute("DELETE FROM donors WHERE user_id = $1", uid_str)

                    await conn.execute(
                        """
                        INSERT INTO premium_gift_logs (gift_id, action, actor_id, target_user_id, code)
                        VALUES ($1, 'premium_reset', NULL, $2, NULL)
                        """,
                        f"reset_{uid_str}",
                        uid_int
                    )

                await self.bot.redis.setex(f"donor:{uid_str}", 300, "False")
                await self.bot.redis.delete(f"premium_expiry:{uid_str}")

        elif status_type == "famous":
            if action == "add":
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE user_data SET fame = TRUE WHERE user_id = $1 AND fame IS FALSE',
                        uid_str
                    )
                await self.bot.redis.setex(f"famous:{uid_str}", 300, "True")

            elif action == "remove":
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE user_data SET fame = FALSE WHERE user_id = $1 AND fame IS TRUE',
                        uid_str
                    )
                await self.bot.redis.setex(f"famous:{uid_str}", 300, "False")

    async def update_admin(self, user_id, action):
        uid = str(user_id)
        if action == "add":
            async with self.bot.pool.acquire() as conn:
                await conn.execute('INSERT INTO owners (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING', uid)
            await self.bot.redis.setex(f"owner:{uid}", 300, "True")
        elif action == "remove":
            async with self.bot.pool.acquire() as conn:
                await conn.execute('DELETE FROM owners WHERE user_id = $1', uid)
            await self.bot.redis.setex(f"owner:{uid}", 300, "False")

    @admin.command(name="blacklist", description="Manage blacklist for users or guilds")
    @owner_only()
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(action="add or remove", user="User to manage", guild_id="Guild ID to manage", reason="Reason for blacklist")
    @app_commands.choices(action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Remove", value="remove")
    ])
    async def blacklist(self, interaction: Interaction, action: app_commands.Choice[str], user: User = None, guild_id: str = None, reason: str = "Breaking [Heist's Terms of Service](<https://heist.lol/terms>)."):
        ctx = await self.bot.get_context(interaction)
        
        if not user and not guild_id:
            await ctx.warn("Provide either a user or guild id")
            return
        
        if user and guild_id:
            await ctx.warn("Provide only one: user OR guild id")
            return
        
        await interaction.response.defer(thinking=True)

        if action.value == "add":
            from heist.framework.discord.checks import add_blacklist
            try:
                if user:
                    await add_blacklist(self.bot, user.id, "user", reason, ctx.author.id)
                    embed = Embed(
                        title="Notice",
                        description=f"You have been blacklisted from using [**Heist**](<https://heist.lol>).\nReason: **{reason}**\n\nIf you think this decision is wrong, you may appeal [**here**](https://discord.gg/heistbot).",
                        color=await ctx.bot.get_color(user.id)
                    )
                    try:
                        await user.send(embed=embed.set_image(url="https://git.cursi.ng/separator.png").set_thumbnail(url="https://git.cursi.ng/heist.png?a").set_footer(text="heist.lol", icon_url="https://git.cursi.ng/heist.png?a"))
                    except Exception:
                        pass
                    await ctx.approve(f"Blacklisted user **{user}** (`{user.id}`)") 
                elif guild_id:
                    guild = self.bot.get_guild(int(guild_id))
                    await add_blacklist(self.bot, int(guild_id), "guild", reason, ctx.author.id)
                    await ctx.approve(f"Blacklisted guild **{guild.name if guild else guild_id}** (`{guild_id}`)")
            except Exception as e:
                await ctx.deny(f"Error: {e}")
        
        elif action.value == "remove":
            from heist.framework.discord.checks import remove_blacklist
            if user:
                success = await remove_blacklist(self.bot, user.id, "user")
                if success:
                    embed = Embed(
                        title="Notice",
                        description="You have been unblacklisted from using [**Heist**](<https://heist.lol>).",
                        color=await ctx.bot.get_color(user.id)
                    )
                    try:
                        await user.send(embed=embed.set_image(url="https://git.cursi.ng/separator.png").set_thumbnail(url="https://git.cursi.ng/heist.png?a").set_footer(text="heist.lol", icon_url="https://git.cursi.ng/heist.png?a"))
                    except Exception:
                        pass
                    await ctx.approve(f"Removed user **{user}** from blacklist")
                else:
                    await ctx.warn(f"User **{user}** was not blacklisted")
            elif guild_id:
                guild = self.bot.get_guild(int(guild_id))
                success = await remove_blacklist(self.bot, int(guild_id), "guild")
                if success:
                    await ctx.approve(f"Removed guild **{guild.name if guild else guild_id}** from blacklist")
                else:
                    await ctx.warn(f"Guild **{guild.name if guild else guild_id}** was not blacklisted")

    @admin.command(name="grant", description="Grant or remove a status from a user")
    @owner_only()
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(action="Add or remove", status="premium/famous/trusted", user="Target user", duration="Lifetime, 30s, 24h, 3d, 7d, 30d")
    @app_commands.choices(
        action=[app_commands.Choice(name="Add", value="add"), app_commands.Choice(name="Remove", value="remove")],
        status=[app_commands.Choice(name="Premium", value="premium"), app_commands.Choice(name="Famous", value="famous"), app_commands.Choice(name="Trusted", value="trusted")],
        duration=[
            app_commands.Choice(name="Lifetime", value="lifetime"),
            app_commands.Choice(name="30 Seconds", value="30s"),
            app_commands.Choice(name="24 Hours", value="24h"),
            app_commands.Choice(name="3 Days", value="3d"),
            app_commands.Choice(name="7 Days", value="7d"),
            app_commands.Choice(name="30 Days", value="30d")
        ]
    )
    async def grant(self, interaction: Interaction, action: app_commands.Choice[str], status: app_commands.Choice[str], user: User = None, duration: app_commands.Choice[str] = None):
        await interaction.response.defer(thinking=True)
        ctx = await self.bot.get_context(interaction)
        bot = ctx.bot
        user = user or interaction.user
        uid = str(user.id)
        action = action.value
        status = status.value
        duration = duration.value if duration else "lifetime"
        try:
            if action == "add":
                expires_at = None
                if status == "premium" and duration and duration != "lifetime":
                    if duration.endswith("s"):
                        expires_at = datetime.datetime.now(datetime.timezone.utc) + timedelta(seconds=int(duration[:-1]))
                    elif duration.endswith("h"):
                        expires_at = datetime.datetime.now(datetime.timezone.utc) + timedelta(hours=int(duration[:-1]))
                    elif duration.endswith("d"):
                        expires_at = datetime.datetime.now(datetime.timezone.utc) + timedelta(days=int(duration[:-1]))

                donor = await self.bot.pool.fetchrow(
                    "SELECT subscription_type FROM donors WHERE user_id=$1",
                    uid
                )

                if status == "premium" and duration == "lifetime":
                    if donor and donor["subscription_type"] == "temporary":
                        await self.update_user_status(uid, "premium", "remove")

                if status in ("premium", "famous"):
                    await self.update_user_status(uid, status, "add", expires_at)
                    if status == "premium":
                        tier_name = (
                            "Premium Lifetime" if duration == "lifetime"
                            else ("Premium Monthly" if duration == "30d"
                                else f"Premium Temporary ({duration})")
                        )
                        embed = Embed(
                            title=f"{bot.config.emojis.context.premium} Notice",
                            description=(
                                f"You have been given **{tier_name}** on Heist.\n"
                                "Thank you for being a member!\n\n"
                                "Make sure to join our [**Support server**](https://discord.gg/heistbot)."
                            ),
                            color=await ctx.bot.get_color(user.id)
                        )
                        embed.set_thumbnail(url="https://git.cursi.ng/heist.png?a")
                        embed.set_footer(text="heist.lol", icon_url="https://git.cursi.ng/heist.png?a")
                        embed.set_image(url="https://git.cursi.ng/separator.png")
                        guild = self.bot.get_guild(SERVER_ID)
                        if guild:
                            role = guild.get_role(ROLE_ID)
                            member = guild.get_member(int(uid))
                            if role and member:
                                with suppress(Exception):
                                    await member.add_roles(role, reason="Premium granted by staff")
                        try:
                            await user.send(embed=embed)
                        except Exception:
                            pass
                        await ctx.approve(f"{user} has been given premium status ({'Lifetime' if duration == 'lifetime' else duration}).")
                    elif status == "famous":
                        try:
                            await user.send("You have been granted <:famous:1311067416251596870> **`Famous`** on Heist.")
                        except Exception:
                            pass
                        await ctx.approve(f"{user} has been given famous status.")
                elif status == "trusted":
                    limited_key = f"user:{uid}:limited"
                    untrusted_key = f"user:{uid}:untrusted"
                    await self.bot.redis.delete(limited_key)
                    await self.bot.redis.delete(untrusted_key)
                    await ctx.approve(f"{user} is now trusted.")

            elif action == "remove":
                if status in ("premium", "famous"):
                    await self.update_user_status(uid, status, "remove")
                    if status == "premium":
                        embed = Embed(
                            title=f"{bot.config.emojis.context.premium} Notice",
                            description=(
                                "Your **Premium** status has been removed on Heist.\n\n"
                                "This was unexpected? Make a ticket [**here**](https://discord.gg/heistbot)."
                            ),
                            color=await ctx.bot.get_color(user.id)
                        )
                        embed.set_thumbnail(url="https://git.cursi.ng/heist.png?a")
                        embed.set_footer(text="heist.lol", icon_url="https://git.cursi.ng/heist.png?a")
                        embed.set_image(url="https://git.cursi.ng/separator.png")
                        guild = self.bot.get_guild(SERVER_ID)
                        if guild:
                            role = guild.get_role(ROLE_ID)
                            member = guild.get_member((int(uid)))
                            if role and member:
                                with suppress(Exception):
                                    await member.remove_roles(role, reason="Premium removed by staff")
                        try:
                            await user.send(embed=embed)
                        except Exception:
                            pass
                        await ctx.approve(f"{user} no longer has premium status.")
                    elif status == "famous":
                        try:
                            await user.send("Your <:famous:1311067416251596870> **`Famous`** has been removed on Heist.")
                        except Exception:
                            pass
                        await ctx.approve(f"{user} no longer has famous status.")
                elif status == "trusted":
                    limited_key = f"user:{uid}:limited"
                    untrusted_key = f"user:{uid}:untrusted"
                    await self.bot.redis.setex(limited_key, 7 * 24 * 60 * 60, "")
                    await self.bot.redis.setex(untrusted_key, 60 * 24 * 60 * 60, "")
                    await ctx.approve(f"{user} is no longer trusted.")
            else:
                await ctx.warn("Invalid action.")
        except Exception as e:
            await ctx.warn(f"{e}")

    @admin.command(name="dm", description="DM a user")
    @owner_only()
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=False, dms=True, private_channels=False)
    @app_commands.describe(user="Target user", message="Message to send", file="Optional file")
    async def dm(self, interaction: Interaction, user: User, message: str, file: Attachment = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        ctx = await self.bot.get_context(interaction)
        try:
            if file:
                async with aiohttp.ClientSession() as s:
                    async with s.get(file.url) as resp:
                        if resp.status != 200:
                            await ctx.warn("Failed to download file.")
                            return
                        data = await resp.read()
                buffer = io.BytesIO(data)
                buffer.seek(0)
                await user.send(file=File(buffer, filename=file.filename))
                await ctx.approve("File sent.")
            else:
                await user.send(f"{message}\n-# This message was sent by {interaction.user.name} (Heist Team)")
                await ctx.approve("Message sent.")
        except Forbidden:
            await ctx.deny("I cannot send messages to this user. They may have DMs disabled or blocked the bot.")
        except Exception as e:
            await ctx.warn(f"Failed to send message.\n> {e}")

    async def domain_autocomplete(self, ctx: commands.Context, current: str) -> list[app_commands.Choice[str]]:
        domains = ["heist.lol", "cursi.ng"]
        return [
            app_commands.Choice(name=domain, value=domain)
            for domain in domains if current.lower() in domain.lower()
        ]

    @commands.hybrid_command()
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=False, dms=True, private_channels=False)
    @app_commands.autocomplete(domain=domain_autocomplete)
    async def connect(self, ctx: commands.Context, domain: str, verification: str):
        allowed_domains = {
            "heist.lol": CLOUDFLARE_HEISTLOL_ID,
            "cursi.ng": CLOUDFLARE_CURSING_ID
        }
        
        if domain not in allowed_domains:
            await ctx.warn(f"**{domain}** is not a supported domain.")
            return
        
        zone_id = allowed_domains[domain]
        gyat = str(ctx.author.id)
        await ctx.typing()
        
        async with self.bot.pool.acquire() as conn:
            result = await conn.fetchrow("SELECT allowed, verification_key FROM domain_whitelist WHERE user_id = $1", gyat)
            if not result or not result["allowed"]:
                await ctx.warn(f"You don't have permission to connect: **{domain}**")
                return

        loop = asyncio.get_event_loop()
        try:
            is_valid = await loop.run_in_executor(
                None, 
                lambda: re.match(r"^dh=[a-zA-Z0-9]+$", verification) is not None
            )
            if not is_valid:
                connectguide = await CommandCache.get_mention(self.bot, "connectguide")
                await ctx.warn(f"The verification code you have entered is invalid, please use {connectguide}.")
                return
        except Exception as e:
            await ctx.warn(f"Error validating verification code: {str(e)}")
            return

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {CLOUDFLARE_KEY}",
                "Content-Type": "application/json"
            }

            async with self.bot.pool.acquire() as conn:
                old_verification_key = await conn.fetchval("SELECT verification_key FROM domain_whitelist WHERE user_id = $1", gyat)

            if old_verification_key:
                async with session.get(
                    f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records?type=TXT&name=_discord.{domain}&content={old_verification_key}",
                    headers=headers
                ) as check_response:
                    check_result = await check_response.json()
                    if check_response.status == 200 and check_result["result"]:
                        record_id = check_result["result"][0]["id"]
                        async with session.delete(
                            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}",
                            headers=headers
                        ) as delete_response:
                            if delete_response.status != 200:
                                await ctx.warn(f"Failed to clean up old TXT record for **{domain}**.")
                                return

            data = {
                "type": "TXT",
                "name": f"_discord.{domain}",
                "content": verification,
                "ttl": 120
            }
            async with session.post(
                f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
                headers=headers,
                json=data
            ) as response:
                color = await self.bot.get_color(ctx.author.id)
                if response.status == 200:
                    async with self.bot.pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE domain_whitelist SET connected_domain = $1, verification_key = $2 WHERE user_id = $3",
                            domain, verification, gyat
                        )
                    await ctx.approve(f"successfully connected **{domain}**!\n**Please allow __2 minutes__ before attempting to link it.**")
                else:
                    await ctx.warn(f"Failed to verify **{domain}**. Please try again.")

    @commands.hybrid_command()
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=False, dms=True, private_channels=False)
    async def connectguide(self, ctx: commands.Context):
        connect = await CommandCache.get_mention(self.bot, "connect")
        await ctx.send("settings -> connections -> add domain -> **heist.lol** -> copy **content** value\n\n"
                      f"use {connect} (domain: heist.lol/cursi.ng), paste content's value in the **verification** parameter.")

    @commands.hybrid_command(name="allowconnect", description="Allow or disallow a user from connecting domains", aliases=["conn"])
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=False, dms=True, private_channels=False)
    @app_commands.describe(user="The user to allow/disallow")
    @owner_only()
    async def allowconnect(self, ctx: commands.Context, user: discord.User):
        await ctx.typing()
        gyat = str(user.id)
        async with self.bot.pool.acquire() as conn:
            result = await conn.fetchrow("SELECT allowed, connected_domain FROM domain_whitelist WHERE user_id = $1", gyat)
            if result and result["allowed"]:
                await conn.execute(
                    "UPDATE domain_whitelist SET allowed = FALSE, connected_domain = NULL WHERE user_id = $1",
                    gyat
                )
                await ctx.approve(f"{user.mention} has been disallowed from connecting domains.")
            else:
                await conn.execute(
                    "INSERT INTO domain_whitelist (user_id, allowed) VALUES ($1, TRUE) ON CONFLICT (user_id) DO UPDATE SET allowed = TRUE",
                    gyat
                )
                await ctx.approve(f"{user.mention} has been allowed to connect domains.")

    @eco.command(name="resetall", description="Reset all balances for a user")
    @app_commands.describe(user="Target user")
    @owner_only()
    async def resetall(self, interaction: discord.Interaction, user: discord.User):
        async def action():
            async with self.bot.pool.acquire() as conn:
                await conn.execute("UPDATE economy SET money=500, bank=1000, bank_limit=5000 WHERE user_id=$1", user.id)
        await self.confirm_action(interaction, f"Reset all balances for {user.mention}?", action)

    @eco.command(name="resetbank", description="Reset bank balance for a user")
    @app_commands.describe(user="Target user")
    @owner_only()
    async def resetbank(self, interaction: discord.Interaction, user: discord.User):
        async def action():
            async with self.bot.pool.acquire() as conn:
                await conn.execute("UPDATE economy SET bank=0 WHERE user_id=$1", user.id)
        await self.confirm_action(interaction, f"Reset bank balance for {user.mention}?", action)

    @eco.command(name="resetwallet", description="Reset wallet balance for a user")
    @app_commands.describe(user="Target user")
    @owner_only()
    async def resetwallet(self, interaction: discord.Interaction, user: discord.User):
        async def action():
            async with self.bot.pool.acquire() as conn:
                await conn.execute("UPDATE economy SET money=0 WHERE user_id=$1", user.id)
        await self.confirm_action(interaction, f"Reset wallet balance for {user.mention}?", action)

    @eco.command(name="setbank", description="Set bank balance for a user")
    @app_commands.describe(user="Target user", amount="Amount to set")
    @owner_only()
    async def setbank(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async def action():
            async with self.bot.pool.acquire() as conn:
                await conn.execute("UPDATE economy SET bank=$1 WHERE user_id=$2", amount, user.id)
        await self.confirm_action(interaction, f"Set bank balance for {user.mention} to **${amount:,}**?", action)

    @eco.command(name="setwallet", description="Set wallet balance for a user")
    @app_commands.describe(user="Target user", amount="Amount to set")
    @owner_only()
    async def setwallet(self, interaction: discord.Interaction, user: discord.User, amount: int):
        async def action():
            async with self.bot.pool.acquire() as conn:
                await conn.execute("UPDATE economy SET money=$1 WHERE user_id=$2", amount, user.id)
        await self.confirm_action(interaction, f"Set wallet balance for {user.mention} to **${amount:,}**?", action)

    @gifts.command(name="view", description="View a user's gift inventory")
    @owner_only()
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(user="Target user")
    async def gifts_view(self, interaction: Interaction, user: User):
        async def build(page_index: int = 0, flt: str = "none"):
            async with self.bot.pool.acquire() as conn:
                if flt == "active":
                    rows = await conn.fetch(
                        "SELECT * FROM premium_gifts WHERE user_id=$1 AND status IN ('active','code_generated') ORDER BY created_at DESC",
                        user.id
                    )
                elif flt == "code":
                    rows = await conn.fetch(
                        "SELECT * FROM premium_gifts WHERE user_id=$1 AND status='code_generated' ORDER BY created_at DESC",
                        user.id
                    )
                elif flt == "redeemed":
                    rows = await conn.fetch(
                        "SELECT * FROM premium_gifts WHERE user_id=$1 AND status='redeemed' ORDER BY redeemed_at DESC",
                        user.id
                    )
                elif flt == "revoked":
                    rows = await conn.fetch(
                        "SELECT * FROM premium_gifts WHERE user_id=$1 AND status='revoked' ORDER BY revoked_at DESC",
                        user.id
                    )
                else:
                    rows = await conn.fetch(
                        "SELECT * FROM premium_gifts WHERE user_id=$1 ORDER BY created_at DESC",
                        user.id
                    )
            color = await self.bot.get_color(interaction.user.id)
            if not rows:
                return [], color, 0
            lines = []
            for r in rows:
                tag = {
                    "active": "",
                    "code_generated": "(code)",
                    "redeemed": "(redeemed)",
                    "revoked": "(revoked)"
                }.get(r["status"], "")
                lines.append(f"**{r['plan'].capitalize()}** • **`{r['gift_id']}`** {tag}")
            pages = [lines[i:i + 10] for i in range(0, len(lines), 10)]
            embeds = []
            for i, group in enumerate(pages, 1):
                e = Embed(
                    title=f"{user.name}'s Heist Gifts",
                    description="\n".join(group),
                    color=color
                )
                e.set_thumbnail(url=user.display_avatar.url)
                e.set_footer(text=f"Page {i}/{len(pages)} • {len(lines)} gifts")
                embeds.append(e)
            return embeds, color, len(pages)

        current_filter = "none"
        embeds, color, _ = await build(0, current_filter)
        if not embeds:
            await interaction.response.warn(
                embed=Embed(description=f"{user.name} has no gifts.", color=color),
                ephemeral=True
            )
            return

        select = discord.ui.Select(
            placeholder="Filter..",
            options=[
                discord.SelectOption(label="No filters", value="none", default=True),
                discord.SelectOption(label="Active only", value="active"),
                discord.SelectOption(label="Codes only", value="code"),
                discord.SelectOption(label="Redeemed only", value="redeemed"),
                discord.SelectOption(label="Revoked only", value="revoked"),
            ]
        )

        async def select_callback(inter):
            nonlocal current_filter, paginator
            if inter.user.id != interaction.user.id:
                await inter.response.warn("This is not your menu.", ephemeral=True)
                return
            current_filter = select.values[0]
            for opt in select.options:
                opt.default = (opt.value == current_filter)
            new_embeds, _, total_pages = await build(
                paginator.index if paginator.index is not None else 0,
                current_filter
            )
            if not new_embeds:
                await inter.response.edit_message(
                    embed=Embed(description="No gifts match this filter.", color=color),
                    view=paginator
                )
                return
            paginator.pages = new_embeds
            paginator.index = min(paginator.index, total_pages - 1)
            page = paginator.pages[paginator.index]
            await inter.response.edit_message(embed=page, view=paginator)

        select.callback = select_callback
        ctx = await commands.Context.from_interaction(interaction)
        from heist.framework.pagination import Paginator

        async def on_page_switch(p):
            new_embeds, _, total_pages = await build(p.index, current_filter)
            p.pages = new_embeds
            p.index = min(p.index, total_pages - 1)
            page = p.pages[p.index]
            await p.message.edit(embed=page, view=p)

        paginator = Paginator(
            ctx,
            embeds,
            embed=True,
            hide_nav=False,
            hide_footer=True,
            message=None,
            on_page_switch=on_page_switch
        )

        paginator.add_persistent_item(select)
        await interaction.response.send_message(
            embed=embeds[0],
            view=paginator,
            ephemeral=True
        )
        paginator.message = await interaction.original_response()
        paginator.ctx = ctx

    @gifts.command(name="generate", description="Add a Premium gift to a user's inventory")
    @owner_only()
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(user="Target user to receive the gift", plan="Select a gift plan")
    @app_commands.choices(
        plan=[
            app_commands.Choice(name="Lifetime", value="lifetime"),
            app_commands.Choice(name="Monthly", value="monthly")
        ]
    )
    async def gifts_generate(self, interaction: Interaction, user: User, plan: app_commands.Choice[str]):
        gid = ''.join(secrets.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(12))
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO premium_gifts (gift_id, user_id, created_by, plan, status, code) VALUES ($1,$2,$3,$4,$5,$6)",
                gid, user.id, interaction.user.id, plan.value, 'active', None
            )
            await conn.execute(
                "INSERT INTO premium_gift_logs (gift_id, action, actor_id, target_user_id, code) VALUES ($1,$2,$3,$4,$5)",
                gid, "staff_generate", interaction.user.id, user.id, None
            )
        await interaction.response.approve(
            f"Added **Premium {plan.value.capitalize()}** gift (`{gid}`) to {user.mention}.",
            ephemeral=True
        )

    @gifts.command(name="revoke", description="Revoke a gift code by gift ID or code")
    @owner_only()
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(identifier="Gift ID to revoke")
    async def gifts_revoke(self, interaction: Interaction, identifier: str):
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM premium_gifts WHERE gift_id=$1 OR code=$1", identifier
            )
            if not row:
                await interaction.response.warn("No gift found for that identifier.", ephemeral=True)
                return

            if row["status"] == "redeemed":
                await interaction.response.warn(
                    "This gift has already been redeemed and cannot be revoked.",
                    ephemeral=True
                )
                return

            await conn.execute("UPDATE premium_gifts SET code=NULL, status='revoked', revoked_at=NOW() WHERE gift_id=$1", row["gift_id"])
            await conn.execute(
                "INSERT INTO premium_gift_logs (gift_id, action, actor_id, target_user_id, code) VALUES ($1,$2,$3,$4,$5)",
                row["gift_id"], "staff_revoke", interaction.user.id, row["user_id"], row["code"]
            )

        emoji = self.bot.config.emojis.context.premium
        color = await self.bot.get_color(interaction.user.id)
        embed = discord.Embed(
            title=f"{emoji} Gift Revoked",
            description=(
                f"**Identifier:** `{row['gift_id']}`\n"
                f"**Gift Code:** `{row['code'] or 'None'}`\n"
                f"**Owner:** <@{row['user_id']}>"
            ),
            color=color
        )
        embed.set_thumbnail(url="https://git.cursi.ng/heist.png?a")
        embed.set_footer(text="heist.lol", icon_url="https://git.cursi.ng/heist.png?a")
        embed.set_image(url="https://git.cursi.ng/separator.png")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @gifts.command(name="track", description="Track a Heist Premium gift")
    @owner_only()
    @app_commands.allowed_installs(guilds=False, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(identifier="Gift code or gift ID to track")
    async def track(self, interaction: discord.Interaction, identifier: str):
        await interaction.response.defer(ephemeral=True)

        async with self.bot.pool.acquire() as conn:
            gift = await conn.fetchrow("SELECT * FROM premium_gifts WHERE gift_id=$1 OR code=$1", identifier)
            if not gift:
                log = await conn.fetchrow(
                    "SELECT * FROM premium_gift_logs WHERE gift_id=$1 OR code=$1 ORDER BY created_at DESC LIMIT 1",
                    identifier
                )
                if not log:
                    await interaction.followup.send("No data for that gift.", ephemeral=True)
                    return

                plan = await conn.fetchval(
                    "SELECT plan FROM premium_gifts WHERE gift_id=$1",
                    log["gift_id"]
                ) or "unknown"

                gift = {
                    "gift_id": log["gift_id"],
                    "plan": plan,
                    "status": log["action"],
                    "user_id": log["target_user_id"],
                    "created_by": log["actor_id"],
                    "created_at": log["created_at"],
                    "code": log["code"]
                }
            else:
                log = await conn.fetchrow(
                    "SELECT * FROM premium_gift_logs WHERE gift_id=$1 ORDER BY created_at DESC LIMIT 1",
                    gift["gift_id"]
                )

        color = await self.bot.get_color(interaction.user.id)
        embed = discord.Embed(title=f"Gift {gift['gift_id']}", color=color)

        embed.add_field(name="Plan", value=gift["plan"], inline=True)
        embed.add_field(name="Status", value=gift["status"], inline=True)
        embed.add_field(name="Created By", value=f"<@{gift['created_by']}>" if gift["created_by"] else "Unknown", inline=True)
        embed.add_field(name="Assigned To", value=f"<@{gift['user_id']}>" if gift["user_id"] else "Unclaimed", inline=True)
        embed.add_field(name="Code", value=f"`{gift['code']}`" if gift["code"] else "N/A", inline=True)
        embed.add_field(name="Created At", value=f"<t:{int(gift['created_at'].timestamp())}:F>", inline=False)

        if log:
            embed.add_field(name="Last Action", value=log["action"], inline=False)

        sepbyte = await makeseparator(self.bot, interaction.user.id)
        sep = discord.File(io.BytesIO(sepbyte), filename="separator.png")
        embed.set_image(url="attachment://separator.png")

        await interaction.followup.send(embed=embed, ephemeral=True, file=sep)

    @admin.command(name="reload", description="Reload any Heist module")
    @app_commands.describe(target="Module or cog to reload")
    @app_commands.allowed_installs(guilds=True)
    @app_commands.allowed_contexts(guilds=True)
    @owner_only()
    async def reloadstuff(self, interaction: discord.Interaction, target: str):
        await interaction.response.defer(ephemeral=True)

        if target in self.bot.extensions:
            try:
                self.bot.reload_extension(target)
                return await interaction.followup.send(f"Reloaded extension `{target}`", ephemeral=True)
            except Exception as e:
                return await interaction.followup.send(f"Failed to reload `{target}`\n```\n{e}\n```", ephemeral=True)

        try:
            if target in sys.modules:
                importlib.reload(sys.modules[target])
            else:
                __import__(target)
            return await interaction.followup.send(f"🔁 Reloaded module `{target}`", ephemeral=True)
        except Exception as e:
            return await interaction.followup.send(f"❌ Failed to reload module `{target}`\n```\n{e}\n```", ephemeral=True)

    @reloadstuff.autocomplete("target")
    async def autocomplete_target(self, interaction: discord.Interaction, current: str):
        if not await check_owner(self.bot, interaction.user.id):
            return []

        modules = [
            m.name
            for m in pkgutil.walk_packages(heist_plugins.__path__, prefix="heist.plugins.")
        ]

        cur = current.lower()
        matches = [m for m in modules if cur in m.lower()][:25]

        return [
            app_commands.Choice(name=m, value=m)
            for m in matches
        ]

async def setup(bot):
    await bot.add_cog(Staff(bot))
        