import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from typing import Optional
import re
from maniac.core.config import Config
from maniac.core.command_example import example

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.birthday_check.start()
        self.sniped = {}
        self.edit_sniped = {}
        self.reaction_sniped = {}
    
    def cog_unload(self):
        self.birthday_check.cancel()
    
    def parse_date(self, date_str: str):
        patterns = [
            (r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', '%m/%d/%Y'),
            (r'(\d{1,2})[/-](\d{1,2})', '%m/%d'),
            (r'(\w+)\s+(\d{1,2}),?\s*(\d{4})?', None),
        ]
        
        for pattern, fmt in patterns:
            match = re.match(pattern, date_str, re.IGNORECASE)
            if match:
                if fmt:
                    try:
                        return datetime.strptime(date_str, fmt)
                    except:
                        continue
                else:
                    month_str, day_str = match.group(1), match.group(2)
                    year_str = match.group(3) if len(match.groups()) > 2 else None
                    
                    months = {
                        'january': 1, 'jan': 1, 'february': 2, 'feb': 2,
                        'march': 3, 'mar': 3, 'april': 4, 'apr': 4,
                        'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
                        'august': 8, 'aug': 8, 'september': 9, 'sep': 9,
                        'october': 10, 'oct': 10, 'november': 11, 'nov': 11,
                        'december': 12, 'dec': 12
                    }
                    
                    month = months.get(month_str.lower())
                    if month:
                        day = int(day_str)
                        year = int(year_str) if year_str else 2000
                        try:
                            return datetime(year, month, day)
                        except:
                            continue
        return None
    
    @tasks.loop(hours=24)
    async def birthday_check(self):
        from maniac.core.database import db
        
        today = datetime.utcnow()
        yesterday = today - timedelta(days=1)
        
        birthdays = await db.birthdays.find({
            "$or": [
                {"$expr": {"$and": [
                    {"$eq": [{"$month": "$birthday"}, today.month]},
                    {"$eq": [{"$dayOfMonth": "$birthday"}, today.day]}
                ]}},
                {"$expr": {"$and": [
                    {"$eq": [{"$month": "$birthday"}, yesterday.month]},
                    {"$eq": [{"$dayOfMonth": "$birthday"}, yesterday.day]}
                ]}}
            ]
        }).to_list(length=None)
        
        if not birthdays:
            return
        
        guilds = set()
        for record in birthdays:
            user = self.bot.get_user(record["user_id"])
            if user:
                guilds.update(user.mutual_guilds)
        
        configs = await db.birthday_config.find({
            "guild_id": {"$in": [guild.id for guild in guilds]}
        }).to_list(length=None)
        
        config_dict = {config["guild_id"]: config for config in configs}
        
        for guild in guilds:
            config = config_dict.get(guild.id)
            if not config or not config.get("role_id"):
                continue
            
            role = guild.get_role(config["role_id"])
            channel = guild.get_channel(config.get("channel_id")) if config.get("channel_id") else None
            
            if not role:
                continue
            
            for record in birthdays:
                member = guild.get_member(record["user_id"])
                if not member:
                    continue
                
                try:
                    birthday = record["birthday"]
                    if birthday.day == today.day:
                        if role not in member.roles:
                            await member.add_roles(role, reason="Birthday role assignment")
                            
                            if channel:
                                message = config.get("message", "Happy birthday {user}, enjoy your role today 🎉🎂")
                                message = message.replace("{user}", member.mention)
                                message = message.replace("{user.mention}", member.mention)
                                message = message.replace("{user.name}", member.name)
                                
                                await channel.send(message)
                    
                    elif birthday.day == yesterday.day:
                        if role in member.roles:
                            await member.remove_roles(role, reason="Birthday role removal")
                except:
                    pass
    
    @birthday_check.before_loop
    async def before_birthday_check(self):
        await self.bot.wait_until_ready()
    
    @commands.group(aliases=["bday"], invoke_without_command=True, help="View a member's birthday")
    @example(",birthday @offermillions")
    async def birthday(self, ctx, member: discord.Member = None):
        if ctx.invoked_subcommand is not None:
            return
        
        member = member or ctx.author
        
        from maniac.core.database import db
        
        record = await db.birthdays.find_one({"user_id": member.id})
        
        if not record:
            if member == ctx.author:
                return await ctx.warn(f"You haven't set your birthday yet\nUse `{ctx.prefix}birthday set <date>` to set it")
            return await ctx.warn(f"{member.mention} hasn't set their birthday yet")
        
        birthday = record["birthday"]
        current = datetime.utcnow()
        next_birthday = current.replace(month=birthday.month, day=birthday.day)
        
        if next_birthday <= current:
            next_birthday = next_birthday.replace(year=current.year + 1)
        
        days_until = (next_birthday - current).days
        
        if days_until == 0:
            phrase = "today, happy birthday! 🎊"
        elif days_until == 1:
            phrase = "tomorrow, happy early birthday! 🎊"
        else:
            phrase = f"{birthday.strftime('%B %d')}, that's in {days_until} days"
        
        if member == ctx.author:
            return await ctx.approve(f"Your birthday is {phrase}")
        else:
            return await ctx.approve(f"{member.mention}'s birthday is {phrase}")
    
    @birthday.command(name="set", help="Set your birthday")
    async def birthday_set(self, ctx, *, date: str):
        birthday = self.parse_date(date)
        
        if not birthday:
            return await ctx.deny("Invalid date format\nTry: `MM/DD/YYYY`, `January 15`, or `01/15`")
        
        from maniac.core.database import db
        
        existing = await db.birthdays.find_one({"user_id": ctx.author.id})
        
        if existing:
            return await ctx.deny("You've already set your birthday")
        
        await db.birthdays.insert_one({
            "user_id": ctx.author.id,
            "birthday": birthday,
            "created_at": datetime.utcnow()
        })
        
        return await ctx.approve(f"Your birthday has been set to **{birthday.strftime('%B %d')}**")
    
    @birthday.command(name="remove", hidden=True)
    @commands.is_owner()
    async def birthday_remove(self, ctx, user: discord.User):
        from maniac.core.database import db
        
        await db.birthdays.delete_one({"user_id": user.id})
        return await ctx.approve(f"Removed {user.mention}'s birthday")
    
    @birthday.command(name="list", help="View upcoming birthdays in the server")
    async def birthday_list(self, ctx):
        from maniac.core.database import db
        
        member_ids = [member.id for member in ctx.guild.members]
        records = await db.birthdays.find({
            "user_id": {"$in": member_ids}
        }).to_list(length=None)
        
        if not records:
            return await ctx.deny("No birthdays set in this server")
        
        now = datetime.utcnow()
        birthdays = []
        
        for record in records:
            member = ctx.guild.get_member(record["user_id"])
            if not member:
                continue
            
            birthday = record["birthday"]
            is_today = (birthday.month, birthday.day) == (now.month, now.day)
            
            next_bday = now.replace(month=birthday.month, day=birthday.day)
            if next_bday <= now:
                next_bday = next_bday.replace(year=now.year + 1)
            
            days = (next_bday - now).days
            
            birthdays.append({
                "name": member.name,
                "birthday": birthday,
                "days": days,
                "is_today": is_today
            })
        
        birthdays.sort(key=lambda x: x["days"])
        
        if not birthdays:
            return await ctx.deny("No birthdays set in this server")
        
        lines = []
        for b in birthdays[:20]:
            date_str = b['birthday'].strftime('%B %d')
            if b['is_today']:
                time_str = 'Today'
            else:
                time_str = f"{b['days']} days"
            lines.append(f"**{b['name']}** - {date_str} ({time_str})")
        
        embed = discord.Embed(
            title="Upcoming Birthdays",
            description="\n".join(lines),
            color=Config.COLORS.DEFAULT
        )
        
        await ctx.send(embed=embed)
    
    @birthday.group(name="role", invoke_without_command=True, help="Set the birthday role")
    @commands.has_permissions(manage_roles=True)
    async def birthday_role(self, ctx, role: discord.Role):
        from maniac.core.database import db
        
        await db.birthday_config.update_one(
            {"guild_id": ctx.guild.id},
            {"$set": {"role_id": role.id}},
            upsert=True
        )
        
        return await ctx.approve(f"Now assigning {role.mention} to members on their birthday")
    
    @birthday_role.command(name="remove", help="Remove the birthday role")
    @commands.has_permissions(manage_roles=True)
    async def birthday_role_remove(self, ctx):
        from maniac.core.database import db
        
        result = await db.birthday_config.update_one(
            {"guild_id": ctx.guild.id},
            {"$unset": {"role_id": ""}}
        )
        
        if result.matched_count == 0:
            return await ctx.deny("No birthday role is set")
        
        return await ctx.approve("No longer assigning a role on birthdays")
    
    @birthday.group(name="channel", invoke_without_command=True, help="Set the birthday announcement channel")
    @commands.has_permissions(manage_channels=True)
    async def birthday_channel(self, ctx, channel: discord.TextChannel):
        from maniac.core.database import db
        
        await db.birthday_config.update_one(
            {"guild_id": ctx.guild.id},
            {"$set": {"channel_id": channel.id}},
            upsert=True
        )
        
        return await ctx.approve(f"Now sending birthday messages in {channel.mention}")
    
    @birthday_channel.command(name="remove", help="Remove the birthday announcement channel")
    @commands.has_permissions(manage_channels=True)
    async def birthday_channel_remove(self, ctx):
        from maniac.core.database import db
        
        result = await db.birthday_config.update_one(
            {"guild_id": ctx.guild.id},
            {"$unset": {"channel_id": ""}}
        )
        
        if result.matched_count == 0:
            return await ctx.deny("No birthday channel is set")
        
        return await ctx.approve("No longer sending birthday messages")
    
    @birthday.group(name="message", invoke_without_command=True, help="Set a custom birthday message")
    @commands.has_permissions(manage_messages=True)
    async def birthday_message(self, ctx, *, message: str):
        from maniac.core.database import db
        
        await db.birthday_config.update_one(
            {"guild_id": ctx.guild.id},
            {"$set": {"message": message}},
            upsert=True
        )
        
        return await ctx.approve("Updated the birthday message")
    
    @birthday_message.command(name="remove", help="Reset the birthday message to default")
    @commands.has_permissions(manage_messages=True)
    async def birthday_message_remove(self, ctx):
        from maniac.core.database import db
        
        result = await db.birthday_config.update_one(
            {"guild_id": ctx.guild.id},
            {"$unset": {"message": ""}}
        )
        
        if result.matched_count == 0:
            return await ctx.deny("No custom birthday message is set")
        
        return await ctx.approve("Reset the birthday message to default")
    
    @commands.group(aliases=["hl"], invoke_without_command=True)
    @example(",highlight add giveaway")
    async def highlight(self, ctx):
        pass
    
    @highlight.command(name="add", help="Add a keyword to your highlights")
    async def highlight_add(self, ctx, *, keyword: str):
        if len(keyword) < 2 or len(keyword) > 32:
            return await ctx.deny("Keyword must be between 2 and 32 characters")
        
        keyword = keyword.lower()
        
        if "@" in keyword or "#" in keyword:
            return await ctx.deny("Keywords cannot contain mentions")
        
        from maniac.core.database import db
        
        existing = await db.highlights.find_one({
            "guild_id": ctx.guild.id,
            "user_id": ctx.author.id,
            "keyword": keyword
        })
        
        if existing:
            return await ctx.deny("You're already being notified for that keyword")
        
        await db.highlights.insert_one({
            "guild_id": ctx.guild.id,
            "user_id": ctx.author.id,
            "keyword": keyword,
            "created_at": datetime.utcnow()
        })
        
        return await ctx.approve(f"I'll notify you when `{keyword}` is said")
    
    @highlight.command(name="remove", aliases=["delete", "del", "rm"], help="Remove a keyword from your highlights")
    async def highlight_remove(self, ctx, *, keyword: str):
        keyword = keyword.lower()
        
        from maniac.core.database import db
        
        result = await db.highlights.delete_one({
            "guild_id": ctx.guild.id,
            "user_id": ctx.author.id,
            "keyword": keyword
        })
        
        if result.deleted_count == 0:
            return await ctx.deny("You're not being notified for that keyword")
        
        return await ctx.approve(f"I won't notify you for `{keyword}` anymore")
    
    @highlight.command(name="list", help="View your keyword highlights")
    async def highlight_list(self, ctx):
        from maniac.core.database import db
        
        keywords = await db.highlights.find({
            "guild_id": ctx.guild.id,
            "user_id": ctx.author.id
        }).to_list(length=None)
        
        if not keywords:
            return await ctx.deny("You don't have any active highlights")
        
        embed = discord.Embed(
            title="Your Highlights",
            description="\n".join([f"`{record['keyword']}`" for record in keywords]),
            color=Config.COLORS.DEFAULT
        )
        
        await ctx.send(embed=embed)
    
    @commands.Cog.listener("on_message")
    async def highlight_listener(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        
        from maniac.core.database import db
        
        content_lower = message.content.lower()
        
        records = await db.highlights.find({
            "guild_id": message.guild.id
        }).to_list(length=None)
        
        if not records:
            return
        
        for record in records:
            if record["user_id"] == message.author.id:
                continue
            
            member = message.guild.get_member(record["user_id"])
            if not member:
                continue
            
            if not message.channel.permissions_for(member).view_channel:
                continue
            
            if member in message.mentions:
                continue
            
            keyword = record["keyword"]
            if keyword not in content_lower:
                continue
            
            try:
                embed = discord.Embed(
                    title=f"Highlight in {message.guild.name}",
                    description=f"Keyword **`{keyword}`** was mentioned in {message.channel.mention}\n\n[Jump to message]({message.jump_url})",
                    color=Config.COLORS.DEFAULT
                )
                
                embed.set_author(
                    name=message.author.display_name,
                    icon_url=message.author.display_avatar.url
                )
                
                content = message.content
                if len(content) > 200:
                    content = content[:200] + "..."
                
                embed.add_field(
                    name="Message",
                    value=f">>> {content}",
                    inline=False
                )
                
                embed.timestamp = message.created_at
                
                await member.send(embed=embed)
            except discord.Forbidden:
                await db.highlights.delete_many({"user_id": member.id})
            except:
                pass
    
    @commands.group(name="gnames", aliases=["guildnames"], invoke_without_command=True, help="View tracked guild name changes")
    @example(",gnames")
    async def gnames(self, ctx):
        if ctx.invoked_subcommand is not None:
            return
        
        from maniac.core.database import db
        
        records = await db.guild_names.find({
            "guild_id": ctx.guild.id
        }).sort("changed_at", -1).limit(20).to_list(length=20)
        
        if not records:
            return await ctx.deny("No guild name changes have been tracked")
        
        embed = discord.Embed(
            title=f"Guild Name History",
            color=Config.COLORS.DEFAULT
        )
        
        description = []
        for i, record in enumerate(records, 1):
            description.append(
                f"`{i}.` **{record['old_name']}** → **{record['new_name']}**\n"
                f"<t:{int(record['changed_at'].timestamp())}:R>"
            )
        
        embed.description = "\n\n".join(description)
        await ctx.reply(embed=embed)
    
    @gnames.command(name="clear", help="Clear guild name history")
    @commands.has_permissions(administrator=True)
    async def gnames_clear(self, ctx):
        from maniac.core.database import db
        
        result = await db.guild_names.delete_many({
            "guild_id": ctx.guild.id
        })
        
        if result.deleted_count == 0:
            return await ctx.deny("No guild name history to clear")
        
        await ctx.approve(f"Successfully cleared {result.deleted_count} guild name record(s)")
    
    @commands.command(name="randomhex", aliases=["randhex"], help="Generate a random hex color")
    @example(",randomhex")
    async def randomhex(self, ctx):
        import random
        
        hex_color = "#{:06x}".format(random.randint(0, 0xFFFFFF))
        
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        
        embed = discord.Embed(
            title="Random Hex Color",
            description=f"**Hex:** `{hex_color}`\n**RGB:** `({r}, {g}, {b})`",
            color=int(hex_color[1:], 16)
        )
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="urban", aliases=["ud"], help="Search Urban Dictionary")
    @example(",urban yeet")
    async def urban(self, ctx, *, term: str):
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.urbandictionary.com/v0/define?term={term}") as r:
                if r.status != 200:
                    return await ctx.deny("Failed to search Urban Dictionary")
                
                data = await r.json()
        
        if not data.get("list"):
            return await ctx.deny(f"No results found for `{term}`")
        
        result = data["list"][0]
        
        definition = result["definition"].replace("[", "").replace("]", "")
        example_text = result["example"].replace("[", "").replace("]", "")
        
        if len(definition) > 1024:
            definition = definition[:1021] + "..."
        if len(example_text) > 1024:
            example_text = example_text[:1021] + "..."
        
        embed = discord.Embed(
            title=result["word"],
            url=result["permalink"],
            color=Config.COLORS.DEFAULT
        )
        
        embed.add_field(
            name="Definition",
            value=definition,
            inline=False
        )
        
        if example_text:
            embed.add_field(
                name="Example",
                value=example_text,
                inline=False
            )
        
        embed.add_field(
            name="Rating",
            value=f"👍 {result['thumbs_up']:,} | 👎 {result['thumbs_down']:,}",
            inline=False
        )
        
        embed.set_footer(text=f"By {result['author']}")
        
        await ctx.reply(embed=embed)
    
    @commands.command(name="translate", aliases=["tr"], help="Translate text to another language")
    @example(",translate es Hello world")
    async def translate(self, ctx, language: str, *, text: str):
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://translate.googleapis.com/translate_a/single",
                params={
                    "client": "gtx",
                    "sl": "auto",
                    "tl": language,
                    "dt": "t",
                    "q": text
                }
            ) as r:
                if r.status != 200:
                    return await ctx.deny("Failed to translate text")
                
                data = await r.json()
        
        try:
            translated = "".join([sentence[0] for sentence in data[0] if sentence[0]])
            detected_lang = data[2] if len(data) > 2 else "Unknown"
        except:
            return await ctx.deny("Failed to parse translation")
        
        embed = discord.Embed(
            title="Translation",
            color=Config.COLORS.DEFAULT
        )
        
        embed.add_field(
            name=f"Original ({detected_lang})",
            value=text[:1024],
            inline=False
        )
        
        embed.add_field(
            name=f"Translated ({language})",
            value=translated[:1024],
            inline=False
        )
        
        await ctx.reply(embed=embed)
    
    @commands.Cog.listener("on_message_delete")
    async def snipe_listener(self, message: discord.Message):
        if message.author.bot:
            return
        
        if message.channel.id not in self.sniped:
            self.sniped[message.channel.id] = []
        
        image_url = None
        if message.attachments:
            image_url = message.attachments[0].url
        
        self.sniped[message.channel.id].append({
            "author": str(message.author),
            "author_url": str(message.author.display_avatar.url),
            "content": message.content,
            "image_url": image_url,
            "timestamp": message.created_at,
            "deleted_at": datetime.utcnow()
        })
    
    @commands.Cog.listener("on_raw_reaction_remove")
    async def reactionsnipe_listener(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        
        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            return
        
        message_link = f"https://discord.com/channels/{payload.guild_id}/{payload.channel_id}/{payload.message_id}"
        emoji = str(payload.emoji)
        
        if payload.channel_id not in self.reaction_sniped:
            self.reaction_sniped[payload.channel_id] = []
        
        self.reaction_sniped[payload.channel_id].append({
            "author": str(payload.user_id),
            "emoji": emoji,
            "message_link": message_link,
            "message_id": payload.message_id,
            "timestamp": datetime.utcnow()
        })
    
    @commands.Cog.listener("on_message_edit")
    async def editsnipe_listener(self, before: discord.Message, after: discord.Message):
        if before.guild and not before.author.bot:
            channel_id = before.channel.id
            
            if channel_id not in self.edit_sniped:
                self.edit_sniped[channel_id] = []
            
            self.edit_sniped[channel_id].append({
                "before_content": before.content,
                "after_content": after.content,
                "author": str(before.author),
                "author_url": str(before.author.display_avatar.url),
                "timestamp": before.edited_at,
                "edited_at": datetime.utcnow()
            })
    
    @commands.command(name="snipe", aliases=["s"], help="View the last deleted message")
    @example(",snipe")
    async def snipe(self, ctx, index: int = 1):
        sniped_messages = self.sniped.get(ctx.channel.id, [])
        
        if not sniped_messages:
            return await ctx.warn("No deleted messages found")
        
        index -= 1
        if index < 0 or index >= len(sniped_messages):
            return await ctx.warn("Invalid index")
        
        sniped_message = sniped_messages[index]
        content = sniped_message.get("content", "")
        author = sniped_message.get("author", "N/A")
        author_icon = sniped_message.get("author_url")
        deleted_at = sniped_message.get("deleted_at", datetime.utcnow())
        image_url = sniped_message.get("image_url")
        
        time_since = datetime.utcnow() - deleted_at
        seconds = int(time_since.total_seconds())
        
        if seconds < 60:
            time_str = f"{seconds} seconds ago"
        elif seconds < 3600:
            time_str = f"{seconds // 60} minutes ago"
        elif seconds < 86400:
            time_str = f"{seconds // 3600} hours ago"
        else:
            time_str = f"{seconds // 86400} days ago"
        
        embed = discord.Embed(
            description=content if content else "*No content*",
            color=Config.COLORS.DEFAULT
        )
        embed.set_author(name=author, icon_url=author_icon)
        embed.set_footer(text=f"Deleted {time_str} • {index + 1}/{len(sniped_messages)}")
        
        if image_url:
            embed.set_image(url=image_url)
        
        await ctx.send(embed=embed)
    
    @commands.command(name="editsnipe", aliases=["es"], help="View the last edited message")
    @example(",editsnipe")
    async def editsnipe(self, ctx, index: int = 1):
        edit_sniped_messages = self.edit_sniped.get(ctx.channel.id, [])
        
        if not edit_sniped_messages:
            return await ctx.warn("No edited messages found")
        
        index -= 1
        if index < 0 or index >= len(edit_sniped_messages):
            return await ctx.warn("Invalid index")
        
        editsniped = edit_sniped_messages[index]
        before = editsniped.get("before_content", "")
        after = editsniped.get("after_content", "")
        author = editsniped.get("author", "N/A")
        author_url = editsniped.get("author_url", "")
        edited_at = editsniped.get("edited_at", datetime.utcnow())
        
        time_since = datetime.utcnow() - edited_at
        seconds = int(time_since.total_seconds())
        
        if seconds < 60:
            time_str = f"{seconds} seconds ago"
        elif seconds < 3600:
            time_str = f"{seconds // 60} minutes ago"
        elif seconds < 86400:
            time_str = f"{seconds // 3600} hours ago"
        else:
            time_str = f"{seconds // 86400} days ago"
        
        embed = discord.Embed(
            description=f"**Before:** {before if before else '*No content*'}\n**After:** {after if after else '*No content*'}",
            color=Config.COLORS.DEFAULT
        )
        embed.set_author(name=author, icon_url=author_url)
        embed.set_footer(text=f"Edited {time_str} • {index + 1}/{len(edit_sniped_messages)}")
        
        await ctx.send(embed=embed)
    
    @commands.command(name="reactionsnipe", aliases=["rs"], help="View recently removed reactions")
    @example(",reactionsnipe")
    async def reactionsnipe(self, ctx, index: int = 1):
        snipes = self.reaction_sniped.get(ctx.channel.id, [])
        
        if not snipes:
            return await ctx.warn("No reaction removals found")
        
        index -= 1
        if index < 0 or index >= len(snipes):
            return await ctx.warn("Invalid index")
        
        sniped = snipes[index]
        user_id = int(sniped.get("author", "0"))
        emoji = sniped.get("emoji", "")
        timestamp = sniped.get("timestamp", datetime.utcnow())
        original_message_id = sniped.get("message_id")
        
        try:
            member = await ctx.guild.fetch_member(user_id)
            member_name = str(member)
        except:
            member_name = f"User {user_id}"
        
        embed = discord.Embed(
            description=f"**{member_name}** reacted with {emoji} {discord.utils.format_dt(timestamp, 'R')}",
            color=Config.COLORS.DEFAULT
        )
        
        try:
            original_message = await ctx.channel.fetch_message(original_message_id)
            await original_message.reply(embed=embed)
        except:
            await ctx.send(embed=embed)
    
    @commands.command(name="clearsnipes", aliases=["cs"], help="Clear all sniped messages in this channel")
    @commands.has_permissions(manage_messages=True)
    @example(",clearsnipes")
    async def clearsnipes(self, ctx):
        cleared = False
        
        if ctx.channel.id in self.sniped:
            del self.sniped[ctx.channel.id]
            cleared = True
        
        if ctx.channel.id in self.edit_sniped:
            del self.edit_sniped[ctx.channel.id]
            cleared = True
        
        if ctx.channel.id in self.reaction_sniped:
            del self.reaction_sniped[ctx.channel.id]
            cleared = True
        
        if cleared:
            await ctx.message.add_reaction("✅")
        else:
            await ctx.warn("There are no sniped messages in this channel")
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        
        prefixes = await self.bot.get_prefix(message)
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        
        used_prefix = next((p for p in prefixes if message.content.startswith(p)), None)
        if not used_prefix:
            return
        
        tokens = message.content[len(used_prefix):].split(maxsplit=1)
        if not tokens:
            return
        
        alias = tokens[0].lower()
        
        from maniac.core.database import db
        
        alias_data = await db.aliases.find_one({
            "guild_id": message.guild.id,
            "alias": alias
        })
        
        if alias_data:
            import copy
            real = alias_data["command"]
            rest = tokens[1] if len(tokens) > 1 else ""
            new_content = f"{used_prefix}{real} {rest}".strip()
            
            fake = copy.copy(message)
            fake.content = new_content
            ctx = await self.bot.get_context(fake)
            await self.bot.invoke(ctx)
    
    @commands.group(name="alias", invoke_without_command=True, help="Manage command aliases")
    @example(",alias list")
    @commands.has_permissions(manage_guild=True)
    async def alias(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
    
    @alias.command(name="add", help="Add a command alias")
    @example(",alias add ban deport")
    @commands.has_permissions(manage_guild=True)
    async def alias_add(self, ctx, command: str, alias: str):
        command, alias = command.lower(), alias.lower()
        
        if not self.bot.get_command(command):
            return await ctx.warn(f"Command `{command}` not found")
        
        from maniac.core.database import db
        
        existing = await db.aliases.find_one({
            "guild_id": ctx.guild.id,
            "alias": alias
        })
        
        if existing:
            return await ctx.deny(f"Alias `{alias}` already exists")
        
        await db.aliases.insert_one({
            "guild_id": ctx.guild.id,
            "alias": alias,
            "command": command,
            "created_at": datetime.utcnow(),
            "created_by": ctx.author.id
        })
        
        await ctx.approve(f"Added alias `{alias}` → `{command}`")
    
    @alias.command(name="remove", aliases=["delete", "del"], help="Remove a command alias")
    @example(",alias remove deport")
    @commands.has_permissions(manage_guild=True)
    async def alias_remove(self, ctx, alias: str):
        alias = alias.lower()
        
        from maniac.core.database import db
        
        result = await db.aliases.delete_one({
            "guild_id": ctx.guild.id,
            "alias": alias
        })
        
        if result.deleted_count == 0:
            return await ctx.warn(f"Alias `{alias}` not found")
        
        await ctx.approve(f"Removed alias `{alias}`")
    
    @alias.command(name="list", help="List all command aliases")
    @example(",alias list")
    async def alias_list(self, ctx):
        from maniac.core.database import db
        
        aliases = await db.aliases.find({
            "guild_id": ctx.guild.id
        }).to_list(length=None)
        
        if not aliases:
            return await ctx.warn("No aliases set")
        
        lines = [f"`{a['alias']}` → `{a['command']}`" for a in aliases]
        
        embed = discord.Embed(
            title="Configured Aliases",
            description="\n".join(lines),
            color=Config.COLORS.DEFAULT
        )
        embed.set_footer(text=f"{len(aliases)} alias(es)")
        
        await ctx.send(embed=embed)
    
    @alias.command(name="clear", help="Clear all command aliases")
    @example(",alias clear")
    @commands.has_permissions(manage_guild=True)
    async def alias_clear(self, ctx):
        from maniac.core.database import db
        
        result = await db.aliases.delete_many({
            "guild_id": ctx.guild.id
        })
        
        if result.deleted_count == 0:
            return await ctx.warn("No aliases to clear")
        
        await ctx.approve(f"Cleared {result.deleted_count} alias(es)")
    
    async def fetch_crypto(self, symbol: str):
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
        headers = {
            "X-CMC_PRO_API_KEY": "4b49c98b-6203-4051-8112-83c07fc48267",
            "Accepts": "application/json"
        }
        params = {"symbol": symbol.upper()}
        
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
    
    async def fetch_conversion(self, amount: float, from_symbol: str, to_symbol: str):
        url = "https://pro-api.coinmarketcap.com/v1/tools/price-conversion"
        headers = {
            "X-CMC_PRO_API_KEY": "4b49c98b-6203-4051-8112-83c07fc48267",
            "Accepts": "application/json"
        }
        params = {
            "amount": amount,
            "symbol": from_symbol.upper(),
            "convert": to_symbol.upper()
        }
        
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    return None
                try:
                    return await resp.json()
                except:
                    return None
    
    async def fetch_logo(self, symbol: str):
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/info"
        headers = {
            "X-CMC_PRO_API_KEY": "4b49c98b-6203-4051-8112-83c07fc48267",
            "Accepts": "application/json"
        }
        params = {"symbol": symbol.upper()}
        
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
    
    @commands.group(name="crypto", invoke_without_command=True, help="View cryptocurrency information")
    @example(",crypto btc")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def crypto(self, ctx, symbol: str = None):
        if not symbol:
            return await ctx.send_help(ctx.command)
        
        data = await self.fetch_crypto(symbol)
        
        if not data or data.get("status", {}).get("error_code") != 0:
            return await ctx.deny(f"Could not fetch data for **{symbol.upper()}**")
        
        coin = data["data"][symbol.upper()]
        quote = coin["quote"]["USD"]
        
        price = f"${quote['price']:,.2f}"
        p1h = f"{quote['percent_change_1h']:.2f}%"
        p24h = f"{quote['percent_change_24h']:.2f}%"
        p7d = f"{quote['percent_change_7d']:.2f}%"
        p30d = f"{quote['percent_change_30d']:.2f}%"
        
        logo_data = await self.fetch_logo(symbol)
        logo_url = None
        if logo_data and "data" in logo_data and symbol.upper() in logo_data["data"]:
            logo_url = logo_data["data"][symbol.upper()]["logo"]
        
        embed = discord.Embed(
            description=f"**(USD) Current Price**\n> {price}\n\u200b",
            color=Config.COLORS.DEFAULT
        )
        embed.add_field(name="(1h) Change", value=f"> {p1h}", inline=True)
        embed.add_field(name="(24h) Change", value=f"> {p24h}", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="(7d) Change", value=f"> {p7d}", inline=True)
        embed.add_field(name="(30d) Change", value=f"> {p30d}", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.set_author(name=f"[{coin['name']}] {coin['symbol']} Information", icon_url=logo_url)
        
        await ctx.send(embed=embed)
    
    @crypto.command(name="convert", help="Convert between cryptocurrencies")
    @example(",crypto convert 1 btc eth")
    async def crypto_convert(self, ctx, amount: float = None, from_symbol: str = None, to_symbol: str = None):
        if not amount or not from_symbol or not to_symbol:
            return await ctx.deny("Usage: `,crypto convert <amount> <from> <to>`")
        
        data = await self.fetch_conversion(amount, from_symbol, to_symbol)
        
        if not data or data.get("status", {}).get("error_code") != 0:
            return await ctx.deny("Failed to fetch conversion")
        
        try:
            converted_value = data["data"]["quote"][to_symbol.upper()]["price"]
        except:
            return await ctx.deny("Error parsing conversion result")
        
        usd_from = None
        usd_to = None
        
        from_usd = await self.fetch_conversion(amount, from_symbol, "USD")
        if from_usd and from_usd.get("status", {}).get("error_code") == 0:
            usd_from = from_usd["data"]["quote"]["USD"]["price"]
        
        to_usd = await self.fetch_conversion(1, to_symbol, "USD")
        if to_usd and to_usd.get("status", {}).get("error_code") == 0:
            usd_to = to_usd["data"]["quote"]["USD"]["price"]
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name="Crypto Conversion", icon_url=ctx.bot.user.display_avatar.url)
        
        embed.add_field(
            name="Conversion",
            value=f"> **{amount} {from_symbol.upper()} = {converted_value:,.6f} {to_symbol.upper()}**",
            inline=False
        )
        
        if usd_from:
            embed.add_field(
                name=f"{from_symbol.upper()} in USD",
                value=f"> **{amount} {from_symbol.upper()} = ${usd_from:,.2f}**",
                inline=True
            )
        
        if usd_to:
            embed.add_field(
                name=f"{to_symbol.upper()} in USD",
                value=f"> **{converted_value:,.6f} {to_symbol.upper()} = ${converted_value * usd_to:,.2f}**",
                inline=True
            )
        
        await ctx.send(embed=embed)
    
    @crypto.command(name="price", help="Get cryptocurrency price in USD")
    @example(",crypto price btc 2")
    async def crypto_price(self, ctx, symbol: str = None, amount: float = 1.0):
        if not symbol:
            return await ctx.deny("Usage: `,crypto price <symbol> [amount]`")
        
        data = await self.fetch_conversion(amount, symbol, "USD")
        
        if not data or data.get("status", {}).get("error_code") != 0:
            return await ctx.deny(f"Could not fetch price for **{symbol.upper()}**")
        
        usd_value = data["data"]["quote"]["USD"]["price"]
        
        desc = f"> **{amount:,.3f} {symbol.upper()} = ${usd_value:,.2f}**"
        
        embed = discord.Embed(description=desc, color=Config.COLORS.DEFAULT)
        embed.set_author(name="Crypto Price", icon_url=ctx.bot.user.display_avatar.url)
        
        await ctx.send(embed=embed)
    
    @crypto.command(name="rates", help="View top cryptocurrencies")
    @example(",crypto rates")
    async def crypto_rates(self, ctx):
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
        headers = {
            "X-CMC_PRO_API_KEY": "4b49c98b-6203-4051-8112-83c07fc48267",
            "Accepts": "application/json"
        }
        params = {"limit": 10, "convert": "USD"}
        
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    return await ctx.deny("Failed to fetch cryptocurrency rates")
                data = await resp.json()
        
        if not data or data.get("status", {}).get("error_code") != 0:
            return await ctx.deny("Failed to fetch cryptocurrency rates")
        
        embed = discord.Embed(
            title="Top 10 Cryptocurrencies",
            color=Config.COLORS.DEFAULT
        )
        
        for coin in data["data"]:
            quote = coin["quote"]["USD"]
            price = f"${quote['price']:,.2f}"
            change_24h = quote['percent_change_24h']
            change_emoji = "📈" if change_24h > 0 else "📉"
            
            embed.add_field(
                name=f"{coin['cmc_rank']}. {coin['name']} ({coin['symbol']})",
                value=f"> **Price:** {price}\n> **24h Change:** {change_emoji} {change_24h:.2f}%",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(help="View Bitcoin information")
    @example(",bitcoin")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def bitcoin(self, ctx):
        await ctx.invoke(self.crypto, symbol="BTC")
    
    @commands.command(help="View Ethereum information")
    @example(",ethereum")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def ethereum(self, ctx):
        await ctx.invoke(self.crypto, symbol="ETH")
    
    @commands.group(invoke_without_command=True, help="View Ethereum information")
    @example(",eth")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def eth(self, ctx):
        await ctx.invoke(self.crypto, symbol="ETH")
    
    @eth.command(name="gas", help="View Ethereum gas prices")
    @example(",eth gas")
    async def eth_gas(self, ctx):
        url = "https://api.owlracle.info/v4/eth/gas"
        params = {"apikey": "5cb7b35142204038b9ccf4dc1b77d08f"}
        
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return await ctx.deny("Failed to fetch Ethereum gas prices")
                data = await resp.json()
        
        if not data or "speeds" not in data:
            return await ctx.deny("Failed to fetch Ethereum gas prices")
        
        speeds = data["speeds"]
        
        embed = discord.Embed(
            title="⛽ Ethereum Gas Prices",
            color=Config.COLORS.DEFAULT
        )
        
        for speed in speeds:
            name = speed["acceptance"].title()
            gas_price = speed["gasPrice"]
            max_fee = speed.get("maxFeePerGas", gas_price)
            priority_fee = speed.get("maxPriorityFeePerGas", 0)
            
            embed.add_field(
                name=f"{name} Speed",
                value=f"> **Gas Price:** {gas_price:.2f} Gwei\n> **Max Fee:** {max_fee:.2f} Gwei\n> **Priority Fee:** {priority_fee:.2f} Gwei",
                inline=True
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(help="View Litecoin information")
    @example(",litecoin")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def litecoin(self, ctx):
        await ctx.invoke(self.crypto, symbol="LTC")
    
    @commands.command(help="View Ripple information")
    @example(",ripple")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def ripple(self, ctx):
        await ctx.invoke(self.crypto, symbol="XRP")
    
    @commands.command(help="View Monero information")
    @example(",monero")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def monero(self, ctx):
        await ctx.invoke(self.crypto, symbol="XMR")
    
    @commands.command(help="View Solana information")
    @example(",solana")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def solana(self, ctx):
        await ctx.invoke(self.crypto, symbol="SOL")

async def setup(bot):
    await bot.add_cog(Utility(bot))
