from discord.ext import commands
from discord.ext.commands import Cog, command, group
from discord import Message, Member, User, Role, Embed, PartialEmoji, Emoji, TextChannel, VoiceChannel, Color, PermissionOverwrite, CategoryChannel
from heist.framework.discord import Context
from heist.framework.tools.converters.role import Role as SafeRoleConverter
from humanfriendly import parse_timespan, format_timespan
from discord.utils import utcnow
from datetime import timedelta
from typing import Iterable, Union, cast, Annotated, Literal, Optional
from collections import defaultdict
import asyncio
from discord.errors import Forbidden
from discord.ext.commands import CommandError
import re
from re import search, match

class Moderation(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.locks = defaultdict(asyncio.Lock)

    @command()
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx: Context):
        """Lock the channel"""
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        
        if overwrite.send_messages is False:
            return await ctx.warn(f"{ctx.channel.mention} is already locked")
        
        overwrite.send_messages = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.approve(f"Locked {ctx.channel.mention}")

    @command()
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx: Context):
        """Unlock the channel"""
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        
        if overwrite.send_messages is not False:
            return await ctx.warn(f"{ctx.channel.mention} is already unlocked")
        
        overwrite.send_messages = None
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.approve(f"Unlocked {ctx.channel.mention}")

    @command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: Context, user: Union[Member, User], *, reason: str = None):
        """Ban a user in the guild."""
        if reason is None:
            reason = f"Banned by {ctx.author}"
        if isinstance(user, Member):
            if user == ctx.guild.owner:
                return await ctx.warn(f"You're unable to ban the **server owner**.")
            if user == ctx.author:
                return await ctx.warn(f"You're unable to ban **yourself**.")
            if ctx.author.top_role.position <= user.top_role.position:
                return await ctx.warn(
                    f"You're unable to ban a user with a **higher role** than **yourself**."
                )

        await ctx.guild.ban(user, reason=reason)
        await ctx.approve(f"Successfully **banned** {user.mention}")

    @command(name="unban")
    @commands.has_permissions(moderate_members=True)
    async def unban(self, ctx: Context, *, user: User):
        """Unbans a user"""
        await ctx.guild.unban(user)
        return await ctx.approve(f"{user.mention} has been **unbanned.**")

    @command(name="mute")
    @commands.has_permissions(moderate_members=True)
    async def mute(
        self, ctx: Context, member: Member, *, time: str = "60s"
    ):
        """Mute a member"""
        if member.id in {self.bot.user.id, ctx.author.id}:
            return await ctx.deny(
                f"You cannot **mute** {'yourself' if member.id == ctx.author.id else 'me'}."
            )

        if ctx.author.id != ctx.guild.owner_id and (
            member.top_role.position
            >= max(ctx.guild.me.top_role.position, ctx.author.top_role.position)
        ):
            return await ctx.warn(
                "You cannot **mute** this member due to role hierarchy."
            )

        try:
            duration = parse_timespan(time)
            await member.timeout(
                utcnow() + timedelta(seconds=duration), reason=f"Muted by {ctx.author}"
            )
            await ctx.approve(
                f"**{member.name}** is now muted for {format_timespan(duration)}"
            )
        except:
            await ctx.warn("I'm **unable** to mute this user.")

    @command(name="unmute")
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx: Context, member: Member):
        """Unmute a member"""
        if member.id == self.bot.user.id:
            return await ctx.deny("I cannot **unmute** myself.")

        if member.id == ctx.author.id:
            return await ctx.deny("You cannot **unmute** yourself.")

        if ctx.author.id != ctx.guild.owner_id:
            if member.top_role.position >= ctx.guild.me.top_role.position:
                return await ctx.warn(
                    "You cannot **unmute** a member with a higher role than me."
                )
            if member.top_role.position >= ctx.author.top_role.position:
                return await ctx.warn(
                    "You cannot **unmute** a member with a higher role than you."
                )

        await member.timeout(None)
        return await ctx.approve(f"**{member.name}** is now unmuted.")

    @command(name="kick")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: Context, user: Member, *, reason: str = None):
        """Kick a user from the server."""
        if reason is None:
            reason = f"Kicked by {ctx.author}"
        if ctx.author == ctx.guild.owner:
            pass
        else:
            if user == ctx.guild.owner:
                return await ctx.deny(f"You're unable to **kick** the guild owner.")
            if user == ctx.author:
                return await ctx.deny(f"You're unable to **kick** yourself.")
            if ctx.author.top_role.position <= user.top_role.position:
                return await ctx.warn(
                    f"You're unable to kick a user with a **higher role** than **yourself**."
                )

        await ctx.guild.kick(user, reason=reason)
        await ctx.approve(f"Successfully **kicked** {user.mention}.")

    @group(name="role", aliases=["r"], invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    async def role(self, ctx: Context, user: Member, *, role: Role):
        """Manage a user's roles."""

        if role in user.roles:
            await user.remove_roles(role, reason=f"Role removed by {ctx.author}")
            return await ctx.approve(
                f"**Edited** {user.mention}'s roles (**removed** {role.mention})"
            )
        else:
            await user.add_roles(role, reason=f"Role added by {ctx.author}")
            return await ctx.approve(
                f"**Edited** {user.mention}'s roles  (**added** {role.mention})"
            )

    @role.command(name="create", aliases=["add"])
    @commands.has_permissions(manage_roles=True)
    async def role_create(self, ctx: Context, *, name: str):
        """Create a role"""
        role = await ctx.guild.create_role(name=name)
        return await ctx.approve(f"Created **role** {role.mention}")

    @role.command(name="delete", aliases=["del"])
    @commands.has_permissions(manage_roles=True)
    async def role_delete(self, ctx: Context, *, role: Union[Role, str]):
        """Delete a role"""
        if isinstance(role, str):
            role = ctx.guild.get_role(int(role)) if role.isdigit() else next((r for r in ctx.guild.roles if r.name == role), None)
            if not role:
                return await ctx.warn("Role not found")

        await role.delete()
        return await ctx.approve(f"Deleted **role** `{role.name}`")

    @role.command(name="humans", aliases=["all"])
    @commands.has_permissions(manage_roles=True)
    async def role_humans(self, ctx: Context, *, role: Role):
        """Give all humans a role."""
        if role >= ctx.guild.me.top_role:
            return await ctx.warn(f"Missing permissions to assign {role.mention}")
        
        humans = [m for m in ctx.guild.members if not m.bot and role not in m.roles]
        if not humans:
            return await ctx.warn("No humans need this role")
        
        await ctx.approve(f"Giving {role.mention} to {len(humans)} members. This may take up to {len(humans) * 0.3:.1f} seconds...")
        
        async with self.locks[ctx.guild.id]:
            for member in humans:
                try:
                    await member.add_roles(role, reason=f"Bulk role assignment by {ctx.author}")
                except Exception:
                    continue
                await asyncio.sleep(0.3)
        
        await ctx.approve(f"Successfully gave {role.mention} to {len(humans)} members")

    @role.command(name="rename", aliases=["edit"])
    @commands.has_permissions(manage_roles=True)
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
        return await ctx.approve(f"Successfully renamed {role.mention} to `{name}`!")

    @role.command(name="color", aliases=["colour"])
    @commands.has_permissions(manage_roles=True)
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
        return await ctx.approve(
            f"Successfully edited {role.mention} color to `{color}`!"
        )

    @role.command(name="position", aliases=["pos"])
    @commands.has_permissions(manage_roles=True)
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

        return await ctx.approve(
            f"Successfully edited {role.mention} position to `{position}`!"
        )

    @role.command(name="hoist", aliases=["display"])
    @commands.has_permissions(manage_roles=True)
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
        return await ctx.approve(
            f"Successfully edited {role.mention} hoist to `{hoist}`!"
        )

    @role.command(name="mentionable", aliases=["mention"])
    @commands.has_permissions(manage_roles=True)
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

        return await ctx.approve(
            f"Successfully edited {role.mention} mentionability to `{mentionable}`!"
        )

    @role.command(name="icon", aliases=["image"])
    @commands.has_permissions(manage_roles=True)
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

        return await ctx.approve(f"Successfully edited {role.mention} icon!")

    @group(name="purge", aliases=["c", "clear"], invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx: Context, *, amount: int = 10):
        """Purge messages."""
        await ctx.message.delete()
        purged = await ctx.channel.purge(
            limit=amount,
            bulk=True,
            check=lambda m: not m.pinned,
            reason=f"Purged by {ctx.author.name}",
        )

    @purge.command(
        name="user",
        aliases=["member"],
    )
    @commands.has_permissions(manage_messages=True)
    async def purge_user(self, ctx: Context, user: Member, amount: int = 15):
        """Purge messages sent by a certain user."""
        messages = await ctx.channel.purge(
            limit=amount,
            bulk=True,
            reason=f"Purged by {ctx.author.name}",
            check=lambda m: m.author == user and not m.pinned,
        )
        await ctx.send("👍", delete_after=2)

    @purge.command(name="bots")
    @commands.has_permissions(manage_messages=True)
    async def purge_bots(self, ctx: Context, amount: int = 15):
        """Purge messages sent by bots"""
        messages = await ctx.channel.purge(
            limit=amount,
            bulk=True,
            reason=f"Purged by {ctx.author.name}",
            check=lambda m: m.author.bot and not m.pinned,
        )
        await ctx.send("👍", delete_after=2)

    @purge.command(name="attachments", aliases=["images", "files"])
    @commands.has_permissions(manage_messages=True)
    async def purge_attachments(self, ctx: Context, amount: int = 15):
        messages = await ctx.channel.purge(
            limit=amount,
            bulk=True,
            reason=f"Purged by {ctx.author.name}",
            check=lambda m: m.attachments,
        )
        await ctx.send("👍", delete_after=2)

    @purge.command(name="invites", aliases=["inv", "invite"])
    @commands.has_permissions(manage_messages=True)
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
    @commands.has_permissions(manage_messages=True)
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
    @commands.has_permissions(manage_messages=True)
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
    @commands.has_permissions(manage_messages=True)
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
    @commands.has_permissions(manage_messages=True)
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
    @commands.has_permissions(manage_messages=True)
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
    @commands.has_permissions(manage_messages=True)
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
    @commands.has_permissions(manage_messages=True)
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
    @commands.has_permissions(manage_messages=True)
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

    @command(name="botclear", aliases=["bc"])
    @commands.has_permissions(manage_messages=True)
    async def botclear(self, ctx: Context, amount: int = 15):
        """Purge messages sent by bots"""
        messages = await ctx.channel.purge(
            limit=amount,
            bulk=True,
            reason=f"Purged by {ctx.author.name}",
            check=lambda m: m.author.bot and not m.pinned,
        )
        await ctx.message.delete()

    @purge.command(name="links", description="Purges messages containing links.")
    @commands.has_permissions(manage_messages=True)
    async def purge_links(self, ctx: Context, amount: int = 15):
        """Purge any messages containing links."""

        def links(message: Message):
            match = search(
                r"(http|ftp|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])",
                message.content,
            )

            return message.embeds or match

        messages = await ctx.channel.purge(
            limit=amount,
            bulk=True,
            reason=f"Purged by {ctx.author.name}",
            check=links,
        )
        await ctx.message.delete()

    @group(
        name="emoji",
        description="Returns a large emoji or server emote",
        invoke_without_command=True,
    )
    async def emoji(self, ctx: Context, *, emoji: Union[PartialEmoji, Emoji]):
        """Enlarge an emoji"""
        return await ctx.send(
            file=await emoji.to_file(
                filename=f"{emoji.name}{'.gif' if emoji.animated else '.png'}"
            )
        )

    @emoji.command(
        name="steal",
        aliases=["copy", "add"],
        description="Downloads emote and adds to server",
    )
    @commands.has_permissions(manage_expressions=True)
    async def emoji_steal(
        self, ctx: Context, emoji: Union[Emoji, PartialEmoji], *, name: str = None
    ):
        """Steal an emoji."""
        if not name:
            name = emoji.name

        try:
            emoji = await ctx.guild.create_custom_emoji(
                image=await emoji.read(), name=name
            )
            return await ctx.approve(f"Added **emote** {emoji}")
        except Exception as E:
            return await ctx.warn(f"{E}")

    @emoji.command(
        name="remove",
        aliases=["delete"],
        description="Remove an emoji from the server.",
    )
    @commands.has_permissions(manage_expressions=True)
    async def emoji_remove(self, ctx: Context, *, emoji: Union[Emoji, PartialEmoji]):
        """Delete an emoji."""
        try:
            await emoji.delete()
            return await ctx.approve(f"Removed **emote** `{emoji.name}`")
        except Exception as E:
            return await ctx.warn(f"{E}")

    @emoji.command(name="rename")
    @commands.has_permissions(manage_expressions=True)
    async def emoji_rename(
        self, ctx: Context, emoji: Union[Emoji, PartialEmoji], *, name: str
    ):
        try:
            await emoji.edit(name=name)
            return await ctx.approve(f"Changed {emoji} **name** to **{name}**")
        except Exception as e:
            return await ctx.warn(f"An error occurred: {e}")

    @command(name="imute", aliases=["imagemute"])
    @commands.has_permissions(moderate_members=True)
    async def imute(self, ctx: Context, *, member: Member):
        """Revoke a members image permissions"""
        await ctx.channel.set_permissions(member, attach_files=False, embed_links=False)
        return await ctx.approve(
            f"Removed **attach files & embed links** from **{member.name}**"
        )

    @command(name="iunmute", aliases=["imageunmute"])
    @commands.has_permissions(moderate_members=True)
    async def iunmute(self, ctx: Context, *, member: Member):
        """Restore a members image permissions"""
        await ctx.channel.set_permissions(member, attach_files=True, embed_links=True)
        return await ctx.approve(
            f"Restored **attach files & embed links** to **{member.name}**"
        )

    @command(name="picperms", aliases=["pic"])
    @commands.has_permissions(moderate_members=True)
    async def picperms(self, ctx: Context, *, member: Member):
        """Give a member picture permissions."""
        await ctx.channel.set_permissions(member, attach_files=True, embed_links=True)
        return await ctx.approve(
            f"Now allowing **{member.name}** to **attach files & embed links.**"
        )

    @command(name="slowmode")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx: Context, time: int, *, channel: TextChannel = None):
        """Set the slowmode for the channel."""
        if channel is None:
            channel = ctx.channel
        await channel.edit(slowmode_delay=time)
        return await ctx.approve(f"Set the **slowmode** to {format_timespan(time)}")

    @command(name="hide")
    @commands.has_permissions(manage_channels=True)
    async def hide(self, ctx: Context, *, channel: TextChannel = None):
        """Hide a channel from everyone."""
        if channel is None:
            channel = ctx.channel
        await channel.set_permissions(ctx.guild.default_role, view_channel=False)
        return await ctx.approve(f"I have **hidden** the channel.")

    @command(name="reveal", aliases=["unhide"])
    @commands.has_permissions(manage_channels=True)
    async def reveal(self, ctx: Context, *, channel: TextChannel = None):
        """Reveal a channel to everyone."""
        if channel is None:
            channel = ctx.channel
        await channel.set_permissions(ctx.guild.default_role, view_channel=True)
        return await ctx.approve(f"I have **revealed** the channel.")

    @command(name="pin")
    @commands.has_permissions(manage_messages=True)
    async def pin(self, ctx: Context, *, message: str = None):
        """Pin a message."""
        message = None

        if ctx.message.reference:
            message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        elif message:
            match = match(r"https://discord.com/channels/(\d+)/(\d+)/(\d+)", message)
            if match:
                guild_id, channel_id, message_id = map(int, match.groups())
                if guild_id == ctx.guild.id:
                    channel = ctx.guild.get_channel(channel_id)
                    if channel:
                        message = await channel.fetch_message(message_id)

        if message:
            await message.pin()
            return await ctx.message.add_reaction("📌")

    @command(name="unpin")
    @commands.has_permissions(manage_messages=True)
    async def unpin(self, ctx: Context, *, message: str = None):
        """Unpin a message."""
        message = None

        if ctx.message.reference:
            message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        elif message:
            match = match(r"https://discord.com/channels/(\d+)/(\d+)/(\d+)", message)
            if match:
                guild_id, channel_id, message_id = map(int, match.groups())
                if guild_id == ctx.guild.id:
                    channel = ctx.guild.get_channel(channel_id)
                    if channel:
                        message = await channel.fetch_message(message_id)

        if message:
            await message.unpin()
            return await ctx.message.add_reaction("📌")

    @command(aliases=["forcenick", "fn"])
    @commands.has_permissions(manage_guild=True)
    async def forcenickname(self, ctx: Context, member: Member, *, nick: str = None):
        """Force nickname a member"""
        if not nick:
            r = await self.bot.pool.execute(
                "DELETE FROM forcenick WHERE user_id = $1 AND guild_id = $2",
                member.id, ctx.guild.id
            )
            if r == "DELETE 0":
                return await ctx.warn("This member does not have a force nickname assigned")
            
            await self.bot.redis.delete(f"forcenick:{ctx.guild.id}:{member.id}")
            await member.edit(nick=None)
            return await ctx.approve(f"Removed {member.mention}'s nickname")
        else:
            await self.bot.pool.execute(
                "INSERT INTO forcenick VALUES ($1,$2,$3) ON CONFLICT (guild_id, user_id) DO UPDATE SET nickname = $3",
                ctx.guild.id, member.id, nick
            )
            await self.bot.redis.set(f"forcenick:{ctx.guild.id}:{member.id}", nick, ex=3600)
            await member.edit(nick=nick, reason="Forcenickname")
            return await ctx.approve(f"Force nicknamed {member.mention} to `{nick}`")

    @command(aliases=["nick"])
    @commands.has_permissions(manage_nicknames=True)
    async def nickname(self, ctx: Context, member: Member, *, nickname: str = None):
        """Change a member's nickname"""
        if not nickname:
            await member.edit(nick=None)
            return await ctx.approve(f"Removed **{member.name}'s** nickname")
        else:
            await member.edit(nick=nickname)
            return await ctx.approve(f"Changed **{member.name}'s** nickname to {nickname}")

    @command(name="reactionmute", aliases=["rmute"])
    @commands.has_permissions(moderate_members=True)
    async def reactionmute(self, ctx: Context, *, member: Member):
        await ctx.channel.set_permissions(member, add_reactions=False, use_external_emojis=False)  # type: ignore
        return await ctx.approve(
            f"Removed {member.mention}'s permissions to **react** and use **external emotes**."
        )

    @command(name="reactionunmute", aliases=["runmute"])
    @commands.has_permissions(moderate_members=True)
    async def reactionunmute(self, ctx: Context, *, member: Member):
        await ctx.channel.set_permissions(member, add_reactions=True, use_external_emojis=True)  # type: ignore
        return await ctx.approve(
            f"Restored {member.mention}'s permissions to **react** and use **external emotes**."
        )

    @command(name="nuke")
    @commands.has_permissions(administrator=True)
    async def nuke(self, ctx: Context):
        """Clone the channel and delete old channel"""
        try:
            await ctx.prompt("Are you sure you want to **nuke** this channel?")
            
            old_channel_id = ctx.channel.id
            old_channel_name = ctx.channel.name
            chnl = await ctx.channel.clone()
            await chnl.edit(position=ctx.channel.position)
            await ctx.channel.delete()
            
            welcome_channel = await self.bot.pool.fetchval(
                "SELECT channel_id FROM welcome_message WHERE guild_id = $1 AND channel_id = $2",
                ctx.guild.id, old_channel_id
            )
            
            if welcome_channel:
                await self.bot.pool.execute(
                    "UPDATE welcome_message SET channel_id = $1 WHERE guild_id = $2 AND channel_id = $3",
                    chnl.id, ctx.guild.id, old_channel_id
                )
                message = f"**#{old_channel_name}** has been **nuked**.\nWelcome channel has been reconfigured"
            else:
                message = f"**#{old_channel_name}** has been **nuked**"
            
            async def send_approve(channel, message):
                from discord import Embed
                embed = Embed(
                    description=f"{ctx.config.emojis.context.approve} {ctx.author.mention}: {message}",
                    color=ctx.config.colors.approve
                )
                return await channel.send(embed=embed)
            
            return await send_approve(chnl, message)
                
        except Exception as e:
            return await ctx.warn(f"Unable to nuke the channel: {str(e)}")

    @role.command(name="restore")
    @commands.has_permissions(manage_roles=True)
    async def role_restore(self, ctx: Context, *, member: Annotated[Member, Member]):
        """
        Restore a member's roles
        """

        role_ids: List[int] = await self.bot.pool.fetchval(
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

        return await ctx.approve(f"Restored {member.mention}'s roles")

    @command()
    @commands.has_permissions(move_members=True)
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
        return await ctx.approve(
            f"Succesfully dragged {member.mention} to {voice_channel.mention}"
        )

    @command(aliases=["lockall"])
    @commands.has_permissions(manage_channels=True)
    async def lockdown(self, ctx: Context):
        """Lock all server's text channels"""
        for channel in ctx.guild.text_channels:
            try:
                await channel.set_permissions(ctx.guild.default_role, send_messages=False)
            except:
                continue
        return await ctx.approve("Server has been **locked down**")

    @command(aliases=["unlockall"])
    @commands.has_permissions(manage_channels=True)
    async def unlockdown(self, ctx: Context):
        """Remove lockdown from all server's text channels"""
        for channel in ctx.guild.text_channels:
            try:
                await channel.set_permissions(ctx.guild.default_role, send_messages=None)
            except:
                continue
        return await ctx.approve("Server **lockdown** has been removed")

    @command(aliases=["massunban"])
    @commands.has_permissions(ban_members=True)
    @commands.max_concurrency(1, commands.BucketType.guild)
    async def unbanall(self, ctx: Context):
        """Unban all members in the server"""
        async with self.locks[f"unban-{ctx.guild.id}"]:
            users = [entry.user async for entry in ctx.guild.bans()]
            if not users:
                return await ctx.warn("No banned users found")
            
            m = await ctx.neutral(f"Unbanning `{len(users):,}` members...")
            start_time = utcnow()
            
            for user in users:
                await ctx.guild.unban(user, reason=f"Massunban by {ctx.author}")
            
            from humanfriendly import format_timespan
            duration = (utcnow() - start_time).total_seconds()
            
            return await m.edit(embed=Embed(
                description=f"{ctx.config.emojis.context.approve} {ctx.author.mention}: Unbanned `{len(users):,}` members in {format_timespan(duration)}",
                color=ctx.config.colors.approve
            ))

    @command()
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx: Context, member: Member, *, reason: str = "N/A"):
        """Warn a member"""
        await self.bot.pool.execute(
            "INSERT INTO warns VALUES ($1,$2,$3,$4)",
            member.id, ctx.guild.id, reason, utcnow()
        )
        return await ctx.approve(f"{member.mention} has been warned - **{reason}**")

    @command()
    @commands.has_permissions(manage_messages=True)
    async def warns(self, ctx: Context, *, member: Member):
        """Check a member's warns"""
        results = await self.bot.pool.fetch(
            "SELECT * FROM warns WHERE user_id = $1 AND guild_id = $2 ORDER BY date ASC",
            member.id, ctx.guild.id
        )
        if not results:
            raise CommandError("This member has no warns")
        embed = Embed(title=f"{member.display_name}'s warns")
        return await ctx.paginate(
            [f"{result['date'].strftime('%Y-%m-%d')} - {result['reason']}" for result in results],
            embed=embed
        )

    @command()
    @commands.has_permissions(manage_messages=True)
    async def clearwarns(
        self: "Moderation", ctx: Context, *, member: Annotated[Member, Member]
    ):
        """
        Clear someone's warns
        """

        r = await self.bot.pool.execute(
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

        return await ctx.approve("Cleared all warns")

    @command(name="setup", aliases=["setmod", "setme"])
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx: Context):
        """Setup moderation"""
        if await self.bot.pool.fetch(
            "SELECT * FROM moderation WHERE guild_id = $1", ctx.guild.id
        ):
            raise CommandError("You already have moderation setup!")

        role = await ctx.guild.create_role(name="jail", reason="mod setup")

        for channel in ctx.guild.channels:
            await channel.set_permissions(role, view_channel=False)

        category = await ctx.guild.create_category(name="moderation", reason="mod setup")

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

        await self.bot.pool.execute(
            "INSERT INTO moderation (guild_id, role_id, channel_id, jail_id, category_id) VALUES ($1, $2, $3, $4, $5)",
            ctx.guild.id, role.id, logs.id, channel.id, category.id
        )

        return await ctx.approve("Moderation setup complete")

    @command(name="reset", aliases=["unsetup"])
    @commands.has_permissions(administrator=True)
    async def reset(self, ctx: Context):
        """Reset moderation"""
        if channel_ids := await self.bot.pool.fetchrow(
            "DELETE FROM moderation WHERE guild_id = $1 RETURNING channel_id, role_id, jail_id, category_id",
            ctx.guild.id
        ):
            for channel in (
                channel
                for channel_id in channel_ids
                if (channel := ctx.guild.get_channel(channel_id))
            ):
                await channel.delete()

            return await ctx.approve("Moderation reset complete")
        else:
            raise CommandError("Moderation hasn't been setup yet!")

    @command(name="jail")
    @commands.has_permissions(moderate_members=True)
    async def jail(self, ctx: Context, member: Member, *, reason: str = "N/A"):
        """Jail a member"""
        if not (data := await self.bot.pool.fetchrow(
            "SELECT * FROM moderation WHERE guild_id = $1", ctx.guild.id
        )):
            raise CommandError("You don't have moderation configured yet!")

        if await self.bot.pool.fetchrow(
            "SELECT * FROM jail WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id
        ):
            raise CommandError("This member is **already** jailed")

        try:
            role = ctx.guild.get_role(data["role_id"])
            member_roles = [r for r in member.roles[1:] if r.is_assignable()]
            
            await self.bot.pool.execute(
                "INSERT INTO jail VALUES ($1,$2,$3)",
                ctx.guild.id, member.id, [r.id for r in member_roles]
            )

            roles = [r for r in member.roles if not r.is_assignable()]
            roles.append(role)
            await member.edit(roles=roles, reason=f"{ctx.author.name} - {reason}")
        except Exception:
            await self.bot.pool.execute(
                "DELETE FROM jail WHERE user_id = $1 AND guild_id = $2",
                member.id, ctx.guild.id
            )
            raise CommandError(f"Unable to jail {member.mention}!")

        if channel := ctx.guild.get_channel(data["jail_id"]):
            await channel.send(
                f"{member.mention} you have been jailed by {ctx.author.mention}. Contact the staff members for any disputes about the punishment"
            )

        return await ctx.approve(f"Jailed {member.mention}")

    @command(name="unjail")
    @commands.has_permissions(moderate_members=True)
    async def unjail(self, ctx: Context, member: Member, *, reason: str = "N/A"):
        """Unjail a member"""
        if not await self.bot.pool.fetchrow(
            "SELECT * FROM moderation WHERE guild_id = $1", ctx.guild.id
        ):
            raise CommandError("You don't have moderation configured yet!")

        jail_data = await self.bot.pool.fetchrow(
            "SELECT role_ids FROM jail WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id
        )

        if not jail_data:
            raise CommandError("This member is **not** jailed")
        
        roles = jail_data['role_ids'] or []

        member_roles = [r for r in member.roles if not r.is_assignable()]
        member_roles.extend([
            role for role in [ctx.guild.get_role(r) for r in roles]
            if role and role.is_assignable()
        ])

        await member.edit(roles=member_roles, reason=f"{ctx.author.name} - {reason}")
        await self.bot.pool.execute(
            "DELETE FROM jail WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id
        )

        return await ctx.approve(f"Unjailed {member.mention}")

    @command(name="hardban")
    @commands.has_permissions(administrator=True)
    async def hardban(self, ctx: Context, user: Union[Member, User], *, reason: str = "No reason provided"):
        """Keep a member banned from the server"""
        await ctx.prompt(f"Are you sure you want to **hardban** {user.mention}?")
        
        await self.bot.pool.execute(
            "INSERT INTO hardban VALUES ($1, $2)",
            user.id, ctx.guild.id
        )
        
        await ctx.guild.ban(user, reason=f"Hardbanned by {ctx.author} ({ctx.author.id}): {reason}")
        return await ctx.approve(f"Hardbanned {user.mention}")

    @command(name="unhardban")
    @commands.has_permissions(administrator=True)
    async def unhardban(self, ctx: Context, user: User, *, reason: str = "No reason provided"):
        """Unhardban a hardbanned member"""
        check = await self.bot.pool.fetchrow(
            "SELECT * FROM hardban WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, user.id
        )
        
        if not check:
            raise CommandError(f"{user.mention} is **not** hardbanned")
        
        await self.bot.pool.execute(
            "DELETE FROM hardban WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, user.id
        )
        
        try:
            await ctx.guild.unban(user, reason=f"Unhardbanned by {ctx.author} ({ctx.author.id}): {reason}")
        except:
            pass
        
        return await ctx.approve(f"Unhardbanned {user.mention}")

    @command(name="deafen")
    @commands.has_permissions(deafen_members=True)
    async def deafen(self, ctx: Context, member: Member):
        """Deafen a member in voice channel"""
        if not member.voice:
            raise CommandError("Member must be in a voice channel")
        
        await member.edit(deafen=True, reason=f"Deafened by {ctx.author}")
        return await ctx.approve(f"Deafened {member.mention}")

    @command(name="undeafen")
    @commands.has_permissions(deafen_members=True)
    async def undeafen(self, ctx: Context, member: Member):
        """Undeafen a member in voice channel"""
        if not member.voice:
            raise CommandError("Member must be in a voice channel")
        
        await member.edit(deafen=False, reason=f"Undeafened by {ctx.author}")
        return await ctx.approve(f"Undeafened {member.mention}")

    @group(name="channel", invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def channel(self, ctx: Context):
        """Manage channels in your server"""
        return await ctx.send_help(ctx.command)

    @channel.command(name="voice", aliases=["vc"])
    @commands.has_permissions(manage_channels=True)
    async def channel_voice(self, ctx: Context, *, name: str):
        """Create a voice channel"""
        channel = await ctx.guild.create_voice_channel(name=name)
        return await ctx.approve(f"Created voice channel **{channel.name}**")

    @channel.command(name="stage")
    @commands.has_permissions(manage_channels=True)
    async def channel_stage(self, ctx: Context, *, name: str):
        """Create a stage channel"""
        channel = await ctx.guild.create_stage_channel(name=name)
        return await ctx.approve(f"Created stage channel **{channel.name}**")

    @channel.command(name="forum")
    @commands.has_permissions(manage_channels=True)
    async def channel_forum(self, ctx: Context, *, name: str):
        """Create a forum channel"""
        channel = await ctx.guild.create_forum_channel(name=name)
        return await ctx.approve(f"Created forum channel **{channel.name}**")

    @channel.command(name="create", aliases=["make"])
    @commands.has_permissions(manage_channels=True)
    async def channel_create(self, ctx: Context, *, name: str):
        """Create a channel in your server"""
        channel = await ctx.guild.create_text_channel(name=name)
        return await ctx.approve(f"Created **channel** {channel.mention}")

    @channel.command(name="remove", aliases=["delete", "del"])
    @commands.has_permissions(manage_channels=True)
    async def channel_remove(self, ctx: Context, *, channel: TextChannel):
        """Delete a channel in your server"""
        await channel.delete(reason=f"Deleted by {ctx.author} ({ctx.author.id})")
        return await ctx.approve(f"Deleted **channel** `#{channel.name}`")

    @channel.command(name="rename", aliases=["name"])
    @commands.has_permissions(manage_channels=True)
    async def channel_rename(self, ctx: Context, channel: Optional[TextChannel] = None, *, name: str):
        """Rename a channel"""
        channel = channel or ctx.channel
        if len(name) > 150:
            raise CommandError("Channel names can't be over **150 characters**")
        
        name = name.replace(" ", "-")
        await channel.edit(name=name)
        return await ctx.approve(f"Renamed `#{channel.name}` to **{name}**")

    @channel.command(name="category")
    @commands.has_permissions(manage_channels=True)
    async def channel_category(self, ctx: Context, channel: TextChannel, *, category: CategoryChannel):
        """Move a channel to a new category"""
        await channel.edit(category=category)
        return await ctx.approve(f"Moved {channel.mention} under {category.mention}")

    @channel.command(name="nsfw", aliases=["naughty"])
    @commands.has_permissions(manage_channels=True)
    async def channel_nsfw(self, ctx: Context, *, channel: TextChannel):
        """Toggle NSFW for a channel"""
        await channel.edit(nsfw=not channel.nsfw)
        return await ctx.message.add_reaction("✅")

    @channel.command(name="topic")
    @commands.has_permissions(manage_channels=True)
    async def channel_topic(self, ctx: Context, channel: Optional[TextChannel] = None, *, topic: str):
        """Change a channel's topic"""
        channel = channel or ctx.channel
        if len(topic) > 1024:
            raise CommandError("Channel topics can't be over **1024 characters**")
        
        await channel.edit(topic=topic)
        return await ctx.approve(f"Changed {channel.mention}'s topic to `{topic}`")

    @channel.command(name="hide")
    @commands.has_permissions(manage_channels=True)
    async def channel_hide(self, ctx: Context, channel: Optional[TextChannel] = None):
        """Hide a channel from everyone"""
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, view_channel=False)
        return await ctx.approve(f"Hidden {channel.mention}")

    @channel.command(name="reveal", aliases=["unhide", "show"])
    @commands.has_permissions(manage_channels=True)
    async def channel_reveal(self, ctx: Context, channel: Optional[TextChannel] = None):
        """Reveal a hidden channel"""
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, view_channel=True)
        return await ctx.approve(f"Revealed {channel.mention}")

    @channel.command(name="clone", aliases=["duplicate"])
    @commands.has_permissions(manage_channels=True)
    async def channel_clone(self, ctx: Context, channel: Optional[TextChannel] = None, *, name: str = None):
        """Clone a channel"""
        channel = channel or ctx.channel
        new_channel = await channel.clone(name=name or channel.name, reason=f"Cloned by {ctx.author}")
        return await ctx.approve(f"Cloned {channel.mention} to {new_channel.mention}")

    @channel.command(name="position", aliases=["pos"])
    @commands.has_permissions(manage_channels=True)
    async def channel_position(self, ctx: Context, channel: TextChannel, position: int):
        """Change a channel's position"""
        await channel.edit(position=position)
        return await ctx.approve(f"Moved {channel.mention} to position {position}")

    @channel.command(name="sync")
    @commands.has_permissions(manage_channels=True)
    async def channel_sync(self, ctx: Context, channel: Optional[TextChannel] = None):
        """Sync channel permissions with its category"""
        channel = channel or ctx.channel
        if not channel.category:
            raise CommandError("Channel must be in a category to sync permissions")
        await channel.edit(sync_permissions=True)
        return await ctx.approve(f"Synced {channel.mention} permissions with {channel.category.mention}")

    @channel.command(name="slowmode", aliases=["sm"])
    @commands.has_permissions(manage_channels=True)
    async def channel_slowmode(self, ctx: Context, channel: Optional[TextChannel] = None, seconds: int = 0):
        """Set channel slowmode"""
        channel = channel or ctx.channel
        if seconds > 21600:
            raise CommandError("Slowmode cannot exceed 6 hours (21600 seconds)")
        await channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            return await ctx.approve(f"Disabled slowmode for {channel.mention}")
        return await ctx.approve(f"Set slowmode to {seconds} seconds for {channel.mention}")

    @channel.command(name="info")
    @commands.has_permissions(manage_channels=True)
    async def channel_info(self, ctx: Context, channel: Optional[TextChannel] = None):
        """Get channel information"""
        channel = channel or ctx.channel
        embed = Embed(title=f"#{channel.name}", color=ctx.config.colors.information)
        embed.add_field(name="ID", value=channel.id, inline=True)
        embed.add_field(name="Category", value=channel.category.name if channel.category else "None", inline=True)
        embed.add_field(name="Position", value=channel.position, inline=True)
        embed.add_field(name="NSFW", value="Yes" if channel.nsfw else "No", inline=True)
        embed.add_field(name="Slowmode", value=f"{channel.slowmode_delay}s" if channel.slowmode_delay else "None", inline=True)
        embed.add_field(name="Created", value=channel.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
        if channel.topic:
            embed.add_field(name="Topic", value=channel.topic[:1024], inline=False)
        return await ctx.send(embed=embed)

    @group(name="category", invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def category(self, ctx: Context):
        """Manage categories in your server"""
        return await ctx.send_help(ctx.command)

    @category.command(name="create")
    @commands.has_permissions(manage_channels=True)
    async def category_create(self, ctx: Context, *, name: str):
        """Create a category in your server"""
        category = await ctx.guild.create_category(name=name)
        return await ctx.approve(f"Created category {category.mention}")

    @category.command(name="delete")
    @commands.has_permissions(manage_channels=True)
    async def category_delete(self, ctx: Context, *, category: CategoryChannel):
        """Delete a category in your server"""
        await ctx.prompt(f"Are you sure you want to **delete** the category `#{category.name}`?")
        await category.delete(reason=f"Deleted by {ctx.author} {ctx.author.id}")
        return await ctx.approve(f"Deleted category `#{category.name}`")

    @category.command(name="rename")
    @commands.has_permissions(manage_channels=True)
    async def category_rename(self, ctx: Context, category: CategoryChannel, *, name: str):
        """Rename a category in your server"""
        old_name = category.name
        await category.edit(name=name, reason=f"Edited by {ctx.author} ({ctx.author.id})")
        return await ctx.approve(f"Renamed **{old_name}** to `{name}`")

    @category.command(name="duplicate", aliases=["clone", "remake"])
    @commands.has_permissions(manage_channels=True)
    async def category_duplicate(self, ctx: Context, *, category: CategoryChannel):
        """Clone an already existing category in your server"""
        new_category = await category.clone(name=category.name, reason=f"Cloned by {ctx.author} ({ctx.author.id})")
        return await ctx.approve(f"Cloned {category.mention} to {new_category.mention}")

    @category.command(name="position", aliases=["pos"])
    @commands.has_permissions(manage_channels=True)
    async def category_position(self, ctx: Context, category: CategoryChannel, position: int):
        """Change a category's position"""
        await category.edit(position=position)
        return await ctx.approve(f"Moved {category.mention} to position {position}")

    @category.command(name="info")
    @commands.has_permissions(manage_channels=True)
    async def category_info(self, ctx: Context, category: CategoryChannel):
        """Get category information"""
        embed = Embed(title=category.name, color=ctx.config.colors.information)
        embed.add_field(name="ID", value=category.id, inline=True)
        embed.add_field(name="Position", value=category.position, inline=True)
        embed.add_field(name="Channels", value=len(category.channels), inline=True)
        embed.add_field(name="Created", value=category.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
        return await ctx.send(embed=embed)

async def setup(bot):
    from .events import ModerationEvents
    await bot.add_cog(Moderation(bot))
    await bot.add_cog(ModerationEvents(bot))