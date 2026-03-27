from discord.ext.commands import Cog, command, is_owner
from discord import User, Guild

from heist.framework.discord import Context
from heist.framework.discord.checks import add_blacklist


class BotAdministrator(Cog):
    def __init__(self, bot):
        self.bot = bot

    @command()
    @is_owner()
    async def blacklist(self, ctx: Context, target: User | Guild, *, reason: str = "No reason provided"):
        """Blacklist a user or guild from using the bot"""
        try:
            if isinstance(target, User):
                await add_blacklist(self.bot, target.id, "user", reason, ctx.author.id)
                await ctx.embed(f"Blacklisted user **{target}** (`{target.id}`)", "approve")
            elif isinstance(target, Guild):
                await add_blacklist(self.bot, target.id, "guild", reason, ctx.author.id)
                await ctx.embed(f"Blacklisted guild **{target.name}** (`{target.id}`)", "approve")
            else:
                await ctx.embed(f"Invalid target type: {type(target)}", "deny")
        except Exception as e:
            await ctx.embed(f"Error: {e}", "deny")
        
    @command()
    @is_owner()
    async def unblacklist(self, ctx: Context, target: User | Guild):
        """Remove a user or guild from the blacklist"""
        from heist.framework.discord.checks import remove_blacklist
        
        if isinstance(target, User):
            success = await remove_blacklist(self.bot, target.id, "user")
            if success:
                await ctx.embed(f"Removed user **{target}** from blacklist", "approve")
            else:
                await ctx.embed(f"User **{target}** was not blacklisted", "warn")
        elif isinstance(target, Guild):
            success = await remove_blacklist(self.bot, target.id, "guild")
            if success:
                await ctx.embed(f"Removed guild **{target.name}** from blacklist", "approve")
            else:
                await ctx.embed(f"Guild **{target.name}** was not blacklisted", "warn")


async def setup(bot):
    await bot.add_cog(BotAdministrator(bot))
