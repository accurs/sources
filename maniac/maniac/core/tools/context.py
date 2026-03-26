import discord
from discord.ext import commands
from ..config import Config

class CustomContext(commands.Context):
    async def approve(self, message: str, **kwargs):
        embed = discord.Embed(
            description=f"{Config.EMOJIS.SUCCESS} {self.author.mention}: {message}",
            color=Config.COLORS.SUCCESS
        )
        return await self.reply(embed=embed, mention_author=False, **kwargs)
    
    async def deny(self, message: str, **kwargs):
        embed = discord.Embed(
            description=f"{Config.EMOJIS.ERROR} {self.author.mention}: {message}",
            color=Config.COLORS.ERROR
        )
        return await self.reply(embed=embed, mention_author=False, **kwargs)
    
    async def warn(self, message: str, **kwargs):
        embed = discord.Embed(
            description=f"{Config.EMOJIS.WARNING} {self.author.mention}: {message}",
            color=Config.COLORS.WARNING
        )
        return await self.reply(embed=embed, mention_author=False, **kwargs)
    
    async def loading(self, message: str, **kwargs):
        embed = discord.Embed(
            description=f"{Config.EMOJIS.LOADING} {self.author.mention}: {message}",
            color=Config.COLORS.LOADING
        )
        return await self.reply(embed=embed, mention_author=False, **kwargs)
