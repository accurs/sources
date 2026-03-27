import discord

from heist.framework.tools import Button, View, ConfirmView
from heist.framework.pagination import Paginator
from heist.shared.clients.settings import Settings

from discord import (
    ButtonStyle,
    Colour,
    Embed,
    Guild,
    HTTPException,
    Interaction,
    Member,
    Message,
    Attachment,
    WebhookMessage,
    Thread,
    Webhook,
)

from discord.ext.commands import (
    Context as DefaultContext,
    UserInputError,
)
from discord.types.embed import EmbedType
from discord.ui import button
from discord.utils import cached_property

from datetime import datetime
from typing import Optional, Any, Union, cast
from xxhash import xxh32_hexdigest
from typing import TYPE_CHECKING, Literal, List

if TYPE_CHECKING:
    from discord.ext.commands import Context

from contextlib import suppress

if TYPE_CHECKING:
    from heist.framework import heist
    from heist.shared.config import Configuration, Emojis

MESSAGE_TYPES = Literal[
    "approve",
    "warn",
    "deny",
    "neutral",
    "juul",
    "no_juul",
    "blunt",
]


class Approve(ConfirmView):
    """
    Custom prompt that allows manually specifying a user.
    """

    message: Message = None

    def __init__(
        self,
        *,
        ctx: "Context",
        user: Optional[Member] = None,
        timeout: Optional[int] = 60,
    ):
        super().__init__(
            ctx=ctx, timeout=timeout, member=user
        )
        self.value = None

    async def on_timeout(self) -> None:
        if self.message:
            with suppress(HTTPException):
                await self.message.delete()

    @button(label="Approve", style=ButtonStyle.green)
    async def approve(
        self, interaction: Interaction, _: Button
    ):
        self.value = True
        await interaction.response.defer()

        if self.message:
            with suppress(HTTPException):
                await self.message.delete()

        self.stop()

    @button(label="Decline", style=ButtonStyle.danger)
    async def decline(
        self, interaction: Interaction, _: Button
    ):
        self.value = False
        await interaction.response.defer()

        if self.message:
            with suppress(HTTPException):
                await self.message.delete()

        self.stop()


