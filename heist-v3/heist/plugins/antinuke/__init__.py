import discord
from discord.ext import commands
from heist.framework.discord import Context
from datetime import datetime
from typing import Dict, List
from .events import AntiNukeEvents

class AntiNukeModule:
    def __init__(self, module: str, punishment: str, threshold: int, toggled: bool):
        self.module = module
        self.punishment = punishment
        self.threshold = threshold
        self.toggled = toggled

    @classmethod
    async def from_database(cls, pool, guild_id: int, module: str):
        result = await pool.fetchrow(
            "SELECT * FROM antinuke_modules WHERE guild_id = $1 AND module = $2",
            guild_id, module
        )
        if not result:
            return None
        return cls(result['module'], result['punishment'], result['threshold'], result['toggled'])

    async def update(self, pool, guild_id: int):
        await pool.execute(
            "UPDATE antinuke_modules SET punishment = $1, threshold = $2, toggled = $3 WHERE guild_id = $4 AND module = $5",
            self.punishment, self.threshold, self.toggled, guild_id, self.module
        )

class AntiNukeUser:
    def __init__(self, module: str, user_id: int, last_action: datetime, amount: int):
        self.module = module
        self.user_id = user_id
        self.last_action = last_action
        self.amount = amount

async def has_admin(ctx: Context) -> bool:
    if ctx.author.id in ctx.bot.config.authentication.owner_ids or ctx.author.id == ctx.guild.owner.id:
        return True
    admin = await ctx.bot.pool.fetchrow(
        "SELECT * FROM antinuke_admins WHERE guild_id = $1 AND user_id = $2",
        ctx.guild.id, ctx.author.id
    )
    if not admin:
        await ctx.warn("You do not have **anti-nuke admin**")
        return False
    return True

async def is_enabled(ctx: Context) -> bool:
    module = await ctx.bot.pool.fetchrow(
        "SELECT * FROM ancfg WHERE guild_id = $1", ctx.guild.id
    )
    if not module:
        await ctx.warn("AntiNuke is not **enabled** in this server. Use `antinuke enable` to **enable** it.")
        return False
    return True

