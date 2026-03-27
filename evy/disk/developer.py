import discord
from discord.ext import commands


class Developer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _exec(self, q: str, *a):
        async with self.bot.db.acquire() as c:
            await c.execute(q, *a)

    async def _row(self, q: str, *a):
        async with self.bot.db.acquire() as c:
            return await c.fetchrow(q, *a)

    async def _ensure_user(self, uid: int, gid: int):
        await self._exec(
            "INSERT INTO economy(user_id,guild_id,wallet,bank,bank_max,inventory)"
            " VALUES($1,$2,0,0,5000,'{}') ON CONFLICT DO NOTHING",
            uid, gid
        )

    @commands.command(name="error", help="developer", usage="<error_id>")
    @commands.check(lambda ctx: ctx.author.id in ctx.bot.owner_ids)
    async def error_lookup(self, ctx: commands.Context, error_id: str = None):
        if not error_id:
            embed = discord.Embed(description="> **Provide an error id...**", color=self.bot.color)
            return await ctx.send(embed=embed)

        entry = (getattr(self.bot, "error_cache", {})).get(error_id)
        if not entry:
            embed = discord.Embed(
                description=f"> **No cached error found with id `{error_id}`...**",
                color=self.bot.color
            )
            return await ctx.send(embed=embed)

        pages  = [entry[i:i+1900] for i in range(0, len(entry), 1900)]
        bot_ref = self.bot

        class ErrorView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=120)
                self.page    = 0
                self.message = None
                self._sync()

            def _sync(self):
                self.prev_btn.disabled = self.page == 0
                self.next_btn.disabled = self.page == len(pages) - 1

            def _embed(self) -> discord.Embed:
                e = discord.Embed(
                    title=f"Error `{error_id}`",
                    description=f"```py\n{pages[self.page]}\n```",
                    color=bot_ref.color
                )
                e.set_footer(text=f"Page {self.page + 1} / {len(pages)}")
                return e

            @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:left:1265476224742850633>"), style=discord.ButtonStyle.blurple)
            async def prev_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("> **This isn't your menu...**", ephemeral=True)
                self.page -= 1
                self._sync()
                await interaction.response.edit_message(embed=self._embed(), view=self)

            @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:right:1265476229876678768>"), style=discord.ButtonStyle.blurple)
            async def next_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("> **This isn't your menu...**", ephemeral=True)
                self.page += 1
                self._sync()
                await interaction.response.edit_message(embed=self._embed(), view=self)

            @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:bin:1317214464231079989>"), style=discord.ButtonStyle.danger)
            async def delete_btn(self, interaction: discord.Interaction, btn: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("> **This isn't your menu...**", ephemeral=True)
                await interaction.message.delete()

            async def on_timeout(self):
                try:
                    for item in self.children:
                        item.disabled = True
                    await self.message.edit(view=self)
                except:
                    pass

        view         = ErrorView()
        view.message = await ctx.send(embed=view._embed(), view=view)

    @commands.group(name="eco", invoke_without_command=True, help="developer")
    @commands.check(lambda ctx: ctx.author.id in ctx.bot.owner_ids)
    async def eco(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            return await ctx.create_pages()

    @eco.command(name="add", usage="<user> <amount> [wallet|bank]")
    @commands.check(lambda ctx: ctx.author.id in ctx.bot.owner_ids)
    async def eco_add(self, ctx: commands.Context, user: discord.Member, amount: int, target: str = "wallet"):
        if amount <= 0:
            embed = discord.Embed(description="> **Amount must be greater than 0...**", color=self.bot.color)
            return await ctx.send(embed=embed)
        target = target.lower()
        if target not in ("wallet", "bank"):
            embed = discord.Embed(description="> **Target must be `wallet` or `bank`...**", color=self.bot.color)
            return await ctx.send(embed=embed)
        await self._ensure_user(user.id, ctx.guild.id)
        await self._exec(
            f"UPDATE economy SET {target}={target}+$1 WHERE user_id=$2 AND guild_id=$3",
            amount, user.id, ctx.guild.id
        )
        row = await self._row(
            "SELECT wallet, bank FROM economy WHERE user_id=$1 AND guild_id=$2",
            user.id, ctx.guild.id
        )
        embed = discord.Embed(
            description=(
                f"> Added **{amount:,} coins** to **{user.name}**'s {target}\n"
                f"> New {target} balance: **{row[target]:,} coins**"
            ),
            color=self.bot.color
        )
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
        embed.set_thumbnail(url=user.display_avatar.url)
        await ctx.send(embed=embed)

    @eco.command(name="remove", usage="<user> <amount> [wallet|bank]")
    @commands.check(lambda ctx: ctx.author.id in ctx.bot.owner_ids)
    async def eco_remove(self, ctx: commands.Context, user: discord.Member, amount: int, target: str = "wallet"):
        if amount <= 0:
            embed = discord.Embed(description="> **Amount must be greater than 0...**", color=self.bot.color)
            return await ctx.send(embed=embed)
        target = target.lower()
        if target not in ("wallet", "bank"):
            embed = discord.Embed(description="> **Target must be `wallet` or `bank`...**", color=self.bot.color)
            return await ctx.send(embed=embed)
        await self._ensure_user(user.id, ctx.guild.id)
        row = await self._row(
            "SELECT wallet, bank FROM economy WHERE user_id=$1 AND guild_id=$2",
            user.id, ctx.guild.id
        )
        current = row[target] if row else 0
        actual  = min(amount, current)
        await self._exec(
            f"UPDATE economy SET {target}={target}-$1 WHERE user_id=$2 AND guild_id=$3",
            actual, user.id, ctx.guild.id
        )
        row2 = await self._row(
            "SELECT wallet, bank FROM economy WHERE user_id=$1 AND guild_id=$2",
            user.id, ctx.guild.id
        )
        embed = discord.Embed(
            description=(
                f"> Removed **{actual:,} coins** from **{user.name}**'s {target}\n"
                f"> New {target} balance: **{row2[target]:,} coins**"
            ),
            color=self.bot.color
        )
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
        embed.set_thumbnail(url=user.display_avatar.url)
        await ctx.send(embed=embed)

    @eco.command(name="set", usage="<user> <amount> [wallet|bank]")
    @commands.check(lambda ctx: ctx.author.id in ctx.bot.owner_ids)
    async def eco_set(self, ctx: commands.Context, user: discord.Member, amount: int, target: str = "wallet"):
        if amount < 0:
            embed = discord.Embed(description="> **Amount can't be negative...**", color=self.bot.color)
            return await ctx.send(embed=embed)
        target = target.lower()
        if target not in ("wallet", "bank"):
            embed = discord.Embed(description="> **Target must be `wallet` or `bank`...**", color=self.bot.color)
            return await ctx.send(embed=embed)
        await self._ensure_user(user.id, ctx.guild.id)
        await self._exec(
            f"UPDATE economy SET {target}=$1 WHERE user_id=$2 AND guild_id=$3",
            amount, user.id, ctx.guild.id
        )
        embed = discord.Embed(
            description=f"> Set **{user.name}**'s {target} to **{amount:,} coins**",
            color=self.bot.color
        )
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
        embed.set_thumbnail(url=user.display_avatar.url)
        await ctx.send(embed=embed)

    @eco.command(name="reset", usage="<user>")
    @commands.check(lambda ctx: ctx.author.id in ctx.bot.owner_ids)
    async def eco_reset(self, ctx: commands.Context, user: discord.Member):
        await self._ensure_user(user.id, ctx.guild.id)
        await self._exec(
            "UPDATE economy SET wallet=0, bank=0, bank_max=5000, inventory='{}'"
            " WHERE user_id=$1 AND guild_id=$2",
            user.id, ctx.guild.id
        )
        await self._exec(
            "DELETE FROM economy_cooldowns WHERE user_id=$1 AND guild_id=$2",
            user.id, ctx.guild.id
        )
        embed = discord.Embed(
            description=(
                f"> Reset **{user.name}**'s economy\n"
                f"> Wallet, bank, inventory and cooldowns cleared..."
            ),
            color=self.bot.color
        )
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
        embed.set_thumbnail(url=user.display_avatar.url)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Developer(bot))