class Context(DefaultContext):
    bot: "heist"
    config: "Configuration"
    guild: Guild  # type: ignore
    settings: Settings

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure config is properly initialized
        if hasattr(self.bot, 'config') and self.bot.config:
            self.config = self.bot.config
        else:
            # Fallback to default configuration
            from heist.shared.config import Configuration
            self.config = Configuration()

    @cached_property
    def replied_message(self) -> Optional[Message]:
        reference = self.message.reference
        if reference and isinstance(
            reference.resolved, Message
        ):
            return reference.resolved

        return None

    async def get_attachment(self) -> Optional[Attachment]:
        """
        Get a discord attachment from the channel.
        """
        if self.message.attachments:
            return self.message.attachments[0]

        if self.message.reference:
            if self.message.reference.resolved.attachments:
                return self.message.reference.resolved.attachments[
                    0
                ]

        messages = [
            mes
            async for mes in self.channel.history(limit=10)
            if mes.attachments
        ]

        if len(messages) > 0:
            return messages[0].attachments[0]

        return None

    async def embed(
        self,
        message: str,
        message_type: MESSAGE_TYPES,
        edit: Optional[Message] = None,
        color: Optional[Colour] = None,
        tip: Optional[str] = None,
        reference: Optional[Message] = None,
        **kwargs,
    ) -> Message:
        """
        Send an embed with a message type.

        Supported message types: approve, warn, deny, neutral, juul, no_juul
        """
        if message_type == "neutral":
            emoji = ""
        else:
            emoji = getattr(self.bot.config.emojis.context, message_type)

        embed = Embed(
            description=f"{emoji} {self.author.mention}: {message}",
            color=color or getattr(self.config.colors, message_type),
        )
        if tip:
            embed.set_footer(text=f"Tip: {tip}")

        if edit:
            await edit.edit(embed=embed)
            return edit

        return await self.send(
            embed=embed, reference=reference, **kwargs
        )

    async def check(self):
        return await self.message.add_reaction(
            "👍"
        )  # not a check but who cares

    async def prompt(
        self,
        *args: str,
        timeout: int = 60,
    ) -> Literal[True]:
        """
        Prompt the user for confirmation.
        """
        key = xxh32_hexdigest(
            f"prompt:{self.author.id}:{self.command.qualified_name}"
        )

        async with self.bot.redis.get_lock(key):
            embed = Embed(
                description="\n".join(
                    (
                        ""
                        if len(args) == 1
                        or index == len(args) - 1
                        else ""
                    )
                    + str(arg)
                    for index, arg in enumerate(args)
                ),
            )

            view = Confirmation(self, timeout=timeout)

            try:
                view.message = await self.send(
                    embed=embed, view=view
                )
            except HTTPException as exc:
                raise UserInputError(
                    "Failed to send prompt message!"
                ) from exc

            await view.wait()

            if view.value is True:
                return True

            if view.message:
                with suppress(HTTPException):
                    await view.message.delete()

            raise UserInputError(
                "Confirmation prompt wasn't approve!"
            )

    async def confirm(
        self,
        *args: str,
        user: Member,
        timeout: int = 60,
    ) -> bool:
        """
        An interactive reaction confirmation dialog.

        Raises UserInputError if the user denies the prompt.
        """
        key = f"confirm:{self.author.id}:{self.command.qualified_name}"

        async with self.bot.redis.get_lock(key):
            embed = Embed(
                description="\n".join(
                    (
                        ""
                        if len(args) == 1
                        or index == len(args) - 1
                        else ""
                    )
                    + str(arg)
                    for index, arg in enumerate(args)
                ),
            )
            view = Approve(
                ctx=self, user=user, timeout=timeout
            )

            try:
                view.message = await self.send(
                    embed=embed, view=view
                )

            except HTTPException as exc:
                raise UserInputError(
                    "Failed to send prompt message!"
                ) from exc

            await view.wait()

            if view.value is True:
                return True

            if view.message:
                with suppress(HTTPException):
                    await view.message.delete()

            raise UserInputError(
                "Confirmation prompt wasn't approve!"
            )

    async def paginate(
        self,
        entries: List[str],
        *,
        embed: Optional[Embed] = None,
        per_page: int = 10,
        counter: bool = True,
        show_entries: bool = False,
        delete_after: Optional[float] = None,
    ) -> None:
        paginator = Paginator(
            self,
            entries,
            embed=embed,
            per_page=per_page,
            counter=counter,
            show_entries=show_entries,
            delete_after=delete_after,
        )
        await paginator.start()

    async def send_help(
        self, command=None
    ) -> Optional[Message]:
        help_command = self.bot.get_command("help")
        if help_command:
            if isinstance(command, str):
                return await self.invoke(help_command, command=command)
            elif command:
                return await self.invoke(help_command, command=command.qualified_name)
            return await self.invoke(help_command)
        return await super().send_help(command)

    async def approve(self, message: str, *, title: str = None, image: str = None, footer: str = None, **kwargs) -> Message:
        embed_kwargs = {}
        if title or image or footer:
            if message_type := "approve":
                emoji = getattr(self.bot.config.emojis.context, message_type)
            else:
                emoji = ""
            
            embed = Embed(
                title=title,
                description=f"{emoji} {self.author.mention}: {message}" if not title else None,
                color=getattr(self.config.colors, "approve")
            )
            if image:
                embed.set_image(url=image)
            if footer:
                embed.set_footer(text=footer)
            return await self.send(embed=embed, **kwargs)
        return await self.embed(message, "approve", **kwargs)

    async def warn(self, message: str, *, title: str = None, image: str = None, footer: str = None, **kwargs) -> Message:
        embed_kwargs = {}
        if title or image or footer:
            if message_type := "warn":
                emoji = getattr(self.bot.config.emojis.context, message_type)
            else:
                emoji = ""
            
            embed = Embed(
                title=title,
                description=f"{emoji} {self.author.mention}: {message}" if not title else None,
                color=getattr(self.config.colors, "warn")
            )
            if image:
                embed.set_image(url=image)
            if footer:
                embed.set_footer(text=footer)
            return await self.send(embed=embed, **kwargs)
        return await self.embed(message, "warn", **kwargs)

    async def edit_warn(self, message: str, target_message: Optional[Message] = None, *, title: str = None, image: str = None, footer: str = None, **kwargs) -> Message:
        if not target_message:
            return await self.warn(message, title=title, image=image, footer=footer, **kwargs)

        embed_kwargs = {}
        if title or image or footer:
            if message_type := "warn":
                emoji = getattr(self.bot.config.emojis.context, message_type)
            else:
                emoji = ""
            
            embed = Embed(
                title=title,
                description=f"{emoji} {self.author.mention}: {message}" if not title else None,
                color=getattr(self.config.colors, "warn")
            )
            if image:
                embed.set_image(url=image)
            if footer:
                embed.set_footer(text=footer)
        else:
            embed = Embed(
                description=f"{getattr(self.bot.config.emojis.context, 'warn')} {self.author.mention}: {message}",
                color=getattr(self.config.colors, "warn")
            )

        await target_message.edit(embed=embed, **kwargs)
        return target_message

    async def deny(self, message: str, *, title: str = None, image: str = None, footer: str = None, **kwargs) -> Message:
        embed_kwargs = {}
        if title or image or footer:
            if message_type := "deny":
                emoji = getattr(self.bot.config.emojis.context, message_type)
            else:
                emoji = ""
            
            embed = Embed(
                title=title,
                description=f"{emoji} {self.author.mention}: {message}" if not title else None,
                color=getattr(self.config.colors, "deny")
            )
            if image:
                embed.set_image(url=image)
            if footer:
                embed.set_footer(text=footer)
            return await self.send(embed=embed, **kwargs)
        return await self.embed(message, "deny", **kwargs)

    async def neutral(self, message: str, *, title: str = None, image: str = None, footer: str = None, **kwargs) -> Message:
        embed_kwargs = {}
        if title or image or footer:
            embed = Embed(
                title=title,
                description=f"{self.author.mention}: {message}" if not title else None,
                #color=getattr(self.config.colors, "neutral")
                color=await self.bot.get_color(self.author.id)
            )
            if image:
                embed.set_image(url=image)
            if footer:
                embed.set_footer(text=footer)
            return await self.send(embed=embed, **kwargs)
        return await self.embed(message, "neutral", **kwargs)


