from .context import Context

from typing import Any
from contextlib import suppress
from typing import Sequence
from humanfriendly import format_timespan

from discord import (
    Forbidden,
    Guild,
    HTTPException,
    Invite,
    Member,
    NotFound,
    User,
)
from discord.ext.commands import (
    BadInviteArgument,
    BadLiteralArgument,
    BadUnionArgument,
    ChannelNotFound,
    CheckFailure,
    CommandError,
    CommandInvokeError,
    CommandNotFound,
    CommandOnCooldown,
    DisabledCommand,
    FlagError,
    MaxConcurrencyReached,
    MemberNotFound,
    MessageNotFound,
    MissingFlagArgument,
    MissingPermissions,
    MissingRequiredArgument,
    MissingRequiredAttachment,
    MissingRequiredFlag,
    NSFWChannelRequired,
    NotOwner,
    RangeError,
    RoleNotFound,
    TooManyFlags,
    UserNotFound,
)


class plural:
    value: str | int | list
    markdown: str

    def __init__(
        self, value: str | int | list, md: str = ""
    ):
        self.value = value
        self.markdown = md

    def __format__(self, format_spec: str) -> str:
        v = self.value
        if isinstance(v, str):
            v = (
                int(v.split(" ", 1)[-1])
                if v.startswith(("CREATE", "DELETE"))
                else int(v)
            )

        elif isinstance(v, list):
            v = len(v)

        singular, sep, plural = format_spec.partition("|")
        plural = plural or f"{singular}s"
        return (
            f"{self.markdown}{v:,}{self.markdown} {plural}"
            if abs(v) != 1
            else f"{self.markdown}{v:,}{self.markdown} {singular}"
        )


def human_join(
    seq: Sequence[str], delim: str = ", ", final: str = "or"
) -> str:
    size = len(seq)
    if size == 0:
        return ""

    if size == 1:
        return seq[0]

    if size == 2:
        return f"{seq[0]} {final} {seq[1]}"

    return delim.join(seq[:-1]) + f" {final} {seq[-1]}"


