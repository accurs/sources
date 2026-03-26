import discord
from discord.ext import commands
from datetime import datetime
from typing import Optional
from maniac.core.config import Config
from maniac.core.command_example import example

class Case:
    def __init__(self, bot, case_id: int, guild_id: int, target_id: int, moderator_id: int, 
                 action: str, reason: str, created_at: datetime):
        self.bot = bot
        self.id = case_id
        self.guild_id = guild_id
        self.target_id = target_id
        self.moderator_id = moderator_id
        self.action = action
        self.reason = reason
        self.created_at = created_at
    
    async def to_embed(self):
        guild = self.bot.get_guild(self.guild_id)
        target = await self.bot.fetch_user(self.target_id)
        moderator = await self.bot.fetch_user(self.moderator_id)
        
        embed = discord.Embed(
            title=f"Case #{self.id}",
            color=Config.COLORS.DEFAULT,
            timestamp=self.created_at
        )
        
        embed.add_field(name="Action", value=self.action.title(), inline=True)
        embed.add_field(name="Target", value=f"{target.mention} (`{target.id}`)", inline=True)
        embed.add_field(name="Moderator", value=f"{moderator.mention} (`{moderator.id}`)", inline=True)
        embed.add_field(name="Reason", value=self.reason, inline=False)
        
        return embed
    
    @classmethod
    async def create(cls, ctx, target: discord.User | discord.Member, action: str, reason: str):
        from maniac.core.database import db
        
        created_at = datetime.utcnow()
        
        try:
            last_case = await db.moderation_cases.find_one(
                {"guild_id": ctx.guild.id},
                sort=[("case_id", -1)]
            )
            case_id = (last_case["case_id"] + 1) if last_case else 1
            
            await db.moderation_cases.insert_one({
                "guild_id": ctx.guild.id,
                "case_id": case_id,
                "target_id": target.id,
                "moderator_id": ctx.author.id,
                "action": action,
                "reason": reason,
                "created_at": created_at
            })
            
            return cls(ctx.bot, case_id, ctx.guild.id, target.id, ctx.author.id, action, reason, created_at)
        except:
            return None

class History(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.group(invoke_without_command=True)
    @example(",case 5")
    @commands.has_permissions(manage_messages=True)
    async def case(self, ctx, case_id: int = None):
        if ctx.invoked_subcommand is not None:
            return
        
        if not case_id:
            return
        
        from maniac.core.database import db
        
        try:
            record = await db.moderation_cases.find_one({
                "guild_id": ctx.guild.id,
                "case_id": case_id
            })
            
            if not record:
                return await ctx.deny(f"Case with ID #{case_id} doesn't exist")
            
            case = Case(
                self.bot,
                record['case_id'],
                record['guild_id'],
                record['target_id'],
                record['moderator_id'],
                record['action'],
                record['reason'],
                record['created_at']
            )
            
            embed = await case.to_embed()
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.deny(f"Failed to fetch case: {str(e)}")
    
    @case.command(name="delete")
    @commands.has_permissions(manage_messages=True)
    async def case_delete(self, ctx, case_id: int):
        from maniac.core.database import db
        
        try:
            result = await db.moderation_cases.delete_one({
                "guild_id": ctx.guild.id,
                "case_id": case_id
            })
            
            if result.deleted_count == 0:
                return await ctx.deny(f"Case with ID #{case_id} doesn't exist")
            
            await ctx.approve(f"Successfully deleted case #{case_id}")
        except Exception as e:
            await ctx.deny(f"Failed to delete case: {str(e)}")
    
    @commands.command()
    @example(",history @offermillions")
    @commands.has_permissions(manage_messages=True)
    async def history(self, ctx, user: discord.User):
        from maniac.core.database import db
        
        try:
            records = await db.moderation_cases.find({
                "guild_id": ctx.guild.id,
                "target_id": user.id
            }).sort("created_at", -1).to_list(length=100)
            
            if not records:
                return await ctx.deny(f"{user.mention} has no moderation history")
            
            embed = discord.Embed(
                title=f"Moderation History for {user}",
                color=Config.COLORS.DEFAULT
            )
            
            description = []
            for record in records[:10]:
                description.append(
                    f"**Case #{record['case_id']}** - {record['action'].title()}\n"
                    f"Reason: {record['reason']}\n"
                    f"<t:{int(record['created_at'].timestamp())}:R>"
                )
            
            embed.description = "\n\n".join(description)
            
            if len(records) > 10:
                embed.set_footer(text=f"Showing 10 of {len(records)} cases")
            
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.deny(f"Failed to fetch history: {str(e)}")
    
    @commands.command()
    @example(",clearhistory @offermillions")
    @commands.has_permissions(administrator=True)
    async def clearhistory(self, ctx, user: discord.User):
        from maniac.core.database import db
        
        try:
            result = await db.moderation_cases.delete_many({
                "guild_id": ctx.guild.id,
                "target_id": user.id
            })
            
            if result.deleted_count == 0:
                return await ctx.deny(f"{user.mention} has no moderation history")
            
            await ctx.approve(f"Successfully cleared {result.deleted_count} case(s) for {user.mention}")
        except Exception as e:
            await ctx.deny(f"Failed to clear history: {str(e)}")

async def setup(bot):
    await bot.add_cog(History(bot))
