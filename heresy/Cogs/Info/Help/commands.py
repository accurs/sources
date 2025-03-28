import discord
from discord.ext import commands
import json
import os

class Commands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        file_path = os.path.join("cogs", "info", "help", "commands.json")

        with open(file_path, 'r') as f:
            self.command_data = json.load(f)

    @commands.command(name='commands', aliases= ['cmd'], description="Shows the command menu or details about a specific command.")
    async def help_command(self, ctx, command_name: str = None):
        if command_name is None:
            embed = discord.Embed(
                title="Heresy Command Menu",
                description="Information\n > [] = optional, <> = required",
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            embed.add_field(name="Resources", value="[Invite](https://discord.com/oauth2/authorize?client_id=1276814848554176583&permissions=8&integration_type=0&scope=bot) | [Website](https://playfairs.cc) | [Discord Server](https://discord.gg/heresy)", inline=False)
            embed.set_footer(text="Please select a category from the dropdown menu below")

            categories = self.command_data["commands"].keys()
            options = [discord.SelectOption(label=category) for category in categories]

            class Dropdown(discord.ui.Select):
                def __init__(self, outer_instance):
                    super().__init__(
                        placeholder="Select a category...",
                        min_values=1,
                        max_values=1,
                        options=options
                    )
                    self.outer_instance = outer_instance

                async def callback(self, interaction: discord.Interaction):
                    selected = self.values[0]
                    category_embed = discord.Embed(
                        title="heresy Command Menu",
                        description=f"Category: {selected}",
                        color=discord.Color.red()
                    )
                    commands_list = self.outer_instance.get_commands_for_category(selected)
                    command_count = len(commands_list)
                    commands_display = ", ".join(commands_list)
                    category_embed.add_field(name="Commands", value=f"```{commands_display}```", inline=False)
                    category_embed.set_footer(text=f"{command_count} commands")

                    await interaction.response.edit_message(embed=category_embed, view=view)

            view = discord.ui.View()
            view.add_item(Dropdown(self))

            await ctx.send(embed=embed, view=view)

        else:
            await self.command_help(ctx, command_name)

    def get_commands_for_category(self, category):
        return self.command_data["commands"].get(category, {}).keys()

    async def command_help(self, ctx, command_name: str):
        for category, commands in self.command_data["commands"].items():
            if command_name in commands:
                command_info = commands[command_name]
                embed = discord.Embed(
                    title=f"{command_name.capitalize()} Command",
                    description=f"{command_info['description']}\n```ruby\nSyntax: {command_info['syntax']}\nExample: {command_info['example']}\n```",
                    color=discord.Color.red()
                )
                embed.add_field(name="Permissions", value=command_info.get('permissions', 'None'))
                embed.add_field(name="Optional Flags", value=command_info.get('flags', 'None'))
                embed.add_field(name="Arguments", value=command_info.get('args', 'None'))
                embed.add_field(name="NOTE", value=command_info.get('note', 'none'))

                aliases = command_info.get('aliases', [])
                aliases_str = ', '.join(aliases) if isinstance(aliases, list) else 'None'
                embed.add_field(name="Aliases", value=aliases_str if aliases else 'None')

                await ctx.send(embed=embed)
                return

        await ctx.send(f"No information found for the command: `{command_name}`")


async def setup(bot):
    await bot.add_cog(Commands(bot))
