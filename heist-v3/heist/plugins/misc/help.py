from discord.ext.commands import Cog, command
from discord import Embed
from heist.framework.discord import Context

class Help(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.remove_command('help')

    def get_permissions(self, command):
        """Extract permissions from command checks"""
        perms = set()
        
        # Check if command has perms attribute (like in the example)
        if hasattr(command, 'perms') and command.perms:
            if isinstance(command.perms, list):
                perms.update(p.replace('_', ' ') for p in command.perms)
            else:
                perms.add(str(command.perms).replace('_', ' '))
        
        # Check command checks for permissions (using the working approach)
        if hasattr(command, 'checks'):
            for check in command.checks:
                if hasattr(check, 'permissions'):
                    perms.update(p.replace('_', ' ') for p in check.permissions.keys())
                elif hasattr(check, 'predicate') and hasattr(check.predicate, 'permissions'):
                    perms.update(p.replace('_', ' ') for p in check.predicate.permissions.keys())
                elif hasattr(check, '__closure__') and check.__closure__:
                    for cell in check.__closure__:
                        try:
                            value = cell.cell_contents
                            if isinstance(value, dict):
                                for k, v in value.items():
                                    if v is True:
                                        perms.add(k.replace('_', ' '))
                        except:
                            continue
        
        # Convert to list and title case
        return [perm.title() for perm in sorted(perms) if perm != 'send messages']

    @command(name="help")
    async def help_command(self, ctx: Context, *, command=None):
        """Get help for commands"""
        if not command:
            return await ctx.send(f"https://heist.lol/commands, join the discord server @ https://discord.gg/heistbot")
        
        from discord.ext.commands import Command, Group, Cog
        
        if isinstance(command, str):
            cmd = self.bot.get_command(command)
            cog = self.bot.get_cog(command.title())
            if cmd:
                command = cmd
            elif cog:
                command = cog
            else:
                return await ctx.warn(f"Command or module **{command}** not found")
        
        if isinstance(command, Command) and not isinstance(command, Group):
            full_name = command.qualified_name
            embed = Embed(
                title=f"Command: {full_name}",
                description=command.help or "No description available",
                color=ctx.config.colors.information
            )
            
            aliases = ", ".join(command.aliases) if command.aliases else "N/A"
            embed.add_field(name="Aliases", value=aliases, inline=True)
            
            params = []
            required_params = []
            optional_params = []
            if command.params:
                for param_name, param in command.params.items():
                    if param_name not in ['self', 'ctx']:
                        if param.default is param.empty:
                            params.append(f"__{param_name}__")
                            required_params.append(param_name)
                        else:
                            params.append(param_name)
                            optional_params.append(param_name)
            embed.add_field(name="Parameters", value=", ".join(params) if params else "None", inline=True)
            
            perms = self.get_permissions(command)
            
            if perms:
                perm_text = '\n'.join(f"{ctx.config.emojis.context.warn} {perm}" for perm in perms)
                embed.add_field(name="Permissions", value=perm_text, inline=True)
            else:
                embed.add_field(name="Permissions", value="None", inline=True)
            
            guild_prefix = await ctx.bot.get_guild_prefix(ctx.guild.id) if ctx.guild else ctx.config.clean_prefix
            syntax = f"{guild_prefix}{full_name}"
            if required_params:
                syntax += f" {' '.join(f'<{param}>' for param in required_params)}"
            if optional_params:
                syntax += f" {' '.join(f'[{param}]' for param in optional_params)}"
            
            usage_text = f"Syntax: {syntax}"
            example = f"{guild_prefix}{full_name}"
            example_values = {
                "user": "@john", "member": "@john", "channel": "#general", "role": "@admin", 
                "reason": "spam", "message": "hello", "text": "hello", "amount": "5", 
                "time": "10m", "duration": "1h", "delete": "true", "delete_after": "5s",
                "template": "Welcome {user}!", "status": "online", "color": "red",
                "limit": "10", "number": "3", "value": "example", "name": "test",
                "content": "hello world", "topic": "support", "description": "help topic",
                "enabled": "true", "text_bonus": "10", "image_bonus": "15", "booster_bonus": "20",
                "effort": "true", "multiplier": "2", "level": "5", "xp": "100", "points": "50",
                "prefix": "!", "toggle": "on", "state": "enabled", "mode": "normal"
            }
            all_params = required_params + optional_params
            if all_params:
                example += f" {' '.join(example_values.get(param, param) for param in all_params)}"
            usage_text += f"\nExample: {example}"
            
            embed.add_field(name="Usage", value=f"```{usage_text}```", inline=False)
            
            module_name = command.cog.__class__.__name__.lower() if command.cog else "core"
            embed.set_footer(text=f"Module: {module_name} ・ Page: 1/1")
            embed.set_author(name=self.bot.user.display_name, icon_url=self.bot.user.display_avatar.url)
            
            return await ctx.send(embed=embed)
        
        elif isinstance(command, Group):
            embed = Embed(
                title=f"Group: {command.name}",
                description=command.help or "No description available",
                color=ctx.config.colors.information
            )
            
            aliases = ", ".join(command.aliases) if command.aliases else "N/A"
            embed.add_field(name="Aliases", value=aliases, inline=True)
            
            commands = [cmd for cmd in command.commands if not cmd.hidden]
            embed.add_field(name="Subcommands", value=str(len(commands)), inline=True)
            
            perms = self.get_permissions(command)
            
            if perms:
                perm_text = '\n'.join(f"{ctx.config.emojis.context.warn} {perm}" for perm in perms)
                embed.add_field(name="Permissions", value=perm_text, inline=True)
            else:
                embed.add_field(name="Permissions", value="None", inline=True)
            
            guild_prefix = await ctx.bot.get_guild_prefix(ctx.guild.id) if ctx.guild else ctx.config.clean_prefix
            syntax = f"{guild_prefix}{command.name} <subcommand>"
            embed.add_field(name="Syntax", value=f"```{syntax}```", inline=False)
            
            module_name = command.cog.__class__.__name__.lower() if command.cog else "core"
            
            if not commands:
                embed.set_footer(text=f"Page: 1/1 ・ Module: {module_name}")
                embed.set_author(name=self.bot.user.display_name, icon_url=self.bot.user.display_avatar.url)
                return await ctx.send(embed=embed)
            
            embeds = [embed]
            for i, cmd in enumerate(commands, 1):
                full_cmd_name = f"{command.name} {cmd.name}"
                cmd_embed = Embed(
                    title=f"Command: {full_cmd_name}",
                    description=cmd.help or "No description available",
                    color=ctx.config.colors.information
                )
                
                aliases = ", ".join(cmd.aliases) if cmd.aliases else "N/A"
                cmd_embed.add_field(name="Aliases", value=aliases, inline=True)
                
                params = []
                required_params = []
                optional_params = []
                if cmd.params:
                    for param_name, param in cmd.params.items():
                        if param_name not in ['self', 'ctx']:
                            if param.default is param.empty:
                                params.append(f"__{param_name}__")
                                required_params.append(param_name)
                            else:
                                params.append(param_name)
                                optional_params.append(param_name)
                cmd_embed.add_field(name="Parameters", value=", ".join(params) if params else "None", inline=True)
                
                perms = self.get_permissions(cmd)
                
                if perms:
                    perm_text = '\n'.join(f"{ctx.config.emojis.context.warn} {perm}" for perm in perms)
                    cmd_embed.add_field(name="Permissions", value=perm_text, inline=True)
                else:
                    cmd_embed.add_field(name="Permissions", value="None", inline=True)
                
                guild_prefix = await ctx.bot.get_guild_prefix(ctx.guild.id) if ctx.guild else ctx.config.clean_prefix
                syntax = f"{guild_prefix}{full_cmd_name}"
                if required_params:
                    syntax += f" {' '.join(f'<{param}>' for param in required_params)}"
                if optional_params:
                    syntax += f" {' '.join(f'[{param}]' for param in optional_params)}"
                
                usage_text = f"Syntax: {syntax}"
                example = f"{guild_prefix}{full_cmd_name}"
                example_values = {
                    "user": "@john", "member": "@john", "channel": "#general", "role": "@admin", 
                    "reason": "spam", "message": "hello", "text": "hello", "amount": "5", 
                    "time": "10m", "duration": "1h", "delete": "true", "delete_after": "5s",
                    "template": "Welcome {user}!", "status": "online", "color": "#9E6C6D",
                    "limit": "10", "number": "3", "value": "example", "name": "test",
                    "content": "hello world", "topic": "support", "description": "help topic",
                    "enabled": "true", "text_bonus": "10", "image_bonus": "15", "booster_bonus": "20",
                    "effort": "true", "multiplier": "2", "level": "5", "xp": "100", "points": "50",
                    "prefix": ";", "toggle": "on", "state": "enabled", "mode": "normal"
                }
                all_params = required_params + optional_params
                if all_params:
                    example += f" {' '.join(example_values.get(param, param) for param in all_params)}"
                usage_text += f"\nExample: {example}"
                
                cmd_embed.add_field(name="Usage", value=f"```{usage_text}```", inline=False)
                
                cmd_embed.set_author(name=self.bot.user.display_name, icon_url=self.bot.user.display_avatar.url)
                embeds.append(cmd_embed)
            
            from heist.framework.pagination import Paginator
            paginator = Paginator(ctx, embeds)
            return await paginator.start()
            
        elif isinstance(command, Cog):
            all_commands = []
            for cmd in command.get_commands():
                if not cmd.hidden:
                    all_commands.append(cmd)
                    if isinstance(cmd, Group):
                        for subcmd in cmd.commands:
                            if not subcmd.hidden:
                                all_commands.append(subcmd)
            
            module_name = command.__class__.__name__.lower()
            
            if not all_commands:
                return await ctx.warn("No commands found")
            
            embeds = []
            for i, cmd in enumerate(all_commands, 1):
                full_name = cmd.qualified_name
                embed = Embed(
                    title=f"Command: {full_name}",
                    description=cmd.help or "No description available",
                    color=ctx.config.colors.information
                )
                
                aliases = ", ".join(cmd.aliases) if cmd.aliases else "N/A"
                embed.add_field(name="Aliases", value=aliases, inline=True)
                
                params = []
                required_params = []
                if cmd.params:
                    for param_name, param in cmd.params.items():
                        if param_name not in ['self', 'ctx']:
                            if param.default is param.empty:
                                params.append(f"__{param_name}__")
                                required_params.append(param_name)
                            else:
                                params.append(param_name)
                embed.add_field(name="Parameters", value=", ".join(params) if params else "None", inline=True)
                
                perms = self.get_permissions(cmd)
                
                if perms:
                    perm_text = '\n'.join(f"{ctx.config.emojis.context.warn} {perm}" for perm in perms)
                    embed.add_field(name="Permissions", value=perm_text, inline=True)
                else:
                    embed.add_field(name="Permissions", value="None", inline=True)
                
                guild_prefix = await ctx.bot.get_guild_prefix(ctx.guild.id) if ctx.guild else ctx.config.clean_prefix
                syntax = f"{guild_prefix}{full_name}"
                if required_params:
                    syntax += f" {' '.join(f'<{param}>' for param in required_params)}"
                embed.add_field(name="Syntax", value=f"```{syntax}```", inline=False)
                
                embed.set_footer(text=f"Module: {module_name}")
                embed.set_author(name=self.bot.user.display_name, icon_url=self.bot.user.display_avatar.url)
                
                embeds.append(embed)
            
            from heist.framework.pagination import Paginator
            paginator = Paginator(ctx, embeds)
            return await paginator.start()
        
        return await ctx.warn("Invalid command or module")

async def setup(bot):
    await bot.add_cog(Help(bot))