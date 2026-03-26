import discord
from discord.ui import View, Button, Modal, TextInput
from typing import List

class SkipToModal(Modal):
    def __init__(self, paginator_view):
        super().__init__(title="Skip to Page")
        self.paginator_view = paginator_view
        
        self.page_input = TextInput(
            label="Page Number",
            placeholder=f"Enter a page number (1-{len(paginator_view.embeds)})",
            required=True,
            max_length=4
        )
        self.add_item(self.page_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            page_num = int(self.page_input.value) - 1
            if 0 <= page_num < len(self.paginator_view.embeds):
                self.paginator_view.current_page = page_num
                await interaction.response.edit_message(
                    embed=self.paginator_view.embeds[page_num],
                    view=self.paginator_view
                )
            else:
                await interaction.response.send_message(
                    f"Invalid page number. Please enter a number between 1 and {len(self.paginator_view.embeds)}",
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message(
                "Please enter a valid number.",
                ephemeral=True
            )

class PaginatorView(View):
    def __init__(self, embeds: List[discord.Embed], user: discord.User = None, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.current_page = 0
        self.buttons_visible = True
        self.user = user  # Store the user who initiated the paginator
        
        # Update all embeds with page numbers in footer
        self._update_footers()
        
        # Add buttons with custom emojis from your server
        self.back_button = Button(
            emoji="<:left:1472264409756733480>",
            style=discord.ButtonStyle.secondary
        )
        self.back_button.callback = self.back_callback
        
        self.forward_button = Button(
            emoji="<:right:1472264412789346365>",
            style=discord.ButtonStyle.secondary
        )
        self.forward_button.callback = self.forward_callback
        
        self.skipto_button = Button(
            emoji="<:skipto:1472264407085088920>",
            style=discord.ButtonStyle.secondary
        )
        self.skipto_button.callback = self.skipto_callback
        
        self.close_button = Button(
            emoji="<:cancel:1472264411422003321>",
            style=discord.ButtonStyle.secondary
        )
        self.close_button.callback = self.close_callback
        
        self.add_item(self.back_button)
        self.add_item(self.forward_button)
        self.add_item(self.skipto_button)
        self.add_item(self.close_button)
    
    def _update_footers(self):
        """Update all embed footers with page numbers"""
        for i, embed in enumerate(self.embeds, 1):
            # Get existing footer text if any
            existing_text = embed.footer.text if embed.footer else ""
            existing_icon = embed.footer.icon_url if embed.footer else None
            
            # Add page number
            if existing_text:
                new_text = f"{existing_text} • Page {i}/{len(self.embeds)}"
            else:
                new_text = f"Page {i}/{len(self.embeds)}"
            
            embed.set_footer(text=new_text, icon_url=existing_icon)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the user is allowed to interact with this view"""
        if self.user and interaction.user.id != self.user.id:
            await interaction.response.send_message("lil bro u can't use this", ephemeral=True)
            return False
        return True
    
    async def back_callback(self, interaction: discord.Interaction):
        if self.current_page == 0:
            self.current_page = len(self.embeds) - 1
        else:
            self.current_page -= 1
        
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page],
            view=self
        )
    
    async def forward_callback(self, interaction: discord.Interaction):
        if self.current_page == len(self.embeds) - 1:
            self.current_page = 0
        else:
            self.current_page += 1
        
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page],
            view=self
        )
    
    async def skipto_callback(self, interaction: discord.Interaction):
        modal = SkipToModal(self)
        await interaction.response.send_modal(modal)
    
    async def close_callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page],
            view=None
        )
        self.stop()