class AntiNuke(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.modules = ["Ban", "Kick", "Bot", "Roles", "Vanity", "Webhook", "Channels", "Permissions", "Massmention"]
        self.actions: Dict[int, List[AntiNukeUser]] = {}

    @commands.group(invoke_without_command=True, aliases=["an"])
    @commands.has_permissions(administrator=True)
    async def antinuke(self, ctx: Context):
        if not await has_admin(ctx):
            return
        await ctx.send_help(ctx.command)

    @antinuke.command(aliases=["config"])
    @commands.has_permissions(administrator=True)
    async def settings(self, ctx: Context):
        if not await has_admin(ctx) or not await is_enabled(ctx):
            return

        embed = discord.Embed(
            title=f"Anti-Nuke Settings - {ctx.guild.name}",
            color=ctx.config.colors.information
        )

        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)

        for name in self.modules:
            module = await AntiNukeModule.from_database(self.bot.pool, ctx.guild.id, name)
            status = ctx.config.emojis.context.approve if module and module.toggled else ctx.config.emojis.context.deny
            embed.add_field(
                name=f"{name}: {status}",
                value=f"Action: `{module.punishment if module else 'None'}`\nThreshold: `{module.threshold if module else 'None'}`",
                inline=True
            )

        await ctx.send(embed=embed)

    @antinuke.command(aliases=["wl"])
    @commands.has_permissions(administrator=True)
    async def whitelist(self, ctx: Context, user: discord.User):
        if not await has_admin(ctx) or not await is_enabled(ctx):
            return

        whitelist = await self.bot.pool.fetchrow(
            "SELECT * FROM antinuke_whitelist WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, user.id
        )
        
        if whitelist:
            await self.bot.pool.execute(
                "DELETE FROM antinuke_whitelist WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id, user.id
            )
            await ctx.approve(f"**{user.name}** has been **unwhitelisted** in this server.")
        else:
            await self.bot.pool.execute(
                "INSERT INTO antinuke_whitelist VALUES ($1, $2)",
                ctx.guild.id, user.id
            )
            await ctx.approve(f"**{user.name}** has been **whitelisted** in this server.")

    @antinuke.command()
    @commands.has_permissions(administrator=True)
    async def admin(self, ctx: Context, user: discord.User):
        if not await has_admin(ctx) or not await is_enabled(ctx):
            return

        admin = await self.bot.pool.fetchrow(
            "SELECT * FROM antinuke_admins WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, user.id
        )
        
        if admin:
            await self.bot.pool.execute(
                "DELETE FROM antinuke_admins WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id, user.id
            )
            await ctx.approve(f"**{user.name}** has been **removed** from the **Anti-Nuke Admin** list in this server.")
        else:
            await self.bot.pool.execute(
                "INSERT INTO antinuke_admins VALUES ($1, $2)",
                ctx.guild.id, user.id
            )
            await ctx.approve(f"**{user.name}** has been **added** to the **Anti-Nuke Admin** list in this server.")

    @antinuke.command()
    @commands.has_permissions(administrator=True)
    async def whitelisted(self, ctx: Context):
        if not await has_admin(ctx):
            return

        whitelisted = await self.bot.pool.fetch(
            "SELECT * FROM antinuke_whitelist WHERE guild_id = $1", ctx.guild.id
        )
        
        if not whitelisted:
            return await ctx.warn("No users are **whitelisted** in this server.")

        embed = discord.Embed(
            title=f"Anti-Nuke Whitelisted Members - {ctx.guild.name}",
            color=ctx.config.colors.information
        )

        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)

        embed.description = "\n".join([
            f"{ctx.guild.get_member(user['user_id']).name if ctx.guild.get_member(user['user_id']) else 'Unknown'} ({user['user_id']})"
            for user in whitelisted
        ])

        await ctx.send(embed=embed)

    @antinuke.command()
    @commands.has_permissions(administrator=True)
    async def admins(self, ctx: Context):
        if not await has_admin(ctx):
            return

        admins = await self.bot.pool.fetch(
            "SELECT * FROM antinuke_admins WHERE guild_id = $1", ctx.guild.id
        )
        
        if not admins:
            return await ctx.warn("No users are **Anti-Nuke Admins** in this server.")

        embed = discord.Embed(
            title=f"Anti-Nuke Admins - {ctx.guild.name}",
            color=ctx.config.colors.information
        )

        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)

        embed.description = "\n".join([
            f"{ctx.guild.get_member(user['user_id']).name if ctx.guild.get_member(user['user_id']) else 'Unknown'} ({user['user_id']})"
            for user in admins
        ])

        await ctx.send(embed=embed)

    @antinuke.command()
    @commands.has_permissions(administrator=True)
    async def enable(self, ctx: Context):
        if not await has_admin(ctx):
            return

        enabled = await self.bot.pool.fetchrow(
            "SELECT * FROM ancfg WHERE guild_id = $1", ctx.guild.id
        )
        
        if enabled:
            return await ctx.warn("AntiNuke is already **enabled** in this server.")

        await self.bot.pool.execute("INSERT INTO ancfg VALUES ($1)", ctx.guild.id)

        modules = await self.bot.pool.fetch(
            "SELECT * FROM antinuke_modules WHERE guild_id = $1", ctx.guild.id
        )

        if not modules:
            for name in self.modules:
                await self.bot.pool.execute(
                    "INSERT INTO antinuke_modules VALUES ($1, $2, $3, $4, $5)",
                    ctx.guild.id, name, "ban", 1, False
                )

        await ctx.approve("Anti-Nuke has been **enabled** in this server.")

    @antinuke.command()
    @commands.has_permissions(administrator=True)
    async def disable(self, ctx: Context):
        if not await has_admin(ctx) or not await is_enabled(ctx):
            return

        await self.bot.pool.execute("DELETE FROM ancfg WHERE guild_id = $1", ctx.guild.id)
        await ctx.approve("Anti-Nuke has been **disabled** in this server.")

    @antinuke.command()
    @commands.has_permissions(administrator=True)
    async def toggle(self, ctx: Context, module: str):
        if not await has_admin(ctx) or not await is_enabled(ctx):
            return

        if module.capitalize() not in self.modules:
            return await ctx.warn(f"The module `{module}` is not a valid **Anti-Nuke module**.")

        an_module = await AntiNukeModule.from_database(self.bot.pool, ctx.guild.id, module.capitalize())
        if not an_module:
            return await ctx.warn("Module not found.")
        
        an_module.toggled = not an_module.toggled
        await an_module.update(self.bot.pool, ctx.guild.id)

        await ctx.approve(f"Anti-Nuke module `{module}` has been **{'Enabled' if an_module.toggled else 'Disabled'}**.")

    @antinuke.command()
    @commands.has_permissions(administrator=True)
    async def threshold(self, ctx: Context, module: str, threshold: int):
        if not await has_admin(ctx) or not await is_enabled(ctx):
            return

        if module.capitalize() not in self.modules:
            return await ctx.warn(f"The module `{module}` is not a valid **Anti-Nuke module**.")

        an_module = await AntiNukeModule.from_database(self.bot.pool, ctx.guild.id, module.capitalize())
        if not an_module:
            return await ctx.warn("Module not found.")
        
        an_module.threshold = threshold
        await an_module.update(self.bot.pool, ctx.guild.id)

        await ctx.approve(f"Anti-Nuke module `{module}` threshold has been set to `{threshold}`.")

    @antinuke.command(aliases=["punishment"])
    @commands.has_permissions(administrator=True)
    async def action(self, ctx: Context, module: str, action: str):
        if not await has_admin(ctx) or not await is_enabled(ctx):
            return

        if module.capitalize() not in self.modules:
            return await ctx.warn(f"The module `{module}` is not a valid **Anti-Nuke module**.")
        
        if action.lower() not in ["ban", "warn", "kick", "strip"]:
            return await ctx.warn(f"The action `{action}` is not a valid action. Use `ban`, `warn`, `kick` or `strip`.")

        an_module = await AntiNukeModule.from_database(self.bot.pool, ctx.guild.id, module.capitalize())
        if not an_module:
            return await ctx.warn("Module not found.")
        
        an_module.punishment = action.lower()
        await an_module.update(self.bot.pool, ctx.guild.id)

        await ctx.approve(f"Anti-Nuke module `{module}` action has been set to `{action}`.")

async def setup(bot):
    await bot.add_cog(AntiNuke(bot))
    await bot.add_cog(AntiNukeEvents(bot))