import discord
import asyncio
from typing import Union
from discord.ext import commands
from stare.core.config import Config
from stare.core.tools.context import CustomContext as Context
from stare.core.tools.paginator import PaginatorView


class SupportModal(discord.ui.Modal, title="Support Request"):
    """Modal for submitting support requests"""
    
    problem = discord.ui.TextInput(
        label="Describe your problem",
        placeholder="Please describe your issue in detail...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )
    
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle support request submission"""
        # Get support category ID from config
        support_category_id = getattr(Config, 'SUPPORT_CATEGORY_ID', None)
        
        if not support_category_id:
            return await interaction.response.send_message(
                "Support category not configured. Please contact the bot owner.",
                ephemeral=True
            )
        
        category = self.bot.get_channel(support_category_id)
        if not category:
            return await interaction.response.send_message(
                "Support category not found. Please contact the bot owner.",
                ephemeral=True
            )
        
        # Create a new channel for this ticket
        channel_name = f"support-{interaction.user.name}".lower()
        support_channel = await category.create_text_channel(
            name=channel_name,
            topic=f"Support ticket for {interaction.user} ({interaction.user.id})"
        )
        
        # Create support ticket embed
        embed = discord.Embed(
            title="New Support Request",
            description=self.problem.value,
            color=0x35578E,
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(
            name=f"{interaction.user} ({interaction.user.id})",
            icon_url=interaction.user.display_avatar.url
        )
        embed.set_footer(text=f"User ID: {interaction.user.id}")
        
        # Send to support channel
        msg = await support_channel.send(embed=embed)
        
        # Store ticket in database
        await self.bot.db_pool.execute(
            """INSERT INTO support_tickets (user_id, message_id, channel_id, problem, status)
               VALUES ($1, $2, $3, $4, $5)""",
            interaction.user.id, msg.id, support_channel.id, self.problem.value, 'open'
        )
        
        await interaction.response.send_message(
            f"Your support request has been submitted in {support_channel.mention}! A bot owner will respond soon.",
            ephemeral=True
        )


class Owner(commands.Cog):
    """Owner-only commands for bot management"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def cog_load(self):
        """Create blacklist and support tables"""
        if not hasattr(self.bot, 'db_pool') or not self.bot.db_pool:
            return
        
        try:
            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS blacklist_user (
                    user_id BIGINT PRIMARY KEY
                )
            """)
            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS blacklist_guild (
                    guild_id BIGINT PRIMARY KEY
                )
            """)
            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    message_id BIGINT NOT NULL,
                    channel_id BIGINT NOT NULL,
                    problem TEXT NOT NULL,
                    status TEXT DEFAULT 'open',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            print("✅ Blacklist and support tables created/verified")
        except Exception as e:
            print(f"❌ Error creating tables: {e}")
    
    @commands.command()
    @commands.is_owner()
    async def closeticket(self, ctx: Context):
        """Close a support ticket channel"""
        if not ctx.channel.name.startswith('support-'):
            return await ctx.warn("This command can only be used in support ticket channels")
        
        # Update ticket status in database
        await self.bot.db_pool.execute(
            "UPDATE support_tickets SET status = 'closed' WHERE channel_id = $1",
            ctx.channel.id
        )
        
        await ctx.approve("Closing this support ticket in 5 seconds...")
        await asyncio.sleep(5)
        await ctx.channel.delete(reason="Support ticket closed")
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for messages in support ticket channels and DMs"""
        if message.author.bot:
            return
        
        # Check if database is available
        if not hasattr(self.bot, 'db_pool') or not self.bot.db_pool:
            return
        
        # Handle DM messages from users with open tickets
        if isinstance(message.channel, discord.DMChannel):
            try:
                # Check if user has an open ticket - get the most recent one
                ticket = await self.bot.db_pool.fetchrow(
                    "SELECT * FROM support_tickets WHERE user_id = $1 AND status = 'open' ORDER BY created_at DESC LIMIT 1",
                    message.author.id
                )
                
                if not ticket:
                    print(f"No open ticket found for user {message.author.id}")
                    return
                
                # Get the support channel
                support_channel = self.bot.get_channel(ticket['channel_id'])
                if not support_channel:
                    print(f"Support channel {ticket['channel_id']} not found")
                    return
                
                print(f"Forwarding DM from {message.author} to channel {support_channel.name} (ID: {support_channel.id})")
                
                # Send user's message to support channel
                embed = discord.Embed(
                    description=message.content,
                    color=0x35578E,
                    timestamp=discord.utils.utcnow()
                )
                embed.set_author(
                    name=f"{message.author}",
                    icon_url=message.author.display_avatar.url
                )
                
                await support_channel.send(embed=embed)
                await message.add_reaction("✅")
                print(f"Successfully forwarded DM to {support_channel.name}")
            except Exception as e:
                print(f"Error forwarding DM: {e}")
                import traceback
                traceback.print_exc()
            return
        
        # Handle messages in support ticket channels
        if not isinstance(message.channel, discord.TextChannel):
            return
            
        if not message.channel.name.startswith('support-'):
            return
        
        try:
            # Get the ticket from database
            ticket = await self.bot.db_pool.fetchrow(
                "SELECT * FROM support_tickets WHERE channel_id = $1",
                message.channel.id
            )
            
            if not ticket:
                print(f"No ticket found for channel {message.channel.id}")
                return
            
            # If message is from the ticket owner, don't forward (they're already in the channel)
            if message.author.id == ticket['user_id']:
                return
            
            # If message is from someone else (bot owner), send to user via DM
            print(f"Sending DM to user {ticket['user_id']}")
            user = await self.bot.fetch_user(ticket['user_id'])
            embed = discord.Embed(
                title="Support Response",
                description=message.content,
                color=0x35578E,
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(
                name=f"{message.author} (Bot Owner)",
                icon_url=message.author.display_avatar.url
            )
            embed.set_footer(text="Reply to this DM to continue the conversation")
            
            await user.send(embed=embed)
            await message.add_reaction("✅")
            print(f"DM sent successfully to {user}")
        except Exception as e:
            print(f"Error in support listener: {e}")
            await message.channel.send(f"Failed to send DM to user: {e}")
    
    @commands.group(invoke_without_command=True, aliases=['bl'])
    @commands.is_owner()
    async def blacklist(self, ctx: Context):
        """Manage blacklisted users and guilds"""
        await ctx.send_help(ctx.command)
    
    @blacklist.command(name='guild')
    @commands.is_owner()
    async def blacklist_guild(self, ctx: Context, guild_id: int):
        """Blacklist a guild from using the bot"""
        await self.bot.db_pool.execute(
            "INSERT INTO blacklist_guild (guild_id) VALUES ($1) ON CONFLICT DO NOTHING",
            guild_id
        )
        await ctx.approve(f"Blacklisted guild **{guild_id}**")
    
    @blacklist.command(name='user')
    @commands.is_owner()
    async def blacklist_user(self, ctx: Context, *, user: str):
        """Blacklist a user from using the bot"""
        # Try to convert to user/member first
        try:
            converted_user = await commands.UserConverter().convert(ctx, user)
            user_id = converted_user.id
            user_display = str(converted_user)
        except:
            # Try as user ID
            try:
                user_id = int(user)
                user_display = f"User ID {user_id}"
            except:
                return await ctx.warn("Invalid user. Provide a mention, ID, or username.")
        
        await self.bot.db_pool.execute(
            "INSERT INTO blacklist_user (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
            user_id
        )
        await ctx.approve(f"Blacklisted **{user_display}**")
    
    @blacklist.command(name='remove')
    @commands.is_owner()
    async def blacklist_remove(self, ctx: Context, type: str, target: Union[int, discord.User, discord.Member]):
        """Remove a user or guild from the blacklist"""
        if type.lower() in ['guild', 'server']:
            if not isinstance(target, int):
                return await ctx.warn("Guild ID must be a number")
            
            result = await self.bot.db_pool.execute(
                "DELETE FROM blacklist_guild WHERE guild_id = $1",
                target
            )
            
            if result == "DELETE 0":
                await ctx.warn(f"Guild **{target}** is not blacklisted")
            else:
                await ctx.approve(f"Removed guild **{target}** from blacklist")
        
        elif type.lower() == 'user':
            user_id = target.id if isinstance(target, (discord.User, discord.Member)) else target
            user_obj = target if isinstance(target, (discord.User, discord.Member)) else None
            
            result = await self.bot.db_pool.execute(
                "DELETE FROM blacklist_user WHERE user_id = $1",
                user_id
            )
            
            if result == "DELETE 0":
                user_display = str(user_obj) if user_obj else f"**{user_id}**"
                await ctx.warn(f"User {user_display} is not blacklisted")
            else:
                user_display = str(user_obj) if user_obj else f"**{user_id}**"
                await ctx.approve(f"Removed {user_display} from blacklist")
        else:
            await ctx.warn("Invalid type. Use `user` or `guild`")
    
    @commands.group(invoke_without_command=True, aliases=['ubl'])
    @commands.is_owner()
    async def unblacklist(self, ctx: Context):
        """Remove users or guilds from the blacklist"""
        await ctx.send_help(ctx.command)
    
    @unblacklist.command(name='user')
    @commands.is_owner()
    async def unblacklist_user(self, ctx: Context, *, user: str):
        """Remove a user from the blacklist"""
        # Try to convert to user/member first
        try:
            converted_user = await commands.UserConverter().convert(ctx, user)
            user_id = converted_user.id
            user_display = str(converted_user)
        except:
            # Try as user ID
            try:
                user_id = int(user)
                user_display = f"User ID {user_id}"
            except:
                return await ctx.warn("Invalid user. Provide a mention, ID, or username.")
        
        result = await self.bot.db_pool.execute(
            "DELETE FROM blacklist_user WHERE user_id = $1",
            user_id
        )
        
        if result == "DELETE 0":
            await ctx.warn(f"{user_display} is not blacklisted")
        else:
            await ctx.approve(f"Removed **{user_display}** from blacklist")
    
    @unblacklist.command(name='guild')
    @commands.is_owner()
    async def unblacklist_guild(self, ctx: Context, guild_id: int):
        """Remove a guild from the blacklist"""
        result = await self.bot.db_pool.execute(
            "DELETE FROM blacklist_guild WHERE guild_id = $1",
            guild_id
        )
        
        if result == "DELETE 0":
            await ctx.warn(f"Guild **{guild_id}** is not blacklisted")
        else:
            await ctx.approve(f"Removed guild **{guild_id}** from blacklist")
    
    @commands.group(invoke_without_command=True, aliases=['db'])
    @commands.is_owner()
    async def database(self, ctx: Context):
        """Manage database tables and schema"""
        await ctx.send_help(ctx.command)
    
    @database.command(name='tables')
    @commands.is_owner()
    async def database_tables(self, ctx: Context):
        """List all tables in the database"""
        tables = await self.bot.db_pool.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        
        if not tables:
            return await ctx.warn("No tables found")
        
        embed = discord.Embed(
            description="\n".join([f"`{table['table_name']}`" for table in tables]),
            color=Config.COLORS.DEFAULT
        )
        await ctx.send(embed=embed)
    
    @database.command(name='schema')
    @commands.is_owner()
    async def database_schema(self, ctx: Context, table: str):
        """View the schema of a table"""
        columns = await self.bot.db_pool.fetch(
            "SELECT column_name, data_type, character_maximum_length FROM information_schema.columns WHERE table_name = $1",
            table
        )
        
        if not columns:
            return await ctx.warn(f"Table `{table}` not found")
        
        embed = discord.Embed(
            title=f"Schema: {table}",
            description="\n".join([
                f"`{col['column_name']}` - {col['data_type']}" + 
                (f"({col['character_maximum_length']})" if col['character_maximum_length'] else "")
                for col in columns
            ]),
            color=Config.COLORS.DEFAULT
        )
        await ctx.send(embed=embed)
    
    @database.command(name='query')
    @commands.is_owner()
    async def database_query(self, ctx: Context, *, query: str):
        """Execute a SQL query"""
        try:
            if query.strip().upper().startswith('SELECT'):
                results = await self.bot.db_pool.fetch(query)
                
                if not results:
                    return await ctx.approve("Query executed successfully (no results)")
                
                embeds = []
                for i in range(0, len(results), 10):
                    chunk = results[i:i+10]
                    description = ""
                    
                    for row in chunk:
                        description += "```\n"
                        for key, value in dict(row).items():
                            description += f"{key}: {value}\n"
                        description += "```\n"
                    
                    embed = discord.Embed(
                        title=f"Query Results",
                        description=description,
                        color=Config.COLORS.DEFAULT
                    )
                    embeds.append(embed)
                
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    view = PaginatorView(embeds, user=ctx.author)
                    await ctx.send(embed=embeds[0], view=view)
            else:
                await self.bot.db_pool.execute(query)
                await ctx.approve("Query executed successfully")
        except Exception as e:
            await ctx.warn(f"Query failed: {str(e)}")
    
    @database.command(name='create')
    @commands.is_owner()
    async def database_create(self, ctx: Context, table: str, *, schema: str):
        """Create a new table"""
        try:
            await self.bot.db_pool.execute(f"CREATE TABLE {table} ({schema})")
            await ctx.approve(f"Created table `{table}`")
        except Exception as e:
            await ctx.warn(f"Failed to create table: {str(e)}")
    
    @database.command(name='drop')
    @commands.is_owner()
    async def database_drop(self, ctx: Context, table: str):
        """Drop a table"""
        try:
            await self.bot.db_pool.execute(f"DROP TABLE {table}")
            await ctx.approve(f"Dropped table `{table}`")
        except Exception as e:
            await ctx.warn(f"Failed to drop table: {str(e)}")
    
    @database.command(name='addcolumn')
    @commands.is_owner()
    async def database_addcolumn(self, ctx: Context, table: str, column: str, datatype: str):
        """Add a column to a table"""
        try:
            await self.bot.db_pool.execute(f"ALTER TABLE {table} ADD COLUMN {column} {datatype}")
            await ctx.approve(f"Added column `{column}` to `{table}`")
        except Exception as e:
            await ctx.warn(f"Failed to add column: {str(e)}")
    
    @database.command(name='dropcolumn')
    @commands.is_owner()
    async def database_dropcolumn(self, ctx: Context, table: str, column: str):
        """Drop a column from a table"""
        try:
            await self.bot.db_pool.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
            await ctx.approve(f"Dropped column `{column}` from `{table}`")
        except Exception as e:
            await ctx.warn(f"Failed to drop column: {str(e)}")
    
    @database.command(name='truncate')
    @commands.is_owner()
    async def database_truncate(self, ctx: Context, table: str):
        """Delete all rows from a table"""
        try:
            await self.bot.db_pool.execute(f"TRUNCATE TABLE {table}")
            await ctx.approve(f"Truncated table `{table}`")
        except Exception as e:
            await ctx.warn(f"Failed to truncate table: {str(e)}")


async def setup(bot):
    await bot.add_cog(Owner(bot))
