import discord
from discord.ext import commands
from stare.core.config import Config


class CustomContext(commands.Context):
    """Custom context with utility methods"""
    
    async def approve(self, message: str, **kwargs):
        """Send a success embed"""
        embed = discord.Embed(
            description=f"{Config.EMOJIS.SUCCESS} {self.author.mention}: {message}",
            color=Config.COLORS.DEFAULT
        )
        return await self.reply(embed=embed, mention_author=False, **kwargs)
    
    async def deny(self, message: str, **kwargs):
        """Send an error embed"""
        embed = discord.Embed(
            description=f"{Config.EMOJIS.ERROR} {self.author.mention}: {message}",
            color=Config.COLORS.DEFAULT
        )
        return await self.reply(embed=embed, mention_author=False, **kwargs)
    
    async def warn(self, message: str, **kwargs):
        """Send a warning embed"""
        embed = discord.Embed(
            description=f"{Config.EMOJIS.WARNING} {self.author.mention}: {message}",
            color=Config.COLORS.DEFAULT
        )
        return await self.reply(embed=embed, mention_author=False, **kwargs)
    
    async def loading(self, message: str, **kwargs):
        """Send a loading embed"""
        embed = discord.Embed(
            description=f"{Config.EMOJIS.LOADING} {self.author.mention}: {message}",
            color=Config.COLORS.DEFAULT
        )
        return await self.reply(embed=embed, mention_author=False, **kwargs)
