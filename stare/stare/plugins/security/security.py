import discord
from discord.ext import commands
from discord import Member, User, Embed, Role, AuditLogAction, Guild
from discord.abc import GuildChannel
import datetime
import humanfriendly
import json
from typing import Union
from stare.core.config import Config
from stare.core.tools.context import CustomContext as Context


class Security(commands.Cog):
    """Security commands"""
    massjoin_cooldown = 10
    massjoin_cache = {}
    antinuke_cache = {}
    
    def __init__(self, bot):
        self.bot = bot
    
    def is_dangerous_permission(self, permissions: discord.Permissions) -> bool:
        dangerous = [
            'administrator',
            'kick_members',
            'ban_members',
            'manage_guild',
            'manage_roles',
            'manage_channels',
            'manage_webhooks',
            'mention_everyone'
        ]
        return any(getattr(permissions, perm, False) for perm in dangerous)
    
    def check_hierarchy(self, user: Member, bot_member: Member) -> bool:
        if user.id == user.guild.owner_id:
            return False
        return user.top_role < bot_member.top_role
    
    async def is_antinuke_owner(self, guild_id: int, user_id: int) -> bool:
        check = await self.bot.db_pool.fetchrow(
            "SELECT owner_id FROM antinuke WHERE guild_id = $1", guild_id
        )
        if not check:
            return user_id == self.bot.get_guild(guild_id).owner_id
        return check['owner_id'] == user_id
    
    async def is_antinuke_admin(self, guild_id: int, user_id: int) -> bool:
        if await self.is_antinuke_owner(guild_id, user_id):
            return True
        check = await self.bot.db_pool.fetchrow(
            "SELECT admins FROM antinuke WHERE guild_id = $1", guild_id
        )
        if check and check['admins']:
            admins = json.loads(check['admins'])
            return user_id in admins
        return False
    
    async def is_antinuke_whitelisted(self, guild_id: int, user_id: int) -> bool:
        check = await self.bot.db_pool.fetchrow(
            "SELECT whitelisted FROM antinuke WHERE guild_id = $1", guild_id
        )
        if check and check['whitelisted']:
            whitelisted = json.loads(check['whitelisted'])
            return user_id in whitelisted
        return False
    
    async def is_antinuke_module_enabled(self, guild_id: int, module: str) -> bool:
        check = await self.bot.db_pool.fetchrow(
            "SELECT * FROM antinuke_modules WHERE guild_id = $1 AND module = $2",
            guild_id, module
        )
        return check is not None
    
    async def cog_load(self):
        if not self.bot.db_pool:
            return
        
        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS antiraid (
                guild_id BIGINT,
                command TEXT,
                punishment TEXT,
                seconds INTEGER,
                PRIMARY KEY (guild_id, command)
            )
        """)
        
        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS whitelist (
                guild_id BIGINT,
                module TEXT,
                object_id BIGINT,
                mode TEXT,
                PRIMARY KEY (guild_id, module, object_id, mode)
            )
        """)
        
        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS antinuke (
                guild_id BIGINT PRIMARY KEY,
                owner_id BIGINT,
                configured TEXT DEFAULT 'false',
                whitelisted TEXT,
                admins TEXT,
                logs BIGINT
            )
        """)
        
        await self.bot.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS antinuke_modules (
                guild_id BIGINT,
                module TEXT,
                punishment TEXT,
                threshold INTEGER,
                PRIMARY KEY (guild_id, module)
            )
        """)
    
    @commands.Cog.listener("on_member_join")
    async def check_for_avatar(self, member: Member):
        if member.avatar is None:
            res = await self.bot.db_pool.fetchrow(
                "SELECT * FROM antiraid WHERE command = $1 AND guild_id = $2",
                "Default Avatar",
                member.guild.id,
            )
            if res is not None:
                res1 = await self.bot.db_pool.fetchrow(
                    "SELECT * FROM whitelist WHERE guild_id = $1 AND module = $2 AND object_id = $3 AND mode = $4",
                    member.guild.id,
                    "Default Avatar",
                    member.id,
                    "user",
                )
                if res1:
                    return
                if res["punishment"] == "kick":
                    await member.kick(reason="Antiraid: This user does not have a custom avatar.")
                elif res["punishment"] == "ban":
                    await member.ban(reason="Antiraid: This user does not have a custom avatar.")
    
    @commands.Cog.listener("on_member_join")
    async def new_accounts(self, member: Member):
        res = await self.bot.db_pool.fetchrow(
            "SELECT * FROM antiraid WHERE command = $1 AND guild_id = $2",
            "New Accounts",
            member.guild.id,
        )
        if not res:
            return
        
        res1 = await self.bot.db_pool.fetchrow(
            "SELECT * FROM whitelist WHERE guild_id = $1 AND module = $2 AND object_id = $3 AND mode = $4",
            member.guild.id,
            "New Accounts",
            member.id,
            "user",
        )
        if res1:
            return
        
        account_age_seconds = (datetime.datetime.utcnow() - member.created_at.replace(tzinfo=None)).total_seconds()
        
        if account_age_seconds < int(res["seconds"]):
            if res["punishment"] == "kick":
                await member.kick(reason="Antiraid: The account is too young, suspected alt.")
            elif res["punishment"] == "ban":
                await member.ban(reason="Antiraid: The account is too young, suspected alt.")
    
    @commands.Cog.listener("on_member_join")
    async def mass_joins(self, member: Member):
        res = await self.bot.db_pool.fetchrow(
            "SELECT * FROM antiraid WHERE command = $1 AND guild_id = $2",
            "massjoin",
            member.guild.id,
        )
        if res:
            if not self.massjoin_cache.get(str(member.guild.id)):
                self.massjoin_cache[str(member.guild.id)] = []
            
            self.massjoin_cache[str(member.guild.id)].append(tuple([datetime.datetime.now(), member.id]))
            
            expired = [
                mem
                for mem in self.massjoin_cache[str(member.guild.id)]
                if (datetime.datetime.now() - mem[0]).total_seconds() > self.massjoin_cooldown
            ]
            for m in expired:
                self.massjoin_cache[str(member.guild.id)].remove(m)
            
            if len(self.massjoin_cache[str(member.guild.id)]) > res["seconds"]:
                members = [me[1] for me in self.massjoin_cache[str(member.guild.id)]]
                for mem in members:
                    if res["punishment"] == "ban":
                        try:
                            await member.guild.ban(
                                user=self.bot.get_user(mem),
                                reason="AntiRaid: Join raid triggered",
                            )
                        except:
                            continue
                    else:
                        try:
                            await member.guild.kick(
                                user=member.guild.get_member(mem),
                                reason="AntiRaid: Join raid triggered",
                            )
                        except:
                            continue
    
    @commands.group(name="antiraid", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def antiraid(self, ctx: Context):
        return await ctx.send_help(ctx.command)
    
    @antiraid.command(name="settings", aliases=["stats", "config"])
    @commands.has_permissions(manage_guild=True)
    async def antiraid_settings(self, ctx: Context):
        desc = "**Current Raid State:** "
        enabled = {
            "Mass Join": Config.EMOJIS.ERROR,
            "Default Avatar": Config.EMOJIS.ERROR,
            "New Accounts": Config.EMOJIS.ERROR,
        }
        module_details = {
            "Mass Join": {"punishment": "N/A", "seconds": "N/A"},
            "Default Avatar": {"punishment": "N/A", "seconds": "N/A"},
            "New Accounts": {"punishment": "N/A", "seconds": "N/A"},
        }
        
        res = await self.bot.db_pool.fetch(
            "SELECT command, punishment, seconds FROM antiraid WHERE guild_id = $1",
            ctx.guild.id,
        )
        
        for result in res:
            command = result["command"]
            punishment = result["punishment"]
            seconds = result["seconds"]
            
            if command in enabled:
                enabled[command] = Config.EMOJIS.SUCCESS
            
            if command == "New Accounts":
                seconds = humanfriendly.format_timespan(seconds)
            
            module_details[command] = {"punishment": punishment, "seconds": seconds}
        
        if all(status == Config.EMOJIS.SUCCESS for status in enabled.values()):
            desc += "Safe"
        else:
            desc += "Unsafe"
        
        embed = Embed(title="Antiraid Settings", color=Config.COLORS.DEFAULT, description=desc)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        
        modules_info = [
            f"**{module}:** {enabled.get(module)} (Do: **{details['punishment']}**, Threshold: **{details['seconds']}**)"
            for module, details in module_details.items()
        ]
        embed.add_field(name="Modules", value="\n".join(modules_info))
        
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        
        await ctx.reply(embed=embed)
    
    @antiraid.command(name="whitelist", aliases=["wl"])
    @commands.has_permissions(manage_guild=True)
    async def antiraid_whitelist(self, ctx: Context, *, member: Member):
        res = await self.bot.db_pool.fetchrow(
            "SELECT * FROM whitelist WHERE guild_id = $1 AND object_id = $2 AND module = $3 AND mode = $4",
            ctx.guild.id,
            member.id,
            "antiraid",
            "user",
        )
        if res:
            return await ctx.warn(f"{member.mention} is already whitelisted for **antiraid**.")
        
        await self.bot.db_pool.execute(
            "INSERT INTO whitelist VALUES ($1,$2,$3,$4)",
            ctx.guild.id,
            "antiraid",
            member.id,
            "user",
        )
        return await ctx.approve(f"{member.mention} will now be **ignored** on antiraid events.")
    
    @antiraid.command(name="unwhitelist", aliases=["unwl"])
    @commands.has_permissions(manage_guild=True)
    async def antiraid_unwhitelist(self, ctx: Context, *, member: Member):
        res = await self.bot.db_pool.fetchrow(
            "SELECT * FROM whitelist WHERE guild_id = $1 AND object_id = $2 AND module = $3 AND mode = $4",
            ctx.guild.id,
            member.id,
            "antiraid",
            "user",
        )
        if not res:
            return await ctx.warn(f"**{member.mention}** is not whitelisted for **anti raid**")
        
        await self.bot.db_pool.execute(
            "DELETE FROM whitelist WHERE guild_id = $1 AND object_id = $2 AND module = $3",
            ctx.guild.id,
            member.id,
            "antiraid",
        )
        return await ctx.approve(f"**{member.mention}** is **no longer** ignored on antiraid events.")
    
    @antiraid.group(name="massjoin", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def antiraid_massjoin(self, ctx: Context):
        return await ctx.send_help(ctx.command)
    
    @antiraid_massjoin.command(name="enable", aliases=["on"])
    @commands.has_permissions(manage_guild=True)
    async def antiraid_massjoin_enable(self, ctx: Context, *, args: str):
        split_args = args.split()
        if "--do" not in split_args or "--threshold" not in split_args:
            return await ctx.warn("Invalid syntax! Use: `;antiraid massjoin on --do <punishment> --threshold <joins>`")
        
        try:
            do_index = split_args.index("--do") + 1
            threshold_index = split_args.index("--threshold") + 1
            punishment = split_args[do_index]
            threshold = split_args[threshold_index]
            
            if punishment not in ["kick", "ban"]:
                return await ctx.warn("Punishment must be either **kick** or **ban**")
            
            joins = int(threshold)
            if joins <= 0:
                raise ValueError("Threshold must be a positive number of joins.")
        except (IndexError, ValueError):
            return await ctx.warn("Invalid syntax! `--threshold` must be a positive integer representing the join threshold.")
        
        res = await self.bot.db_pool.fetchrow(
            "SELECT * FROM antiraid WHERE guild_id = $1 AND command = $2",
            ctx.guild.id,
            "Mass Join",
        )
        
        if res:
            await self.bot.db_pool.execute(
                "UPDATE antiraid SET punishment = $1, seconds = $2 WHERE guild_id = $3 AND command = $4",
                punishment,
                joins,
                ctx.guild.id,
                "Mass Join",
            )
            return await ctx.approve(f"Updated **Massjoin** antiraid. Punishment is set to **{punishment}**, threshold is set to **{joins} joins**.")
        
        await self.bot.db_pool.execute(
            "INSERT INTO antiraid (guild_id, command, punishment, seconds) VALUES ($1, $2, $3, $4)",
            ctx.guild.id,
            "Mass Join",
            punishment,
            joins,
        )
        return await ctx.approve(f"Added **Massjoin** antiraid. Punishment is set to **{punishment}**, threshold is set to **{joins} joins**.")
    
    @antiraid_massjoin.command(name="disable", aliases=["off"])
    @commands.has_permissions(manage_guild=True)
    async def antiraid_massjoin_disable(self, ctx: Context):
        res = await self.bot.db_pool.fetchrow(
            "SELECT * FROM antiraid WHERE guild_id = $1 AND command = $2",
            ctx.guild.id,
            "Mass Join",
        )
        if not res:
            return await ctx.warn(f"Mass Join protection **isn't** enabled.")
        
        await self.bot.db_pool.execute(
            "DELETE FROM antiraid WHERE command = $1 AND guild_id = $2",
            "Mass Join",
            ctx.guild.id,
        )
        return await ctx.approve("Mass Join protection has been **disabled**")
    
    @antiraid.group(name="newaccounts", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def antiraid_newaccounts(self, ctx: Context):
        return await ctx.send_help(ctx.command)
    
    @antiraid_newaccounts.command(name="on", aliases=["enable"])
    @commands.has_permissions(manage_guild=True)
    async def newaccounts_on(self, ctx: Context, *, args: str):
        split_args = args.split()
        if "--do" not in split_args or "--threshold" not in split_args:
            return await ctx.warn("Invalid syntax! Use: `;antiraid newaccounts on --do <punishment> --threshold <days>`")
        
        try:
            do_index = split_args.index("--do") + 1
            threshold_index = split_args.index("--threshold") + 1
            punishment = split_args[do_index]
            threshold = split_args[threshold_index]
            
            if punishment not in ["kick", "ban"]:
                return await ctx.warn("Punishment must be either **kick** or **ban**")
            
            days = int(threshold)
            if days <= 0:
                raise ValueError("Threshold must be a positive number of days.")
            
            time_seconds = days * 86400
        except (IndexError, ValueError):
            return await ctx.warn("Invalid syntax! `--threshold` must be in days.")
        
        res = await self.bot.db_pool.fetchrow(
            "SELECT * FROM antiraid WHERE command = $1 AND guild_id = $2",
            "New Accounts",
            ctx.guild.id,
        )
        
        if res:
            await self.bot.db_pool.execute(
                "UPDATE antiraid SET punishment = $1, seconds = $2 WHERE guild_id = $3 AND command = $4",
                punishment,
                time_seconds,
                ctx.guild.id,
                "New Accounts",
            )
            return await ctx.approve(f"Updated **New Accounts** antiraid. Punishment is set to **{punishment}**, account age threshold is set to **{days} days**.")
        
        await self.bot.db_pool.execute(
            "INSERT INTO antiraid (guild_id, command, punishment, seconds) VALUES ($1, $2, $3, $4)",
            ctx.guild.id,
            "New Accounts",
            punishment,
            time_seconds,
        )
        return await ctx.approve(f"Added **New Accounts** antiraid. Punishment is set to **{punishment}**, account age threshold is set to **{days} days**.")
    
    @antiraid_newaccounts.command(name="disable", aliases=["off"])
    @commands.has_permissions(manage_guild=True)
    async def antiraid_newaccounts_disable(self, ctx: Context):
        res = await self.bot.db_pool.fetchrow(
            "SELECT * FROM antiraid WHERE guild_id = $1 AND command = $2",
            ctx.guild.id,
            "New Accounts",
        )
        if not res:
            return await ctx.warn(f"New Account protection **isn't** enabled.")
        
        await self.bot.db_pool.execute(
            "DELETE FROM antiraid WHERE command = $1 AND guild_id = $2",
            "New Accounts",
            ctx.guild.id,
        )
        return await ctx.approve("New Account protection has been **disabled**")
    
    @antiraid_newaccounts.command(name="whitelist", aliases=["wl"])
    @commands.has_permissions(manage_guild=True)
    async def antiraid_newaccounts_whitelist(self, ctx: Context, *, user: User):
        check = await self.bot.db_pool.fetchrow(
            "SELECT * FROM whitelist WHERE guild_id = $1 AND module = $2 AND object_id = $3 AND mode = $4",
            ctx.guild.id,
            "New Accounts",
            user.id,
            "user",
        )
        if check:
            await self.bot.db_pool.execute(
                "DELETE FROM whitelist WHERE guild_id = $1 AND module = $2 AND object_id = $3 AND mode = $4",
                ctx.guild.id,
                "New Accounts",
                user.id,
                "user",
            )
            return await ctx.approve(f"**{user.display_name}** has been removed from the whitelist.")
        
        await self.bot.db_pool.execute(
            "INSERT INTO whitelist (guild_id, module, object_id, mode) VALUES ($1, $2, $3, $4)",
            ctx.guild.id,
            "New Accounts",
            user.id,
            "user",
        )
        return await ctx.approve(f"**{user.display_name}** is now whitelisted for **antiraid newaccounts** and can join.")
    
    @antiraid.group(name="defaultavatar", aliases=["dav", "defaultpfp"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def antiraid_defaultavatar(self, ctx: Context):
        return await ctx.send_help(ctx.command)
    
    @antiraid_defaultavatar.command(name="enable", aliases=["on"])
    @commands.has_permissions(manage_guild=True)
    async def antiraid_defaultavatar_enable(self, ctx: Context, *, args: str):
        split_args = args.split()
        if "--do" not in split_args:
            return await ctx.warn("Invalid syntax! Use: `;antiraid defaultavatar on --do <punishment>`")
        
        try:
            do_index = split_args.index("--do") + 1
            punishment = split_args[do_index]
        except IndexError:
            return await ctx.warn("You must specify a punishment after `--do`.")
        
        if punishment not in ["kick", "ban"]:
            return await ctx.warn("Punishment must be either **kick** or **ban**.")
        
        res = await self.bot.db_pool.fetchrow(
            "SELECT * FROM antiraid WHERE guild_id = $1 AND command = $2",
            ctx.guild.id,
            "Default Avatar",
        )
        
        if res:
            await self.bot.db_pool.execute(
                "UPDATE antiraid SET punishment = $1 WHERE guild_id = $2 AND command = $3",
                punishment,
                ctx.guild.id,
                "Default Avatar",
            )
            return await ctx.approve(f"Updated **Default Avatar** antiraid. Punishment is now set to **{punishment}**.")
        
        await self.bot.db_pool.execute(
            "INSERT INTO antiraid (guild_id, command, punishment, seconds) VALUES ($1, $2, $3, $4)",
            ctx.guild.id,
            "Default Avatar",
            punishment,
            0,
        )
        return await ctx.approve(f"Added **Default Avatar** antiraid. Punishment is set to **{punishment}**.")
    
    @antiraid_defaultavatar.command(name="disable", aliases=["off"])
    @commands.has_permissions(manage_guild=True)
    async def antiraid_defaultavatar_disable(self, ctx: Context):
        res = await self.bot.db_pool.fetchrow(
            "SELECT * FROM antiraid WHERE guild_id = $1 AND command = $2",
            ctx.guild.id,
            "Default Avatar",
        )
        if not res:
            return await ctx.warn(f"Default Avatar protection **isn't** enabled.")
        
        await self.bot.db_pool.execute(
            "DELETE FROM antiraid WHERE command = $1 AND guild_id = $2",
            "Default Avatar",
            ctx.guild.id,
        )
        return await ctx.approve("Default Avatar protection has been **disabled**")
    
    @antiraid.command(name="whitelistview", aliases=["wlview"])
    @commands.has_permissions(manage_guild=True)
    async def antiraid_whitelist_view(self, ctx: Context):
        rows = await self.bot.db_pool.fetch(
            "SELECT object_id FROM whitelist WHERE guild_id = $1 AND mode = $2",
            ctx.guild.id,
            "user",
        )
        if not rows:
            return await ctx.warn("No **whitelisted** users found.")
        
        entries = []
        for i, row in enumerate(rows, start=1):
            user_id = row["object_id"]
            user = ctx.guild.get_member(user_id) or await self.bot.fetch_user(user_id)
            username = user.name if user else "Unknown User"
            entries.append(f"`{i}` **{username}** (`{user_id}`)")
        
        total_pages = (len(entries) + 9) // 10
        embeds = []
        
        embed = discord.Embed(
            color=Config.COLORS.DEFAULT,
            title=f"Antiraid Whitelists",
            description="",
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        
        count = 0
        for entry in entries:
            embed.description += f"{entry}\n"
            count += 1
            if count == 10:
                embed.set_footer(text=f"Page {len(embeds) + 1}/{total_pages} ({len(entries)} entries)")
                embeds.append(embed)
                embed = discord.Embed(
                    color=Config.COLORS.DEFAULT,
                    title=f"Whitelisted Users for {ctx.guild.name} ({len(entries)})",
                    description="",
                )
                count = 0
        
        if count > 0:
            embed.set_footer(text=f"Page {len(embeds) + 1}/{total_pages} ({len(entries)} entries)")
            embeds.append(embed)
        
        if len(embeds) > 1:
            from stare.core.tools.paginator import PaginatorView
            view = PaginatorView(embeds, ctx.author)
            await ctx.send(embed=embeds[0], view=view)
        else:
            await ctx.send(embed=embeds[0])
    
    @commands.group(name="antinuke", aliases=["an"], invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def antinuke(self, ctx: Context):
        return await ctx.send_help(ctx.command)
    
    @antinuke.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def antinuke_setup(self, ctx: Context):
        check = await self.bot.db_pool.fetchrow(
            "SELECT * FROM antinuke WHERE guild_id = $1", ctx.guild.id
        )
        
        if check and check['configured'] == 'true':
            return await ctx.warn("Antinuke is already configured")
        
        if check and check['owner_id']:
            owner_id = check['owner_id']
        else:
            owner_id = ctx.guild.owner_id
        
        if ctx.author.id != owner_id:
            return await ctx.warn(f"Only <@{owner_id}> can setup antinuke")
        
        if check:
            await self.bot.db_pool.execute(
                "UPDATE antinuke SET configured = $1 WHERE guild_id = $2",
                'true', ctx.guild.id
            )
        else:
            await self.bot.db_pool.execute(
                "INSERT INTO antinuke (guild_id, owner_id, configured) VALUES ($1, $2, $3)",
                ctx.guild.id, owner_id, 'true'
            )
        
        return await ctx.approve("Antinuke has been enabled")
    
    @antinuke.command(name="disable", aliases=["reset"])
    @commands.has_permissions(administrator=True)
    async def antinuke_disable(self, ctx: Context):
        check = await self.bot.db_pool.fetchrow(
            "SELECT * FROM antinuke WHERE guild_id = $1", ctx.guild.id
        )
        
        if not check:
            return await ctx.warn("Antinuke is not configured")
        
        if not await self.is_antinuke_owner(ctx.guild.id, ctx.author.id):
            return await ctx.warn("Only the antinuke owner can disable it")
        
        await self.bot.db_pool.execute(
            "DELETE FROM antinuke WHERE guild_id = $1", ctx.guild.id
        )
        await self.bot.db_pool.execute(
            "DELETE FROM antinuke_modules WHERE guild_id = $1", ctx.guild.id
        )
        
        return await ctx.approve("Antinuke has been disabled")
    
    @antinuke.command(name="whitelist", aliases=["wl"])
    @commands.has_permissions(administrator=True)
    async def antinuke_whitelist(self, ctx: Context, *, member: Union[Member, User]):
        if not await self.is_antinuke_admin(ctx.guild.id, ctx.author.id):
            return await ctx.warn("You must be an antinuke admin to use this")
        
        check = await self.bot.db_pool.fetchrow(
            "SELECT whitelisted FROM antinuke WHERE guild_id = $1", ctx.guild.id
        )
        
        if not check:
            return await ctx.warn("Antinuke is not configured")
        
        whitelisted = json.loads(check['whitelisted']) if check['whitelisted'] else []
        
        if member.id in whitelisted:
            return await ctx.warn(f"{member.mention} is already whitelisted")
        
        whitelisted.append(member.id)
        
        await self.bot.db_pool.execute(
            "UPDATE antinuke SET whitelisted = $1 WHERE guild_id = $2",
            json.dumps(whitelisted), ctx.guild.id
        )
        
        return await ctx.approve(f"Whitelisted {member.mention} from antinuke")
    
    @antinuke.command(name="unwhitelist", aliases=["unwl"])
    @commands.has_permissions(administrator=True)
    async def antinuke_unwhitelist(self, ctx: Context, *, member: Union[Member, User]):
        if not await self.is_antinuke_admin(ctx.guild.id, ctx.author.id):
            return await ctx.warn("You must be an antinuke admin to use this")
        
        check = await self.bot.db_pool.fetchrow(
            "SELECT whitelisted FROM antinuke WHERE guild_id = $1", ctx.guild.id
        )
        
        if not check or not check['whitelisted']:
            return await ctx.warn("No whitelisted members found")
        
        whitelisted = json.loads(check['whitelisted'])
        
        if member.id not in whitelisted:
            return await ctx.warn(f"{member.mention} is not whitelisted")
        
        whitelisted.remove(member.id)
        
        await self.bot.db_pool.execute(
            "UPDATE antinuke SET whitelisted = $1 WHERE guild_id = $2",
            json.dumps(whitelisted), ctx.guild.id
        )
        
        return await ctx.approve(f"Unwhitelisted {member.mention} from antinuke")
    
    @antinuke.command(name="whitelisted")
    @commands.has_permissions(administrator=True)
    async def antinuke_whitelisted_list(self, ctx: Context):
        check = await self.bot.db_pool.fetchrow(
            "SELECT owner_id, whitelisted FROM antinuke WHERE guild_id = $1", ctx.guild.id
        )
        
        if not check:
            return await ctx.warn("Antinuke is not configured")
        
        content = [f"<@{check['owner_id']}> (Owner)"]
        
        if check['whitelisted']:
            whitelisted = json.loads(check['whitelisted'])
            for user_id in whitelisted:
                content.append(f"<@{user_id}>")
        
        embed = Embed(
            title=f"Antinuke Whitelisted ({len(content)})",
            description="\n".join(content),
            color=Config.COLORS.DEFAULT
        )
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        
        await ctx.send(embed=embed)
    
    @antinuke.group(name="admin", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def antinuke_admin_group(self, ctx: Context):
        return await ctx.send_help(ctx.command)
    
    @antinuke_admin_group.command(name="add")
    @commands.has_permissions(administrator=True)
    async def antinuke_admin_add(self, ctx: Context, *, member: Member):
        if not await self.is_antinuke_owner(ctx.guild.id, ctx.author.id):
            return await ctx.warn("Only the antinuke owner can add admins")
        
        if member.bot:
            return await ctx.warn("Bots cannot be antinuke admins")
        
        if member.id == ctx.author.id:
            return await ctx.warn("You are already the owner")
        
        check = await self.bot.db_pool.fetchrow(
            "SELECT admins FROM antinuke WHERE guild_id = $1", ctx.guild.id
        )
        
        admins = json.loads(check['admins']) if check and check['admins'] else []
        
        if member.id in admins:
            return await ctx.warn(f"{member.mention} is already an antinuke admin")
        
        admins.append(member.id)
        
        await self.bot.db_pool.execute(
            "UPDATE antinuke SET admins = $1 WHERE guild_id = $2",
            json.dumps(admins), ctx.guild.id
        )
        
        return await ctx.approve(f"Added {member.mention} as an antinuke admin")
    
    @antinuke_admin_group.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def antinuke_admin_remove(self, ctx: Context, *, member: Member):
        if not await self.is_antinuke_owner(ctx.guild.id, ctx.author.id):
            return await ctx.warn("Only the antinuke owner can remove admins")
        
        check = await self.bot.db_pool.fetchrow(
            "SELECT admins FROM antinuke WHERE guild_id = $1", ctx.guild.id
        )
        
        if not check or not check['admins']:
            return await ctx.warn("No antinuke admins found")
        
        admins = json.loads(check['admins'])
        
        if member.id not in admins:
            return await ctx.warn(f"{member.mention} is not an antinuke admin")
        
        admins.remove(member.id)
        
        await self.bot.db_pool.execute(
            "UPDATE antinuke SET admins = $1 WHERE guild_id = $2",
            json.dumps(admins), ctx.guild.id
        )
        
        return await ctx.approve(f"Removed {member.mention} from antinuke admins")
    
    @antinuke.command(name="admins")
    @commands.has_permissions(administrator=True)
    async def antinuke_admins_list(self, ctx: Context):
        check = await self.bot.db_pool.fetchrow(
            "SELECT owner_id, admins FROM antinuke WHERE guild_id = $1", ctx.guild.id
        )
        
        if not check:
            return await ctx.warn("Antinuke is not configured")
        
        content = [f"<@{check['owner_id']}> (Owner)"]
        
        if check['admins']:
            admins = json.loads(check['admins'])
            for user_id in admins:
                content.append(f"<@{user_id}>")
        
        embed = Embed(
            title=f"Antinuke Admins ({len(content)})",
            description="\n".join(content),
            color=Config.COLORS.DEFAULT
        )
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        
        await ctx.send(embed=embed)
    
    @antinuke.command(name="config", aliases=["settings", "status"])
    @commands.has_permissions(administrator=True)
    async def antinuke_config(self, ctx: Context):
        results = await self.bot.db_pool.fetch(
            "SELECT module, punishment, threshold FROM antinuke_modules WHERE guild_id = $1",
            ctx.guild.id
        )
        
        if not results:
            return await ctx.warn("No antinuke modules are enabled")
        
        modules_info = []
        for row in results:
            module = row['module']
            punishment = row['punishment']
            threshold = row['threshold']
            
            if threshold:
                modules_info.append(f"**{module.title()}**: {Config.EMOJIS.SUCCESS} (Punishment: **{punishment}**, Threshold: **{threshold}/60s**)")
            else:
                modules_info.append(f"**{module.title()}**: {Config.EMOJIS.SUCCESS} (Punishment: **{punishment}**)")
        
        embed = Embed(
            title=f"{ctx.guild.name}'s Antinuke Configuration",
            description="\n".join(modules_info),
            color=Config.COLORS.DEFAULT
        )
        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)
        
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Security(bot))
