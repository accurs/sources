import discord
import json
import io
from typing import List, Any, Dict

class PaginatorView(discord.ui.View):
    def __init__(self, author_id: int, data: List[Any], title: str, url: str, 
                 embed_color: int, thumbnail_url: str, items_per_page: int = 5,
                 format_callback=None):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.data = data
        self.title = title
        self.url = url
        self.embed_color = embed_color
        self.thumbnail_url = thumbnail_url
        self.items_per_page = items_per_page
        self.format_callback = format_callback
        self.current_page = 0
        self.total_pages = (len(data) + items_per_page - 1) // items_per_page
        self.update_buttons_state()
    
    def update_buttons_state(self):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == self.total_pages - 1
    
    def create_embed(self):
        embed = discord.Embed(
            title=f"{self.title} ({len(self.data)})",
            url=self.url,
            color=self.embed_color
        )
        start_idx = self.current_page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.data))
        if self.format_callback:
            embed.description = self.format_callback(self.data[start_idx:end_idx])
        else:
            desc = ""
            for item in self.data[start_idx:end_idx]:
                desc += f"{item}\n\n"
            embed.description = desc
        embed.set_footer(
            text=f"{self.current_page + 1}/{self.total_pages}", 
            icon_url="https://git.cursi.ng/discord_logo.png?a"
        )
        return embed

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            if hasattr(self, "message"):
                await self.message.edit(view=self)
        except:
            pass
    
    async def create_ephemeral_copy(self, interaction: discord.Interaction) -> 'PaginatorView':
        ephemeral_view = PaginatorView(
            author_id=interaction.user.id,
            data=self.data,
            title=self.title,
            url=self.url,
            embed_color=self.embed_color,
            thumbnail_url=self.thumbnail_url,
            items_per_page=self.items_per_page,
            format_callback=self.format_callback
        )
        ephemeral_view.current_page = self.current_page
        ephemeral_view.update_buttons_state()
        return ephemeral_view
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True
    
    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:left:1265476224742850633>"), style=discord.ButtonStyle.primary, custom_id="previous")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            ephemeral_view = await self.create_ephemeral_copy(interaction)
            ephemeral_view.current_page = max(0, self.current_page - 1)
            ephemeral_view.update_buttons_state()
            embed = ephemeral_view.create_embed()
            await interaction.response.send_message(embed=embed, view=ephemeral_view, ephemeral=True)
            return
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons_state()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:right:1265476229876678768>"), style=discord.ButtonStyle.primary, custom_id="next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            ephemeral_view = await self.create_ephemeral_copy(interaction)
            ephemeral_view.current_page = min(self.total_pages - 1, self.current_page + 1)
            ephemeral_view.update_buttons_state()
            embed = ephemeral_view.create_embed()
            await interaction.response.send_message(embed=embed, view=ephemeral_view, ephemeral=True)
            return
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        self.update_buttons_state()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:sort:1317260205381386360>"), style=discord.ButtonStyle.secondary, custom_id="skip")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.author_id:
            await self.handle_skip_modal(interaction, self)
        else:
            ephemeral_view = await self.create_ephemeral_copy(interaction)
            await self.handle_skip_modal(interaction, ephemeral_view, ephemeral=True)
    
    async def handle_skip_modal(self, interaction: discord.Interaction, view: 'PaginatorView', ephemeral: bool = False):
        class GoToPageModal(discord.ui.Modal, title="Go to Page"):
            page_number = discord.ui.TextInput(
                label="Navigate to page",
                placeholder=f"Enter a page number (1-{view.total_pages})",
                min_length=1,
                max_length=len(str(view.total_pages))
            )
            async def on_submit(self, modal_interaction: discord.Interaction):
                try:
                    page = int(self.page_number.value) - 1
                    if page < 0 or page >= view.total_pages:
                        raise ValueError
                    view.current_page = page
                    view.update_buttons_state()
                    embed = view.create_embed()
                    if ephemeral:
                        await modal_interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                    else:
                        await modal_interaction.response.edit_message(embed=embed, view=view)
                except ValueError:
                    await modal_interaction.response.send_message("Invalid page number!", ephemeral=True)
        modal = GoToPageModal()
        modal.view = view
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:json:1292867766755524689>"), style=discord.ButtonStyle.secondary, custom_id="json")
    async def json_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        formatjson = json.dumps(self.data, indent=4, ensure_ascii=False)
        file = io.BytesIO(formatjson.encode('utf-8'))
        await interaction.response.send_message(file=discord.File(file, filename="data.json"), ephemeral=True)
    
    @discord.ui.button(emoji=discord.PartialEmoji.from_str("<:bin:1317214464231079989>"), style=discord.ButtonStyle.danger, custom_id="delete")
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            e = discord.Embed(description="no lol.", color=self.embed_color)
            await interaction.response.send_message(embed=e, ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.delete_original_response()


class MessagePaginatorView(PaginatorView):
    def __init__(self, author_id: int, messages: List[Dict], user: discord.User, embed_color: int, format_callback=None):
        super().__init__(
            author_id=author_id,
            data=messages,
            title=f"{user.name}'s Recent Messages",
            url=f"https://discord.com/users/{user.id}",
            embed_color=embed_color,
            thumbnail_url=user.display_avatar.url,
            items_per_page=5,
            format_callback=format_callback
        )
        self.user = user
    
    def create_embed(self):
        embed = super().create_embed()
        embed.set_author(name=f"{self.user.name}", icon_url=self.user.display_avatar.url)
        embed.set_thumbnail(url=self.user.display_avatar.url)
        return embed
    
    async def create_ephemeral_copy(self, interaction: discord.Interaction) -> 'MessagePaginatorView':
        ephemeral_view = MessagePaginatorView(
            author_id=interaction.user.id,
            messages=self.data,
            user=self.user,
            embed_color=self.embed_color,
            format_callback=self.format_callback
        )
        ephemeral_view.current_page = self.current_page
        ephemeral_view.update_buttons_state()
        return ephemeral_view


class GuildPaginatorView(PaginatorView):
    def __init__(self, author_id: int, guilds: List[Dict], user: discord.User, embed_color: int, format_callback=None):
        super().__init__(
            author_id=author_id,
            data=guilds,
            title=f"{user.name}'s guilds shared with Hysteria",
            url=f"https://discord.com/users/{user.id}",
            embed_color=embed_color,
            thumbnail_url=user.display_avatar.url,
            items_per_page=5,
            format_callback=format_callback
        )
        self.user = user
    
    def create_embed(self):
        embed = super().create_embed()
        embed.set_author(name=f"{self.user.name}", icon_url=self.user.display_avatar.url)
        embed.set_thumbnail(url=self.user.display_avatar.url)
        return embed
    
    async def create_ephemeral_copy(self, interaction: discord.Interaction) -> 'GuildPaginatorView':
        ephemeral_view = GuildPaginatorView(
            author_id=interaction.user.id,
            guilds=self.data,
            user=self.user,
            embed_color=self.embed_color,
            format_callback=self.format_callback
        )
        ephemeral_view.current_page = self.current_page
        ephemeral_view.update_buttons_state()
        return ephemeral_view


def format_messages_page(messages: List[Dict]) -> str:
    import re
    from datetime import datetime
    pattern = r"(https://cdn\.discordapp\.com/attachments/[^\s]+)"
    def get_name(url):
        parts = url.split('/')
        last_part = parts[-1].split('?')[0] if '?' in parts[-1] else parts[-1]
        return last_part or "attachment"
    def format_content(content: str) -> str:
        parts = re.split(pattern, content)
        formatted_parts = []
        for part in parts:
            if re.match(pattern, part):
                name = get_name(part)
                formatted_parts.append(f"[**`{name}`**]({part})")
            else:
                safe_part = part.replace("`", "ˋ").replace("\n", " ⏎ ")
                formatted_parts.append(f"`{safe_part}`" if safe_part.strip() else safe_part)
        return "".join(formatted_parts)
    desc = ""
    for msg in messages:
        timestamp = datetime.fromisoformat(msg['timestamp'].rstrip('Z')).timestamp()
        guild_name = msg.get('guild_name', 'Unknown Guild')
        guild_line = (
            f"**[{guild_name}](https://discord.gg/{msg['vanity_url']})**\n"
            if msg.get('vanity_url') else f"**{guild_name}**\n"
        )
        desc += f"{guild_line}-# {format_content(msg['content'])}\n-# <t:{int(timestamp)}:R>\n\n"
    return desc


def format_guilds_page(guilds: List[Dict]) -> str:
    desc = ""
    for guild in guilds:
        guild_name = guild.get("name", "Unknown Guild")
        vanity = guild.get("vanity_url")
        vanity_text = f"`discord.gg/{vanity}`" if vanity else "`no vanity found`"
        desc += f"**{guild_name}**\n-# {vanity_text}\n\n"
    return desc
