from __future__ import annotations

import os
import random
import string
from typing import Any

import discord
from discord.ext import commands


def _env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def _color(name: str) -> discord.Color:
    raw = _env(name).lower()
    raw = raw[1:] if raw.startswith("#") else raw
    try:
        return discord.Color(int(raw, 16))
    except ValueError:
        raise RuntimeError(f"Invalid color value for {name}: {raw}")


def _emoji(name: str) -> str:
    return _env(name)


def _strip_success_prefix(message: str) -> str:
    text = (message or "").strip()
    if text.lower().startswith("successfully "):
        return text[13:].strip()
    return text


def _strip_leading_mention(message: str, mention: str) -> str:
    text = (message or "").strip()
    if mention and text.startswith(mention):
        return text[len(mention):].lstrip(": ").strip()
    return text


def _buttons_to_view(buttons: list[dict[str, Any]] | None) -> discord.ui.View | None:
    if not buttons:
        return None

    view = discord.ui.View(timeout=None)
    for item in buttons:
        label = item.get("label", "")
        style = item.get("style", discord.ButtonStyle.secondary)
        disabled = bool(item.get("disabled", False))
        url = item.get("url")
        custom_id = item.get("custom_id")
        if url:
            button = discord.ui.Button(label=label, url=url, disabled=disabled)
        else:
            button = discord.ui.Button(
                label=label,
                style=style,
                custom_id=custom_id or _random_token(),
                disabled=disabled,
            )
        view.add_item(button)
    return view