class CommandErrorHandler:
    """
    Custom command error handler for heist.
    """

    async def on_command_error(
        self, ctx: Context, exc: CommandError
    ) -> Any:
        """
        Custom on_command_error method that handles command errors.
        """
        if not ctx.channel:
            return

        if not ctx.guild:
            can_send = True
        else:
            guild_me = ctx.guild.get_member(ctx.bot.user.id)
            can_send = (
                ctx.channel.permissions_for(
                    guild_me
                ).send_messages
                and ctx.channel.permissions_for(
                    guild_me
                ).embed_links
            )

        if not can_send:
            return

        if isinstance(
            exc,
            (
                CommandNotFound,
                DisabledCommand,
                NotOwner,
            ),
        ):
            return

        elif isinstance(
            exc,
            (
                MissingRequiredArgument,
                MissingRequiredAttachment,
                BadLiteralArgument,
            ),
        ):
            return await ctx.send_help( f"{ctx.command.qualified_name}")

        elif isinstance(exc, FlagError):
            if isinstance(exc, TooManyFlags):
                return await ctx.embed(
                    f"You specified the **{exc.flag.name}** flag more than once!",
                    "warn",
                )

            elif isinstance(exc, MissingRequiredFlag):
                return await ctx.embed(
                    f"You must specify the **{exc.flag.name}** flag!",
                    "warn",
                )

            elif isinstance(exc, MissingFlagArgument):
                return await ctx.embed(
                    f"You must specify a value for the **{exc.flag.name}** flag!",
                    "warn",
                )

        if isinstance(exc, CommandInvokeError):
            return await ctx.embed(exc.original, "warn")

        elif isinstance(exc, MaxConcurrencyReached):
            if ctx.command.qualified_name in (
                "lastfm set",
                "lastfm index",
            ):
                return

            return await ctx.embed(
                f"This command can only be used **{plural(exc.number):time}** per **{exc.per.name}** concurrently!",
                "warn",
            )

        elif isinstance(exc, CommandOnCooldown):
            if exc.retry_after > 30:
                return await ctx.embed(
                    f"This command is currently on cooldown!\nTry again in **{format_timespan(exc.retry_after)}**",
                    "warn",
                )

            return await ctx.message.add_reaction("⏰")

        elif isinstance(exc, BadUnionArgument):
            if exc.converters == (Member, User):
                return await ctx.embed(
                    f"No **{exc.param.name}** was found matching **{ctx.current_argument}**!\nIf the user is not in this server, try using their **ID** instead",
                    "warn",
                )

            elif exc.converters == (Guild, Invite):
                return await ctx.embed(
                    f"No server was found matching **{ctx.current_argument}**!",
                    "warn",
                )

            else:
                return await ctx.embed(
                    f"Casting **{exc.param.name}** to {human_join([f'`{c.__name__}`' for c in exc.converters])} failed!",
                    "warn",
                )

        elif isinstance(exc, MemberNotFound):
            return await ctx.embed(
                f"No **member** was found matching **{exc.argument}**!",
                "warn",
            )

        elif isinstance(exc, UserNotFound):
            return await ctx.embed(
                f"No **user** was found matching `{exc.argument}`!",
                "warn",
            )

        elif isinstance(exc, RoleNotFound):
            return await ctx.embed(
                f"No **role** was found matching **{exc.argument}**!",
                "warn",
            )

        elif isinstance(exc, ChannelNotFound):
            return await ctx.embed(
                f"No **channel** was found matching **{exc.argument}**!",
                "warn",
            )

        elif isinstance(exc, BadInviteArgument):
            return await ctx.embed(
                "Invalid **invite code** provided!",
                "warn",
            )

        elif isinstance(exc, MessageNotFound):
            return await ctx.embed(
                "The provided **message** was not found!\n Try using the **message URL** instead",
                "warn",
            )

        elif isinstance(exc, RangeError):
            label = ""
            if (
                exc.minimum is None
                and exc.maximum is not None
            ):
                label = f"no more than `{exc.maximum}`"
            elif (
                exc.minimum is not None
                and exc.maximum is None
            ):
                label = f"no less than `{exc.minimum}`"
            elif (
                exc.maximum is not None
                and exc.minimum is not None
            ):
                label = f"between `{exc.minimum}` and `{exc.maximum}`"

            if label and isinstance(exc.value, str):
                label += " characters"

            return await ctx.embed(
                f"The input must be {label}!", "warn"
            )

        elif isinstance(exc, MissingPermissions):
            permissions = human_join(
                [
                    f"`{permission}`"
                    for permission in exc.missing_permissions
                ],
                final="and",
            )
            _plural = (
                "s"
                if len(exc.missing_permissions) > 1
                else ""
            )

            return await ctx.embed(
                f"You're missing the {permissions} permission{_plural}!",
                "warn",
            )


        elif isinstance(exc, NSFWChannelRequired):
            return await ctx.embed(
                "This command can only be used in NSFW channels!",
                "warn",
            )

        elif isinstance(exc, CommandError):
            if isinstance(
                exc, (HTTPException, NotFound)
            ) and not isinstance(
                exc, (CheckFailure, Forbidden)
            ):
                if "Unknown Channel" in exc.text:
                    return
                return await ctx.embed(
                    exc.text.capitalize(), "warn"
                )

            if isinstance(
                exc, (Forbidden, CommandInvokeError)
            ):
                error = (
                    exc.original
                    if isinstance(exc, CommandInvokeError)
                    else exc
                )

                if isinstance(error, Forbidden):
                    perms = ctx.guild.me.guild_permissions
                    missing_perms = []

                    if not perms.manage_channels:
                        missing_perms.append(
                            "`manage_channels`"
                        )
                    if not perms.manage_roles:
                        missing_perms.append(
                            "`manage_roles`"
                        )

                    error_msg = (
                        f"I'm missing the following permissions: {', '.join(missing_perms)}\n"
                        if missing_perms
                        else "I'm missing required permissions. Please check my role's permissions and position.\n"
                    )

                    return await ctx.embed(
                        error_msg,
                        f"Error: {str(error)}",
                        "warn",
                    )

                return await ctx.embed(str(error), "warn")

            origin = getattr(exc, "original", exc)
            with suppress(TypeError):
                if any(
                    forbidden in origin.args[-1]
                    for forbidden in (
                        "global check",
                        "check functions",
                        "Unknown Channel",
                    )
                ):
                    return

            return await ctx.embed(*origin.args, "warn")

        else:
            return await ctx.send_help(ctx.command)
