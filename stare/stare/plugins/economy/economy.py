import io
import random
from typing import Optional

import discord
from discord.ext import commands

from stare.core.config import Config
from stare.core.tools.context import CustomContext as Context

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS economy (
                user_id BIGINT PRIMARY KEY,
                money BIGINT DEFAULT 0,
                bank BIGINT DEFAULT 0,
                bank_limit BIGINT DEFAULT 10000,
                last_daily TIMESTAMP WITH TIME ZONE,
                daily_streak INTEGER DEFAULT 0
            )
        """)

    async def _ensure_account(self, user_id: int):
        await self.bot.db_pool.execute(
            "INSERT INTO economy (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
            user_id,
        )

    @commands.group(name="economy", aliases=["eco"], invoke_without_command=True)
    async def economy(self, ctx: Context):
        """Economy command group."""
        await ctx.send_help(ctx.command)

    @economy.command(name="wallet", aliases=["bal", "balance"])
    async def economy_wallet(self, ctx: Context, *, user: Optional[discord.Member] = None):
        """View your wallet and bank balance."""
        target = user or ctx.author
        await self._ensure_account(target.id)

        row = await self.bot.db_pool.fetchrow(
            "SELECT money, bank FROM economy WHERE user_id=$1", target.id
        )

        money = row["money"] if row else 0
        bank = row["bank"] if row else 0

        embed = discord.Embed(
            title=f"{target.name}'s Wallet",
            color=Config.COLORS.DEFAULT,
        )
        embed.add_field(name="Wallet", value=f"> ${money:,}", inline=True)
        embed.add_field(name="Bank", value=f"> ${bank:,}", inline=True)
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @economy.command(name="deposit", aliases=["dep"])
    async def economy_deposit(self, ctx: Context, amount: str):
        """Deposit money into your bank."""
        await self._ensure_account(ctx.author.id)

        row = await self.bot.db_pool.fetchrow(
            "SELECT money, bank, bank_limit FROM economy WHERE user_id=$1", ctx.author.id
        )
        money = row["money"] or 0
        bank = row["bank"] or 0
        bank_limit = row["bank_limit"] or 0

        deposit_amount = money if amount.lower() == "all" else int(amount)

        if deposit_amount <= 0:
            return await ctx.warn("Amount must be greater than zero!")
        if deposit_amount > money:
            return await ctx.warn("You don't have that much in your wallet!")
        if bank + deposit_amount > bank_limit:
            return await ctx.warn(
                f"You can't do that because it would exceed your bank limit of **${bank_limit:,}**!"
            )

        await self.bot.db_pool.execute(
            "UPDATE economy SET money=money-$1, bank=bank+$1 WHERE user_id=$2",
            deposit_amount, ctx.author.id,
        )

        embed = discord.Embed(
            description=f"💰 {ctx.author.mention}: Deposited **${deposit_amount:,}** into your bank",
            color=Config.COLORS.DEFAULT,
        )
        await ctx.send(embed=embed)

    @economy.command(name="withdraw", aliases=["with"])
    async def economy_withdraw(self, ctx: Context, amount: str):
        """Withdraw money from your bank."""
        await self._ensure_account(ctx.author.id)

        bank = await self.bot.db_pool.fetchval(
            "SELECT bank FROM economy WHERE user_id=$1", ctx.author.id
        ) or 0

        withdraw_amount = bank if amount.lower() == "all" else int(amount)

        if withdraw_amount <= 0:
            return await ctx.warn("Amount must be greater than zero!")
        if withdraw_amount > bank:
            return await ctx.warn("You don't have that much in your bank!")

        await self.bot.db_pool.execute(
            "UPDATE economy SET money=money+$1, bank=bank-$1 WHERE user_id=$2",
            withdraw_amount, ctx.author.id,
        )

        embed = discord.Embed(
            description=f"💵 {ctx.author.mention}: Withdrew **${withdraw_amount:,}** from your bank",
            color=Config.COLORS.DEFAULT,
        )
        await ctx.send(embed=embed)

    @economy.command(name="give", aliases=["pay", "transfer"])
    async def economy_give(self, ctx: Context, user: discord.Member, amount: int):
        """Give money to another user."""
        if user.id == ctx.author.id:
            return await ctx.warn("You can't give money to yourself!")
        if amount <= 0:
            return await ctx.warn("Amount must be greater than zero!")

        await self._ensure_account(ctx.author.id)
        await self._ensure_account(user.id)

        money = await self.bot.db_pool.fetchval(
            "SELECT money FROM economy WHERE user_id=$1", ctx.author.id
        ) or 0

        if amount > money:
            return await ctx.warn("You don't have enough in your wallet!")

        await self.bot.db_pool.execute(
            "UPDATE economy SET money=money-$1 WHERE user_id=$2", amount, ctx.author.id
        )
        await self.bot.db_pool.execute(
            "UPDATE economy SET money=money+$1 WHERE user_id=$2", amount, user.id
        )

        embed = discord.Embed(
            description=f"💸 {ctx.author.mention}: Sent **${amount:,}** to {user.mention}",
            color=Config.COLORS.DEFAULT,
        )
        await ctx.send(embed=embed)

    @economy.command(name="rob")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def economy_rob(self, ctx: Context, user: discord.Member):
        """Attempt to rob another user's wallet."""
        if user.id == ctx.author.id:
            return await ctx.warn("You can't rob yourself!")

        await self._ensure_account(ctx.author.id)
        await self._ensure_account(user.id)

        target_money = await self.bot.db_pool.fetchval(
            "SELECT money FROM economy WHERE user_id=$1", user.id
        ) or 0

        if target_money < 100:
            return await ctx.warn(f"{user.mention} doesn't have enough money to rob!")

        success = random.random() < 0.45
        if success:
            stolen = random.randint(int(target_money * 0.05), int(target_money * 0.20))
            stolen = max(stolen, 1)
            await self.bot.db_pool.execute(
                "UPDATE economy SET money=money+$1 WHERE user_id=$2", stolen, ctx.author.id
            )
            await self.bot.db_pool.execute(
                "UPDATE economy SET money=money-$1 WHERE user_id=$2", stolen, user.id
            )
            embed = discord.Embed(
                description=f"🥷 {ctx.author.mention}: You robbed **${stolen:,}** from {user.mention}",
                color=Config.COLORS.DEFAULT,
            )
        else:
            fine = random.randint(100, 500)
            await self.bot.db_pool.execute(
                "UPDATE economy SET money=GREATEST(money-$1,0) WHERE user_id=$2", fine, ctx.author.id
            )
            embed = discord.Embed(
                description=f"🚔 {ctx.author.mention}: You got caught trying to rob {user.mention} and were fined **${fine:,}**",
                color=0xFF6464,
            )

        await ctx.send(embed=embed)

    @economy_rob.error
    async def economy_rob_error(self, ctx: Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.warn(f"You can rob again in **{error.retry_after:.0f}s**!")

    @economy.command(name="work")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def economy_work(self, ctx: Context):
        """Work a job to earn money."""
        await self._ensure_account(ctx.author.id)

        jobs = [
            ("joined /sixth", 100, 500),
            ("streamer", 50, 3000),
            ("nurse", 500, 1500),
            ("artist", 150, 1200),
            ("engineer", 800, 2500),
            ("pizza delivery driver", 200, 600),
            ("accountant", 600, 1800),
        ]
        job, min_pay, max_pay = random.choice(jobs)
        earned = random.randint(min_pay, max_pay)

        await self.bot.db_pool.execute(
            "UPDATE economy SET money=money+$1 WHERE user_id=$2", earned, ctx.author.id
        )

        embed = discord.Embed(
            description=f"💼 {ctx.author.mention}: You worked as a **{job}** and earned **${earned:,}**",
            color=Config.COLORS.DEFAULT,
        )
        await ctx.send(embed=embed)

    @economy_work.error
    async def economy_work_error(self, ctx: Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            retry = int(error.retry_after)
            hours, remainder = divmod(retry, 3600)
            minutes, seconds = divmod(remainder, 60)
            time_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"
            await ctx.warn(f"You can work again in **{time_str}**!")

    @economy.command(name="daily")
    async def economy_daily(self, ctx: Context):
        """Claim your daily reward."""
        from datetime import datetime, timedelta, timezone

        await self._ensure_account(ctx.author.id)

        row = await self.bot.db_pool.fetchrow(
            "SELECT last_daily, daily_streak FROM economy WHERE user_id=$1", ctx.author.id
        )
        now = datetime.now(timezone.utc)
        last_claim = row["last_daily"]
        streak = row["daily_streak"] or 0
        rewards = [1500, 3000, 5000, 10000, 20000, 35000, 50000]

        if last_claim:
            end = last_claim + timedelta(hours=24)
            if now < end:
                ts = int(end.timestamp())
                return await ctx.warn(f"You can claim your daily again <t:{ts}:R>!")

        streak = min(streak + 1, 7) if last_claim and now <= last_claim + timedelta(hours=48) else 1
        reward = rewards[streak - 1]

        await self.bot.db_pool.execute(
            "UPDATE economy SET money=money+$1, last_daily=$2, daily_streak=$3 WHERE user_id=$4",
            reward, now, streak, ctx.author.id,
        )

        embed = discord.Embed(
            description=f"🎉 {ctx.author.mention}: You claimed your daily reward!\n\n**Day {streak} Streak** — You earned **${reward:,}**",
            color=Config.COLORS.DEFAULT,
        )
        await ctx.send(embed=embed)

    @economy.command(name="leaderboard", aliases=["lb", "top"])
    async def economy_leaderboard(self, ctx: Context):
        """View the richest users."""
        rows = await self.bot.db_pool.fetch(
            "SELECT user_id, money+bank AS total FROM economy ORDER BY total DESC LIMIT 10"
        )

        if not rows:
            return await ctx.warn("I couldn't find any economy data yet!")

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for i, row in enumerate(rows, 1):
            user = self.bot.get_user(row["user_id"]) or f"Unknown ({row['user_id']})"
            medal = medals.get(i, f"`{i}.`")
            lines.append(f"{medal} **{user}** — ${row['total']:,}")

        embed = discord.Embed(
            title="Economy Leaderboard",
            description="\n".join(lines),
            color=Config.COLORS.DEFAULT,
        )
        await ctx.send(embed=embed)

    @economy.command(name="gamble", aliases=["bet"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def economy_gamble(self, ctx: Context, amount: str):
        """Gamble your money for a chance to double it."""
        await self._ensure_account(ctx.author.id)

        money = await self.bot.db_pool.fetchval(
            "SELECT money FROM economy WHERE user_id=$1", ctx.author.id
        ) or 0

        bet = money if amount.lower() == "all" else int(amount)

        if bet <= 0:
            return await ctx.warn("Bet must be greater than zero!")
        if bet > money:
            return await ctx.warn("You don't have that much in your wallet!")

        win = random.random() < 0.48
        if win:
            await self.bot.db_pool.execute(
                "UPDATE economy SET money=money+$1 WHERE user_id=$2", bet, ctx.author.id
            )
            embed = discord.Embed(
                description=f"🎰 {ctx.author.mention}: You won **${bet:,}**",
                color=0xA4EC7C,
            )
        else:
            await self.bot.db_pool.execute(
                "UPDATE economy SET money=money-$1 WHERE user_id=$2", bet, ctx.author.id
            )
            embed = discord.Embed(
                description=f"🎰 {ctx.author.mention}: You lost **${bet:,}**",
                color=0xFF6464,
            )

        await ctx.send(embed=embed)

    @economy_gamble.error
    async def economy_gamble_error(self, ctx: Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.warn(f"You can gamble again in **{error.retry_after:.1f}s**!")

async def setup(bot):
    await bot.add_cog(Economy(bot))
