import discord
import base64
import aiohttp
import re
from discord import TextChannel, Embed, Message, Role
from discord.ext import commands, tasks
from discord.http import Route
from stare.core.config import Config
from stare.core.tools.context import CustomContext as Context
from stare.core.tools.paginator import PaginatorView
from stare.core.tools.pfps import PFPS
from discord.ui import View, Button
from datetime import datetime, timezone, timedelta
from typing import Optional
import random


def is_guild_owner():
    async def predicate(ctx):
        return ctx.author.id == ctx.guild.owner_id
    return commands.check(predicate)


VM_EMOJIS = {
    'lock': '<:lock:1475189460466536630>',
    'unlock': '<:unlock:1475189463687626822>',
    'hide': '<:ghost:1475189456586801203>',
    'reveal': '<:reveal:1475189462362226698>',
    'claim': '<:claim:1475189454246510705>',
    'increase': '<:increase:1475189457828446291>',
    'decrease': '<:decrease:1475189455190097941>',
    'view': '<:info:1475189459204050975>'
}


class VoiceMasterView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    async def get_owner_channel(self, user_id: int, guild_id: int):
        result = await self.bot.db_pool.fetchrow(
            'SELECT channel_id FROM voicemaster_channels WHERE owner_id = $1 AND guild_id = $2',
            user_id, guild_id
        )
        return result['channel_id'] if result else None

    def _no_channel_embed(self, user):
        return discord.Embed(
            description=f"{Config.EMOJIS.DENY} {user.mention}: You do not own a voice channel!",
            color=Config.COLORS.DENY
        )

    def _not_found_embed(self, user):
        return discord.Embed(
            description=f"{Config.EMOJIS.DENY} {user.mention}: Channel not found!",
            color=Config.COLORS.DENY
        )

    def _success_embed(self, user, text):
        return discord.Embed(
            description=f"{Config.EMOJIS.SUCCESS} {user.mention}: {text}",
            color=Config.COLORS.SUCCESS
        )

    def _warn_embed(self, user, text):
        return discord.Embed(
            description=f"{Config.EMOJIS.WARNING} {user.mention}: {text}",
            color=Config.COLORS.WARNING
        )

    @discord.ui.button(
        emoji='<:lock:1475189460466536630>',
        style=discord.ButtonStyle.secondary,
        custom_id='vm_lock',
        row=0
    )
    async def lock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel_id = await self.get_owner_channel(interaction.user.id, interaction.guild.id)
        if not channel_id:
            return await interaction.response.send_message(embed=self._no_channel_embed(interaction.user), ephemeral=True)

        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(embed=self._not_found_embed(interaction.user), ephemeral=True)

        await channel.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message(embed=self._success_embed(interaction.user, "Locked your voice channel!"), ephemeral=True)

    @discord.ui.button(
        emoji='<:unlock:1475189463687626822>',
        style=discord.ButtonStyle.secondary,
        custom_id='vm_unlock',
        row=0
    )
    async def unlock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel_id = await self.get_owner_channel(interaction.user.id, interaction.guild.id)
        if not channel_id:
            return await interaction.response.send_message(embed=self._no_channel_embed(interaction.user), ephemeral=True)

        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(embed=self._not_found_embed(interaction.user), ephemeral=True)

        await channel.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message(embed=self._success_embed(interaction.user, "Unlocked your voice channel."), ephemeral=True)

    @discord.ui.button(
        emoji='<:ghost:1475189456586801203>',
        style=discord.ButtonStyle.secondary,
        custom_id='vm_ghost',
        row=0
    )
    async def ghost_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel_id = await self.get_owner_channel(interaction.user.id, interaction.guild.id)
        if not channel_id:
            return await interaction.response.send_message(embed=self._no_channel_embed(interaction.user), ephemeral=True)

        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(embed=self._not_found_embed(interaction.user), ephemeral=True)

        await channel.set_permissions(interaction.guild.default_role, view_channel=False)
        await interaction.response.send_message(embed=self._success_embed(interaction.user, "Ghosted your voice channel."), ephemeral=True)

    @discord.ui.button(
        emoji='<:reveal:1475189462362226698>',
        style=discord.ButtonStyle.secondary,
        custom_id='vm_reveal',
        row=0
    )
    async def reveal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel_id = await self.get_owner_channel(interaction.user.id, interaction.guild.id)
        if not channel_id:
            return await interaction.response.send_message(embed=self._no_channel_embed(interaction.user), ephemeral=True)

        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(embed=self._not_found_embed(interaction.user), ephemeral=True)

        await channel.set_permissions(interaction.guild.default_role, view_channel=True)
        await interaction.response.send_message(embed=self._success_embed(interaction.user, "Revealed your voice channel."), ephemeral=True)

    @discord.ui.button(
        emoji='<:claim:1475189454246510705>',
        style=discord.ButtonStyle.secondary,
        custom_id='vm_claim',
        row=1
    )
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{Config.EMOJIS.DENY} {interaction.user.mention}: You must be in a voice channel!",
                    color=Config.COLORS.DENY
                ),
                ephemeral=True
            )

        result = await self.bot.db_pool.fetchrow(
            'SELECT owner_id FROM voicemaster_channels WHERE channel_id = $1',
            interaction.user.voice.channel.id
        )

        if not result:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{Config.EMOJIS.DENY} {interaction.user.mention}: This is not a **VoiceMaster** channel!",
                    color=Config.COLORS.DENY
                ),
                ephemeral=True
            )

        owner = interaction.guild.get_member(result['owner_id'])
        if owner and owner in interaction.user.voice.channel.members:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{Config.EMOJIS.DENY} {interaction.user.mention}: The owner is still in the channel!",
                    color=Config.COLORS.DENY
                ),
                ephemeral=True
            )

        await self.bot.db_pool.execute(
            'UPDATE voicemaster_channels SET owner_id = $1 WHERE channel_id = $2',
            interaction.user.id, interaction.user.voice.channel.id
        )
        await interaction.response.send_message(embed=self._success_embed(interaction.user, "Claimed the voice channel."), ephemeral=True)

    @discord.ui.button(
        emoji='<:increase:1475189457828446291>',
        style=discord.ButtonStyle.secondary,
        custom_id='vm_increase',
        row=1
    )
    async def increase_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel_id = await self.get_owner_channel(interaction.user.id, interaction.guild.id)
        if not channel_id:
            return await interaction.response.send_message(embed=self._no_channel_embed(interaction.user), ephemeral=True)

        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(embed=self._not_found_embed(interaction.user), ephemeral=True)

        if channel.user_limit >= 99:
            return await interaction.response.send_message(embed=self._warn_embed(interaction.user, "Channel is at maximum limit!"), ephemeral=True)

        await channel.edit(user_limit=channel.user_limit + 1)
        await interaction.response.send_message(embed=self._success_embed(interaction.user, f"Increased limit to **{channel.user_limit}**."), ephemeral=True)

    @discord.ui.button(
        emoji='<:decrease:1475189455190097941>',
        style=discord.ButtonStyle.secondary,
        custom_id='vm_decrease',
        row=1
    )
    async def decrease_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel_id = await self.get_owner_channel(interaction.user.id, interaction.guild.id)
        if not channel_id:
            return await interaction.response.send_message(embed=self._no_channel_embed(interaction.user), ephemeral=True)

        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(embed=self._not_found_embed(interaction.user), ephemeral=True)

        if channel.user_limit <= 0:
            return await interaction.response.send_message(embed=self._warn_embed(interaction.user, "Channel is at minimum limit!"), ephemeral=True)

        await channel.edit(user_limit=max(0, channel.user_limit - 1))
        await interaction.response.send_message(embed=self._success_embed(interaction.user, f"Decreased limit to **{channel.user_limit}**."), ephemeral=True)

    @discord.ui.button(
        emoji='<:info:1475189459204050975>',
        style=discord.ButtonStyle.secondary,
        custom_id='vm_view',
        row=1
    )
    async def view_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel_id = await self.get_owner_channel(interaction.user.id, interaction.guild.id)
        if not channel_id:
            return await interaction.response.send_message(embed=self._no_channel_embed(interaction.user), ephemeral=True)

        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(embed=self._not_found_embed(interaction.user), ephemeral=True)

        embed = discord.Embed(title='Channel Information', color=Config.COLORS.DEFAULT)
        embed.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.add_field(name='Name', value=channel.name, inline=False)
        embed.add_field(name='Members', value=len(channel.members), inline=False)
        embed.add_field(name='Limit', value=channel.user_limit if channel.user_limit > 0 else 'Unlimited', inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


import io


async def send_transcript(bot, interaction: discord.Interaction, channel: discord.TextChannel, ticket_author: discord.Member, claimed_by: discord.Member = None):
    messages = []
    async for msg in channel.history(limit=None, oldest_first=True):
        if msg.author.bot:
            continue
        messages.append(f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author.name}: {msg.content}")

    transcript_content = "\n".join(messages) if messages else "No messages found."
    
    transcript_channel_id = None
    if bot and bot.db_pool:
        result = await bot.db_pool.fetchrow(
            'SELECT transcript_channel_id FROM tickets WHERE guild_id = $1',
            interaction.guild.id
        )
        if result and result['transcript_channel_id']:
            transcript_channel_id = result['transcript_channel_id']
    
    if transcript_channel_id:
        transcript_channel = interaction.guild.get_channel(transcript_channel_id)
        if transcript_channel:
            file = discord.File(
                fp=io.BytesIO(transcript_content.encode('utf-8')),
                filename=f"ticket-{ticket_author.name}.txt"
            )
            embed = discord.Embed(
                title=f"Ticket Transcript - {ticket_author.name}",
                description=f"Ticket closed by {interaction.user.mention}",
                color=Config.COLORS.DEFAULT
            )
            embed.add_field(name="Ticket Author", value=ticket_author.mention, inline=True)
            embed.add_field(name="Closed By", value=interaction.user.mention, inline=True)
            if claimed_by:
                embed.add_field(name="Claimed By", value=claimed_by.mention, inline=True)
            embed.set_footer(text=f"Ticket: {channel.name}")
            await transcript_channel.send(embed=embed, file=file)
    
    try:
        file_dm = discord.File(
            fp=io.BytesIO(transcript_content.encode('utf-8')),
            filename=f"ticket-{ticket_author.name}.txt"
        )
        await ticket_author.send(
            content=f"Here's a full transcript of your **ticket** in **{interaction.guild.name}** (`{interaction.guild.id}`)",
            file=file_dm
        )
    except discord.Forbidden:
        pass


class TicketCloseConfirmView(discord.ui.View):
    def __init__(self, bot=None):
        super().__init__(timeout=60)
        self.bot = bot

    @discord.ui.button(emoji="<:success:1472263845174181920>", style=discord.ButtonStyle.secondary)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        channel = interaction.channel
        category = channel.category

        ticket_author_name = channel.name.removeprefix('ticket-').removeprefix('closed-')
        ticket_author = discord.utils.find(
            lambda m: m.name.lower() == ticket_author_name.lower(), interaction.guild.members
        )

        claimed_by = None
        if self.bot and self.bot.db_pool:
            result = await self.bot.db_pool.fetchrow(
                'SELECT claimed_by FROM ticket_channels WHERE channel_id = $1',
                channel.id
            )
            if result and result['claimed_by']:
                claimed_by = interaction.guild.get_member(result['claimed_by'])

        await send_transcript(self.bot, interaction, channel, ticket_author or interaction.user, claimed_by)

        if ticket_author and category:
            await channel.set_permissions(ticket_author, view_channel=False)
            await category.set_permissions(ticket_author, view_channel=False)

        await channel.edit(name=f'closed-{ticket_author_name}')
        await interaction.edit_original_response(
            embed=discord.Embed(
                description=f"{Config.EMOJIS.SUCCESS} {interaction.user.mention}: Closed the ticket.",
                color=Config.COLORS.SUCCESS
            ),
            view=None
        )

    @discord.ui.button(emoji="<:fail:1472263737896468676>", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="aw man i wanted to go kaboom on ur ticket...",
            embed=None,
            view=None
        )


class TicketDeleteConfirmView(discord.ui.View):
    def __init__(self, bot=None):
        super().__init__(timeout=60)
        self.bot = bot

    @discord.ui.button(emoji="<:success:1472263845174181920>", style=discord.ButtonStyle.secondary)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        channel = interaction.channel

        if self.bot:
            try:
                await self.bot.db_pool.execute('DELETE FROM ticket_channels WHERE channel_id = $1', channel.id)
            except Exception:
                pass

        await channel.delete(reason=f'Ticket deleted by {interaction.user}')

    @discord.ui.button(emoji="<:fail:1472263737896468676>", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="aw man i wanted to go kaboom on ur ticket...",
            embed=None,
            view=None
        )


class TicketActionView(discord.ui.View):
    def __init__(self, bot=None):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Claim",
        emoji="<:04_ticket:1478781894836486144>",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_claim_button",
    )
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith('ticket-'):
            return await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{Config.EMOJIS.DENY} {interaction.user.mention}: This ticket is already closed.",
                    color=Config.COLORS.DENY
                ),
                ephemeral=True
            )

        # Only staff with Manage Channels or a configured supporter role can claim tickets
        if not interaction.user.guild_permissions.manage_channels:
            allowed = False
            if self.bot and self.bot.db_pool and interaction.guild:
                rows = await self.bot.db_pool.fetch(
                    "SELECT role_id FROM ticket_support_roles WHERE guild_id = $1",
                    interaction.guild.id,
                )
                supporter_role_ids = {row["role_id"] for row in rows}
                if supporter_role_ids and any(r.id in supporter_role_ids for r in interaction.user.roles):
                    allowed = True

            if not allowed:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        description=f"{Config.EMOJIS.DENY} {interaction.user.mention}: You don't have permission to claim tickets!",
                        color=Config.COLORS.DENY,
                    ),
                    ephemeral=True,
                )
        
        if self.bot and self.bot.db_pool:
            result = await self.bot.db_pool.fetchrow(
                'SELECT claimed_by FROM ticket_channels WHERE channel_id = $1',
                interaction.channel.id
            )
            
            if result and result['claimed_by']:
                claimer = interaction.guild.get_member(result['claimed_by'])
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        description=f"{Config.EMOJIS.DENY} {interaction.user.mention}: This ticket is already claimed by {claimer.mention if claimer else 'someone'}!",
                        color=Config.COLORS.DENY
                    ),
                    ephemeral=True
                )
            
            await self.bot.db_pool.execute(
                'UPDATE ticket_channels SET claimed_by = $1 WHERE channel_id = $2',
                interaction.user.id, interaction.channel.id
            )
            
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{Config.EMOJIS.SUCCESS} {interaction.user.mention} has claimed this ticket!",
                    color=Config.COLORS.SUCCESS
                )
            )

    @discord.ui.button(
        label="Close",
        emoji="<:cancel:1472264411422003321>",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_close_button",
    )
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith('ticket-'):
            return await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{Config.EMOJIS.DENY} {interaction.user.mention}: This ticket is already closed.",
                    color=Config.COLORS.DENY
                ),
                ephemeral=True
            )

        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"{Config.EMOJIS.WARNING} {interaction.user.mention}: Are you **sure** you want to close this **ticket**?",
                color=Config.COLORS.WARNING
            ),
            view=TicketCloseConfirmView(self.bot),
            ephemeral=True
        )

    @discord.ui.button(
        label="Delete",
        emoji="<:trash:1475205210166132818>",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_delete_button",
    )
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{Config.EMOJIS.DENY} {interaction.user.mention}: You don't have permission to delete tickets!",
                    color=Config.COLORS.DENY
                ),
                ephemeral=True
            )

        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"{Config.EMOJIS.WARNING} {interaction.user.mention}: Are you **sure** you want to delete this **ticket**?",
                color=Config.COLORS.WARNING
            ),
            view=TicketDeleteConfirmView(self.bot),
            ephemeral=True
        )


