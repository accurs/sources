from __future__ import annotations

import datetime
from typing import Union

import discord
from discord.ext import commands
import humanfriendly

from bot.helpers.context import TormentContext, _color


class Security(commands.Cog):
    __cog_name__ = "safety"
    
    massjoin_cooldown = 10
    massjoin_cache = {}

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def storage(self):
        return self.bot.storage

    @commands.Cog.listener("on_member_join")
    async def check_for_avatar(self, member: discord.Member):
        if member.avatar is None:
            res = await self.storage.pool.fetchrow(
                "SELECT * FROM antiraid WHERE command = $1 AND guild_id = $2",
                "Default Avatar",
                member.guild.id,
            )
            if res is not None:
                res1 = await self.storage.pool.fetchrow(
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
    async def new_accounts(self, member: discord.Member):
        res = await self.storage.pool.fetchrow(
            "SELECT * FROM antiraid WHERE command = $1 AND guild_id = $2",
            "New Accounts",
            member.guild.id,
        )
        if not res:
            return

        res1 = await self.storage.pool.fetchrow(
            "SELECT * FROM whitelist WHERE guild_id = $1 AND module = $2 AND object_id = $3 AND mode = $4",
            member.guild.id,
            "New Accounts",
            member.id,
            "user",
        )
        if res1:
            return

        account_age_seconds = (
            datetime.datetime.utcnow() - member.created_at.replace(tzinfo=None)
        ).total_seconds()

        if account_age_seconds < int(res["seconds"]):
            if res["punishment"] == "kick":
                await member.kick(reason="Antiraid: The account is too young, suspected alt.")
            elif res["punishment"] == "ban":
                await member.ban(reason="Antiraid: The account is too young, suspected alt.")

    @commands.Cog.listener("on_member_join")
    async def mass_joins(self, member: discord.Member):
        res = await self.storage.pool.fetchrow(
            "SELECT * FROM antiraid WHERE command = $1 AND guild_id = $2",
            "massjoin",
            member.guild.id,
        )
        if res:
            if not self.massjoin_cache.get(str(member.guild.id)):
                self.massjoin_cache[str(member.guild.id)] = []

            self.massjoin_cache[str(member.guild.id)].append(
                tuple([datetime.datetime.now(), member.id])
            )

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

    @commands.group(
        name="antiraid",
        invoke_without_command=True,
        help="Configure antiraid protection for your server",
        extras={"parameters": "n/a", "usage": "antiraid"},
    )
    @commands.has_permissions(manage_guild=True)
    async def antiraid(self, ctx: TormentContext):
        await ctx.send_help_embed(ctx.command)

    @antiraid.command(
        name="settings",
        aliases=["stats", "config"],
        help="Check the antiraid configuration",
        extras={"parameters": "n/a", "usage": "antiraid settings"},
    )
    @commands.has_permissions(manage_guild=True)
    async def antiraid_settings(self, ctx: TormentContext):
        desc = "**Current Raid State:** "
        enabled = {
            "Mass Join": "❌",
            "Default Avatar": "❌",
            "New Accounts": "❌",
        }
        module_details = {
            "Mass Join": {"punishment": "N/A", "seconds": "N/A"},
            "Default Avatar": {"punishment": "N/A", "seconds": "N/A"},
            "New Accounts": {"punishment": "N/A", "seconds": "N/A"},
        }

        res = await self.storage.pool.fetch(
            "SELECT command, punishment, seconds FROM antiraid WHERE guild_id = $1",
            ctx.guild.id,
        )

        for result in res:
            command = result["command"]
            punishment = result["punishment"]
            seconds = result["seconds"]

            if command in enabled:
                enabled[command] = "✅"

            if command == "New Accounts":
                seconds = humanfriendly.format_timespan(seconds)

            module_details[command] = {"punishment": punishment, "seconds": seconds}

        if all(status == "✅" for status in enabled.values()):
            desc += "Safe"
        else:
            desc += "Unsafe"

        embed = discord.Embed(
            title="Antiraid Settings",
            color=_color("EMBED_INFO_COLOR"),
            description=desc
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)

        modules_info = [
            f"**{module}:** {enabled.get(module)} (Do: **{details['punishment']}**, Threshold: **{details['seconds']}**)"
            for module, details in module_details.items()
        ]
        embed.add_field(name="Modules", value="\n".join(modules_info))

        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)

        await ctx.reply(embed=embed)

    @antiraid.group(
        name="whitelist",
        aliases=["wl"],
        invoke_without_command=True,
        help="Whitelist a user for the antiraid",
        extras={"parameters": "member", "usage": "antiraid whitelist (member)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def antiraid_whitelist(self, ctx: TormentContext, *, member: discord.Member):
        res = await self.storage.pool.fetchrow(
            "SELECT * FROM whitelist WHERE guild_id = $1 AND object_id = $2 AND module = $3 AND mode = $4",
            ctx.guild.id,
            member.id,
            "antiraid",
            "user",
        )
        if res:
            return await ctx.warn(f"{member.mention} is already whitelisted for **antiraid**")

        await self.storage.pool.execute(
            "INSERT INTO whitelist VALUES ($1,$2,$3,$4)",
            ctx.guild.id,
            "antiraid",
            member.id,
            "user",
        )
        return await ctx.success(f"{member.mention} will now be **ignored** on antiraid events")

    @antiraid.command(
        name="unwhitelist",
        aliases=["unwl"],
        help="Unwhitelist a user on the antiraid",
        extras={"parameters": "member", "usage": "antiraid unwhitelist (member)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def antiraid_unwhitelist(self, ctx: TormentContext, *, member: discord.Member):
        res = await self.storage.pool.fetchrow(
            "SELECT * FROM whitelist WHERE guild_id = $1 AND object_id = $2 AND module = $3 AND mode = $4",
            ctx.guild.id,
            member.id,
            "antiraid",
            "user",
        )
        if not res:
            return await ctx.warn(f"**{member.mention}** is not whitelisted for **anti raid**")

        await self.storage.pool.execute(
            "DELETE FROM whitelist WHERE guild_id = $1 AND object_id = $2 AND module = $3",
            ctx.guild.id,
            member.id,
            "antiraid",
        )
        return await ctx.success(f"**{member.mention}** is **no longer** ignored on antiraid events")

    @antiraid.group(
        name="massjoin",
        invoke_without_command=True,
        help="Configure antiraid massjoin protection",
        extras={"parameters": "n/a", "usage": "antiraid massjoin"},
    )
    @commands.has_permissions(manage_guild=True)
    async def antiraid_massjoin(self, ctx: TormentContext):
        await ctx.send_help_embed(ctx.command)

    @antiraid_massjoin.command(
        name="enable",
        aliases=["on"],
        help="Enable massjoin event",
        extras={"parameters": "--do <punishment> --threshold <joins>", "usage": "antiraid massjoin enable --do <kick|ban> --threshold <number>"},
    )
    @commands.has_permissions(manage_guild=True)
    async def antiraid_massjoin_enable(self, ctx: TormentContext, *, args: str):
        split_args = args.split()
        
        if "--do" not in split_args or "--threshold" not in split_args:
            return await ctx.warn("Invalid syntax! Use: `antiraid massjoin enable --do <kick|ban> --threshold <joins>`")
        
        try:
            do_index = split_args.index("--do") + 1
            threshold_index = split_args.index("--threshold") + 1
            
            punishment = split_args[do_index]
            threshold = split_args[threshold_index]
            
            if punishment not in ["kick", "ban"]:
                return await ctx.warn("Punishment must be either **kick** or **ban**")
            
            joins = int(threshold)
            if joins <= 0:
                raise ValueError("Threshold must be a positive number of joins")
        except (IndexError, ValueError):
            return await ctx.warn("Invalid syntax! `--threshold` must be a positive integer")

        res = await self.storage.pool.fetchrow(
            "SELECT * FROM antiraid WHERE guild_id = $1 AND command = $2",
            ctx.guild.id,
            "Mass Join",
        )

        if res:
            await self.storage.pool.execute(
                "UPDATE antiraid SET punishment = $1, seconds = $2 WHERE guild_id = $3 AND command = $4",
                punishment,
                joins,
                ctx.guild.id,
                "Mass Join",
            )
            return await ctx.success(
                f"Updated **Massjoin** antiraid. Punishment is set to **{punishment}**, threshold is set to **{joins} joins**"
            )

        await self.storage.pool.execute(
            "INSERT INTO antiraid (guild_id, command, punishment, seconds) VALUES ($1, $2, $3, $4)",
            ctx.guild.id,
            "Mass Join",
            punishment,
            joins,
        )
        return await ctx.success(
            f"Added **Massjoin** antiraid. Punishment is set to **{punishment}**, threshold is set to **{joins} joins**"
        )

    @antiraid_massjoin.command(
        name="disable",
        aliases=["off"],
        help="Disable massjoin event",
        extras={"parameters": "n/a", "usage": "antiraid massjoin disable"},
    )
    @commands.has_permissions(manage_guild=True)
    async def antiraid_massjoin_disable(self, ctx: TormentContext):
        res = await self.storage.pool.fetchrow(
            "SELECT * FROM antiraid WHERE guild_id = $1 AND command = $2",
            ctx.guild.id,
            "Mass Join",
        )
        if not res:
            return await ctx.warn(f"Mass Join protection **isn't** enabled")

        await self.storage.pool.execute(
            "DELETE FROM antiraid WHERE command = $1 AND guild_id = $2",
            "Mass Join",
            ctx.guild.id,
        )
        return await ctx.success("Mass Join protection has been **disabled**")

    @antiraid.group(
        name="newaccounts",
        invoke_without_command=True,
        help="Configure antiraid new accounts protection",
        extras={"parameters": "n/a", "usage": "antiraid newaccounts"},
    )
    @commands.has_permissions(manage_guild=True)
    async def antiraid_newaccounts(self, ctx: TormentContext):
        await ctx.send_help_embed(ctx.command)

    @antiraid_newaccounts.command(
        name="on",
        aliases=["enable"],
        help="Enable antiraid new accounts",
        extras={"parameters": "--do <punishment> --threshold <days>", "usage": "antiraid newaccounts on --do <kick|ban> --threshold <days>"},
    )
    @commands.has_permissions(manage_guild=True)
    async def newaccounts_on(self, ctx: TormentContext, *, args: str):
        split_args = args.split()
        
        if "--do" not in split_args or "--threshold" not in split_args:
            return await ctx.warn("Invalid syntax! Use: `antiraid newaccounts on --do <kick|ban> --threshold <days>`")
        
        try:
            do_index = split_args.index("--do") + 1
            threshold_index = split_args.index("--threshold") + 1
            
            punishment = split_args[do_index]
            threshold = split_args[threshold_index]
            
            if punishment not in ["kick", "ban"]:
                return await ctx.warn("Punishment must be either **kick** or **ban**")
            
            days = int(threshold)
            if days <= 0:
                raise ValueError("Threshold must be a positive number of days")
            
            time_seconds = days * 86400
        except (IndexError, ValueError):
            return await ctx.warn("Invalid syntax! `--threshold` must be in days")

        res = await self.storage.pool.fetchrow(
            "SELECT * FROM antiraid WHERE command = $1 AND guild_id = $2",
            "New Accounts",
            ctx.guild.id,
        )

        if res:
            await self.storage.pool.execute(
                "UPDATE antiraid SET punishment = $1, seconds = $2 WHERE guild_id = $3 AND command = $4",
                punishment,
                time_seconds,
                ctx.guild.id,
                "New Accounts",
            )
            return await ctx.success(
                f"Updated **New Accounts** antiraid. Punishment is set to **{punishment}**, account age threshold is set to **{days} days**"
            )

        await self.storage.pool.execute(
            "INSERT INTO antiraid (guild_id, command, punishment, seconds) VALUES ($1, $2, $3, $4)",
            ctx.guild.id,
            "New Accounts",
            punishment,
            time_seconds,
        )
        return await ctx.success(
            f"Added **New Accounts** antiraid. Punishment is set to **{punishment}**, account age threshold is set to **{days} days**"
        )

    @antiraid_newaccounts.command(
        name="disable",
        aliases=["off"],
        help="Disable antiraid new accounts",
        extras={"parameters": "n/a", "usage": "antiraid newaccounts disable"},
    )
    @commands.has_permissions(manage_guild=True)
    async def antiraid_newaccounts_disable(self, ctx: TormentContext):
        res = await self.storage.pool.fetchrow(
            "SELECT * FROM antiraid WHERE guild_id = $1 AND command = $2",
            ctx.guild.id,
            "New Accounts",
        )
        if not res:
            return await ctx.warn(f"New Account protection **isn't** enabled")

        await self.storage.pool.execute(
            "DELETE FROM antiraid WHERE command = $1 AND guild_id = $2",
            "New Accounts",
            ctx.guild.id,
        )
        return await ctx.success("New Account protection has been **disabled**")

    @antiraid_newaccounts.command(
        name="whitelist",
        aliases=["wl"],
        help="Allow a user to join the server if under aged",
        extras={"parameters": "user", "usage": "antiraid newaccounts whitelist (user)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def antiraid_newaccounts_whitelist(self, ctx: TormentContext, *, user: discord.User):
        check = await self.storage.pool.fetchrow(
            "SELECT * FROM whitelist WHERE guild_id = $1 AND module = $2 AND object_id = $3 AND mode = $4",
            ctx.guild.id,
            "New Accounts",
            user.id,
            "user",
        )

        if check:
            await self.storage.pool.execute(
                "DELETE FROM whitelist WHERE guild_id = $1 AND module = $2 AND object_id = $3 AND mode = $4",
                ctx.guild.id,
                "New Accounts",
                user.id,
                "user",
            )
            return await ctx.success(f"**{user.display_name}** has been removed from the whitelist")

        await self.storage.pool.execute(
            "INSERT INTO whitelist (guild_id, module, object_id, mode) VALUES ($1, $2, $3, $4)",
            ctx.guild.id,
            "New Accounts",
            user.id,
            "user",
        )
        return await ctx.success(
            f"**{user.display_name}** is now whitelisted for **antiraid newaccounts** and can join"
        )

    @antiraid.group(
        name="defaultavatar",
        aliases=["dav", "defaultpfp"],
        invoke_without_command=True,
        help="Configure antiraid default avatar protection",
        extras={"parameters": "n/a", "usage": "antiraid defaultavatar"},
    )
    @commands.has_permissions(manage_guild=True)
    async def antiraid_defaultavatar(self, ctx: TormentContext):
        await ctx.send_help_embed(ctx.command)

    @antiraid_defaultavatar.command(
        name="enable",
        aliases=["on"],
        help="Enable antiraid default avatar",
        extras={"parameters": "--do <punishment>", "usage": "antiraid defaultavatar enable --do <kick|ban>"},
    )
    @commands.has_permissions(manage_guild=True)
    async def antiraid_defaultavatar_enable(self, ctx: TormentContext, *, args: str):
        split_args = args.split()
        
        if "--do" not in split_args:
            return await ctx.warn("Invalid syntax! Use: `antiraid defaultavatar enable --do <kick|ban>`")
        
        try:
            do_index = split_args.index("--do") + 1
            punishment = split_args[do_index]
        except IndexError:
            return await ctx.warn("You must specify a punishment after `--do`")

        if punishment not in ["kick", "ban"]:
            return await ctx.warn("Punishment must be either **kick** or **ban**")

        res = await self.storage.pool.fetchrow(
            "SELECT * FROM antiraid WHERE guild_id = $1 AND command = $2",
            ctx.guild.id,
            "Default Avatar",
        )

        if res:
            await self.storage.pool.execute(
                "UPDATE antiraid SET punishment = $1 WHERE guild_id = $2 AND command = $3",
                punishment,
                ctx.guild.id,
                "Default Avatar",
            )
            return await ctx.success(
                f"Updated **Default Avatar** antiraid. Punishment is now set to **{punishment}**"
            )

        await self.storage.pool.execute(
            "INSERT INTO antiraid (guild_id, command, punishment, seconds) VALUES ($1, $2, $3, $4)",
            ctx.guild.id,
            "Default Avatar",
            punishment,
            0,
        )
        return await ctx.success(f"Added **Default Avatar** antiraid. Punishment is set to **{punishment}**")

    @antiraid_defaultavatar.command(
        name="disable",
        aliases=["off"],
        help="Disable antiraid default avatar",
        extras={"parameters": "n/a", "usage": "antiraid defaultavatar disable"},
    )
    @commands.has_permissions(manage_guild=True)
    async def antiraid_defaultavatar_disable(self, ctx: TormentContext):
        res = await self.storage.pool.fetchrow(
            "SELECT * FROM antiraid WHERE guild_id = $1 AND command = $2",
            ctx.guild.id,
            "Default Avatar",
        )
        if not res:
            return await ctx.warn(f"Default Avatar protection **isn't** enabled")

        await self.storage.pool.execute(
            "DELETE FROM antiraid WHERE command = $1 AND guild_id = $2",
            "Default Avatar",
            ctx.guild.id,
        )
        return await ctx.success("Default Avatar protection has been **disabled**")

    @antiraid_whitelist.command(
        name="view",
        help="View the whitelisted users on the antiraid module",
        extras={"parameters": "n/a", "usage": "antiraid whitelist view"},
    )
    @commands.has_permissions(manage_guild=True)
    async def antiraid_whitelist_view(self, ctx: TormentContext):
        rows = await self.storage.pool.fetch(
            "SELECT object_id FROM whitelist WHERE guild_id = $1 AND mode = $2",
            ctx.guild.id,
            "user",
        )

        if not rows:
            return await ctx.warn("No **whitelisted** users found")

        entries = []
        for i, row in enumerate(rows, start=1):
            user_id = row["object_id"]
            user = ctx.guild.get_member(user_id) or await self.bot.fetch_user(user_id)
            username = user.name if user else "Unknown User"
            entries.append(f"`{i}` **{username}** (`{user_id}`)")

        total_pages = (len(entries) + 9) // 10
        embeds = []
        embed = discord.Embed(
            color=_color("EMBED_INFO_COLOR"),
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
                    color=_color("EMBED_INFO_COLOR"),
                    title=f"Whitelisted Users for {ctx.guild.name} ({len(entries)})",
                    description="",
                )
                count = 0

        if count > 0:
            embed.set_footer(text=f"Page {len(embeds) + 1}/{total_pages} ({len(entries)} entries)")
            embeds.append(embed)

        if len(embeds) > 1:
            await ctx.paginate(embeds)
        else:
            await ctx.send(embed=embeds[0])

    @commands.group(
        name="fakepermissions",
        aliases=["fakeperms", "fp"],
        invoke_without_command=True,
        help="Manage fake permissions for roles to restrict Discord API access",
        extras={"parameters": "n/a", "usage": "fakepermissions"},
    )
    async def fakepermissions(self, ctx: TormentContext):
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.warn("Only the **server owner** can manage fake permissions")
        await ctx.send_help_embed(ctx.command)

    @fakepermissions.command(
        name="add",
        help="Add fake permissions to a role",
        extras={"parameters": "role, permissions", "usage": "fakepermissions add (role) (permissions)"},
    )
    async def fakepermissions_add(self, ctx: TormentContext, role: discord.Role, *, permissions: str):
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.warn("Only the **server owner** can manage fake permissions")

        valid_perms = [
            "kick_members", "ban_members", "manage_channels", "manage_guild",
            "manage_messages", "manage_nicknames", "manage_roles", "manage_webhooks",
            "manage_emojis", "moderate_members", "administrator"
        ]

        perm_list = [p.strip().lower() for p in permissions.split(",")]
        invalid_perms = [p for p in perm_list if p not in valid_perms]

        if invalid_perms:
            return await ctx.warn(
                f"Invalid permissions: {', '.join(invalid_perms)}\n"
                f"Valid permissions: {', '.join(valid_perms)}"
            )

        added = []
        for perm in perm_list:
            existing = await self.storage.pool.fetchrow(
                "SELECT * FROM fake_permissions WHERE guild_id = $1 AND role_id = $2 AND permission = $3",
                ctx.guild.id, role.id, perm
            )
            if not existing:
                await self.storage.pool.execute(
                    "INSERT INTO fake_permissions (guild_id, role_id, permission) VALUES ($1, $2, $3)",
                    ctx.guild.id, role.id, perm
                )
                added.append(perm)

        if added:
            return await ctx.success(
                f"Added fake permissions to {role.mention}: {', '.join(added)}"
            )
        else:
            return await ctx.warn(f"{role.mention} already has all specified fake permissions")

    @fakepermissions.command(
        name="remove",
        help="Remove fake permissions from a role",
        extras={"parameters": "role, permissions", "usage": "fakepermissions remove (role) (permissions)"},
    )
    async def fakepermissions_remove(self, ctx: TormentContext, role: discord.Role, *, permissions: str):
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.warn("Only the **server owner** can manage fake permissions")

        perm_list = [p.strip().lower() for p in permissions.split(",")]
        removed = []

        for perm in perm_list:
            result = await self.storage.pool.execute(
                "DELETE FROM fake_permissions WHERE guild_id = $1 AND role_id = $2 AND permission = $3",
                ctx.guild.id, role.id, perm
            )
            if result != "DELETE 0":
                removed.append(perm)

        if removed:
            return await ctx.success(
                f"Removed fake permissions from {role.mention}: {', '.join(removed)}"
            )
        else:
            return await ctx.warn(f"{role.mention} doesn't have any of the specified fake permissions")

    @fakepermissions.command(
        name="list",
        help="List fake permissions for a role or all roles",
        extras={"parameters": "role", "usage": "fakepermissions list [role]"},
    )
    async def fakepermissions_list(self, ctx: TormentContext, role: discord.Role = None):
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.warn("Only the **server owner** can view fake permissions")

        if role:
            perms = await self.storage.pool.fetch(
                "SELECT permission FROM fake_permissions WHERE guild_id = $1 AND role_id = $2",
                ctx.guild.id, role.id
            )
            if not perms:
                return await ctx.warn(f"{role.mention} has no fake permissions")

            perm_list = [p["permission"] for p in perms]
            embed = discord.Embed(
                title=f"Fake Permissions for {role.name}",
                description=", ".join(perm_list),
                color=_color("EMBED_INFO_COLOR")
            )
            return await ctx.send(embed=embed)

        query = """
            SELECT role_id, ARRAY_AGG(permission) as permissions
            FROM fake_permissions
            WHERE guild_id = $1
            GROUP BY role_id
        """
        records = await self.storage.pool.fetch(query, ctx.guild.id)

        if not records:
            return await ctx.warn("No fake permissions are configured in this server")

        entries = []
        for record in records:
            role_obj = ctx.guild.get_role(record["role_id"])
            if role_obj:
                perms = ", ".join(record["permissions"])
                entries.append(f"{role_obj.mention}: {perms}")

        if not entries:
            return await ctx.warn("No fake permissions are configured in this server")

        embed = discord.Embed(
            title="Fake Permissions",
            color=_color("EMBED_INFO_COLOR")
        )
        
        from bot.helpers.paginator import Paginator
        paginator = Paginator(ctx, entries, embed)
        await paginator.start()

    @fakepermissions.command(
        name="reset",
        help="Reset all fake permissions in the server",
        extras={"parameters": "n/a", "usage": "fakepermissions reset"},
    )
    async def fakepermissions_reset(self, ctx: TormentContext):
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.warn("Only the **server owner** can reset fake permissions")

        if not await ctx.confirm("Are you sure you want to reset all fake permissions?"):
            return

        result = await self.storage.pool.execute(
            "DELETE FROM fake_permissions WHERE guild_id = $1",
            ctx.guild.id
        )

        count = int(result.split()[-1]) if result else 0
        if count > 0:
            return await ctx.success(f"Reset {count} fake permission entries")
        else:
            return await ctx.warn("No fake permissions to reset")

    async def has_fake_permission(self, member: discord.Member, permission: str) -> bool:
        """Check if a member has a fake permission through their roles"""
        for role in member.roles:
            result = await self.storage.pool.fetchrow(
                "SELECT * FROM fake_permissions WHERE guild_id = $1 AND role_id = $2 AND permission = $3",
                member.guild.id, role.id, permission
            )
            if result:
                return True
        return False


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Security(bot))
