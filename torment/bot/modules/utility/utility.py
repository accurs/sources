from __future__ import annotations

import colorsys
import io
import os
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from collections import defaultdict

import aiohttp
import asyncpg
import dateparser
import discord
import pytz
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from PIL import Image

from bot.helpers.context import TormentContext, _color
from bot.helpers.converters.script.main import Script
from bot.helpers.paginator import Paginator

load_dotenv()
DB_DSN = os.getenv("DATABASE_URL")

EMBED_COLOR = discord.Color.from_str("#9FAB85")
GW_COLOR = discord.Color.from_str("#9FAB85")

EMOJI_RE = re.compile(r"<a?:[a-zA-Z0-9_]+:(\d+)>")


def parse_emoji_url(emoji_str: str) -> str | None:
    match = EMOJI_RE.search(emoji_str)
    if not match:
        return None
    emoji_id = match.group(1)
    animated = emoji_str.startswith("<a:")
    ext = "gif" if animated else "png"
    return f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=96"


async def fetch_image(url: str) -> bytes | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception:
        pass
    return None


def parse_duration(value: str) -> int:
    match = re.fullmatch(r"(\d+)\s*([smhdw])", value.strip().lower())
    if not match:
        raise ValueError(f"Invalid duration `{value}`. Use `s`, `m`, `h`, `d`, or `w` — e.g. `24h`, `30m`, `7d`.")
    amount, unit = int(match.group(1)), match.group(2)
    return amount * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]


def build_giveaway_embed(data: dict) -> discord.Embed:
    ends_at = data["ends_at"]
    ended = data.get("ended", False)
    host_id = data["host_id"]
    winner_count = data.get("winner_count", 1)

    embed = discord.Embed(title=data["prize"], color=GW_COLOR)

    if ended:
        winner_ids = data.get("winners") or []
        winners_fmt = ", ".join(f"<@{w}>" for w in winner_ids) if winner_ids else "No valid entries."
        embed.description = data["description"] if data.get("description") else None
        embed.add_field(name="Winners", value=winners_fmt, inline=False)
        embed.add_field(name="Ended", value=f"<t:{int(ends_at)}:R> (<t:{int(ends_at)}:f>)", inline=False)
    else:
        entry_count = len(data.get("participants") or [])
        desc = f"🎉 **{entry_count}** {'entry' if entry_count == 1 else 'entries'}"
        if data.get("description"):
            desc = f"{data['description']}\n\n{desc}"
        embed.description = desc
        embed.add_field(name="Ends", value=f"<t:{int(ends_at)}:R> (<t:{int(ends_at)}:f>)", inline=False)

    embed.add_field(name="Hosted by", value=f"<@{host_id}>", inline=True)
    embed.add_field(name="Winners", value=str(winner_count), inline=True)

    if data.get("required_roles"):
        roles_fmt = " ".join(f"<@&{r}>" for r in data["required_roles"])
        embed.add_field(name="Required Roles", value=roles_fmt, inline=False)

    if data.get("thumbnail"):
        embed.set_thumbnail(url=data["thumbnail"])
    if data.get("image"):
        embed.set_image(url=data["image"])

    return embed


async def can_dm(ctx: TormentContext) -> bool:
    try:
        await ctx.author.send()
    except discord.HTTPException as exc:
        if exc.code == 50007:
            raise commands.CheckFailure("You need to enable DMs to use this command")
    return True


class SnipeData:
    def __init__(self, max_snipes: int = 10):
        self.max_snipes = max_snipes
        self.deleted_messages: List[dict] = []
        self.edited_messages: List[dict] = []
        self.reaction_removes: List[dict] = []

    def add_deleted(self, message: discord.Message):
        data = {
            "author": message.author,
            "content": message.content,
            "attachments": [a.url for a in message.attachments],
            "timestamp": datetime.now(tz=timezone.utc),
            "channel_id": message.channel.id
        }
        self.deleted_messages.insert(0, data)
        if len(self.deleted_messages) > self.max_snipes:
            self.deleted_messages.pop()

    def add_edited(self, before: discord.Message, after: discord.Message):
        data = {
            "author": before.author,
            "before": before.content,
            "after": after.content,
            "timestamp": datetime.now(tz=timezone.utc),
            "channel_id": before.channel.id
        }
        self.edited_messages.insert(0, data)
        if len(self.edited_messages) > self.max_snipes:
            self.edited_messages.pop()

    def add_reaction(self, reaction: discord.Reaction, user: discord.User):
        data = {
            "user": user,
            "emoji": str(reaction.emoji),
            "message_author": reaction.message.author,
            "message_content": reaction.message.content[:50] + "..." if len(reaction.message.content) > 50 else reaction.message.content,
            "timestamp": datetime.now(tz=timezone.utc),
            "channel_id": reaction.message.channel.id
        }
        self.reaction_removes.insert(0, data)
        if len(self.reaction_removes) > self.max_snipes:
            self.reaction_removes.pop()


def parse_duration_to_timedelta(duration_str: str) -> timedelta:
    duration_str = duration_str.strip().lower()
    time_units = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400,
        'w': 604800
    }
    match = re.match(r'^(\d+)([smhdw])$', duration_str)
    if not match:
        raise ValueError("Invalid duration format. Use format like: 5m, 2h, 1d, 1w")
    amount = int(match.group(1))
    unit = match.group(2)
    if amount < 1:
        raise ValueError("Duration must be at least 1 minute")
    seconds = amount * time_units[unit]
    if seconds < 60:
        raise ValueError("Duration must be at least 1 minute")
    return timedelta(seconds=seconds)


class GiveawayView(discord.ui.View):
    def __init__(self, message_id: int, cog_ref=None) -> None:
        super().__init__(timeout=None)
        self.message_id = message_id
        self.cog_ref = cog_ref
        self._update_label()

    def _update_label(self) -> None:
        if self.cog_ref:
            data = self.cog_ref.giveaways.get(str(self.message_id))
            count = len(data.get("participants") or []) if data else 0
        else:
            count = 0
        self.enter_button.label = f"🎉 Enter ({count})"

    @discord.ui.button(label="🎉 Enter (0)", style=discord.ButtonStyle.primary, custom_id="giveaway:enter")
    async def enter_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.cog_ref:
            await interaction.response.send_message("Giveaway system unavailable.", ephemeral=True)
            return

        data = self.cog_ref.giveaways.get(str(self.message_id))
        if not data:
            await interaction.response.send_message("This giveaway no longer exists.", ephemeral=True)
            return
        if data.get("ended") or data.get("cancelled"):
            await interaction.response.send_message("This giveaway has already ended.", ephemeral=True)
            return

        required_roles = data.get("required_roles") or []
        if required_roles:
            member = interaction.guild.get_member(interaction.user.id)
            if not member or not any(r.id in required_roles for r in member.roles):
                role_mentions = ", ".join(f"<@&{r}>" for r in required_roles)
                await interaction.response.send_message(
                    f"You need one of these roles to enter: {role_mentions}", ephemeral=True
                )
                return

        participants = list(data.get("participants") or [])
        user_id = interaction.user.id

        if user_id in participants:
            participants.remove(user_id)
            data["participants"] = participants
            await self.cog_ref.pool.execute(
                "UPDATE giveaways SET participants = $1 WHERE message_id = $2",
                participants, self.message_id,
            )
            self._update_label()
            await interaction.response.edit_message(embed=build_giveaway_embed(data), view=self)
            await interaction.followup.send("You've been removed from the giveaway.", ephemeral=True)
        else:
            participants.append(user_id)
            data["participants"] = participants
            await self.cog_ref.pool.execute(
                "UPDATE giveaways SET participants = $1 WHERE message_id = $2",
                participants, self.message_id,
            )
            self._update_label()
            await interaction.response.edit_message(embed=build_giveaway_embed(data), view=self)
            await interaction.followup.send("You've entered the giveaway!", ephemeral=True)


