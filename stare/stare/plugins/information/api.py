import discord
from discord.ext import commands, tasks
from stare.core.tools.context import CustomContext as Context
import aiohttp
import json

class API(commands.Cog):
    """API integration for website"""
    
    def __init__(self, bot):
        self.bot = bot
        self.api_url = "https://stare.lat/api"  # Your production URL
    
    async def cog_load(self):
        """Start the stats update task when cog loads"""
        # Don't sync immediately - wait for bot to be ready
        self.update_stats_task.start()
        print("✅ Stats update task started")
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Update commands when bot is fully ready (all cogs loaded)"""
        # Only sync once when bot first becomes ready
        if not hasattr(self, '_commands_synced'):
            await self.update_commands()
            await self.update_stats()
            print("✅ Commands synced to website")
            self._commands_synced = True
    
    async def cog_unload(self):
        """Stop the stats update task when cog unloads"""
        self.update_stats_task.cancel()
    
    @tasks.loop(minutes=5)
    async def update_stats_task(self):
        """Update stats every 5 minutes"""
        await self.update_stats()
    
    @update_stats_task.before_loop
    async def before_update_stats(self):
        """Wait until bot is ready before starting the loop"""
        await self.bot.wait_until_ready()
    
    async def update_stats(self):
        """POST stats to the production API"""
        from stare.core.config import Config
        
        try:
            # Calculate total users across all guilds
            total_users = sum(guild.member_count for guild in self.bot.guilds)
            
            # Handle NaN latency (bot not fully connected yet)
            latency = self.bot.latency
            if latency != latency:  # NaN check (NaN != NaN is True)
                latency = 0
            ping = round(latency * 1000)
            
            # Prepare stats data
            stats_data = {
                'guilds': len(self.bot.guilds),
                'users': total_users,
                'ping': ping,
                'shards': [{
                    'id': 0,
                    'latency': ping,
                    'guilds': len(self.bot.guilds),
                    'users': total_users,
                    'status': 'online'
                }]
            }
            
            # POST to production API
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/stats?token={Config.KEYS.API_TOKEN}",
                    json=stats_data,
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    if resp.status == 200:
                        print(f"✅ Stats updated: {stats_data['guilds']} guilds, {stats_data['users']} users")
                    else:
                        error_text = await resp.text()
                        print(f"❌ Stats update failed: {resp.status} - {error_text}")
        
        except Exception as e:
            print(f"❌ Error updating stats: {e}")
    
    async def update_commands(self):
        """POST commands to the production API"""
        from stare.core.config import Config
        
        commands_list = []
        category_counts = {}
        
        # Group commands by their folder (category)
        for cog_name, cog in self.bot.cogs.items():
            # Skip jishaku and API cog specifically (not Information!)
            if cog_name.lower() in ['jishaku', 'api']:
                continue
            
            # Get the module path to determine folder/category
            module_path = cog.__module__
            
            if 'stare.plugins.' in module_path:
                parts = module_path.split('.')
                if len(parts) >= 3:
                    category = parts[2].capitalize()
                    # Skip developer folder
                    if category.lower() == 'developer':
                        continue
                else:
                    category = "Other"
            else:
                category = "Other"
            
            # Get all commands from this cog
            cog_cmd_count = 0
            for cmd in cog.get_commands():
                if cmd.hidden:
                    continue
                
                # Add the main command
                self._add_command_to_list(cmd, category, commands_list)
                category_counts[category] = category_counts.get(category, 0) + 1
                cog_cmd_count += 1
                
                # If it's a group, add all subcommands
                if isinstance(cmd, commands.Group):
                    for subcmd in cmd.commands:
                        if not subcmd.hidden:
                            self._add_command_to_list(subcmd, category, commands_list)
                            category_counts[category] = category_counts.get(category, 0) + 1
                            cog_cmd_count += 1
        
        # POST to production API
        try:
            print(f"📊 Sending {len(commands_list)} commands to website")
            print(f"📊 Categories: {category_counts}")
            print(f"📊 All cogs: {list(self.bot.cogs.keys())}")
            
            # Sort commands alphabetically by name
            commands_list.sort(key=lambda x: x['name'].lower())
            
            # Sort categories alphabetically
            category_counts = dict(sorted(category_counts.items(), key=lambda x: x[0].lower()))
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/commands?token={Config.KEYS.API_TOKEN}",
                    json={"commands": commands_list, "categories": category_counts},
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    if resp.status == 200:
                        print("✅ Commands updated on website")
                    else:
                        error_text = await resp.text()
                        print(f"⚠️  Failed to update commands: {resp.status}")
                        print(f"⚠️  Response: {error_text}")
        
        except Exception as e:
            print(f"❌ Error updating commands: {e}")
    
    def _add_command_to_list(self, cmd, category, commands_list):
        """Helper method to add a command to the list"""
        # Build usage string
        usage = f"{self.bot.command_prefix}{cmd.qualified_name}"
        if cmd.signature:
            usage += f" {cmd.signature}"
        
        # Build aliases string
        aliases = []
        if cmd.aliases:
            aliases = [f"{self.bot.command_prefix}{alias}" for alias in cmd.aliases]
        
        # Extract arguments from signature
        arguments = []
        if cmd.signature:
            import re
            arg_pattern = r'[<\[]([^>\]]+)[>\]]'
            matches = re.findall(arg_pattern, cmd.signature)
            for match in matches:
                arg_name = match.replace('...', '').strip()
                arguments.append(arg_name)
        
        commands_list.append({
            'name': cmd.qualified_name,
            'description': cmd.help or 'No description',
            'category': category,
            'usage': usage,
            'aliases': aliases,
            'arguments': arguments if arguments else None
        })
    
    @commands.command(hidden=True)
    @commands.is_owner()
    async def syncweb(self, ctx: Context):
        """Manually sync commands and stats to website"""
        await ctx.send("🔄 Syncing to website...")
        await self.update_commands()
        await self.update_stats()
        await ctx.send("✅ Synced!")

async def setup(bot):
    await bot.add_cog(API(bot))
