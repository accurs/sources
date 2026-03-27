from discord import Role
from discord.ext.commands import (
    CommandError,
    RoleConverter,
    RoleNotFound,
)
from discord.utils import find

from .basic import DANGEROUS_PERMISSIONS
from heist.framework import Context
from heist.framework.tools.converters.regex import (
    DISCORD_ID,
    DISCORD_ROLE_MENTION,
)


class Role(RoleConverter):
    @staticmethod
    async def convert(ctx: Context, argument: str):
        """
        A converter that converts a string to a role.
        """
        role = None
        if match := DISCORD_ID.match(argument):
            role = ctx.guild.get_role(int(match.group(1)))
        elif match := DISCORD_ROLE_MENTION.match(argument):
            role = ctx.guild.get_role(int(match.group(1)))
        else:
            role = (
                find(
                    lambda r: r.name.lower()
                    == argument.lower(),
                    ctx.guild.roles,
                )
                or find(
                    lambda r: argument.lower()
                    in r.name.lower(),
                    ctx.guild.roles,
                )
                or find(
                    lambda r: r.name.lower().startswith(
                        argument.lower()
                    ),
                    ctx.guild.roles,
                )
            )
        if not role or role.is_default():
            raise RoleNotFound(argument)
        return role

    @staticmethod
    async def manageable(
        ctx: Context, role: Role, booster: bool = False
    ):
        """
        A method that checks if a role is manageable.
        """
        if role.managed and not booster:
            raise CommandError(
                f"You're unable to manage {role.mention}"
            )
        if not role.is_assignable() and not booster:
            raise CommandError(
                f"I'm unable to manage {role.mention}"
            )
        if (
            role >= ctx.author.top_role
            and ctx.author.id != ctx.guild.owner.id
        ):
            raise CommandError(
                f"You're unable to manage {role.mention}"
            )

        return True

    @staticmethod
    async def dangerous(
        ctx: Context, role: Role, _: str = "manage"
    ):
        """
        A method that checks if a role is dangerous.
        """
        if (
            permissions := list(
                filter(
                    lambda permission: getattr(
                        role.permissions, permission
                    ),
                    DANGEROUS_PERMISSIONS,
                )
            )
        ) and ctx.author.id != ctx.guild.owner_id:
            raise CommandError(
                f"You're unable to {_} {role.mention} because it has the `{permissions[0]}` permission"
            )

        return False
