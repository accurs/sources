import asyncio
import discord
from discord.ext import commands, tasks

from heist.framework.discord.context import Context
from .models import AutoPFPConfig
from .pinterest import PinterestScraper

class AutoPFP(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = AutoPFPConfig(bot.pool)
        self.scraper = PinterestScraper(self.config)
        self.autopfp_task.start()

    async def cog_load(self):
        await self.config.setup_tables()

    def cog_unload(self):
        self.autopfp_task.cancel()
        asyncio.create_task(self.scraper.close())

    @tasks.loop(minutes=1)
    async def autopfp_task(self):
        try:
            configs = await self.config.get_active_configs()
            
            for config_data in configs:
                try:
                    guild = self.bot.get_guild(config_data['guild_id'])
                    if not guild:
                        continue
                    
                    keyword = config_data['keyword']
                    image_url = await self.scraper.get_next_image(
                        config_data['guild_id'], 
                        config_data['user_id'], 
                        keyword
                    )
                    
                    if image_url:
                        channels = config_data.get('channels', [])
                        
                        if channels:
                            for channel_id in channels:
                                channel = guild.get_channel(channel_id)
                                if channel and isinstance(channel, discord.TextChannel):
                                    if not channel.permissions_for(guild.me).send_messages:
                                        continue
                                    try:
                                        embed = discord.Embed(color=0xd3d6f1)
                                        embed.set_image(url=image_url)
                                        embed.set_footer(text=f"AutoPFP • {keyword}")
                                        await channel.send(embed=embed)
                                        
                                        await self.config.add_used_image(
                                            config_data['guild_id'], 
                                            config_data['user_id'], 
                                            keyword,
                                            image_url
                                        )
                                        break
                                    except Exception as e:
                                        continue
                        else:
                            for channel in guild.text_channels:
                                if not channel.permissions_for(guild.me).send_messages:
                                    continue
                                try:
                                    embed = discord.Embed(color=0xd3d6f1)
                                    embed.set_image(url=image_url)
                                    embed.set_footer(text=f"AutoPFP • {keyword}")
                                    await channel.send(embed=embed)
                                    
                                    await self.config.add_used_image(
                                        config_data['guild_id'], 
                                        config_data['user_id'], 
                                        keyword,
                                        image_url
                                    )
                                    break
                                except Exception as e:
                                    continue
                    
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    continue
            
        except Exception as e:
            pass

    @autopfp_task.before_loop
    async def before_autopfp_task(self):
        await self.bot.wait_until_ready()

    @commands.group(name="autopfp", aliases=["apfp"], invoke_without_command=True)
    async def autopfp(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @autopfp.command(name="setup")
    @commands.has_permissions(manage_channels=True)
    async def autopfp_setup(self, ctx: Context, *keywords):
        if not keywords:
            return await ctx.deny("Provide keywords for image search")
        
        added = []
        for keyword in keywords:
            success = await self.config.add_config(
                ctx.guild.id, ctx.author.id, keyword
            )
            if success:
                added.append(keyword)
        
        if added:
            await ctx.approve(f"AutoPFP setup with keywords: {', '.join(added)}")
        else:
            await ctx.deny("Failed to setup AutoPFP")

    @autopfp.command(name="channels")
    @commands.has_permissions(manage_channels=True)
    async def autopfp_channels(self, ctx: Context, keyword: str, *channels: discord.TextChannel):
        config_data = await self.config.get_config(ctx.guild.id, ctx.author.id, keyword)
        if not config_data:
            return await ctx.deny(f"No AutoPFP configuration found for keyword '{keyword}'")
        
        channel_ids = [c.id for c in channels] if channels else []
        
        success = await self.config.add_config(
            ctx.guild.id, ctx.author.id, keyword, channel_ids
        )
        
        if success:
            if channels:
                channel_mentions = ', '.join(c.mention for c in channels)
                await ctx.approve(f"AutoPFP for '{keyword}' will send images to: {channel_mentions}")
            else:
                await ctx.approve(f"AutoPFP for '{keyword}' will send images to any available channel")
        else:
            await ctx.deny("Failed to update channels")

    @autopfp.command(name="toggle")
    @commands.has_permissions(manage_channels=True)
    async def autopfp_toggle(self, ctx: Context, keyword: str):
        enabled = await self.config.toggle_config(ctx.guild.id, ctx.author.id, keyword)
        
        if enabled is None:
            await ctx.deny(f"No AutoPFP configuration found for keyword '{keyword}'")
        elif enabled:
            await ctx.approve(f"AutoPFP for '{keyword}' enabled")
        else:
            await ctx.warn(f"AutoPFP for '{keyword}' disabled")

    @autopfp.command(name="remove")
    @commands.has_permissions(manage_channels=True)
    async def autopfp_remove(self, ctx: Context, keyword: str = None):
        success = await self.config.remove_config(ctx.guild.id, ctx.author.id, keyword)
        
        if success:
            await self.config.reset_pagination(ctx.guild.id, ctx.author.id, keyword)
            if keyword:
                await ctx.approve(f"AutoPFP configuration for '{keyword}' removed")
            else:
                await ctx.approve("All AutoPFP configurations removed")
        else:
            await ctx.deny("No AutoPFP configuration found")

    @autopfp.command(name="status")
    async def autopfp_status(self, ctx: Context):
        configs = await self.bot.pool.fetch("""
            SELECT * FROM autopfp.config WHERE guild_id = $1
        """, ctx.guild.id)
        
        if not configs:
            return await ctx.deny("No AutoPFP configurations found")
        
        embed = discord.Embed(
            title="AutoPFP Status",
            color=ctx.config.colors.neutral
        )
        
        user_configs = {}
        for config in configs:
            user = ctx.guild.get_member(config['user_id'])
            if not user:
                continue
            
            if user.id not in user_configs:
                user_configs[user.id] = {'user': user, 'keywords': []}
            
            enabled = f"{ctx.config.emojis.context.approve}" if config['enabled'] else f"{ctx.config.emojis.context.deny}"
            channels = config.get('channels', [])
            if channels:
                channel_mentions = ', '.join(f"<#{c}>" for c in channels)
            else:
                channel_mentions = "Any available channel"
            
            user_configs[user.id]['keywords'].append({
                'keyword': config['keyword'],
                'enabled': enabled,
                'channels': channel_mentions
            })
        
        for user_data in user_configs.values():
            user = user_data['user']
            keywords_info = []
            for kw in user_data['keywords']:
                keywords_info.append(f"{kw['enabled']} **{kw['keyword']}** → {kw['channels']}")
            
            embed.add_field(
                name=f"{user.display_name}",
                value="\n".join(keywords_info),
                inline=False
            )
        
        await ctx.send(embed=embed)

    @autopfp.command(name="clear")
    @commands.has_permissions(manage_channels=True)
    async def autopfp_clear(self, ctx: Context, keyword: str = None):
        if keyword:
            await self.bot.pool.execute("""
                DELETE FROM autopfp.used_images 
                WHERE guild_id = $1 AND user_id = $2 AND keyword = $3
            """, ctx.guild.id, ctx.author.id, keyword)
            await self.config.reset_pagination(ctx.guild.id, ctx.author.id, keyword)
            await ctx.approve(f"Reset pagination for '{keyword}'")
        else:
            await self.bot.pool.execute("""
                DELETE FROM autopfp.used_images 
                WHERE guild_id = $1 AND user_id = $2
            """, ctx.guild.id, ctx.author.id)
            await self.config.reset_pagination(ctx.guild.id, ctx.author.id)
            await ctx.approve("Reset all pagination")

    @autopfp.command(name="test")
    @commands.has_permissions(manage_channels=True)
    async def autopfp_test(self, ctx: Context, keyword: str):
        config_data = await self.config.get_config(ctx.guild.id, ctx.author.id, keyword)
        
        if not config_data:
            return await ctx.deny(f"No AutoPFP configuration found for keyword '{keyword}'")
        
        try:
            pagination = await self.config.get_pagination(ctx.guild.id, ctx.author.id, keyword)
            page_num = pagination['page_number'] if pagination else 0
            
            used_count = await self.bot.pool.fetchval(
                "SELECT COUNT(*) FROM autopfp.used_images WHERE guild_id = $1 AND user_id = $2 AND keyword = $3",
                ctx.guild.id, ctx.author.id, keyword
            )
            
            await ctx.neutral(f"Page: {page_num}, Used: {used_count}")
            
            image_url = await self.scraper.get_next_image(ctx.guild.id, ctx.author.id, keyword)
            
            if image_url:
                embed = discord.Embed(color=ctx.config.colors.approve)
                embed.set_image(url=image_url)
                embed.set_footer(text=f"Test Image • {keyword} • Page: {page_num}")
                await ctx.send(embed=embed)
                
                await self.config.add_used_image(ctx.guild.id, ctx.author.id, keyword, image_url)
            else:
                await ctx.deny(f"No more images for '{keyword}'")
                
        except Exception as e:
            await ctx.deny(f"Error: {str(e)}")

    @autopfp.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def autopfp_reset(self, ctx: Context):
        await ctx.prompt("Are you sure you want to **reset** all AutoPFP configurations?")
        
        await self.bot.pool.execute("""
            DELETE FROM autopfp.config WHERE guild_id = $1
        """, ctx.guild.id)
        
        await self.bot.pool.execute("""
            DELETE FROM autopfp.used_images WHERE guild_id = $1
        """, ctx.guild.id)
        
        await self.bot.pool.execute("""
            DELETE FROM autopfp.pagination WHERE guild_id = $1
        """, ctx.guild.id)
        
        await ctx.approve("Reset all AutoPFP configurations and cleared image history")

async def setup(bot):
    await bot.add_cog(AutoPFP(bot))