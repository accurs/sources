import asyncio
import re
from asyncio import Event, Lock, ensure_future
from collections import defaultdict
from datetime import datetime, timedelta
from typing import (Annotated, Any, Callable, Dict, List, Literal, Optional,
                    Union)

import humanize
from discord import (Client, Color, Embed, File, Forbidden, Guild, Interaction,
                     Member, Message, NotFound, Object, PartialEmoji,
                     PermissionOverwrite, Role, TextChannel, Thread, User,
                     VoiceChannel)
from discord.ext.commands import (BucketType, Cog, CommandError, Emoji,
                                  MaxConcurrencyReached, MultipleRoles, Range,
                                  SafeRoleConverter, TextChannelConverter,
                                  Timeframe, bot_has_permissions, command,
                                  group, has_permissions, hybrid_group,
                                  max_concurrency)
from discord.utils import utcnow
from loguru import logger
from system.classes.builtins import human_join
from system.managers.flags import ModerationFlags
from system.patch.context import Context

from .views import Confirm


class Channel(TextChannelConverter):
    async def convert(self, ctx: Context, argument: str):
        if argument == "all":
            return argument

        return await super().convert(ctx, argument)


class Moderation(Cog):
    def __init__(self, bot: Client):
        self.bot = bot
        self.lock: Lock = Lock()
        self.locks = defaultdict(Lock)
        self.events: Dict[str, Event] = {}
        self.action_map = {
            "ban": "banned",
            "kick": "kicked",
            "jail": "jailed",
            "unjail": "unjailed",
            "mute": "muted",
            "unmute": "unmuted",
            "warn": "warned",
            "unban": "unbanned",
            "unbanall": "cleared bans",
            "nickname": "altered a member's nickname",
            "forcenick": "forced a member's nickname",
            "lock": "started a channel lockdown",
            "softban": "soft banned",
            "nuke": "nuked",
            "unlockall": "ended the lockdown",
            "unlock": "ended a channel lockdown",
            "imagemute": "image muted",
            "imageunmute": "removed a image mute",
        }  # this is just encase anyone wants to customize the behavior in the future

    async def get_user(self, user_id: int):
        if user := self.bot.get_user(user_id):
            return user
        else:
            return await self.bot.fetch_user(user_id)

    async def moderation_entry(self, ctx: Context, **kwargs: Any):
        async with self.locks["moderation_entry"]:
            reason = kwargs.pop("reason", "No Reason Provided")
            if not (action := self.action_map.get(ctx.command.qualified_name.lower())):
                return
            target = kwargs.pop(
                "member",
                kwargs.pop("user", kwargs.pop("channel", kwargs.pop("user_id", "all"))),
            )
            if isinstance(target, int):
                target = await self.get_user(target)
            self.bot.dispatch("moderation_case", ctx, target, action, reason, **kwargs)

    async def do_removal(
        self,
        ctx: Context,
        amount: int,
        predicate: Callable[[Message], bool] = lambda _: True,
        *,
        before: Optional[Message] = None,
        after: Optional[Message] = None,
    ) -> List[Message]:
        """
        A helper function to do bulk message removal.
        """

        if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            raise CommandError("I don't have permission to delete messages!")

        if not before:
            before = ctx.message

        def check(message: Message) -> bool:
            if message.created_at < (utcnow() - timedelta(weeks=2)):
                return False

            elif message.pinned:
                return False

            return predicate(message)

        await ctx.message.delete()
        messages = await ctx.channel.purge(
            limit=amount,
            check=check,
            before=before,
            after=after,
        )
        if not messages:
            raise CommandError("No messages were found, try a larger search?")

        return messages

    @Cog.listener()
    async def on_member_join(self, member: Member):
        if await self.bot.db.fetchrow(
            "SELECT * FROM jail WHERE user_id = $1 AND guild_id = $2",
            member.id,
            member.guild.id,
        ):
            if role_id := self.bot.db.fetchval(
                "SELECT role_id FROM moderation WHERE guild_id = $1", member.guild.id
            ):
                if role := member.guild.get_role(role_id):
                    await member.add_roles(role, reason="Jailed member")

    @Cog.listener()
    async def on_member_remove(self, member: Member):
        await self.bot.db.execute(
            """
            INSERT INTO role_restore VALUES ($1,$2,$3)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET
            roles = $3
            """,
            member.guild.id,
            member.id,
            list(map(lambda r: r.id, member.roles)),
        )

    @Cog.listener("on_member_update")
    async def on_forcenick(self, before: Member, after: Member):
        if before.guild.me.guild_permissions.manage_nicknames:
            if str(before.nick) != str(after.nick):
                if nickname := await self.bot.db.fetchval(
                    "SELECT nickname FROM forcenick WHERE guild_id = $1 AND user_id = $2",
                    before.guild.id,
                    before.id,
                ):
                    if str(after.nick) != nickname:
                        if (
                            after.top_role < after.guild.me.top_role
                            and after.id != after.guild.owner_id
                        ):
                            await after.edit(nick=nickname, reason="Force nickname")

    async def notify(
        self: "Moderation",
        author: Member,
        command: Literal["ban", "kick", "jail"],
        victim: Member,
        reason: str,
    ):
        action = f"{command}ned" if command == "ban" else f"{command}ed"
        embed = (
            Embed(
                color=Color.red(),
                title=action.capitalize(),
                description=f"You have been {action} by **{author}** in **{author.guild}**",
                timestamp=datetime.now(),
            )
            .add_field(name="Reason", value=reason.split(" - ")[1])
            .set_thumbnail(url=author.guild.icon)
            .set_footer(
                text="for more about this punishment, please contact a staff member"
            )
        )

        try:
            await victim.send(embed=embed)
            return None
        except Exception:
            return "Couldn't DM member"

    @command(aliases=["bc", "botpurge", "botclear", "botclean", "bp"])
    @has_permissions(manage_messages=True)
    async def cleanup(
        self,
        ctx: Context,
        amount: Annotated[
            int,
            Range[int, 1, 1000],
        ] = 100,
    ):
        """
        Remove messages from bots.
        """

        await self.do_removal(
            ctx,
            amount,
            lambda message: (
                message.author.bot
                or message.content.startswith(
                    (
                        ctx.clean_prefix,
                        self.bot.user.mention,
                        ",",
                        ";",
                        ".",
                        "!",
                        "$",
                        "?",
                        "-",
                        "/",
                        ">",
                        "+",
                        "*",
                        "#",
                        "â€¢",
                    )
                )
            ),
        )

    @command()
    @has_permissions(manage_channels=True)
    async def lock(self, ctx: Context, channel: TextChannel = None):
        """
        lock a channel
        """
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)

        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        ensure_future(self.moderation_entry(ctx, channel=channel))
        return await ctx.send("👍")

    @command()
    @has_permissions(manage_channels=True)
    async def unlock(self: "Moderation", ctx: Context, channel: TextChannel = None):
        """
        unlock a channel
        """
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)

        if overwrite.send_messages:
            raise CommandError("This channel is not locked")

        overwrite.send_messages = True
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        ensure_future(self.moderation_entry(ctx, channel=channel))
        return await ctx.send("👍")

    @command()
    @has_permissions(manage_messages=True)
    async def warn(
        self: "Moderation",
        ctx: Context,
        member: Annotated[Member, Member],
        *,
        reason: Optional[str] = "N/A",
    ):
        """
        Warn a member
        """

        await self.bot.db.execute(
            "INSERT INTO warns VALUES ($1,$2,$3,$4)",
            member.id,
            ctx.guild.id,
            reason,
            utcnow(),
        )
        ensure_future(self.moderation_entry(ctx, member=member, reason=reason))
        return await ctx.success(f"{member.mention} has been warned - **{reason}**")

    @command(name="reactionmute", aliases=["rmute"])
    @has_permissions(moderate_members=True)
    async def reactionmute(self, ctx: Context, *, member: Member):
        await ctx.channel.set_permissions(member, add_reactions=False, use_external_emojis=False)  # type: ignore
        return await ctx.success(
            f"Removed {member.mention}'s permissions to **react** and use **external emotes**."
        )

    @command(name="reactionunmute", aliases=["runmute"])
    @has_permissions(moderate_members=True)
    async def reactionunmute(self, ctx: Context, *, member: Member):
        await ctx.channel.set_permissions(member, add_reactions=True, use_external_emojis=True)  # type: ignore
        return await ctx.success(
            f"Restored {member.mention}'s permissions to **react** and use **external emotes**."
        )

    @command()
    @has_permissions(manage_messages=True)
    async def clearwarns(
        self: "Moderation", ctx: Context, *, member: Annotated[Member, Member]
    ):
        """
        Clear someone's warns
        """

        r = await self.bot.db.execute(
            """
            DELETE FROM warns
            WHERE user_id = $1
            AND guild_id = $2
            """,
            member.id,
            ctx.guild.id,
        )

        if r == "DELETE 0":
            raise CommandError("This member has no warns")

        return await ctx.success("Cleared all warns")

    @command()
    @has_permissions(manage_messages=True)
    async def warns(self: "Moderation", ctx: Context, *, member: Member):
        """
        Check a member's warns
        """

        results = await self.bot.db.fetch(
            """
            SELECT * FROM warns
            WHERE user_id = $1
            AND guild_id = $2
            ORDER BY date ASC
            """,
            member.id,
            ctx.guild.id,
        )

        if not results:
            raise CommandError("This member has no warns")

        return await ctx.paginate(
            Embed(title=f"{member.display_name}'s warns"),
            [
                f"{result.date.strftime('%Y-%m-%d')} - {result.reason}"
                for result in results
            ],
        )

    @hybrid_group(aliases=["c", "clear"], invoke_without_command=True)
    @has_permissions(manage_messages=True)
    async def purge(
        self: "Moderation",
        ctx: Context,
        member: Optional[Member] = None,
        amount: int = 15,
    ) -> Message:
        """
        Clear a certain amount of messages
        """

        if amount > 1000:
            raise CommandError("You can only delete 1000 messages at a time!")

        async with self.locks[ctx.channel.id]:
            if not member:
                await ctx.channel.purge(
                    limit=amount,
                    bulk=True,
                    check=lambda m: not m.pinned,
                    reason=f"Purged by {ctx.author.name}",
                )
            else:
                await ctx.channel.purge(
                    limit=amount,
                    bulk=True,
                    check=lambda m: m.author == member and not m.pinned,
                    reason=f"Purged by {ctx.author.name}",
                )
            await ctx.send("👍", delete_after=2)

    @purge.command(name="user", aliases=["member"])
    @has_permissions(manage_messages=True)
    async def purge_user(
        self: "Moderation", ctx: Context, member: Member, amount: int = 15
    ) -> Message:
        """
        Clear messages from a specific user
        """

        if amount > 1000:
            raise CommandError("You can only delete 1000 messages at a time!")

        async with self.locks[ctx.channel.id]:
            await ctx.channel.purge(
                limit=amount,
                bulk=True,
                reason=f"Purged by {ctx.author.name}",
                check=lambda m: m.author == member and not m.pinned,
            )
            await ctx.send("👍", delete_after=2)

    @purge.command(name="bot", aliases=["bots"])
    @has_permissions(manage_messages=True)
    async def purge_bot(self: "Moderation", ctx: Context, amount: int = 15) -> Message:
        """
        Clear messages from bots
        """

        if amount > 1000:
            raise CommandError("You can only delete 1000 messages at a time!")

        async with self.locks[ctx.channel.id]:
            await ctx.channel.purge(
                limit=amount,
                bulk=True,
                reason=f"Purged by {ctx.author.name}",
                check=lambda m: m.author.bot and not m.pinned,
            )
            await ctx.send("👍", delete_after=2)

    @purge.command(name="links", aliases=["embeds"])
    @has_permissions(manage_messages=True)
    async def purge_embeds(
        self: "Moderation", ctx: Context, amount: int = 15
    ) -> Message:
        """
        Clear messages containing links or embeds
        """
        if amount > 1000:
            raise CommandError("You can only delete 1000 messages at a time!")

        def check(m: Message):
            match = re.search(
                r"(http|ftp|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])",
                m.content,
            )

            return m.embeds or match

        async with self.locks[ctx.channel.id]:
            await ctx.channel.purge(
                limit=amount,
                bulk=True,
                reason=f"Purged by {ctx.author.name}",
                check=check,
            )
            await ctx.send("👍", delete_after=2)

    @purge.command(name="attachments", aliases=["files", "images"])
    @has_permissions(manage_messages=True)
    async def purge_attachments(
        self: "Moderation", ctx: Context, amount: int = 15
    ) -> Message:
        """
        Clear messages containing attachments
        """

        if amount > 1000:
            raise CommandError("You can only delete 1000 messages at a time!")

        async with self.locks[ctx.channel.id]:
            await ctx.channel.purge(
                limit=amount,
                bulk=True,
                reason=f"Purged by {ctx.author.name}",
                check=lambda m: m.attachments,
            )
            await ctx.send("👍", delete_after=2)

    @purge.command(name="humans", aliases=["members"])
    @has_permissions(manage_messages=True)
    async def purge_humans(
        self: "Moderation", ctx: Context, amount: int = 15
    ) -> Message:
        """
        Clear messages from humans
        """

        if amount > 1000:
            raise CommandError("You can only delete 1000 messages at a time!")

        async with self.locks[ctx.channel.id]:
            await ctx.channel.purge(
                limit=amount,
                bulk=True,
                reason=f"Purged by {ctx.author.name}",
                check=lambda m: not m.author.bot,
            )
            await ctx.send("👍", delete_after=2)

    @purge.command(name="invites", aliases=["inv", "invite"])
    @has_permissions(manage_messages=True)
    async def purge_invites(
        self: "Moderation", ctx: Context, amount: int = 15
    ) -> Message:
        """
        Clear messages containing invites
        """

        if amount > 1000:
            raise CommandError("You can only delete 1000 messages at a time!")

        async with self.locks[ctx.channel.id]:
            await ctx.channel.purge(
                limit=amount,
                bulk=True,
                reason=f"Purged by {ctx.author.name}",
                check=lambda m: re.search(self.bot.invite_regex, m.content),
            )
            await ctx.send("👍", delete_after=2)

    @purge.command(name="reactions", aliases=["reacts", "emoji"])
    @has_permissions(manage_messages=True)
    async def purge_reactions(
        self: "Moderation", ctx: Context, amount: int = 15
    ) -> Message:
        """
        Clear messages containing reactions
        """

        if amount > 1000:
            raise CommandError("You can only delete 1000 messages at a time!")

        async with self.locks[ctx.channel.id]:
            await ctx.channel.purge(
                limit=amount,
                bulk=True,
                reason=ctx.author.name,
                check=lambda m: m.emojis,
            )
            await ctx.send("👍", delete_after=2)

    @purge.command(name="stickers", aliases=["sticker"])
    @has_permissions(manage_messages=True)
    async def purge_stickers(
        self: "Moderation", ctx: Context, amount: int = 15
    ) -> Message:
        """
        Clear messages containing stickers
        """

        if amount > 1000:
            raise CommandError("You can only delete 1000 messages at a time!")

        async with self.locks[ctx.channel.id]:
            await ctx.channel.purge(
                limit=amount,
                bulk=True,
                reason=f"Purged by {ctx.author.name}",
                check=lambda m: m.stickers,
            )
            await ctx.send("👍", delete_after=2)

    @purge.command(name="mentions", aliases=["mention"])
    @has_permissions(manage_messages=True)
    async def purge_mentions(
        self: "Moderation", ctx: Context, amount: int = 15
    ) -> Message:
        """
        Clear messages containing mentions
        """

        if amount > 1000:
            raise CommandError("You can only delete 1000 messages at a time!")

        async with self.locks[ctx.channel.id]:
            await ctx.channel.purge(
                limit=amount,
                bulk=True,
                reason=f"Purged by {ctx.author.name}",
                check=lambda m: m.mentions,
            )
            await ctx.send("👍", delete_after=2)

    @purge.command(name="after", aliases=["since"])
    @has_permissions(manage_messages=True)
    async def purge_after(
        self: "Moderation", ctx: Context, message: Message
    ) -> Message:
        """
        Clear messages after a specific message
        """

        if message.channel != ctx.channel:
            return await ctx.send("The message must be in this channel!")

        async with self.locks[ctx.channel.id]:
            await ctx.channel.purge(
                limit=300,
                after=message,
                before=ctx.message,
                bulk=True,
                reason=f"Purged by {ctx.author.name}",
                check=lambda m: m.mentions,
            )
            await ctx.send("👍", delete_after=2)

    @purge.command(name="between", aliases=["range"])
    @has_permissions(manage_messages=True)
    async def purge_between(
        self: "Moderation", ctx: Context, start: Message, end: Message
    ) -> Message:
        """
        Clear messages between two specific messages
        """

        if start.channel != ctx.channel or end.channel != ctx.channel:
            return await ctx.send("The messages must be in this channel!")

        async with self.locks[ctx.channel.id]:
            await ctx.channel.purge(
                limit=300,
                after=start,
                before=end,
                bulk=True,
                reason=f"Purged by {ctx.author.name}",
                check=lambda m: m.mentions,
            )
            await ctx.send("👍", delete_after=2)

    @purge.command(name="startswith", aliases=["start"])
    @has_permissions(manage_messages=True)
    async def purge_startswith(
        self: "Moderation", ctx: Context, string: str, amount: int = 15
    ) -> Message:
        """
        Clear messages starting with a specific string
        """

        if amount > 1000:
            raise CommandError("You can only delete 1000 messages at a time!")

        async with self.locks[ctx.channel.id]:
            await ctx.channel.purge(
                limit=amount,
                bulk=True,
                reason=ctx.author.name,
                check=lambda m: m.content
                and m.content.lower().startswith(string.lower()),
            )
            await ctx.send("👍", delete_after=2)

    @purge.command(name="endswith", aliases=["end"])
    @has_permissions(manage_messages=True)
    async def purge_endswith(
        self: "Moderation", ctx: Context, string: str, amount: int = 15
    ) -> Message:
        """
        Clear messages ending with a specific string
        """

        if amount > 1000:
            raise CommandError("You can only delete 1000 messages at a time!")

        async with self.locks[ctx.channel.id]:
            await ctx.channel.purge(
                limit=amount,
                bulk=True,
                reason=ctx.author.name,
                check=lambda m: m.content
                and m.content.lower().endswith(string.lower()),
            )
            await ctx.send("👍", delete_after=2)

    @purge.command(name="contains", aliases=["contain"])
    @has_permissions(manage_messages=True)
    async def purge_contains(
        self: "Moderation", ctx: Context, string: str, amount: int = 15
    ) -> Message:
        """
        Clear messages containing a specific string
        """

        if amount > 1000:
            raise CommandError("You can only delete 1000 messages at a time!")

        async with self.locks[ctx.channel.id]:
            await ctx.channel.purge(
                limit=amount,
                bulk=True,
                reason=f"Purged by {ctx.author.name}",
                check=lambda m: m.content and string.lower() in m.content.lower(),
            )
            await ctx.send("👍", delete_after=2)

    @purge.before_invoke
    async def before_purge(self, ctx: Context):
        await ctx.message.delete()

    @command()
    @has_permissions(ban_members=True)
    @bot_has_permissions(ban_members=True)
    async def banreason(self: "Moderation", ctx: Context, *, member: User):
        """
        Check the reason why this member was banned
        """

        bans = [entry async for entry in ctx.guild.bans()]
        entry = next((b for b in bans if b.user.id == member.id), None)

        if not entry:
            raise CommandError("This member is **not** banned from this server")

        embed = Embed(
            color=self.bot.color,
            description=f"> **{member}** was banned - {entry.reason}",
        )
        return await ctx.reply(embed=embed)

    async def do_unban(self, ctx, u: Union[Member, User, str]):
        if isinstance(u, User):
            pass  # type: ignore
        elif isinstance(u, Member):
            pass  # type: ignore
        else:
            async for ban in ctx.guild.bans():
                if ban.user.name == u or ban.user.global_name == u:
                    await ctx.guild.unban(Object(ban.user.id))
                    return ban
            return None
        await ctx.guild.unban(Object(u.id))
        return u

    @command(name="unban", brief="Unban a banned user from the guild")
    @has_permissions(ban_members=True)
    @bot_has_permissions(ban_members=True)
    async def unban_member(self, ctx, user_id: Union[int, str]):
        guild = ctx.guild
        try:
            if isinstance(user_id, int):
                banned_entry = await guild.fetch_ban(Object(id=user_id))
                if banned_entry:
                    await guild.unban(banned_entry.user)
                    await ctx.success(
                        f"{banned_entry.user.mention} has been **unbanned**"
                    )
                    ensure_future(self.moderation_entry(ctx, user_id=user_id))
                else:
                    return await ctx.fail("That User is **not banned**")
            else:
                banned_entry = await self.do_unban(ctx, user_id)
                ensure_future(self.moderation_entry(ctx, user_id=user_id))
                await ctx.success(f"`{user_id}` **user** has been **unbanned**")
        except Forbidden:
            return await ctx.warning(
                "I don't have the **necessary permissions** to **unban** members."
            )
        except NotFound:
            return await ctx.fail("That User is **not banned**")

    @command(aliases=["massunban"])
    @has_permissions(ban_members=True)
    @bot_has_permissions(ban_members=True)
    async def unbanall(self: "Moderation", ctx: Context):
        """
        Unban all members in the server
        """

        async with self.locks[f"unban-{ctx.guild.id}"]:
            users = [entry.user async for entry in ctx.guild.bans()]
            m = await ctx.normal(f"Unbanning `{len(users):,}` members...")
            for u in users:
                await ctx.guild.unban(u, reason=f"Massunban by {ctx.author}")
            embed = m.embeds[0]
            ensure_future(self.moderation_entry(ctx))
            embed.description = f"Unbanned `{len(users):,}`** members in **{humanize.precisedelta(utcnow() - m.created_at, format='%0.0f')}"
            return await m.edit(embed=embed)

    @command(aliases=["forcenick", "fn"])
    @has_permissions(manage_guild=True)
    async def forcenickname(
        self: "Moderation",
        ctx: Context,
        member: Annotated[Member, Member],
        *,
        nick: str,
    ):
        """
        Force nickname a member
        """

        if nick.lower() == "none":
            r = await self.bot.db.execute(
                "DELETE FROM forcenick WHERE user_id = $1 AND guild_id = $2",
                member.id,
                ctx.guild.id,
            )

            if r == "DELETE 0":
                raise CommandError(
                    "This member does not have a force nickname assigned"
                )

            await member.edit(nick=None)
            return await ctx.success(f"Removed {member.mention}'s nickname")
        else:
            await self.bot.db.execute(
                """
                INSERT INTO forcenick VALUES ($1,$2,$3)
                ON CONFLICT (guild_id, user_id) 
                DO UPDATE SET nickname = $3 
                """,
                ctx.guild.id,
                member.id,
                nick,
            )
            await member.edit(nick=nick, reason="Forcenickname")
            ensure_future(self.moderation_entry(ctx, member=member))
            return await ctx.success(f"Force nicknamed {member.mention} to `{nick}`")

    @command(aliases=["nick"])
    @has_permissions(manage_nicknames=True)
    async def nickname(
        self: "Moderation",
        ctx: Context,
        member: Annotated[Member, Member],
        *,
        nickname: str,
    ):
        """
        Change a member's nickname
        """

        if nickname == "none":
            await member.edit(nick=None)
            ensure_future(self.moderation_entry(ctx, member=member))
            return await ctx.success(f"Removed **{member.name}'s** nickname")
        else:
            await member.edit(nick=nickname)
            ensure_future(self.moderation_entry(ctx, member=member))
            return await ctx.success(
                f"Changed **{member.name}'s** nickname to {nickname}"
            )

    @command()
    @has_permissions(ban_members=True)
    async def softban(self, ctx: Context, *, member: Annotated[Member, Member]):
        """
        Ban an user just to purge their messages
        """

        await member.ban(delete_message_days=7, reason=f"Softbanned by {ctx.author}")
        await ctx.guild.unban(member)
        ensure_future(self.moderation_entry(ctx, member=member))
        return await ctx.reply("👍")

    @command(aliases=["banish"])
    @has_permissions(ban_members=True)
    async def ban(
        self: "Moderation",
        ctx: Context,
        member: Union[Member, User],
        *,
        reason: str = "N/A",
    ):
        """
        Ban a member from your guild
        """

        reason = ctx.author.name + f" - {reason}"
        notify = None

        if isinstance(member, Member):

            if member.premium_since:
                embed = Embed(
                    color=self.bot.color,
                    description="This member is a **server booster?** Are you sure you want to **ban** them?",
                )
                view = Confirm(ctx.author, member, "ban", reason)

                return await ctx.reply(embed=embed, view=view)

            else:
                notify = await self.notify(ctx.author, ctx.command.name, member, reason)

        await ctx.guild.ban(member, reason=reason)

        ensure_future(self.moderation_entry(ctx, member=member, reason=reason))
        return await ctx.send(f"👍 {f'- {notify}' if notify else ''}")

    @command(aliases=["untimeout", "unt"])
    @has_permissions(moderate_members=True)
    async def unmute(
        self: "Moderation",
        ctx: Context,
        member: Annotated[Member, Member],
        *,
        reason: Optional[str] = "N/A",
    ):
        """
        Remove a member's timeout
        """

        if not member.is_timed_out():
            raise CommandError("This member not timed out")

        await member.timeout(None, reason=f"Untimed out by {ctx.author} - {reason}")

        ensure_future(self.moderation_entry(ctx, member=member, reason=reason))
        return await ctx.reply("👍")

    @command(aliases=["timeout", "tm"])
    @has_permissions(moderate_members=True)
    async def mute(
        self: "Moderation",
        ctx: Context,
        member: Annotated[Member, Member],
        time: Timeframe = 300,
        *,
        reason: Optional[str] = "N/A",
    ):
        """
        Timeout a member
        """

        if member.is_timed_out():
            raise CommandError("This member is timed out")

        await member.timeout(
            timedelta(seconds=time),
            reason=f"Timed out by {ctx.author} - {reason}",
        )

        ensure_future(self.moderation_entry(ctx, member=member, reason=reason))
        return await ctx.reply("👍")

    @command(name="kick")
    @has_permissions(kick_members=True)
    async def kick(
        self: "Moderation",
        ctx: Context,
        member: Annotated[Member, Member],
        *,
        reason: str = "N/A",
    ):
        """
        Kick a member from your guild
        """

        reason = ctx.author.name + f" - {reason}"

        if member.premium_since:
            embed = Embed(
                color=self.bot.color,
                description="This member is a **server booster?** Are you sure you want to **kick** them?",
            )
            view = Confirm(ctx.author, member, "kick", reason)

            return await ctx.reply(embed=embed, view=view)

        await ctx.guild.kick(member, reason=reason)

        notify = await self.notify(ctx.author, ctx.command.name, member, reason)

        ensure_future(self.moderation_entry(ctx, member=member, reason=reason))
        return await ctx.send(f"👍 {f'- {notify}' if notify else ''}")

    @command(
        name="nuke",
    )
    @has_permissions(administrator=True)
    async def nuke(
        self: "Moderation",
        ctx: Context,
    ):
        """
        Clone the channel and delete old channel
        """

        async def channel_nuke(interaction: Interaction):
            try:
                await interaction.channel.delete()
            except Exception:
                return await interaction.fail(
                    f"Unable to nuke {interaction.channel.mention}!"
                )

            chnl = await interaction.channel.clone()
            await chnl.edit(position=interaction.channel.position)
            args = [chnl.id, interaction.channel.id]
            updates = {}
            tasks = []
            channels = await self.bot.db.fetchrow(
                """SELECT welcome_channel, boost_channel, leave_channel FROM config WHERE guild_id = $1""",
                interaction.guild.id,
            )
            queries = [
                "UPDATE config SET welcome_channel = $1 WHERE welcome_channel = $2",
                "UPDATE config SET leave_channel = $1 WHERE leave_channel = $2",
                "UPDATE config SET boost_channel = $1 WHERE boost_channel = $2",
            ]
            if channels.welcome_channel == interaction.channel.id:
                updates["welcome_channel"] = True
                tasks.append(self.bot.db.execute(queries[0], *args))
            else:
                updates["welcome_channel"] = False
            if channels.leave_channel == interaction.channel.id:
                updates["leave_channel"] = True
                tasks.append(self.bot.db.execute(queries[1], *args))
            else:
                updates["leave_channel"] = False
            if channels.boost_channel == interaction.channel.id:
                updates["boost_channel"] = True
                tasks.append(self.bot.db.execute(queries[2], *args))
            else:
                updates["boost_channel"] = False

            await asyncio.gather(*tasks)
            ensure_future(self.moderation_entry(ctx, channel=interaction.channel))
            updated = [
                f"**{k.replace('_', ' ')}**" for k, v in updates.items() if v is True
            ]
            updates_str = human_join(updated, final="and")
            if len(updated) > 0:
                updates_str = (
                    "\n"
                    + updates_str
                    + f" {'has' if len(updated) == 1 else 'have'} been reconfigured"
                )
            return await chnl.normal(
                f"[**#{interaction.channel.name}**]({interaction.channel.jump_url}) has been **nuked**.{updates_str}",
                author=interaction.user,
            )

        return await ctx.confirmation(
            "Are you sure you want to **nuke** this channel?", channel_nuke
        )

    @group(name="role", aliases=["r"], invoke_without_command=True)
    @has_permissions(manage_roles=True)
    async def role(
        self: "Moderation", ctx: Context, member: Member, *, role_input: MultipleRoles
    ):
        """
        Manage roles
        """
        removed = []
        added = []
        roles = member.roles
        for role in role_input:
            if role in roles:
                roles.remove(role)
                removed.append(f"{role.mention}")
            else:
                roles.append(role)
                added.append(f"{role.mention}")
        await member.edit(roles=roles, reason=f"invoked by author | {ctx.author.id}")
        text = ""
        if len(added) > 0:
            if len(added) == 1:
                text += f"**Added** {added[0]} **role** "
            else:
                text += f"**Added** {len(added)} **roles** "
        if len(removed) > 0:
            if len(removed) == 1:
                t = f"{removed[0]} **role**"
            else:
                t = f"{len(removed)} **roles**"
            if len(added) > 0:
                text += f"and **Removed** {t} **from** {member.mention}"
            else:
                text += f"**Removed** {t} **from** {member.mention}"
        else:
            text += f"**to** {member.mention}"
        return await ctx.success(text)

    @role.command(name="restore")
    @has_permissions(manage_roles=True)
    async def role_restore(self, ctx: Context, *, member: Annotated[Member, Member]):
        """
        Restore a member's roles
        """

        role_ids: List[int] = await self.bot.db.fetchval(
            """
            SELECT roles FROM role_restore 
            WHERE guild_id = $1 AND user_id = $2
            """,
            ctx.guild.id,
            member.id,
        )

        roles: List[Role] = list(
            filter(
                lambda r: r and r.is_assignable() and r not in member.roles,
                map(lambda x: ctx.guild.get_role(x), role_ids),
            )
        )

        if not roles:
            raise CommandError("There are no roles to restore")

        roles.extend(member.roles)
        await member.edit(roles=roles, reason=f"Roles restored by {ctx.author}")

        return await ctx.success(f"Restored {member.mention}'s roles")

    @role.group(name="all", invoke_without_command=True)
    async def role_all(self, ctx: Context):
        return await ctx.send_help()

    @role_all.command(
        name="humans",
        aliases=["users"],
        description="gives a role to all non bots",
        example=",role all humans members",
    )
    @has_permissions(manage_roles=True)
    async def role_all_humans(
        self, ctx: Context, *, role: Annotated[Role, SafeRoleConverter]
    ):
        """
        Add a role to all members
        """
        lock = self.locks[f"role_all:{ctx.guild.id}"]
        cancelled = False
        if not (event := self.events.get(str(ctx.guild.id))):
            self.events[str(ctx.guild.id)] = Event()
        event = self.events[str(ctx.guild.id)]
        if lock.locked():
            raise MaxConcurrencyReached(1, BucketType.guild)
        async with lock:
            users = [
                m
                for m in ctx.guild.members
                if m.is_bannable and not m.bot and role not in m.roles
            ]

            if not users:
                raise CommandError("All members have this role")

            message = await ctx.normal(f"Giving {role.mention} to `{len(users)}` users")
            # Define a batch size and delay
            batch_size = 3
            delay = 1  # seconds
            total = len(users)
            # Process users in batches
            for i in range(0, len(users), batch_size):
                batch = users[i : i + batch_size]
                tasks = []
                if event.is_set():
                    cancelled = True
                    break
                for m in batch:
                    tasks.append(m.add_roles(role))

                # Wait for all tasks in the current batch to complete
                await asyncio.gather(*tasks)
                total -= len(batch)
                embed = message.embeds[0]
                embed.description = f"Giving {role.mention} to `{min(i + batch_size, len(users))}/{total + min(i + batch_size, len(users))}` users..."
                # Optionally update the message with progress
                await message.edit(embed=embed)
                # Wait before processing the next batch
                await asyncio.sleep(delay)
        if cancelled:
            self.events.pop(str(ctx.guild.id), None)
            return
        reskin = await ctx.get_reskin()
        return await message.edit(
            embed=Embed(
                color=reskin.color if reskin else self.bot.color,
                description=f"> {ctx.author.mention}: Finished this task in **{humanize.precisedelta(utcnow() - message.created_at, format='%0.0f')}**",
            )
        )

    @role_all.command(
        name="bots",
        aliases=["bot", "robot", "robots"],
        description="gives a role to all bots",
        example=",role all bots members",
    )
    @has_permissions(manage_roles=True)
    async def role_all_bots(
        self, ctx: Context, *, role: Annotated[Role, SafeRoleConverter]
    ):
        """
        Add a role to all members
        """
        lock = self.locks[f"role_all:{ctx.guild.id}"]
        if not (event := self.events.get(str(ctx.guild.id))):
            self.events[str(ctx.guild.id)] = Event()
        event = self.events[str(ctx.guild.id)]
        cancelled = False
        if lock.locked():
            raise MaxConcurrencyReached(1, BucketType.guild)
        async with lock:
            users = [
                m
                for m in ctx.guild.members
                if m.is_bannable and m.bot and role not in m.roles
            ]

            if not users:
                raise CommandError("All bots have this role")

            message = await ctx.normal(f"Giving {role.mention} to `{len(users)}` bots")
            # Define a batch size and delay
            batch_size = 3
            delay = 1  # seconds
            total = len(users)
            # Process users in batches
            for i in range(0, len(users), batch_size):
                batch = users[i : i + batch_size]
                tasks = []
                if event.is_set():
                    cancelled = True
                    break
                for m in batch:
                    tasks.append(m.add_roles(role))

                # Wait for all tasks in the current batch to complete
                await asyncio.gather(*tasks)
                total -= len(batch)
                embed = message.embeds[0]
                embed.description = f"Giving {role.mention} to `{min(i + batch_size, len(users))}/{total + min(i + batch_size, len(users))}` bots..."
                # Optionally update the message with progress
                await message.edit(embed=embed)

                # Wait before processing the next batch
                await asyncio.sleep(delay)

            reskin = await ctx.get_reskin()
        if cancelled:
            self.event.pop(str(ctx.guild.id), None)
            return
        return await message.edit(
            embed=Embed(
                color=reskin.color if reskin else self.bot.color,
                description=f"> {ctx.author.mention}: Finished this task in **{humanize.precisedelta(utcnow() - message.created_at, format='%0.0f')}**",
            )
        )

    @role_all.command(name="cancel", description="cancel a role all task")
    @has_permissions(manage_roles=True)
    async def role_all_cancel(self, ctx: Context):
        if not (event := self.events.get(str(ctx.guild.id))):
            raise CommandError("there is no current `role all` task running")
        event.set()
        return await ctx.normal("cancelled the `role all` task")

    @role.command(name="create", aliases=["make"])
    @has_permissions(manage_roles=True)
    async def role_create(self: "Moderation", ctx: Context, *, name: str):
        """
        Creates a role
        """

        if len(name) < 2:
            raise CommandError("The role name must be at least 2 characters long!")

        role = await ctx.guild.create_role(name=name, reason=ctx.author.name)
        return await ctx.success(f"Successfully created {role.mention}!")

    @role.command(
        name="delete",
    )
    @has_permissions(manage_roles=True)
    async def role_delete(
        self: "Moderation", ctx: Context, *, role: Annotated[Role, SafeRoleConverter]
    ):
        """
        Deletes a role
        """

        if role == ctx.guild.default_role:
            raise CommandError("Unable to delete the default role")

        await role.delete(reason=ctx.author.name)

        return await ctx.success(f"Successfully deleted {role.mention}!")

    @role.command(name="rename", aliases=["edit"])
    @has_permissions(manage_roles=True)
    async def role_rename(
        self: "Moderation",
        ctx: Context,
        role: Annotated[Role, SafeRoleConverter],
        *,
        name: str,
    ):
        """
        Renames a role
        """

        if len(name) < 2:
            raise CommandError("The role name must be at least 2 characters long!")

        await role.edit(name=name, reason=ctx.author.name)
        return await ctx.success(f"Successfully renamed {role.mention} to `{name}`!")

    @role.command(name="color", aliases=["colour"])
    @has_permissions(manage_roles=True)
    async def role_color(
        self: "Moderation",
        ctx: Context,
        role: Annotated[Role, SafeRoleConverter],
        color: Color,
    ):
        """
        Changes the color of a role
        """

        await role.edit(color=color, reason=ctx.author.name)
        return await ctx.success(
            f"Successfully edited {role.mention} color to `{color}`!"
        )

    @role.command(name="position", aliases=["pos"])
    @has_permissions(manage_roles=True)
    async def role_position(
        self: "Moderation",
        ctx: Context,
        role: Annotated[Role, SafeRoleConverter],
        position: int,
    ):
        """
        Changes the position of a role
        """

        await role.edit(position=position, reason=ctx.author.name)

        return await ctx.success(
            f"Successfully edited {role.mention} position to `{position}`!"
        )

    @role.command(name="hoist", aliases=["display"])
    @has_permissions(manage_roles=True)
    async def role_hoist(
        self: "Moderation",
        ctx: Context,
        role: Annotated[Role, SafeRoleConverter],
        hoist: bool,
    ):
        """
        Changes the display of a role
        """

        await role.edit(hoist=hoist, reason=ctx.author.name)
        return await ctx.success(
            f"Successfully edited {role.mention} hoist to `{hoist}`!"
        )

    @role.command(name="mentionable", aliases=["mention"])
    @has_permissions(manage_roles=True)
    async def role_mentionable(
        self: "Moderation",
        ctx: Context,
        role: Annotated[Role, SafeRoleConverter],
        mentionable: bool,
    ):
        """
        Changes the mentionability of a role
        """

        await role.edit(mentionable=mentionable, reason=ctx.author.name)

        return await ctx.success(
            f"Successfully edited {role.mention} mentionability to `{mentionable}`!"
        )

    @role.command(name="icon", aliases=["image"])
    @has_permissions(manage_roles=True)
    async def role_icon(
        self: "Moderation",
        ctx: Context,
        role: Annotated[Role, SafeRoleConverter],
        icon: Union[Emoji, Literal["remove", "clear", "reset", "off"]],
    ):
        """
        Changes the icon of a role
        """

        if isinstance(icon, PartialEmoji):
            if icon.url:
                buffer = await self.bot.session.get(icon.url)
            else:
                buffer = str(icon)
        else:
            buffer = None

        try:
            await role.edit(display_icon=buffer, reason=ctx.author.name)
        except Forbidden:
            raise CommandError(
                f"{ctx.guild.name} needs more boosts to perform this action!"
            )

        return await ctx.success(f"Successfully edited {role.mention} icon!")

    @command(name="setup", aliases=["setmod", "setme"])
    @has_permissions(administrator=True)
    async def setup(self: "Moderation", ctx: Context):
        """
        Setup moderation
        """

        if await self.bot.db.fetch(
            """
            SELECT * FROM moderation
            WHERE guild_id = $1
            """,
            ctx.guild.id,
        ):
            raise CommandError("You already have moderation setup!")

        role = await ctx.guild.create_role(name="jail", reason="mod setup")

        for channel in ctx.guild.channels:
            await channel.set_permissions(role, view_channel=False)

        category = await ctx.guild.create_category(
            name="moderation", reason="mod setup"
        )

        channel = await category.create_text_channel(
            name="jail",
            reason="mod setup",
            overwrites={
                role: PermissionOverwrite(view_channel=True),
                ctx.guild.default_role: PermissionOverwrite(view_channel=False),
            },
        )

        logs = await category.create_text_channel(
            name="logs",
            reason="mod setup",
            overwrites={
                role: PermissionOverwrite(view_channel=False),
                ctx.guild.default_role: PermissionOverwrite(view_channel=False),
            },
        )

        await self.bot.db.execute(
            """
            INSERT INTO moderation (
                guild_id,
                role_id,
                channel_id,
                jail_id,
                category_id
            ) VALUES ($1, $2, $3, $4, $5)
            """,
            ctx.guild.id,
            role.id,
            logs.id,
            channel.id,
            category.id,
        )

        return await ctx.send("👍")

    @command(name="reset", aliases=["unsetup"])
    @has_permissions(administrator=True)
    async def reset(self: "Moderation", ctx: Context):
        """
        Reset moderation
        """

        if channel_ids := await self.bot.db.fetchrow(
            """
            DELETE FROM moderation
            WHERE guild_id = $1
            RETURNING channel_id, role_id, jail_id, category_id
            """,
            ctx.guild.id,
        ):
            for channel in (
                channel
                for channel_id in channel_ids
                if (channel := ctx.guild.get_channel(channel_id))
            ):
                await channel.delete()

            return await ctx.send("👍")
        else:
            raise CommandError("Moderation hasn't been setup yet!")

    @command(name="jail")
    @has_permissions(moderate_members=True)
    async def jail(
        self: "Moderation", ctx: Context, member: Member, *, reason: str = "N/A"
    ):
        """
        Jail a member
        """

        if not (
            data := await self.bot.db.fetchrow(
                """
                SELECT * FROM moderation
                WHERE guild_id = $1
                """,
                ctx.guild.id,
            )
        ):
            raise CommandError("You don't have moderation configured yet!")

        reason = ctx.author.name + f" - {reason}"
        try:
            role = ctx.guild.get_role(data["role_id"])
            member_roles = [r for r in member.roles[1:] if r.is_assignable()]
            r = await self.bot.db.execute(
                """
                INSERT INTO jail VALUES ($1,$2,$3)
                ON CONFLICT (guild_id, user_id)
                DO NOTHING 
                """,
                ctx.guild.id,
                member.id,
                list(map(lambda r: r.id, member_roles)),
            )

            if r == "INSERT 0":
                raise CommandError("This member is **already** jailed")

            roles = [r for r in member.roles if r not in member.roles]
            roles.append(role)
            await member.edit(roles=roles, reason=ctx.author.name + f" - {reason}")
        except Exception:
            await self.bot.db.execute(
                "DELETE FROM jail WHERE user_id = $1 AND guild_id = $2",
                member.id,
                ctx.guild.id,
            )
            raise CommandError(f"Unable to jail {member.mention}!")

        notify = await self.notify(ctx.author, ctx.command.name, member, reason)
        ensure_future(self.moderation_entry(ctx, member=member, reason=reason))

        if channel := ctx.guild.get_channel(data["jail_id"]):
            await channel.send(
                f"{member.mention} you have been jailed by {ctx.author.mention}. Contact the staff members for any disputes about the punishment"
            )

        return await ctx.send(f"👍 {f'- {notify}' if notify else ''}")

    @command(name="unjail")
    @has_permissions(moderate_members=True)
    async def unjail(
        self: "Moderation", ctx: Context, member: Member, *, reason: str = "N/A"
    ):
        """
        Unjail a member
        """

        if not (
            await self.bot.db.fetchrow(
                """
                SELECT * FROM moderation
                WHERE guild_id = $1
                """,
                ctx.guild.id,
            )
        ):
            raise CommandError("You don't have moderation configured yet!")

        try:
            roles = await self.bot.db.fetchval(
                """
                SELECT role_ids FROM jail
                WHERE guild_id = $1
                AND user_id = $2
                """,
                ctx.guild.id,
                member.id,
            )

            if not roles:
                raise CommandError("This member is **not** jailed")

            member_roles = [r for r in member.roles if not r.is_assignable()]
            member_roles.extend(
                list(
                    filter(
                        lambda ro: ro and ro.is_assignable(),
                        map(lambda r: ctx.guild.get_role(r), roles),
                    )
                )
            )

            await member.edit(
                roles=member_roles, reason=ctx.author.name + f" - {reason}"
            )

            await self.bot.db.execute(
                """
                DELETE FROM jail 
                WHERE guild_id = $1 
                AND user_id = $2
                """,
                ctx.guild.id,
                member.id,
            )
        except Exception:
            raise CommandError(f"Unable to unjail {member.mention}!")

        ensure_future(self.moderation_entry(ctx, member=member, reason=reason))
        return await ctx.send("👍")

    @command()
    @has_permissions(move_members=True)
    async def drag(
        self,
        ctx: Context,
        member: Member,
        *,
        voice_channel: Optional[VoiceChannel] = None,
    ):
        """
        Drag a member to a voice channel. If no voice channel is parsed, then the member is going to be dragged in your voice channel
        """

        if not voice_channel and not ctx.author.voice:
            return await ctx.send_help(ctx.command)

        if not member.voice:
            raise CommandError("The member must be in a voice channel to be dragged!")

        if not voice_channel:
            voice_channel = ctx.author.voice.channel

        await member.move_to(voice_channel, reason=f"Dragged by {ctx.author}")
        return await ctx.success(
            f"Succesfully dragged {member.mention} to {voice_channel.mention}"
        )

    @command(aliases=["lockall"])
    @has_permissions(manage_channels=True)
    async def lockdown(self, ctx: Context):
        """
        Lock all server's text channels
        """

        async def yes(interaction: Interaction):
            embed = interaction.message.embeds[0]

            for channel in ctx.guild.text_channels:
                overwrites = channel.overwrites_for(ctx.guild.default_role)
                overwrites.send_messages = False
                await channel.set_permissions(
                    ctx.guild.default_role, overwrite=overwrites
                )

            embed.description = "The server is now on lockdown"
            ensure_future(self.moderation_entry(ctx))
            return await interaction.response.edit_message(embed=embed, view=None)

        return await ctx.confirmation(
            "Are you sure you want to put the **entire** server on lockdown?", yes
        )

    @command()
    @has_permissions(manage_channels=True)
    async def unlockall(self, ctx: Context):
        """
        Unlock all server's text channels
        """

        for channel in ctx.guild.text_channels:
            overwrites = channel.overwrites_for(ctx.guild.default_role)
            overwrites.send_messages = None
            await channel.set_permissions(ctx.guild.default_role, overwrite=overwrites)
        ensure_future(self.moderation_entry(ctx))
        return await ctx.success("Unlocked the entire server")

    @command(aliases=["imute"])
    @has_permissions(moderate_members=True)
    async def imagemute(
        self,
        ctx: Context,
        member: Annotated[Member, Member],
        *,
        channel: Optional[Channel] = None,
    ):
        """
        image mute someone from the channel
        """
        channel = channel or ctx.channel
        if channel == "all":
            for c in ctx.guild.text_channels:
                perms = c.overwrites_for(member)
                perms.attach_files = False
                await c.set_permissions(member, overwrite=perms)
            ensure_future(self.moderation_entry(ctx, member=member))
            return await ctx.send(":thumbsup:")
        else:
            perms = channel.overwrites_for(member)
            perms.attach_files = False
            await channel.set_permissions(member, overwrite=perms)
            ensure_future(self.moderation_entry(ctx, member=member))
            await ctx.send(":thumbsup:")

    @command(aliases=["iunmute"])
    @has_permissions(moderate_members=True)
    async def imageunmute(
        self, ctx: Context, member: Member, channel: Optional[Channel] = None
    ):
        """
        image unmute someone from the channel
        """

        channel = channel or ctx.channel

        if channel == "all":
            for c in ctx.guild.text_channels:
                perms = c.overwrites_for(member)
                perms.attach_files = None
                await c.set_permissions(member, overwrite=perms)
            ensure_future(self.moderation_entry(ctx, member=member))
            return await ctx.send(":thumbsup:")
        else:
            perms = channel.overwrites_for(member)
            perms.attach_files = None
            await channel.set_permissions(member, overwrite=perms)
            ensure_future(self.moderation_entry(ctx, member=member))
            return await ctx.send(":thumbsup:")


async def setup(bot: Client):
    await bot.add_cog(Moderation(bot))
