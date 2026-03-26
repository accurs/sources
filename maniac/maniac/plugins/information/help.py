import discord
from discord.ext import commands
from maniac.core.config import Config

class HelpView(discord.ui.View):
    def __init__(self, ctx, pages, current_page=0):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.pages = pages
        self.current_page = current_page
        self.message = None
        self.setup_buttons()
        self.update_buttons()
    
    def setup_buttons(self):
        self.children[0].emoji = Config.EMOJIS.BACKWARD
        self.children[0].style = discord.ButtonStyle.blurple
        self.children[1].emoji = Config.EMOJIS.FORWARD
        self.children[1].style = discord.ButtonStyle.blurple
        self.children[2].emoji = Config.EMOJIS.SKIPTO
        self.children[2].style = discord.ButtonStyle.gray
        self.children[3].emoji = Config.EMOJIS.CLOSE
        self.children[3].style = discord.ButtonStyle.red
    
    def update_buttons(self):
        pass
    
    async def update_message(self):
        self.update_buttons()
        await self.message.edit(embed=self.pages[self.current_page], view=self)
    
    @discord.ui.button(style=discord.ButtonStyle.gray)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This isn't your help menu!", ephemeral=True)
        
        if self.current_page == 0:
            self.current_page = len(self.pages) - 1
        else:
            self.current_page -= 1
        
        await interaction.response.defer()
        await self.update_message()
    
    @discord.ui.button(style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This isn't your help menu!", ephemeral=True)
        
        if self.current_page >= len(self.pages) - 1:
            self.current_page = 0
        else:
            self.current_page += 1
        
        await interaction.response.defer()
        await self.update_message()
    
    @discord.ui.button(style=discord.ButtonStyle.gray)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This isn't your help menu!", ephemeral=True)
        await interaction.response.send_modal(SkipModal(self))
    
    @discord.ui.button(style=discord.ButtonStyle.red)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This isn't your help menu!", ephemeral=True)
        await interaction.message.delete()
        self.stop()

class SkipModal(discord.ui.Modal, title="Skip to Page"):
    page_number = discord.ui.TextInput(label="Page Number", placeholder="Enter page number...", max_length=3)
    
    def __init__(self, view):
        super().__init__()
        self.view = view
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            page = int(self.page_number.value) - 1
            if 0 <= page < len(self.view.pages):
                self.view.current_page = page
                await interaction.response.defer()
                await self.view.update_message()
            else:
                await interaction.response.send_message(f"Invalid page! Choose between 1-{len(self.view.pages)}", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Please enter a valid number!", ephemeral=True)

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        
        if not message.content.startswith(Config.PREFIX):
            return
        
        content = message.content[len(Config.PREFIX):].strip()
        
        if not content or ' ' in content:
            return
        
        command = self.bot.get_command(content)
        
        if command and isinstance(command, commands.Group) and command.commands:
            ctx = await self.bot.get_context(message)
            await self.send_group_help(ctx, command)
    
    @commands.command(name="help", aliases=["h", "commands"])
    async def help_command(self, ctx, *, command_name: str = None):
        if command_name:
            await self.send_command_help(ctx, command_name)
        else:
            await self.send_bot_help(ctx)
    
    async def send_bot_help(self, ctx):
        embed = discord.Embed(
            title=f"{ctx.bot.user.name} Command Help",
            color=Config.COLORS.DEFAULT
        )
        embed.set_thumbnail(url=ctx.bot.user.display_avatar.url)
        
        total_commands = len([cmd for cmd in self.bot.commands if not cmd.hidden])
        total_categories = len([cog for cog in self.bot.cogs if cog != "Help" and self.bot.get_cog(cog).get_commands()])
        
        info_text = f"> **Prefix:** ,\n"
        info_text += f"> **Categories:** {total_categories}\n"
        info_text += f"> **Commands:** {total_commands}"
        embed.add_field(name="Information", value=info_text, inline=True)
        
        links_text = "> [Website](https://maniac.best)\n"
        links_text += "> [Documentation](https://maniac.best)\n"
        links_text += "> [Invite](https://discordapp.com/oauth2/authorize?client_id=1476968435186401486&scope=bot+applications.commands&permissions=0)\n"
        links_text += "> [Support Server](https://maniac.best/support)"
        embed.add_field(name="Links", value=links_text, inline=True)
        
        embed.set_footer(text="If you need help with a specific command, use ,help (command)")
        
        await ctx.send(embed=embed)
    
    async def send_command_help(self, ctx, command_name):
        command = self.bot.get_command(command_name)
        
        if not command:
            return await ctx.warn(f"Command `{command_name}` does not exist.")
        
        if isinstance(command, commands.Group) and command.commands:
            return await self.send_group_help(ctx, command)
        
        cog_name = command.cog.qualified_name if command.cog else "No Category"
        
        embed = discord.Embed(
            title=f"Command: {command.name}",
            description=command.help or "No description available.",
            color=Config.COLORS.DEFAULT
        )
        embed.set_author(name=f"{ctx.bot.user.name} help", icon_url=ctx.bot.user.display_avatar.url)
        
        aliases_text = ", ".join(command.aliases) if command.aliases else "n/a"
        
        params = []
        for param_name, param in command.clean_params.items():
            if param.default == param.empty:
                params.append(f"{param_name}")
            else:
                params.append(f"[{param_name}]")
        
        params_text = ", ".join(params) if params else "n/a"
        
        perms = []
        for check in command.checks:
            check_name = check.__qualname__ if hasattr(check, '__qualname__') else str(check)
            if 'has_permissions' in check_name:
                if hasattr(check, '__closure__') and check.__closure__:
                    for cell in check.__closure__:
                        if isinstance(cell.cell_contents, dict):
                            perm_names = [f"`{perm}`" for perm in cell.cell_contents.keys()]
                            perms.extend(perm_names)
            elif 'is_owner' in check_name:
                perms.append("Bot owner only")
        
        perm_text = f"{Config.EMOJIS.WARNING} " + ", ".join(perms) if perms else "n/a"
        
        embed.add_field(name="Aliases", value=aliases_text, inline=True)
        embed.add_field(name="Parameters", value=params_text, inline=True)
        embed.add_field(name="Permissions", value=perm_text, inline=True)
        
        syntax_params = []
        for param_name, param in command.clean_params.items():
            if param.default == param.empty:
                syntax_params.append(f"<{param_name}>")
            else:
                syntax_params.append(f"[{param_name}]")
        
        syntax = f"{Config.PREFIX}{command.name} {' '.join(syntax_params)}".strip()
        
        example_text = None
        if hasattr(command, '__example__'):
            example_text = command.__example__
        elif hasattr(command.callback, '__example__'):
            example_text = command.callback.__example__
        elif hasattr(command.callback, '__func__'):
            example_text = getattr(command.callback.__func__, '__example__', None)
        
        if not example_text:
            example_text = f"{Config.PREFIX}{command.name}"
        
        embed.add_field(
            name="Usage",
            value=f"```ansi\n\u001b[0;35mSyntax:\u001b[0m  {syntax}\n\u001b[0;35mExample:\u001b[0m {example_text}\n```",
            inline=False
        )
        
        embed.set_footer(text=f"Page 1/1 (1 entries) • Module: {cog_name.lower()}")
        
        await ctx.send(embed=embed)
    
    async def send_group_help(self, ctx, group):
        cog_name = group.cog.qualified_name if group.cog else "No Category"
        subcommands = [cmd for cmd in group.commands if not cmd.hidden]
        
        if not subcommands:
            return await self.send_command_help(ctx, group.name)
        
        pages = []
        total_entries = len(subcommands) + (1 if group.invoke_without_command else 0)
        
        if group.invoke_without_command:
            embed = discord.Embed(
                title=f"Command: {group.name}",
                description=group.help or "No description available.",
                color=Config.COLORS.DEFAULT
            )
            embed.set_author(name=f"{ctx.bot.user.name} help", icon_url=ctx.bot.user.display_avatar.url)
            
            aliases_text = ", ".join(group.aliases) if group.aliases else "n/a"
            
            params = []
            for param_name, param in group.clean_params.items():
                if param.default == param.empty:
                    params.append(f"{param_name}")
                else:
                    params.append(f"[{param_name}]")
            
            params_text = ", ".join(params) if params else "n/a"
            
            perms = []
            for check in group.checks:
                check_name = check.__qualname__ if hasattr(check, '__qualname__') else str(check)
                if 'has_permissions' in check_name:
                    if hasattr(check, '__closure__') and check.__closure__:
                        for cell in check.__closure__:
                            if isinstance(cell.cell_contents, dict):
                                perm_names = [f"`{perm}`" for perm in cell.cell_contents.keys()]
                                perms.extend(perm_names)
                elif 'is_owner' in check_name:
                    perms.append("Bot owner only")
            
            perm_text = f"{Config.EMOJIS.WARNING} " + ", ".join(perms) if perms else "n/a"
            
            embed.add_field(name="Aliases", value=aliases_text, inline=True)
            embed.add_field(name="Parameters", value=params_text, inline=True)
            embed.add_field(name="Permissions", value=perm_text, inline=True)
            
            syntax_params = []
            for param_name, param in group.clean_params.items():
                if param.default == param.empty:
                    syntax_params.append(f"<{param_name}>")
                else:
                    syntax_params.append(f"[{param_name}]")
            
            syntax = f"{Config.PREFIX}{group.name} {' '.join(syntax_params)}".strip()
            
            example_text = None
            if hasattr(group, '__example__'):
                example_text = group.__example__
            elif hasattr(group.callback, '__example__'):
                example_text = group.callback.__example__
            elif hasattr(group.callback, '__func__'):
                example_text = getattr(group.callback.__func__, '__example__', None)
            
            if not example_text:
                example_text = f"{Config.PREFIX}{group.name}"
            
            embed.add_field(
                name="Usage",
                value=f"```ansi\n\u001b[0;35mSyntax:\u001b[0m  {syntax}\n\u001b[0;35mExample:\u001b[0m {example_text}\n```",
                inline=False
            )
            
            embed.set_footer(text=f"Page 1/{total_entries} ({total_entries} entries) • Module: {cog_name.lower()}")
            pages.append(embed)
        
        for cmd in subcommands:
            embed = discord.Embed(
                title=f"Group command: {group.name} {cmd.name}",
                description=cmd.help or "No description available.",
                color=Config.COLORS.DEFAULT
            )
            embed.set_author(name=f"{ctx.bot.user.name} help", icon_url=ctx.bot.user.display_avatar.url)
            
            aliases_text = ", ".join(cmd.aliases) if cmd.aliases else "n/a"
            
            params = []
            for param_name, param in cmd.clean_params.items():
                if param.default == param.empty:
                    params.append(f"{param_name}")
                else:
                    params.append(f"[{param_name}]")
            
            params_text = ", ".join(params) if params else "n/a"
            
            perms = []
            for check in cmd.checks:
                check_name = check.__qualname__ if hasattr(check, '__qualname__') else str(check)
                if 'has_permissions' in check_name:
                    if hasattr(check, '__closure__') and check.__closure__:
                        for cell in check.__closure__:
                            if isinstance(cell.cell_contents, dict):
                                perm_names = [f"`{perm}`" for perm in cell.cell_contents.keys()]
                                perms.extend(perm_names)
                elif 'is_owner' in check_name:
                    perms.append("Bot owner only")
            
            perm_text = f"{Config.EMOJIS.WARNING} " + ", ".join(perms) if perms else "n/a"
            
            embed.add_field(name="Aliases", value=aliases_text, inline=True)
            embed.add_field(name="Parameters", value=params_text, inline=True)
            embed.add_field(name="Permissions", value=perm_text, inline=True)
            
            syntax_params = []
            for param_name, param in cmd.clean_params.items():
                if param.default == param.empty:
                    syntax_params.append(f"<{param_name}>")
                else:
                    syntax_params.append(f"[{param_name}]")
            
            syntax = f"{Config.PREFIX}{group.name} {cmd.name} {' '.join(syntax_params)}".strip()
            
            example_text = None
            if hasattr(cmd, '__example__'):
                example_text = cmd.__example__
            elif hasattr(cmd.callback, '__example__'):
                example_text = cmd.callback.__example__
            elif hasattr(cmd.callback, '__func__'):
                example_text = getattr(cmd.callback.__func__, '__example__', None)
            
            if not example_text:
                example_text = f"{Config.PREFIX}{group.name} {cmd.name}"
            
            embed.add_field(
                name="Usage",
                value=f"```ansi\n\u001b[0;35mSyntax:\u001b[0m  {syntax}\n\u001b[0;35mExample:\u001b[0m {example_text}\n```",
                inline=False
            )
            
            embed.set_footer(text=f"Page {len(pages) + 1}/{total_entries} ({total_entries} entries) • Module: {cog_name.lower()}")
            pages.append(embed)
        
        if len(pages) == 1:
            await ctx.send(embed=pages[0])
        else:
            view = HelpView(ctx, pages)
            view.message = await ctx.send(embed=pages[0], view=view)

async def setup(bot):
    await bot.add_cog(Help(bot))