class Confirmation(View):
    value: Optional[bool]
    message: Message = None

    def __init__(
        self, ctx: Context, *, timeout: Optional[int] = 60
    ):
        super().__init__(ctx, timeout=timeout)
        self.ctx = ctx
        self.value = None

    async def on_timeout(self) -> None:
        if self.message:
            with suppress(HTTPException):
                await self.message.delete()

    @button(label="Approve", style=ButtonStyle.green)
    async def approve(
        self, interaction: Interaction, button: Button
    ):
        self.value = True
        await interaction.response.defer()
        if self.message:
            with suppress(HTTPException):
                await self.message.delete()
        self.stop()

    @button(label="Decline", style=ButtonStyle.danger)
    async def decline(
        self, interaction: Interaction, _: Button
    ):
        self.value = False
        await interaction.response.defer()

        if self.message:
            with suppress(HTTPException):
                await self.message.delete()

        self.stop()


class Embed(discord.Embed):
    def __init__(
        self,
        value: Optional[str] = None,
        *,
        colour: int | Colour | None = None,
        color: int | Colour | None = None,
        title: Any | None = None,
        type: EmbedType = "rich",
        url: Any | None = None,
        description: Any | None = None,
        timestamp: datetime | None = None,
    ):
        description = description or value
        super().__init__(
            colour=colour,
            color=color or 0xd3d6f1,
            title=title,
            type=type,
            url=url,
            description=description[:4096]
            if description
            else None,
            timestamp=timestamp,
        )

    def add_field(
        self, *, name: Any, value: Any, inline: bool = True
    ) -> "discord.Embed":
        if not name or (
            isinstance(name, str)
            and ("```" in name or "`" in name)
        ):
            return super().add_field(
                name=name, value=value, inline=inline
            )
        return super().add_field(
            name=f"**{name}**", value=value, inline=inline
        )


discord.Embed = Embed