class Utility(commands.Cog):
    __cog_name__ = "utility"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.pool: asyncpg.Pool = None
        self.giveaways: dict[str, dict] = {}
        self.snipes: Dict[int, SnipeData] = defaultdict(SnipeData)
        self.reminders: List[Dict[str, Any]] = []
        self._shutup_rate: dict[str, float] = {}

    @property
    def storage(self):
        return self.bot.storage

    async def cog_load(self) -> None:
        self.pool = await asyncpg.create_pool(dsn=DB_DSN)

        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS giveaways (
                message_id    BIGINT PRIMARY KEY,
                guild_id      BIGINT NOT NULL,
                channel_id    BIGINT NOT NULL,
                host_id       BIGINT NOT NULL,
                prize         TEXT NOT NULL,
                description   TEXT,
                ends_at       TIMESTAMPTZ NOT NULL,
                winner_count  INTEGER NOT NULL DEFAULT 1,
                ended         BOOLEAN NOT NULL DEFAULT FALSE,
                cancelled     BOOLEAN NOT NULL DEFAULT FALSE,
                winners       BIGINT[] NOT NULL DEFAULT '{}',
                required_roles BIGINT[] NOT NULL DEFAULT '{}',
                thumbnail     TEXT,
                image         TEXT
            )
        """)

        await self.pool.execute("ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS cancelled BOOLEAN NOT NULL DEFAULT FALSE")
        await self.pool.execute("ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS required_roles BIGINT[] NOT NULL DEFAULT '{}'")
        await self.pool.execute("ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS thumbnail TEXT")
        await self.pool.execute("ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS image TEXT")
        await self.pool.execute("ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS description TEXT")
        await self.pool.execute("ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS winner_count INTEGER NOT NULL DEFAULT 1")
        await self.pool.execute("ALTER TABLE giveaways ADD COLUMN IF NOT EXISTS participants BIGINT[] NOT NULL DEFAULT '{}'")

        records = await self.pool.fetch("SELECT * FROM giveaways WHERE cancelled = FALSE")
        for r in records:
            d = dict(r)
            d["ends_at"] = d["ends_at"].timestamp()
            d["winners"] = list(d.get("winners") or [])
            d["required_roles"] = list(d.get("required_roles") or [])
            d["participants"] = list(d.get("participants") or [])
            self.giveaways[str(r["message_id"])] = d

        for mid, data in self.giveaways.items():
            if not data.get("ended") and not data.get("cancelled"):
                view = GiveawayView(int(mid), cog_ref=self)
                self.bot.add_view(view, message_id=int(mid))

        await self._load_reminders()
        self._check_giveaways.start()
        self._check_reminders.start()
        self._check_bumps.start()

    async def cog_unload(self) -> None:
        self._check_giveaways.cancel()
        self._check_reminders.cancel()
        self._check_bumps.cancel()
        if self.pool:
            await self.pool.close()


    async def _load_reminders(self) -> None:
        query = "SELECT * FROM reminders WHERE expires_at > NOW() ORDER BY expires_at"
        records = await self.storage.pool.fetch(query)
        self.reminders = [dict(r) for r in records]

    @tasks.loop(seconds=10)
    async def _check_reminders(self) -> None:
        now = datetime.now(tz=timezone.utc)
        for reminder in list(self.reminders):
            if now >= reminder["expires_at"]:
                await self._send_reminder(reminder)
                self.reminders.remove(reminder)
                await self.storage.pool.execute("DELETE FROM reminders WHERE id = $1", reminder["id"])

    async def _send_reminder(self, reminder: dict) -> None:
        user = self.bot.get_user(reminder["user_id"])
        if not user:
            try:
                user = await self.bot.fetch_user(reminder["user_id"])
            except discord.HTTPException:
                return
        embed = discord.Embed(
            title="Reminder",
            description=f"[Jump to Message]({reminder['jump_url']})\n>>> {reminder['text']}",
            color=EMBED_COLOR,
        )
        try:
            await user.send(embed=embed)
        except discord.HTTPException:
            pass

    @tasks.loop(seconds=15)
    async def _check_giveaways(self) -> None:
        now = datetime.now(tz=timezone.utc).timestamp()
        for mid, data in list(self.giveaways.items()):
            if not data.get("ended") and not data.get("cancelled") and now >= data["ends_at"]:
                created_at = data.get("created_at", 0)
                if now - created_at < 10:
                    continue
                await self._conclude_giveaway(mid)

    async def _conclude_giveaway(self, mid: str) -> None:
        data = self.giveaways.get(mid)
        if not data or data.get("ended") or data.get("cancelled"):
            return

        try:
            channel = self.bot.get_channel(data["channel_id"]) or await self.bot.fetch_channel(data["channel_id"])
            message = await channel.fetch_message(int(mid))
        except (discord.NotFound, discord.HTTPException):
            data["ended"] = True
            await self.pool.execute("UPDATE giveaways SET ended = TRUE WHERE message_id = $1", int(mid))
            return

        entries: list[int] = []
        required_roles = data.get("required_roles") or []
        participants = data.get("participants") or []
        for user_id in participants:
            member = message.guild.get_member(user_id)
            if not member:
                continue
            if required_roles and not any(r.id in required_roles for r in member.roles):
                continue
            entries.append(user_id)

        count = data.get("winner_count", 1)
        winners = random.sample(entries, min(count, len(entries))) if entries else []

        data["ended"] = True
        data["winners"] = winners
        await self.pool.execute(
            "UPDATE giveaways SET ended = TRUE, winners = $1 WHERE message_id = $2",
            winners, int(mid),
        )

        await message.edit(embed=build_giveaway_embed(data), view=None)

        if winners:
            mentions = ", ".join(f"<@{w}>" for w in winners)
            await message.reply(
                f"{mentions} won **{data['prize']}**!",
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        else:
            await channel.send(f"The giveaway for **{data['prize']}** ended with no valid entries.")

    async def _parse_message_link(self, ctx: TormentContext, link: str) -> discord.Message | None:
        parts = link.strip("/").split("/")
        try:
            channel_id = int(parts[-2])
            message_id = int(parts[-1])
        except (ValueError, IndexError):
            await ctx.warn("Invalid message link.")
            return None
        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            await ctx.warn("Channel not found.")
            return None
        try:
            return await channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.warn("Message not found.")
            return None

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not message.content and not message.attachments:
            return
        self.snipes[message.channel.id].add_deleted(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild:
            return
        if before.content == after.content:
            return
        self.snipes[before.channel.id].add_edited(before, after)

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction: discord.Reaction, user: discord.User):
        if user.bot or not reaction.message.guild:
            return
        self.snipes[reaction.message.channel.id].add_reaction(reaction, user)

    @commands.group(
        name="giveaway",
        aliases=["gw"],
        invoke_without_command=True,
        help="Manage server giveaways",
        extras={"parameters": "n/a", "usage": "giveaway"},
    )
    @commands.has_permissions(manage_guild=True)
    async def giveaway_group(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @giveaway_group.command(
        name="start",
        help="Start a new giveaway",
        extras={"parameters": "channel, duration, winners, prize", "usage": "giveaway start (channel) (duration) (winners) (prize)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def giveaway_start(
        self,
        ctx: TormentContext,
        channel: discord.TextChannel,
        duration: str,
        winners: int,
        *,
        prize: str,
    ) -> None:
        try:
            seconds = parse_duration(duration)
        except ValueError as e:
            return await ctx.warn(str(e))

        if winners < 1 or winners > 20:
            return await ctx.warn("Winner count must be between **1** and **20**.")

        ends_at_dt = datetime.now(tz=timezone.utc) + timedelta(seconds=seconds)
        ends_at_ts = ends_at_dt.timestamp()

        data: dict = {
            "guild_id": ctx.guild.id,
            "channel_id": channel.id,
            "host_id": ctx.author.id,
            "prize": prize,
            "description": None,
            "ends_at": ends_at_ts,
            "winner_count": winners,
            "ended": False,
            "cancelled": False,
            "winners": [],
            "required_roles": [],
            "participants": [],
            "thumbnail": None,
            "image": None,
        }

        msg = await channel.send(embed=build_giveaway_embed(data))
        view = GiveawayView(msg.id, cog_ref=self)
        await msg.edit(view=view)
        self.bot.add_view(view, message_id=msg.id)

        data["message_id"] = msg.id
        data["created_at"] = datetime.now(tz=timezone.utc).timestamp()
        self.giveaways[str(msg.id)] = data

        await self.pool.execute(
            """
            INSERT INTO giveaways
                (message_id, guild_id, channel_id, host_id, prize, ends_at, winner_count, participants)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            msg.id, ctx.guild.id, channel.id, ctx.author.id, prize, ends_at_dt, winners, [],
        )

        await ctx.message.add_reaction("✅")

    @giveaway_group.command(
        name="end",
        help="End an active giveaway",
        extras={"parameters": "message link", "usage": "giveaway end (message link)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def giveaway_end(self, ctx: TormentContext, *, link: str) -> None:
        msg = await self._parse_message_link(ctx, link)
        if not msg:
            return
        data = self.giveaways.get(str(msg.id))
        if not data:
            return await ctx.warn("That message isn't a giveaway.")
        if data.get("ended"):
            return await ctx.warn("That giveaway has already ended.")
        if data.get("cancelled"):
            return await ctx.warn("That giveaway was cancelled.")
        await self._conclude_giveaway(str(msg.id))
        await ctx.success(f"Ended the Giveaway in {msg.channel.mention}")

    @giveaway_group.command(
        name="reroll",
        help="Reroll the winner(s) of an ended giveaway",
        extras={"parameters": "message link", "usage": "giveaway reroll (message link)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def giveaway_reroll(self, ctx: TormentContext, *, link: str) -> None:
        msg = await self._parse_message_link(ctx, link)
        if not msg:
            return
        data = self.giveaways.get(str(msg.id))
        if not data:
            return await ctx.warn("That message isn't a giveaway.")
        if not data.get("ended"):
            return await ctx.warn("That giveaway hasn't ended yet.")

        entries: list[int] = []
        required_roles = data.get("required_roles") or []
        participants = data.get("participants") or []
        for user_id in participants:
            member = msg.guild.get_member(user_id)
            if not member:
                continue
            if required_roles and not any(r.id in required_roles for r in member.roles):
                continue
            entries.append(user_id)

        count = data.get("winner_count", 1)
        winners = random.sample(entries, min(count, len(entries))) if entries else []
        if not winners:
            return await ctx.warn("No valid entries to reroll from.")

        data["winners"] = winners
        await self.pool.execute("UPDATE giveaways SET winners = $1 WHERE message_id = $2", winners, msg.id)
        await msg.edit(embed=build_giveaway_embed(data))

        mentions = ", ".join(f"<@{w}>" for w in winners)
        await msg.reply(f"{mentions} won **{data['prize']}**!", allowed_mentions=discord.AllowedMentions(users=True))
        await ctx.message.add_reaction("✅")
        await ctx.success(f"Rerolled the Giveaway in {msg.channel.mention}")

    @giveaway_group.command(
        name="cancel",
        help="Cancel a giveaway without drawing winners and delete the message",
        extras={"parameters": "message link", "usage": "giveaway cancel (message link)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def giveaway_cancel(self, ctx: TormentContext, *, link: str) -> None:
        msg = await self._parse_message_link(ctx, link)
        if not msg:
            return
        data = self.giveaways.get(str(msg.id))
        if not data:
            return await ctx.warn("That message isn't a giveaway.")
        if data.get("cancelled"):
            return await ctx.warn("That giveaway is already cancelled.")

        data["cancelled"] = True
        self.giveaways.pop(str(msg.id), None)
        await self.pool.execute("UPDATE giveaways SET cancelled = TRUE WHERE message_id = $1", msg.id)
        try:
            await msg.delete()
        except discord.HTTPException:
            pass
        await ctx.success(f"Canceled the Giveaway in {msg.channel.mention}")

    @giveaway_group.command(
        name="list",
        help="View all active giveaways in this server",
        extras={"parameters": "n/a", "usage": "giveaway list"},
    )
    @commands.has_permissions(manage_guild=True)
    async def giveaway_list(self, ctx: TormentContext) -> None:
        guild_gws = [
            (mid, d) for mid, d in self.giveaways.items()
            if d.get("guild_id") == ctx.guild.id and not d.get("cancelled")
        ]
        if not guild_gws:
            return await ctx.warn("No giveaways found in this server.")

        guild_gws.sort(key=lambda x: (x[1].get("ended", False), x[1]["ends_at"]))
        lines = []
        for i, (mid, d) in enumerate(guild_gws, 1):
            status = "ended" if d.get("ended") else "active"
            channel = ctx.guild.get_channel(d["channel_id"])
            ch_mention = channel.mention if channel else f"`{d['channel_id']}`"
            lines.append(f"`{i:02}` **{d['prize']}** ({status}) — {ch_mention} [`{mid}`]")

        embed = discord.Embed(title="Giveaways", color=GW_COLOR)
        if ctx.guild.icon:
            embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url)
        paginator = Paginator(ctx, lines, embed)
        await paginator.start()

    @giveaway_group.group(
        name="edit",
        invoke_without_command=True,
        help="Edit an active giveaway",
        extras={"parameters": "n/a", "usage": "giveaway edit"},
    )
    @commands.has_permissions(manage_guild=True)
    async def giveaway_edit(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @giveaway_edit.command(
        name="host",
        help="Change the host of a giveaway",
        extras={"parameters": "message link, member", "usage": "giveaway edit host (message link) (member)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def giveaway_edit_host(self, ctx: TormentContext, link: str, *, member: discord.Member) -> None:
        msg = await self._parse_message_link(ctx, link)
        if not msg:
            return
        data = self.giveaways.get(str(msg.id))
        if not data:
            return await ctx.warn("That message isn't a giveaway.")
        if data.get("ended") or data.get("cancelled"):
            return await ctx.warn("That giveaway is no longer active.")
        data["host_id"] = member.id
        await self.pool.execute("UPDATE giveaways SET host_id = $1 WHERE message_id = $2", member.id, msg.id)
        await msg.edit(embed=build_giveaway_embed(data))
        await ctx.success(f"Updated the giveaway host to {member.mention}.")

    @giveaway_edit.command(
        name="prize",
        help="Change the prize of a giveaway",
        extras={"parameters": "message link, prize", "usage": "giveaway edit prize (message link) (prize)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def giveaway_edit_prize(self, ctx: TormentContext, link: str, *, prize: str) -> None:
        msg = await self._parse_message_link(ctx, link)
        if not msg:
            return
        data = self.giveaways.get(str(msg.id))
        if not data:
            return await ctx.warn("That message isn't a giveaway.")
        if data.get("ended") or data.get("cancelled"):
            return await ctx.warn("That giveaway is no longer active.")
        data["prize"] = prize
        await self.pool.execute("UPDATE giveaways SET prize = $1 WHERE message_id = $2", prize, msg.id)
        await msg.edit(embed=build_giveaway_embed(data))
        await ctx.success(f"Updated the giveaway prize to **{prize}**.")

    @giveaway_edit.command(
        name="winners",
        help="Change the winner count of a giveaway",
        extras={"parameters": "message link, amount", "usage": "giveaway edit winners (message link) (amount)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def giveaway_edit_winners(self, ctx: TormentContext, link: str, amount: int) -> None:
        msg = await self._parse_message_link(ctx, link)
        if not msg:
            return
        data = self.giveaways.get(str(msg.id))
        if not data:
            return await ctx.warn("That message isn't a giveaway.")
        if data.get("ended") or data.get("cancelled"):
            return await ctx.warn("That giveaway is no longer active.")
        if amount < 1 or amount > 20:
            return await ctx.warn("Winner count must be between **1** and **20**.")
        data["winner_count"] = amount
        await self.pool.execute("UPDATE giveaways SET winner_count = $1 WHERE message_id = $2", amount, msg.id)
        await msg.edit(embed=build_giveaway_embed(data))
        await ctx.success(f"Updated the winner count to **{amount}**.")

    @giveaway_edit.command(
        name="duration",
        help="Change the end time of a giveaway",
        extras={"parameters": "message link, duration", "usage": "giveaway edit duration (message link) (duration)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def giveaway_edit_duration(self, ctx: TormentContext, link: str, duration: str) -> None:
        msg = await self._parse_message_link(ctx, link)
        if not msg:
            return
        data = self.giveaways.get(str(msg.id))
        if not data:
            return await ctx.warn("That message isn't a giveaway.")
        if data.get("ended") or data.get("cancelled"):
            return await ctx.warn("That giveaway is no longer active.")
        try:
            seconds = parse_duration(duration)
        except ValueError as e:
            return await ctx.warn(str(e))
        new_ends = datetime.now(tz=timezone.utc) + timedelta(seconds=seconds)
        data["ends_at"] = new_ends.timestamp()
        await self.pool.execute("UPDATE giveaways SET ends_at = $1 WHERE message_id = $2", new_ends, msg.id)
        await msg.edit(embed=build_giveaway_embed(data))
        await ctx.success(f"Updated the giveaway end time to <t:{int(data['ends_at'])}:R>.")

    @giveaway_edit.command(
        name="thumbnail",
        help="Set a thumbnail image on a giveaway",
        extras={"parameters": "message link, url", "usage": "giveaway edit thumbnail (message link) (url)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def giveaway_edit_thumbnail(self, ctx: TormentContext, link: str, url: str) -> None:
        msg = await self._parse_message_link(ctx, link)
        if not msg:
            return
        data = self.giveaways.get(str(msg.id))
        if not data:
            return await ctx.warn("That message isn't a giveaway.")
        if data.get("ended") or data.get("cancelled"):
            return await ctx.warn("That giveaway is no longer active.")
        data["thumbnail"] = url
        await self.pool.execute("UPDATE giveaways SET thumbnail = $1 WHERE message_id = $2", url, msg.id)
        await msg.edit(embed=build_giveaway_embed(data))
        await ctx.success("Updated the giveaway thumbnail.")

    @giveaway_edit.command(
        name="image",
        help="Set a large image on a giveaway",
        extras={"parameters": "message link, url", "usage": "giveaway edit image (message link) (url)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def giveaway_edit_image(self, ctx: TormentContext, link: str, url: str) -> None:
        msg = await self._parse_message_link(ctx, link)
        if not msg:
            return
        data = self.giveaways.get(str(msg.id))
        if not data:
            return await ctx.warn("That message isn't a giveaway.")
        if data.get("ended") or data.get("cancelled"):
            return await ctx.warn("That giveaway is no longer active.")
        data["image"] = url
        await self.pool.execute("UPDATE giveaways SET image = $1 WHERE message_id = $2", url, msg.id)
        await msg.edit(embed=build_giveaway_embed(data))
        await ctx.success("Updated the giveaway image.")

    @giveaway_edit.command(
        name="requiredroles",
        aliases=["roles"],
        help="Set required roles to enter a giveaway",
        extras={"parameters": "message link, roles...", "usage": "giveaway edit requiredroles (message link) (roles)"},
    )
    @commands.has_permissions(manage_guild=True)
    async def giveaway_edit_requiredroles(self, ctx: TormentContext, link: str, *roles: discord.Role) -> None:
        msg = await self._parse_message_link(ctx, link)
        if not msg:
            return
        data = self.giveaways.get(str(msg.id))
        if not data:
            return await ctx.warn("That message isn't a giveaway.")
        if data.get("ended") or data.get("cancelled"):
            return await ctx.warn("That giveaway is no longer active.")
        if not roles:
            return await ctx.warn("Please provide at least one role.")
        role_ids = [r.id for r in roles]
        data["required_roles"] = role_ids
        await self.pool.execute("UPDATE giveaways SET required_roles = $1 WHERE message_id = $2", role_ids, msg.id)
        await msg.edit(embed=build_giveaway_embed(data))
        roles_fmt = ", ".join(r.mention for r in roles)
        await ctx.success(f"Set required roles: {roles_fmt}")

    @commands.command(
        name="snipe",
        aliases=["s"],
        help="Snipe a deleted message",
        extras={"parameters": "index", "usage": "snipe [index]"},
    )
    async def snipe(self, ctx: TormentContext, index: int = 1):
        snipe_data = self.snipes.get(ctx.channel.id)
        if not snipe_data or not snipe_data.deleted_messages:
            return await ctx.warn("There are no deleted messages to snipe")

        if index < 1 or index > len(snipe_data.deleted_messages):
            return await ctx.warn(f"Invalid index. Available snipes: **1-{len(snipe_data.deleted_messages)}**")

        data = snipe_data.deleted_messages[index - 1]
        author = data["author"]

        embed = discord.Embed(
            color=_color("EMBED_INFO_COLOR"),
            description=data["content"] or "*No text content*",
            timestamp=data["timestamp"]
        )
        embed.set_author(name=author.display_name, icon_url=author.display_avatar.url)

        if data["attachments"]:
            embed.set_image(url=data["attachments"][0])
            if len(data["attachments"]) > 1:
                embed.add_field(
                    name="Attachments",
                    value="\n".join(data["attachments"][1:]),
                    inline=False
                )

        footer_text = f"Snipe {index}/{len(snipe_data.deleted_messages)}"
        if len(snipe_data.deleted_messages) > 1:
            footer_text += f" • Use snipe <1-{len(snipe_data.deleted_messages)}> to view others"
        embed.set_footer(text=footer_text)

        await ctx.send(embed=embed)

    @commands.command(
        name="editsnipe",
        aliases=["es", "esnipe"],
        help="Snipe an edited message",
        extras={"parameters": "index", "usage": "editsnipe [index]"},
    )
    async def editsnipe(self, ctx: TormentContext, index: int = 1):
        snipe_data = self.snipes.get(ctx.channel.id)
        if not snipe_data or not snipe_data.edited_messages:
            return await ctx.warn("There are no edited messages to snipe")

        if index < 1 or index > len(snipe_data.edited_messages):
            return await ctx.warn(f"Invalid index. Available snipes: **1-{len(snipe_data.edited_messages)}**")

        data = snipe_data.edited_messages[index - 1]
        author = data["author"]

        embed = discord.Embed(
            color=_color("EMBED_INFO_COLOR"),
            timestamp=data["timestamp"]
        )
        embed.set_author(name=author.display_name, icon_url=author.display_avatar.url)
        embed.add_field(name="Before", value=data["before"][:1024] or "*Empty*", inline=False)
        embed.add_field(name="After", value=data["after"][:1024] or "*Empty*", inline=False)

        footer_text = f"Edit Snipe {index}/{len(snipe_data.edited_messages)}"
        if len(snipe_data.edited_messages) > 1:
            footer_text += f" • Use editsnipe <1-{len(snipe_data.edited_messages)}> to view others"
        embed.set_footer(text=footer_text)

        await ctx.send(embed=embed)

    @commands.command(
        name="reactionsnipe",
        aliases=["rs", "rsnipe"],
        help="Snipe a removed reaction",
        extras={"parameters": "index", "usage": "reactionsnipe [index]"},
    )
    async def reactionsnipe(self, ctx: TormentContext, index: int = 1):
        snipe_data = self.snipes.get(ctx.channel.id)
        if not snipe_data or not snipe_data.reaction_removes:
            return await ctx.warn("There are no removed reactions to snipe")

        if index < 1 or index > len(snipe_data.reaction_removes):
            return await ctx.warn(f"Invalid index. Available snipes: **1-{len(snipe_data.reaction_removes)}**")

        data = snipe_data.reaction_removes[index - 1]
        user = data["user"]

        embed = discord.Embed(
            color=_color("EMBED_INFO_COLOR"),
            description=f"{user.mention} removed {data['emoji']} from **{data['message_author'].display_name}**'s message",
            timestamp=data["timestamp"]
        )
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)

        if data["message_content"]:
            embed.add_field(name="Message", value=data["message_content"], inline=False)

        footer_text = f"Reaction Snipe {index}/{len(snipe_data.reaction_removes)}"
        if len(snipe_data.reaction_removes) > 1:
            footer_text += f" • Use reactionsnipe <1-{len(snipe_data.reaction_removes)}> to view others"
        embed.set_footer(text=footer_text)

        await ctx.send(embed=embed)

    @commands.command(
        name="clearsnipes",
        aliases=["cs"],
        help="Clear all snipes in the channel",
        extras={"parameters": "n/a", "usage": "clearsnipes"},
    )
    @commands.has_permissions(manage_messages=True)
    async def clearsnipes(self, ctx: TormentContext):
        if ctx.channel.id in self.snipes:
            del self.snipes[ctx.channel.id]
        await ctx.message.add_reaction("👍")

    @commands.group(
        name="birthday",
        aliases=["bday", "bd"],
        invoke_without_command=True,
        help="View your or another member's birthday",
        extras={"parameters": "[member]", "usage": "birthday [member]"},
    )
    async def birthday(self, ctx: TormentContext, member: discord.Member = None) -> None:
        target = member or ctx.author
        
        query = "SELECT birthday FROM birthday_users WHERE user_id = $1"
        birthday = await self.storage.pool.fetchval(query, target.id)
        
        if not birthday:
            if target == ctx.author:
                return await ctx.warn(f"You have not set your birthday yet\nUse `{ctx.prefix}birthday set <date>` to set it")
            return await ctx.warn(f"{target.mention} hasn't set their birthday yet")
        
        from discord.utils import utcnow, format_dt
        current = utcnow()
        next_birthday = current.replace(month=birthday.month, day=birthday.day)
        if next_birthday <= current:
            next_birthday = next_birthday.replace(year=current.year + 1)
        
        days_until = (next_birthday - current).days
        
        if days_until == 0:
            phrase = "today, happy birthday! 🎊"
        elif days_until == 1:
            phrase = "tomorrow, happy early birthday! 🎊"
        else:
            phrase = f"`{next_birthday.strftime('%B')} {next_birthday.day}`, that's {format_dt(next_birthday, 'R')}"
        
        if target == ctx.author:
            return await ctx.success(f"Your birthday is {phrase}")
        else:
            return await ctx.success(f"{target.mention}'s birthday is {phrase}")

    @birthday.command(
        name="set",
        help="Set your birthday",
        extras={"parameters": "date", "usage": "birthday set (date)"},
    )
    async def birthday_set(self, ctx: TormentContext, *, date: str) -> None:
        try:
            birthday = dateparser.parse(date)
            if not birthday:
                raise ValueError
        except (ValueError, KeyError):
            return await ctx.warn("The provided date is invalid")
        
        existing = await self.storage.pool.fetchval(
            "SELECT birthday FROM birthday_users WHERE user_id = $1", ctx.author.id
        )
        
        if existing:
            if not await ctx.confirm(f"You already have a birthday set. Are you sure you want to change it to `{birthday.strftime('%B')} {birthday.day}`?"):
                return
            
            query = "UPDATE birthday_users SET birthday = $2 WHERE user_id = $1"
            await self.storage.pool.execute(query, ctx.author.id, birthday)
            return await ctx.success(f"Your birthday has been updated to `{birthday.strftime('%B')} {birthday.day}`")
        
        if not await ctx.confirm(f"Are you sure you want to set your birthday as `{birthday.strftime('%B')} {birthday.day}`?"):
            return
        
        query = "INSERT INTO birthday_users (user_id, birthday) VALUES ($1, $2)"
        await self.storage.pool.execute(query, ctx.author.id, birthday)
        
        return await ctx.success(f"Your birthday has been set to `{birthday.strftime('%B')} {birthday.day}`")

    @birthday.command(
        name="list",
        aliases=["all"],
        help="View all upcoming birthdays in this server",
        extras={"parameters": "n/a", "usage": "birthday list"},
    )
    async def birthday_list(self, ctx: TormentContext) -> None:
        query = """
            SELECT * FROM birthday_users
            WHERE user_id = ANY($1::BIGINT[])
            ORDER BY EXTRACT(MONTH FROM birthday), EXTRACT(DAY FROM birthday)
        """
        records = await self.storage.pool.fetch(query, [member.id for member in ctx.guild.members])
        
        from discord.utils import utcnow
        now = utcnow()
        birthdays = []
        
        for record in records:
            member = ctx.guild.get_member(record["user_id"])
            if member:
                birthday = record["birthday"]
                next_bday = now.replace(month=birthday.month, day=birthday.day)
                if next_bday <= now:
                    next_bday = next_bday.replace(year=now.year + 1)
                days = (next_bday - now).days
                
                if days == 0:
                    day_str = "Today"
                else:
                    day_str = f"{days} days"
                
                birthdays.append(f"**{member}** - {birthday.strftime('%B')} {birthday.day} ({day_str})")
        
        if not birthdays:
            return await ctx.warn("No upcoming birthdays in this server")
        
        embed = discord.Embed(
            title="Upcoming Birthdays",
            color=_color("EMBED_INFO_COLOR")
        )
        
        from bot.helpers.paginator import Paginator
        paginator = Paginator(ctx, birthdays, embed)
        return await paginator.start()

    @birthday.group(
        name="role",
        invoke_without_command=True,
        help="Set a role to be assigned to members on their birthday",
        extras={"parameters": "role", "usage": "birthday role (role)"},
    )
    @commands.has_permissions(manage_roles=True)
    async def birthday_role(self, ctx: TormentContext, role: discord.Role) -> None:
        query = """
            INSERT INTO birthday_config (guild_id, role_id)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE
            SET role_id = EXCLUDED.role_id
        """
        await self.storage.pool.execute(query, ctx.guild.id, role.id)
        return await ctx.success(f"Now assigning {role.mention} to members on their birthday")

    @birthday_role.command(
        name="remove",
        aliases=["delete", "del", "rm"],
        help="Remove the birthday role",
        extras={"parameters": "n/a", "usage": "birthday role remove"},
    )
    @commands.has_permissions(manage_roles=True)
    async def birthday_role_remove(self, ctx: TormentContext) -> None:
        query = "UPDATE birthday_config SET role_id = NULL WHERE guild_id = $1"
        result = await self.storage.pool.execute(query, ctx.guild.id)
        if result == "UPDATE 0":
            return await ctx.warn("No birthday role is set")
        return await ctx.success("No longer assigning a role on birthdays")

    @birthday.group(
        name="channel",
        invoke_without_command=True,
        help="Set a channel to send birthday messages in",
        extras={"parameters": "channel", "usage": "birthday channel (channel)"},
    )
    @commands.has_permissions(manage_channels=True)
    async def birthday_channel(self, ctx: TormentContext, channel: discord.TextChannel) -> None:
        query = """
            INSERT INTO birthday_config (guild_id, channel_id)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE
            SET channel_id = EXCLUDED.channel_id
        """
        await self.storage.pool.execute(query, ctx.guild.id, channel.id)
        return await ctx.success(f"Now sending birthday messages in {channel.mention}")

    @birthday_channel.command(
        name="remove",
        aliases=["delete", "del", "rm"],
        help="Remove the birthday message channel",
        extras={"parameters": "n/a", "usage": "birthday channel remove"},
    )
    @commands.has_permissions(manage_channels=True)
    async def birthday_channel_remove(self, ctx: TormentContext) -> None:
        query = "UPDATE birthday_config SET channel_id = NULL WHERE guild_id = $1"
        result = await self.storage.pool.execute(query, ctx.guild.id)
        if result == "UPDATE 0":
            return await ctx.warn("No birthday message channel is set")
        return await ctx.success("No longer sending birthday messages")

    @birthday.group(
        name="message",
        aliases=["msg", "template"],
        invoke_without_command=True,
        help="Set a custom message to send on birthdays",
        extras={"parameters": "script", "usage": "birthday message (script)"},
    )
    @commands.has_permissions(manage_messages=True)
    async def birthday_message(self, ctx: TormentContext, *, script_text: str) -> None:
        script = await Script().convert(ctx, script_text)
        
        query = """
            INSERT INTO birthday_config (guild_id, template)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE
            SET template = EXCLUDED.template
        """
        await self.storage.pool.execute(query, ctx.guild.id, script_text)
        return await ctx.success("Now sending a custom message on birthdays")

    @birthday_message.command(
        name="remove",
        aliases=["delete", "del", "rm"],
        help="Remove the custom birthday message",
        extras={"parameters": "n/a", "usage": "birthday message remove"},
    )
    @commands.has_permissions(manage_messages=True)
    async def birthday_message_remove(self, ctx: TormentContext) -> None:
        query = "UPDATE birthday_config SET template = NULL WHERE guild_id = $1"
        result = await self.storage.pool.execute(query, ctx.guild.id)
        if result == "UPDATE 0":
            return await ctx.warn("No custom birthday message is set")
        return await ctx.success("Reset the birthday message to the default")

    @commands.group(
        name="emoji",
        invoke_without_command=True,
        help="Manage server emojis.",
        extras={"parameters": "n/a", "usage": "emoji"},
    )
    @commands.has_permissions(manage_emojis=True)
    async def emoji_group(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @emoji_group.command(
        name="steal",
        help="Steal an emoji from another server.",
        extras={"parameters": "emoji", "usage": "emoji steal <emoji>"},
    )
    @commands.has_permissions(manage_emojis=True)
    async def emoji_steal(self, ctx: TormentContext, emoji: str) -> None:
        url = parse_emoji_url(emoji)
        if not url:
            await ctx.warn("Please provide a custom emoji!")
            return

        name_match = re.search(r"<a?:([a-zA-Z0-9_]+):\d+>", emoji)
        name = name_match.group(1) if name_match else "stolen_emoji"

        image = await fetch_image(url)
        if not image:
            await ctx.warn("Failed to download the emoji image.")
            return

        try:
            new_emoji = await ctx.guild.create_custom_emoji(name=name, image=image)
        except discord.Forbidden:
            await ctx.warn("I'm missing the permission: `Manage Expressions`!")
            return
        except discord.HTTPException as e:
            await ctx.warn(f"Failed to add emoji: {e}")
            return

        embed = discord.Embed(
            description=f"Added {new_emoji} **{new_emoji.name}** to the server.",
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @emoji_group.command(
        name="addmany",
        help="Steal multiple emojis from another server.",
        extras={"parameters": "emojis", "usage": "emoji addmany <emojis>"},
    )
    @commands.has_permissions(manage_emojis=True)
    async def emoji_addmany(self, ctx: TormentContext, *, emojis: str) -> None:
        matches = re.findall(r"<(a?):([a-zA-Z0-9_]+):(\d+)>", emojis)
        if not matches:
            await ctx.warn("There were no custom emojis found in this server.")
            return

        added: list[str] = []
        failed: list[str] = []

        for animated, name, emoji_id in matches:
            ext = "gif" if animated else "png"
            url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=96"
            image = await fetch_image(url)
            if not image:
                failed.append(name)
                continue
            try:
                new_emoji = await ctx.guild.create_custom_emoji(name=name, image=image)
                added.append(str(new_emoji))
            except discord.HTTPException:
                failed.append(name)

        lines: list[str] = []
        if added:
            lines.append(f"**Added** ({len(added)}): {' '.join(added)}")
        if failed:
            lines.append(f"**Failed** ({len(failed)}): {', '.join(f'`{n}`' for n in failed)}")

        embed = discord.Embed(
            description="\n".join(lines) or "Nothing was processed.",
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @emoji_group.command(
        name="removeduplicates",
        aliases=["rmdupes"],
        help="Remove duplicate emojis from your server.",
        extras={"parameters": "n/a", "usage": "emoji removeduplicates"},
    )
    @commands.has_permissions(manage_emojis=True)
    async def emoji_removeduplicates(self, ctx: TormentContext) -> None:
        seen_names: dict[str, discord.Emoji] = {}
        to_delete: list[discord.Emoji] = []

        for emoji in ctx.guild.emojis:
            key = emoji.name.lower()
            if key in seen_names:
                to_delete.append(emoji)
            else:
                seen_names[key] = emoji

        if not to_delete:
            await ctx.warn("There's no **duplicate** emojis found in this server.")
            return

        removed: list[str] = []
        for emoji in to_delete:
            try:
                await emoji.delete()
                removed.append(f"`:{emoji.name}:`")
            except discord.HTTPException:
                pass

        word = "emoji" if len(removed) == 1 else "emojis"
        embed = discord.Embed(
            description=f"Removed **{len(removed)}** duplicate {word} from this server.",
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @emoji_group.command(
        name="remove",
        aliases=["rm"],
        help="Remove an emoji from your server.",
        extras={"parameters": "emoji", "usage": "emoji remove <emoji>"},
    )
    @commands.has_permissions(manage_emojis=True)
    async def emoji_remove(self, ctx: TormentContext, emoji: discord.Emoji) -> None:
        name = emoji.name
        try:
            await emoji.delete()
        except discord.Forbidden:
            await ctx.warn("I'm missing the permission: `Manage Expressions`!")
            return
        except discord.HTTPException as e:
            await ctx.warn(f"Failed to remove emoji: {e}")
            return

        embed = discord.Embed(
            description=f"Removed the emoji **:{name}:** from this server.",
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @emoji_group.command(
        name="rename",
        aliases=["rn"],
        help="Rename an emoji.",
        extras={"parameters": "emoji, new_name", "usage": "emoji rename <emoji> <new name>"},
    )
    @commands.has_permissions(manage_emojis=True)
    async def emoji_rename(
        self,
        ctx: TormentContext,
        emoji: discord.Emoji,
        *,
        new_name: str,
    ) -> None:
        new_name = re.sub(r"[^a-zA-Z0-9_]", "_", new_name.strip())[:32]
        if len(new_name) < 2:
            await ctx.warn("The new emoji name must be at least 2 characters!")
            return

        old_name = emoji.name
        try:
            await emoji.edit(name=new_name)
        except discord.Forbidden:
            await ctx.warn("I'm missing the permission: `Manage Expressions`!")
            return
        except discord.HTTPException as e:
            await ctx.warn(f"Failed to rename emoji: {e}")
            return

        embed = discord.Embed(
            description=f"Renamed **:{old_name}:** to **:{new_name}:**.",
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @emoji_group.command(
        name="add",
        help="Add an emoji to your server.",
        extras={"parameters": "url", "usage": "emoji add <url>"},
    )
    @commands.has_permissions(manage_emojis=True)
    async def emoji_add(self, ctx: TormentContext, url: str, *, name: str | None = None) -> None:
        if not name:
            filename = url.rstrip("/").split("/")[-1].split("?")[0]
            name = re.sub(r"\.[^.]+$", "", filename)
            name = re.sub(r"[^a-zA-Z0-9_]", "_", name)[:32]

        name = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())[:32]
        if len(name) < 2:
            name = "emoji"

        image = await fetch_image(url)
        if not image:
            await ctx.warn("Failed to download the image from that URL.")
            return

        try:
            new_emoji = await ctx.guild.create_custom_emoji(name=name, image=image)
        except discord.Forbidden:
            await ctx.warn("I'm missing the permission: `Manage Expressions`!")
            return
        except discord.HTTPException as e:
            await ctx.warn(f"Failed to add emoji: {e}")
            return

        embed = discord.Embed(
            description=f"Added {new_emoji} **:{new_emoji.name}:** to the server.",
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @emoji_group.command(
        name="removemany",
        aliases=["rmmany"],
        help="Remove multiple emojis from your server.",
        extras={"parameters": "emojis", "usage": "emoji removemany <emojis>"},
    )
    @commands.has_permissions(manage_emojis=True)
    async def emoji_removemany(
        self,
        ctx: TormentContext,
        *emojis: discord.Emoji,
    ) -> None:
        if not emojis:
            await ctx.warn("Please provide at least one emoji to remove.")
            return

        removed: list[str] = []
        failed: list[str] = []

        for emoji in emojis:
            try:
                await emoji.delete()
                removed.append(f"`:{emoji.name}:`")
            except discord.HTTPException:
                failed.append(f"`:{emoji.name}:`")

        lines: list[str] = []
        if removed:
            lines.append(f"**Removed** ({len(removed)}): {', '.join(removed)}")
        if failed:
            lines.append(f"**Failed** ({len(failed)}): {', '.join(failed)}")

        embed = discord.Embed(
            description="\n".join(lines) or "Nothing was processed.",
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @emoji_group.command(
        name="recolor",
        aliases=["tint", "color"],
        help="Recolor an emoji to a specific hex color.",
        extras={"parameters": "hex, emoji", "usage": "emoji recolor (hex) (emoji)"},
    )
    @commands.has_permissions(manage_emojis=True)
    async def emoji_recolor(
        self,
        ctx: TormentContext,
        hex_color: str,
        emoji: str,
    ) -> None:
        hex_color = hex_color.lstrip("#")
        if not re.fullmatch(r"[0-9a-fA-F]{6}", hex_color):
            await ctx.warn("Please provide a valid hex color (e.g. `#FF5733`).")
            return

        target_r = int(hex_color[0:2], 16)
        target_g = int(hex_color[2:4], 16)
        target_b = int(hex_color[4:6], 16)

        url = parse_emoji_url(emoji)
        if not url:
            await ctx.warn("Please provide a custom emoji!")
            return

        name_match = re.search(r"<a?:([a-zA-Z0-9_]+):\d+>", emoji)
        name = name_match.group(1) if name_match else "recolored"

        image_bytes = await fetch_image(url)
        if not image_bytes:
            await ctx.warn("Failed to download the emoji image.")
            return

        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        r, g, b, a = img.split()

        target_h, target_s, _ = colorsys.rgb_to_hsv(
            target_r / 255, target_g / 255, target_b / 255
        )

        pixels = list(img.getdata())
        new_pixels: list[tuple[int, int, int, int]] = []

        for pr, pg, pb, pa in pixels:
            if pa == 0:
                new_pixels.append((pr, pg, pb, pa))
                continue
            _, _, v = colorsys.rgb_to_hsv(pr / 255, pg / 255, pb / 255)
            nr, ng, nb = colorsys.hsv_to_rgb(target_h, target_s, v)
            new_pixels.append((int(nr * 255), int(ng * 255), int(nb * 255), pa))

        img.putdata(new_pixels)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        view = AddToServerView(
            author_id=ctx.author.id,
            image_bytes=buf.getvalue(),
            emoji_name=name,
            guild=ctx.guild,
        )

        await ctx.reply(
            file=discord.File(buf, filename=f"{name}_recolored.png"),
            view=view,
            mention_author=False,
        )

    @commands.group(
        name="reminder",
        aliases=["remind", "remindme"],
        invoke_without_command=True,
        help="Set a reminder for a specific duration",
        extras={"parameters": "duration, text", "usage": "reminder (duration) (text)"},
    )
    @commands.check(can_dm)
    async def reminder(self, ctx: TormentContext, duration: str, *, text: str) -> None:
        try:
            duration_delta = parse_duration_to_timedelta(duration)
        except ValueError as e:
            return await ctx.warn(str(e))
        
        expires_at = datetime.now(tz=timezone.utc) + duration_delta
        
        query = """
            INSERT INTO reminders (user_id, text, jump_url, expires_at)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """
        reminder_id = await self.storage.pool.fetchval(
            query, ctx.author.id, text, ctx.message.jump_url, expires_at
        )
        
        reminder_data = {
            "id": reminder_id,
            "user_id": ctx.author.id,
            "text": text,
            "jump_url": ctx.message.jump_url,
            "expires_at": expires_at,
            "created_at": datetime.now(tz=timezone.utc)
        }
        self.reminders.append(reminder_data)
        
        from discord.utils import format_dt
        return await ctx.success(
            f"I'll remind you about that {format_dt(expires_at, 'R')}\n"
            f"Use `{ctx.prefix}reminder cancel {reminder_id}` to cancel it early"
        )

    @reminder.command(
        name="cancel",
        aliases=["delete", "remove", "del", "rm"],
        help="Cancel a reminder via its ID",
        extras={"parameters": "id", "usage": "reminder cancel (id)"},
    )
    async def reminder_cancel(self, ctx: TormentContext, reminder_id: int) -> None:
        query = "DELETE FROM reminders WHERE id = $1 AND user_id = $2"
        result = await self.storage.pool.execute(query, reminder_id, ctx.author.id)
        
        if result == "DELETE 0":
            return await ctx.warn("You don't have a reminder with that ID")
        
        for reminder in self.reminders:
            if reminder["id"] == reminder_id and reminder["user_id"] == ctx.author.id:
                self.reminders.remove(reminder)
                break
        
        return await ctx.success(f"Reminder with ID `{reminder_id}` has been cancelled")

    @reminder.command(
        name="list",
        aliases=["all"],
        help="View all your active reminders",
        extras={"parameters": "n/a", "usage": "reminder list"},
    )
    async def reminder_list(self, ctx: TormentContext) -> None:
        query = """
            SELECT * FROM reminders
            WHERE user_id = $1 AND expires_at > NOW()
            ORDER BY expires_at
        """
        records = await self.storage.pool.fetch(query, ctx.author.id)
        
        if not records:
            return await ctx.warn("You don't have any active reminders")
        
        from discord.utils import format_dt
        reminder_lines = []
        for record in records:
            text_preview = record["text"][:24] + "..." if len(record["text"]) > 24 else record["text"]
            reminder_lines.append(
                f"`{str(record['id']).zfill(2)}` {text_preview} {format_dt(record['expires_at'], 'R')}"
            )
        
        embed = discord.Embed(
            title="Reminders",
            color=EMBED_COLOR
        )
        
        from bot.helpers.paginator import Paginator
        paginator = Paginator(ctx, reminder_lines, embed, counter=False)
        return await paginator.start()

    @commands.group(
        name="shutup",
        aliases=["stfu"],
        invoke_without_command=True,
        help="Toggle automatically deleting a member's messages",
        extras={"parameters": "member", "usage": "shutup (member)"},
    )
    @commands.has_permissions(manage_messages=True)
    async def shutup(self, ctx: TormentContext, *, member: discord.Member) -> None:
        record = await self.storage.pool.fetchrow(
            "SELECT * FROM shutup WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id, member.id,
        )
        if record:
            await self.storage.pool.execute(
                "DELETE FROM shutup WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id, member.id,
            )
            return await ctx.success(f"{member.mention} has been removed from shutup")
        await self.storage.pool.execute(
            "INSERT INTO shutup (guild_id, user_id) VALUES ($1, $2)",
            ctx.guild.id, member.id,
        )
        return await ctx.success(f"{member.mention} has been shut up")

    @shutup.command(
        name="list",
        help="List all shutup members in the server",
        extras={"parameters": "n/a", "usage": "shutup list"},
    )
    async def shutup_list(self, ctx: TormentContext) -> None:
        records = await self.storage.pool.fetch(
            "SELECT * FROM shutup WHERE guild_id = $1", ctx.guild.id,
        )
        if not records:
            return await ctx.warn("Nobody is in shutup in this server")
        members = [
            f"{m.mention} (`{m.id}`)"
            for r in records
            if (m := ctx.guild.get_member(r["user_id"]))
        ]
        if not members:
            return await ctx.warn("Nobody is in shutup in this server")
        embed = discord.Embed(title="Shutup Members", color=EMBED_COLOR)
        paginator = Paginator(ctx, members, embed)
        await paginator.start()

    @shutup.command(
        name="reset",
        help="Clear the shutup list",
        extras={"parameters": "n/a", "usage": "shutup reset"},
    )
    @commands.has_permissions(manage_messages=True)
    async def shutup_reset(self, ctx: TormentContext) -> None:
        data = await self.storage.pool.fetch(
            "SELECT * FROM shutup WHERE guild_id = $1", ctx.guild.id,
        )
        if not data:
            return await ctx.warn("There is no one in shutup in this server")
        await self.storage.pool.execute(
            "DELETE FROM shutup WHERE guild_id = $1", ctx.guild.id,
        )
        return await ctx.success("Shutup list has been reset")

    @commands.Cog.listener("on_message")
    async def shutup_listener(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        record = await self.storage.pool.fetchrow(
            "SELECT * FROM shutup WHERE guild_id = $1 AND user_id = $2",
            message.guild.id, message.author.id,
        )
        if not record:
            return
        key = f"{message.author.id}:{message.channel.id}"
        now = datetime.now(tz=timezone.utc).timestamp()
        last = self._shutup_rate.get(key, 0)
        if now - last < 3:
            return
        self._shutup_rate[key] = now
        try:
            await message.delete()
        except discord.HTTPException:
            pass

    async def _fetch_sport(self, ctx: TormentContext, sport: str) -> None:
        url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/scoreboard"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
        if not data.get("events"):
            return await ctx.warn("There isn't any ongoing event for this sport.")
        embeds: list[discord.Embed] = []
        for event in data["events"]:
            competitors = event["competitions"][0]["competitors"]
            teams = [c["team"] for c in competitors]
            embed = discord.Embed(
                url=event["links"][0]["href"] if event.get("links") else None,
                title=event["name"],
                color=EMBED_COLOR,
                timestamp=datetime.fromisoformat(event["date"].replace("Z", "+00:00")),
            )
            embed.set_author(name=teams[0]["displayName"], icon_url=teams[0].get("logo"))
            embed.set_thumbnail(url=teams[1].get("logo"))
            embed.add_field(name="Status", value=event["status"]["type"]["shortDetail"])
            embed.add_field(name="Teams", value=f"{teams[0]['abbreviation']} vs {teams[1]['abbreviation']}")
            embed.add_field(name="Score", value=f"{competitors[0]['score']} - {competitors[1]['score']}")
            embeds.append(embed)
        paginator = Paginator(ctx, embeds)
        await paginator.start()

    @commands.group(
        name="basketball",
        aliases=["nba", "bb"],
        invoke_without_command=True,
        help="National Basketball Association scores",
        extras={"parameters": "n/a", "usage": "basketball"},
    )
    async def basketball(self, ctx: TormentContext) -> None:
        await self._fetch_sport(ctx, "basketball/nba")

    @basketball.command(
        name="women",
        aliases=["wnba", "wbb"],
        help="Women's National Basketball Association scores",
        extras={"parameters": "n/a", "usage": "basketball women"},
    )
    async def basketball_women(self, ctx: TormentContext) -> None:
        await self._fetch_sport(ctx, "basketball/wnba")

    @basketball.group(
        name="college",
        aliases=["cb", "cbb"],
        invoke_without_command=True,
        help="College Basketball scores",
        extras={"parameters": "n/a", "usage": "basketball college"},
    )
    async def basketball_college(self, ctx: TormentContext) -> None:
        await self._fetch_sport(ctx, "basketball/mens-college-basketball")

    @basketball_college.command(
        name="women",
        aliases=["cbbw", "cbw"],
        help="Women's College Basketball scores",
        extras={"parameters": "n/a", "usage": "basketball college women"},
    )
    async def basketball_college_women(self, ctx: TormentContext) -> None:
        await self._fetch_sport(ctx, "basketball/womens-college-basketball")

    @commands.group(
        name="football",
        aliases=["nfl", "fb"],
        invoke_without_command=True,
        help="National Football League scores",
        extras={"parameters": "n/a", "usage": "football"},
    )
    async def football(self, ctx: TormentContext) -> None:
        await self._fetch_sport(ctx, "football/nfl")

    @football.group(
        name="college",
        aliases=["cfb", "cf"],
        invoke_without_command=True,
        help="College Football scores",
        extras={"parameters": "n/a", "usage": "football college"},
    )
    async def football_college(self, ctx: TormentContext) -> None:
        await self._fetch_sport(ctx, "football/college-football")

    @commands.command(
        name="soccer",
        aliases=["futbol"],
        help="Soccer scores",
        extras={"parameters": "n/a", "usage": "soccer"},
    )
    async def soccer(self, ctx: TormentContext) -> None:
        await self._fetch_sport(ctx, "soccer/eng.1")

    @commands.command(
        name="hockey",
        aliases=["nhl", "hock"],
        help="National Hockey League scores",
        extras={"parameters": "n/a", "usage": "hockey"},
    )
    async def hockey(self, ctx: TormentContext) -> None:
        await self._fetch_sport(ctx, "hockey/nhl")

    @commands.command(
        name="baseball",
        aliases=["mlb", "baseb"],
        help="Major League Baseball scores",
        extras={"parameters": "n/a", "usage": "baseball"},
    )
    async def baseball(self, ctx: TormentContext) -> None:
        await self._fetch_sport(ctx, "baseball/mlb")

    @commands.group(
        name="timezone",
        aliases=["tz"],
        invoke_without_command=True,
        help="View your or another user's current time",
        extras={"parameters": "[member]", "usage": "timezone [member]"},
    )
    async def timezone(self, ctx: TormentContext, *, member: discord.Member = None) -> None:
        member = member or ctx.author
        row = await self.storage.pool.fetchrow(
            "SELECT timezone FROM user_timezones WHERE user_id = $1", member.id
        )
        if not row:
            if member == ctx.author:
                return await ctx.warn(f"You haven't set a timezone yet. Use `{ctx.prefix}timezone set <timezone>`")
            return await ctx.warn(f"**{member.display_name}** hasn't set a timezone yet")
        tz = pytz.timezone(row["timezone"])
        current_time = datetime.now(tz)
        if member == ctx.author:
            label = "Your"
        else:
            label = f"{member.mention}'s"
        return await ctx.success(f"{label} current time is **{current_time.strftime('%B %d, %I:%M %p')}**")

    @timezone.command(
        name="set",
        help="Set your timezone",
        extras={"parameters": "timezone", "usage": "timezone set (timezone)"},
    )
    async def timezone_set(self, ctx: TormentContext, *, timezone_str: str) -> None:
        valid_timezones = set(pytz.all_timezones)
        timezone_lower = timezone_str.lower().replace(" ", "_")
        matched_tz = None
        for tz in valid_timezones:
            if tz.lower() == timezone_lower:
                matched_tz = tz
                break
        if not matched_tz:
            matches = [tz for tz in valid_timezones if timezone_lower in tz.lower()]
            if len(matches) == 1:
                matched_tz = matches[0]
            elif 1 < len(matches) <= 10:
                tz_list = "\n".join(f"`{tz}`" for tz in sorted(matches)[:10])
                return await ctx.warn(f"Multiple timezones found, be more specific:\n{tz_list}")
            elif len(matches) > 10:
                return await ctx.warn(f"Too many matches. Use `{ctx.prefix}timezone list <region>` to browse")
            else:
                return await ctx.warn(f"Invalid timezone. Use `{ctx.prefix}timezone list <region>` to browse")
        await self.storage.pool.execute(
            """
            INSERT INTO user_timezones (user_id, timezone)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET timezone = $2
            """,
            ctx.author.id, matched_tz,
        )
        tz = pytz.timezone(matched_tz)
        current_time = datetime.now(tz)
        return await ctx.success(f"Your timezone has been set to `{matched_tz}` (Current time: **{current_time.strftime('%B %d, %I:%M %p')}**)")

    @timezone.command(
        name="list",
        help="List available timezones by region",
        extras={"parameters": "[region]", "usage": "timezone list [region]"},
    )
    async def timezone_list(self, ctx: TormentContext, *, region: str = None) -> None:
        valid_timezones = pytz.all_timezones
        if not region:
            regions = sorted({tz.split("/")[0] for tz in valid_timezones if "/" in tz})
            embed = discord.Embed(
                title="Timezone Regions",
                description="\n".join(f"`{r}`" for r in regions),
                color=EMBED_COLOR,
            )
            embed.set_footer(text=f"Use {ctx.prefix}timezone list <region> to see timezones in a region")
            return await ctx.send(embed=embed)
        region_lower = region.lower()
        matching = sorted(tz for tz in valid_timezones if region_lower in tz.lower())
        if not matching:
            return await ctx.warn(f"No timezones found for `{region}`")
        pages = []
        per_page = 15
        total_pages = (len(matching) + per_page - 1) // per_page
        for i in range(0, len(matching), per_page):
            chunk = matching[i:i + per_page]
            embed = discord.Embed(
                title=f"Timezones matching '{region}'",
                description="\n".join(f"`{tz}`" for tz in chunk),
                color=EMBED_COLOR,
            )
            embed.set_footer(text=f"Page {len(pages) + 1}/{total_pages} • {len(matching)} results")
            pages.append(embed)
        return await ctx.paginate(pages)


    DISBOARD_BOT_ID = 302050872383242240

    @tasks.loop(minutes=2)
    async def _check_bumps(self) -> None:
        records = await self.storage.pool.fetch(
            """
            SELECT * FROM bump_config
            WHERE status = TRUE
            AND next_bump IS NOT NULL
            AND next_bump < NOW()
            """
        )
        for record in records:
            guild = self.bot.get_guild(record["guild_id"])
            if not guild:
                continue
            channel = None
            for cid in [record["channel_id"], record["last_channel_id"]]:
                if cid:
                    channel = guild.get_channel(cid)
                    if channel:
                        break
            if not channel:
                continue
            last_user = guild.get_member(record["last_user_id"]) if record["last_user_id"] else None
            msg = record["message"] or "It's been 2 hours, someone bump the server using </bump:947088344167366698>!"
            if last_user:
                msg = msg.replace("{user}", last_user.mention).replace("{user.name}", last_user.display_name)
            msg = msg.replace("{server}", guild.name).replace("{bump}", "</bump:947088344167366698>")
            try:
                embed = discord.Embed(color=EMBED_COLOR, description=f"⏰ {msg}")
                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.all())
            except discord.HTTPException:
                pass
            await self.storage.pool.execute(
                "UPDATE bump_config SET next_bump = NOW() + INTERVAL '2 hours' WHERE guild_id = $1",
                guild.id,
            )

    @_check_bumps.before_loop
    async def _before_check_bumps(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener("on_message")
    async def _bump_listener(self, message: discord.Message) -> None:
        if not message.guild or message.author.id != self.DISBOARD_BOT_ID:
            return
        if not message.embeds:
            return
        embed = message.embeds[0]
        if not embed.description or "Bump done" not in embed.description:
            return
        user = None
        if message.interaction_metadata:
            user = message.interaction_metadata.user
        elif message.interaction:
            user = message.interaction.user
        if not user:
            return
        await self.storage.pool.execute(
            "INSERT INTO bump_stats (guild_id, user_id) VALUES ($1, $2)",
            message.guild.id, user.id,
        )
        record = await self.storage.pool.fetchrow(
            """
            UPDATE bump_config
            SET last_user_id = $2, last_channel_id = $3, next_bump = NOW() + INTERVAL '2 hours'
            WHERE guild_id = $1 AND status = TRUE
            RETURNING thank_message
            """,
            message.guild.id, user.id, message.channel.id,
        )
        if not record or not record["thank_message"]:
            return
        stats = await self.storage.pool.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM bump_stats WHERE guild_id = $1 AND user_id = $2) AS user_bumps,
                (SELECT COUNT(*) FROM bump_stats WHERE guild_id = $1) AS total_bumps
            """,
            message.guild.id, user.id,
        )
        thank_msg = record["thank_message"]
        thank_msg = (
            thank_msg
            .replace("{user}", user.mention)
            .replace("{user.name}", user.display_name)
            .replace("{server}", message.guild.name)
            .replace("{bumps}", str(stats["total_bumps"]))
            .replace("{user.bumps}", str(stats["user_bumps"]))
        )
        try:
            embed = discord.Embed(color=EMBED_COLOR, description=thank_msg)
            await message.channel.send(embed=embed)
        except discord.HTTPException:
            pass

    @commands.group(
        name="bumpreminder",
        aliases=["bump", "disboard"],
        invoke_without_command=True,
        help="Manage bump reminders for Disboard",
        extras={"parameters": "n/a", "usage": "bumpreminder"},
    )
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def bumpreminder(self, ctx: TormentContext) -> None:
        record = await self.storage.pool.fetchrow(
            "SELECT * FROM bump_config WHERE guild_id = $1", ctx.guild.id
        )
        if not record:
            return await ctx.warn(f"Bump reminders are not set up. Use `{ctx.prefix}bumpreminder toggle` to enable")
        channel = None
        for cid in [record["channel_id"], record["last_channel_id"]]:
            if cid:
                channel = ctx.guild.get_channel(cid)
                if channel:
                    break
        status = "Enabled" if record["status"] else "Disabled"
        channel_text = channel.mention if channel else "Last bumped channel"
        next_bump = discord.utils.format_dt(record["next_bump"], "R") if record["next_bump"] else "Not recorded"
        embed = discord.Embed(title="Bump Reminder Settings", color=EMBED_COLOR)
        embed.add_field(name="Status", value=f"`{status}`", inline=True)
        embed.add_field(name="Channel", value=channel_text, inline=True)
        embed.add_field(name="Next Bump", value=next_bump, inline=True)
        msg = record["message"] or "It's been 2 hours, someone bump the server using /bump!"
        embed.add_field(name="Reminder Message", value=f"```{msg[:200]}```", inline=False)
        if record["thank_message"]:
            embed.add_field(name="Thank Message", value=f"```{record['thank_message'][:200]}```", inline=False)
        await ctx.send(embed=embed)

    @bumpreminder.command(
        name="toggle",
        help="Toggle bump reminders on or off",
        extras={"parameters": "n/a", "usage": "bumpreminder toggle"},
    )
    @commands.has_permissions(manage_channels=True)
    async def bumpreminder_toggle(self, ctx: TormentContext) -> None:
        status = await self.storage.pool.fetchval(
            """
            INSERT INTO bump_config (guild_id, status)
            VALUES ($1, TRUE)
            ON CONFLICT (guild_id)
            DO UPDATE SET status = NOT bump_config.status
            RETURNING status
            """,
            ctx.guild.id,
        )
        if status:
            return await ctx.success("Successfully enabled bump reminders")
        return await ctx.success("Successfully disabled bump reminders")

    @bumpreminder.command(
        name="channel",
        help="Set the channel for bump reminders",
        extras={"parameters": "[channel]", "usage": "bumpreminder channel [channel]"},
    )
    @commands.has_permissions(manage_channels=True)
    async def bumpreminder_channel(self, ctx: TormentContext, channel: discord.TextChannel = None) -> None:
        channel = channel or ctx.channel
        await self.storage.pool.execute(
            """
            INSERT INTO bump_config (guild_id, channel_id)
            VALUES ($1, $2)
            ON CONFLICT (guild_id)
            DO UPDATE SET channel_id = $2
            """,
            ctx.guild.id, channel.id,
        )
        return await ctx.success(f"Successfully set bump reminders to {channel.mention}")

    @bumpreminder.command(
        name="message",
        aliases=["msg"],
        help="Set the bump reminder message",
        extras={"parameters": "message", "usage": "bumpreminder message (message)"},
    )
    @commands.has_permissions(manage_channels=True)
    async def bumpreminder_message(self, ctx: TormentContext, *, message: str) -> None:
        if len(message) > 500:
            return await ctx.warn("Message must be under 500 characters")
        await self.storage.pool.execute(
            """
            INSERT INTO bump_config (guild_id, message)
            VALUES ($1, $2)
            ON CONFLICT (guild_id)
            DO UPDATE SET message = $2
            """,
            ctx.guild.id, message,
        )
        return await ctx.success(f"Successfully set the bump reminder message")

    @bumpreminder.command(
        name="thank",
        aliases=["thanks"],
        help="Set the thank you message after a bump",
        extras={"parameters": "message", "usage": "bumpreminder thank (message)"},
    )
    @commands.has_permissions(manage_channels=True)
    async def bumpreminder_thank(self, ctx: TormentContext, *, message: str) -> None:
        if len(message) > 500:
            return await ctx.warn("Message must be under 500 characters")
        await self.storage.pool.execute(
            """
            INSERT INTO bump_config (guild_id, thank_message)
            VALUES ($1, $2)
            ON CONFLICT (guild_id)
            DO UPDATE SET thank_message = $2
            """,
            ctx.guild.id, message,
        )
        return await ctx.success("Successfully set the thank you message")

    @bumpreminder.command(
        name="reset",
        help="Reset all bump reminder settings",
        extras={"parameters": "n/a", "usage": "bumpreminder reset"},
    )
    @commands.has_permissions(manage_channels=True)
    async def bumpreminder_reset(self, ctx: TormentContext) -> None:
        await self.storage.pool.execute(
            "DELETE FROM bump_config WHERE guild_id = $1", ctx.guild.id
        )
        return await ctx.success("Successfully reset all bump reminder settings")

    @bumpreminder.command(
        name="leaderboard",
        aliases=["lb", "top"],
        help="View the bump leaderboard",
        extras={"parameters": "n/a", "usage": "bumpreminder leaderboard"},
    )
    @commands.guild_only()
    async def bumpreminder_leaderboard(self, ctx: TormentContext) -> None:
        records = await self.storage.pool.fetch(
            """
            SELECT user_id, COUNT(*) AS bumps
            FROM bump_stats
            WHERE guild_id = $1
            GROUP BY user_id
            ORDER BY COUNT(*) DESC
            LIMIT 10
            """,
            ctx.guild.id,
        )
        if not records:
            return await ctx.warn("No one has bumped this server yet")
        lines = []
        for i, record in enumerate(records, 1):
            member = ctx.guild.get_member(record["user_id"])
            if member:
                bumps = record["bumps"]
                lines.append(f"`{i}.` **{member.display_name}** — {bumps} {'bump' if bumps == 1 else 'bumps'}")
        if not lines:
            return await ctx.warn("No bump data found")
        embed = discord.Embed(title="Bump Leaderboard", color=EMBED_COLOR)
        paginator = Paginator(ctx, lines, embed)
        await paginator.start()

    @commands.hybrid_command(
        name="embedbuilder",
        aliases=["eb", "embed"],
        help="Interactively build and send a fully customized embed to any channel",
        extras={"parameters": "n/a", "usage": "embedbuilder"},
    )
    @commands.has_permissions(manage_messages=True)
    async def embedbuilder(self, ctx: TormentContext) -> None:
        view = EmbedBuilderView(ctx)
        msg = await ctx.reply(embed=view.build_status_embed(), view=view)
        view.preview_message = msg


class AddToServerView(discord.ui.View):
    def __init__(
        self,
        author_id: int,
        image_bytes: bytes,
        emoji_name: str,
        guild: discord.Guild,
    ) -> None:
        super().__init__(timeout=300)
        self.author_id = author_id
        self.image_bytes = image_bytes
        self.emoji_name = emoji_name
        self.guild = guild

    @discord.ui.button(label="Add to Server", style=discord.ButtonStyle.secondary)
    async def add_to_server(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                f"{interaction.user.mention}: This isn't your session.",
                ephemeral=True,
            )
            return

        button.disabled = True
        await interaction.response.edit_message(view=self)

        try:
            new_emoji = await self.guild.create_custom_emoji(
                name=self.emoji_name,
                image=self.image_bytes,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"{interaction.user.mention}: I'm missing the permission: `Manage Expressions`!",
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"{interaction.user.mention}: Failed to add emoji: {e}",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"{interaction.user.mention}: Added the recolored **emoji** to this server as "
            f"<:{new_emoji.name}:{new_emoji.id}>.",
            ephemeral=True,
        )


class EmbedBuilderModal(discord.ui.Modal):
    def __init__(self, title: str, fields: list[tuple[str, str, bool, int]]) -> None:
        super().__init__(title=title)
        self._field_keys: list[str] = []
        for label, placeholder, required, max_length in fields:
            key = label.lower().replace(" ", "_")
            self._field_keys.append(key)
            self.add_item(discord.ui.TextInput(
                label=label,
                placeholder=placeholder,
                required=required,
                max_length=max_length,
                style=discord.TextStyle.paragraph if max_length > 100 else discord.TextStyle.short,
            ))
        self.values: dict[str, str] = {}

    async def on_submit(self, interaction: discord.Interaction) -> None:
        for key, child in zip(self._field_keys, self.children):
            self.values[key] = str(child.value).strip() if child.value else ""
        await interaction.response.defer()


class EmbedBuilderView(discord.ui.View):
    def __init__(self, ctx: TormentContext) -> None:
        super().__init__(timeout=300)
        self.ctx = ctx
        self.data: dict = {
            "title": None, "description": None, "color": None,
            "url": None, "author_name": None, "author_icon": None, "author_url": None,
            "footer_text": None, "footer_icon": None,
            "thumbnail": None, "image": None,
            "fields": [],
        }
        self.target_channel: discord.TextChannel | None = None
        self.preview_message: discord.Message | None = None

    def build_embed(self) -> discord.Embed:
        color = EMBED_COLOR
        if self.data["color"]:
            try:
                raw = self.data["color"].lstrip("#")
                color = discord.Color(int(raw, 16))
            except (ValueError, AttributeError):
                pass
        embed = discord.Embed(
            title=self.data["title"] or None,
            description=self.data["description"] or None,
            color=color,
            url=self.data["url"] or None,
        )
        if self.data["author_name"]:
            embed.set_author(
                name=self.data["author_name"],
                icon_url=self.data["author_icon"] or None,
                url=self.data["author_url"] or None,
            )
        if self.data["footer_text"]:
            embed.set_footer(text=self.data["footer_text"], icon_url=self.data["footer_icon"] or None)
        if self.data["thumbnail"]:
            embed.set_thumbnail(url=self.data["thumbnail"])
        if self.data["image"]:
            embed.set_image(url=self.data["image"])
        for field in self.data["fields"]:
            embed.add_field(name=field["name"], value=field["value"], inline=field.get("inline", False))
        return embed

    def build_status_embed(self) -> discord.Embed:
        fields_count = len(self.data["fields"])
        lines = [
            f"**Title:** {self.data['title'] or '`not set`'}",
            f"**Description:** {'`set`' if self.data['description'] else '`not set`'}",
            f"**Color:** {self.data['color'] or '`default`'}",
            f"**URL:** {self.data['url'] or '`not set`'}",
            f"**Author:** {self.data['author_name'] or '`not set`'}",
            f"**Footer:** {self.data['footer_text'] or '`not set`'}",
            f"**Thumbnail:** {'`set`' if self.data['thumbnail'] else '`not set`'}",
            f"**Image:** {'`set`' if self.data['image'] else '`not set`'}",
            f"**Fields:** {fields_count}/25",
            f"**Send to:** {self.target_channel.mention if self.target_channel else '`not set`'}",
        ]
        embed = discord.Embed(
            title="Embed Builder",
            description="\n".join(lines),
            color=EMBED_COLOR,
        )
        embed.set_footer(text="Use the buttons below to edit your embed • Times out in 5 minutes")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This embed builder isn't yours.", ephemeral=True)
            return False
        return True

    async def _refresh(self, interaction: discord.Interaction) -> None:
        await interaction.edit_original_response(embed=self.build_status_embed(), view=self)

    @discord.ui.button(label="Title / Description", style=discord.ButtonStyle.secondary, row=0)
    async def btn_title(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        modal = EmbedBuilderModal("Title & Description", [
            ("Title", "Enter the embed title", False, 256),
            ("Description", "Enter the embed description", False, 4000),
            ("URL", "https://... (makes title a hyperlink)", False, 512),
        ])
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.values.get("title") is not None:
            self.data["title"] = modal.values["title"] or None
        if modal.values.get("description") is not None:
            self.data["description"] = modal.values["description"] or None
        if modal.values.get("url") is not None:
            self.data["url"] = modal.values["url"] or None
        await self._refresh(interaction)

    @discord.ui.button(label="Color", style=discord.ButtonStyle.secondary, row=0)
    async def btn_color(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        modal = EmbedBuilderModal("Embed Color", [
            ("Hex Color", "#9FAB85 or random for a random color", False, 20),
        ])
        await interaction.response.send_modal(modal)
        await modal.wait()
        val = modal.values.get("hex_color", "").strip()
        if val.lower() == "random":
            import random as _random
            self.data["color"] = f"{_random.randint(0, 0xFFFFFF):06X}"
        elif val:
            self.data["color"] = val.lstrip("#")
        await self._refresh(interaction)

    @discord.ui.button(label="Author", style=discord.ButtonStyle.secondary, row=0)
    async def btn_author(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        modal = EmbedBuilderModal("Author", [
            ("Author Name", "Enter the author name", False, 256),
            ("Author Icon URL", "https://... (icon shown next to author name)", False, 512),
            ("Author URL", "https://... (makes author name a hyperlink)", False, 512),
        ])
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.data["author_name"] = modal.values.get("author_name") or None
        self.data["author_icon"] = modal.values.get("author_icon_url") or None
        self.data["author_url"] = modal.values.get("author_url") or None
  
        await self._refresh(interaction)

    @discord.ui.button(label="Footer", style=discord.ButtonStyle.secondary, row=0)
    async def btn_footer(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        modal = EmbedBuilderModal("Footer", [
            ("Footer Text", "Enter the footer text", False, 2048),
            ("Footer Icon URL", "https://... (small icon next to footer text)", False, 512),
        ])
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.data["footer_text"] = modal.values.get("footer_text") or None
        self.data["footer_icon"] = modal.values.get("footer_icon_url") or None
        await self._refresh(interaction)

    @discord.ui.button(label="Images", style=discord.ButtonStyle.secondary, row=1)
    async def btn_images(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        modal = EmbedBuilderModal("Images", [
            ("Thumbnail URL", "https://... (small image top-right)", False, 512),
            ("Image URL", "https://... (large image at the bottom)", False, 512),
        ])
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.data["thumbnail"] = modal.values.get("thumbnail_url") or None
        self.data["image"] = modal.values.get("image_url") or None
        await self._refresh(interaction)

    @discord.ui.button(label="Add Field", style=discord.ButtonStyle.secondary, row=1)
    async def btn_add_field(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if len(self.data["fields"]) >= 25:
            await interaction.response.send_message("You can't have more than 25 fields.", ephemeral=True)
            return
        modal = EmbedBuilderModal("Add Field", [
            ("Field Name", "Enter the field name", True, 256),
            ("Field Value", "Enter the field value", True, 1024),
            ("Inline (yes/no)", "Type yes for inline, no for full width", False, 3),
        ])
        await interaction.response.send_modal(modal)
        await modal.wait()
        name = modal.values.get("field_name")
        value = modal.values.get("field_value")
        inline_raw = modal.values.get("inline_(yes/no)", "no").lower()
        if name and value:
            self.data["fields"].append({
                "name": name,
                "value": value,
                "inline": inline_raw in ("yes", "y", "true", "1"),
            })
        await self._refresh(interaction)

    @discord.ui.button(label="Remove Field", style=discord.ButtonStyle.secondary, row=1)
    async def btn_remove_field(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.data["fields"]:
            await interaction.response.send_message("There are no fields to remove.", ephemeral=True)
            return
        modal = EmbedBuilderModal("Remove Field", [
            ("Field Number", f"Enter a number from 1 to {len(self.data['fields'])}", True, 3),
        ])
        await interaction.response.send_modal(modal)
        await modal.wait()
        raw = modal.values.get("field_number", "")
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(self.data["fields"]):
                self.data["fields"].pop(idx)
        await self._refresh(interaction)

    @discord.ui.button(label="Clear Fields", style=discord.ButtonStyle.secondary, row=1)
    async def btn_clear_fields(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.data["fields"] = []
        await self._refresh(interaction)

    @discord.ui.button(label="Set Channel", style=discord.ButtonStyle.secondary, row=2)
    async def btn_channel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        modal = EmbedBuilderModal("Set Send Channel", [
            ("Channel ID or #mention", "Paste the channel ID or type the name", True, 100),
        ])
        await interaction.response.send_modal(modal)
        await modal.wait()
        raw = modal.values.get("channel_id_or_#mention", "").strip().strip("<#>")
        channel = None
        if raw.isdigit():
            channel = interaction.guild.get_channel(int(raw))
        else:
            channel = discord.utils.get(interaction.guild.text_channels, name=raw.lstrip("#"))
        if not channel:
            await interaction.followup.send("Channel not found.", ephemeral=True)
            return
        self.target_channel = channel
        await self._refresh(interaction)

    @discord.ui.button(label="Preview", style=discord.ButtonStyle.primary, row=2)
    async def btn_preview(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        try:
            embed = self.build_embed()
        except Exception as e:
            await interaction.response.send_message(f"Failed to build embed: {e}", ephemeral=True)
            return
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Send", style=discord.ButtonStyle.success, row=2)
    async def btn_send(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.target_channel:
            await interaction.response.send_message("Set a channel first using the **Set Channel** button.", ephemeral=True)
            return
        try:
            embed = self.build_embed()
        except Exception as e:
            await interaction.response.send_message(f"Failed to build embed: {e}", ephemeral=True)
            return
        if not self.target_channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(f"I don't have permission to send messages in {self.target_channel.mention}.", ephemeral=True)
            return
        await self.target_channel.send(embed=embed)
        for child in self.children:
            child.disabled = True
        done_embed = discord.Embed(
            description=f"Embed successfully sent to {self.target_channel.mention}.",
            color=EMBED_COLOR,
        )
        await interaction.response.edit_message(embed=done_embed, view=self)
        self.stop()

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger, row=2)
    async def btn_reset(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.data = {
            "title": None, "description": None, "color": None,
            "url": None, "author_name": None, "author_icon": None, "author_url": None,
            "footer_text": None, "footer_icon": None,
            "thumbnail": None, "image": None,
            "fields": [],
        }
        self.target_channel = None
        await self._refresh(interaction)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        try:
            if self.preview_message:
                await self.preview_message.edit(view=self)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Utility(bot))
