import math
import random
import discord
from discord.ext import commands
from datetime import datetime, timezone

class LevelEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        config = await self.bot.pool.fetchrow(
            "SELECT * FROM level.config WHERE guild_id = $1", message.guild.id
        )
        if not config or not config['status']:
            return

        member_data = await self.bot.pool.fetchrow(
            "SELECT * FROM level.member WHERE guild_id = $1 AND user_id = $2",
            message.guild.id, message.author.id
        )

        now = datetime.now(timezone.utc)
        
        if member_data:
            time_diff = (now - member_data['last_message']).total_seconds()
            if time_diff < config['cooldown']:
                return
        
        xp_gain = random.randint(config['xp_min'], config['xp_max'])
        
        if config['effort_status']:
            if len(message.content) >= config['effort_text']:
                xp_gain += 5
            if message.attachments:
                xp_gain += config['effort_image']
            if message.author.premium_since:
                xp_gain += config['effort_booster']

        xp_gain = int(xp_gain * config['xp_multiplier'])

        if not member_data:
            await self.bot.pool.execute(
                "INSERT INTO level.member (guild_id, user_id, xp, level, total_xp, last_message) VALUES ($1, $2, $3, $4, $5, $6)",
                message.guild.id, message.author.id, xp_gain, 0, xp_gain, now
            )
            current_xp = xp_gain
            current_level = 0
        else:
            current_xp = member_data['xp'] + xp_gain
            current_level = member_data['level']
            total_xp = member_data['total_xp'] + xp_gain
            
            await self.bot.pool.execute(
                "UPDATE level.member SET xp = $1, total_xp = $2, last_message = $3 WHERE guild_id = $4 AND user_id = $5",
                current_xp, total_xp, now, message.guild.id, message.author.id
            )

        xp_needed = math.floor(5 * math.sqrt(current_level + 1) + 50 * (current_level + 1) + 30)
        
        if current_xp >= xp_needed and (not config['max_level'] or current_level < config['max_level']):
            new_level = current_level + 1
            new_xp = current_xp - xp_needed
            
            await self.bot.pool.execute(
                "UPDATE level.member SET level = $1, xp = $2 WHERE guild_id = $3 AND user_id = $4",
                new_level, new_xp, message.guild.id, message.author.id
            )

            await self.handle_level_up(message, new_level)

    async def handle_level_up(self, message: discord.Message, new_level: int):
        notification = await self.bot.pool.fetchrow(
            "SELECT * FROM level.notification WHERE guild_id = $1", message.guild.id
        )
        
        level_roles = await self.bot.pool.fetch(
            "SELECT * FROM level.role WHERE guild_id = $1 AND level <= $2",
            message.guild.id, new_level
        )

        config = await self.bot.pool.fetchrow(
            "SELECT * FROM level.config WHERE guild_id = $1", message.guild.id
        )

        if level_roles:
            member = message.author
            if config['stack_roles']:
                roles_to_add = [message.guild.get_role(row['role_id']) for row in level_roles]
                roles_to_add = [role for role in roles_to_add if role and role not in member.roles]
                if roles_to_add:
                    try:
                        await member.add_roles(*roles_to_add, reason=f"Level {new_level} reward")
                    except:
                        pass
            else:
                highest_role_data = max(level_roles, key=lambda x: x['level'])
                highest_role = message.guild.get_role(highest_role_data['role_id'])
                if highest_role and highest_role not in member.roles:
                    current_level_roles = [message.guild.get_role(row['role_id']) for row in level_roles if message.guild.get_role(row['role_id']) in member.roles]
                    try:
                        if current_level_roles:
                            await member.remove_roles(*current_level_roles, reason="Level role update")
                        await member.add_roles(highest_role, reason=f"Level {new_level} reward")
                    except:
                        pass

        if not notification:
            return

        level_up_message = f"🎉 {message.author.mention} leveled up to **level {new_level}**!"

        if notification['template']:
            from heist.framework.script import Script
            
            member_data = await self.bot.pool.fetchrow(
                "SELECT * FROM level.member WHERE guild_id = $1 AND user_id = $2",
                message.guild.id, message.author.id
            )
            
            try:
                script = Script(
                    notification['template'],
                    [message.author, message.guild, ('level', new_level), ('xp', member_data['xp'] if member_data else 0), ('total_xp', member_data['total_xp'] if member_data else 0)]
                )
                
                if notification['dm']:
                    await script.send(message.author)
                elif notification['channel_id']:
                    channel = message.guild.get_channel(notification['channel_id'])
                    if channel:
                        await script.send(channel)
                else:
                    await script.send(message.channel)
                return
            except Exception as e:
                print(f"Script error: {e}")
                level_up_message = f"🎉 {message.author.mention} leveled up to **level {new_level}**!"

        if notification['dm']:
            try:
                await message.author.send(level_up_message)
            except:
                pass
        elif notification['channel_id']:
            channel = message.guild.get_channel(notification['channel_id'])
            if channel:
                try:
                    await channel.send(level_up_message)
                except:
                    pass
        else:
            try:
                await message.channel.send(level_up_message)
            except:
                pass