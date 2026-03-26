from discord.ext import commands
from .database import db
from .config import Config
import discord
import traceback
import random
import string

error_cache = {}

def generate_error_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

async def setup_events(bot):
    @bot.event
    async def on_ready():
        await db.connect()
        print(f"Logged in as {bot.user}")
        print(f"Bot ID: {bot.user.id}")
    
    @bot.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingPermissions):
            perms = ", ".join([f"`{perm}`" for perm in error.missing_permissions])
            await ctx.warn(f"You are missing required permission(s): {perms}")
        elif isinstance(error, commands.BotMissingPermissions):
            perms = ", ".join([f"`{perm}`" for perm in error.missing_permissions])
            await ctx.warn(f"I am missing required permission(s): {perms}")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.warn(f"Missing required argument: `{error.param.name}`")
        elif isinstance(error, commands.BadArgument):
            await ctx.warn("The argument you provided was invalid.")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.warn(f"This command is on cooldown. Try again in {error.retry_after:.2f}s")
        elif isinstance(error, commands.NotOwner):
            await ctx.warn("This command is only available to the bot owner")
        elif isinstance(error, commands.CheckFailure):
            return
        else:
            error_code = generate_error_code()
            error_cache[error_code] = {
                'error': error,
                'traceback': ''.join(traceback.format_exception(type(error), error, error.__traceback__)),
                'command': ctx.command.name if ctx.command else 'Unknown',
                'author': str(ctx.author),
                'guild': str(ctx.guild) if ctx.guild else 'DM',
                'channel': str(ctx.channel)
            }
            
            class SupportButton(discord.ui.Button):
                def __init__(self):
                    super().__init__(
                        label="Support Server",
                        style=discord.ButtonStyle.link,
                        url="https://discord.gg/mT8MhykGAH"
                    )
            
            view = discord.ui.View()
            view.add_item(SupportButton())
            
            embed = discord.Embed(
                description=f"An error occurred while running the **{ctx.command.name if ctx.command else 'command'}** command. Please report the attached code to a developer in the support server",
                color=Config.COLORS.WARNING
            )
            
            try:
                await ctx.reply(content=f"`{error_code}`", embed=embed, view=view)
            except:
                pass
            
            print(f"Error {error_code}: {error}")

