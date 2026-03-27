import asyncio
from discord import Member, Message, Embed
from discord.ext.commands import Cog
from contextlib import suppress
from discord import HTTPException
from heist.framework.script import Script
from datetime import datetime, timezone
import json
import base64
import zlib
import aiohttp
import discord
import io

class MiscEvents(Cog):
    def __init__(self, bot):
        self.bot = bot
    
    async def compress_file(self, file_data: bytes) -> str:
        compressed = zlib.compress(file_data, level=9)
        return base64.b64encode(compressed).decode('utf-8')
    
    async def decompress_file(self, compressed_data: str) -> bytes:
        decoded = base64.b64decode(compressed_data.encode('utf-8'))
        return zlib.decompress(decoded)
    
    async def download_attachment(self, url: str) -> bytes:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200 and resp.content_length and resp.content_length < 8 * 1024 * 1024:
                    return await resp.read()
        return b''

    @Cog.listener()
    async def on_member_join(self, member: Member):
        if member.bot:
            return
        
        welcome_result = await self.bot.pool.fetchrow(
            "SELECT channel_id, template, delete_after FROM welcome_message WHERE guild_id = $1",
            member.guild.id
        )
        
        if welcome_result:
            channel = member.guild.get_channel(welcome_result['channel_id'])
            if channel:
                template = welcome_result['template']
                delete_after = welcome_result['delete_after']
                
                script = Script(template, [member, member.guild])
                
                try:
                    sent_message = await script.send(channel)
                    
                    if delete_after:
                        await asyncio.sleep(delete_after)
                        with suppress(HTTPException):
                            await sent_message.delete()
                            
                except HTTPException:
                    pass
        
        joindm_config = await self.bot.pool.fetchrow("SELECT * FROM joindm.config WHERE guild_id = $1 AND enabled = true", member.guild.id)
        if joindm_config and joindm_config["message"]:
            try:
                script = Script(joindm_config["message"], [member, member.guild])
                await script.send(member)
            except HTTPException:
                pass
        
        ping_config = await self.bot.pool.fetchrow("SELECT * FROM pingonjoin.config WHERE guild_id = $1", member.guild.id)
        if ping_config:
            ping_channel = member.guild.get_channel(ping_config["channel_id"])
            if ping_channel:
                try:
                    message = await ping_channel.send(f"{member.mention}")
                    
                    if ping_config["delete_ping"]:
                        if ping_config["delete_after"] == 0:
                            await message.delete()
                        elif ping_config["delete_after"]:
                            await asyncio.sleep(ping_config["delete_after"])
                            await message.delete()
                except HTTPException:
                    pass

    @Cog.listener()
    async def on_message(self, message: Message):
        if not message.guild or message.author.bot:
            return
        
        ctx = await self.bot.get_context(message)
        
        afk_data = await self.bot.redis.get(f"afk:{message.author.id}")
        if afk_data:
            await self.bot.pool.execute(
                "DELETE FROM afk WHERE user_id = $1",
                message.author.id
            )
            await self.bot.redis.delete(f"afk:{message.author.id}")
            
            left_at = int(afk_data['left_at'])
            embed = Embed(
                color=ctx.config.colors.information,
                description=f"{message.author.mention}: Welcome back, you were away for <t:{left_at}:R>."
            )
            await message.reply(embed=embed)
            return
        
        if message.mentions:
            for mentioned_user in message.mentions:
                if mentioned_user.bot:
                    continue
                    
                afk_data = await self.bot.redis.get(f"afk:{mentioned_user.id}")
                if afk_data:
                    ratelimit = await self.bot.redis.ratelimited(
                        f"afk_mention:{message.author.id}:{mentioned_user.id}",
                        limit=2,
                        timespan=10,
                    )
                    if ratelimit:
                        continue
                    
                    left_at = int(afk_data['left_at'])
                    embed = Embed(
                        color=ctx.config.colors.information,
                        description=f"{mentioned_user.mention} is AFK: {afk_data['status']} - <t:{left_at}:R>"
                    )
                    await message.reply(embed=embed)
                    
                    await self.bot.pool.execute(
                        "INSERT INTO afk_mentions (afk_user_id, mentioner_id, message_id, channel_id, guild_id) "
                        "VALUES ($1, $2, $3, $4, $5)",
                        mentioned_user.id, message.author.id, message.id, message.channel.id, message.guild.id
                    )
                    break

    @Cog.listener()
    async def on_message_delete(self, message: Message):
        if not message.guild or message.author.bot:
            return
        
        if not message.content and not message.attachments and not message.stickers:
            return
        
        ignore_check = await self.bot.pool.fetchrow(
            "SELECT 1 FROM snipe.ignore WHERE guild_id = $1 AND user_id = $2",
            message.guild.id, message.author.id
        )
        if ignore_check:
            return
        
        redis_key = f"snipe_filter:{message.guild.id}"
        cached_filter = await self.bot.redis.get(redis_key)
        
        if cached_filter:
            if isinstance(cached_filter, str):
                filter_data = json.loads(cached_filter)
            else:
                filter_data = cached_filter
        else:
            filter_data = await self.bot.pool.fetchrow(
                "SELECT invites, links, words FROM snipe.filter WHERE guild_id = $1",
                message.guild.id
            )
            if filter_data:
                filter_data = dict(filter_data)
                await self.bot.redis.set(redis_key, json.dumps(filter_data), ex=3600)
            else:
                filter_data = None
        
        if filter_data and message.content:
            content_lower = message.content.lower()
            
            if filter_data['invites'] and ('discord.gg/' in content_lower or 'discord.com/invite/' in content_lower):
                return
            
            if filter_data['links'] and ('http://' in content_lower or 'https://' in content_lower):
                return
            
            if filter_data['words'] and any(word.lower() in content_lower for word in filter_data['words']):
                return
        
        sticker_data = None
        if message.stickers:
            sticker_data = json.dumps([{
                'id': s.id,
                'name': s.name,
                'format': str(s.format),
                'url': s.url
            } for s in message.stickers])
        
        attachment_data = None
        file_data = None
        
        if message.attachments:
            attachment_info = []
            files = []
            
            for attachment in message.attachments:
                attachment_info.append({
                    'id': attachment.id,
                    'filename': attachment.filename,
                    'size': attachment.size,
                    'url': attachment.url,
                    'content_type': attachment.content_type
                })
                
                if attachment.size < 8 * 1024 * 1024:
                    try:
                        file_bytes = await self.download_attachment(attachment.url)
                        if file_bytes:
                            compressed = await self.compress_file(file_bytes)
                            files.append({
                                'filename': attachment.filename,
                                'data': compressed
                            })
                    except:
                        pass
            
            attachment_data = json.dumps(attachment_info)
            if files:
                file_data = json.dumps(files)
        
        await self.bot.pool.execute(
            "INSERT INTO snipe.messages (guild_id, channel_id, user_id, content, stickers, attachments, files) VALUES ($1, $2, $3, $4, $5, $6, $7)",
            message.guild.id, message.channel.id, message.author.id, message.content, sticker_data, attachment_data, file_data
        )
        
        count = await self.bot.pool.fetchval(
            "SELECT COUNT(*) FROM snipe.messages WHERE guild_id = $1 AND channel_id = $2",
            message.guild.id, message.channel.id
        )
        
        if count >= 30:
            await self.bot.pool.execute(
                "DELETE FROM snipe.messages WHERE guild_id = $1 AND channel_id = $2",
                message.guild.id, message.channel.id
            )
            await self.bot.redis.delete(f"snipe:{message.guild.id}:{message.channel.id}")
        else:
            await self.bot.redis.delete(f"snipe:{message.guild.id}:{message.channel.id}")

    @Cog.listener()
    async def on_message_edit(self, before: Message, after: Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        
        ignore_check = await self.bot.pool.fetchrow(
            "SELECT 1 FROM snipe.ignore WHERE guild_id = $1 AND user_id = $2",
            before.guild.id, before.author.id
        )
        if ignore_check:
            return
        
        redis_key = f"snipe_filter:{before.guild.id}"
        cached_filter = await self.bot.redis.get(redis_key)
        
        if cached_filter:
            if isinstance(cached_filter, str):
                filter_data = json.loads(cached_filter)
            else:
                filter_data = cached_filter
        else:
            filter_data = await self.bot.pool.fetchrow(
                "SELECT invites, links, words FROM snipe.filter WHERE guild_id = $1",
                before.guild.id
            )
            if filter_data:
                filter_data = dict(filter_data)
                await self.bot.redis.set(redis_key, json.dumps(filter_data), ex=3600)
            else:
                filter_data = None
        
        if filter_data:
            old_content_lower = before.content.lower() if before.content else ""
            new_content_lower = after.content.lower() if after.content else ""
            
            if filter_data['invites'] and ('discord.gg/' in old_content_lower or 'discord.com/invite/' in old_content_lower or 'discord.gg/' in new_content_lower or 'discord.com/invite/' in new_content_lower):
                return
            
            if filter_data['links'] and ('http://' in old_content_lower or 'https://' in old_content_lower or 'http://' in new_content_lower or 'https://' in new_content_lower):
                return
            
            if filter_data['words'] and (any(word.lower() in old_content_lower for word in filter_data['words']) or any(word.lower() in new_content_lower for word in filter_data['words'])):
                return
        
        old_stickers = None
        new_stickers = None
        
        if before.stickers:
            old_stickers = json.dumps([{
                'id': s.id,
                'name': s.name,
                'format': str(s.format),
                'url': s.url
            } for s in before.stickers])
        
        if after.stickers:
            new_stickers = json.dumps([{
                'id': s.id,
                'name': s.name,
                'format': str(s.format),
                'url': s.url
            } for s in after.stickers])
        
        old_attachments = None
        new_attachments = None
        
        if before.attachments:
            old_attachments = json.dumps([{
                'id': a.id,
                'filename': a.filename,
                'size': a.size,
                'url': a.url,
                'content_type': a.content_type
            } for a in before.attachments])
        
        if after.attachments:
            new_attachments = json.dumps([{
                'id': a.id,
                'filename': a.filename,
                'size': a.size,
                'url': a.url,
                'content_type': a.content_type
            } for a in after.attachments])
        
        await self.bot.pool.execute(
            "INSERT INTO snipe.edits (guild_id, channel_id, user_id, old_content, new_content, old_stickers, new_stickers, old_attachments, new_attachments) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
            before.guild.id, before.channel.id, before.author.id, before.content, after.content, old_stickers, new_stickers, old_attachments, new_attachments
        )
        
        count = await self.bot.pool.fetchval(
            "SELECT COUNT(*) FROM snipe.edits WHERE guild_id = $1 AND channel_id = $2",
            before.guild.id, before.channel.id
        )
        
        if count >= 30:
            await self.bot.pool.execute(
                "DELETE FROM snipe.edits WHERE guild_id = $1 AND channel_id = $2",
                before.guild.id, before.channel.id
            )
            await self.bot.redis.delete(f"editsnipe:{before.guild.id}:{before.channel.id}")
        else:
            await self.bot.redis.delete(f"editsnipe:{before.guild.id}:{before.channel.id}")

    @Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if not payload.guild_id or payload.user_id == self.bot.user.id:
            return
        
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        
        member = guild.get_member(payload.user_id)
        emoji_str = str(payload.emoji)
        
        rr_data = await self.bot.pool.fetchrow(
            "SELECT role_id FROM reaction_role WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3 AND emoji = $4",
            payload.guild_id, payload.channel_id, payload.message_id, emoji_str
        )
        
        if rr_data and member and not member.bot:
            role = guild.get_role(rr_data['role_id'])
            if role:
                try:
                    await member.add_roles(role, reason="Reaction role")
                except:
                    pass
        
        skull_data = await self.bot.pool.fetchrow("SELECT * FROM skullboard WHERE guild_id = $1", payload.guild_id)
        if not skull_data:
            return
        
        emoji_match = False
        if payload.emoji.is_unicode_emoji():
            emoji_match = ord(str(payload.emoji)) == skull_data["emoji_id"]
        elif payload.emoji.is_custom_emoji():
            emoji_match = payload.emoji.id == skull_data["emoji_id"]
        
        if not emoji_match:
            return
        
        channel = guild.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        
        existing = await self.bot.pool.fetchrow(
            "SELECT * FROM skullboardmes WHERE guild_id = $1 AND channel_message_id = $2 AND message_id = $3",
            payload.guild_id, payload.channel_id, payload.message_id
        )
        
        if existing:
            skull_channel = guild.get_channel(existing["channel_skullboard_id"])
            skull_message = await skull_channel.fetch_message(existing["message_skullboard_id"])
            reaction_count = sum(r.count for r in message.reactions if str(r.emoji) == str(payload.emoji))
            await skull_message.edit(content=f"{payload.emoji} <#{payload.channel_id}>")
            return
        
        skull_channel = guild.get_channel(skull_data["channel_id"])
        if not skull_channel:
            return
        
        for reaction in message.reactions:
            if ((isinstance(reaction.emoji, str) and ord(str(reaction.emoji)) == skull_data["emoji_id"]) or 
                (hasattr(reaction.emoji, 'id') and reaction.emoji.id == skull_data["emoji_id"])):
                
                if reaction.count >= (skull_data["count"] or 3):
                    embed = Embed(
                        color=message.embeds[0].color if message.embeds else 0x2f3136,
                        title=message.embeds[0].title if message.embeds else None,
                        description=message.embeds[0].description if message.embeds else message.content,
                        timestamp=message.created_at
                    )
                    
                    if message.embeds and message.embeds[0].image:
                        embed.set_image(url=message.embeds[0].image.url)
                    if message.embeds and message.embeds[0].footer:
                        embed.set_footer(text=message.embeds[0].footer.text, icon_url=message.embeds[0].footer.icon_url)
                    
                    embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
                    
                    files = []
                    if message.attachments:
                        if message.attachments[0].url.endswith(('.mp4', '.mov')):
                            try:
                                async with aiohttp.ClientSession() as session:
                                    async with session.get(message.attachments[0].url) as resp:
                                        if resp.status == 200:
                                            data = await resp.read()
                                            files.append(discord.File(io.BytesIO(data), filename=message.attachments[0].filename))
                            except:
                                pass
                        else:
                            embed.set_image(url=message.attachments[0].url)
                    
                    view = discord.ui.View()
                    view.add_item(discord.ui.Button(label="Message", style=discord.ButtonStyle.link, url=message.jump_url))
                    
                    skull_msg = await skull_channel.send(
                        content=f"{reaction.emoji} <#{payload.channel_id}>",
                        embed=embed,
                        view=view,
                        files=files
                    )
                    
                    await self.bot.pool.execute(
                        "INSERT INTO skullboardmes (guild_id, channel_skullboard_id, channel_message_id, message_skullboard_id, message_id) VALUES ($1, $2, $3, $4, $5)",
                        payload.guild_id, skull_channel.id, payload.channel_id, skull_msg.id, payload.message_id
                    )
                    break

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if not payload.guild_id:
            return
        
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        
        member = guild.get_member(payload.user_id)
        emoji_str = str(payload.emoji)
        
        if member and not member.bot and payload.user_id != self.bot.user.id:
            rr_data = await self.bot.pool.fetchrow(
                "SELECT role_id FROM reaction_role WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3 AND emoji = $4",
                payload.guild_id, payload.channel_id, payload.message_id, emoji_str
            )
            
            if rr_data:
                role = guild.get_role(rr_data['role_id'])
                if role:
                    try:
                        await member.remove_roles(role, reason="Reaction role removed")
                    except:
                        pass
        
        skull_data = await self.bot.pool.fetchrow("SELECT * FROM skullboard WHERE guild_id = $1", payload.guild_id)
        if not skull_data:
            return
        
        emoji_match = False
        if payload.emoji.is_unicode_emoji():
            emoji_match = ord(str(payload.emoji)) == skull_data["emoji_id"]
        elif payload.emoji.is_custom_emoji():
            emoji_match = payload.emoji.id == skull_data["emoji_id"]
        
        if not emoji_match:
            return
        
        existing = await self.bot.pool.fetchrow(
            "SELECT * FROM skullboardmes WHERE guild_id = $1 AND channel_message_id = $2 AND message_id = $3",
            payload.guild_id, payload.channel_id, payload.message_id
        )
        
        if existing:
            channel = guild.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            skull_channel = guild.get_channel(existing["channel_skullboard_id"])
            skull_message = await skull_channel.fetch_message(existing["message_skullboard_id"])
            
            for reaction in message.reactions:
                if ((isinstance(reaction.emoji, str) and ord(str(reaction.emoji)) == skull_data["emoji_id"]) or 
                    (hasattr(reaction.emoji, 'id') and reaction.emoji.id == skull_data["emoji_id"])):
                    await skull_message.edit(content=f"{reaction.emoji} <#{payload.channel_id}>")
                    break

async def setup(bot):
    await bot.add_cog(MiscEvents(bot))