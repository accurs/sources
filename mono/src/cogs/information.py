from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from src.cogs.owner import owner_clearance


class Information(commands.Cog):
    """General Discord object inspection commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="server-icon",
        aliases=["servericon", "sicon"],
        description="Show the current server's icon",
    )
    @commands.guild_only()
    @app_commands.guild_only()
    async def server_icon(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        assert guild is not None
        if guild.icon is None:
            await ctx.send("This server does not have an icon.", ephemeral=True)
            return
        icon = guild.icon.with_size(4096)
        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## {guild.name}'s Icon"),
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(icon.url, description=f"{guild.name} icon")
                ),
                discord.ui.ActionRow(
                    discord.ui.Button(
                        label="Open Original",
                        style=discord.ButtonStyle.link,
                        url=icon.url,
                    )
                ),
            )
        )
        await ctx.send(view=view)

    @commands.hybrid_command(
        name="membercount",
        aliases=["members", "mc"],
        description="Show the current server's member count",
    )
    @commands.guild_only()
    @app_commands.guild_only()
    async def membercount(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        assert guild is not None
        cached = list(guild.members)
        humans = sum(not member.bot for member in cached)
        bots = sum(member.bot for member in cached)
        total = guild.member_count if guild.member_count is not None else len(cached)
        complete = len(cached) >= total
        detail_label = "Members" if complete else "Cached members"
        body = (
            f"**Total:** `{total:,}`\n"
            f"**Humans:** `{humans:,}`\n"
            f"**Bots:** `{bots:,}`"
        )
        if not complete:
            body += f"\n**{detail_label}:** `{len(cached):,}`"
        header = discord.ui.TextDisplay(f"## {guild.name}\n{body}")
        if guild.icon:
            item: discord.ui.Item = discord.ui.Section(
                header,
                accessory=discord.ui.Thumbnail(
                    guild.icon.url, description=f"{guild.name} icon"
                ),
            )
        else:
            item = header
        view = discord.ui.LayoutView()
        view.add_item(discord.ui.Container(item))
        await ctx.send(view=view)

    @commands.hybrid_command(
        name="inviteinfo",
        aliases=["ii"],
        description="Inspect any valid public Discord invite",
    )
    @app_commands.describe(invite="Invite code or full Discord invite URL")
    @owner_clearance()
    async def inviteinfo(
        self,
        ctx: commands.Context,
        invite: str,
        ephemeral: bool = False,
    ) -> None:
        invite = invite.strip().strip("<>")
        try:
            data = await self.bot.fetch_invite(
                invite,
                with_counts=True,
                with_expiration=True,
            )
        except discord.NotFound:
            await ctx.send("That invite does not exist or has expired.")
            return
        except discord.Forbidden:
            await ctx.send("Discord refused access to that invite.")
            return
        except discord.HTTPException as error:
            await ctx.send(f"Discord could not inspect that invite: `{error}`")
            return

        guild = data.guild
        guild_name = guild.name if guild else "Group DM"
        guild_id = str(guild.id) if guild else "Not applicable"
        channel = data.channel
        channel_name = getattr(channel, "name", None) or "Unknown"
        channel_id = getattr(channel, "id", None)
        inviter = (
            f"{data.inviter} (`{data.inviter.id}`)" if data.inviter else "N/A"
        )
        expires = (
            f"<t:{int(data.expires_at.timestamp())}:F> "
            f"(<t:{int(data.expires_at.timestamp())}:R>)"
            if data.expires_at
            else "Never or N/A"
        )
        created = (
            f"<t:{int(data.created_at.timestamp())}:F>"
            if data.created_at
            else "N/A"
        )
        uses = (
            f"{data.uses}/{data.max_uses or 'Unlimited'}"
            if data.uses is not None
            else "N/A"
        )
        counts = (
            f"{data.approximate_member_count:,} members • "
            f"{data.approximate_presence_count:,} online"
            if data.approximate_member_count is not None
            and data.approximate_presence_count is not None
            else "N/A"
        )
        icon_url = getattr(getattr(guild, "icon", None), "url", None)
        header_text = f"## Invite Information\n[{guild_name}]({data.url})"
        if icon_url:
            header: discord.ui.Item = discord.ui.Section(
                discord.ui.TextDisplay(header_text),
                accessory=discord.ui.Thumbnail(
                    icon_url,
                    description=f"{guild_name} icon",
                ),
            )
        else:
            header = discord.ui.TextDisplay(header_text)

        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                header,
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    "### Destination\n"
                    f"**Server:** {guild_name}\n"
                    f"**Server ID:** `{guild_id}`\n"
                    f"**Channel:** {channel_name}\n"
                    f"**Channel ID:** `{channel_id or 'Unavailable'}`\n"
                    f"**Invite code:** `{data.code}`"
                ),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    "### Invite Details\n"
                    f"**Inviter:** {inviter}\n"
                    f"**Created:** {created}\n"
                    f"**Expires:** {expires}\n"
                    f"**Uses:** {uses}\n"
                    f"**Temporary membership:** "
                    f"{'Yes' if data.temporary else 'No'}\n"
                    f"**Approximate counts:** {counts}"
                ),
            )
        )
        await ctx.send(view=view)

    @commands.hybrid_command(
        name="snowflake",
        aliases=["sf"],
        description="Decode a Discord ID into its creation time",
    )
    @app_commands.describe(discord_id="User, server, channel, role, or message ID")
    async def snowflake(
        self,
        ctx: commands.Context,
        discord_id: str,
        ephemeral: bool = False,
    ) -> None:
        cleaned = discord_id.strip().strip("<@!#&>")
        if not cleaned.isdigit() or not 15 <= len(cleaned) <= 22:
            await ctx.send("Provide a valid numeric Discord ID.")
            return

        try:
            value = int(cleaned)
            created_at = discord.utils.snowflake_time(value)
        except (ValueError, OverflowError, OSError):
            await ctx.send("That value is not a valid Discord snowflake.")
            return

        view = discord.ui.LayoutView()
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    "## Snowflake Information\n"
                    f"**ID:** `{value}`\n"
                    f"**Created:** <t:{int(created_at.timestamp())}:F>\n"
                    f"**Relative:** <t:{int(created_at.timestamp())}:R>\n"
                    f"**Worker ID:** `{(value & 0x3E0000) >> 17}`\n"
                    f"**Process ID:** `{(value & 0x1F000) >> 12}`\n"
                    f"**Increment:** `{value & 0xFFF}`"
                )
            )
        )
        await ctx.send(view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Information(bot))
