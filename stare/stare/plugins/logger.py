import discord
from discord.ext import commands

# ── Config ──────────────────────────────────────────────────────────────────
JOIN_LOG_CHANNEL_ID  = 1475992628129566833
LEAVE_LOG_CHANNEL_ID = 1475992657292689500
# ────────────────────────────────────────────────────────────────────────────


class Logger(commands.Cog, command_attrs=dict(hidden=True)):
    """Guild join/leave logger — hidden from all help menus."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        # Block any accidental command invocations from non-owners
        return await self.bot.is_owner(ctx.author)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        channel = self.bot.get_channel(JOIN_LOG_CHANNEL_ID)
        if channel is None:
            print(f"[Logger] Could not find join log channel (ID: {JOIN_LOG_CHANNEL_ID})")
            return

        try:
            owner = await self.bot.fetch_user(guild.owner_id)
            owner_name = str(owner)
        except Exception:
            owner_name = f"<@{guild.owner_id}>"

        embed = discord.Embed(
            title="Joined Server",
            description=(
                f"> **ID:** {guild.id}\n"
                f"> **Owner:** {owner_name}\n"
                f"> **Name:** {guild.name}\n"
            ),
            color=discord.Color.greyple(),
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.set_footer(text="Logging | stare.lat | discord.gg/starebot")

        invite_url = None
        try:
            invite_channel = guild.system_channel or next(
                (c for c in guild.text_channels if c.permissions_for(guild.me).create_instant_invite),
                None,
            )
            if invite_channel:
                invite = await invite_channel.create_invite(max_age=0, max_uses=0, unique=False)
                invite_url = invite.url
        except discord.Forbidden:
            print(f"[Logger] Missing permissions to create invite in {guild.name}")
        except Exception as e:
            print(f"[Logger] Failed to create invite: {e}")

        view = discord.ui.View()
        if invite_url:
            view.add_item(
                discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    label="Join Server",
                    url=invite_url,
                )
            )

        await channel.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        channel = self.bot.get_channel(LEAVE_LOG_CHANNEL_ID)
        if channel is None:
            print(f"[Logger] Could not find leave log channel (ID: {LEAVE_LOG_CHANNEL_ID})")
            return

        try:
            owner = await self.bot.fetch_user(guild.owner_id)
            owner_name = str(owner)
        except Exception:
            owner_name = f"<@{guild.owner_id}>"

        embed = discord.Embed(
            title="Left Server",
            description=(
                f"> **ID:** {guild.id}\n"
                f"> **Owner:** {owner_name}\n"
                f"> **Name:** {guild.name}\n"
            ),
            color=discord.Color.greyple(),
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.set_footer(text="Logging | stare.lat | discord.gg/starebot")

        invite_url = None
        try:
            invite_channel = guild.system_channel or next(
                (c for c in guild.text_channels if c.permissions_for(guild.me).create_instant_invite),
                None,
            )
            if invite_channel:
                invite = await invite_channel.create_invite(max_age=0, max_uses=0, unique=False)
                invite_url = invite.url
        except Exception:
            pass

        view = discord.ui.View()
        if invite_url:
            view.add_item(
                discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    label="Join Server",
                    url=invite_url,
                )
            )

        await channel.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logger(bot))