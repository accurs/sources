from typing import Dict, Optional, List, Any
import discord

class CommandCache:
    """Reusable command cache for Discord bots."""
    
    _commands: Dict[str, int] = {}
    _detailed_cache: List[Dict[str, Any]] = []
    _loaded: bool = False

    @classmethod
    async def load_commands(cls, bot) -> None:
        """Fetch all application commands and cache them."""
        commands = await bot.tree.fetch_commands()
        cls._commands = {}
        cls._detailed_cache = []

        def process_command(cmd, parent_name="", parent_id=None):
            full_name = f"{parent_name} {cmd.name}".strip()
            cmd_id = getattr(cmd, 'id', parent_id)

            if cmd_id:
                cls._commands[full_name] = cmd_id

                cmd_type = getattr(cmd, 'type', discord.AppCommandType.chat_input)
                if not parent_name and cmd_type != discord.AppCommandType.chat_input:
                    return

                # Detect hybrid commands
                is_hybrid = hasattr(bot.get_command(cmd.name.split()[-1]), 'callback') \
                    if bot.get_command(cmd.name.split()[-1]) else False

                # Find cog name
                cog_name = "Unknown"
                cmd_name_parts = full_name.split()
                base_cmd_name = cmd_name_parts[0] if cmd_name_parts else full_name

                for cog_name_key, cog in bot.cogs.items():
                    try:
                        for app_cmd in cog.get_app_commands():
                            if (hasattr(app_cmd, 'name') and app_cmd.name == base_cmd_name) or \
                               (hasattr(app_cmd, 'qualified_name') and base_cmd_name in app_cmd.qualified_name):
                                cog_name = cog.__class__.__name__
                                break
                        if cog_name != "Unknown":
                            break
                    except Exception:
                        continue

                # Check if it's a group
                is_group = hasattr(cmd, 'options') and any(
                    option.type in [discord.AppCommandOptionType.subcommand,
                                    discord.AppCommandOptionType.subcommand_group]
                    for option in cmd.options
                )

                # Gather arguments
                arguments = []
                if hasattr(cmd, 'options'):
                    for option in cmd.options:
                        if option.type not in [
                            discord.AppCommandOptionType.subcommand,
                            discord.AppCommandOptionType.subcommand_group
                        ]:
                            arguments.append({
                                "name": option.name,
                                "description": getattr(option, 'description', ''),
                                "type": option.type.name,
                                "required": getattr(option, 'required', True),
                                "choices": [choice.name for choice in getattr(option, 'choices', [])]
                            })

                cls._detailed_cache.append({
                    "name": full_name,
                    "id": cmd_id,
                    "description": getattr(cmd, 'description', ''),
                    "type": cmd_type.name if hasattr(cmd_type, 'name') else 'chat_input',
                    "is_hybrid": is_hybrid,
                    "is_group": is_group,
                    "cog": cog_name,
                    "arguments": arguments,
                    "mention": f"</{full_name}:{cmd_id}>"
                })

            # Recursively handle subcommands
            if hasattr(cmd, 'options'):
                for option in cmd.options:
                    if option.type == discord.AppCommandOptionType.subcommand_group:
                        if hasattr(option, 'options'):
                            for sub_option in option.options:
                                process_command(sub_option, f"{full_name} {option.name}", cmd_id)
                    elif option.type == discord.AppCommandOptionType.subcommand:
                        process_command(option, full_name, cmd_id)

        for cmd in commands:
            process_command(cmd, "", getattr(cmd, 'id', None))

        cls._loaded = True

    @classmethod
    async def ensure_loaded(cls, bot):
        """Ensure command cache is loaded."""
        if not cls._loaded or not cls._commands:
            await cls.load_commands(bot)

    @classmethod
    async def get_command_id(cls, bot, name: str) -> Optional[int]:
        """Get command ID by full name (loads cache if empty)."""
        await cls.ensure_loaded(bot)
        return cls._commands.get(name)

    @classmethod
    async def get_mention(cls, bot, name: str) -> str:
        """Get a formatted command mention string."""
        cmd_id = await cls.get_command_id(bot, name)
        return f"</{name}:{cmd_id}>" if cmd_id else f"`/{name}`"

    @classmethod
    async def get_all(cls, bot) -> List[Dict[str, Any]]:
        """Get all cached commands (loads cache if empty)."""
        await cls.ensure_loaded(bot)
        return cls._detailed_cache
