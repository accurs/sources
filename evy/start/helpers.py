from typing import List

import discord
from discord.ext import commands
from .paginator import PaginatorView

class NeoContext(commands.Context): 
 def __init__(self, **kwargs): 
  super().__init__(**kwargs) 

 def find_role(self, name: str): 
   for role in self.guild.roles:
    if role.name == "@everyone": continue  
    if name.lower() in role.name.lower(): return role 
   return None 
 
 async def success(self, message: str) -> discord.Message:  
  return await self.reply(embed=discord.Embed(color=self.bot.color, description=f"{self.bot.yes} {self.author.mention}: {message}") )
 
 async def error(self, message: str) -> discord.Message: 
  return await self.reply(embed=discord.Embed(color=self.bot.color, description=f"{self.bot.no} {self.author.mention}: {message}") ) 
 
 async def warning(self, message: str) -> discord.Message: 
  return await self.reply(embed=discord.Embed(color=self.bot.color, description=f"{self.bot.warning} {self.author.mention}: {message}") )
 
 async def paginator(self, embeds: List[discord.Embed]):
  if len(embeds) == 1: return await self.send(embed=embeds[0]) 
  view = PaginatorView(self, embeds)
  view.message = await self.reply(embed=embeds[0], view=view) 
 
 async def cmdhelp(self): 
    command = self.command
    commandname = f"{str(command.parent)} {command.name}" if str(command.parent) != "None" else command.name
    if command.cog_name == "owner": return
    embed = discord.Embed(color=self.bot.color, title=f"Command: {command.name}", description=command.description)
    embed.set_author(name=self.bot.user.name, icon_url=self.bot.user.avatar.url)
    embed.add_field(name="Category", value=command.help)
    embed.add_field(name="Aliases", value=', '.join(map(str, command.aliases)) or "none")
    embed.add_field(name="Permissions", value=command.brief or "any")
    embed.add_field(name="Usage", value=f"```{commandname} {command.usage if command.usage else ''}```", inline=False)
    await self.reply(embed=embed)

 async def create_pages(self): 
  embeds = []
  i=0
  for command in self.command.commands: 
    commandname = f"{str(command.parent)} {command.name}" if str(command.parent) != "None" else command.name
    i+=1 
    embeds.append(discord.Embed(color=self.bot.color, title=f"Command: {command.name}", description=command.description).set_author(name=self.bot.user.name, icon_url=self.bot.user.avatar.url).add_field(name="Usage", value=f"```{commandname} {command.usage if command.usage else ''}```", inline=False).set_footer(text=f"Aliases: {', '.join(a for a in command.aliases) if len(command.aliases) > 0 else 'none'} ・ {i}/{len(self.command.commands)}"))
     
  return await self.paginator(embeds)  

class HelpCommand(commands.HelpCommand):
  def __init__(self, **kwargs):
   self.categories = {
      "home": "Return to the main page", 
      "misc": "Miscellaneous commands for general use",
      "config": "Configure your server with those commands",
      "economy": "Use commands to earn and spend money",
      "lastfm": "Connect your last.fm account and show your stats",
      "utility": "Useful commands for various purposes",
      } 
   super().__init__(**kwargs)
  
  async def send_bot_help(self, mapping):
      embed = discord.Embed(
          color=self.context.bot.color,
          description=(
              "> Browse through the categories below to explore all available commands.\n"
              "> Need help? Join our [**support server**](https://discord.gg/lol) anytime."
          )
      )
      embed.set_author(
          name=f"{self.context.bot.user.name}",
          icon_url=self.context.bot.user.avatar.url if self.context.bot.user.avatar else self.context.bot.user.default_avatar.url
      )
      embed.set_thumbnail(
          url=self.context.bot.user.avatar.url if self.context.bot.user.avatar else self.context.bot.user.default_avatar.url
      )
      embed.set_footer(
          text=f"{len(set(self.context.bot.walk_commands()))} commands"
      )
  
      options = [
          discord.SelectOption(
              label=c,
              description=self.categories.get(c),
              emoji="📂"
          )
          for c in self.categories
      ]
  
      select = discord.ui.Select(options=options, placeholder="🔍 Select a category...")
  
      async def select_callback(interaction: discord.Interaction): 
       if interaction.user.id != self.context.author.id: return await self.context.bot.ext.send_warning(interaction, "You are not the author of this embed", ephemeral=True)
       if select.values[0] == "home": return await interaction.response.edit_message(embed=embed)
       com = []
       for c in [cm for cm in set(self.context.bot.walk_commands()) if cm.help == select.values[0]]:
        if c.parent:
          entry = f"{c.parent} {c.name}"
          if entry not in com:
            com.append(entry)
        else:
          if c.name not in com:
            com.append(c.name)
       e = discord.Embed(color=self.context.bot.color, title=f"{select.values[0]} commands", description=f"```{', '.join(com)}```").set_author(name=self.context.author.name, icon_url=self.context.author.display_avatar.url)  
       return await interaction.response.edit_message(embed=e)
      select.callback = select_callback
  
      view = discord.ui.View(timeout=None)
      view.add_item(select) 
      return await self.context.reply(embed=embed, view=view)
  
  async def send_command_help(self, command: commands.Command): 
    commandname = f"{str(command.parent)} {command.name}" if str(command.parent) != "None" else command.name
    if command.cog_name == "owner": return
    embed = discord.Embed(color=self.context.bot.color, title=f"Command: {command.name}", description=command.description)
    embed.set_author(name=self.context.bot.user.name, icon_url=self.context.bot.user.avatar.url)
    embed.add_field(name="Category", value=command.help)
    embed.add_field(name="Aliases", value=', '.join(map(str, command.aliases)) or "none")
    embed.add_field(name="Permissions", value=command.brief or "any")
    embed.add_field(name="Usage", value=f"```{commandname} {command.usage if command.usage else ''}```", inline=False)
    channel = self.get_destination()
    await channel.send(embed=embed)

  async def send_group_help(self, group: commands.Group): 
   ctx = self.context
   embeds = []
   i=0
   for command in group.commands: 
    commandname = f"{str(command.parent)} {command.name}" if str(command.parent) != "None" else command.name
    i+=1 
    embeds.append(discord.Embed(color=self.context.bot.color, title=f"Command: {command.name}", description=command.description).set_author(name=self.context.bot.user.name, icon_url=self.context.bot.user.display_avatar.url).add_field(name="Usage", value=f"```{commandname} {command.usage if command.usage else ''}```", inline=False).set_footer(text=f"Aliases: {', '.join(a for a in command.aliases) if len(command.aliases) > 0 else 'none'} ・ {i}/{len(group.commands)}"))
     
   return await ctx.paginator(embeds)