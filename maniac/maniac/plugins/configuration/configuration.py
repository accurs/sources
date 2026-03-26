import discord
from discord.ext import commands
from maniac.core.config import Config
from maniac.core.command_example import example

class Configuration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.Cog.listener("on_raw_reaction_add")
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member.bot:
            return
        
        from maniac.core.database import db
        
        reaction_role = await db.reaction_roles.find_one({
            "guild_id": payload.guild_id,
            "message_id": payload.message_id,
            "emoji": str(payload.emoji)
        })
        
        if not reaction_role:
            return
        
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        
        role = guild.get_role(reaction_role["role_id"])
        if not role:
            return
        
        try:
            await payload.member.add_roles(role, reason="Reaction role")
        except:
            pass
    
    @commands.Cog.listener("on_raw_reaction_remove")
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        from maniac.core.database import db
        
        reaction_role = await db.reaction_roles.find_one({
            "guild_id": payload.guild_id,
            "message_id": payload.message_id,
            "emoji": str(payload.emoji)
        })
        
        if not reaction_role:
            return
        
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return
        
        role = guild.get_role(reaction_role["role_id"])
        if not role:
            return
        
        try:
            await member.remove_roles(role, reason="Reaction role removed")
        except:
            pass
    
    @commands.group(name="reactionrole", aliases=["rr"], invoke_without_command=True, help="Manage reaction roles")
    @example(",reactionrole add 123456789 🎮 @Gamer")
    @commands.has_permissions(manage_roles=True)
    async def reactionrole(self, ctx):
        pass
    
    @reactionrole.command(name="add", help="Add a reaction role - Example: ,rr add 123456789 🎮 @Gamer")
    @commands.has_permissions(manage_roles=True)
    async def reactionrole_add(self, ctx, message_id: int, emoji: str, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot assign roles higher than or equal to my highest role")
        
        if role.managed:
            return await ctx.deny("I cannot assign managed roles (bot roles, booster roles, etc.)")
        
        try:
            message = await ctx.channel.fetch_message(message_id)
        except:
            return await ctx.deny("Message not found in this channel")
        
        try:
            await message.add_reaction(emoji)
        except:
            return await ctx.deny("Invalid emoji or I don't have access to that emoji")
        
        from maniac.core.database import db
        
        await db.reaction_roles.update_one(
            {
                "guild_id": ctx.guild.id,
                "message_id": message_id,
                "emoji": str(emoji)
            },
            {
                "$set": {
                    "role_id": role.id,
                    "channel_id": ctx.channel.id
                }
            },
            upsert=True
        )
        
        await ctx.approve(f"Successfully added reaction role {role.mention} for {emoji}")
    
    @reactionrole.command(name="remove", aliases=["delete"], help="Remove a reaction role - Example: ,rr remove 123456789 🎮")
    @commands.has_permissions(manage_roles=True)
    async def reactionrole_remove(self, ctx, message_id: int, emoji: str):
        from maniac.core.database import db
        
        result = await db.reaction_roles.delete_one({
            "guild_id": ctx.guild.id,
            "message_id": message_id,
            "emoji": str(emoji)
        })
        
        if result.deleted_count == 0:
            return await ctx.deny("No reaction role found for that message and emoji")
        
        try:
            message = await ctx.channel.fetch_message(message_id)
            await message.clear_reaction(emoji)
        except:
            pass
        
        await ctx.approve(f"Successfully removed reaction role for {emoji}")
    
    @reactionrole.command(name="list", help="List all reaction roles - Example: ,rr list")
    @commands.has_permissions(manage_roles=True)
    async def reactionrole_list(self, ctx):
        from maniac.core.database import db
        
        reaction_roles = await db.reaction_roles.find({
            "guild_id": ctx.guild.id
        }).to_list(length=None)
        
        if not reaction_roles:
            return await ctx.deny("No reaction roles set up in this server")
        
        embed = discord.Embed(
            title="Reaction Roles",
            color=Config.COLORS.DEFAULT
        )
        
        description = []
        for rr in reaction_roles[:25]:
            role = ctx.guild.get_role(rr["role_id"])
            role_text = role.mention if role else f"Deleted Role ({rr['role_id']})"
            channel = ctx.guild.get_channel(rr["channel_id"])
            channel_text = channel.mention if channel else f"Deleted Channel"
            
            description.append(
                f"**Message ID:** `{rr['message_id']}`\n"
                f"**Channel:** {channel_text}\n"
                f"**Emoji:** {rr['emoji']} → {role_text}\n"
            )
        
        embed.description = "\n".join(description)
        
        if len(reaction_roles) > 25:
            embed.set_footer(text=f"Showing 25 of {len(reaction_roles)} reaction roles")
        
        await ctx.send(embed=embed)
    
    @reactionrole.command(name="clear", help="Clear all reaction roles - Example: ,rr clear")
    @commands.has_permissions(administrator=True)
    async def reactionrole_clear(self, ctx):
        from maniac.core.database import db
        
        result = await db.reaction_roles.delete_many({
            "guild_id": ctx.guild.id
        })
        
        if result.deleted_count == 0:
            return await ctx.deny("No reaction roles to clear")
        
        await ctx.approve(f"Successfully cleared {result.deleted_count} reaction role(s)")

    @commands.group(name="starboard", aliases=["star"], invoke_without_command=True, help="Manage starboard system")
    @example(",starboard add #starboard 5 False")
    @commands.has_permissions(manage_guild=True)
    async def starboard(self, ctx):
        pass
    
    @starboard.command(name="add", help="Add a starboard channel - Example: ,starboard add #starboard 5 False")
    @commands.has_permissions(manage_guild=True)
    async def starboard_add(self, ctx, channel: discord.TextChannel, threshold: int = 3, self_star: bool = False):
        if threshold < 1:
            return await ctx.deny("Threshold must be at least 1")
        
        from maniac.core.database import db
        
        existing = await db.starboard.find_one({
            "guild_id": ctx.guild.id,
            "channel_id": channel.id
        })
        
        if existing:
            return await ctx.deny(f"{channel.mention} is already a starboard channel")
        
        await db.starboard.insert_one({
            "guild_id": ctx.guild.id,
            "channel_id": channel.id,
            "threshold": threshold,
            "self_star": self_star,
            "emoji": "⭐",
            "color": Config.COLORS.DEFAULT,
            "attachments": True
        })
        
        await ctx.approve(f"Starboard added in {channel.mention} with threshold {threshold} (self star: {self_star})")
    
    @starboard.command(name="remove", help="Remove a starboard channel")
    @commands.has_permissions(manage_guild=True)
    async def starboard_remove(self, ctx, channel: discord.TextChannel):
        from maniac.core.database import db
        
        result = await db.starboard.delete_one({
            "guild_id": ctx.guild.id,
            "channel_id": channel.id
        })
        
        if result.deleted_count == 0:
            return await ctx.deny(f"{channel.mention} is not a starboard channel")
        
        await ctx.approve(f"Starboard removed from {channel.mention}")
    
    @starboard.command(name="clear", help="Clear all starboards")
    @commands.has_permissions(administrator=True)
    async def starboard_clear(self, ctx):
        from maniac.core.database import db
        
        result = await db.starboard.delete_many({"guild_id": ctx.guild.id})
        
        if result.deleted_count == 0:
            return await ctx.deny("No starboards to clear")
        
        await ctx.approve(f"Successfully cleared {result.deleted_count} starboard(s)")
    
    @starboard.command(name="ignore", help="Ignore channels/roles/members from starboard")
    @commands.has_permissions(manage_guild=True)
    async def starboard_ignore(self, ctx, target: discord.TextChannel | discord.Role | discord.Member):
        from maniac.core.database import db
        
        target_type = "channel" if isinstance(target, discord.TextChannel) else "role" if isinstance(target, discord.Role) else "member"
        
        existing = await db.starboard_ignore.find_one({
            "guild_id": ctx.guild.id,
            "target_id": target.id,
            "target_type": target_type
        })
        
        if existing:
            return await ctx.deny(f"{target.mention} is already ignored")
        
        await db.starboard_ignore.insert_one({
            "guild_id": ctx.guild.id,
            "target_id": target.id,
            "target_type": target_type
        })
        
        await ctx.approve(f"Now ignoring {target.mention} from starboard")
    
    @starboard.command(name="unignore", help="Unignore channels/roles/members from starboard")
    @commands.has_permissions(manage_guild=True)
    async def starboard_unignore(self, ctx, target: discord.TextChannel | discord.Role | discord.Member):
        from maniac.core.database import db
        
        target_type = "channel" if isinstance(target, discord.TextChannel) else "role" if isinstance(target, discord.Role) else "member"
        
        result = await db.starboard_ignore.delete_one({
            "guild_id": ctx.guild.id,
            "target_id": target.id,
            "target_type": target_type
        })
        
        if result.deleted_count == 0:
            return await ctx.deny(f"{target.mention} is not ignored")
        
        await ctx.approve(f"No longer ignoring {target.mention} from starboard")
    
    @starboard.command(name="color", help="Set starboard embed color")
    @commands.has_permissions(manage_guild=True)
    async def starboard_color(self, ctx, channel: discord.TextChannel, color: str):
        try:
            color_int = int(color.replace("#", ""), 16)
        except:
            return await ctx.deny("Invalid color format. Use hex format like #FFAC33 or FFAC33")
        
        from maniac.core.database import db
        
        result = await db.starboard.update_one(
            {
                "guild_id": ctx.guild.id,
                "channel_id": channel.id
            },
            {"$set": {"color": color_int}}
        )
        
        if result.matched_count == 0:
            return await ctx.deny(f"{channel.mention} is not a starboard channel")
        
        await ctx.approve(f"Starboard color updated for {channel.mention}")
    
    @starboard.command(name="attachments", help="Toggle attachment inclusion in starboard")
    @commands.has_permissions(manage_guild=True)
    async def starboard_attachments(self, ctx, channel: discord.TextChannel, enabled: bool):
        from maniac.core.database import db
        
        result = await db.starboard.update_one(
            {
                "guild_id": ctx.guild.id,
                "channel_id": channel.id
            },
            {"$set": {"attachments": enabled}}
        )
        
        if result.matched_count == 0:
            return await ctx.deny(f"{channel.mention} is not a starboard channel")
        
        status = "enabled" if enabled else "disabled"
        await ctx.approve(f"Attachments {status} for {channel.mention}")
    
    @starboard.command(name="list", help="List all starboards")
    async def starboard_list(self, ctx):
        from maniac.core.database import db
        
        starboards = await db.starboard.find({"guild_id": ctx.guild.id}).to_list(length=None)
        
        if not starboards:
            return await ctx.deny("No starboards set up")
        
        embed = discord.Embed(
            title="Starboards",
            color=Config.COLORS.DEFAULT
        )
        
        description = []
        for sb in starboards:
            channel = ctx.guild.get_channel(sb["channel_id"])
            if not channel:
                continue
            
            description.append(
                f"**Channel:** {channel.mention}\n"
                f"**Threshold:** {sb['threshold']}\n"
                f"**Self Star:** {sb.get('self_star', False)}\n"
                f"**Attachments:** {sb.get('attachments', True)}\n"
            )
        
        embed.description = "\n".join(description) if description else "No active starboards"
        await ctx.send(embed=embed)

    @commands.Cog.listener("on_raw_reaction_add")
    async def starboard_reaction_handler(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        
        from maniac.core.database import db
        
        starboards = await db.starboard.find({"guild_id": payload.guild_id}).to_list(length=None)
        
        if not starboards:
            return
        
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        
        channel = guild.get_channel(payload.channel_id)
        if not channel:
            return
        
        ignored_channels = await db.starboard_ignore.find({
            "guild_id": guild.id,
            "target_type": "channel"
        }).to_list(length=None)
        
        if any(ig["target_id"] == channel.id for ig in ignored_channels):
            return
        
        try:
            message = await channel.fetch_message(payload.message_id)
        except:
            return
        
        if message.author.bot:
            return
        
        member = guild.get_member(payload.user_id)
        if not member:
            return
        
        ignored_members = await db.starboard_ignore.find({
            "guild_id": guild.id,
            "target_type": "member"
        }).to_list(length=None)
        
        if any(ig["target_id"] == message.author.id for ig in ignored_members):
            return
        
        ignored_roles = await db.starboard_ignore.find({
            "guild_id": guild.id,
            "target_type": "role"
        }).to_list(length=None)
        
        author_role_ids = [role.id for role in message.author.roles]
        if any(ig["target_id"] in author_role_ids for ig in ignored_roles):
            return
        
        if channel.is_nsfw():
            return
        
        for starboard in starboards:
            if str(payload.emoji) != starboard["emoji"]:
                continue
            
            if starboard["channel_id"] == channel.id:
                continue
            
            reaction = discord.utils.get(message.reactions, emoji=starboard["emoji"])
            if not reaction:
                continue
            
            if not starboard.get("self_star", False):
                users = [user async for user in reaction.users() if not user.bot and user.id != message.author.id]
                count = len(users)
            else:
                count = reaction.count - sum(1 async for user in reaction.users() if user.bot)
            
            if count < starboard["threshold"]:
                continue
            
            starboard_channel = guild.get_channel(starboard["channel_id"])
            if not starboard_channel:
                continue
            
            existing = await db.starboard_messages.find_one({
                "guild_id": guild.id,
                "message_id": message.id,
                "starboard_channel_id": starboard_channel.id
            })
            
            embed = discord.Embed(
                description=message.content[:2000] if message.content else None,
                color=starboard.get("color", Config.COLORS.DEFAULT),
                timestamp=message.created_at
            )
            embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
            embed.add_field(name="Source", value=f"[Jump to message]({message.jump_url})")
            
            if starboard.get("attachments", True) and message.attachments:
                embed.set_image(url=message.attachments[0].url)
            
            content = f"{starboard['emoji']} **{count}** {channel.mention}"
            
            if existing:
                try:
                    star_message = await starboard_channel.fetch_message(existing["star_message_id"])
                    await star_message.edit(content=content, embed=embed)
                except:
                    pass
            else:
                try:
                    star_message = await starboard_channel.send(content=content, embed=embed)
                    
                    await db.starboard_messages.insert_one({
                        "guild_id": guild.id,
                        "message_id": message.id,
                        "star_message_id": star_message.id,
                        "channel_id": channel.id,
                        "starboard_channel_id": starboard_channel.id
                    })
                except:
                    pass
    
    @commands.Cog.listener("on_raw_reaction_remove")
    async def starboard_reaction_remove_handler(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        
        from maniac.core.database import db
        
        starboards = await db.starboard.find({"guild_id": payload.guild_id}).to_list(length=None)
        
        if not starboards:
            return
        
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        
        channel = guild.get_channel(payload.channel_id)
        if not channel:
            return
        
        try:
            message = await channel.fetch_message(payload.message_id)
        except:
            return
        
        for starboard in starboards:
            if str(payload.emoji) != starboard["emoji"]:
                continue
            
            reaction = discord.utils.get(message.reactions, emoji=starboard["emoji"])
            
            if not starboard.get("self_star", False):
                users = [user async for user in reaction.users() if not user.bot and user.id != message.author.id] if reaction else []
                count = len(users)
            else:
                count = reaction.count - sum(1 async for user in reaction.users() if user.bot) if reaction else 0
            
            starboard_channel = guild.get_channel(starboard["channel_id"])
            if not starboard_channel:
                continue
            
            existing = await db.starboard_messages.find_one({
                "guild_id": guild.id,
                "message_id": message.id,
                "starboard_channel_id": starboard_channel.id
            })
            
            if not existing:
                continue
            
            if count < starboard["threshold"]:
                try:
                    star_message = await starboard_channel.fetch_message(existing["star_message_id"])
                    await star_message.delete()
                except:
                    pass
                
                await db.starboard_messages.delete_one({"_id": existing["_id"]})
            else:
                try:
                    star_message = await starboard_channel.fetch_message(existing["star_message_id"])
                    
                    embed = discord.Embed(
                        description=message.content[:2000] if message.content else None,
                        color=starboard.get("color", Config.COLORS.DEFAULT),
                        timestamp=message.created_at
                    )
                    embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
                    embed.add_field(name="Source", value=f"[Jump to message]({message.jump_url})")
                    
                    if starboard.get("attachments", True) and message.attachments:
                        embed.set_image(url=message.attachments[0].url)
                    
                    content = f"{starboard['emoji']} **{count}** {channel.mention}"
                    await star_message.edit(content=content, embed=embed)
                except:
                    pass
    
    @commands.Cog.listener("on_guild_channel_delete")
    async def starboard_channel_delete(self, channel: discord.TextChannel):
        from maniac.core.database import db
        
        await db.starboard.delete_many({
            "guild_id": channel.guild.id,
            "channel_id": channel.id
        })
        
        await db.starboard_messages.delete_many({
            "guild_id": channel.guild.id,
            "channel_id": channel.id
        })
    
    @commands.Cog.listener("on_raw_reaction_clear")
    async def starboard_reaction_clear(self, payload: discord.RawReactionClearEvent):
        if not payload.guild_id:
            return
        
        from maniac.core.database import db
        
        starboard_entries = await db.starboard_messages.find({
            "guild_id": payload.guild_id,
            "message_id": payload.message_id
        }).to_list(length=None)
        
        for entry in starboard_entries:
            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
                continue
            
            starboard_channel = guild.get_channel(entry["starboard_channel_id"])
            if not starboard_channel:
                continue
            
            try:
                star_message = await starboard_channel.fetch_message(entry["star_message_id"])
                await star_message.delete()
            except:
                pass
        
        await db.starboard_messages.delete_many({
            "guild_id": payload.guild_id,
            "message_id": payload.message_id
        })

    @commands.group(name="giveaway", aliases=["gw"], invoke_without_command=True, help="Manage giveaways")
    @example(",giveaway start 10m 1 Discord Nitro")
    @commands.has_permissions(manage_guild=True)
    async def giveaway(self, ctx):
        pass
    
    @example(",giveaway start 10m 1 Discord Nitro")
    @giveaway.command(name="start", help="Start a giveaway")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_start(self, ctx, duration: str, winners: int, *, prize: str):
        import re
        from datetime import datetime, timedelta, timezone
        
        time_regex = re.match(r"(\d+)([smhd])", duration.lower())
        if not time_regex:
            return await ctx.deny("Invalid duration format. Use: 10s, 5m, 2h, 1d")
        
        amount, unit = time_regex.groups()
        amount = int(amount)
        
        time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        seconds = amount * time_units[unit]
        
        if seconds < 10:
            return await ctx.deny("Giveaway duration must be at least 10 seconds")
        
        if winners < 1:
            return await ctx.deny("Must have at least 1 winner")
        
        end_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        
        embed = discord.Embed(
            title="🎉 GIVEAWAY 🎉",
            description=f"**Prize:** {prize}\n**Winners:** {winners}\n**Ends:** <t:{int(end_time.timestamp())}:R>\n\nReact with 🎉 to enter!",
            color=Config.COLORS.ERROR
        )
        embed.set_footer(text=f"Hosted by {ctx.author}")
        
        giveaway_msg = await ctx.send(embed=embed)
        await giveaway_msg.add_reaction("🎉")
        
        from maniac.core.database import db
        
        await db.giveaways.insert_one({
            "guild_id": ctx.guild.id,
            "channel_id": ctx.channel.id,
            "message_id": giveaway_msg.id,
            "host_id": ctx.author.id,
            "prize": prize,
            "winners": winners,
            "end_time": end_time,
            "ended": False
        })
        
        await ctx.message.add_reaction("✅")
    
    @giveaway.command(name="end", help="End a giveaway early")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_end(self, ctx, message_id: int):
        from maniac.core.database import db
        import random
        
        giveaway = await db.giveaways.find_one({
            "guild_id": ctx.guild.id,
            "message_id": message_id,
            "ended": False
        })
        
        if not giveaway:
            return await ctx.deny("Giveaway not found or already ended")
        
        try:
            channel = ctx.guild.get_channel(giveaway["channel_id"])
            message = await channel.fetch_message(message_id)
        except:
            return await ctx.deny("Failed to fetch giveaway message")
        
        reaction = discord.utils.get(message.reactions, emoji="🎉")
        if not reaction:
            return await ctx.deny("No entries found")
        
        users = [user async for user in reaction.users() if not user.bot]
        
        if len(users) < giveaway["winners"]:
            winners = users
        else:
            winners = random.sample(users, giveaway["winners"])
        
        if not winners:
            winner_text = "No valid entries"
        else:
            winner_text = ", ".join([winner.mention for winner in winners])
        
        embed = discord.Embed(
            title="🎉 GIVEAWAY ENDED 🎉",
            description=f"**Prize:** {giveaway['prize']}\n**Winners:** {winner_text}",
            color=Config.COLORS.SUCCESS
        )
        embed.set_footer(text=f"Hosted by {ctx.guild.get_member(giveaway['host_id'])}")
        
        await message.edit(embed=embed)
        
        if winners:
            await channel.send(f"Congratulations {winner_text}! You won **{giveaway['prize']}**!")
        
        await db.giveaways.update_one(
            {"_id": giveaway["_id"]},
            {"$set": {"ended": True}}
        )
        
        await ctx.approve("Giveaway ended successfully")
    
    @giveaway.command(name="reroll", help="Reroll giveaway winners")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_reroll(self, ctx, message_id: int):
        from maniac.core.database import db
        import random
        
        giveaway = await db.giveaways.find_one({
            "guild_id": ctx.guild.id,
            "message_id": message_id,
            "ended": True
        })
        
        if not giveaway:
            return await ctx.deny("Giveaway not found or not ended")
        
        try:
            channel = ctx.guild.get_channel(giveaway["channel_id"])
            message = await channel.fetch_message(message_id)
        except:
            return await ctx.deny("Failed to fetch giveaway message")
        
        reaction = discord.utils.get(message.reactions, emoji="🎉")
        if not reaction:
            return await ctx.deny("No entries found")
        
        users = [user async for user in reaction.users() if not user.bot]
        
        if len(users) < giveaway["winners"]:
            winners = users
        else:
            winners = random.sample(users, giveaway["winners"])
        
        if not winners:
            return await ctx.deny("No valid entries to reroll")
        
        winner_text = ", ".join([winner.mention for winner in winners])
        
        await channel.send(f"🎉 New winners: {winner_text}! You won **{giveaway['prize']}**!")
        await ctx.approve("Giveaway rerolled successfully")
    
    @giveaway.command(name="list", help="List active giveaways")
    async def giveaway_list(self, ctx):
        from maniac.core.database import db
        
        giveaways = await db.giveaways.find({
            "guild_id": ctx.guild.id,
            "ended": False
        }).to_list(length=None)
        
        if not giveaways:
            return await ctx.deny("No active giveaways")
        
        embed = discord.Embed(
            title="Active Giveaways",
            color=Config.COLORS.DEFAULT
        )
        
        description = []
        for gw in giveaways:
            channel = ctx.guild.get_channel(gw["channel_id"])
            description.append(
                f"**Prize:** {gw['prize']}\n"
                f"**Channel:** {channel.mention if channel else 'Unknown'}\n"
                f"**Ends:** <t:{int(gw['end_time'].timestamp())}:R>\n"
                f"**Message ID:** `{gw['message_id']}`\n"
            )
        
        embed.description = "\n".join(description)
        await ctx.send(embed=embed)

    @commands.Cog.listener("on_member_join")
    async def welcome_listener(self, member: discord.Member):
        from maniac.core.database import db
        from maniac.core.tools.embed import send_embed
        
        records = await db.welcome.find({
            "guild_id": member.guild.id
        }).to_list(length=None)
        
        if not records:
            return
        
        for record in records:
            channel = member.guild.get_channel(record["channel_id"])
            if not channel:
                continue
            
            try:
                await send_embed(channel, record["message"], member)
            except:
                pass
    
    @commands.group(name="welcome", aliases=["welc"], invoke_without_command=True, help="Configure welcome messages")
    @example(",welcome add #welcome {embed}$v{title: Welcome!}$v{description: Welcome {user.mention}!}")
    @commands.has_permissions(manage_guild=True)
    async def welcome(self, ctx):
        pass
    
    @welcome.command(name="add", help="Add a welcome message to a channel")
    @example(",welcome add #welcome {embed}$v{title: Welcome!}$v{description: Welcome {user.mention}!}")
    @commands.has_permissions(manage_guild=True)
    async def welcome_add(self, ctx, channel: discord.TextChannel, *, message: str):
        from maniac.core.database import db
        
        count = await db.welcome.count_documents({"guild_id": ctx.guild.id})
        if count >= 3:
            return await ctx.deny("You can only have up to 3 welcome channels")
        
        await db.welcome.update_one(
            {
                "guild_id": ctx.guild.id,
                "channel_id": channel.id
            },
            {
                "$set": {
                    "message": message
                }
            },
            upsert=True
        )
        
        await ctx.approve(f"Welcome messages will now be sent to {channel.mention}")
    
    @welcome.command(name="remove", aliases=["delete", "del"], help="Remove welcome messages from a channel")
    @example(",welcome remove #welcome")
    @commands.has_permissions(manage_guild=True)
    async def welcome_remove(self, ctx, channel: discord.TextChannel):
        from maniac.core.database import db
        
        result = await db.welcome.delete_one({
            "guild_id": ctx.guild.id,
            "channel_id": channel.id
        })
        
        if result.deleted_count == 0:
            return await ctx.deny(f"No welcome message found for {channel.mention}")
        
        await ctx.approve(f"No longer sending welcome messages to {channel.mention}")
    
    @welcome.command(name="test", help="Test the welcome message")
    @example(",welcome test #welcome")
    @commands.has_permissions(manage_guild=True)
    async def welcome_test(self, ctx, channel: discord.TextChannel):
        from maniac.core.database import db
        from maniac.core.tools.embed import send_embed
        
        record = await db.welcome.find_one({
            "guild_id": ctx.guild.id,
            "channel_id": channel.id
        })
        
        if not record:
            return await ctx.deny(f"No welcome message found for {channel.mention}")
        
        try:
            await send_embed(channel, record["message"], ctx.author)
            await ctx.approve(f"Sent test welcome message to {channel.mention}")
        except Exception as e:
            await ctx.deny(f"Failed to send welcome message: {str(e)}")
    
    @welcome.command(name="view", help="View the welcome message for a channel")
    @example(",welcome view #welcome")
    @commands.has_permissions(manage_guild=True)
    async def welcome_view(self, ctx, channel: discord.TextChannel):
        from maniac.core.database import db
        
        record = await db.welcome.find_one({
            "guild_id": ctx.guild.id,
            "channel_id": channel.id
        })
        
        if not record:
            return await ctx.deny(f"No welcome message found for {channel.mention}")
        
        await ctx.reply(f"```\n{record['message']}\n```")
    
    @welcome.command(name="clear", help="Remove all welcome messages")
    @example(",welcome clear")
    @commands.has_permissions(manage_guild=True)
    async def welcome_clear(self, ctx):
        from maniac.core.database import db
        
        result = await db.welcome.delete_many({
            "guild_id": ctx.guild.id
        })
        
        if result.deleted_count == 0:
            return await ctx.deny("No welcome messages to clear")
        
        await ctx.approve(f"Cleared {result.deleted_count} welcome message(s)")
    
    @welcome.command(name="list", help="List all welcome channels")
    @example(",welcome list")
    @commands.has_permissions(manage_guild=True)
    async def welcome_list(self, ctx):
        from maniac.core.database import db
        
        records = await db.welcome.find({
            "guild_id": ctx.guild.id
        }).to_list(length=None)
        
        if not records:
            return await ctx.deny("No welcome channels configured")
        
        embed = discord.Embed(
            title="Welcome Channels",
            color=Config.COLORS.DEFAULT
        )
        
        description = []
        for record in records:
            channel = ctx.guild.get_channel(record["channel_id"])
            if channel:
                description.append(f"{channel.mention}")
        
        embed.description = "\n".join(description) if description else "No active channels"
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Configuration(bot))
