import discord
import discord_ios
from discord.ext import commands, tasks
from pathlib import Path
from datetime import datetime
from stare.core.config import Config
from stare.core.tools.context import CustomContext
import asyncpg
import requests

API_URL = 'https://stare.lat'

async def update_stats(bot):
    try:
        total_users = len(bot.users)  # Unique users across all guilds
        data = {
            'guilds': len(bot.guilds),
            'users': total_users,
            'ping': round(bot.latency * 1000),
            'shards': [{
                'id': 0,
                'latency': round(bot.latency * 1000),
                'guilds': len(bot.guilds),
                'users': total_users,
                'status': 'online'
            }]
        }
        requests.post(f'{API_URL}/api/stats', json=data)
        print('✅ Stats updated')
    except Exception as e:
        print(f'❌ Error updating stats: {e}')

async def update_commands(bot):
    commands_list = []
    
    # Group commands by their folder (category)
    for cmd in bot.commands:
        if not cmd.hidden:
            # Skip jishaku commands only
            if cmd.cog and cmd.cog.qualified_name.lower() in ['jishaku']:
                continue
            
            # Determine category from cog's module path (folder name)
            if cmd.cog:
                module_path = cmd.cog.__module__
                if 'stare.plugins.' in module_path:
                    parts = module_path.split('.')
                    if len(parts) >= 3:
                        category = parts[2].capitalize()  # Get folder name
                    else:
                        category = "Other"
                else:
                    category = "Other"
            else:
                category = "Uncategorized"
            
            commands_list.append({
                'name': cmd.name,
                'description': cmd.help or 'No description',
                'category': category,
                'usage': f'{Config.PREFIX}{cmd.qualified_name} {cmd.signature}'.strip()
            })
    
    try:
        requests.post(f'{API_URL}/api/commands', json={'commands': commands_list})
        print('✅ Commands updated')
    except Exception as e:
        print(f'❌ Error updating commands: {e}')

class StareBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix=Config.PREFIX,
            intents=intents,
            activity=discord.Streaming(name="🔗 stare.lat", url="https://twitch.tv/starelat"),
            help_command=None,
            owner_ids={1019668815728103526, 972254033551179776, 1460003194771083296, 1285277569113133161}
        )
        self.uptime = None
        self.db_pool = None
        self.session = None
        self.db_pool = None
        self.update_stats_task = tasks.loop(minutes=5)(self._update_stats_loop)
    
    async def _update_stats_loop(self):
        """Background task to update stats every 5 minutes"""
        await self.wait_until_ready()
        await update_stats(self)
    
    async def setup_hook(self):
        """Setup hook for bot initialization"""
        # Set uptime
        self.uptime = datetime.now()
        
        # Initialize aiohttp session
        import aiohttp
        self.session = aiohttp.ClientSession()
        
        # Initialize database connection pool
        try:
            self.db_pool = await asyncpg.create_pool(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                database=Config.DB_NAME
            )
            print("✅ Database connection pool created")
        except Exception as e:
            print(f"❌ Failed to create database pool: {e}")
        
        # Load jishaku
        try:
            await self.load_extension('jishaku')
            print("✅ Loaded jishaku")
        except Exception as e:
            print(f"⚠️  Failed to load jishaku: {e}")
        
        # Auto-load all cogs
        await self.load_cogs()
        
        print(f'✅ Setup complete, connecting to Discord...')
    
    async def close(self):
        """Cleanup when bot shuts down"""
        if self.session:
            await self.session.close()
        if self.db_pool:
            await self.db_pool.close()
        await super().close()
    
    async def on_ready(self):
        """Called when the bot is ready"""
        print(f"\n{'='*50}")
        print(f"stare is now online!")
        print(f"logged in as: {self.user.name}")
        print(f"ID: {self.user.id}")
        print(f"Serving {len(self.guilds)} guilds")
        print(f"Across {len(self.users)} users")
        print(f"{'='*50}\n")
        
        # Update stats and commands
        await update_commands(self)
        await update_stats(self)
        
        # Start stats update task
        if not self.update_stats_task.is_running():
            self.update_stats_task.start()
    
    async def on_guild_join(self, guild: discord.Guild):
        """Called when bot joins a guild"""
        print(f"Stare joined a new guild: {guild.name} (ID: {guild.id})")
        
        # Create welcome embed
        embed = discord.Embed(
            title="Thanks for adding stare!",
            description="> -# Need any help? [Join the support server!](https://discord.gg/falln)\n",
            color=Config.COLORS.DEFAULT
        )
        embed.add_field(
            name="stare's prefix",
            value=f"My prefix is **`{Config.PREFIX}`**!\n",
            inline=False
        )
        embed.add_field(
            name="Links",
            value="• [**Website**](https://stare.best)\n• [**Invite**](https://discord.com/oauth2/authorize?client_id=1472023540227117322&permissions=8&integration_type=0&scope=bot)\n• [**Support Server**](https://discord.gg/falln)",
            inline=False
        )
        
        if self.user.avatar:
            embed.set_thumbnail(url=self.user.avatar.url)
        
        # Try to send to system channel first, then first available channel
        channel = guild.system_channel
        
        if not channel or not channel.permissions_for(guild.me).send_messages:
            # Find first text channel where bot can send messages
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break
        
        if channel:
            try:
                await channel.send(embed=embed)
                print(f"📨 Sent welcome message to {guild.name}")
            except Exception as e:
                print(f"❌ Failed to send welcome message to {guild.name}: {e}")
        else:
            print(f"⚠️  No suitable channel found to send welcome message in {guild.name}")
    
    async def on_guild_remove(self, guild: discord.Guild):
        """Called when bot leaves a guild"""
        print(f"⚠️  Removed from guild: {guild.name} (ID: {guild.id})")

    async def get_context(self, message, *, cls=None):
        """Override to use CustomContext"""
        return await super().get_context(message, cls=cls or CustomContext)
    
    async def on_message(self, message):
        """Process commands from messages"""
        if message.author.bot:
            return
        
        # Check if bot is mentioned (not a reply)
        if self.user in message.mentions and not message.reference:
            # Get the guild's custom prefix if it exists
            prefix = Config.PREFIX
            if message.guild and self.db_pool:
                prefix_row = await self.db_pool.fetchrow(
                    'SELECT prefix FROM prefixes WHERE guild_id = $1',
                    message.guild.id
                )
                if prefix_row:
                    prefix = prefix_row['prefix']
            
            # Create context to use approve method
            ctx = await self.get_context(message)
            return await ctx.approve(f'My current prefix is `{prefix}`')
        
        # Only check blacklist if message starts with prefix (is a command)
        if not message.content.startswith(Config.PREFIX):
            return
        
        # Get the context to check if it's a valid command
        ctx = await self.get_context(message)
        
        # Check for custom aliases if command not found and in a guild
        if not ctx.command and message.guild and self.db_pool:
            # Extract the alias from the message
            content_without_prefix = message.content[len(Config.PREFIX):]
            alias_name = content_without_prefix.split()[0].lower() if content_without_prefix else None
            
            if alias_name:
                # Check if this alias exists
                alias_row = await self.db_pool.fetchrow(
                    'SELECT command FROM aliases WHERE guild_id = $1 AND alias = $2',
                    message.guild.id, alias_name
                )
                
                if alias_row:
                    # Replace the alias with the actual command
                    args = content_without_prefix.split()[1:] if len(content_without_prefix.split()) > 1 else []
                    new_content = f"{Config.PREFIX}{alias_row['command']} {' '.join(args)}".strip()
                    message.content = new_content
                    ctx = await self.get_context(message)
        
        # Only show blacklist message if it's a valid command
        if not ctx.command:
            await self.process_commands(message)
            return
        
        # Check if user is blacklisted
        if self.db_pool:
            user_bl = await self.db_pool.fetchrow(
                "SELECT * FROM blacklist_user WHERE user_id = $1",
                message.author.id
            )
            if user_bl:
                try:
                    embed = discord.Embed(
                        description=f"{Config.EMOJIS.WARNING} {message.author.mention}: lil bro you blacklisted, join the [server](https://discord.gg/starebot) to appeal",
                        color=Config.COLORS.WARNING
                    )
                    await message.channel.send(embed=embed)
                except:
                    pass
                return
            
            # Check if guild is blacklisted
            if message.guild:
                guild_bl = await self.db_pool.fetchrow(
                    "SELECT * FROM blacklist_guild WHERE guild_id = $1",
                    message.guild.id
                )
                if guild_bl:
                    try:
                        embed = discord.Embed(
                            description=f"{Config.EMOJIS.WARNING} {message.author.mention}: lil bro this server is blacklisted, join the [server](https://discord.gg/starebot) to appeal",
                            color=Config.COLORS.WARNING
                        )
                        await message.channel.send(embed=embed)
                    except:
                        pass
                    return
        
        await self.process_commands(message)
    
    async def on_command_error(self, ctx: CustomContext, error):
        """Global error handler for commands"""
        if hasattr(ctx.command, 'on_error'):
            return
        
        error = getattr(error, 'original', error)
        
        if isinstance(error, commands.CheckFailure):
            if str(error) == "premium_required":
                return await ctx.warn("This is a **premium** command! Do `;premium` to see how to **buy** it.")
            return
        
        elif isinstance(error, commands.MissingPermissions):
            missing_perms = ', '.join([perm.replace('_', ' ').title() for perm in error.missing_permissions])
            return await ctx.warn(f'You are missing permission(s): `{missing_perms}`')
        
        elif isinstance(error, commands.BotMissingPermissions):
            missing_perms = ', '.join([perm.replace('_', ' ').title() for perm in error.missing_permissions])
            return await ctx.warn(f'I am missing permission(s): `{missing_perms}`')
        
        elif isinstance(error, commands.MissingRequiredArgument):
            return await ctx.warn(f'Missing required argument: **{error.param.name}**')
        
        elif isinstance(error, commands.BadArgument):
            return await ctx.warn(f'Invalid argument provided')
        
        elif isinstance(error, commands.CommandOnCooldown):
            return await ctx.warn(f'This command is on cooldown. Try again in **{error.retry_after:.1f}s**')
        
        elif isinstance(error, commands.NotOwner):
            return await ctx.deny('This command is owner-only')
        
        elif isinstance(error, commands.NSFWChannelRequired):
            return await ctx.warn('This command can only be used in **NSFW** channels')
        
        elif isinstance(error, commands.CommandNotFound):
            return
        
        else:
            print(f'Ignoring exception in command {ctx.command}:')
            print(f'{type(error).__name__}: {error}')
    
    async def load_cogs(self):
        """Automatically load all cogs from the plugins directory"""
        plugins_path = Path(__file__).parent.parent / 'plugins'
        
        if not plugins_path.exists():
            print("⚠️  Plugins directory not found!")
            return
        
        loaded = 0
        failed = 0
        
        # Load plugins from main plugins directory
        for file in plugins_path.glob('*.py'):
            if file.name.startswith('_'):
                continue
                
            cog_name = f'stare.plugins.{file.stem}'
            try:
                await self.load_extension(cog_name)
                print(f"✅ Loaded {cog_name}")
                loaded += 1
            except Exception as e:
                print(f"❌ Failed to load {cog_name}: {e}")
                failed += 1
        
        # Load plugins from subdirectories
        for subfolder in plugins_path.iterdir():
            if subfolder.is_dir() and not subfolder.name.startswith('_'):
                for file in subfolder.glob('*.py'):
                    if file.name.startswith('_'):
                        continue
                    
                    cog_name = f'stare.plugins.{subfolder.name}.{file.stem}'
                    try:
                        await self.load_extension(cog_name)
                        print(f"✅ Loaded {cog_name}")
                        loaded += 1
                    except Exception as e:
                        print(f"❌ Failed to load {cog_name}: {e}")
                        failed += 1
        
        print(f"\n📦 Cogs loaded: {loaded} | Failed: {failed}")

bot = StareBot()

def run():
    """Run the bot"""
    bot.run(Config.BOT_TOKEN)
