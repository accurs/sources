from ...types.plugin import Plugin
from ...types.context import Context
from ...managers.ui.embed import Embed

from discord.ext.commands import command
from discord import __version__, utils, Permissions, User, Member

from platform import python_version, system


class Information(Plugin):
    @command(aliases=["latency", "heartbeat"])
    async def ping(self, ctx: Context):
        return await ctx.respond(f"...{round(self.bot.latency * 1000)}ms", author=False)

    @command(aliases=["bi", "bot", "about"])
    async def botinfo(self, ctx: Context):
        if self.bot.user is None:
            return await ctx.respond("something weird occured lol")

        embed = Embed(
            title="aerith",
            description=f"""[invite]({utils.oauth_url(self.bot.user.id, permissions=Permissions(permissions=8))}) · [support](https://discord.gg/aerithbot)
-# **guilds**: {len(self.bot.guilds):,} · **users**: {len(self.bot.users):,} · **commands**: {len(self.bot.commands)} · **plugins**: {len(self.bot.cogs)}
-# **python**: {python_version()} · **discord.py**: {__version__} · **os**: {system()} Ubuntu""",
            thumbnail=self.bot.user.avatar.url if self.bot.user.avatar else None,
        )
        embed.set_footer(text=f"; Requested by {ctx.author.display_name}")

        return await ctx.send(view=embed)

    @command(aliases=["av", "pfp"])
    async def avatar(self, ctx: Context, user: User | Member | None = None):
        user = user or ctx.author

        if user.avatar is None:
            return await ctx.respond("this user has no avatar")

        embed = Embed(title=f"{user.display_name}'s avatar", main_image=user.avatar.url)
        embed.set_footer(text=f"; Requested by {ctx.author.display_name}")

        return await ctx.send(view=embed)

    @command(aliases=["bnnr"])
    async def banner(self, ctx: Context, user: User | Member | None = None):
        user = user or ctx.author

        if user.banner is None:
            return await ctx.respond("this user has no banner")

        embed = Embed(title=f"{user.display_name}'s banner", main_image=user.banner.url)
        embed.set_footer(text=f"; Requested by {ctx.author.display_name}")

        return await ctx.send(view=embed)

    @command(aliases=["gav", "gpfp"])
    async def guildavatar(self, ctx: Context, user: User | Member | None = None):
        if ctx.guild is None:
            return await ctx.respond("this command can only be used in a guild")

        user = user or ctx.author
        member = ctx.guild.get_member(user.id)

        if member is None:
            return await ctx.respond("user not found in this guild")

        if member.guild_avatar is None:
            return await ctx.respond("this user has no guild avatar")

        embed = Embed(
            title=f"{user.display_name}'s guild avatar",
            main_image=member.guild_avatar.url,
        )
        embed.set_footer(text=f"; Requested by {ctx.author.display_name}")

        return await ctx.send(view=embed)

    @command(aliases=["gbnnr"])
    async def guildbanner(self, ctx: Context, user: User | Member | None = None):
        if ctx.guild is None:
            return await ctx.respond("this command can only be used in a guild")

        user = user or ctx.author
        member = ctx.guild.get_member(user.id)

        if member is None:
            return await ctx.respond("user not found in this guild")

        if member.guild_banner is None:
            return await ctx.respond("this user has no guild banner")

        embed = Embed(
            title=f"{user.display_name}'s guild banner",
            main_image=member.guild_banner.url,
        )
        embed.set_footer(text=f"; Requested by {ctx.author.display_name}")

        return await ctx.send(view=embed)

    @command(aliases=["ui", "user"])
    async def userinfo(self, ctx: Context, user: User | Member | None = None):
        user = user or ctx.author
        member = (
            user
            if isinstance(user, Member)
            else ctx.guild.get_member(user.id)
            if ctx.guild
            else None
        )

        display_avatar = (
            member.guild_avatar or user.display_avatar
            if member
            else user.display_avatar
        )
        display_banner = member.guild_banner or user.banner if member else user.banner

        embed = Embed(
            title=f"{user.display_name}",
            description=f"""[avatar]({display_avatar.url}){f" · [banner]({display_banner.url})" if display_banner else ""}
-# **id**: {user.id} · **created**: {user.created_at.strftime("%b %d, %Y")}
-# **bot**: {user.bot}{f" · **joined**: {member.joined_at.strftime('%b %d, %Y')}" if member and member.joined_at else ""}
{f"-# **roles**: {len(member.roles) - 1:,} · **top role**: {member.top_role.mention if member and member.top_role else 'none'}" if member else ""}""",
            main_image=display_banner.url if display_banner else None,
            thumbnail=display_avatar.url,
        )
        embed.set_footer(text=f"; Requested by {ctx.author.display_name}")
        return await ctx.send(view=embed)