def _random_token(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


class PagerModal(discord.ui.Modal):
    def __init__(self, view: "PagedView") -> None:
        super().__init__(title="Skip to page", timeout=60)
        self.view = view
        self.page = discord.ui.TextInput(
            label="Page number",
            placeholder=f"1-{len(view.pages)}",
            max_length=4,
        )
        self.add_item(self.page)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = str(self.page.value).strip()
        if not raw.isdigit():
            await interaction.response.send_message("Provide a valid page number.", ephemeral=True)
            return
        page = int(raw)
        if page < 1 or page > len(self.view.pages):
            await interaction.response.send_message("That page is out of range.", ephemeral=True)
            return
        self.view.index = page - 1
        await interaction.response.edit_message(embed=self.view.pages[self.view.index], view=self.view)


class PagedView(discord.ui.View):
    def __init__(self, author_id: int, pages: list[discord.Embed]) -> None:
        super().__init__(timeout=180)
        self.author_id = author_id
        self.pages = pages
        self.index = 0
        self.message: discord.Message | None = None
        disabled = len(pages) <= 1
        self.previous.label = None
        self.previous.emoji = _emoji("EMOJI_LEFT")
        self.previous.disabled = disabled
        self.next.label = None
        self.next.emoji = _emoji("EMOJI_RIGHT")
        self.next.disabled = disabled
        self.skip.label = None
        self.skip.emoji = _emoji("EMOJI_SKIP")
        self.skip.disabled = disabled
        self.close.label = None
        self.close.emoji = _emoji("EMOJI_CANCEL")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user and interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("This paginator is not for you.", ephemeral=True)
        return False

    async def on_timeout(self) -> None:
        if not self.message:
            return
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            return

    @discord.ui.button(label="previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.index = (self.index - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.index = (self.index + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(PagerModal(self))

    @discord.ui.button(label="close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()
        if interaction.message:
            try:
                await interaction.message.delete()
            except discord.HTTPException:
                return
        self.stop()


class TormentContext(commands.Context["TormentBot"]):
    async def send(self, *args: Any, **kwargs: Any) -> discord.Message:
        return await super().send(*args, **kwargs)

    def _build_status_embed(self, message: str, *, color: discord.Color) -> discord.Embed:
        return discord.Embed(description=message, color=color)

    async def _send_status(
        self,
        message: str,
        *,
        color: discord.Color,
        buttons: list[dict[str, Any]] | None = None,
    ) -> discord.Message:
        embed = self._build_status_embed(message, color=color)
        view = _buttons_to_view(buttons)
        return await self.send(embed=embed, view=view)

    async def paginate(
        self,
        pages: list[discord.Embed],
        *,
        start_index: int = 0,
    ) -> discord.Message:
        if not pages:
            return await self.send(embed=discord.Embed(description="n/a", color=_color("EMBED_INFO_COLOR")))
        if len(pages) == 1:
            return await self.send(embed=pages[0])
        view = PagedView(self.author.id, pages)
        view.index = min(max(start_index, 0), len(pages) - 1)
        message = await self.send(embed=pages[view.index], view=view)
        view.message = message
        return message

    async def send_help_embed(self, command: commands.Command[Any, ..., Any]) -> None:
        from bot.helpers.help import build_command_pages

        pages = build_command_pages(command, self.clean_prefix, self.author)
        invoked_subcommand = getattr(self, "invoked_subcommand", None)
        is_direct_command_invoke = self.command is command and invoked_subcommand is None
        if invoked_subcommand is command:
            is_direct_command_invoke = True
        if is_direct_command_invoke and pages:
            first_page = pages[0]
            usage_value = ""
            for field in first_page.fields:
                if field.name.replace("*", "").strip().lower() == "usage":
                    usage_value = field.value
                    break
            description = (first_page.description or "").strip()
            if usage_value:
                description = f"{description}\n{usage_value}" if description else usage_value
            embed = discord.Embed(
                title=f"Command: {command.qualified_name}",
                description=description or "n/a",
                color=first_page.color,
            )
            bot_user = getattr(self.bot, "user", None)
            if bot_user:
                embed.set_author(
                    name=f"{bot_user.name} help",
                    icon_url=getattr(bot_user.display_avatar, "url", None),
                )
            await self.send(embed=embed)
            return

        entries = len(pages)
        for index, page in enumerate(pages, start=1):
            module_text = page.footer.text or "module: misc"
            page.set_footer(text=f"Page {index}/{entries} ({entries} entries) | Module: {module_text}")
        await self.paginate(pages)

    async def confirm(
        self,
        message: str,
        *,
        timeout: int = 30,
        user: discord.abc.User | None = None,
    ) -> bool:
        target_user = user or self.author
        prompt = f"{_emoji('EMOJI_WARN')} {target_user.mention}: {message}"
        result: dict[str, bool | None] = {"value": None}

        class ConfirmView(discord.ui.View):
            def __init__(self) -> None:
                super().__init__(timeout=timeout)
                self.message: discord.Message | None = None

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                if interaction.user and interaction.user.id == target_user.id:
                    return True
                await interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
                return False

            async def on_timeout(self) -> None:
                if not self.message:
                    return
                try:
                    await self.message.edit(view=None)
                except discord.HTTPException:
                    return

            @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
            async def approve(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
                result["value"] = True
                await interaction.response.defer()
                if self.message:
                    try:
                        await self.message.delete()
                    except discord.HTTPException:
                        pass
                self.stop()

            @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger)
            async def deny(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
                result["value"] = False
                await interaction.response.defer()
                if self.message:
                    try:
                        await self.message.edit(view=None)
                    except discord.HTTPException:
                        pass
                self.stop()

        view = ConfirmView()
        view.message = await self.send(embed=self._build_status_embed(prompt, color=_color("EMBED_WARN_COLOR")), view=view)
        await view.wait()
        return bool(result["value"])

    async def info(self, message: str) -> discord.Message:
        text = f"{_emoji('EMOJI_INFO')} {self.author.mention}: {_strip_leading_mention(message, self.author.mention)}"
        return await self._send_status(text, color=_color("EMBED_INFO_COLOR"))

    async def success(
        self,
        message: str,
        *,
        buttons: list[dict[str, Any]] | None = None,
    ) -> discord.Message:
        text = f"{_emoji('EMOJI_SUCCESS')} {self.author.mention}: {_strip_leading_mention(message, self.author.mention)}"
        return await self._send_status(text, color=_color("EMBED_SUCCESS_COLOR"), buttons=buttons)

    async def warn(self, message: str) -> discord.Message:
        text = f"{_emoji('EMOJI_WARN')} {self.author.mention}: {_strip_leading_mention(message, self.author.mention)}"
        return await self._send_status(text, color=_color("EMBED_WARN_COLOR"))

    async def deny(self, message: str) -> discord.Message:
        text = f"{_emoji('EMOJI_DENY')} {self.author.mention}: {_strip_leading_mention(message, self.author.mention)}"
        return await self._send_status(text, color=_color("EMBED_DENY_COLOR"))
