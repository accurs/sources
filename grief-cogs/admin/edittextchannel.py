from AAA3A_utils import Cog, CogsUtils, Menu  # isort:skip
from grief.core import commands  # isort:skip
from grief.core.i18n import Translator, cog_i18n  # isort:skip
from grief.core.bot import Grief  # isort:skip
import discord  # isort:skip
import typing  # isort:skip

import datetime

from grief.core.commands.converter import get_timedelta_converter
from grief.core.utils.chat_formatting import box, pagify

TimedeltaConverter = get_timedelta_converter(
    default_unit="s",
    maximum=datetime.timedelta(seconds=21600),
    minimum=datetime.timedelta(seconds=0),
)


def _(untranslated: str) -> str:  # `redgettext` will found these strings.
    return untranslated


ERROR_MESSAGE = _(
    "I attempted to do something that Discord denied me permissions for. Your command failed to successfully complete.\n{error}"
)

_ = Translator("DiscordEdit", __file__)


class PositionConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> int:
        try:
            position = int(argument)
        except ValueError:
            raise commands.BadArgument("The position must be an integer.")
        max_guild_text_channels_position = len(
            [c for c in ctx.guild.channels if isinstance(c, discord.TextChannel)]
        )
        if position <= 0 or position >= max_guild_text_channels_position + 1:
            raise commands.BadArgument(
                f"The indicated position must be between 1 and {max_guild_text_channels_position}."
            )
        position -= 1
        return position


class PermissionConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> str:
        permissions = [
            key
            for key, value in dict(discord.Permissions.all_channel()).items()
            if value
        ]
        if argument not in permissions:
            raise commands.BadArgument(_("This permission is invalid."))
        return argument


