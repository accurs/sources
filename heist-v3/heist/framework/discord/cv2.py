import discord
from discord import ui
from typing import Union, List, Optional

ColorLike = Union[int, discord.Color, None]
Ctx = Union[discord.Interaction, "discord.ext.commands.Context"]

async def _resolve_color(ctx: Ctx, color: ColorLike):
    if isinstance(color, discord.Color):
        return color
    if isinstance(color, int):
        return discord.Color(color)
    bot = getattr(ctx, "bot", None)
    user = getattr(ctx, "author", None) or getattr(ctx, "user", None)
    if bot and hasattr(bot, "get_color") and user:
        try:
            c = await bot.get_color(user.id)
            return discord.Color(c) if isinstance(c, int) else c
        except:
            pass
    return discord.Color.blurple()

def make_accessory(url: str):
    return ui.Thumbnail(url)

class CV2:
    @staticmethod
    def link_button(label, url, emoji=None):
        if isinstance(emoji, str):
            try:
                emoji = discord.PartialEmoji.from_str(emoji)
            except:
                emoji = None
        return ui.Button(label=label, url=url, emoji=emoji, style=discord.ButtonStyle.link)

    async def _build(
        self,
        ctx,
        title=None,
        content=None,
        media_url=None,
        footer=None,
        sections=None,
        components=None,
        color=None,
        accessory_thumbnail=None,
        advanced_sections=None,
        buttons=None,
        buttons_inside=False
    ):
        col = await _resolve_color(ctx, color)
        attrs = {}
        i = 0

        if components:
            for comp in components:
                attrs[f"attr_{i}"] = comp
                i += 1
        else:
            if title:
                attrs[f"attr_{i}"] = ui.TextDisplay(title)
                i += 1

            if content:
                if title:
                    attrs[f"attr_{i}"] = ui.Separator()
                    i += 1

                if accessory_thumbnail:
                    section = ui.Section(
                        ui.TextDisplay(content),
                        accessory=make_accessory(accessory_thumbnail)
                    )
                    attrs[f"attr_{i}"] = section
                    i += 1
                else:
                    attrs[f"attr_{i}"] = ui.TextDisplay(content)
                    i += 1

            if media_url:
                if title or content:
                    attrs[f"attr_{i}"] = ui.Separator()
                    i += 1
                item = discord.MediaGalleryItem(media_url)
                attrs[f"attr_{i}"] = ui.MediaGallery(item)
                i += 1

            if footer:
                if title or content or media_url:
                    attrs[f"attr_{i}"] = ui.Separator()
                    i += 1
                attrs[f"attr_{i}"] = ui.TextDisplay(footer)
                i += 1

            if sections:
                for s in sections:
                    attrs[f"attr_{i}"] = s
                    i += 1

        if advanced_sections:
            for block in advanced_sections:
                if attrs:
                    attrs[f"attr_{i}"] = ui.Separator()
                    i += 1
                for elem in block:
                    attrs[f"attr_{i}"] = elem
                    i += 1

        if buttons_inside and buttons:
            row = ui.ActionRow()
            for b in buttons:
                row.add_item(b)
            attrs[f"attr_{i}"] = row
            i += 1

        Container = type("DynamicContainer", (ui.Container,), attrs)
        return Container(accent_color=col)

    async def send(
        self,
        ctx,
        *,
        title=None,
        content=None,
        media_url=None,
        footer=None,
        sections=None,
        components=None,
        files=None,
        color=None,
        accessory_thumbnail=None,
        advanced_sections=None,
        buttons=None,
        buttons_inside=False,
        ephemeral=None
    ):
        container = await self._build(
            ctx,
            title,
            content,
            media_url,
            footer,
            sections,
            components,
            color,
            accessory_thumbnail,
            advanced_sections,
            buttons,
            buttons_inside
        )

        if buttons_inside:
            class V(ui.LayoutView):
                main = container
            view = V()
        else:
            if buttons:
                class V(ui.LayoutView):
                    main = container
                    bar = ui.ActionRow()
                view = V()
                for b in buttons:
                    view.bar.add_item(b)
            else:
                class V(ui.LayoutView):
                    main = container
                view = V()

        kw = {"view": view}
        if files:
            kw["files"] = files

        if isinstance(ctx, discord.Interaction):
            if ephemeral is not None:
                kw["ephemeral"] = ephemeral
            return await ctx.response.send_message(**kw)

        return await ctx.send(**kw)

    async def edit(
        self,
        message,
        ctx: Ctx,
        *,
        title=None,
        content=None,
        media_url=None,
        footer=None,
        sections=None,
        components=None,
        buttons=None,
        buttons_inside=False,
        files=None,
        color=None,
        accessory_thumbnail=None,
        advanced_sections=None
    ):
        container = await self._build(
            ctx,
            title,
            content,
            media_url,
            footer,
            sections,
            components,
            color,
            accessory_thumbnail,
            advanced_sections,
            buttons,
            buttons_inside
        )

        if buttons_inside:
            class V(ui.LayoutView):
                main = container
            view = V()
        else:
            if buttons:
                class V(ui.LayoutView):
                    main = container
                    bar = ui.ActionRow()
                view = V()
                for b in buttons:
                    view.bar.add_item(b)
            else:
                class V(ui.LayoutView):
                    main = container
                view = V()

        kw = {"view": view}
        if files:
            kw["attachments"] = files
        return await message.edit(**kw)

    async def warn(
        self,
        ctx: Ctx,
        message: str,
        *,
        title: str = None,
        media_url: str = None,
        footer: str = None,
        buttons=None,
        buttons_inside=False,
        ephemeral: bool = False
    ):
        emoji = getattr(ctx.bot.config.emojis.context, "warn", "")
        color = ctx.config.colors.warn
        content = f"{emoji} {ctx.author.mention}: {message}"

        return await self.send(
            ctx,
            title=title,
            content=content,
            media_url=media_url,
            footer=footer,
            buttons=buttons,
            buttons_inside=buttons_inside,
            color=color,
            ephemeral=ephemeral
        )

    async def edit_warn(self, message_obj, ctx, message, *, title=None, footer=None, media_url=None, buttons=None, buttons_inside=False):
        emoji = getattr(ctx.bot.config.emojis.context, "warn", "")
        content = f"{emoji} {ctx.author.mention}: {message}"
        return await self.edit(
            message_obj,
            ctx,
            title=title,
            content=content,
            media_url=media_url,
            footer=footer,
            color=ctx.config.colors.warn,
            buttons=buttons,
            buttons_inside=buttons_inside
        )

cv2 = CV2()
import builtins
builtins.cpv2 = cv2
