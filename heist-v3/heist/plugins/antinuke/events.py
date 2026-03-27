import discord
from discord.ext import commands
from datetime import datetime
from typing import Dict, List

class AntiNukeModule:
    def __init__(self, module: str, punishment: str, threshold: int, toggled: bool):
        self.module = module
        self.punishment = punishment
        self.threshold = threshold
        self.toggled = toggled

    @classmethod
    async def from_database(cls, pool, guild_id: int, module: str):
        result = await pool.fetchrow(
            "SELECT * FROM antinuke_modules WHERE guild_id = $1 AND module = $2",
            guild_id, module
        )
        if not result:
            return None
        return cls(result['module'], result['punishment'], result['threshold'], result['toggled'])

class AntiNukeUser:
    def __init__(self, module: str, user_id: int, last_action: datetime, amount: int):
        self.module = module
        self.user_id = user_id
        self.last_action = last_action
        self.amount = amount

class AntiNukeEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.actions: Dict[int, List[AntiNukeUser]] = {}

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.bot:
            return

        enabled = await self.bot.pool.fetchrow("SELECT * FROM ancfg WHERE guild_id = $1", member.guild.id)
        if not enabled:
            return

        module = await AntiNukeModule.from_database(self.bot.pool, member.guild.id, "Bot")
        if not module or not module.toggled:
            return

        admin = await self.bot.pool.fetchrow(
            "SELECT * FROM antinuke_admins WHERE guild_id = $1 AND user_id = $2",
            member.guild.id, member.id
        )

        whitelisted = await self.bot.pool.fetchrow(
            "SELECT * FROM antinuke_whitelist WHERE guild_id = $1 AND user_id = $2",
            member.guild.id, member.id
        )
        
        if whitelisted or admin:
            return

        await member.ban(reason=f"{self.bot.user.name} Anti-Nuke: Protection (Anti-Bot)")

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        if entry.user is None or entry.user.id == entry.guild.me.id:
            return

        enabled = await self.bot.pool.fetchrow("SELECT * FROM ancfg WHERE guild_id = $1", entry.guild.id)
        if not enabled:
            return

        if entry.action in [discord.AuditLogAction.ban, discord.AuditLogAction.unban]:
            module = await AntiNukeModule.from_database(self.bot.pool, entry.guild.id, "Ban")
            if module and module.toggled:
                await self.take_action(entry.guild.id, entry.user.id, entry.guild.owner.id, module)

        elif entry.action == discord.AuditLogAction.kick:
            module = await AntiNukeModule.from_database(self.bot.pool, entry.guild.id, "Kick")
            if module and module.toggled:
                await self.take_action(entry.guild.id, entry.user.id, entry.guild.owner.id, module)

        elif entry.action in [discord.AuditLogAction.channel_delete, discord.AuditLogAction.channel_update, discord.AuditLogAction.channel_create]:
            module = await AntiNukeModule.from_database(self.bot.pool, entry.guild.id, "Channels")
            if module and module.toggled:
                await self.take_action(entry.guild.id, entry.user.id, entry.guild.owner.id, module)

        elif entry.action in [discord.AuditLogAction.role_delete, discord.AuditLogAction.role_create]:
            module = await AntiNukeModule.from_database(self.bot.pool, entry.guild.id, "Roles")
            if module and module.toggled:
                await self.take_action(entry.guild.id, entry.user.id, entry.guild.owner.id, module)

        elif entry.action == discord.AuditLogAction.member_role_update:
            module = await AntiNukeModule.from_database(self.bot.pool, entry.guild.id, "Permissions")
            if not module or not module.toggled:
                return

            admin = await self.bot.pool.fetchrow(
                "SELECT * FROM antinuke_admins WHERE guild_id = $1 AND user_id = $2",
                entry.guild.id, entry.user.id
            )
            whitelisted = await self.bot.pool.fetchrow(
                "SELECT * FROM antinuke_whitelist WHERE guild_id = $1 AND user_id = $2",
                entry.guild.id, entry.user.id
            )

            if admin or whitelisted or entry.user.id == entry.guild.owner.id:
                return

            for role in entry.after.roles:
                if role not in entry.before.roles and role.permissions.administrator:
                    await self.take_action(entry.guild.id, entry.user.id, entry.guild.owner.id, module)
                    await entry.target.remove_roles(role)
                    return

        elif entry.action in [discord.AuditLogAction.webhook_create, discord.AuditLogAction.webhook_delete]:
            module = await AntiNukeModule.from_database(self.bot.pool, entry.guild.id, "Webhook")
            if module and module.toggled:
                await self.take_action(entry.guild.id, entry.user.id, entry.guild.owner.id, module)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        if before.vanity_url_code != after.vanity_url_code:
            enabled = await self.bot.pool.fetchrow("SELECT * FROM ancfg WHERE guild_id = $1", after.id)
            if not enabled:
                return
            
            user = None
            async for entry in before.audit_logs(limit=1, action=discord.AuditLogAction.guild_update):
                user = entry.user

            if user:
                module = await AntiNukeModule.from_database(self.bot.pool, after.id, "Vanity")
                if module and module.toggled:
                    await self.take_action(after.id, user.id, after.owner.id, module)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        if message.mention_everyone:
            enabled = await self.bot.pool.fetchrow("SELECT * FROM ancfg WHERE guild_id = $1", message.guild.id)
            if not enabled:
                return
            
            module = await AntiNukeModule.from_database(self.bot.pool, message.guild.id, "Massmention")
            if module and module.toggled:
                admin = await self.bot.pool.fetchrow(
                    "SELECT * FROM antinuke_admins WHERE guild_id = $1 AND user_id = $2",
                    message.guild.id, message.author.id
                )
                whitelisted = await self.bot.pool.fetchrow(
                    "SELECT * FROM antinuke_whitelist WHERE guild_id = $1 AND user_id = $2",
                    message.guild.id, message.author.id
                )
                
                if not admin and not whitelisted and message.author.id != message.guild.owner.id:
                    await self.take_action(message.guild.id, message.author.id, message.guild.owner.id, module)
                    try:
                        await message.delete()
                    except:
                        pass

    async def take_action(self, guild_id: int, user_id: int, owner_id: int, module: AntiNukeModule):
        admin = await self.bot.pool.fetchrow(
            "SELECT * FROM antinuke_admins WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id
        )
        whitelisted = await self.bot.pool.fetchrow(
            "SELECT * FROM antinuke_whitelist WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id
        )

        if whitelisted or admin or user_id == self.bot.user.id or user_id == owner_id:
            return

        if guild_id not in self.actions:
            self.actions[guild_id] = [AntiNukeUser(module.module, user_id, datetime.now(), 1)]
            return

        found = False
        for action in self.actions[guild_id]:
            if action.user_id == user_id and action.module == module.module:
                found = True
                if (datetime.now() - action.last_action).total_seconds() > 60:
                    self.remove_action(guild_id, user_id, module.module)
                    action.amount = 1
                    self.actions[guild_id].append(AntiNukeUser(module.module, user_id, datetime.now(), 1))
                    return

                if action.amount >= module.threshold:
                    self.remove_action(guild_id, user_id, module.module)
                    await self.send_action(guild_id, user_id, module)
                    return

                action.amount += 1
                self.remove_action(guild_id, user_id, module.module)
                self.actions[guild_id].append(AntiNukeUser(module.module, user_id, datetime.now(), action.amount))
                return

        if not found:
            self.actions[guild_id].append(AntiNukeUser(module.module, user_id, datetime.now(), 1))

    async def send_action(self, guild_id: int, user_id: int, module: AntiNukeModule):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        user = await self.bot.fetch_user(user_id)
        if not user:
            return

        reason = f"{self.bot.user.name} Anti-Nuke: Protection {module.module} (Anti-{module.module})"

        if module.punishment.lower() == "ban":
            await guild.ban(user=user, reason=reason)
        elif module.punishment.lower() == "kick":
            await guild.kick(user=user, reason=reason)
        elif module.punishment.lower() == "warn":
            try:
                await user.send(f"{self.bot.user.name} Anti-Nuke: Protection {module.module} (Anti-{module.module})\n**You have been warned**, further actions will result in a punishment decided by relevant staff.")
            except:
                pass
        elif module.punishment.lower() == "strip":
            member = guild.get_member(user_id)
            if member:
                dangerous_roles = [
                    role for role in member.roles
                    if any([
                        role.permissions.administrator,
                        role.permissions.manage_channels,
                        role.permissions.manage_roles,
                        role.permissions.manage_webhooks,
                        role.permissions.mention_everyone,
                        role.permissions.manage_expressions,
                        role.permissions.moderate_members,
                        role.permissions.manage_messages,
                        role.permissions.manage_guild,
                        role.permissions.ban_members,
                        role.permissions.kick_members,
                        role.permissions.mute_members
                    ])
                ]
                if dangerous_roles:
                    await member.remove_roles(*dangerous_roles, reason=reason)

        log_embed = discord.Embed(
            title=f"Anti-Nuke: {module.module}",
            description=f"Action taken by {self.bot.user.name}",
            color=0xd3d6f1,
            timestamp=datetime.now()
        )
        log_embed.add_field(name="User", value=f"<@{user_id}>", inline=True)
        log_embed.add_field(name="Action", value=module.punishment, inline=True)
        log_embed.set_footer(text=f"{self.bot.user.name} Anti-Nuke", icon_url=self.bot.user.avatar.url)

        log_channel_id = await self.bot.pool.fetchval(
            "SELECT channel_id FROM logging WHERE guild_id = $1", guild_id
        )
        
        if log_channel_id:
            channel = self.bot.get_channel(log_channel_id)
            if channel:
                try:
                    await channel.send(embed=log_embed)
                except:
                    pass

    def remove_action(self, guild_id: int, user_id: int, module: str):
        if guild_id not in self.actions:
            return
        
        for pos, action in enumerate(self.actions[guild_id]):
            if action.user_id == user_id and action.module == module:
                del self.actions[guild_id][pos]
                return