from __future__ import annotations

import asyncio
import re
import sqlite3
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from pathlib import Path

import discord
from discord.ext import commands


DB = Path(__file__).resolve().parents[2] / ".cache" / "community.db"
INVITE_RE = re.compile(r"(?:discord\.gg|discord(?:app)?\.com/invite)/[\w-]+", re.I)


def card(title: str, body: str) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView()
    view.add_item(discord.ui.Container(discord.ui.TextDisplay(f"## {title}\n{body}")))
    return view


def render_member_message(template: str, member: discord.abc.User, guild: discord.Guild) -> str:
    try:
        return template.format(
            user=member.mention,
            server=guild.name,
            member_count=guild.member_count or 0,
        )
    except (KeyError, ValueError, IndexError):
        return template


class CommunityStore:
    def __init__(self) -> None:
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS community_config (
                    guild_id INTEGER PRIMARY KEY, welcome_channel INTEGER,
                    welcome_message TEXT, goodbye_channel INTEGER, goodbye_message TEXT,
                    autorole_id INTEGER, automod_spam INTEGER NOT NULL DEFAULT 0,
                    automod_mentions INTEGER NOT NULL DEFAULT 0,
                    automod_invites INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS community_daily (
                    guild_id INTEGER NOT NULL, day INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL, messages INTEGER NOT NULL DEFAULT 0,
                    joins INTEGER NOT NULL DEFAULT 0, leaves INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, day, channel_id)
                );
            """)

    @contextmanager
    def connection(self):
        with self.lock:
            db = sqlite3.connect(DB, timeout=30)
            db.row_factory = sqlite3.Row
            try:
                yield db
                db.commit()
            finally:
                db.close()

    def config(self, guild_id: int) -> sqlite3.Row:
        with self.connection() as db:
            db.execute("INSERT OR IGNORE INTO community_config(guild_id) VALUES (?)", (guild_id,))
            return db.execute("SELECT * FROM community_config WHERE guild_id=?", (guild_id,)).fetchone()

    def set_values(self, guild_id: int, **values) -> None:
        self.config(guild_id)
        assignments = ", ".join(f"{key}=?" for key in values)
        with self.connection() as db:
            db.execute(f"UPDATE community_config SET {assignments} WHERE guild_id=?", (*values.values(), guild_id))

    def record(self, guild_id: int, channel_id: int, field: str) -> None:
        day = int(time.time()) // 86400
        with self.connection() as db:
            db.execute("""INSERT INTO community_daily(guild_id,day,channel_id,messages,joins,leaves)
                VALUES(?,?,?,0,0,0) ON CONFLICT(guild_id,day,channel_id) DO NOTHING""",
                (guild_id, day, channel_id))
            db.execute(f"UPDATE community_daily SET {field}={field}+1 WHERE guild_id=? AND day=? AND channel_id=?",
                       (guild_id, day, channel_id))

    def stats(self, guild_id: int) -> list[sqlite3.Row]:
        cutoff = int(time.time()) // 86400 - 6
        with self.connection() as db:
            return db.execute("""SELECT channel_id,SUM(messages) messages,SUM(joins) joins,SUM(leaves) leaves
                FROM community_daily WHERE guild_id=? AND day>=? GROUP BY channel_id ORDER BY messages DESC""",
                (guild_id, cutoff)).fetchall()


store = CommunityStore()


class MemberPages(discord.ui.View):
    def __init__(self, author_id: int, role: discord.Role, members: list[discord.Member]):
        super().__init__(timeout=120)
        self.author_id, self.role, self.members, self.page = author_id, role, members, 0

    def embed(self) -> discord.Embed:
        pages = max(1, (len(self.members) + 14) // 15)
        group = self.members[self.page * 15:(self.page + 1) * 15]
        text = "\n".join(f"{i}. {member.mention}" for i, member in enumerate(group, self.page * 15 + 1)) or "No members have this role."
        embed = discord.Embed(title=f"Members with {self.role.name}", description=text, colour=self.role.colour)
        embed.set_footer(text=f"Page {self.page + 1}/{pages} · {len(self.members)} members")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id: return True
        await interaction.response.send_message("Only the command user can change pages.", ephemeral=True)
        return False

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.page = (self.page - 1) % max(1, (len(self.members) + 14) // 15)
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.page = (self.page + 1) % max(1, (len(self.members) + 14) // 15)
        await interaction.response.edit_message(embed=self.embed(), view=self)


class Community(commands.Cog):
    """Server onboarding, automod, role tools, and activity statistics."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.recent: dict[tuple[int, int], deque[float]] = defaultdict(lambda: deque(maxlen=8))

    @commands.group(name="voice", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def voice(self, ctx: commands.Context) -> None:
        await ctx.send("Use `voice mute`, `deafen`, `disconnect`, or `move`.")

    async def _voice_action(self, ctx: commands.Context, member: discord.Member, **changes) -> None:
        if member.voice is None:
            await ctx.send("That member is not in a voice channel."); return
        try:
            await member.edit(reason=f"Voice moderation by {ctx.author}", **changes)
            await ctx.send(f"Updated {member.mention}'s voice state.")
        except discord.Forbidden:
            await ctx.send("I cannot moderate that member. Check my role position and permissions.")

    @voice.command(name="mute")
    async def voice_mute(self, ctx: commands.Context, member: discord.Member): await self._voice_action(ctx, member, mute=True)
    @voice.command(name="deafen")
    async def voice_deafen(self, ctx: commands.Context, member: discord.Member): await self._voice_action(ctx, member, deafen=True)
    @voice.command(name="disconnect")
    async def voice_disconnect(self, ctx: commands.Context, member: discord.Member): await self._voice_action(ctx, member, voice_channel=None)
    @voice.command(name="move")
    async def voice_move(self, ctx: commands.Context, member: discord.Member, channel: discord.VoiceChannel): await self._voice_action(ctx, member, voice_channel=channel)

    @commands.group(name="automod", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def automod(self, ctx: commands.Context): await ctx.send("Use `automod status` or `automod setup`.")

    @automod.command(name="status")
    async def automod_status(self, ctx: commands.Context):
        cfg = await asyncio.to_thread(store.config, ctx.guild.id)
        fmt = lambda value: "Enabled" if value else "Disabled"
        await ctx.send(view=card("AutoMod Status", f"**Spam:** {fmt(cfg['automod_spam'])}\n**Mention spam:** {fmt(cfg['automod_mentions'])}\n**Invite links:** {fmt(cfg['automod_invites'])}"))

    @automod.command(name="setup")
    async def automod_setup(self, ctx: commands.Context, spam: bool = True, mentions: bool = True, invites: bool = True):
        await asyncio.to_thread(store.set_values, ctx.guild.id, automod_spam=int(spam), automod_mentions=int(mentions), automod_invites=int(invites))
        await ctx.send("AutoMod settings saved. Use `;automod setup false false false` to disable all filters.")

    async def _message_setup(self, ctx: commands.Context, kind: str, channel: discord.TextChannel, message: str):
        if not message.strip(): await ctx.send("Add a message."); return
        await asyncio.to_thread(store.set_values, ctx.guild.id, **{f"{kind}_channel": channel.id, f"{kind}_message": message[:1800]})
        await ctx.send(f"{kind.title()} messages will be sent in {channel.mention}.")

    async def _message_test(self, ctx: commands.Context, kind: str):
        cfg = await asyncio.to_thread(store.config, ctx.guild.id)
        channel = ctx.guild.get_channel(cfg[f"{kind}_channel"] or 0)
        if not isinstance(channel, discord.TextChannel): await ctx.send(f"{kind.title()} messages are not configured."); return
        text = render_member_message(cfg[f"{kind}_message"] or "{user} joined {server}.", ctx.author, ctx.guild)
        await channel.send(text, allowed_mentions=discord.AllowedMentions(users=True))
        await ctx.send("Test sent.")

    @commands.group(name="welcome", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def welcome(self, ctx): await ctx.send("Use `welcome setup #channel message`, `disable`, or `test`.")
    @welcome.command(name="setup")
    async def welcome_setup(self, ctx, channel: discord.TextChannel, *, message: str): await self._message_setup(ctx, "welcome", channel, message)
    @welcome.command(name="disable")
    async def welcome_disable(self, ctx): await asyncio.to_thread(store.set_values, ctx.guild.id, welcome_channel=None); await ctx.send("Welcome messages disabled.")
    @welcome.command(name="test")
    async def welcome_test(self, ctx): await self._message_test(ctx, "welcome")

    @commands.group(name="goodbye", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def goodbye(self, ctx): await ctx.send("Use `goodbye setup #channel message`, `disable`, or `test`.")
    @goodbye.command(name="setup")
    async def goodbye_setup(self, ctx, channel: discord.TextChannel, *, message: str): await self._message_setup(ctx, "goodbye", channel, message)
    @goodbye.command(name="disable")
    async def goodbye_disable(self, ctx): await asyncio.to_thread(store.set_values, ctx.guild.id, goodbye_channel=None); await ctx.send("Goodbye messages disabled.")
    @goodbye.command(name="test")
    async def goodbye_test(self, ctx): await self._message_test(ctx, "goodbye")

    @commands.group(name="autorole", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def autorole(self, ctx): await ctx.send("Use `autorole set @role` or `autorole remove`.")
    @autorole.command(name="set")
    async def autorole_set(self, ctx, role: discord.Role):
        if role >= ctx.guild.me.top_role: await ctx.send("That role is above my highest role."); return
        await asyncio.to_thread(store.set_values, ctx.guild.id, autorole_id=role.id); await ctx.send(f"New members will receive {role.mention}.")
    @autorole.command(name="remove")
    async def autorole_remove(self, ctx): await asyncio.to_thread(store.set_values, ctx.guild.id, autorole_id=None); await ctx.send("Autorole removed.")

    @commands.command(name="server-stats")
    @commands.guild_only()
    async def server_stats(self, ctx: commands.Context):
        rows = await asyncio.to_thread(store.stats, ctx.guild.id)
        messages = sum(int(row["messages"]) for row in rows); joins = sum(int(row["joins"]) for row in rows); leaves = sum(int(row["leaves"]) for row in rows)
        active = [row for row in rows if row["channel_id"] and row["messages"]][:5]
        channels = "\n".join(f"<#{row['channel_id']}> — `{row['messages']:,}`" for row in active) or "No activity recorded yet."
        await ctx.send(view=card("Server Stats — Last 7 Days", f"**Members:** `{ctx.guild.member_count or 0:,}`\n**Growth:** `{joins - leaves:+,}` ({joins:,} joined, {leaves:,} left)\n**Messages:** `{messages:,}`\n\n### Active Channels\n{channels}"))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot: return
        await asyncio.to_thread(store.record, message.guild.id, message.channel.id, "messages")
        cfg = await asyncio.to_thread(store.config, message.guild.id)
        if isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_messages: return
        violation = None
        now = time.monotonic(); recent = self.recent[(message.guild.id, message.author.id)]; recent.append(now)
        if cfg["automod_spam"] and len(recent) >= 6 and now - recent[-6] < 8: violation = "message spam"
        if cfg["automod_mentions"] and len(message.mentions) + len(message.role_mentions) >= 5: violation = "mention spam"
        if cfg["automod_invites"] and INVITE_RE.search(message.content): violation = "invite links"
        if violation:
            try: await message.delete(); await message.channel.send(f"{message.author.mention}, {violation} is not allowed.", delete_after=5)
            except discord.HTTPException: pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await asyncio.to_thread(store.record, member.guild.id, 0, "joins")
        cfg = await asyncio.to_thread(store.config, member.guild.id)
        role = member.guild.get_role(cfg["autorole_id"] or 0)
        if role:
            try: await member.add_roles(role, reason="Configured autorole")
            except discord.HTTPException: pass
        channel = member.guild.get_channel(cfg["welcome_channel"] or 0)
        if isinstance(channel, discord.TextChannel):
            text = render_member_message(cfg["welcome_message"] or "Welcome {user} to {server}!", member, member.guild)
            await channel.send(text, allowed_mentions=discord.AllowedMentions(users=True))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await asyncio.to_thread(store.record, member.guild.id, 0, "leaves")
        cfg = await asyncio.to_thread(store.config, member.guild.id)
        channel = member.guild.get_channel(cfg["goodbye_channel"] or 0)
        if isinstance(channel, discord.TextChannel):
            text = render_member_message(cfg["goodbye_message"] or "{user} left {server}.", member, member.guild)
            await channel.send(text, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Community(bot))
