import re

from discord import Interaction, ButtonStyle, Emoji
from discord.ui import Button, DynamicItem


class DynamicRoleButton(
    DynamicItem[Button],
    template=r"RB:(?P<message_id>[0-9]+):(?P<role_id>[0-9]+)",
):
    def __init__(
        self, message_id: int, role_id: int, emoji: Emoji
    ) -> None:
        super().__init__(
            Button(
                style=ButtonStyle.secondary,
                label=None,
                emoji=emoji,
                custom_id=f"RB:{message_id}:{role_id}",
            )
        )
        self.message_id: int = message_id
        self.role_id: int = role_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: Interaction,
        item: Button,
        match: re.Match[str],
        /,
    ):
        message_id = int(match["message_id"])
        role_id = int(match["role_id"])
        return cls(message_id, role_id, item.emoji)

    async def callback(
        self, interaction: Interaction
    ) -> None:
        role = interaction.guild.get_role(self.role_id)

        if role is None:
            return await interaction.embed(
                "This role button no longer exists!"
            )

        member = interaction.guild.get_member(
            interaction.user.id
        )

        if member is None:
            return await interaction.embed("???")

        if role in member.roles:
            await member.remove_roles(role)
            return await interaction.embed(
                f"Removed role {role.mention} from you"
            )

        await member.add_roles(role)
        return await interaction.embed(
            f"Added role {role.mention} to you"
        )
