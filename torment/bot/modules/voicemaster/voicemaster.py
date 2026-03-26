from __future__ import annotations

import os

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from bot.helpers.context import TormentContext

load_dotenv()

VM_EMOJIS = {
    'lock': '<:lock:1479910901292335124>',
    'unlock': '<:unlock:1479910910150709248>',
    'hide': '<:ghost:1479910897282449650>',
    'reveal': '<:reveal:1479910902651158528>',
    'claim': '<:claim:1479910893348454711>',
    'increase': '<:increase:1479910898670768228>',
    'decrease': '<:decrease:1479910894648561745>',
    'view': '<:info:1479910900088701039>',
}


class VoiceMasterView(discord.ui.View):
    def __init__(self, pool: asyncpg.Pool) -> None:
        super().__init__(timeout=None)
        self.pool = pool

    async def get_owner_channel(self, user_id: int, guild_id: int) -> int | None:
        result = await self.pool.fetchrow(
            'SELECT channel_id FROM voicemaster_channels WHERE owner_id = $1 AND guild_id = $2',
            user_id, guild_id
        )
        return result['channel_id'] if result else None

    @discord.ui.button(emoji='<:lock:1479910901292335124>', style=discord.ButtonStyle.secondary, custom_id='vm_lock', row=0)
    async def lock_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel_id = await self.get_owner_channel(interaction.user.id, interaction.guild.id)
        if not channel_id:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: You do not own a voice channel"),
                ephemeral=True
            )
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: Channel not found"),
                ephemeral=True
            )
        await channel.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message(
            embed=discord.Embed(description=f"> {interaction.user.mention}: Locked your voice channel"),
            ephemeral=True
        )

    @discord.ui.button(emoji='<:unlock:1479910910150709248>', style=discord.ButtonStyle.secondary, custom_id='vm_unlock', row=0)
    async def unlock_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel_id = await self.get_owner_channel(interaction.user.id, interaction.guild.id)
        if not channel_id:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: You do not own a voice channel"),
                ephemeral=True
            )
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: Channel not found"),
                ephemeral=True
            )
        await channel.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message(
            embed=discord.Embed(description=f"> {interaction.user.mention}: Unlocked your voice channel"),
            ephemeral=True
        )

    @discord.ui.button(emoji='<:ghost:1479910897282449650>', style=discord.ButtonStyle.secondary, custom_id='vm_ghost', row=0)
    async def ghost_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel_id = await self.get_owner_channel(interaction.user.id, interaction.guild.id)
        if not channel_id:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: You do not own a voice channel"),
                ephemeral=True
            )
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: Channel not found"),
                ephemeral=True
            )
        await channel.set_permissions(interaction.guild.default_role, view_channel=False)
        await interaction.response.send_message(
            embed=discord.Embed(description=f"> {interaction.user.mention}: Ghosted your voice channel"),
            ephemeral=True
        )

    @discord.ui.button(emoji='<:reveal:1479910902651158528>', style=discord.ButtonStyle.secondary, custom_id='vm_reveal', row=0)
    async def reveal_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel_id = await self.get_owner_channel(interaction.user.id, interaction.guild.id)
        if not channel_id:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: You do not own a voice channel"),
                ephemeral=True
            )
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: Channel not found"),
                ephemeral=True
            )
        await channel.set_permissions(interaction.guild.default_role, view_channel=True)
        await interaction.response.send_message(
            embed=discord.Embed(description=f"> {interaction.user.mention}: Revealed your voice channel"),
            ephemeral=True
        )

    @discord.ui.button(emoji='<:claim:1479910893348454711>', style=discord.ButtonStyle.secondary, custom_id='vm_claim', row=1)
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: You must be in a voice channel"),
                ephemeral=True
            )
        result = await self.pool.fetchrow(
            'SELECT owner_id FROM voicemaster_channels WHERE channel_id = $1',
            interaction.user.voice.channel.id
        )
        if not result:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: This is not a **VoiceMaster** channel"),
                ephemeral=True
            )
        owner = interaction.guild.get_member(result['owner_id'])
        if owner and owner in interaction.user.voice.channel.members:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: The owner is still in the channel"),
                ephemeral=True
            )
        await self.pool.execute(
            'UPDATE voicemaster_channels SET owner_id = $1 WHERE channel_id = $2',
            interaction.user.id, interaction.user.voice.channel.id
        )
        await interaction.response.send_message(
            embed=discord.Embed(description=f"> {interaction.user.mention}: Claimed the voice channel"),
            ephemeral=True
        )

    @discord.ui.button(emoji='<:increase:1479910898670768228>', style=discord.ButtonStyle.secondary, custom_id='vm_increase', row=1)
    async def increase_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel_id = await self.get_owner_channel(interaction.user.id, interaction.guild.id)
        if not channel_id:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: You do not own a voice channel"),
                ephemeral=True
            )
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: Channel not found"),
                ephemeral=True
            )
        if channel.user_limit >= 99:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: Channel is at maximum limit"),
                ephemeral=True
            )
        await channel.edit(user_limit=channel.user_limit + 1)
        await interaction.response.send_message(
            embed=discord.Embed(description=f"> {interaction.user.mention}: Increased limit to **{channel.user_limit}**."),
            ephemeral=True
        )

    @discord.ui.button(emoji='<:decrease:1479910894648561745>', style=discord.ButtonStyle.secondary, custom_id='vm_decrease', row=1)
    async def decrease_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel_id = await self.get_owner_channel(interaction.user.id, interaction.guild.id)
        if not channel_id:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: You do not own a voice channel"),
                ephemeral=True
            )
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: Channel not found"),
                ephemeral=True
            )
        if channel.user_limit <= 0:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: Channel is at minimum limit"),
                ephemeral=True
            )
        await channel.edit(user_limit=max(0, channel.user_limit - 1))
        await interaction.response.send_message(
            embed=discord.Embed(description=f"> {interaction.user.mention}: Decreased limit to **{channel.user_limit}**"),
            ephemeral=True
        )

    @discord.ui.button(emoji='<:info:1479910900088701039>', style=discord.ButtonStyle.secondary, custom_id='vm_view', row=1)
    async def view_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel_id = await self.get_owner_channel(interaction.user.id, interaction.guild.id)
        if not channel_id:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: You do not own a voice channel"),
                ephemeral=True
            )
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"> {interaction.user.mention}: Channel not found"),
                ephemeral=True
            )
        embed = discord.Embed(title='Channel Information')
        embed.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.add_field(name='Name', value=channel.name, inline=False)
        embed.add_field(name='Members', value=len(channel.members), inline=False)
        embed.add_field(name='Limit', value=channel.user_limit if channel.user_limit > 0 else 'Unlimited', inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class VoiceMaster(commands.Cog):
    __cog_name__ = "VoiceMaster"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.pool: asyncpg.Pool = None  # type: ignore — set in cog_load

    async def cog_load(self) -> None:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise RuntimeError('DATABASE_URL is not set in the environment / .env file')

        self.pool = await asyncpg.create_pool(database_url)

        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS voicemaster (
                guild_id BIGINT PRIMARY KEY,
                channel_id BIGINT,
                category_id BIGINT,
                channel_name TEXT,
                interface_channel_id BIGINT
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS voicemaster_channels (
                guild_id BIGINT,
                channel_id BIGINT PRIMARY KEY,
                owner_id BIGINT
            )
        """)

        # Pass pool directly so persistent view buttons always have DB access
        self.bot.add_view(VoiceMasterView(self.pool))

    async def cog_unload(self) -> None:
        if self.pool:
            await self.pool.close()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        config = await self.pool.fetchrow(
            'SELECT channel_id, category_id, channel_name FROM voicemaster WHERE guild_id = $1',
            member.guild.id
        )
        if not config:
            return

        if after.channel and after.channel.id == config['channel_id']:
            channel_name = (config.get('channel_name') or "{user}'s channel").replace("{user}", member.display_name)
            category = member.guild.get_channel(config['category_id'])
            channel = await member.guild.create_voice_channel(name=channel_name, category=category)
            await self.pool.execute(
                'INSERT INTO voicemaster_channels (guild_id, channel_id, owner_id) VALUES ($1, $2, $3)',
                member.guild.id, channel.id, member.id
            )
            await member.move_to(channel)

        if before.channel and before.channel.id != config['channel_id']:
            record = await self.pool.fetchrow(
                'SELECT channel_id FROM voicemaster_channels WHERE guild_id = $1 AND channel_id = $2',
                member.guild.id, before.channel.id
            )
            if record and len(before.channel.members) == 0:
                await before.channel.delete()
                await self.pool.execute(
                    'DELETE FROM voicemaster_channels WHERE channel_id = $1',
                    before.channel.id
                )

    @commands.hybrid_group(
        name="voicemaster",
        aliases=["vm", "vc"],
        invoke_without_command=True,
        help="Manage the VoiceMaster system",
        extras={"parameters": "n/a", "usage": "voicemaster"},
    )
    async def voicemaster(self, ctx: TormentContext) -> None:
        await ctx.send_help(ctx.command)

    @voicemaster.command(
        name="setup",
        help="Setup the VoiceMaster configuration.",
        extras={"parameters": "n/a", "usage": "voicemaster setup"},
    )
    @commands.has_permissions(manage_guild=True)
    async def voicemaster_setup(self, ctx: TormentContext) -> None:
        channel_name = "{user}'s channel"
        category = await ctx.guild.create_category('VoiceMaster')

        interface_channel = await ctx.guild.create_text_channel(name='interface', category=category)
        await interface_channel.set_permissions(ctx.guild.default_role, send_messages=False, add_reactions=False)

        join_channel = await ctx.guild.create_voice_channel(name='j2c', category=category)

        embed = discord.Embed(
            title='VoiceMaster Interface',
            description=f'> **This interface is linked to** {join_channel.mention}',
        )
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        embed.add_field(name='', value=(
            f"{VM_EMOJIS['lock']} — **Lock** your voice channel\n"
            f"{VM_EMOJIS['unlock']} — **Unlock** your voice channel\n"
            f"{VM_EMOJIS['hide']} — **Hide** your voice channel\n"
            f"{VM_EMOJIS['reveal']} — **Reveal** your voice channel\n"
            f"{VM_EMOJIS['claim']} — **Claim** a voice channel\n"
            f"{VM_EMOJIS['increase']} — **Increase** your channel's user limit\n"
            f"{VM_EMOJIS['decrease']} — **Decrease** your channel's user limit\n"
            f"{VM_EMOJIS['view']} — **View** a channel's information"
        ), inline=False)

        await interface_channel.send(embed=embed, view=VoiceMasterView(self.pool))

        await self.pool.execute('''
            INSERT INTO voicemaster (guild_id, channel_id, category_id, channel_name, interface_channel_id)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id) DO UPDATE SET
                channel_id = $2, category_id = $3, channel_name = $4, interface_channel_id = $5
        ''', ctx.guild.id, join_channel.id, category.id, channel_name, interface_channel.id)

        await ctx.success("setup **VoiceMaster**. I've created 2 channels and 1 category, you can rename them if you'd like.")

    @voicemaster.command(
        name="reset",
        aliases=["disable", "remove"],
        help="Reset the VoiceMaster configuration.",
        extras={"parameters": "n/a", "usage": "voicemaster reset"},
    )
    @commands.has_permissions(manage_guild=True)
    async def voicemaster_reset(self, ctx: TormentContext) -> None:
        result = await self.pool.fetchrow(
            'SELECT category_id FROM voicemaster WHERE guild_id = $1', ctx.guild.id
        )
        if not result:
            await ctx.warn("**VoiceMaster** is not set up in this server.")
            return

        category = ctx.guild.get_channel(result['category_id'])
        if category:
            for channel in category.channels:
                await channel.delete()
            await category.delete()

        await self.pool.execute('DELETE FROM voicemaster WHERE guild_id = $1', ctx.guild.id)
        await self.pool.execute('DELETE FROM voicemaster_channels WHERE guild_id = $1', ctx.guild.id)

        await ctx.success("I've reset the **VoiceMaster** configuration.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceMaster(bot))
