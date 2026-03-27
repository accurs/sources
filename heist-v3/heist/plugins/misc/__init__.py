from discord.ext import commands
from discord.ext.commands import Cog, group, command
from discord import TextChannel, Embed, Member, Message, Button, ActionRow, PartialEmoji
import discord
from heist.framework.discord import Context
from heist.framework.script import Script
from datetime import datetime, timezone
from .events import MiscEvents
from typing import Union, Optional
import json
import asyncio
import discord
import io
import base64
import zlib

class Misc(Cog):
    def __init__(self, bot):
        self.bot = bot
    
    async def decompress_file(self, compressed_data: str) -> bytes:
        decoded = base64.b64decode(compressed_data.encode('utf-8'))
        return zlib.decompress(decoded)
    
    def humanize_time(self, seconds):
        if seconds < 60:
            return f"{seconds} seconds ago"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            days = seconds // 86400
            return f"{days} day{'s' if days != 1 else ''} ago"

    def embed_to_code(self, embed: Union[dict, Message, Embed], message: Optional[str] = None, escaped: Optional[bool] = True) -> str:
        code = "{embed}"
        msg = None
        if isinstance(embed, dict):
            message = embed.pop("message", embed.pop("content", message))
            embed = Embed.from_dict(embed)
        elif isinstance(embed, Message):
            msg = embed
            message = message or str(embed.content)
            embed = embed.embeds[0]
        if msg:
            for component in msg.components:
                if isinstance(component, (Button, discord.components.Button)):
                    if component.url:
                        substeps = "$v{button: "
                        if component.label:
                            substeps += f"{component.label} && "
                        if component.emoji:
                            substeps += f"{str(component.emoji)} && "
                        substeps += f"{component.url}}}"
                        code += substeps
                elif isinstance(component, ActionRow):
                    for child in component.children:
                        if isinstance(child, (Button, discord.components.Button)):
                            if child.url:
                                substeps = "$v{button: "
                                if child.label:
                                    substeps += f"{child.label} && "
                                if child.emoji:
                                    substeps += f"{str(child.emoji)} && "
                                substeps += f"{child.url}}}"
                                code += substeps
        if message:
            code += f"$v{{content: {message}}}"
        if embed.title:
            code += f"$v{{title: {embed.title}}}"
        if embed.description:
            code += f"$v{{description: {embed.description}}}"
        if embed.timestamp:
            code += "$v{timestamp: true}"
        if embed.url:
            code += f"$v{{url: {embed.url}}}"
        if fields := embed.fields:
            for field in fields:
                inline = " && inline" if field.inline else ""
                code += f"$v{{field: {field.name} && {field.value}{inline}}}"
        if embed.footer:
            substeps = ""
            text = embed.footer.text or ""
            icon_url = embed.footer.icon_url or ""
            substeps += f"footer: {embed.footer.text}"
            if icon_url:
                substeps += f" && {icon_url}"
            code += f"$v{{{substeps}}}"
        if embed.author:
            substeps = ""
            icon_url = embed.author.icon_url or ""
            url = embed.author.url or None
            substeps += f"author: {embed.author.name}"
            if url:
                substeps += f" && {url}"
            if icon_url:
                substeps += f" && {icon_url}"
            code += "$v{" + substeps + "}"
        if image_url := embed.image.url:
            code += f"$v{{image: {image_url}}}"
        if thumbnail_url := embed.thumbnail.url:
            code += f"$v{{thumbnail: {thumbnail_url}}}"
        if color := embed.color:
            code += f"$v{{color: #{str(color)}}}".replace("##", "#")
        if escaped:
            code = code.replace("```", "`\u200b`\u200b`")
        return code

    @group(invoke_without_command=True)
    async def welcome(self, ctx: Context):
        """View welcome message configuration"""
        await ctx.send_help(ctx.command)

    @welcome.command(name="config")
    @commands.has_permissions(manage_guild=True, manage_channels=True)
    async def welcome_cfg(self, ctx: Context):
        """View your welcome config."""
        result = await self.bot.pool.fetchrow(
            "SELECT channel_id, template FROM welcome_message WHERE guild_id = $1",
            ctx.guild.id
        )
        
        if not result:
            return await ctx.warn("No welcome message is configured.")
        
        channel = ctx.guild.get_channel(result['channel_id'])
        channel_text = f"<#{result['channel_id']}>" if channel else "Unknown Channel"

        embed = Embed(
            color=ctx.config.colors.information,
            description=f"**Channel**: {channel_text}\n```{result['template'][:1000]}{'...' if len(result['template']) > 1000 else ''}```"
        )
        
        await ctx.send(embed=embed)

    @welcome.command(name="setup", aliases=["add"])
    @commands.has_permissions(manage_guild=True, manage_channels=True)
    async def welcome_setup(self, ctx: Context, channel: TextChannel, *, template: str):
        """Setup a welcome message"""
        existing = await self.bot.pool.fetchrow(
            "SELECT 1 FROM welcome_message WHERE guild_id = $1",
            ctx.guild.id
        )
        
        if existing:
            return await ctx.warn("Welcome message already exists. Use `welcome clear` to remove it first.")
        
        await self.bot.pool.execute(
            "INSERT INTO welcome_message (guild_id, channel_id, template) VALUES ($1, $2, $3)",
            ctx.guild.id, channel.id, template
        )
        
        await ctx.approve(f"Welcome message setup for {channel.mention}")

    @welcome.command(name="clear")
    @commands.has_permissions(manage_guild=True, manage_channels=True)
    async def welcome_clear(self, ctx: Context):
        """Clear the welcome message"""
        result = await self.bot.pool.execute(
            "DELETE FROM welcome_message WHERE guild_id = $1",
            ctx.guild.id
        )
        
        if result == "DELETE 0":
            return await ctx.warn("No welcome message is configured.")
        
        await ctx.approve("Welcome message cleared.")

    @welcome.command(name="invoke")
    @commands.has_permissions(manage_guild=True, manage_channels=True)
    async def welcome_invoke(self, ctx: Context, member: Member = None):
        """Simulate a welcome message"""
        if not member:
            member = ctx.author
        
        result = await self.bot.pool.fetchrow(
            "SELECT channel_id, template FROM welcome_message WHERE guild_id = $1",
            ctx.guild.id
        )
        
        if not result:
            return await ctx.warn("No welcome message is configured.")
        
        channel = ctx.guild.get_channel(result['channel_id'])
        if not channel:
            return await ctx.warn("Welcome channel not found.")
        
        script = Script(result['template'], [member, ctx.guild])
        await script.send(channel)

    @command()
    async def afk(self, ctx: Context, *, reason: str = None):
        """Set your AFK status"""
        reason = reason or "AFK"
        
        await self.bot.pool.execute(
            "INSERT INTO afk (user_id, status, left_at) VALUES ($1, $2, $3) "
            "ON CONFLICT (user_id) DO UPDATE SET status = $2, left_at = $3",
            ctx.author.id, reason, datetime.now(timezone.utc)
        )
        
        await self.bot.redis.set(f"afk:{ctx.author.id}", {
            "status": reason,
            "left_at": datetime.now(timezone.utc).timestamp()
        }, ex=86400)

        await ctx.approve(f"You're now **afk** - {reason}")

    @command(name="setprefix")
    @commands.has_permissions(manage_guild=True)
    async def setprefix(self, ctx: Context, *, new_prefix: str):
        """Change the bot's prefix for this server"""
        if len(new_prefix) > 1:
            return await ctx.warn("Prefix cannot be longer than 1 character")
        
        await self.bot.update_guild_prefix(ctx.guild.id, new_prefix)
        await ctx.approve(f"Prefix changed to `{new_prefix}`")

    @command(aliases=["s"])
    async def snipe(self, ctx: Context, number: int = 1):
        """View deleted messages in this channel"""
        redis_key = f"snipe:{ctx.guild.id}:{ctx.channel.id}"
        cached_snipes = await self.bot.redis.get(redis_key)
        
        if cached_snipes and isinstance(cached_snipes, str):
            try:
                snipes = json.loads(cached_snipes)
            except (json.JSONDecodeError, TypeError):
                snipes = None
        else:
            snipes = None
            
        if not snipes:
            snipes = await self.bot.pool.fetch(
                "SELECT user_id, content, deleted_at, stickers, attachments, files FROM snipe.messages WHERE guild_id = $1 AND channel_id = $2 ORDER BY deleted_at DESC LIMIT 30",
                ctx.guild.id, ctx.channel.id
            )
            snipes = [dict(s) for s in snipes]
            if snipes:
                await self.bot.redis.set(redis_key, json.dumps(snipes, default=str), ex=300)
        
        if not snipes:
            return await ctx.warn("No deleted messages found")
        
        if number < 1 or number > len(snipes):
            return await ctx.warn(f"Invalid snipe number. Available: 1-{len(snipes)}")
        
        snipe = snipes[number - 1]
        user = self.bot.get_user(snipe['user_id'])
        
        if isinstance(snipe['deleted_at'], str):
            deleted_at = datetime.fromisoformat(snipe['deleted_at'].replace('Z', '+00:00'))
        else:
            deleted_at = snipe['deleted_at']
        
        seconds_ago = int((datetime.now(timezone.utc) - deleted_at).total_seconds())
        
        description = snipe['content'] or "*No content*"
        
        embed = Embed(
            color=ctx.config.colors.information,
            description=description
        )
        
        if user:
            embed.set_author(
                name=user.display_name,
                icon_url=user.display_avatar.url
            )
        
        if snipe.get('stickers'):
            try:
                stickers = json.loads(snipe['stickers'])
                sticker_text = ", ".join([f":{s['name']}:" for s in stickers])
                embed.add_field(name="Stickers", value=sticker_text, inline=False)
            except:
                pass
        
        if snipe.get('attachments'):
            try:
                attachments = json.loads(snipe['attachments'])
                attachment_text = "\n".join([f"[{a['filename']}]({a['url']})" for a in attachments])
                embed.add_field(name="Attachments", value=attachment_text, inline=False)
            except:
                pass
        
        embed.set_footer(text=f"{number}/{len(snipes)} • Deleted {self.humanize_time(seconds_ago)}")
        
        files = []
        if snipe.get('files'):
            try:
                file_data = json.loads(snipe['files'])
                for file_info in file_data:
                    try:
                        decompressed = await self.decompress_file(file_info['data'])
                        files.append(discord.File(
                            io.BytesIO(decompressed),
                            filename=file_info['filename']
                        ))
                    except:
                        pass
            except:
                pass
        
        await ctx.send(embed=embed, files=files)

    @command(aliases=["esnipe", "es"])
    async def editsnipe(self, ctx: Context, number: int = 1):
        """View edited messages in this channel"""
        redis_key = f"editsnipe:{ctx.guild.id}:{ctx.channel.id}"
        cached_edits = await self.bot.redis.get(redis_key)
        
        if cached_edits and isinstance(cached_edits, str):
            try:
                edits = json.loads(cached_edits)
            except (json.JSONDecodeError, TypeError):
                edits = None
        else:
            edits = None
            
        if not edits:
            edits = await self.bot.pool.fetch(
                "SELECT user_id, old_content, new_content, edited_at, old_stickers, new_stickers, old_attachments, new_attachments FROM snipe.edits WHERE guild_id = $1 AND channel_id = $2 ORDER BY edited_at DESC LIMIT 30",
                ctx.guild.id, ctx.channel.id
            )
            edits = [dict(e) for e in edits]
            if edits:
                await self.bot.redis.set(redis_key, json.dumps(edits, default=str), ex=300)
        
        if not edits:
            return await ctx.warn("No edited messages found")
        
        if number < 1 or number > len(edits):
            return await ctx.warn(f"Invalid edit number. Available: 1-{len(edits)}")
        
        edit = edits[number - 1]
        user = self.bot.get_user(edit['user_id'])
        
        if isinstance(edit['edited_at'], str):
            edited_at = datetime.fromisoformat(edit['edited_at'].replace('Z', '+00:00'))
        else:
            edited_at = edit['edited_at']
        
        seconds_ago = int((datetime.now(timezone.utc) - edited_at).total_seconds())
        
        old_content = edit['old_content'] or "*No content*"
        new_content = edit['new_content'] or "*No content*"
        
        embed = Embed(
            color=ctx.config.colors.information,
            description=f"**Before:** {old_content}\n**After:** {new_content}"
        )
        
        if user:
            embed.set_author(
                name=user.display_name,
                icon_url=user.display_avatar.url
            )
        
        if edit.get('old_stickers') or edit.get('new_stickers'):
            old_stickers = ""
            new_stickers = ""
            
            if edit.get('old_stickers'):
                try:
                    stickers = json.loads(edit['old_stickers'])
                    old_stickers = ", ".join([f":{s['name']}:" for s in stickers])
                except:
                    pass
            
            if edit.get('new_stickers'):
                try:
                    stickers = json.loads(edit['new_stickers'])
                    new_stickers = ", ".join([f":{s['name']}:" for s in stickers])
                except:
                    pass
            
            if old_stickers or new_stickers:
                embed.add_field(
                    name="Stickers",
                    value=f"**Before:** {old_stickers or '*None*'}\n**After:** {new_stickers or '*None*'}",
                    inline=False
                )
        
        if edit.get('old_attachments') or edit.get('new_attachments'):
            old_attachments = ""
            new_attachments = ""
            
            if edit.get('old_attachments'):
                try:
                    attachments = json.loads(edit['old_attachments'])
                    old_attachments = "\n".join([f"[{a['filename']}]({a['url']})" for a in attachments])
                except:
                    pass
            
            if edit.get('new_attachments'):
                try:
                    attachments = json.loads(edit['new_attachments'])
                    new_attachments = "\n".join([f"[{a['filename']}]({a['url']})" for a in attachments])
                except:
                    pass
            
            if old_attachments or new_attachments:
                embed.add_field(
                    name="Attachments",
                    value=f"**Before:**\n{old_attachments or '*None*'}\n**After:**\n{new_attachments or '*None*'}",
                    inline=False
                )
        
        embed.set_footer(text=f"{number}/{len(edits)} • Edited {self.humanize_time(seconds_ago)}")
        
        await ctx.send(embed=embed)

    @command(aliases=["cs"])
    @commands.has_permissions(manage_messages=True)
    async def clearsnipe(self, ctx: Context):
        """Clear all snipes in this channel"""
        await self.bot.pool.execute(
            "DELETE FROM snipe.messages WHERE guild_id = $1 AND channel_id = $2",
            ctx.guild.id, ctx.channel.id
        )
        await self.bot.redis.delete(f"snipe:{ctx.guild.id}:{ctx.channel.id}")
        await ctx.approve("Cleared all snipes in this channel")

    @command(aliases=["ces"])
    @commands.has_permissions(manage_messages=True)
    async def cleareditsnipe(self, ctx: Context):
        """Clear all editsnipes in this channel"""
        await self.bot.pool.execute(
            "DELETE FROM snipe.edits WHERE guild_id = $1 AND channel_id = $2",
            ctx.guild.id, ctx.channel.id
        )
        await self.bot.redis.delete(f"editsnipe:{ctx.guild.id}:{ctx.channel.id}")
        await ctx.approve("Cleared all editsnipes in this channel")

    @group(invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def snipefilter(self, ctx: Context):
        """View snipe filter configuration"""
        redis_key = f"snipe_filter:{ctx.guild.id}"
        cached_filter = await self.bot.redis.get(redis_key)
        
        if cached_filter and isinstance(cached_filter, str):
            try:
                result = json.loads(cached_filter)
            except (json.JSONDecodeError, TypeError):
                result = None
        else:
            result = None
            
        if not result:
            result = await self.bot.pool.fetchrow(
                "SELECT invites, links, words FROM snipe.filter WHERE guild_id = $1",
                ctx.guild.id
            )
            if result:
                result = dict(result)
                await self.bot.redis.set(redis_key, json.dumps(result), ex=3600)
        
        if not result:
            return await ctx.warn("No snipe filters configured")
        
        filters = []
        if result['invites']:
            filters.append("Invites")
        if result['links']:
            filters.append("Links")
        if result['words']:
            filters.append(f"Words: {', '.join(result['words'])}")
        
        if not filters:
            return await ctx.warn("No snipe filters enabled")
        
        embed = Embed(
            color=ctx.config.colors.information,
            title="Snipe Filters",
            description="\n".join(f"• {f}" for f in filters)
        )
        await ctx.send(embed=embed)

    @snipefilter.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def snipefilter_add(self, ctx: Context, filter_type: str, *, value: str = None):
        """Add a snipe filter"""
        filter_type = filter_type.lower()
        
        if filter_type not in ['invites', 'links', 'words']:
            return await ctx.warn("Invalid filter type. Use: invites, links, or words")
        
        if filter_type == 'words' and not value:
            return await ctx.warn("Word filter requires a word to filter")
        
        existing = await self.bot.pool.fetchrow(
            "SELECT 1 FROM snipe.filter WHERE guild_id = $1",
            ctx.guild.id
        )
        
        if not existing:
            await self.bot.pool.execute(
                "INSERT INTO snipe.filter (guild_id) VALUES ($1)",
                ctx.guild.id
            )
        
        if filter_type in ['invites', 'links']:
            await self.bot.pool.execute(
                f"UPDATE snipe.filter SET {filter_type} = true WHERE guild_id = $1",
                ctx.guild.id
            )
            await self.bot.redis.delete(f"snipe_filter:{ctx.guild.id}")
            await ctx.approve(f"Added {filter_type} filter")
        else:
            current_words = await self.bot.pool.fetchval(
                "SELECT words FROM snipe.filter WHERE guild_id = $1",
                ctx.guild.id
            ) or []
            
            if value.lower() in [w.lower() for w in current_words]:
                return await ctx.warn("Word already in filter")
            
            current_words.append(value.lower())
            await self.bot.pool.execute(
                "UPDATE snipe.filter SET words = $1 WHERE guild_id = $2",
                current_words, ctx.guild.id
            )
            await self.bot.redis.delete(f"snipe_filter:{ctx.guild.id}")
            await ctx.approve(f"Added word filter: {value}")

    @snipefilter.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def snipefilter_remove(self, ctx: Context, filter_type: str, *, value: str = None):
        """Remove a snipe filter"""
        filter_type = filter_type.lower()
        
        if filter_type not in ['invites', 'links', 'words']:
            return await ctx.warn("Invalid filter type. Use: invites, links, or words")
        
        redis_key = f"snipe_filter:{ctx.guild.id}"
        cached_filter = await self.bot.redis.get(redis_key)
        
        if cached_filter and isinstance(cached_filter, str):
            try:
                result = json.loads(cached_filter)
            except (json.JSONDecodeError, TypeError):
                result = None
        else:
            result = None
            
        if not result:
            result = await self.bot.pool.fetchrow(
                "SELECT invites, links, words FROM snipe.filter WHERE guild_id = $1",
                ctx.guild.id
            )
            if result:
                result = dict(result)
                await self.bot.redis.set(redis_key, json.dumps(result), ex=3600)
        
        if not result:
            return await ctx.warn("No snipe filters configured")
        
        if filter_type in ['invites', 'links']:
            if not result[filter_type]:
                return await ctx.warn(f"{filter_type.title()} filter is not enabled")
            
            await self.bot.pool.execute(
                f"UPDATE snipe.filter SET {filter_type} = false WHERE guild_id = $1",
                ctx.guild.id
            )
            await self.bot.redis.delete(f"snipe_filter:{ctx.guild.id}")
            await ctx.approve(f"Removed {filter_type} filter")
        else:
            if not value:
                return await ctx.warn("Word filter requires a word to remove")
            
            current_words = result['words'] or []
            word_lower = value.lower()
            
            if word_lower not in [w.lower() for w in current_words]:
                return await ctx.warn("Word not found in filter")
            
            current_words = [w for w in current_words if w.lower() != word_lower]
            await self.bot.pool.execute(
                "UPDATE snipe.filter SET words = $1 WHERE guild_id = $2",
                current_words, ctx.guild.id
            )
            await self.bot.redis.delete(f"snipe_filter:{ctx.guild.id}")
            await ctx.approve(f"Removed word filter: {value}")

    @group(name="boosterrole", aliases=["boosterroles", "br"], invoke_without_command=True)
    async def boosterrole(self, ctx: Context):
        """Make your own role as a reward for boosting the server"""
        await ctx.send_help(ctx.command)



    async def is_booster(self, ctx: Context):
        if not ctx.author.premium_since:
            await ctx.warn("You must be a server booster to use this command")
            return False
        return True

    @boosterrole.command(name="create", aliases=["c"])
    async def boosterrole_create(self, ctx: Context, color: str, *, name: str):
        """Create a new booster role"""
        if not await self.is_booster(ctx):
            return

        existing = await self.bot.pool.fetchval(
            "SELECT role_id FROM booster_role WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id
        )
        if existing:
            return await ctx.warn("You already have a booster role.")

        color_map = {
            "red": discord.Color.red(),
            "blue": discord.Color.blue(),
            "green": discord.Color.green(),
            "yellow": discord.Color.yellow(),
            "orange": discord.Color.orange(),
            "purple": discord.Color.purple(),
            "teal": discord.Color.teal(),
            "magenta": discord.Color.magenta(),
            "gold": discord.Color.gold(),
            "dark_red": discord.Color.dark_red(),
            "dark_blue": discord.Color.dark_blue(),
            "dark_green": discord.Color.dark_green(),
            "dark_purple": discord.Color.dark_purple(),
            "light_gray": discord.Color.light_gray(),
            "dark_gray": discord.Color.dark_gray(),
            "blurple": discord.Color.blurple(),
        }

        color = color.lower()
        if color.startswith("#"):
            try:
                color_value = discord.Color(int(color.replace("#", ""), 16))
            except Exception:
                color_value = discord.Color.default()
        else:
            color_value = color_map.get(color, discord.Color.default())

        role = await ctx.guild.create_role(name=name, color=color_value, reason="Booster role creation")

        booster_role = discord.utils.find(lambda r: "Server Booster" in r.name, ctx.guild.roles)
        if booster_role:
            try:
                await role.edit(position=booster_role.position + 1)
            except discord.Forbidden:
                pass

        await self.bot.pool.execute(
            "INSERT INTO booster_role (guild_id, user_id, role_id, shared, multi_boost_enabled) VALUES ($1, $2, $3, $4, $5)",
            ctx.guild.id, ctx.author.id, role.id, False, False
        )

        await ctx.author.add_roles(role, reason="Booster role created")
        await ctx.approve(f"successfully assigned you {role.mention} as your booster role")

    @boosterrole.command(name="hoist", aliases=["display"])
    async def boosterrole_hoist(self, ctx: Context):
        """Toggle whether your booster role is hoisted"""
        if not await self.is_booster(ctx):
            return

        role_id = await self.bot.pool.fetchval(
            "SELECT role_id FROM booster_role WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id
        )
        if not role_id:
            return await ctx.warn("You do not have a booster role.")

        role = ctx.guild.get_role(role_id)
        if not role:
            return await ctx.warn("Your booster role has been **DELETED**.")

        new_state = not role.hoist
        await role.edit(hoist=new_state, reason=f"Booster role hoist toggled by {ctx.author}.")
        
        state_text = "now **displayed separately**" if new_state else "no longer displayed separately"
        await ctx.approve(f"{role.mention} is {state_text}.")

    @boosterrole.command(name="color")
    async def boosterrole_color(self, ctx: Context, *, color: str):
        """Change the color of your booster role"""
        if not await self.is_booster(ctx):
            return
        
        role_id = await self.bot.pool.fetchval(
            "SELECT role_id FROM booster_role WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, ctx.author.id
        )
        if not role_id:
            return await ctx.warn("You do not have a booster role.")
        
        role = ctx.guild.get_role(role_id)
        if not role:
            return await ctx.warn("Your booster role has been **DELETED**.")

        color_map = {
            "red": discord.Color.red(),
            "blue": discord.Color.blue(),
            "green": discord.Color.green(),
            "yellow": discord.Color.yellow(),
            "orange": discord.Color.orange(),
            "purple": discord.Color.purple(),
            "teal": discord.Color.teal(),
            "magenta": discord.Color.magenta(),
            "gold": discord.Color.gold(),
            "dark_red": discord.Color.dark_red(),
            "dark_blue": discord.Color.dark_blue(),
            "dark_green": discord.Color.dark_green(),
            "dark_purple": discord.Color.dark_purple(),
            "light_gray": discord.Color.light_gray(),
            "dark_gray": discord.Color.dark_gray(),
            "blurple": discord.Color.blurple(),
        }

        color = color.lower().strip()
        if color.startswith("#"):
            try:
                color_value = discord.Color(int(color.replace("#", ""), 16))
            except ValueError:
                return await ctx.warn("Invalid hex color format.")
        else:
            color_value = color_map.get(color)
            if not color_value:
                return await ctx.warn("Invalid color name or format")

        await role.edit(color=color_value, reason=f"Booster role recolored by {ctx.author}")
        await ctx.approve(f"Successfully re-colored your role to {str(color_value)}")

    @boosterrole.command(name="share")
    async def boosterrole_share(self, ctx: Context, *, member: discord.Member):
        """Share your booster roles with other users"""
        if not await self.is_booster(ctx):
            return
        
        role_id = await self.bot.pool.fetchval("SELECT role_id FROM booster_role WHERE guild_id = $1 AND user_id = $2", ctx.guild.id, ctx.author.id)
        if not role_id:
            return await ctx.warn("You do not have a booster role.")
        
        role = ctx.guild.get_role(role_id)
        if not role:
            return await ctx.warn("Your booster role has been **DELETED**.")
        
        if member.id == ctx.author.id:
            return await ctx.warn("You cannot share your booster role to yourself.")
        
        await member.add_roles(role, reason="Booster Role Shared")
        await self.bot.pool.execute("UPDATE booster_role SET shared = $1 WHERE guild_id = $2 AND user_id = $3", True, ctx.guild.id, ctx.author.id)
        await ctx.approve(f"successfully shared your booster role with {member.mention}")

    @boosterrole.command(name="cleanup")
    @commands.has_permissions(manage_roles=True)
    async def boosterrole_cleanup(self, ctx: Context):
        """Cleanup unused booster roles"""
        roles = await self.bot.pool.fetch("SELECT role_id FROM booster_role WHERE guild_id = $1", ctx.guild.id)
        if not roles:
            return await ctx.warn("there are no booster roles")
        
        delete = []
        cleanable_roles = []
        
        for record in roles:
            role = ctx.guild.get_role(record["role_id"])
            if not role:
                delete.append(record["role_id"])
                continue
            
            members = [m for m in role.members if m.premium_since]
            if len(members) == 0:
                cleanable_roles.append(role)
                delete.append(record["role_id"])
        
        if not cleanable_roles:
            return await ctx.warn("there are no unused booster roles")
        
        for role in cleanable_roles:
            await role.delete(reason="Booster Role Cleanup")
        
        if delete:
            await self.bot.pool.execute("DELETE FROM booster_role WHERE guild_id = $1 AND role_id = ANY($2)", ctx.guild.id, delete)
        
        await ctx.approve(f"successfully cleaned up `{len(cleanable_roles)}` **booster roles**")

    @boosterrole.command(name="name")
    async def boosterrole_name(self, ctx: Context, *, name: str):
        """Rename your booster role"""
        if not await self.is_booster(ctx):
            return
        
        role_id = await self.bot.pool.fetchval("SELECT role_id FROM booster_role WHERE guild_id = $1 AND user_id = $2", ctx.guild.id, ctx.author.id)
        if not role_id:
            return await ctx.warn("You do not have a booster role.")
        
        role = ctx.guild.get_role(role_id)
        if not role:
            return await ctx.warn("your booster role has been **DELETED**")
        
        await role.edit(name=name)
        await ctx.approve(f"successfully renamed your booster role to **{name}**")

    @boosterrole.command(name="delete", aliases=["remove"])
    async def boosterrole_delete(self, ctx: Context):
        """Delete your booster role"""
        if not await self.is_booster(ctx):
            return
        
        role_id = await self.bot.pool.fetchval("SELECT role_id FROM booster_role WHERE guild_id = $1 AND user_id = $2", ctx.guild.id, ctx.author.id)
        if not role_id:
            return await ctx.warn("You do not have a booster role.")
        
        role = ctx.guild.get_role(role_id)
        if role:
            await role.delete(reason="Booster role deleted by owner")
        
        await self.bot.pool.execute("DELETE FROM booster_role WHERE guild_id = $1 AND user_id = $2", ctx.guild.id, ctx.author.id)
        await ctx.approve("successfully deleted your booster role")

    @group(invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def pingonjoin(self, ctx: Context):
        """View pingonjoin configuration"""
        config = await self.bot.pool.fetchrow("SELECT * FROM pingonjoin.config WHERE guild_id = $1", ctx.guild.id)
        if not config:
            return await ctx.warn("Pingonjoin is not configured")
        
        channel = ctx.guild.get_channel(config["channel_id"])
        delete_info = "No" if not config["delete_ping"] else ("Instant" if config["delete_after"] == 0 else f"{config['delete_after']}s")
        
        embed = Embed(color=ctx.config.colors.information, title="Pingonjoin Configuration")
        embed.add_field(name="Channel", value=channel.mention if channel else "Unknown")
        embed.add_field(name="Delete Ping", value=delete_info)
        await ctx.send(embed=embed)

    @pingonjoin.command(name="set")
    @commands.has_permissions(manage_guild=True)
    async def pingonjoin_set(self, ctx: Context, channel: TextChannel, delete: bool = False, delete_after: str = None):
        """Set pingonjoin channel and deletion settings"""
        delete_seconds = None
        
        if delete and delete_after:
            if delete_after.lower() == "instant":
                delete_seconds = 0
            else:
                try:
                    if delete_after.endswith('s'):
                        delete_seconds = int(delete_after[:-1])
                    elif delete_after.endswith('m'):
                        delete_seconds = int(delete_after[:-1]) * 60
                    elif delete_after.endswith('h'):
                        delete_seconds = int(delete_after[:-1]) * 3600
                    else:
                        delete_seconds = int(delete_after)
                except ValueError:
                    return await ctx.warn("Invalid time format. Use: instant, 5s, 10m, 1h, or just a number")
        elif delete and not delete_after:
            return await ctx.warn("Delete time is required when delete is enabled")
        
        await self.bot.pool.execute(
            "INSERT INTO pingonjoin.config (guild_id, channel_id, delete_ping, delete_after) VALUES ($1, $2, $3, $4) ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2, delete_ping = $3, delete_after = $4",
            ctx.guild.id, channel.id, delete, delete_seconds
        )
        
        delete_info = "disabled" if not delete else ("instant" if delete_seconds == 0 else f"after {delete_after}")
        await ctx.approve(f"Pingonjoin set to {channel.mention} with deletion {delete_info}")

    @pingonjoin.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def pingonjoin_remove(self, ctx: Context):
        """Remove pingonjoin configuration"""
        result = await self.bot.pool.execute("DELETE FROM pingonjoin.config WHERE guild_id = $1", ctx.guild.id)
        if result == "DELETE 0":
            return await ctx.warn("Pingonjoin is not configured")
        await ctx.approve("Pingonjoin configuration removed")

    @command(
        name="embedcode",
        description="get the code of an already existing embed",
        example=",embedcode .../channels/...",
    )
    @commands.has_permissions(manage_messages=True)
    async def embedcode(self, ctx: Context, message: Message = None):
        target_message = message or ctx.message.reference.resolved if ctx.message.reference else None
        if not target_message:
            return await ctx.warn("Reply to a message or provide a message link")
        code = self.embed_to_code(target_message)
        return await ctx.approve(
            f"**Successfully copied the embed code**\n```{code}```"
        )

    @group(invoke_without_command=True, aliases=["rr"])
    async def reactionrole(self, ctx: Context):
        """Manage reaction roles"""
        await ctx.send_help(ctx.command)

    @reactionrole.command(name="add")
    @commands.has_permissions(manage_roles=True)
    async def rr_add(self, ctx: Context, message_id: int, channel: TextChannel, emoji: Union[discord.Emoji, str], *, role: Union[discord.Role, str]):
        """Add a reaction role to a message"""
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            return await ctx.warn("Message not found")
        
        if isinstance(role, str):
            role = discord.utils.get(ctx.guild.roles, name=role)
            if not role:
                return await ctx.warn("Role not found")
        
        emoji_str = str(emoji)
        
        check = await self.bot.pool.fetchrow(
            "SELECT 1 FROM reaction_role WHERE guild_id = $1 AND message_id = $2 AND channel_id = $3 AND emoji = $4",
            ctx.guild.id, message.id, channel.id, emoji_str
        )
        if check:
            return await ctx.warn("A reaction role with this emoji already exists on this message")
        
        try:
            await message.add_reaction(emoji)
            await self.bot.pool.execute(
                "INSERT INTO reaction_role (guild_id, channel_id, message_id, role_id, emoji) VALUES ($1, $2, $3, $4, $5)",
                ctx.guild.id, channel.id, message.id, role.id, emoji_str
            )
            await ctx.approve(f"Added reaction role {emoji} for {role.mention}")
        except discord.Forbidden:
            await ctx.warn("I don't have permission to add reactions or manage this role")
        except Exception:
            await ctx.warn("Unable to add reaction role")

    @reactionrole.command(name="remove")
    @commands.has_permissions(manage_roles=True)
    async def rr_remove(self, ctx: Context, message_id: int, channel: TextChannel, emoji: Union[discord.Emoji, str]):
        """Remove a reaction role from a message"""
        emoji_str = str(emoji)
        
        check = await self.bot.pool.fetchrow(
            "SELECT 1 FROM reaction_role WHERE guild_id = $1 AND message_id = $2 AND channel_id = $3 AND emoji = $4",
            ctx.guild.id, message_id, channel.id, emoji_str
        )
        if not check:
            return await ctx.warn("No reaction role found with the given arguments")
        
        await self.bot.pool.execute(
            "DELETE FROM reaction_role WHERE guild_id = $1 AND message_id = $2 AND channel_id = $3 AND emoji = $4",
            ctx.guild.id, message_id, channel.id, emoji_str
        )
        await ctx.approve("Removed reaction role")

    @reactionrole.command(name="removeall")
    @commands.has_permissions(manage_roles=True)
    async def rr_removeall(self, ctx: Context, channel: TextChannel = None):
        """Remove all reaction roles from the server or a specific channel"""
        if channel:
            result = await self.bot.pool.execute(
                "DELETE FROM reaction_role WHERE guild_id = $1 AND channel_id = $2",
                ctx.guild.id, channel.id
            )
            if result == "DELETE 0":
                return await ctx.warn(f"No reaction roles found in {channel.mention}")
            await ctx.approve(f"Removed all reaction roles from {channel.mention}")
        else:
            result = await self.bot.pool.execute(
                "DELETE FROM reaction_role WHERE guild_id = $1",
                ctx.guild.id
            )
            if result == "DELETE 0":
                return await ctx.warn("No reaction roles found in this server")
            await ctx.approve("Removed all reaction roles from this server")

    @reactionrole.command(name="list")
    async def rr_list(self, ctx: Context):
        """List all reaction roles in the server"""
        results = await self.bot.pool.fetch(
            "SELECT * FROM reaction_role WHERE guild_id = $1",
            ctx.guild.id
        )
        
        if not results:
            return await ctx.warn("No reaction roles found")
        
        embeds = []
        entries = []
        
        for result in results:
            channel = ctx.guild.get_channel(result['channel_id'])
            role = ctx.guild.get_role(result['role_id'])
            
            if not channel or not role:
                continue
            
            try:
                message = await channel.fetch_message(result['message_id'])
                message_link = message.jump_url
            except:
                message_link = "Message not found"
            
            entries.append(f"{result['emoji']} - {role.mention} [message link]({message_link})")
        
        if not entries:
            return await ctx.warn("No valid reaction roles found")
        
        pages = [entries[i:i+10] for i in range(0, len(entries), 10)]
        
        for i, page in enumerate(pages):
            embed = Embed(
                color=ctx.config.colors.information,
                title=f"Reaction Roles ({len(entries)})",
                description="\n".join(f"`{j+1+(i*10)}` {entry}" for j, entry in enumerate(page))
            )
            embeds.append(embed)
        
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            from heist.framework.pagination import Paginator
            paginator = Paginator(ctx, embeds)
            await paginator.start()

    @group(invoke_without_command=True)
    async def skull(self, ctx: Context):
        """Manage skullboard"""
        await ctx.send_help(ctx.command)

    @skull.command(name="count", aliases=["amount"])
    @commands.has_permissions(manage_guild=True)
    async def skull_count(self, ctx: Context, count: int):
        """Set the skullboard reaction count"""
        if count < 1:
            return await ctx.warn("Count can't be less than 1")
        
        await self.bot.pool.execute(
            "INSERT INTO skullboard (guild_id, count) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET count = $2",
            ctx.guild.id, count
        )
        await ctx.approve(f"Skull count set to **{count}**")

    @skull.command(name="channel")
    @commands.has_permissions(manage_guild=True)
    async def skull_channel(self, ctx: Context, *, channel: TextChannel):
        """Set the skullboard channel"""
        await self.bot.pool.execute(
            "INSERT INTO skullboard (guild_id, channel_id) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2",
            ctx.guild.id, channel.id
        )
        await ctx.approve(f"Skullboard channel set to {channel.mention}")

    @skull.command(name="remove", aliases=["disable"])
    @commands.has_permissions(manage_guild=True)
    async def skull_remove(self, ctx: Context):
        """Remove skullboard"""
        check = await self.bot.pool.fetchrow("SELECT 1 FROM skullboard WHERE guild_id = $1", ctx.guild.id)
        if not check:
            return await ctx.warn("Skullboard is not enabled")
        
        await self.bot.pool.execute("DELETE FROM skullboard WHERE guild_id = $1", ctx.guild.id)
        await self.bot.pool.execute("DELETE FROM skullboardmes WHERE guild_id = $1", ctx.guild.id)
        await ctx.approve("Disabled skullboard successfully")

    @skull.command(name="stats", aliases=["settings", "status"])
    @commands.has_permissions(manage_guild=True)
    async def skull_stats(self, ctx: Context):
        """Check skullboard settings"""
        check = await self.bot.pool.fetchrow("SELECT * FROM skullboard WHERE guild_id = $1", ctx.guild.id)
        if not check:
            return await ctx.warn("Skullboard is not enabled")
        
        embed = Embed(color=ctx.config.colors.information, title="Skullboard Settings")
        
        if check["channel_id"]:
            channel = ctx.guild.get_channel(check["channel_id"])
            embed.add_field(name="Channel", value=channel.mention if channel else "Unknown")
        
        if check["count"]:
            embed.add_field(name="Amount", value=check["count"])
        
        if check["emoji_text"]:
            embed.add_field(name="Emoji", value=check["emoji_text"])
        
        await ctx.send(embed=embed)

    @skull.command(name="emoji")
    @commands.has_permissions(manage_guild=True)
    async def skull_emoji(self, ctx: Context, emoji: Union[discord.PartialEmoji, str]):
        """Set the skullboard emoji"""
        emoji_id = emoji.id if isinstance(emoji, discord.PartialEmoji) else ord(str(emoji))
        
        await self.bot.pool.execute(
            "INSERT INTO skullboard (guild_id, emoji_id, emoji_text) VALUES ($1, $2, $3) ON CONFLICT (guild_id) DO UPDATE SET emoji_id = $2, emoji_text = $3",
            ctx.guild.id, emoji_id, str(emoji)
        )
        await ctx.approve(f"Skullboard emoji set to {emoji}")

    @group(invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def joindm(self, ctx: Context):
        """View joindm configuration"""
        config = await self.bot.pool.fetchrow("SELECT * FROM joindm.config WHERE guild_id = $1", ctx.guild.id)
        if not config:
            return await ctx.warn("Joindm is not configured")
        
        status = "Enabled" if config["enabled"] else "Disabled"
        embed = Embed(color=ctx.config.colors.information, title="Joindm Configuration")
        embed.add_field(name="Status", value=status)
        embed.add_field(name="Message", value=config["message"] or "None")
        await ctx.send(embed=embed)

    @joindm.command(name="set")
    @commands.has_permissions(manage_guild=True)
    async def joindm_set(self, ctx: Context, *, message: str):
        """Set joindm message"""
        await self.bot.pool.execute(
            "INSERT INTO joindm.config (guild_id, message, enabled) VALUES ($1, $2, true) ON CONFLICT (guild_id) DO UPDATE SET message = $2, enabled = true",
            ctx.guild.id, message
        )
        await ctx.approve(f"Joindm message set and enabled")

    @joindm.command(name="disable")
    @commands.has_permissions(manage_guild=True)
    async def joindm_disable(self, ctx: Context):
        """Disable joindm"""
        result = await self.bot.pool.execute(
            "UPDATE joindm.config SET enabled = false WHERE guild_id = $1",
            ctx.guild.id
        )
        if result == "UPDATE 0":
            return await ctx.warn("Joindm is not configured")
        await ctx.approve("Joindm disabled")

    @joindm.command(name="enable")
    @commands.has_permissions(manage_guild=True)
    async def joindm_enable(self, ctx: Context):
        """Enable joindm"""
        config = await self.bot.pool.fetchrow("SELECT message FROM joindm.config WHERE guild_id = $1", ctx.guild.id)
        if not config or not config["message"]:
            return await ctx.warn("Set a joindm message first")
        
        await self.bot.pool.execute(
            "UPDATE joindm.config SET enabled = true WHERE guild_id = $1",
            ctx.guild.id
        )
        await ctx.approve("Joindm enabled")

    @joindm.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def joindm_remove(self, ctx: Context):
        """Remove joindm configuration"""
        result = await self.bot.pool.execute("DELETE FROM joindm.config WHERE guild_id = $1", ctx.guild.id)
        if result == "DELETE 0":
            return await ctx.warn("Joindm is not configured")
        await ctx.approve("Joindm configuration removed")

async def setup(bot):
    from .help import Help
    await bot.add_cog(Misc(bot))
    await bot.add_cog(MiscEvents(bot))
    await bot.add_cog(Help(bot))