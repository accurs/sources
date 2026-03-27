import discord
from discord.ext import commands
from typing import List


class GoToModal(discord.ui.Modal, title="Go to page"):
    page = discord.ui.TextInput(
        label="Page Number",
        placeholder="Enter a page number...",
        max_length=3
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if int(self.page.value) > len(self.embeds):
            return await interaction.client.ext.send_warning(
                interaction,
                f"You can only select a page **between** 1 and {len(self.embeds)}",
                ephemeral=True
            )
        await interaction.response.edit_message(embed=self.embeds[int(self.page.value) - 1])

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.client.ext.send_warning(interaction, "Unable to change the page", ephemeral=True)


class PaginatorView(discord.ui.View):
    def __init__(self, ctx: commands.Context, embeds: list):
        super().__init__()
        self.embeds = embeds
        self.ctx = ctx
        self.i = 0

    @discord.ui.button(emoji="<:left:1018156480991612999>", style=discord.ButtonStyle.blurple)
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.client.ext.send_warning(interaction, "You are not the author of this embed")
        if self.i == 0:
            self.i = len(self.embeds) - 1
            return await interaction.response.edit_message(embed=self.embeds[-1])
        self.i -= 1
        return await interaction.response.edit_message(embed=self.embeds[self.i])

    @discord.ui.button(emoji="<:right:1018156484170883154>", style=discord.ButtonStyle.blurple)
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.client.ext.send_warning(interaction, "You are not the author of this embed")
        if self.i == len(self.embeds) - 1:
            self.i = 0
            return await interaction.response.edit_message(embed=self.embeds[0])
        self.i += 1
        return await interaction.response.edit_message(embed=self.embeds[self.i])

    @discord.ui.button(emoji="<:filter:1039235211789078628>")
    async def goto(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.client.ext.send_warning(interaction, "You are not the author of this embed")
        modal = GoToModal()
        modal.embeds = self.embeds
        await interaction.response.send_modal(modal)
        await modal.wait()
        try:
            self.i = int(modal.page.value) - 1
        except:
            pass

    @discord.ui.button(emoji="<:stop:1018156487232720907>", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.client.ext.send_warning(interaction, "You are not the author of this embed")
        await interaction.message.delete()

    async def on_timeout(self) -> None:
        mes = await self.message.channel.fetch_message(self.message.id)
        if mes is None:
            return
        if len(mes.components) == 0:
            return
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass