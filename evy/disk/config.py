import asyncio
import discord, aiohttp, datetime, time

from discord.ext import commands
from discord.ext.commands import command, group, Cog
from typing import Union

class Config(Cog):
    def __init__(self, bot):
        self.bot = bot

    @group(name="emoji")
    async def emoji(self, ctx):
        if ctx.invoked_subcommand is None:
            return await ctx.create_pages()

    @emoji.command(description="add an emoji to your server", help="emoji", usage="[emoji] <name>")
    @commands.has_permissions(manage_emojis=True)
    async def addemoji(self, ctx: commands.Context, emoji: Union[discord.Emoji, discord.PartialEmoji], *, name: str=None):
     if not name: name = emoji.name
     try:
       emoji = await ctx.guild.create_custom_emoji(image= await emoji.read(), name=name)
       return await ctx.success(f"added {emoji} as `{name}`")
     except discord.HTTPException as e: await ctx.warning(f"Unable to add emoji - {e}")
        
    @emoji.command(description="add multiple emojis", help="emoji", usage="[emojis]", aliases=["am"], brief="manage emojis")
    @commands.has_permissions(manage_emojis=True)
    async def addmultiple(self, ctx: commands.Context, *emoji: Union[discord.Emoji, discord.PartialEmoji]): 
     if len(emoji) == 0: return await ctx.warning("Please provide the emojis you want to add")       
     emojis = []
     await ctx.channel.typing()
     for emo in emoji:
      try:
        emoj = await ctx.guild.create_custom_emoji(image=await emo.read(), name=emo.name)
        emojis.append(f"{emoj}")
        await asyncio.sleep(.5)
      except discord.HTTPException as e: return await ctx.warning(f"Unable to add the emoji -> {e}")

     embed = discord.Embed(color=self.bot.color, title=f"added {len(emoji)} emojis") 
     embed.description = "".join(map(str, emojis))    
     return await ctx.reply(embed=embed)

    
    @commands.group(aliases=["guildedit", "set"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def gedit(self, ctx):
       return await ctx.create_pages()
    
    @gedit.command(name="banner", description="change the server banner", usage="[image/link]", help="config")
    @commands.has_permissions(manage_guild=True)
    async def ge_banner(self, ctx: commands.Context, url: str=None):

      if len(ctx.message.attachments) > 0:
            data = await ctx.message.attachments[0].read()
        
      elif url is not None:
            if url.startswith("<") and url.endswith(">"):
                url = url[1:-1]

            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(url) as r:
                        data = await r.read()
                except aiohttp.InvalidURL:
                    return await ctx.warning('That url is **invalid**.')
                except aiohttp.ClientError:
                    return await ctx.warning('Something went wrong when trying to get the image.')
      else:
            await ctx.guild.edit(banner=None)
            await ctx.success('I have **cleared** the server banner.')
            return
      try:
            async with ctx.typing():
                await ctx.guild.edit(banner=data, reason=f'server banner updated by {ctx.author}')
      except ValueError:
            await ctx.warning('JPG/PNG format only.')
      else:
            await ctx.success(f'I have **updated** the server banner to [**image**]({url}).')
    
    @gedit.command(name="icon", description="change the server icon", usage="[image/link]", help="config")
    @commands.has_permissions(manage_guild=True)
    async def ge_icon(self, ctx, url: str=None):
        
        if len(ctx.message.attachments) > 0:
            data = await ctx.message.attachments[0].read()
        elif url is not None:
            if url.startswith("<") and url.endswith(">"):
                url = url[1:-1]

            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(url) as r:
                        data = await r.read()
                except aiohttp.InvalidURL:
                    return await ctx.warning('That link is invalid.')
                except aiohttp.ClientError:
                    return await ctx.warning('Something went wrong when trying to get the image.')
        else:
            await ctx.guild.edit(icon=None, reason=f'server icon updated by {ctx.author}')
            await ctx.success('I have **cleared** the server icon.')
            return

        try:
            async with ctx.typing():
                await ctx.guild.edit(icon=data, reason=f'server icon updated by {ctx.author}')
        except ValueError:
            await ctx.warning('JPG/PNG format only.')
        else:
            await ctx.success(f'I have **updated** the server icon to [**image**]({url}).')


    @gedit.command(name="splash", description="change the server splash", usage="[image/link]", help="config")
    @commands.has_permissions(manage_guild=True)
    async def ge_splash(self, ctx, url: str=None):
        
        if len(ctx.message.attachments) > 0:
            data = await ctx.message.attachments[0].read()
        elif url is not None:
            if url.startswith("<") and url.endswith(">"):
                url = url[1:-1]

            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(url) as r:
                        data = await r.read()
                except aiohttp.InvalidURL:
                    return await ctx.warning('That link is invalid.')
                except aiohttp.ClientError:
                    return await ctx.warning('Something went wrong when trying to get the image.')
        else:
            await ctx.guild.edit(splash=None, reason=f'server splash updated by {ctx.author}')
            await ctx.success('I have **removed** the server invite splash.')
            return

        try:
            async with ctx.typing():
                await ctx.guild.edit(splash=data, reason=f'server splash updated by {ctx.author}')
        except ValueError:
            await ctx.warning('JPG/PNG format only.')
        else:
            await ctx.success(f'I have **updated** the server invite splash to [**image**]({url}).')

async def setup(bot):
    await bot.add_cog(Config(bot))
