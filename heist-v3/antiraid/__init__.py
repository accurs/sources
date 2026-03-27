from typing import Optional, Union
from discord import Client, Embed, Guild, Member, User
from discord.ext.commands import Cog, CommandError, command, group, has_permissions
from heist.framework.discord.context import Context
from .flags import ActionParameters, AntiRaidParameters

class AntiRaid(Cog):
    def __init__(self, bot: Client):
        self.bot = bot

    def to_boolean(self, state: bool):
        if state is True:
            return self.bot.config.emojis.context.approve
        else:
            return self.bot.config.emojis.context.deny

    def to_action(self, value: Optional[int] = None):
        if value:
            if value == 1:
                return "kick"
            elif value == 2:
                return "ban"
        else:
            return "N/A"

    @group(
        name="antiraid",
        description="Configure protection against potential raids",
        invoke_without_command=True,
    )
    async def antiraid(self, ctx: Context):
        return await ctx.send_help(ctx.command)

    @antiraid.command(name="config", description="View server antiraid configuration")
    @has_permissions(manage_guild=True)
    async def antiraid_config(self, ctx: Context):
        data = await self.bot.pool.fetchrow(
            """SELECT locked, joins, mentions, avatar, browser FROM antiraid WHERE guild_id = $1""",
            ctx.guild.id,
        )
        if not data:
            raise CommandError("antiraid has not been setup")
        description = f"**Current Raid State:** {'locked' if data['locked'] else 'unlocked'}"
        modules_value = (
            f"**Joins Protection:** {self.to_boolean(bool(data['joins']))}\n"
            + f"**Mentions Protection:** {self.to_boolean(bool(data['mentions']))}\n"
            + f"**Avatar Protection:** {self.to_boolean(bool(data['avatar']))}\n"
            + f"**Browser Protection:** {self.to_boolean(bool(data['browser']))}"
        )
        embed = Embed(title="Antiraid settings", description=description, color=ctx.config.colors.information)
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        embed.add_field(name="Modules", value=modules_value, inline=False)
        return await ctx.send(embed=embed)

    @antiraid.group(
        name="whitelist",
        description="Create a one-time whitelist to allow a user to join",
        aliases=["wl", "allow"],
        invoke_without_command=True,
    )
    @has_permissions(manage_guild=True)
    async def antiraid_whitelist(self, ctx: Context, *, member: Union[User, Member]):
        user_ids = (
            await self.bot.pool.fetchval(
                """SELECT whitelist FROM antiraid WHERE guild_id = $1""", ctx.guild.id
            )
            or []
        )
        if member.id not in user_ids:
            user_ids.append(member.id)
            message = f"successfully **WHITELISTED** {member.mention} to join"
        else:
            user_ids.remove(member.id)
            message = f"successfully **UNWHITELISTED** {member.mention} from joining"

        await self.bot.pool.execute(
            """INSERT INTO antiraid (guild_id, whitelist) VALUES($1, $2) ON CONFLICT(guild_id) DO UPDATE SET whitelist = excluded.whitelist""",
            ctx.guild.id,
            user_ids,
        )
        return await ctx.approve(message)

    @antiraid_whitelist.command(
        name="view",
        aliases=["ls", "list", "show"],
        description="View all current antiraid whitelists",
    )
    @has_permissions(manage_guild=True)
    async def antiraid_whitelist_view(self, ctx: Context):
        if not (
            user_ids := await self.bot.pool.fetchval(
                """SELECT whitelist FROM antiraid WHERE guild_id = $1""", ctx.guild.id
            )
        ):
            raise CommandError("there are no whitelists")

        if len(user_ids) == 0:
            return await ctx.send("there are no whitelists")

        def get_user(u: int):
            if user := self.bot.get_user(u):
                return f"**{str(user)}** (`{u}`)"
            else:
                return f"**Unknown** (`{u}`)"

        rows = [
            f"`{i}` {get_user(user_id)}" for i, user_id in enumerate(user_ids, start=1)
        ]
        embed = Embed(title="Antiraid Whitelists").set_author(
            name=str(ctx.author), icon_url=ctx.author.display_avatar.url
        )
        return await ctx.paginate(rows, embed=embed)

    @antiraid.command(
        name="avatar",
        aliases=["pfp", "nopfp", "defaultpfp"],
        description="Punish accounts without a profile picture",
    )
    @has_permissions(manage_guild=True)
    async def antiraid_avatar(
        self, ctx: Context, setting: bool, *, flags: ActionParameters
    ):
        await self.bot.pool.execute(
            """INSERT INTO antiraid (guild_id, no_avatar, no_avatar_punishment) VALUES($1, $2, $3) ON CONFLICT(guild_id) DO UPDATE SET no_avatar = excluded.no_avatar, no_avatar_punishment = excluded.no_avatar_punishment""",
            ctx.guild.id,
            setting,
            flags.action or 2,
        )

        if setting:
            flags_value = f"\n(action: `{self.to_action(flags.action)})`)"
        else:
            flags_value = ""

        return await ctx.approve(
            f"successfully **{'ENABLED' if setting is True else 'DISABLED'}** punishment for accounts without avatars{flags_value}"
        )

    @antiraid.command(
        name="newaccounts",
        description="Punish new registered accounts",
        aliases=["age", "accountage", "newaccs"],
    )
    @has_permissions(manage_guild=True)
    async def antiraid_newaccounts(
        self, ctx: Context, setting: bool, *, flags: AntiRaidParameters
    ):
        await self.bot.pool.execute(
            """INSERT INTO antiraid (guild_id, new_accounts, new_account_punishment, new_account_threshold, lock_channels, punish) VALUES($1, $2, $3, $4, $5, $6) ON CONFLICT(guild_id) DO UPDATE SET new_accounts = excluded.new_accounts, new_account_punishment = excluded.new_account_punishment, new_account_threshold = excluded.new_account_threshold, lock_channels = excluded.lock_channels, punish = excluded.punish""",
            ctx.guild.id,
            setting,
            flags.action,
            flags.threshold,
            flags.lock,
            flags.punish,
        )
        flags_value = f"\nPunishment set to **{self.to_action(flags.action)}**, threshold set to **{flags.threshold}**, lock channels set to **{flags.lock}**, punish new members set to **{flags.punish}**"
        return await ctx.approve(
            f"successfully **{'ENABLED' if setting is True else 'DISABLED'}** new account antiraid{flags_value}"
        )

    @antiraid.command(
        name="massjoin",
        aliases=["joingate", "massbot", "joins"],
        description="Protect server against mass bot raids",
    )
    @has_permissions(manage_guild=True)
    async def antiraid_massjoin(
        self, ctx: Context, setting: bool, *, flags: AntiRaidParameters
    ):
        await self.bot.pool.execute(
            """INSERT INTO antiraid (guild_id, joins, join_punishment, join_threshold, lock_channels, punish) VALUES($1, $2, $3, $4, $5, $6) ON CONFLICT(guild_id) DO UPDATE SET joins = excluded.joins, join_punishment = excluded.join_punishment, join_threshold = excluded.join_threshold, lock_channels = excluded.lock_channels, punish = excluded.punish""",
            ctx.guild.id,
            setting,
            flags.action,
            flags.threshold,
            flags.lock,
            flags.punish,
        )
        flags_value = f"\nPunishment set to **{self.to_action(flags.action)}**, threshold set to **{flags.threshold}**, lock channels set to **{flags.lock}**, punish new members set to **{flags.punish}**"
        return await ctx.approve(
            f"successfully **{'ENABLED' if setting is True else 'DISABLED'}** mass joins antiraid{flags_value}"
        )

    @antiraid.command(name="state", description="Turn off server's raid state")
    @has_permissions(manage_guild=True)
    async def antiraid_state(self, ctx: Context):
        try:
            await self.bot.pool.execute(
                """UPDATE antiraid SET raid_status = FALSE WHERE guild_id = $1""",
                ctx.guild.id,
            )
        except Exception:
            raise CommandError("you haven't setup antiraid yet")
        return await ctx.approve("successfully **ENDED** the raid")

async def setup(bot: Client):
    await bot.add_cog(AntiRaid(bot))