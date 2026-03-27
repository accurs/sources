import discord
from discord import Embed, Colour
from typing import Optional

async def _send_embed_interaction(
    self: discord.Interaction,
    message: str,
    type_: str,
    *,
    title: Optional[str] = None,
    image: Optional[str] = None,
    footer: Optional[str] = None,
    **kwargs
):
    emoji = getattr(self.client.config.emojis.context, type_, "")
    color = getattr(self.client.config.colors, type_, Colour.blurple())
    embed = Embed(
        title=title,
        description=f"{emoji} {self.user.mention}: {message}" if not title else None,
        color=color
    )
    if image:
        embed.set_image(url=image)
    if footer:
        embed.set_footer(text=footer)

    if self.response.is_done():
        return await self.followup.send(embed=embed, **kwargs)
    return await self.response.send_message(embed=embed, **kwargs)

async def _send_embed_response(
    self: discord.InteractionResponse,
    interaction: discord.Interaction,
    message: str,
    type_: str,
    *,
    title: Optional[str] = None,
    image: Optional[str] = None,
    footer: Optional[str] = None,
    **kwargs
):
    client = interaction.client
    emoji = getattr(client.config.emojis.context, type_, "")
    color = getattr(client.config.colors, type_, Colour.blurple())
    embed = Embed(
        title=title,
        description=f"{emoji} {interaction.user.mention}: {message}" if not title else None,
        color=color
    )
    if image:
        embed.set_image(url=image)
    if footer:
        embed.set_footer(text=footer)

    if self.is_done():
        return await interaction.followup.send(embed=embed, **kwargs)
    return await self.send_message(embed=embed, **kwargs)

async def followup_embed(
    interaction: discord.Interaction,
    message: str,
    type_: str,
    *,
    title: Optional[str] = None,
    image: Optional[str] = None,
    footer: Optional[str] = None,
    **kwargs
):
    emoji = getattr(interaction.client.config.emojis.context, type_, "")
    color = getattr(interaction.client.config.colors, type_, Colour.blurple())
    embed = Embed(
        title=title,
        description=f"{emoji} {interaction.user.mention}: {message}" if not title else None,
        color=color
    )
    if image:
        embed.set_image(url=image)
    if footer:
        embed.set_footer(text=footer)

    return await interaction.followup.send(embed=embed, **kwargs)

discord.Interaction.approve = lambda self, message, **kwargs: _send_embed_interaction(self, message, "approve", **kwargs)
discord.Interaction.warn = lambda self, message, **kwargs: _send_embed_interaction(self, message, "warn", **kwargs)
discord.Interaction.deny = lambda self, message, **kwargs: _send_embed_interaction(self, message, "deny", **kwargs)
discord.Interaction.neutral = lambda self, message, **kwargs: _send_embed_interaction(self, message, "neutral", **kwargs)

discord.InteractionResponse.approve = lambda self, message, **kwargs: _send_embed_response(self, self._parent, message, "approve", **kwargs)
discord.InteractionResponse.warn = lambda self, message, **kwargs: _send_embed_response(self, self._parent, message, "warn", **kwargs)
discord.InteractionResponse.deny = lambda self, message, **kwargs: _send_embed_response(self, self._parent, message, "deny", **kwargs)
discord.InteractionResponse.neutral = lambda self, message, **kwargs: _send_embed_response(self, self._parent, message, "neutral", **kwargs)

def followup_approve(interaction: discord.Interaction, message: str, **kwargs):
    return followup_embed(interaction, message, "approve", **kwargs)

def followup_warn(interaction: discord.Interaction, message: str, **kwargs):
    return followup_embed(interaction, message, "warn", **kwargs)

def followup_deny(interaction: discord.Interaction, message: str, **kwargs):
    return followup_embed(interaction, message, "deny", **kwargs)

def followup_neutral(interaction: discord.Interaction, message: str, **kwargs):
    return followup_embed(interaction, message, "neutral", **kwargs)