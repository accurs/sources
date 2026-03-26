import discord
from discord.ext import commands
from maniac.core.config import Config
from maniac.core.command_example import example

class Developer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command()
    @example(",trace ABC123")
    @commands.is_owner()
    async def trace(self, ctx, error_code: str = None):
        if not error_code:
            return await ctx.warn("You need to provide an **error code**")
        
        try:
            from maniac.core.events import error_cache
        except ImportError:
            return await ctx.deny("Error cache system is not available")
        
        error_code = error_code.upper().strip('`')
        
        if error_code not in error_cache:
            return await ctx.deny(f"Error code `{error_code}` not found")
        
        error_data = error_cache[error_code]
        
        embed = discord.Embed(
            title=f"Error Trace: {error_code}",
            color=Config.COLORS.ERROR
        )
        
        embed.add_field(
            name="Command",
            value=f"`{error_data['command']}`",
            inline=True
        )
        
        embed.add_field(
            name="Author",
            value=error_data['author'],
            inline=True
        )
        
        embed.add_field(
            name="Guild",
            value=error_data['guild'],
            inline=True
        )
        
        embed.add_field(
            name="Channel",
            value=error_data['channel'],
            inline=True
        )
        
        embed.add_field(
            name="Error Type",
            value=f"`{type(error_data['error']).__name__}`",
            inline=True
        )
        
        error_msg = str(error_data['error'])
        if len(error_msg) > 100:
            error_msg = error_msg[:100] + "..."
        
        embed.add_field(
            name="Error Message",
            value=f"```{error_msg}```",
            inline=False
        )
        
        traceback_text = error_data['traceback']
        
        if len(traceback_text) > 1990:
            traceback_text = "..." + traceback_text[-1987:]
        
        await ctx.reply(embed=embed)
        
        await ctx.send(f"```py\n{traceback_text}\n```")

async def setup(bot):
    await bot.add_cog(Developer(bot))