@cog_i18n(_)
class EditTextChannel(Cog):
    """A cog to edit text channels!"""

    def __init__(self, bot: Grief) -> None:  # Never executed except manually.
        super().__init__(bot=bot)

    async def check_text_channel(
        self, ctx: commands.Context, channel: discord.TextChannel
    ) -> bool:
        # if (
        #     not channel.permissions_for(ctx.author).manage_channels
        #     and ctx.author.id != ctx.guild.owner.id
        #     and ctx.author.id not in ctx.bot.owner_ids
        # ):
        #     raise commands.UserFeedbackCheckFailure(
        #         _(
        #             "I can not let you edit the text channel {channel.mention} ({channel.id}) because you don't have the `manage_channel` permission."
        #         ).format(channel=channel)
        #     )
        if not channel.permissions_for(ctx.me).manage_channels:
            raise commands.UserFeedbackCheckFailure(
                _(
                    "I can not edit the text channel {channel.mention} ({channel.id}) because I don't have the `manage_channel` permission."
                ).format(channel=channel)
            )
        return True

    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.hybrid_group()
    async def edittextchannel(self, ctx: commands.Context) -> None:
        """Commands for edit a text channel."""
        pass

    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @edittextchannel.command(name="create")
    async def edittextchannel_create(
        self,
        ctx: commands.Context,
        category: typing.Optional[discord.CategoryChannel] = None,
        *,
        name: str,
    ) -> None:
        """Create a text channel."""
        try:
            await ctx.guild.create_text_channel(
                name=name,
                category=category,
                reason=f"{ctx.author} ({ctx.author.id}) has created the text channel #{name}.",
            )
        except discord.HTTPException as e:
            raise commands.UserFeedbackCheckFailure(
                _(ERROR_MESSAGE).format(error=box(e, lang="py"))
            )

    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @edittextchannel.command(name="list")
    async def edittextchannel_list(
        self,
        ctx: commands.Context,
    ) -> None:
        """List all text channels in the current guild."""
        description = "".join(
            f"\n**•** **{channel.position + 1}** - {channel.mention} - #{channel.name} ({channel.id}) - {len(channel.members)} members"
            for channel in sorted(ctx.guild.text_channels, key=lambda x: x.position)
        )
        embed: discord.Embed = discord.Embed(color=await ctx.embed_color())
        embed.title = _("List of text channels in {guild.name} ({guild.id})").format(
            guild=ctx.guild
        )
        embeds = []
        pages = pagify(description, page_length=4096)
        for page in pages:
            e = embed.copy()
            e.description = page
            embeds.append(e)
        await Menu(pages=embeds).start(ctx)

    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @edittextchannel.command(name="clone")
    async def edittextchannel_clone(
        self,
        ctx: commands.Context,
        channel: typing.Optional[discord.TextChannel],
        *,
        name: str,
    ) -> None:
        """Clone a text channel."""
        if channel is None:
            channel = ctx.channel
        await self.check_text_channel(ctx, channel)
        try:
            await channel.clone(
                name=name,
                reason=f"{ctx.author} ({ctx.author.id}) has cloned the text channel #{channel.name} ({channel.id}).",
            )
        except discord.HTTPException as e:
            raise commands.UserFeedbackCheckFailure(
                _(ERROR_MESSAGE).format(error=box(e, lang="py"))
            )

    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @edittextchannel.command(name="invite")
    async def edittextchannel_invite(
        self,
        ctx: commands.Context,
        channel: typing.Optional[discord.TextChannel],
        max_age: typing.Optional[float] = None,
        max_uses: typing.Optional[int] = None,
        temporary: typing.Optional[bool] = False,
        unique: typing.Optional[bool] = True,
    ) -> None:
        """Create an invite for a text channel.

        `max_age`: How long the invite should last in days. If it's 0 then the invite doesn't expire.
        `max_uses`: How many uses the invite could be used for. If it's 0 then there are unlimited uses.
        `temporary`: Denotes that the invite grants temporary membership (i.e. they get kicked after they disconnect).
        `unique`: Indicates if a unique invite URL should be created. Defaults to True. If this is set to False then it will return a previously created invite.
        """
        if channel is None:
            channel = ctx.channel
        await self.check_text_channel(ctx, channel)
        try:
            invite = await channel.create_invite(
                max_age=(max_age or 0) * 86400,
                max_uses=max_uses,
                temporary=temporary,
                unique=unique,
                reason=f"{ctx.author} ({ctx.author.id}) has create an invite for the text channel #{channel.name} ({channel.id}).",
            )
        except discord.HTTPException as e:
            raise commands.UserFeedbackCheckFailure(
                _(ERROR_MESSAGE).format(error=box(e, lang="py"))
            )
        else:
            await ctx.send(invite.url)

    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @edittextchannel.command(name="name")
    async def edittextchannel_name(
        self,
        ctx: commands.Context,
        channel: typing.Optional[discord.TextChannel],
        name: str,
    ) -> None:
        """Edit text channel name."""
        if channel is None:
            channel = ctx.channel
        await self.check_text_channel(ctx, channel)
        try:
            await channel.edit(
                name=name,
                reason=f"{ctx.author} ({ctx.author.id}) has edited the text channel #{channel.name} ({channel.id}).",
            )
        except discord.HTTPException as e:
            raise commands.UserFeedbackCheckFailure(
                _(ERROR_MESSAGE).format(error=box(e, lang="py"))
            )

    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @edittextchannel.command(name="topic")
    async def edittextchannel_topic(
        self,
        ctx: commands.Context,
        channel: typing.Optional[discord.TextChannel],
        *,
        topic: str,
    ) -> None:
        """Edit text channel topic."""
        if channel is None:
            channel = ctx.channel
        await self.check_text_channel(ctx, channel)
        try:
            await channel.edit(
                topic=topic,
                reason=f"{ctx.author} ({ctx.author.id}) has edited the text channel #{channel.name} ({channel.id}).",
            )
        except discord.HTTPException as e:
            raise commands.UserFeedbackCheckFailure(
                _(ERROR_MESSAGE).format(error=box(e, lang="py"))
            )

    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @edittextchannel.command(name="position")
    async def edittextchannel_position(
        self,
        ctx: commands.Context,
        channel: typing.Optional[discord.TextChannel],
        *,
        position: PositionConverter,
    ) -> None:
        """Edit text channel position.

        Warning: Only text channels are taken into account. Channel 1 is the highest positioned text channel.
        Channels cannot be moved to a position that takes them out of their current category.
        """
        if channel is None:
            channel = ctx.channel
        await self.check_text_channel(ctx, channel)
        try:
            await channel.edit(
                position=position,
                reason=f"{ctx.author} ({ctx.author.id}) has edited the text channel #{channel.name} ({channel.id}).",
            )
        except discord.HTTPException as e:
            raise commands.UserFeedbackCheckFailure(
                _(ERROR_MESSAGE).format(error=box(e, lang="py"))
            )

    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @edittextchannel.command(name="nsfw")
    async def edittextchannel_nsfw(
        self,
        ctx: commands.Context,
        channel: typing.Optional[discord.TextChannel],
        nsfw: bool = None,
    ) -> None:
        """Edit text channel nsfw."""
        if channel is None:
            channel = ctx.channel
        await self.check_text_channel(ctx, channel)
        if nsfw is None:
            nsfw = not channel.nsfw
        try:
            await channel.edit(
                nsfw=nsfw,
                reason=f"{ctx.author} ({ctx.author.id}) has edited the text channel #{channel.name} ({channel.id}).",
            )
        except discord.HTTPException as e:
            raise commands.UserFeedbackCheckFailure(
                _(ERROR_MESSAGE).format(error=box(e, lang="py"))
            )

    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @edittextchannel.command(name="syncpermissions")
    async def edittextchannel_sync_permissions(
        self,
        ctx: commands.Context,
        channel: typing.Optional[discord.TextChannel],
        sync_permissions: bool = None,
    ) -> None:
        """Edit text channel syncpermissions with category."""
        if channel is None:
            channel = ctx.channel
        await self.check_text_channel(ctx, channel)
        if sync_permissions is None:
            sync_permissions = not channel.permissions_synced
        try:
            await channel.edit(
                sync_permissions=sync_permissions,
                reason=f"{ctx.author} ({ctx.author.id}) has edited the text channel #{channel.name} ({channel.id}).",
            )
        except discord.HTTPException as e:
            raise commands.UserFeedbackCheckFailure(
                _(ERROR_MESSAGE).format(error=box(e, lang="py"))
            )

    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @edittextchannel.command(name="category")
    async def edittextchannel_category(
        self,
        ctx: commands.Context,
        channel: typing.Optional[discord.TextChannel],
        category: discord.CategoryChannel,
    ) -> None:
        """Edit text channel category."""
        if channel is None:
            channel = ctx.channel
        await self.check_text_channel(ctx, channel)
        try:
            await channel.edit(
                category=category,
                reason=f"{ctx.author} ({ctx.author.id}) has edited the text channel #{channel.name} ({channel.id}).",
            )
        except discord.HTTPException as e:
            raise commands.UserFeedbackCheckFailure(
                _(ERROR_MESSAGE).format(error=box(e, lang="py"))
            )

    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @edittextchannel.command(name="slowmodedelay")
    async def edittextchannel_slowmode_delay(
        self,
        ctx: commands.Context,
        channel: typing.Optional[discord.TextChannel],
        slowmode_delay: TimedeltaConverter,
    ) -> None:
        """Edit text channel slowmode delay.

        Specifies the slowmode rate limit for user in this channel, in seconds. A value of 0s disables slowmode. The maximum value possible is 21600s.
        """
        if channel is None:
            channel = ctx.channel
        await self.check_text_channel(ctx, channel)
        slowmode_delay = int(slowmode_delay.total_seconds())
        if slowmode_delay < 0 or slowmode_delay > 21600:
            await ctx.send_help()
            return
        try:
            await channel.edit(
                slowmode_delay=slowmode_delay,
                reason=f"{ctx.author} ({ctx.author.id}) has edited the text channel #{channel.name} ({channel.id}).",
            )
        except discord.HTTPException as e:
            raise commands.UserFeedbackCheckFailure(
                _(ERROR_MESSAGE).format(error=box(e, lang="py"))
            )

    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @edittextchannel.command(name="type")
    async def edittextchannel_type(
        self,
        ctx: commands.Context,
        channel: typing.Optional[discord.TextChannel],
        _type: typing.Literal["0", "5"],
    ) -> None:
        """Edit text channel type.

        `text`: 0
        `news`: 5
        Currently, only conversion between ChannelType.text and ChannelType.news is supported. This is only available to guilds that contain NEWS in Guild.features.
        """
        if channel is None:
            channel = ctx.channel
        await self.check_text_channel(ctx, channel)
        _type = discord.ChannelType(int(_type))
        try:
            await channel.edit(
                type=_type,
                reason=f"{ctx.author} ({ctx.author.id}) has edited the text channel #{channel.name} ({channel.id}).",
            )
        except discord.HTTPException as e:
            raise commands.UserFeedbackCheckFailure(
                _(ERROR_MESSAGE).format(error=box(e, lang="py"))
            )

    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @edittextchannel.command(name="defaultautoarchiveduration")
    async def edittextchannel_default_auto_archive_duration(
        self,
        ctx: commands.Context,
        channel: typing.Optional[discord.TextChannel],
        default_auto_archive_duration: typing.Literal["60", "1440", "4320", "10080"],
    ) -> None:
        """Edit text channel default auto archive duration.

        The new default auto archive duration in minutes for threads created in this channel. Must be one of `60`, `1440`, `4320`, or `10080`.
        """
        if channel is None:
            channel = ctx.channel
        await self.check_text_channel(ctx, channel)
        try:
            await channel.edit(
                default_auto_archive_duration=int(default_auto_archive_duration),
                reason=f"{ctx.author} ({ctx.author.id}) has edited the text channel #{channel.name} ({channel.id}).",
            )
        except discord.HTTPException as e:
            raise commands.UserFeedbackCheckFailure(
                _(ERROR_MESSAGE).format(error=box(e, lang="py"))
            )

    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @edittextchannel.command(name="defaultthreadslowmodedelay")
    async def edittextchannel_default_thread_slowmode_delay(
        self,
        ctx: commands.Context,
        channel: typing.Optional[discord.TextChannel],
        default_thread_slowmode_delay: commands.Range[int, 0, 21_600],
    ) -> None:
        """Edit text channel default thread slowmode delay.

        The new default thread slowmode delay in seconds for threads created in this channel. Must be between 0 and 21600 (6 hours) seconds.
        """
        if channel is None:
            channel = ctx.channel
        await self.check_text_channel(ctx, channel)
        try:
            await channel.edit(
                default_thread_slowmode_delay=default_thread_slowmode_delay,
                reason=f"{ctx.author} ({ctx.author.id}) has edited the text channel #{channel.name} ({channel.id}).",
            )
        except discord.HTTPException as e:
            raise commands.UserFeedbackCheckFailure(
                _(ERROR_MESSAGE).format(error=box(e, lang="py"))
            )

    @commands.has_permissions(administrator=True)
    @edittextchannel.command(name="overwrites", aliases=["permissions", "perms"])
    async def edittextchannel_overwrites(
        self,
        ctx: commands.Context,
        channel: typing.Optional[discord.TextChannel],
        roles_or_users: commands.Greedy[
            typing.Union[discord.Member, discord.Role, typing.Literal["everyone"]]
        ],
        true_or_false: typing.Optional[bool],
        permissions: commands.Greedy[PermissionConverter],
    ) -> None:
        """Edit text channel overwrites/permissions.

        You may not specify `True` or `False` to reset the permission(s).
        You must possess the permissions you wish to modify.

        • `create_instant_invite`
        • `manage_channels`
        • `add_reactions`
        • `priority_speaker`
        • `stream`
        • `read_messages`
        • `send_messages`
        • `send_tts_messages`
        • `manage_messages`
        • `embed_links`
        • `attach_files`
        • `read_message_history`
        • `mention_everyone`
        • `external_emojis`
        • `connect`
        • `speak`
        • `mute_members`
        • `deafen_members`
        • `move_members`
        • `use_voice_activation`
        • `manage_roles`
        • `manage_webhooks`
        • `use_application_commands`
        • `request_to_speak`
        • `manage_threads`
        • `create_public_threads`
        • `create_private_threads`
        • `external_stickers`
        • `send_messages_in_threads`
        """
        if channel is None:
            channel = ctx.channel
        await self.check_text_channel(ctx, channel)
        targets = list(roles_or_users)
        for r in roles_or_users:
            if r == "everyone":
                targets.remove(r)
                targets.append(ctx.guild.default_role)
        if not targets:
            raise commands.UserFeedbackCheckFailure(
                _(
                    "You need to provide a role or user you want to edit permissions for."
                )
            )
        # for target in targets:
        #     if (
        #         ctx.author != ctx.guild.owner
        #         and (
        #             target if isinstance(target, discord.Role) else target.top_role
        #         )
        #         >= ctx.author.top_role
        #     ):
        #         raise commands.UserFeedbackCheckFailure(_("You cannot change the permissions of a role/member higher up the hierarchy than your top role."))
        #     if (target if isinstance(target, discord.Role) else target.top_role) >= ctx.me.top_role:
        #         raise commands.UserFeedbackCheckFailure(_("I cannot change the permissions of a role/member higher up the hierarchy than my top role."))
        if not permissions:
            raise commands.UserFeedbackCheckFailure(
                _("You need to provide at least one permission.")
            )
        channel_permissions = channel.permissions_for(ctx.author)
        for permission in permissions:
            if not getattr(channel_permissions, permission):
                raise commands.UserFeedbackCheckFailure(
                    _(
                        "You don't have the permission {permission_name} in this channel."
                    ).format(permission_name=permission)
                )
        overwrites = channel.overwrites
        for target in targets:
            if target in overwrites:
                overwrites[target].update(
                    **{permission: true_or_false for permission in permissions}
                )
            else:
                perm = discord.PermissionOverwrite(
                    **{permission: true_or_false for permission in permissions}
                )
                overwrites[target] = perm
        try:
            await channel.edit(
                overwrites=overwrites,
                reason=f"{ctx.author} ({ctx.author.id}) has edited the text channel #{channel.name} ({channel.id}).",
            )
        except discord.HTTPException as e:
            raise commands.UserFeedbackCheckFailure(
                _(ERROR_MESSAGE).format(error=box(e, lang="py"))
            )

    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @edittextchannel.command(name="delete")
    async def edittextchannel_delete(
        self,
        ctx: commands.Context,
        channel: typing.Optional[discord.TextChannel],
        confirmation: bool = False,
    ) -> None:
        """Delete a text channel."""
        if channel is None:
            channel = ctx.channel
        await self.check_text_channel(ctx, channel)
        if not confirmation and not ctx.assume_yes:
            if ctx.bot_permissions.embed_links:
                embed: discord.Embed = discord.Embed()
                embed.title = _("⚠️ - Delete text channel")
                embed.description = _(
                    "Do you really want to delete the text channel {channel.mention} ({channel.id})?"
                ).format(channel=channel)
                embed.color = 0xF00020
                content = ctx.author.mention
            else:
                embed = None
                content = f"{ctx.author.mention} " + _(
                    "Do you really want to delete the text channel {channel.mention} ({channel.id})?"
                ).format(channel=channel)
            if not await CogsUtils.ConfirmationAsk(ctx, content=content, embed=embed):
                await CogsUtils.delete_message(ctx.message)
                return
        try:
            await channel.delete(
                reason=f"{ctx.author} ({ctx.author.id}) has deleted the text channel #{channel.name} ({channel.id})."
            )
        except discord.HTTPException as e:
            raise commands.UserFeedbackCheckFailure(
                _(ERROR_MESSAGE).format(error=box(e, lang="py"))
            )