class TicketSetupView(discord.ui.View):
    def __init__(self, bot=None):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="🎟️ Create Ticket",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket_create_button",
    )
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        author = interaction.user

        category = discord.utils.get(guild.categories, name="Tickets")
        if category:
            for channel in category.channels:
                if channel.name == f"ticket-{author.name.lower()}":
                    return await interaction.response.send_message(
                        embed=discord.Embed(
                            description=f"{author.mention}: You already **have** a ticket **open** in {channel.mention}!"
                        ),
                        ephemeral=True,
                    )

        if not category:
            overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
            category = await guild.create_category("Tickets", overwrites=overwrites)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            author: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }

        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{author.name.lower()}",
            category=category,
            overwrites=overwrites,
        )

        welcome_embed = discord.Embed(
            title="Welcome to your ticket",
            description="Wait patiently, and our team will be with you soon.",
        )
        welcome_embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)

        welcome_msg = await ticket_channel.send(content=author.mention, embed=welcome_embed, view=TicketActionView(self.bot))

        if self.bot and self.bot.db_pool:
            try:
                await self.bot.db_pool.execute(
                    'INSERT INTO ticket_channels (channel_id, guild_id, author_id, claimed_by) VALUES ($1, $2, $3, NULL) ON CONFLICT (channel_id) DO UPDATE SET author_id = $3',
                    ticket_channel.id, guild.id, author.id
                )
            except Exception:
                pass

        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"{author.mention}: Your ticket has been created in {ticket_channel.mention}."
            ),
            ephemeral=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Confessions UI
# ─────────────────────────────────────────────────────────────────────────────

class ConfessionModal(discord.ui.Modal, title="Submit a Confession"):
    confession_content = discord.ui.TextInput(
        label="What is your confession?",
        style=discord.TextStyle.long,
        placeholder="Type your confession here...",
        required=True,
        max_length=2000,
    )
    attachment_url = discord.ui.TextInput(
        label="Attachment URL (optional)",
        style=discord.TextStyle.short,
        required=False,
        placeholder="https://...",
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        message = self.confession_content.value.strip()

        async def respond(embed, ephemeral=True):
            await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

        await _submit_confession(self.bot, interaction, message, respond=respond)


def _cv2_payload(text: str, button_disabled: bool = False, custom_id: str = "confess_submit_btn") -> dict:
    """Build a CV2 message payload dict for use with the raw HTTP API."""
    return {
        "flags": 32768,
        "components": [
            {
                "type": 17,
                "components": [
                    {
                        "type": 10,
                        "content": text
                    },
                    {"type": 14},
                    {
                        "type": 1,
                        "components": [
                            {
                                "type": 2,
                                "style": 2,
                                "label": "Submit a confession",
                                "emoji": {
                                    "id": "1475189457828446291",
                                    "name": "increase",
                                    "animated": False
                                },
                                "custom_id": custom_id,
                                "disabled": button_disabled
                            }
                        ]
                    }
                ]
            }
        ]
    }


async def _submit_confession(bot, source, message: str, respond=None):
    """
    Core confession submission logic.
    source  : commands.Context or discord.Interaction
    respond : async callable(embed, ephemeral) — used for modal/button replies
    """
    guild = source.guild

    config = await bot.db_pool.fetchrow(
        'SELECT channel_id, last_message_id, confession_count FROM confession_config WHERE guild_id = $1',
        guild.id
    )

    if not config or not config['channel_id']:
        embed = discord.Embed(
            description="**Confessions** aren't setup in this server!",
            color=Config.COLORS.DENY
        )
        if respond:
            await respond(embed=embed, ephemeral=True)
        else:
            await source.deny(embed=embed)
        return

    # Blacklist check
    blacklisted = await bot.db_pool.fetch(
        'SELECT word FROM confession_blacklist WHERE guild_id = $1', guild.id
    )
    msg_lower = message.lower()
    for row in blacklisted:
        if re.search(r'\b' + re.escape(row['word']) + r'\b', msg_lower):
            embed = discord.Embed(
                description="I **couldn't** submit your confession, because it contains blacklisted words.",
                color=Config.COLORS.WARNING
            )
            if respond:
                await respond(embed=embed, ephemeral=True)
            else:
                await source.warn(embed=embed)
            return

    channel = guild.get_channel(config['channel_id'])
    if not channel:
        embed = discord.Embed(
            description="**Confessions** aren't setup in this server!",
            color=Config.COLORS.DENY
        )
        if respond:
            await respond(embed=embed, ephemeral=True)
        else:
            await source.deny(embed=embed)
        return

    # Increment count first so we have the number before sending
    count_row = await bot.db_pool.fetchrow("""
        INSERT INTO confession_config (guild_id, channel_id, confession_count, last_message_id)
        VALUES ($1, $2, 1, NULL)
        ON CONFLICT (guild_id) DO UPDATE
            SET confession_count = confession_config.confession_count + 1,
                channel_id = EXCLUDED.channel_id
        RETURNING confession_count
    """, guild.id, config['channel_id'])

    count = count_row['confession_count']

    # Disable the button on the previous confession message via raw HTTP PATCH
    last_msg_id = config['last_message_id']
    if last_msg_id:
        try:
            route_get = Route('GET', '/channels/{channel_id}/messages/{message_id}',
                              channel_id=channel.id, message_id=last_msg_id)
            prev_data = await bot.http.request(route_get)
            # Extract text from the CV2 container's text display component
            prev_text = ""
            for comp in prev_data.get("components", []):
                if comp.get("type") == 17:
                    for inner in comp.get("components", []):
                        if inner.get("type") == 10:
                            prev_text = inner.get("content", "")
                            break
                    break

            route_patch = Route('PATCH', '/channels/{channel_id}/messages/{message_id}',
                                channel_id=channel.id, message_id=last_msg_id)
            await bot.http.request(route_patch, json=_cv2_payload(
                prev_text,
                button_disabled=True,
                custom_id=f"confess_disabled_{last_msg_id}"
            ))
        except Exception:
            pass

    # Send the new confession via raw HTTP POST
    confession_text = f"# Confession (#{count})\n<:info:1475189459204050975> \"{message}\""
    payload = _cv2_payload(confession_text)

    route = Route('POST', '/channels/{channel_id}/messages', channel_id=channel.id)
    data = await bot.http.request(route, json=payload)
    msg_id = int(data['id'])

    # Store the new last_message_id
    await bot.db_pool.execute(
        "UPDATE confession_config SET last_message_id = $1 WHERE guild_id = $2",
        msg_id, guild.id
    )

    msg_link = f"https://discord.com/channels/{guild.id}/{channel.id}/{msg_id}"
    success_embed = discord.Embed(
        description=f"Your **confession** has been submitted! [**View your message**]({msg_link})",
        color=Config.COLORS.SUCCESS
    )

    if respond:
        await respond(embed=success_embed, ephemeral=True)
    else:
        await source.approve(embed=success_embed)


# ─────────────────────────────────────────────────────────────────────────────
# Main Cog
# ─────────────────────────────────────────────────────────────────────────────

class Configuration(commands.Cog):
    """Server configuration commands"""

    def __init__(self, bot):
        self.bot = bot
        self.sticky_cache = {}
        self.bump_timers = {}
        self.bot.add_view(VoiceMasterView(bot))
        self.bot.add_view(TicketSetupView(bot))
        self.bot.add_view(TicketActionView(bot))
    
    def _create_embed_from_data(self, data: dict) -> discord.Embed:
        """Helper method to create an embed from JSON data"""
        embed = discord.Embed()
        
        if 'title' in data:
            embed.title = data['title']
        if 'description' in data:
            embed.description = data['description']
        
        if not embed.description:
            embed.description = "\u200b"
        
        if 'color' in data:
            embed.color = data['color']
        elif 'colour' in data:
            embed.color = data['colour']
        else:
            embed.color = Config.COLORS.DEFAULT
        
        if 'url' in data:
            embed.url = data['url']
        
        if 'timestamp' in data:
            if data['timestamp'] == 'now':
                from datetime import datetime
                embed.timestamp = datetime.utcnow()
        
        if 'author' in data:
            author = data['author']
            embed.set_author(
                name=author.get('name', ''),
                url=author.get('url'),
                icon_url=author.get('icon_url')
            )
        
        if 'footer' in data:
            footer = data['footer']
            embed.set_footer(
                text=footer.get('text', ''),
                icon_url=footer.get('icon_url')
            )
        
        if 'thumbnail' in data and data['thumbnail'].get('url'):
            embed.set_thumbnail(url=data['thumbnail']['url'])
        
        if 'image' in data and data['image'].get('url'):
            embed.set_image(url=data['image']['url'])
        
        if 'fields' in data:
            for field in data['fields']:
                embed.add_field(
                    name=field.get('name', 'Field'),
                    value=field.get('value', 'Value'),
                    inline=field.get('inline', False)
                )
        
        return embed
    
    def _create_view_from_components(self, components: list) -> discord.ui.View:
        """Helper method to create a view with buttons from components data"""
        from discord.ui import View, Button
        from discord import ButtonStyle
        
        view = View(timeout=None)
        
        for action_row in components:
            if action_row.get('type') != 1:
                continue
            
            for component in action_row.get('components', []):
                if component.get('type') == 2:
                    style = component.get('style', 1)
                    label = component.get('label', 'Button')
                    url = component.get('url')
                    
                    if style == 5:
                        button = Button(style=ButtonStyle.link, label=label, url=url)
                    else:
                        button = Button(style=ButtonStyle(style), label=label, disabled=True)
                    
                    view.add_item(button)
        
        return view

    async def cog_load(self):
        if not hasattr(self.bot, 'db_pool') or not self.bot.db_pool:
            return

        try:
            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS autorole (
                    guild_id BIGINT,
                    role_id BIGINT,
                    type TEXT,
                    PRIMARY KEY (guild_id, type)
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS reactionrole (
                    guild_id BIGINT,
                    message_id BIGINT,
                    channel_id BIGINT,
                    emoji TEXT,
                    role_id BIGINT,
                    PRIMARY KEY (message_id, emoji)
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS prefixes (
                    guild_id BIGINT PRIMARY KEY,
                    prefix TEXT
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS welcome (
                    guild_id BIGINT PRIMARY KEY,
                    channel_id BIGINT,
                    message TEXT,
                    enabled BOOLEAN DEFAULT TRUE
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS boost (
                    guild_id BIGINT PRIMARY KEY,
                    channel_id BIGINT,
                    message TEXT,
                    enabled BOOLEAN DEFAULT TRUE,
                    role_id BIGINT
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS autoresponder (
                    guild_id BIGINT,
                    trigger_text TEXT,
                    response TEXT,
                    strict BOOLEAN DEFAULT TRUE,
                    reply BOOLEAN DEFAULT FALSE,
                    PRIMARY KEY (guild_id, trigger_text)
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS counting (
                    guild_id BIGINT PRIMARY KEY,
                    channel_id BIGINT,
                    current_count INT DEFAULT 0,
                    block_words BOOLEAN DEFAULT TRUE,
                    last_user BIGINT,
                    reaction TEXT DEFAULT '✅'
                )
            """)

            try:
                await self.bot.db_pool.execute("""
                    ALTER TABLE counting ADD COLUMN IF NOT EXISTS current_count INT DEFAULT 0
                """)
            except Exception:
                pass

            try:
                await self.bot.db_pool.execute("""
                    ALTER TABLE counting ADD COLUMN IF NOT EXISTS reaction TEXT DEFAULT '✅'
                """)
            except Exception:
                pass

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS stickymessage (
                    guild_id BIGINT,
                    channel_id BIGINT PRIMARY KEY,
                    message TEXT,
                    last_message_id BIGINT
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    guild_id BIGINT PRIMARY KEY,
                    channel_id BIGINT,
                    message_id BIGINT,
                    transcript_channel_id BIGINT
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS ticket_channels (
                    channel_id BIGINT PRIMARY KEY,
                    guild_id BIGINT,
                    author_id BIGINT,
                    claimed_by BIGINT
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS ticket_support_roles (
                    guild_id BIGINT,
                    role_id BIGINT,
                    PRIMARY KEY (guild_id, role_id)
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS aliases (
                    guild_id BIGINT,
                    alias TEXT,
                    command TEXT,
                    PRIMARY KEY (guild_id, alias)
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS vanity_rewards (
                    guild_id BIGINT PRIMARY KEY,
                    keyword TEXT,
                    role_id BIGINT,
                    channel_id BIGINT,
                    message TEXT,
                    emoji TEXT
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS bumpreminder (
                    guild_id BIGINT PRIMARY KEY,
                    channel_id BIGINT,
                    message TEXT,
                    role_id BIGINT
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS voicemaster (
                    guild_id BIGINT PRIMARY KEY,
                    channel_id BIGINT,
                    category_id BIGINT,
                    channel_name TEXT,
                    interface_channel_id BIGINT
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS voicemaster_channels (
                    guild_id BIGINT,
                    channel_id BIGINT PRIMARY KEY,
                    owner_id BIGINT
                )
            """)

            # ── Confessions tables ────────────────────────────────────────────

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS confession_config (
                    guild_id         BIGINT PRIMARY KEY,
                    channel_id       BIGINT,
                    last_message_id  BIGINT,
                    confession_count INT DEFAULT 0
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS confession_blacklist (
                    guild_id BIGINT,
                    word     TEXT,
                    PRIMARY KEY (guild_id, word)
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS webhook (
                    identifier TEXT,
                    guild_id BIGINT,
                    channel_id BIGINT,
                    author_id BIGINT,
                    webhook_id BIGINT,
                    PRIMARY KEY (channel_id, webhook_id)
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS starboard (
                    guild_id BIGINT,
                    channel_id BIGINT,
                    self_star BOOLEAN DEFAULT TRUE,
                    threshold INTEGER DEFAULT 3,
                    emoji TEXT,
                    color INTEGER,
                    attachments BOOLEAN DEFAULT TRUE,
                    PRIMARY KEY (guild_id, emoji)
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS starboard_entry (
                    guild_id BIGINT,
                    channel_id BIGINT,
                    message_id BIGINT,
                    star_id BIGINT,
                    emoji TEXT,
                    PRIMARY KEY (message_id, emoji)
                )
            """)

            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS starboard_ignore (
                    guild_id BIGINT,
                    emoji TEXT,
                    target_id BIGINT,
                    target_type TEXT,
                    PRIMARY KEY (guild_id, emoji, target_id)
                )
            """)

            # ── Backwards-compat column additions ────────────────────────────

            try:
                await self.bot.db_pool.execute(
                    "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS transcript_channel_id BIGINT"
                )
                await self.bot.db_pool.execute(
                    "ALTER TABLE ticket_channels ADD COLUMN IF NOT EXISTS author_id BIGINT"
                )
                await self.bot.db_pool.execute(
                    "ALTER TABLE ticket_channels ADD COLUMN IF NOT EXISTS claimed_by BIGINT"
                )
            except Exception:
                pass

            try:
                await self.bot.db_pool.execute(
                    "ALTER TABLE vanity_rewards ADD COLUMN IF NOT EXISTS keyword TEXT"
                )
                await self.bot.db_pool.execute(
                    "ALTER TABLE vanity_rewards ADD COLUMN IF NOT EXISTS channel_id BIGINT"
                )
                await self.bot.db_pool.execute(
                    "ALTER TABLE vanity_rewards ADD COLUMN IF NOT EXISTS message TEXT"
                )
                await self.bot.db_pool.execute(
                    "ALTER TABLE vanity_rewards ADD COLUMN IF NOT EXISTS emoji TEXT"
                )
            except Exception:
                pass

            stickies = await self.bot.db_pool.fetch("SELECT * FROM stickymessage")
            for sticky in stickies:
                self.sticky_cache[sticky['channel_id']] = {
                    'message': sticky['message'],
                    'last_message_id': sticky.get('last_message_id')
                }

            self.bot.add_view(TicketSetupView(self.bot))

            all_tickets = await self.bot.db_pool.fetch("SELECT guild_id, channel_id, message_id FROM tickets")
            for row in all_tickets:
                try:
                    guild = self.bot.get_guild(row['guild_id'])
                    if not guild:
                        continue
                    channel = guild.get_channel(row['channel_id'])
                    if not channel:
                        continue
                    msg = await channel.fetch_message(row['message_id'])
                    await msg.edit(view=TicketSetupView(self.bot))
                except Exception:
                    pass

            all_ticket_channels = await self.bot.db_pool.fetch("SELECT guild_id, channel_id, welcome_message_id FROM ticket_channels")
            for row in all_ticket_channels:
                try:
                    guild = self.bot.get_guild(row['guild_id'])
                    if not guild:
                        continue
                    channel = guild.get_channel(row['channel_id'])
                    if not channel:
                        await self.bot.db_pool.execute('DELETE FROM ticket_channels WHERE channel_id = $1', row['channel_id'])
                        continue
                    msg = await channel.fetch_message(row['welcome_message_id'])
                    await msg.edit(view=TicketActionView(self.bot))
                except Exception:
                    pass

        except Exception:
            pass

    async def download_to_data_uri(self, url: str):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    img = await resp.read()
            except Exception:
                return None
        encoded = base64.b64encode(img).decode()
        return f"data:image/png;base64,{encoded}"

    # ─────────────────────────────────────────────────────────────────────────
    # VoiceMaster
    # ─────────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        config = await self.bot.db_pool.fetchrow(
            'SELECT channel_id, category_id, channel_name FROM voicemaster WHERE guild_id = $1',
            member.guild.id
        )
        if not config:
            return

        if after.channel and after.channel.id == config['channel_id']:
            channel_name = (config.get('channel_name') or "{user}'s channel").replace("{user}", member.display_name)
            category = member.guild.get_channel(config['category_id'])
            channel = await member.guild.create_voice_channel(name=channel_name, category=category)
            await self.bot.db_pool.execute(
                'INSERT INTO voicemaster_channels (guild_id, channel_id, owner_id) VALUES ($1, $2, $3)',
                member.guild.id, channel.id, member.id
            )
            await member.move_to(channel)

        if before.channel and before.channel.id != config['channel_id']:
            record = await self.bot.db_pool.fetchrow(
                'SELECT channel_id FROM voicemaster_channels WHERE guild_id = $1 AND channel_id = $2',
                member.guild.id, before.channel.id
            )
            if record and len(before.channel.members) == 0:
                await before.channel.delete()
                await self.bot.db_pool.execute(
                    'DELETE FROM voicemaster_channels WHERE channel_id = $1',
                    before.channel.id
                )

    @commands.group(invoke_without_command=True, aliases=["vm", "vc"])
    async def voicemaster(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @voicemaster.command(name='setup')
    @commands.has_permissions(manage_guild=True)
    async def voicemaster_setup(self, ctx: Context, channel_name: str = "{user}'s channel"):
        category = await ctx.guild.create_category('stare vm')

        interface_channel = await ctx.guild.create_text_channel(name='interface', category=category)
        await interface_channel.set_permissions(ctx.guild.default_role, send_messages=False, add_reactions=False)

        join_channel = await ctx.guild.create_voice_channel(name='j2c', category=category)

        embed = discord.Embed(
            title='VoiceMaster Interface',
            description=f'Manage your personal voice channel created in {join_channel.mention}',
            color=Config.COLORS.DEFAULT
        )
        embed.set_author(
            name=ctx.guild.name,
            icon_url=ctx.guild.icon.url if ctx.guild.icon else None
        )
        embed.add_field(name='', value=(
            f"{VM_EMOJIS['lock']} - [`Lock`](https://stare.lat) **your voice channel**\n"
            f"{VM_EMOJIS['unlock']} - [`Unlock`](https://stare.lat) **your voice channel**\n"
            f"{VM_EMOJIS['hide']} - [`Hide`](https://stare.lat) **your voice channel**\n"
            f"{VM_EMOJIS['reveal']} - [`Reveal`](https://stare.lat) **your voice channel**\n"
            f"{VM_EMOJIS['claim']} - [`Claim`](https://stare.lat) **a voice channel**\n"
            f"{VM_EMOJIS['increase']} - [`Increase`](https://stare.lat) **your channel's user limit**\n"
            f"{VM_EMOJIS['decrease']} - [`Decrease`](https://stare.lat) **your channel's user limit**\n"
            f"{VM_EMOJIS['view']} - [`View`](https://stare.lat) **a channel's information**"
        ), inline=False)

        await interface_channel.send(embed=embed, view=VoiceMasterView(self.bot))

        await self.bot.db_pool.execute('''
            INSERT INTO voicemaster (guild_id, channel_id, category_id, channel_name, interface_channel_id)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id) DO UPDATE SET
                channel_id = $2, category_id = $3, channel_name = $4, interface_channel_id = $5
        ''', ctx.guild.id, join_channel.id, category.id, channel_name, interface_channel.id)

        await ctx.approve(f"I've setup **VoiceMaster**, created 2 **channels** and 1 **category**. You can rename either if you'd like.")

    @voicemaster.command(name='reset', aliases=["disable", "remove"])
    @commands.has_permissions(manage_guild=True)
    async def voicemaster_reset(self, ctx: Context):
        result = await self.bot.db_pool.fetchrow(
            'SELECT category_id FROM voicemaster WHERE guild_id = $1', ctx.guild.id
        )

        if not result:
            return await ctx.warn("**VoiceMaster** is not set up in this server!")

        category = ctx.guild.get_channel(result['category_id'])
        if category:
            for channel in category.channels:
                await channel.delete()
            await category.delete()

        await self.bot.db_pool.execute('DELETE FROM voicemaster WHERE guild_id = $1', ctx.guild.id)
        await self.bot.db_pool.execute('DELETE FROM voicemaster_channels WHERE guild_id = $1', ctx.guild.id)

        await ctx.approve("I've reset the **VoiceMaster** configuration for this server.")

    # ─────────────────────────────────────────────────────────────────────────
    # Autorole
    # ─────────────────────────────────────────────────────────────────────────

    @commands.group(invoke_without_command=True, aliases=['ar'])
    async def autorole(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @autorole.command(name='humans')
    @commands.has_permissions(manage_roles=True)
    async def autorole_humans(self, ctx: Context, *, role: discord.Role):
        await self.bot.db_pool.execute('''
            INSERT INTO autorole (guild_id, role_id, type) 
            VALUES ($1, $2, $3) 
            ON CONFLICT (guild_id, type) 
            DO UPDATE SET role_id = $2
        ''', ctx.guild.id, role.id, 'humans')
        await ctx.approve(f'Set autorole for humans to {role.mention}')

    @autorole.command(name='bots')
    @commands.has_permissions(manage_roles=True)
    async def autorole_bots(self, ctx: Context, *, role: discord.Role):
        await self.bot.db_pool.execute('''
            INSERT INTO autorole (guild_id, role_id, type) 
            VALUES ($1, $2, $3) 
            ON CONFLICT (guild_id, type) 
            DO UPDATE SET role_id = $2
        ''', ctx.guild.id, role.id, 'bots')
        await ctx.approve(f'Set autorole for bots to {role.mention}')

    @autorole.command(name='list')
    async def autorole_list(self, ctx: Context):
        results = await self.bot.db_pool.fetch('SELECT role_id, type FROM autorole WHERE guild_id = $1', ctx.guild.id)
        if not results:
            return await ctx.warn('No autoroles configured')

        embed = discord.Embed(color=Config.COLORS.DEFAULT, title='Autoroles')
        for row in results:
            role = ctx.guild.get_role(row['role_id'])
            embed.add_field(name=row['type'].title(), value=role.mention if role else 'Deleted', inline=False)
        await ctx.send(embed=embed)

    @autorole.command(name='remove')
    @commands.has_permissions(manage_roles=True)
    async def autorole_remove(self, ctx: Context, type: str):
        if type.lower() not in ['humans', 'bots']:
            return await ctx.warn('Type must be `humans` or `bots`')

        result = await self.bot.db_pool.execute(
            'DELETE FROM autorole WHERE guild_id = $1 AND type = $2',
            ctx.guild.id, type.lower()
        )
        if result == 'DELETE 0':
            return await ctx.warn(f'No autorole set for {type}')
        await ctx.approve(f'Removed autorole for {type}')

    # ─────────────────────────────────────────────────────────────────────────
    # Reaction Roles
    # ─────────────────────────────────────────────────────────────────────────

    @commands.group(invoke_without_command=True, aliases=['rr'])
    async def reactionrole(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @reactionrole.command(name='add')
    @commands.has_permissions(manage_roles=True)
    async def reactionrole_add(self, ctx: Context, message_link: str, emoji: str, role: discord.Role):
        pattern = r'https://discord\.com/channels/(\d+)/(\d+)/(\d+)'
        match = re.match(pattern, message_link)
        if not match:
            return await ctx.warn('Invalid message link')

        guild_id, channel_id, message_id = map(int, match.groups())
        if guild_id != ctx.guild.id:
            return await ctx.warn('Message must be from this server')

        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            return await ctx.warn('Channel not found')

        try:
            message = await channel.fetch_message(message_id)
        except Exception:
            return await ctx.warn('Message not found')

        emoji_str = emoji
        if emoji.startswith('<') and emoji.endswith('>'):
            emoji_id = re.search(r':(\d+)>', emoji)
            if emoji_id:
                emoji_str = emoji_id.group(1)
                emoji_obj = discord.utils.get(ctx.guild.emojis, id=int(emoji_str))
            else:
                return await ctx.warn('Invalid emoji')
        else:
            emoji_obj = emoji

        try:
            await message.add_reaction(emoji_obj)
        except Exception:
            return await ctx.warn('Could not add reaction')

        await self.bot.db_pool.execute('''
            INSERT INTO reactionrole (guild_id, message_id, channel_id, emoji, role_id) 
            VALUES ($1, $2, $3, $4, $5) 
            ON CONFLICT (message_id, emoji) 
            DO UPDATE SET role_id = $5
        ''', ctx.guild.id, message_id, channel_id, emoji_str, role.id)
        await ctx.approve(f'Added reaction role {role.mention} for {emoji}')

    @reactionrole.command(name='remove')
    @commands.has_permissions(manage_roles=True)
    async def reactionrole_remove(self, ctx: Context, message_link: str, emoji: str):
        pattern = r'https://discord\.com/channels/(\d+)/(\d+)/(\d+)'
        match = re.match(pattern, message_link)
        if not match:
            return await ctx.warn('Invalid message link')

        guild_id, channel_id, message_id = map(int, match.groups())
        if guild_id != ctx.guild.id:
            return await ctx.warn('Message must be from this server')

        emoji_str = emoji
        if emoji.startswith('<') and emoji.endswith('>'):
            emoji_id = re.search(r':(\d+)>', emoji)
            if emoji_id:
                emoji_str = emoji_id.group(1)

        result = await self.bot.db_pool.execute(
            'DELETE FROM reactionrole WHERE message_id = $1 AND emoji = $2',
            message_id, emoji_str
        )
        if result == 'DELETE 0':
            return await ctx.warn('No reaction role found')
        await ctx.approve(f'Removed reaction role for {emoji}')

    @reactionrole.command(name='list')
    async def reactionrole_list(self, ctx: Context):
        results = await self.bot.db_pool.fetch(
            'SELECT message_id, channel_id, emoji, role_id FROM reactionrole WHERE guild_id = $1',
            ctx.guild.id
        )
        if not results:
            return await ctx.warn('No reaction roles configured')

        embed = discord.Embed(color=Config.COLORS.DEFAULT, title='Reaction Roles')
        for row in results:
            message_id = row['message_id']
            channel_id = row['channel_id']
            emoji = row['emoji']
            role_id = row['role_id']

            role = ctx.guild.get_role(role_id)
            channel = ctx.guild.get_channel(channel_id)
            emoji_display = emoji if not emoji.isdigit() else f'<:e:{emoji}>'

            embed.add_field(
                name=f'{emoji_display} → {role.mention if role else "Deleted"}',
                value=f'[Message](https://discord.com/channels/{ctx.guild.id}/{channel_id}/{message_id})' if channel else 'Deleted',
                inline=False
            )
        await ctx.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # Prefix
    # ─────────────────────────────────────────────────────────────────────────

    @commands.group(invoke_without_command=True)
    async def prefix(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @prefix.command(name='set')
    @commands.has_permissions(administrator=True)
    async def prefix_set(self, ctx: Context, prefix: str):
        await self.bot.db_pool.execute(
            "INSERT INTO prefixes (guild_id, prefix) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET prefix = $2",
            ctx.guild.id, prefix
        )
        await ctx.approve(f"Prefix changed to `{prefix}`")

    @prefix.command(name='reset')
    @commands.has_permissions(administrator=True)
    async def prefix_reset(self, ctx: Context):
        await self.bot.db_pool.execute("DELETE FROM prefixes WHERE guild_id = $1", ctx.guild.id)
        await ctx.approve("Prefix reset to default")

    # ─────────────────────────────────────────────────────────────────────────
    # Welcome
    # ─────────────────────────────────────────────────────────────────────────

    @commands.group(invoke_without_command=True)
    async def welcome(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @welcome.command(name='enable', aliases=['setup'])
    @commands.has_permissions(manage_guild=True)
    async def welcome_enable(self, ctx: Context):
        result = await self.bot.db_pool.fetchrow('SELECT enabled FROM welcome WHERE guild_id = $1', ctx.guild.id)
        if result and result['enabled']:
            return await ctx.warn('Welcome messages are already enabled')

        await self.bot.db_pool.execute('''
            INSERT INTO welcome (guild_id, enabled) VALUES ($1, $2) 
            ON CONFLICT (guild_id) DO UPDATE SET enabled = $2
        ''', ctx.guild.id, True)
        await ctx.approve('Enabled welcome messages')

    @welcome.command(name='channel')
    @commands.has_permissions(manage_guild=True)
    async def welcome_channel(self, ctx: Context, channel: discord.TextChannel):
        await self.bot.db_pool.execute('''
            INSERT INTO welcome (guild_id, channel_id) VALUES ($1, $2) 
            ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2
        ''', ctx.guild.id, channel.id)
        await ctx.approve(f'Set welcome channel to {channel.mention}')

    @welcome.command(name='message')
    @commands.has_permissions(manage_guild=True)
    async def welcome_message(self, ctx: Context, *, message: str):
        """Set welcome message (supports plain text or JSON for embeds)"""
        # Check if it's JSON
        message = message.strip()
        if message.startswith('```'):
            message = message.strip('`')
            if message.startswith('json'):
                message = message[4:]
            message = message.strip()
        
        # Try to parse as JSON to validate
        try:
            import json
            json.loads(message)
            is_json = True
        except:
            is_json = False
        
        await self.bot.db_pool.execute('''
            INSERT INTO welcome (guild_id, message) VALUES ($1, $2) 
            ON CONFLICT (guild_id) DO UPDATE SET message = $2
        ''', ctx.guild.id, message)
        
        if is_json:
            await ctx.approve('Set welcome message (JSON embed)')
        else:
            await ctx.approve('Set welcome message (plain text)')

    @welcome.command(name='view')
    async def welcome_view(self, ctx: Context):
        result = await self.bot.db_pool.fetchrow(
            'SELECT channel_id, message, enabled FROM welcome WHERE guild_id = $1',
            ctx.guild.id
        )
        if not result:
            return await ctx.warn('No welcome configuration found')

        channel = ctx.guild.get_channel(result['channel_id']) if result['channel_id'] else None

        embed = discord.Embed(color=Config.COLORS.DEFAULT, title='Welcome Configuration')
        embed.add_field(name='Status', value='Enabled' if result['enabled'] else 'Disabled', inline=False)
        embed.add_field(name='Channel', value=channel.mention if channel else 'Not set', inline=False)
        embed.add_field(name='Message', value=result['message'] if result['message'] else 'Not set', inline=False)
        await ctx.send(embed=embed)

    @welcome.command(name='test')
    @commands.has_permissions(manage_guild=True)
    async def welcome_test(self, ctx: Context):
        result = await self.bot.db_pool.fetchrow(
            'SELECT channel_id, message, enabled FROM welcome WHERE guild_id = $1',
            ctx.guild.id
        )
        if not result or not result['channel_id'] or not result['message']:
            return await ctx.warn('Welcome channel and message must be set')

        channel = ctx.guild.get_channel(result['channel_id'])
        if not channel:
            return await ctx.warn('Welcome channel not found')

        formatted = result['message'].replace('{user}', ctx.author.name)
        formatted = formatted.replace('{user.mention}', ctx.author.mention)
        formatted = formatted.replace('{user.id}', str(ctx.author.id))
        formatted = formatted.replace('{server}', ctx.guild.name)
        formatted = formatted.replace('{server.name}', ctx.guild.name)
        formatted = formatted.replace('{server.members}', str(ctx.guild.member_count))

        await channel.send(formatted)
        await ctx.approve(f'Sent test welcome message to {channel.mention}')

    @welcome.command(name='disable', aliases=['reset'])
    @commands.has_permissions(manage_guild=True)
    async def welcome_disable(self, ctx: Context):
        result = await self.bot.db_pool.execute('DELETE FROM welcome WHERE guild_id = $1', ctx.guild.id)
        if result == 'DELETE 0':
            return await ctx.warn('No welcome configuration found')
        await ctx.approve('Disabled and reset welcome messages')

    # ─────────────────────────────────────────────────────────────────────────
    # Boost
    # ─────────────────────────────────────────────────────────────────────────

    @commands.group(invoke_without_command=True)
    async def boost(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @boost.command(name='enable')
    @commands.has_permissions(manage_guild=True)
    async def boost_enable(self, ctx: Context):
        result = await self.bot.db_pool.fetchrow('SELECT enabled FROM boost WHERE guild_id = $1', ctx.guild.id)
        if result and result['enabled']:
            return await ctx.warn('Boost messages are already enabled')

        await self.bot.db_pool.execute('''
            INSERT INTO boost (guild_id, enabled) VALUES ($1, $2) 
            ON CONFLICT (guild_id) DO UPDATE SET enabled = $2
        ''', ctx.guild.id, True)
        await ctx.approve('Enabled boost messages')

    @boost.command(name='channel')
    @commands.has_permissions(manage_guild=True)
    async def boost_channel(self, ctx: Context, channel: discord.TextChannel):
        await self.bot.db_pool.execute('''
            INSERT INTO boost (guild_id, channel_id) VALUES ($1, $2) 
            ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2
        ''', ctx.guild.id, channel.id)
        await ctx.approve(f'Set boost channel to {channel.mention}')

    @boost.command(name='message')
    @commands.has_permissions(manage_guild=True)
    async def boost_message(self, ctx: Context, *, message: str):
        await self.bot.db_pool.execute('''
            INSERT INTO boost (guild_id, message) VALUES ($1, $2) 
            ON CONFLICT (guild_id) DO UPDATE SET message = $2
        ''', ctx.guild.id, message)
        await ctx.approve('Set boost message')

    @boost.command(name='role')
    @commands.has_permissions(manage_guild=True)
    async def boost_role(self, ctx: Context, *, role: discord.Role):
        await self.bot.db_pool.execute('''
            INSERT INTO boost (guild_id, role_id) VALUES ($1, $2) 
            ON CONFLICT (guild_id) DO UPDATE SET role_id = $2
        ''', ctx.guild.id, role.id)
        await ctx.approve(f'Set boost reward role to {role.mention}')

    @boost.command(name='view')
    async def boost_view(self, ctx: Context):
        result = await self.bot.db_pool.fetchrow(
            'SELECT channel_id, message, enabled, role_id FROM boost WHERE guild_id = $1',
            ctx.guild.id
        )
        if not result:
            return await ctx.warn('No boost configuration found')

        channel = ctx.guild.get_channel(result['channel_id']) if result['channel_id'] else None
        role = ctx.guild.get_role(result['role_id']) if result['role_id'] else None

        embed = discord.Embed(color=Config.COLORS.DEFAULT, title='Boost Configuration')
        embed.add_field(name='Status', value='Enabled' if result['enabled'] else 'Disabled', inline=False)
        embed.add_field(name='Channel', value=channel.mention if channel else 'Not set', inline=False)
        embed.add_field(name='Role', value=role.mention if role else 'Not set', inline=False)
        embed.add_field(name='Message', value=result['message'] if result['message'] else 'Not set', inline=False)
        await ctx.send(embed=embed)

    @boost.command(name='disable')
    @commands.has_permissions(manage_guild=True)
    async def boost_disable(self, ctx: Context):
        result = await self.bot.db_pool.execute('DELETE FROM boost WHERE guild_id = $1', ctx.guild.id)
        if result == 'DELETE 0':
            return await ctx.warn('No boost configuration found')
        await ctx.approve('Disabled and reset boost messages')

    # ─────────────────────────────────────────────────────────────────────────
    # Autoresponder
    # ─────────────────────────────────────────────────────────────────────────

    @commands.group(invoke_without_command=True)
    async def autoresponder(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @autoresponder.command(name='add')
    @commands.has_permissions(manage_guild=True)
    async def autoresponder_add(self, ctx: Context, *, args: str):
        flags = []
        if '--not_strict' in args:
            flags.append('--not_strict')
            args = args.replace('--not_strict', '')
        if '--reply' in args:
            flags.append('--reply')
            args = args.replace('--reply', '')

        args = args.strip()
        if ',' not in args:
            return await ctx.deny('Invalid format. Use: `autoresponder add trigger, response`')

        trigger, response = args.split(',', 1)
        trigger = trigger.strip()
        response = response.strip()

        strict = '--not_strict' not in flags
        reply = '--reply' in flags

        await self.bot.db_pool.execute('''
            INSERT INTO autoresponder (guild_id, trigger_text, response, strict, reply) 
            VALUES ($1, $2, $3, $4, $5) 
            ON CONFLICT (guild_id, trigger_text) 
            DO UPDATE SET response = $3, strict = $4, reply = $5
        ''', ctx.guild.id, trigger, response, strict, reply)
        await ctx.approve(f'Added autoresponder for `{trigger}`')

    @autoresponder.command(name='remove')
    @commands.has_permissions(manage_guild=True)
    async def autoresponder_remove(self, ctx: Context, trigger: str):
        result = await self.bot.db_pool.execute(
            'DELETE FROM autoresponder WHERE guild_id = $1 AND trigger_text = $2',
            ctx.guild.id, trigger
        )
        if result == 'DELETE 0':
            return await ctx.warn('No autoresponder found for that trigger')
        await ctx.approve(f'Removed autoresponder for `{trigger}`')

    @autoresponder.command(name='list')
    async def autoresponder_list(self, ctx: Context):
        results = await self.bot.db_pool.fetch(
            'SELECT trigger_text, response, strict, reply FROM autoresponder WHERE guild_id = $1',
            ctx.guild.id
        )
        if not results:
            return await ctx.warn('No autoresponders configured')

        embed = discord.Embed(color=Config.COLORS.DEFAULT, title='Autoresponders')
        for row in results:
            flags = []
            if not row['strict']:
                flags.append('not strict')
            if row['reply']:
                flags.append('reply')
            flag_text = f' ({", ".join(flags)})' if flags else ''
            embed.add_field(name=f'`{row["trigger_text"]}`{flag_text}', value=row['response'][:100], inline=False)
        await ctx.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # Customize
    # ─────────────────────────────────────────────────────────────────────────

    @commands.group(name="customize", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def customize(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @customize.command(name="banner")
    @commands.has_permissions(administrator=True)
    async def customize_banner(self, ctx: Context, image_url: str = None):
        if ctx.message.attachments:
            image_url = ctx.message.attachments[0].url
        elif not image_url:
            return await ctx.deny("You're missing a **url** or **attachment**")

        loading_msg = await ctx.loading("Getting the **banner**...")
        data_uri = await self.download_to_data_uri(image_url)
        if not data_uri:
            await loading_msg.delete()
            return await ctx.deny("Could not **download** the banner.")

        payload = {"banner": data_uri}
        url = f"https://discord.com/api/v10/guilds/{ctx.guild.id}/members/@me"
        headers = {
            "Authorization": f"Bot {self.bot.http.token}",
            "Content-Type": "application/json",
            "X-Audit-Log-Reason": f"Updating bot server banner - by {ctx.author}"
        }

        async with aiohttp.ClientSession() as session:
            async with session.patch(url, headers=headers, json=payload) as resp:
                await loading_msg.delete()
                if resp.status == 200:
                    await ctx.approve("Successfully updated the **banner**.")
                else:
                    await ctx.deny("Failed to update the **banner**.")

    @customize.command(name="pfp", aliases=['avatar'])
    @commands.has_permissions(administrator=True)
    async def customize_pfp(self, ctx: Context, image_url: str = None):
        if ctx.message.attachments:
            image_url = ctx.message.attachments[0].url
        elif not image_url:
            return await ctx.deny("You're missing a **url** or **attachment**")

        loading_msg = await ctx.loading("Getting the **avatar**...")
        data_uri = await self.download_to_data_uri(image_url)
        if not data_uri:
            await loading_msg.delete()
            return await ctx.deny("Could not **download** the avatar.")

        payload = {"avatar": data_uri}
        url = f"https://discord.com/api/v10/guilds/{ctx.guild.id}/members/@me"
        headers = {
            "Authorization": f"Bot {self.bot.http.token}",
            "Content-Type": "application/json",
            "X-Audit-Log-Reason": f"Updating bot server avatar - by {ctx.author}"
        }

        async with aiohttp.ClientSession() as session:
            async with session.patch(url, headers=headers, json=payload) as resp:
                await loading_msg.delete()
                if resp.status == 200:
                    await ctx.approve("Successfully updated the **avatar**.")
                else:
                    await ctx.deny("Failed to update the **avatar**.")

    @customize.command(name="bio")
    @commands.has_permissions(administrator=True)
    async def customize_bio(self, ctx: Context, *, text: str = None):
        if not text:
            return await ctx.deny("You're missing a **bio**")

        loading_msg = await ctx.loading("Updating the **bio**...")
        payload = {"bio": text}
        url = f"https://discord.com/api/v10/guilds/{ctx.guild.id}/members/@me"
        headers = {
            "Authorization": f"Bot {self.bot.http.token}",
            "Content-Type": "application/json",
            "X-Audit-Log-Reason": f"Updating bot server bio - by {ctx.author}"
        }

        async with aiohttp.ClientSession() as session:
            async with session.patch(url, headers=headers, json=payload) as resp:
                await loading_msg.delete()
                if resp.status == 200:
                    await ctx.approve("Successfully updated the **bio**.")
                else:
                    await ctx.deny("Failed to update the **bio**.")

    @customize.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def customize_reset(self, ctx: Context):
        loading_msg = await ctx.loading("Resetting customization...")
        payload = {"avatar": None, "banner": None, "bio": ""}
        url = f"https://discord.com/api/v10/guilds/{ctx.guild.id}/members/@me"
        headers = {
            "Authorization": f"Bot {self.bot.http.token}",
            "Content-Type": "application/json",
            "X-Audit-Log-Reason": f"Resetting bot customization - by {ctx.author}"
        }

        async with aiohttp.ClientSession() as session:
            async with session.patch(url, headers=headers, json=payload) as resp:
                await loading_msg.delete()
                if resp.status == 200:
                    await ctx.approve("Successfully reset customization.")
                else:
                    await ctx.deny("Failed to reset customization.")

    # ─────────────────────────────────────────────────────────────────────────
    # Counting
    # ─────────────────────────────────────────────────────────────────────────

    @commands.group(invoke_without_command=True)
    async def counting(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @counting.command(name='setup')
    @commands.has_permissions(manage_guild=True)
    async def counting_setup(self, ctx: Context, channel: discord.TextChannel):
        await self.bot.db_pool.execute(
            "INSERT INTO counting (guild_id, channel_id, current_count, block_words) VALUES ($1, $2, 0, true) ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2",
            ctx.guild.id, channel.id
        )
        try:
            await channel.edit(topic="Next number: 1")
        except Exception:
            pass
        await ctx.approve(f"Counting channel set to {channel.mention}")

    @counting.command(name='reset')
    @commands.has_permissions(manage_guild=True)
    async def counting_reset(self, ctx: Context):
        await self.bot.db_pool.execute("DELETE FROM counting WHERE guild_id = $1", ctx.guild.id)
        await ctx.approve("Counting disabled")

    @counting.command(name='reaction')
    @commands.has_permissions(manage_guild=True)
    async def counting_reaction(self, ctx: Context, emoji: str):
        """Set a custom reaction for correct counts"""
        row = await self.bot.db_pool.fetchrow(
            "SELECT channel_id FROM counting WHERE guild_id = $1", ctx.guild.id
        )
        if not row:
            return await ctx.deny("Counting is not set up in this server!")

        await self.bot.db_pool.execute(
            "UPDATE counting SET reaction = $1 WHERE guild_id = $2",
            emoji, ctx.guild.id
        )
        await ctx.approve(f"Counting reaction set to {emoji}")

    # ─────────────────────────────────────────────────────────────────────────
    # Tickets
    # ─────────────────────────────────────────────────────────────────────────

    @commands.group(invoke_without_command=True, aliases=['ticket', 't'])
    async def tickets(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @tickets.command(name='support', aliases=['supporters'])
    @commands.has_permissions(administrator=True)
    async def tickets_support(self, ctx: Context, *roles: discord.Role):
        """Configure which roles can claim tickets.

        Usage:
        - tickets support              -> show current supporter roles
        - tickets support @Role1 ...   -> add one or more supporter roles
        """
        if not ctx.guild:
            return await ctx.warn("This command can only be used in a server.")

        if not roles:
            rows = await self.bot.db_pool.fetch(
                "SELECT role_id FROM ticket_support_roles WHERE guild_id = $1",
                ctx.guild.id,
            )
            if not rows:
                return await ctx.warn(
                    "No **ticket supporter** roles are configured yet.\n"
                    "Use `tickets support @Role` to add some."
                )

            role_mentions = []
            for row in rows:
                role = ctx.guild.get_role(row["role_id"])
                if role:
                    role_mentions.append(role.mention)

            if not role_mentions:
                return await ctx.warn(
                    "No valid ticket supporter roles found. They may have been deleted."
                )

            return await ctx.approve(
                "Current **ticket supporter** roles:\n" + ", ".join(role_mentions)
            )

        added = []
        for role in roles:
            await self.bot.db_pool.execute(
                """
                INSERT INTO ticket_support_roles (guild_id, role_id)
                VALUES ($1, $2)
                ON CONFLICT (guild_id, role_id) DO NOTHING
                """,
                ctx.guild.id,
                role.id,
            )
            added.append(role.mention)

        return await ctx.approve(
            f"Added ticket supporter role(s): {', '.join(added)}"
        )

    @tickets.command(name='setup', aliases=['s'])
    @commands.has_permissions(administrator=True)
    async def tickets_setup(self, ctx: Context, *, args: str):
        if not ctx.message.channel_mentions:
            return await ctx.warn(
                'Please mention a channel at the end of your message.\n'
                '**Syntax:** `tickets setup <message> #channel`'
            )

        channel = ctx.message.channel_mentions[0]
        message_text = args.replace(channel.mention, '').strip()

        if not message_text:
            return await ctx.warn('Please provide a message for the embed.')

        setup_embed = discord.Embed(description=f'**{message_text}**')
        setup_embed.set_author(
            name=ctx.guild.name,
            icon_url=ctx.guild.icon.url if ctx.guild.icon else None,
        )
        setup_embed.set_footer(text='Click on the button below to create a ticket.')

        existing = await self.bot.db_pool.fetchrow(
            'SELECT channel_id, message_id FROM tickets WHERE guild_id = $1', ctx.guild.id
        )

        panel_edited = False
        if existing and existing['channel_id'] and existing['message_id']:
            try:
                existing_channel = ctx.guild.get_channel(existing['channel_id'])
                if existing_channel:
                    existing_msg = await existing_channel.fetch_message(existing['message_id'])
                    await existing_msg.edit(embed=setup_embed, view=TicketSetupView(self.bot))
                    panel_edited = True
            except (discord.NotFound, discord.Forbidden):
                pass

        if not panel_edited:
            panel = await channel.send(embed=setup_embed, view=TicketSetupView(self.bot))
            await self.bot.db_pool.execute(
                'INSERT INTO tickets (guild_id, channel_id, message_id) VALUES ($1, $2, $3) ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2, message_id = $3',
                ctx.guild.id, channel.id, panel.id
            )
        else:
            await self.bot.db_pool.execute(
                'INSERT INTO tickets (guild_id, channel_id, message_id) VALUES ($1, $2, $3) ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2, message_id = $3',
                ctx.guild.id, existing['channel_id'], existing['message_id']
            )

        existing_category = discord.utils.get(ctx.guild.categories, name='Tickets')
        if not existing_category:
            overwrites = {ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False)}
            await ctx.guild.create_category('Tickets', overwrites=overwrites)

        if panel_edited:
            await ctx.approve(f'Updated the existing ticket panel.')
        else:
            await ctx.approve(f'Ticket system has been set up in {channel.mention}.')

    @tickets.command(name='transcript')
    @commands.has_permissions(administrator=True)
    async def tickets_transcript(self, ctx: Context, channel: discord.TextChannel):
        await self.bot.db_pool.execute(
            'INSERT INTO tickets (guild_id, transcript_channel_id) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET transcript_channel_id = $2',
            ctx.guild.id, channel.id
        )
        await ctx.approve(f'Ticket transcripts will be sent to {channel.mention}')

    @tickets.command(name='close', aliases=['c'])
    async def tickets_close(self, ctx: Context):
        channel = ctx.channel
        category = channel.category

        if not category or category.name != 'Tickets':
            return await ctx.warn('This command can only be used inside a ticket channel.')

        if not channel.name.startswith('ticket-'):
            return await ctx.warn('This command can only be used inside an open ticket channel.')

        await ctx.send(
            embed=discord.Embed(
                description=f"{Config.EMOJIS.WARNING} {ctx.author.mention}: Are you **sure** you want to close this **ticket**?",
                color=Config.COLORS.WARNING
            ),
            view=TicketCloseConfirmView(self.bot)
        )

    @tickets.command(name='delete', aliases=['d'])
    @commands.has_permissions(manage_channels=True)
    async def tickets_delete(self, ctx: Context):
        channel = ctx.channel
        category = channel.category

        if not category or category.name != 'Tickets':
            return await ctx.warn('This command can only be used inside a ticket channel.')

        if not (channel.name.startswith('ticket-') or channel.name.startswith('closed-')):
            return await ctx.warn('This command can only be used inside a ticket channel.')

        await ctx.send(
            embed=discord.Embed(
                description=f"{Config.EMOJIS.WARNING} {ctx.author.mention}: Are you **sure** you want to delete this **ticket**?",
                color=Config.COLORS.WARNING
            ),
            view=TicketDeleteConfirmView(self.bot)
        )

    @tickets.command(name='remove', aliases=['reset'])
    @commands.has_permissions(administrator=True)
    async def tickets_remove(self, ctx: Context):
        result = await self.bot.db_pool.fetchrow(
            'SELECT channel_id, message_id FROM tickets WHERE guild_id = $1', ctx.guild.id
        )

        await self.bot.db_pool.execute('DELETE FROM tickets WHERE guild_id = $1', ctx.guild.id)

        if result and result['channel_id'] and result['message_id']:
            panel_channel = ctx.guild.get_channel(result['channel_id'])
            if panel_channel:
                try:
                    panel_message = await panel_channel.fetch_message(result['message_id'])
                    await panel_message.delete()
                except Exception:
                    pass

        category = discord.utils.get(ctx.guild.categories, name='Tickets')
        if category:
            for ch in list(category.channels):
                try:
                    await ch.delete(reason=f'Ticket config reset by {ctx.author}')
                except Exception:
                    pass
            try:
                await category.delete(reason=f'Ticket config reset by {ctx.author}')
            except Exception:
                pass

        await ctx.approve("**I've** reset the **current** ticket configuration for this server.")

    # ─────────────────────────────────────────────────────────────────────────
    # Confessions
    # ─────────────────────────────────────────────────────────────────────────

    @commands.group(
        name="confessions",
        aliases=["confess", "confession"],
        invoke_without_command=True
    )
    async def confessions(self, ctx: Context, *, message: str = None):
        """Submit an anonymous confession."""
        if message is None:
            return await ctx.send_help(ctx.command)
        await _submit_confession(self.bot, ctx, message)

    @confessions.command(name='setup')
    @commands.has_permissions(manage_guild=True)
    async def confessions_setup(self, ctx: Context, channel: discord.TextChannel):
        """Set the confessions channel."""
        await self.bot.db_pool.execute("""
            INSERT INTO confession_config (guild_id, channel_id, confession_count, last_message_id)
            VALUES ($1, $2, 0, NULL)
            ON CONFLICT (guild_id) DO UPDATE SET channel_id = $2, last_message_id = NULL
        """, ctx.guild.id, channel.id)
        await ctx.approve(f"**I've** setup **confessions** in {channel.mention}")

    @confessions.command(name='reset', aliases=['disable', 'remove'])
    @commands.has_permissions(manage_guild=True)
    async def confessions_reset(self, ctx: Context):
        """Reset confessions in this server."""
        existing = await self.bot.db_pool.fetchrow(
            'SELECT 1 FROM confession_config WHERE guild_id = $1', ctx.guild.id
        )
        if not existing:
            return await ctx.warn("**Confessions** aren't setup in this server!")
        await self.bot.db_pool.execute(
            'DELETE FROM confession_config WHERE guild_id = $1', ctx.guild.id
        )
        await self.bot.db_pool.execute(
            'DELETE FROM confession_blacklist WHERE guild_id = $1', ctx.guild.id
        )
        await ctx.approve("**I've** successfully reset **confessions** in this server.")

    @confessions.command(name='blacklist')
    @commands.has_permissions(manage_guild=True)
    async def confessions_blacklist(self, ctx: Context, *, word: str):
        """Blacklist a word from confessions."""
        existing = await self.bot.db_pool.fetchrow(
            'SELECT 1 FROM confession_blacklist WHERE guild_id = $1 AND word = $2',
            ctx.guild.id, word.lower()
        )
        if existing:
            return await ctx.warn(f"**{word}** is already blacklisted.")

        await self.bot.db_pool.execute(
            'INSERT INTO confession_blacklist (guild_id, word) VALUES ($1, $2)',
            ctx.guild.id, word.lower()
        )
        await ctx.approve(f"**{word}** has been added to the confessions blacklist.")

    # ─────────────────────────────────────────────────────────────────────────
    # Alias
    # ─────────────────────────────────────────────────────────────────────────

    @commands.group(invoke_without_command=True)
    async def alias(self, ctx: Context):
        """Manage custom command aliases for this server"""
        await ctx.send_help(ctx.command)

    @alias.command(name='add')
    @commands.has_permissions(manage_guild=True)
    async def alias_add(self, ctx: Context, alias: str, *, command: str):
        existing = await self.bot.db_pool.fetchrow(
            'SELECT command FROM aliases WHERE guild_id = $1 AND alias = $2',
            ctx.guild.id, alias.lower()
        )

        if existing:
            return await ctx.warn(f'Alias `{alias}` already exists for command `{existing["command"]}`')

        cmd = self.bot.get_command(command)
        if not cmd:
            return await ctx.warn(f'Command `{command}` does not exist')

        await self.bot.db_pool.execute(
            'INSERT INTO aliases (guild_id, alias, command) VALUES ($1, $2, $3)',
            ctx.guild.id, alias.lower(), command
        )
        await ctx.approve(f'Added alias `{alias}` for command `{command}`')

    @alias.command(name='remove', aliases=['delete', 'del'])
    @commands.has_permissions(manage_guild=True)
    async def alias_remove(self, ctx: Context, alias: str):
        result = await self.bot.db_pool.execute(
            'DELETE FROM aliases WHERE guild_id = $1 AND alias = $2',
            ctx.guild.id, alias.lower()
        )

        if result == 'DELETE 0':
            return await ctx.warn(f'Alias `{alias}` does not exist')

        await ctx.approve(f'Removed alias `{alias}`')

    @alias.command(name='list')
    async def alias_list(self, ctx: Context):
        results = await self.bot.db_pool.fetch(
            'SELECT alias, command FROM aliases WHERE guild_id = $1 ORDER BY alias',
            ctx.guild.id
        )

        if not results:
            return await ctx.warn('No custom aliases configured')

        embed = discord.Embed(color=Config.COLORS.DEFAULT, title=f'Custom Aliases ({len(results)})')
        for row in results:
            embed.add_field(name=f'`{row["alias"]}`', value=f'→ `{row["command"]}`', inline=True)

        await ctx.send(embed=embed)

    @alias.command(name='clear')
    @commands.has_permissions(administrator=True)
    async def alias_clear(self, ctx: Context):
        result = await self.bot.db_pool.execute('DELETE FROM aliases WHERE guild_id = $1', ctx.guild.id)

        count = int(result.split()[-1])
        if count == 0:
            return await ctx.warn('No aliases to clear')

        await ctx.approve(f'Cleared {count} alias(es)')

    # ─────────────────────────────────────────────────────────────────────────
    # Vanity
    # ─────────────────────────────────────────────────────────────────────────

    @commands.group(invoke_without_command=True)
    async def vanity(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @vanity.command(name='setup')
    @commands.has_permissions(manage_guild=True)
    async def vanity_setup(self, ctx: Context, keyword: str, role: discord.Role = None, channel: discord.TextChannel = None, emoji: str = None, *, message: str = None):
        existing = await self.bot.db_pool.fetchrow(
            'SELECT guild_id FROM vanity_rewards WHERE guild_id = $1', ctx.guild.id
        )

        role_id = role.id if role else None
        channel_id = channel.id if channel else None

        if existing:
            await self.bot.db_pool.execute(
                'UPDATE vanity_rewards SET keyword = $2, role_id = $3, channel_id = $4, message = $5, emoji = $6 WHERE guild_id = $1',
                ctx.guild.id, keyword.lower(), role_id, channel_id, message, emoji
            )
        else:
            await self.bot.db_pool.execute(
                'INSERT INTO vanity_rewards (guild_id, keyword, role_id, channel_id, message, emoji) VALUES ($1, $2, $3, $4, $5, $6)',
                ctx.guild.id, keyword.lower(), role_id, channel_id, message, emoji
            )

        response_parts = [f'Vanity detection setup for keyword `{keyword}`']
        if role:
            response_parts.append(f'Users will get {role.mention}')
        if emoji:
            response_parts.append(f'Reaction: {emoji}')
        if channel and message:
            response_parts.append(f'Message will be sent to {channel.mention}')

        await ctx.approve(' • '.join(response_parts))

    @vanity.command(name='remove', aliases=['disable'])
    @commands.has_permissions(manage_guild=True)
    async def vanity_remove(self, ctx: Context):
        result = await self.bot.db_pool.execute('DELETE FROM vanity_rewards WHERE guild_id = $1', ctx.guild.id)
        if result == 'DELETE 0':
            return await ctx.warn('No vanity rewards configured')
        await ctx.approve('Removed vanity rewards')

    @vanity.command(name='view')
    async def vanity_view(self, ctx: Context):
        result = await self.bot.db_pool.fetchrow(
            'SELECT keyword, role_id, channel_id, message, emoji FROM vanity_rewards WHERE guild_id = $1',
            ctx.guild.id
        )

        if not result:
            return await ctx.warn('No vanity rewards configured')

        role = ctx.guild.get_role(result['role_id']) if result['role_id'] else None
        channel = ctx.guild.get_channel(result['channel_id']) if result['channel_id'] else None

        embed = discord.Embed(color=Config.COLORS.DEFAULT, title='Vanity Rewards Configuration')
        embed.add_field(name='Keyword', value=f'`{result["keyword"]}`', inline=False)
        embed.add_field(name='Role', value=role.mention if role else 'Not set', inline=True)
        embed.add_field(name='Channel', value=channel.mention if channel else 'Not set', inline=True)
        embed.add_field(name='Emoji', value=result['emoji'] if result.get('emoji') else 'Not set', inline=True)
        embed.add_field(name='Message', value=result['message'] if result['message'] else 'Not set', inline=False)

        await ctx.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # Bump Reminder
    # ─────────────────────────────────────────────────────────────────────────

    @commands.group(invoke_without_command=True)
    async def bumpreminder(self, ctx: Context):
        await ctx.send_help(ctx.command)

    @bumpreminder.command(name='setup')
    @commands.has_permissions(manage_guild=True)
    async def bumpreminder_setup(self, ctx: Context, channel: discord.TextChannel, role: discord.Role = None, *, message: str = None):
        if not message:
            message = "{role} It's time to bump the server!"

        role_id = role.id if role else None

        await self.bot.db_pool.execute('''
            INSERT INTO bumpreminder (guild_id, channel_id, role_id, message) 
            VALUES ($1, $2, $3, $4) 
            ON CONFLICT (guild_id) 
            DO UPDATE SET channel_id = $2, role_id = $3, message = $4
        ''', ctx.guild.id, channel.id, role_id, message)

        response = f'Bump reminders will be sent to {channel.mention}'
        if role:
            response += f' pinging {role.mention}'
        await ctx.approve(response)

    @bumpreminder.command(name='disable')
    @commands.has_permissions(manage_guild=True)
    async def bumpreminder_disable(self, ctx: Context):
        result = await self.bot.db_pool.execute('DELETE FROM bumpreminder WHERE guild_id = $1', ctx.guild.id)

        if result == 'DELETE 0':
            return await ctx.warn('No bump reminder configured')

        if ctx.guild.id in self.bump_timers:
            self.bump_timers[ctx.guild.id].cancel()
            del self.bump_timers[ctx.guild.id]

        await ctx.approve('Disabled bump reminders')

    @bumpreminder.command(name='view')
    async def bumpreminder_view(self, ctx: Context):
        result = await self.bot.db_pool.fetchrow(
            'SELECT channel_id, role_id, message FROM bumpreminder WHERE guild_id = $1',
            ctx.guild.id
        )

        if not result:
            return await ctx.warn('No bump reminder configured')

        channel = ctx.guild.get_channel(result['channel_id']) if result['channel_id'] else None
        role = ctx.guild.get_role(result['role_id']) if result['role_id'] else None

        embed = discord.Embed(color=Config.COLORS.DEFAULT, title='Bump Reminder Configuration')
        embed.add_field(name='Channel', value=channel.mention if channel else 'Not set', inline=False)
        embed.add_field(name='Role', value=role.mention if role else 'Not set', inline=False)
        embed.add_field(name='Message', value=result['message'] if result['message'] else 'Not set', inline=False)

        await ctx.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # Listeners
    # ─────────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        if not interaction.data:
            return
        if interaction.data.get("custom_id") != "confess_submit_btn":
            return
        await interaction.response.send_modal(ConfessionModal(self.bot))

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        role_type = 'bots' if member.bot else 'humans'
        try:
            result = await self.bot.db_pool.fetchrow(
                'SELECT role_id FROM autorole WHERE guild_id = $1 AND type = $2',
                member.guild.id, role_type
            )
            if result:
                role = member.guild.get_role(result['role_id'])
                if role:
                    await member.add_roles(role)
        except Exception:
            pass

        try:
            welcome_data = await self.bot.db_pool.fetchrow(
                'SELECT channel_id, message, enabled FROM welcome WHERE guild_id = $1',
                member.guild.id
            )
            if welcome_data and welcome_data['enabled'] and welcome_data['channel_id'] and welcome_data['message']:
                channel = member.guild.get_channel(welcome_data['channel_id'])
                if channel and isinstance(channel, discord.TextChannel):
                    message_content = welcome_data['message']
                    
                    # Replace variables
                    message_content = message_content.replace('{user}', member.name)
                    message_content = message_content.replace('{user.mention}', member.mention)
                    message_content = message_content.replace('{user.id}', str(member.id))
                    message_content = message_content.replace('{server}', member.guild.name)
                    message_content = message_content.replace('{server.name}', member.guild.name)
                    message_content = message_content.replace('{server.members}', str(member.guild.member_count))
                    
                    # Try to parse as JSON for embed
                    try:
                        import json
                        data = json.loads(message_content)
                        
                        # Check if it's a full Discord message format with embeds array
                        if 'embeds' in data and isinstance(data['embeds'], list):
                            embeds = []
                            for embed_data in data['embeds']:
                                embed = self._create_embed_from_data(embed_data)
                                embeds.append(embed)
                            
                            # Handle components (buttons) if present
                            view = None
                            if 'components' in data:
                                view = self._create_view_from_components(data['components'])
                            
                            if embeds:
                                await channel.send(embeds=embeds, view=view)
                        else:
                            # Single embed format
                            embed = self._create_embed_from_data(data)
                            await channel.send(embed=embed)
                    except:
                        # Not JSON, send as plain text
                        await channel.send(message_content)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_boost(self, member: discord.Member):
        try:
            boost_data = await self.bot.db_pool.fetchrow(
                'SELECT channel_id, message, enabled, role_id FROM boost WHERE guild_id = $1',
                member.guild.id
            )
            if boost_data and boost_data['enabled']:
                if boost_data['role_id']:
                    role = member.guild.get_role(boost_data['role_id'])
                    if role and role not in member.roles:
                        try:
                            await member.add_roles(role, reason='User boosted the server')
                        except Exception:
                            pass

                if boost_data['channel_id'] and boost_data['message']:
                    channel = member.guild.get_channel(boost_data['channel_id'])
                    if channel and isinstance(channel, discord.TextChannel):
                        formatted = boost_data['message'].replace('{user}', member.name)
                        formatted = formatted.replace('{user.mention}', member.mention)
                        formatted = formatted.replace('{user.id}', str(member.id))
                        formatted = formatted.replace('{server}', member.guild.name)
                        formatted = formatted.replace('{server.name}', member.guild.name)
                        formatted = formatted.replace('{server.boosts}', str(member.guild.premium_subscription_count))
                        await channel.send(formatted)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if before.bot or after.bot:
            return
        if before.activities == after.activities:
            return

        try:
            vanity_config = await self.bot.db_pool.fetchrow(
                'SELECT keyword, role_id, channel_id, message, emoji FROM vanity_rewards WHERE guild_id = $1',
                after.guild.id
            )
            if not vanity_config:
                return

            keyword = vanity_config['keyword'].lower()
            role = None
            if vanity_config['role_id']:
                role = after.guild.get_role(vanity_config['role_id'])
                if role and role in after.roles:
                    return

            has_keyword = False
            for activity in after.activities:
                if hasattr(activity, 'name') and activity.name and keyword in activity.name.lower():
                    has_keyword = True
                    break
                if hasattr(activity, 'state') and activity.state and keyword in activity.state.lower():
                    has_keyword = True
                    break

            if has_keyword:
                if role:
                    await after.add_roles(role, reason=f'Vanity reward: has "{keyword}" in status')

                sent_message = None
                if vanity_config['channel_id'] and vanity_config['message']:
                    channel = after.guild.get_channel(vanity_config['channel_id'])
                    if channel:
                        formatted_message = vanity_config['message'].replace('{user}', after.name)
                        formatted_message = formatted_message.replace('{user.mention}', after.mention)
                        if role:
                            formatted_message = formatted_message.replace('{role}', role.name)
                            formatted_message = formatted_message.replace('{role.mention}', role.mention)
                        sent_message = await channel.send(formatted_message)

                if vanity_config.get('emoji') and sent_message:
                    try:
                        await sent_message.add_reaction(vanity_config['emoji'])
                    except Exception:
                        pass
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.bot or after.bot:
            return
        if before.nick == after.nick:
            return

        try:
            vanity_config = await self.bot.db_pool.fetchrow(
                'SELECT keyword, role_id, channel_id, message, emoji FROM vanity_rewards WHERE guild_id = $1',
                after.guild.id
            )
            if not vanity_config:
                return

            keyword = vanity_config['keyword'].lower()
            role = None
            if vanity_config['role_id']:
                role = after.guild.get_role(vanity_config['role_id'])
                if role and role in after.roles:
                    return

            if after.nick and keyword in after.nick.lower():
                if role:
                    await after.add_roles(role, reason=f'Vanity reward: has "{keyword}" in nickname')

                sent_message = None
                if vanity_config['channel_id'] and vanity_config['message']:
                    channel = after.guild.get_channel(vanity_config['channel_id'])
                    if channel:
                        formatted_message = vanity_config['message'].replace('{user}', after.name)
                        formatted_message = formatted_message.replace('{user.mention}', after.mention)
                        if role:
                            formatted_message = formatted_message.replace('{role}', role.name)
                            formatted_message = formatted_message.replace('{role.mention}', role.mention)
                        sent_message = await channel.send(formatted_message)

                if vanity_config.get('emoji') and sent_message:
                    try:
                        await sent_message.add_reaction(vanity_config['emoji'])
                    except Exception:
                        pass
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        if message.author.bot:
            if message.author.id == 302050872383242240 and self.bot.db_pool:  # Disboard
                if message.embeds and 'Bump done!' in message.embeds[0].description:
                    config = await self.bot.db_pool.fetchrow(
                        'SELECT channel_id, role_id, message FROM bumpreminder WHERE guild_id = $1',
                        message.guild.id
                    )

                    if config:
                        if message.guild.id in self.bump_timers:
                            self.bump_timers[message.guild.id].cancel()

                        async def send_reminder():
                            await discord.utils.sleep_until(datetime.now() + timedelta(hours=2))
                            channel = message.guild.get_channel(config['channel_id'])
                            if channel:
                                role = message.guild.get_role(config['role_id']) if config['role_id'] else None
                                formatted_message = config['message'].replace('{role}', role.mention if role else '')
                                allowed_mentions = discord.AllowedMentions(roles=[role]) if role else discord.AllowedMentions.none()
                                await channel.send(formatted_message, allowed_mentions=allowed_mentions)

                            if message.guild.id in self.bump_timers:
                                del self.bump_timers[message.guild.id]

                        task = self.bot.loop.create_task(send_reminder())
                        self.bump_timers[message.guild.id] = task
            return

        if message.guild and self.bot.db_pool:
            results = await self.bot.db_pool.fetch(
                'SELECT trigger_text, response, strict, reply FROM autoresponder WHERE guild_id = $1',
                message.guild.id
            )
            for row in results:
                content = message.content.lower()
                if row['strict'] and content == row['trigger_text'].lower():
                    if row['reply']:
                        await message.reply(row['response'], mention_author=False)
                    else:
                        await message.channel.send(row['response'])
                    break
                elif not row['strict'] and row['trigger_text'].lower() in content:
                    if row['reply']:
                        await message.reply(row['response'], mention_author=False)
                    else:
                        await message.channel.send(row['response'])
                    break

            row = await self.bot.db_pool.fetchrow(
                "SELECT * FROM counting WHERE guild_id = $1 AND channel_id = $2",
                message.guild.id, message.channel.id
            )
            if row:
                count = row['current_count']
                last_user = row.get('last_user')
                reaction = row.get('reaction', '✅')

                if message.author.id == last_user:
                    await message.delete()
                    return

                content = message.content.strip()
                if row['block_words'] and not content.isdigit():
                    await message.delete()
                    return

                try:
                    number = int(content.split()[0])
                except Exception:
                    await message.delete()
                    return

                if number == count + 1:
                    await message.add_reaction(reaction)
                    await self.bot.db_pool.execute(
                        "UPDATE counting SET current_count = $1, last_user = $2 WHERE guild_id = $3",
                        number, message.author.id, message.guild.id
                    )
                    try:
                        await message.channel.edit(topic=f"Next number: {number + 1}")
                    except Exception:
                        pass
                else:
                    await message.delete()
                    await message.channel.send(
                        f"{message.author.mention} ruined it at **{count}**! Next number is **1**"
                    )
                    await self.bot.db_pool.execute(
                        "UPDATE counting SET current_count = 0, last_user = NULL WHERE guild_id = $1",
                        message.guild.id
                    )
                    try:
                        await message.channel.edit(topic="Next number: 1")
                    except Exception:
                        pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.member.bot:
            return

        emoji_str = str(payload.emoji.id) if payload.emoji.is_custom_emoji() else payload.emoji.name
        result = await self.bot.db_pool.fetchrow(
            'SELECT role_id FROM reactionrole WHERE message_id = $1 AND emoji = $2',
            payload.message_id, emoji_str
        )
        if result:
            guild = self.bot.get_guild(payload.guild_id)
            role = guild.get_role(result['role_id'])
            if role:
                try:
                    await payload.member.add_roles(role)
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        emoji_str = str(payload.emoji.id) if payload.emoji.is_custom_emoji() else payload.emoji.name
        result = await self.bot.db_pool.fetchrow(
            'SELECT role_id FROM reactionrole WHERE message_id = $1 AND emoji = $2',
            payload.message_id, emoji_str
        )
        if result:
            guild = self.bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            role = guild.get_role(result['role_id'])
            if role and member:
                try:
                    await member.remove_roles(role)
                except Exception:
                    pass
    
    @commands.group(name="starboard", aliases=["star", "board"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def starboard(self, ctx: Context):
        return await ctx.send_help(ctx.command)
    
    @starboard.command(name="add", aliases=["create"])
    @commands.has_permissions(manage_guild=True)
    async def starboard_add(self, ctx: Context, channel: discord.TextChannel, emoji: str, threshold: int = 3, self_star: bool = True):
        try:
            await ctx.message.add_reaction(emoji)
        except (discord.HTTPException, TypeError):
            return await ctx.warn(f"I'm not able to use **{emoji}**, try using an emoji from this server")
        
        await self.bot.db_pool.execute("""
            INSERT INTO starboard VALUES ($1, $2, $3, $4, $5, NULL, TRUE)
            ON CONFLICT (guild_id, emoji) DO UPDATE
            SET channel_id = EXCLUDED.channel_id,
                self_star = EXCLUDED.self_star,
                threshold = EXCLUDED.threshold
        """, ctx.guild.id, channel.id, self_star, threshold, emoji)
        
        return await ctx.approve(f"Added a starboard for {emoji} in {channel.mention}")
    
    @starboard.command(name="remove", aliases=["delete", "del", "rm"])
    @commands.has_permissions(manage_guild=True)
    async def starboard_remove(self, ctx: Context, channel: discord.TextChannel, emoji: str):
        result = await self.bot.db_pool.execute("""
            DELETE FROM starboard
            WHERE guild_id = $1 AND channel_id = $2 AND emoji = $3
        """, ctx.guild.id, channel.id, emoji)
        
        if result == "DELETE 0":
            return await ctx.warn(f"A starboard for **{emoji}** in {channel.mention} doesn't exist")
        
        return await ctx.approve(f"Removed the starboard for {emoji} in {channel.mention}")
    
    @starboard.command(name="clear", aliases=["reset", "purge"])
    @commands.has_permissions(manage_guild=True)
    async def starboard_clear(self, ctx: Context):
        result = await self.bot.db_pool.execute("DELETE FROM starboard WHERE guild_id = $1", ctx.guild.id)
        
        if result == "DELETE 0":
            return await ctx.warn("No starboards exist for this server")
        
        count = int(result.split()[-1])
        return await ctx.approve(f"Successfully removed `{count}` starboard{'s' if count != 1 else ''}")
    
    @starboard.command(name="ignore")
    @commands.has_permissions(manage_guild=True)
    async def starboard_ignore(self, ctx: Context, emoji: str, *, target: discord.TextChannel | discord.Role | discord.Member):
        starboard = await self.bot.db_pool.fetchrow("SELECT * FROM starboard WHERE guild_id = $1 AND emoji = $2", ctx.guild.id, emoji)
        if not starboard:
            return await ctx.warn(f"No starboard exists for **{emoji}**")
        
        if isinstance(target, discord.TextChannel):
            target_type = "channel"
        elif isinstance(target, discord.Role):
            target_type = "role"
        else:
            target_type = "member"
        
        result = await self.bot.db_pool.execute("""
            INSERT INTO starboard_ignore (guild_id, emoji, target_id, target_type)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, emoji, target_id) DO NOTHING
        """, ctx.guild.id, emoji, target.id, target_type)
        
        if result == "INSERT 0 0":
            return await ctx.warn(f"**{target}** is already ignored for {emoji}")
        
        return await ctx.approve(f"Now ignoring **{target}** for {emoji} starboard")
    
    @starboard.command(name="unignore")
    @commands.has_permissions(manage_guild=True)
    async def starboard_unignore(self, ctx: Context, emoji: str, *, target: discord.TextChannel | discord.Role | discord.Member):
        result = await self.bot.db_pool.execute("""
            DELETE FROM starboard_ignore
            WHERE guild_id = $1 AND emoji = $2 AND target_id = $3
        """, ctx.guild.id, emoji, target.id)
        
        if result == "DELETE 0":
            return await ctx.warn(f"**{target}** is not ignored for {emoji}")
        
        return await ctx.approve(f"No longer ignoring **{target}** for {emoji} starboard")
    
    @starboard.command(name="color", aliases=["colour"])
    @commands.has_permissions(manage_guild=True)
    async def starboard_color(self, ctx: Context, emoji: str, color: discord.Color = None):
        starboard = await self.bot.db_pool.fetchrow("SELECT * FROM starboard WHERE guild_id = $1 AND emoji = $2", ctx.guild.id, emoji)
        if not starboard:
            return await ctx.warn(f"No starboard exists for **{emoji}**")
        
        await self.bot.db_pool.execute("""
            UPDATE starboard SET color = $3 WHERE guild_id = $1 AND emoji = $2
        """, ctx.guild.id, emoji, color.value if color else None)
        
        if color:
            return await ctx.approve(f"Set the {emoji} starboard color to `{color}`")
        return await ctx.approve(f"Reset the {emoji} starboard color to default")
    
    @starboard.command(name="attachments")
    @commands.has_permissions(manage_guild=True)
    async def starboard_attachments(self, ctx: Context, emoji: str, status: bool):
        starboard = await self.bot.db_pool.fetchrow("SELECT * FROM starboard WHERE guild_id = $1 AND emoji = $2", ctx.guild.id, emoji)
        if not starboard:
            return await ctx.warn(f"No starboard exists for **{emoji}**")
        
        await self.bot.db_pool.execute("""
            UPDATE starboard SET attachments = $3 WHERE guild_id = $1 AND emoji = $2
        """, ctx.guild.id, emoji, status)
        
        status_text = "now" if status else "no longer"
        return await ctx.approve(f"Attachments will {status_text} be included in {emoji} starboard entries")
    
    @starboard.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def starboard_list(self, ctx: Context):
        records = await self.bot.db_pool.fetch("SELECT * FROM starboard WHERE guild_id = $1", ctx.guild.id)
        
        channels = []
        for record in records:
            channel = ctx.guild.get_channel(record["channel_id"])
            if channel:
                channels.append(f"{channel.mention} - **{record['emoji']}** (threshold: `{record['threshold']}`, author: `{record['self_star']}`)")
        
        if not channels:
            return await ctx.warn("No channels have a starboard configured")
        
        embeds = []
        embed = discord.Embed(title="Starboards", color=Config.COLORS.DEFAULT, description="")
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        
        count = 0
        for channel in channels:
            embed.description += f"{channel}\n"
            count += 1
            if count == 10:
                embeds.append(embed)
                embed = discord.Embed(title="Starboards", color=Config.COLORS.DEFAULT, description="")
                embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
                count = 0
        
        if count > 0:
            embeds.append(embed)
        
        if len(embeds) > 1:
            view = PaginatorView(embeds, ctx.author)
            return await ctx.send(embed=embeds[0], view=view)
        else:
            return await ctx.send(embed=embeds[0])
    
    @commands.Cog.listener("on_raw_reaction_add")
    async def starboard_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self._handle_starboard_reaction(payload, adding=True)
    
    @commands.Cog.listener("on_raw_reaction_remove")
    async def starboard_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self._handle_starboard_reaction(payload, adding=False)
    
    async def _handle_starboard_reaction(self, payload: discord.RawReactionActionEvent, adding: bool):
        if not payload.guild_id:
            return
        
        guild = self.bot.get_guild(payload.guild_id)
        if not guild or guild.me.is_timed_out():
            return
        
        channel = guild.get_channel_or_thread(payload.channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return
        
        starboard = await self.bot.db_pool.fetchrow(
            "SELECT * FROM starboard WHERE guild_id = $1 AND emoji = $2",
            guild.id, str(payload.emoji)
        )
        
        if not starboard:
            return
        
        star_channel = guild.get_channel(starboard['channel_id'])
        if not star_channel or star_channel == channel:
            return
        
        if not star_channel.permissions_for(guild.me).send_messages or not star_channel.permissions_for(guild.me).embed_links:
            return
        
        member = guild.get_member(payload.user_id)
        if not member:
            return
        
        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.HTTPException:
            return
        
        if channel.is_nsfw() and not star_channel.is_nsfw():
            return
        
        if message.author.id == member.id and not starboard['self_star']:
            return
        
        ignored = await self.bot.db_pool.fetch(
            "SELECT target_id, target_type FROM starboard_ignore WHERE guild_id = $1 AND emoji = $2",
            guild.id, str(payload.emoji)
        )
        
        for ignore in ignored:
            if ignore['target_type'] == 'channel' and ignore['target_id'] == channel.id:
                return
            elif ignore['target_type'] == 'member' and ignore['target_id'] == message.author.id:
                return
            elif ignore['target_type'] == 'role':
                author = guild.get_member(message.author.id)
                if author and any(role.id == ignore['target_id'] for role in author.roles):
                    return
        
        reaction = discord.utils.find(lambda r: str(r.emoji) == starboard['emoji'], message.reactions)
        
        if not reaction or reaction.count < starboard['threshold']:
            entry = await self.bot.db_pool.fetchrow(
                "SELECT star_id FROM starboard_entry WHERE message_id = $1 AND emoji = $2",
                message.id, starboard['emoji']
            )
            if entry:
                try:
                    star_message = await star_channel.fetch_message(entry['star_id'])
                    await star_message.delete()
                except:
                    pass
                await self.bot.db_pool.execute(
                    "DELETE FROM starboard_entry WHERE star_id = $1",
                    entry['star_id']
                )
            return
        
        entry = await self.bot.db_pool.fetchrow(
            "SELECT star_id FROM starboard_entry WHERE message_id = $1 AND emoji = $2",
            message.id, starboard['emoji']
        )
        
        embed = discord.Embed(
            description=message.content or "",
            color=starboard['color'] if starboard['color'] else Config.COLORS.DEFAULT,
            timestamp=message.created_at
        )
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        
        if message.attachments and starboard['attachments']:
            embed.set_image(url=message.attachments[0].url)
        
        embed.add_field(name="Source", value=f"[Jump to message]({message.jump_url})", inline=False)
        embed.set_footer(text=f"{starboard['emoji']} {reaction.count}")
        
        if entry:
            try:
                star_message = await star_channel.fetch_message(entry['star_id'])
                await star_message.edit(embed=embed)
            except:
                pass
        else:
            star_message = await star_channel.send(embed=embed)
            await self.bot.db_pool.execute("""
                INSERT INTO starboard_entry (guild_id, channel_id, message_id, star_id, emoji)
                VALUES ($1, $2, $3, $4, $5)
            """, guild.id, channel.id, message.id, star_message.id, starboard['emoji'])
    
    @commands.Cog.listener("on_guild_channel_delete")
    async def starboard_channel_delete(self, channel: discord.abc.GuildChannel):
        await self.bot.db_pool.execute(
            "DELETE FROM starboard WHERE guild_id = $1 AND channel_id = $2",
            channel.guild.id, channel.id
        )
        await self.bot.db_pool.execute(
            "DELETE FROM starboard_entry WHERE guild_id = $1 AND channel_id = $2",
            channel.guild.id, channel.id
        )
    
    @commands.Cog.listener("on_raw_reaction_clear")
    async def starboard_reaction_clear(self, payload: discord.RawReactionClearEvent):
        entries = await self.bot.db_pool.fetch("""
            DELETE FROM starboard_entry
            WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3
            RETURNING star_id, emoji
        """, payload.guild_id, payload.channel_id, payload.message_id)
        
        if not entries:
            return
        
        for entry in entries:
            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
                continue
            
            starboard = await self.bot.db_pool.fetchrow(
                "SELECT channel_id FROM starboard WHERE guild_id = $1 AND emoji = $2",
                guild.id, entry["emoji"]
            )
            
            if not starboard:
                continue
            
            star_channel = guild.get_channel(starboard['channel_id'])
            if not star_channel:
                continue
            
            try:
                star_message = await star_channel.fetch_message(entry["star_id"])
                await star_message.delete()
            except:
                pass
    
    @commands.group(name="webhook", aliases=["hook", "wh"], invoke_without_command=True)
    @commands.has_permissions(manage_webhooks=True)
    async def webhook(self, ctx: Context):
        return await ctx.send_help(ctx.command)
    
    @webhook.command(name="create", aliases=["add", "new"])
    @commands.has_permissions(manage_webhooks=True)
    @commands.cooldown(6, 480, commands.BucketType.guild)
    async def webhook_create(self, ctx: Context, channel: discord.TextChannel = None, *, name: str = None):
        channel = channel or ctx.channel
        
        if isinstance(channel, discord.Thread):
            channel = channel.parent
        
        if not isinstance(channel, discord.TextChannel):
            return await ctx.warn("This command only works in text channels")
        
        webhook_id = await self.bot.db_pool.fetchval(
            "SELECT webhook_id FROM webhook WHERE channel_id = $1",
            channel.id
        )
        
        webhook = None
        if webhook_id:
            webhooks = await channel.webhooks()
            webhook = discord.utils.get(webhooks, id=webhook_id)
        
        identifier = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8))
        
        webhook = webhook or await channel.create_webhook(
            name=name or f"Webhook {identifier}",
            reason=f"Webhook created by {ctx.author} ({ctx.author.id})"
        )
        
        await self.bot.db_pool.execute("""
            INSERT INTO webhook (identifier, guild_id, channel_id, author_id, webhook_id)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (channel_id, webhook_id) DO UPDATE
            SET identifier = EXCLUDED.identifier
        """, identifier, ctx.guild.id, channel.id, ctx.author.id, webhook.id)
        
        return await ctx.approve(f"Webhook created in {channel.mention} with the identifier `{identifier}`")
    
    @webhook.command(name="delete", aliases=["remove", "rm", "del"])
    @commands.has_permissions(manage_webhooks=True)
    async def webhook_delete(self, ctx: Context, identifier: str):
        record = await self.bot.db_pool.fetchrow("""
            DELETE FROM webhook
            WHERE guild_id = $1 AND identifier = $2
            RETURNING channel_id, webhook_id
        """, ctx.guild.id, identifier)
        
        if not record:
            return await ctx.warn(f"Webhook with the identifier `{identifier}` not found")
        
        channel = self.bot.get_channel(record["channel_id"])
        if channel:
            webhooks = await channel.webhooks()
            webhook = discord.utils.get(webhooks, id=record["webhook_id"])
            if webhook:
                await webhook.delete(reason=f"Webhook deleted by {ctx.author} ({ctx.author.id})")
        
        return await ctx.approve(f"Webhook with the identifier `{identifier}` has been deleted")
    
    @webhook.command(name="list")
    @commands.has_permissions(manage_webhooks=True)
    async def webhook_list(self, ctx: Context):
        records = await self.bot.db_pool.fetch(
            "SELECT * FROM webhook WHERE guild_id = $1",
            ctx.guild.id
        )
        
        webhooks = []
        for record in records:
            channel = ctx.guild.get_channel(record["channel_id"])
            if channel:
                webhooks.append(f"{channel.mention} - `{record['identifier']}` via <@{record['author_id']}>")
        
        if not webhooks:
            return await ctx.warn("No webhooks have been created")
        
        embeds = []
        embed = discord.Embed(title="Webhooks", color=Config.COLORS.DEFAULT, description="")
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        
        count = 0
        for webhook in webhooks:
            embed.description += f"{webhook}\n"
            count += 1
            if count == 10:
                embeds.append(embed)
                embed = discord.Embed(title="Webhooks", color=Config.COLORS.DEFAULT, description="")
                embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
                count = 0
        
        if count > 0:
            embeds.append(embed)
        
        if len(embeds) > 1:
            view = PaginatorView(embeds, ctx.author)
            return await ctx.send(embed=embeds[0], view=view)
        else:
            return await ctx.send(embed=embeds[0])
    
    @webhook.command(name="send", aliases=["forward", "fwd"])
    @commands.has_permissions(manage_webhooks=True)
    async def webhook_send(self, ctx: Context, identifier: str, *, message: str):
        record = await self.bot.db_pool.fetchrow("""
            SELECT channel_id, webhook_id
            FROM webhook
            WHERE guild_id = $1 AND identifier = $2
        """, ctx.guild.id, identifier)
        
        if not record:
            return await ctx.warn(f"Webhook with the identifier `{identifier}` not found")
        
        channel = self.bot.get_channel(record["channel_id"])
        if not channel:
            return await ctx.warn("The channel for this webhook no longer exists")
        
        webhooks = await channel.webhooks()
        webhook = discord.utils.get(webhooks, id=record["webhook_id"])
        if not webhook:
            return await ctx.warn("The webhook no longer exists")
        
        username = None
        avatar_url = None
        
        if "--username" in message:
            parts = message.split("--username", 1)
            message = parts[0].strip()
            username_part = parts[1].strip().split(None, 1)
            username = username_part[0]
            if len(username_part) > 1:
                message = username_part[1]
        
        if "--avatar" in message:
            parts = message.split("--avatar", 1)
            message = parts[0].strip()
            avatar_part = parts[1].strip().split(None, 1)
            avatar_url = avatar_part[0]
            if len(avatar_part) > 1:
                message = avatar_part[1]
        
        try:
            await webhook.send(
                content=message,
                username=username or webhook.name or ctx.guild.name,
                avatar_url=avatar_url or webhook.avatar or (ctx.guild.icon.url if ctx.guild.icon else None),
                wait=True
            )
        except discord.HTTPException as exc:
            return await ctx.warn(f"Failed to send webhook message: {exc.text}")
        
        if channel != ctx.channel:
            return await ctx.approve(f"Forwarded message to {channel.mention} via webhook `{identifier}`")
        
        return await ctx.message.add_reaction(Config.EMOJIS.SUCCESS)
    
    @webhook.command(name="edit", aliases=["modify", "update"])
    @commands.has_permissions(manage_webhooks=True)
    async def webhook_edit(self, ctx: Context, message: discord.Message, *, content: str):
        if message.guild != ctx.guild:
            return await ctx.warn("The message must be from this server")
        elif not message.webhook_id:
            return await ctx.warn("The message was not sent by a webhook")
        
        webhooks = await ctx.channel.webhooks()
        webhook = discord.utils.get(webhooks, id=message.webhook_id)
        if not webhook:
            return await ctx.warn("The webhook for that message no longer exists")
        
        try:
            await webhook.edit_message(message.id, content=content)
        except discord.HTTPException as exc:
            return await ctx.warn(f"Failed to edit webhook message: {exc.text}")
        
        return await ctx.message.add_reaction(Config.EMOJIS.SUCCESS)


async def setup(bot):
    await bot.add_cog(Configuration(bot))
