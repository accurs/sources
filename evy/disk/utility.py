import discord
import aiohttp
import asyncio
import re
from discord.ext import commands
from datetime import timezone

_snipe_cache:     dict[int, list[dict]] = {}
_editsnipe_cache: dict[int, list[dict]] = {}


def fmt_time(dt) -> str:
    if dt is None:
        return "Unknown"
    ts = int(dt.replace(tzinfo=timezone.utc).timestamp()) if dt.tzinfo is None else int(dt.timestamp())
    return f"<t:{ts}:F> (<t:{ts}:R>)"


def parse_time(s: str) -> int | None:
    pattern = re.fullmatch(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", s.strip())
    if not pattern or not any(pattern.groups()):
        return None
    d, h, m, sec = (int(x) if x else 0 for x in pattern.groups())
    total = d * 86400 + h * 3600 + m * 60 + sec
    return total if total > 0 else None


def fmt_delta(seconds: int) -> str:
    d, r = divmod(int(seconds), 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return " ".join(parts)


class info(commands.Cog):
    def __init__(self, bot):
        self.bot         = bot
        self.description = "utility commands"
        self._afk: dict[int, dict] = {}

    async def _exec(self, q: str, *a):
        async with self.bot.db.acquire() as c:
            await c.execute(q, *a)

    async def _rows(self, q: str, *a):
        async with self.bot.db.acquire() as c:
            return await c.fetch(q, *a)

    async def ensure_tables(self):
        await self._exec("""
            CREATE TABLE IF NOT EXISTS reminders (
                id         SERIAL PRIMARY KEY,
                user_id    BIGINT,
                channel_id BIGINT,
                message    TEXT,
                fire_at    DOUBLE PRECISION
            )
        """)
        await self._exec("""
            CREATE TABLE IF NOT EXISTS afk (
                user_id BIGINT PRIMARY KEY,
                reason  TEXT,
                time    DOUBLE PRECISION
            )
        """)

    async def cog_load(self):
        await self.ensure_tables()
        rows = await self._rows("SELECT user_id, reason, time FROM afk")
        for row in rows:
            self._afk[row["user_id"]] = {"reason": row["reason"], "time": row["time"]}
        rows = await self._rows("SELECT * FROM reminders")
        for row in rows:
            self.bot.loop.create_task(self._fire_reminder(dict(row)))

    async def _fire_reminder(self, row: dict):
        import time
        delay = row["fire_at"] - time.time()
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            ch   = self.bot.get_channel(row["channel_id"])
            user = self.bot.get_user(row["user_id"])
            if ch and user:
                embed = discord.Embed(
                    description=f"> {user.mention} **Reminder:** {row['message']}",
                    color=self.bot.color
                )
                await ch.send(embed=embed)
        except:
            pass
        await self._exec("DELETE FROM reminders WHERE id=$1", row["id"])

    async def _v2(self, ctx: commands.Context, content: str, *, thumb_url: str | None = None, buttons: list | None = None):
        inner = []
        if thumb_url:
            inner.append({
                "type": 9,
                "components": [{"type": 10, "content": content}],
                "accessory": {"type": 11, "media": {"url": thumb_url}}
            })
        else:
            inner.append({"type": 10, "content": content})
        if buttons:
            inner.append({"type": 14})
            inner.append({"type": 1, "components": buttons})
        payload = {"flags": 32768, "components": [{"type": 17, "components": inner}]}
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://discord.com/api/v10/channels/{ctx.channel.id}/messages",
                json=payload,
                headers={"Authorization": f"Bot {self.bot.http.token}", "Content-Type": "application/json"}
            ) as r:
                if r.status not in (200, 201):
                    print(f"[info v2] {r.status}: {await r.text()}")

    async def _v2_image(self, ctx: commands.Context, content: str, image_url: str, *, buttons: list | None = None):
        embed = discord.Embed(description=content, color=self.bot.color)
        embed.set_image(url=image_url)
        view = None
        if buttons:
            view = discord.ui.View(timeout=60)
            for btn in buttons:
                view.add_item(discord.ui.Button(
                    label=btn.get("label", "Link"),
                    url=btn.get("url"),
                    style=discord.ButtonStyle.link
                ))
        await ctx.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.content:
            return
        entry = {"content": message.content, "author": message.author, "time": message.created_at}
        lst   = _snipe_cache.setdefault(message.channel.id, [])
        lst.insert(0, entry)
        if len(lst) > 10:
            lst.pop()

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or before.content == after.content:
            return
        entry = {"before": before.content, "after": after.content, "author": before.author, "time": before.created_at}
        lst   = _editsnipe_cache.setdefault(before.channel.id, [])
        lst.insert(0, entry)
        if len(lst) > 10:
            lst.pop()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        uid = message.author.id
        if uid in self._afk:
            data = self._afk.pop(uid)
            await self._exec("DELETE FROM afk WHERE user_id=$1", uid)
            since = fmt_delta(discord.utils.utcnow().timestamp() - data["time"])
            embed = discord.Embed(
                description=f"> **Welcome back {message.author.mention} - you were AFK for {since}**",
                color=self.bot.color
            )
            await message.channel.send(embed=embed, delete_after=8)
        for user in message.mentions:
            if user.id in self._afk and user.id != message.author.id:
                data = self._afk[user.id]
                since = fmt_delta(discord.utils.utcnow().timestamp() - data["time"])
                embed = discord.Embed(
                    description=f"> **{user.name} is AFK** - {data['reason']} - {since} ago",
                    color=self.bot.color
                )
                await message.channel.send(embed=embed, delete_after=8)
    @commands.hybrid_command(
        name="userinfo", aliases=["ui", "whois"],
        description="Get information about a user",
        usage="[user]", help="utility"
    )
    async def userinfo(self, ctx: commands.Context, user: discord.Member = None):
        user = user or ctx.author
        badges = []
        if user.public_flags.hypesquad_bravery:      badges.append("HypeSquad Bravery")
        if user.public_flags.hypesquad_brilliance:   badges.append("HypeSquad Brilliance")
        if user.public_flags.hypesquad_balance:      badges.append("HypeSquad Balance")
        if user.public_flags.early_supporter:        badges.append("Early Supporter")
        if user.public_flags.verified_bot_developer: badges.append("Verified Bot Dev")
        if user.public_flags.staff:                  badges.append("Discord Staff")
        if user.bot:                                 badges.append("Bot")
        roles = [r.mention for r in reversed(user.roles) if r.name != "@everyone"]
        roles_str = " ".join(roles[:10])
        if len(roles) > 10:
            roles_str += f" *+{len(roles) - 10} more*"
        lines = [
            f"**{user}**", f"",
            f"> **ID** - `{user.id}`",
            f"> **Nickname** - {user.nick or 'None'}",
            f"> **Top Role** - {user.top_role.mention}",
            f"> **Created** - {fmt_time(user.created_at)}",
            f"> **Joined** - {fmt_time(user.joined_at)}",
        ]
        if badges:
            lines.append(f"> **Badges** - {', '.join(badges)}")
        if roles:
            lines += [f"", f"**Roles [{len(roles)}]**", roles_str]
        await self._v2(ctx, "\n".join(lines), thumb_url=str(user.display_avatar.url))

    @commands.hybrid_command(
        name="serverinfo", aliases=["si", "guildinfo"],
        description="Get information about the server",
        help="utility"
    )
    async def serverinfo(self, ctx: commands.Context):
        g        = ctx.guild
        bots     = sum(1 for m in g.members if m.bot)
        humans   = g.member_count - bots
        online   = sum(1 for m in g.members if m.status != discord.Status.offline)
        text_ch  = len(g.text_channels)
        voice_ch = len(g.voice_channels)
        stage_ch = len(g.stage_channels)
        cat_ch   = len(g.categories)
        if g.premium_tier == 0:   boost = "No boosts"
        elif g.premium_tier == 1: boost = f"Level 1 - {g.premium_subscription_count} boosts"
        elif g.premium_tier == 2: boost = f"Level 2 - {g.premium_subscription_count} boosts"
        else:                     boost = f"Level 3 - {g.premium_subscription_count} boosts"
        vl = str(g.verification_level).replace("_", " ").title()
        lines = [
            f"**{g.name}**", f"",
            f"> **ID** - `{g.id}`",
            f"> **Owner** - {g.owner.mention if g.owner else 'Unknown'}",
            f"> **Created** - {fmt_time(g.created_at)}",
            f"> **Verification** - {vl}",
            f"> **Boosts** - {boost}", f"",
            f"**Members [{g.member_count:,}]**",
            f"> **Humans** - {humans:,}",
            f"> **Bots** - {bots:,}",
            f"> **Online** - {online:,}", f"",
            f"**Channels [{text_ch + voice_ch + stage_ch}]**",
            f"> **Text** - {text_ch}",
            f"> **Voice** - {voice_ch}",
            f"> **Stage** - {stage_ch}",
            f"> **Categories** - {cat_ch}", f"",
            f"**Other**",
            f"> **Roles** - {len(g.roles) - 1}",
            f"> **Emojis** - {len(g.emojis)}",
            f"> **Stickers** - {len(g.stickers)}",
        ]
        await self._v2(ctx, "\n".join(lines), thumb_url=str(g.icon.url) if g.icon else None)

    @commands.hybrid_command(
        name="avatar", aliases=["av", "pfp"],
        description="Get a user's avatar",
        usage="[user]", help="utility"
    )
    async def avatar(self, ctx: commands.Context, user: discord.Member = None):
        user    = user or ctx.author
        av      = str(user.display_avatar.url)
        buttons = []
        if user.guild_avatar:
            buttons.append({"type": 2, "style": 5, "label": "Server Avatar", "url": str(user.guild_avatar.url)})
        buttons.append({"type": 2, "style": 5, "label": "Global Avatar", "url": str(user.avatar.url if user.avatar else user.default_avatar.url)})
        await self._v2_image(ctx, f"**{user.name}'s Avatar**", av, buttons=buttons)

    @commands.hybrid_command(
        name="banner",
        description="Get a user's banner",
        usage="[user]", help="utility"
    )
    async def banner(self, ctx: commands.Context, user: discord.Member = None):
        user    = user or ctx.author
        fetched = await self.bot.fetch_user(user.id)
        if not fetched.banner:
            return await self._v2(ctx, f"> **{user.name} doesn't have a banner...**")
        buttons = [{"type": 2, "style": 5, "label": "Open Banner", "url": str(fetched.banner.url)}]
        await self._v2_image(ctx, f"**{user.name}'s Banner**", str(fetched.banner.url), buttons=buttons)

    @commands.hybrid_command(
        name="roleinfo", aliases=["ri"],
        description="Get information about a role",
        usage="<role>", help="utility"
    )
    async def roleinfo(self, ctx: commands.Context, *, role: discord.Role):
        perms = [
            p.replace("_", " ").title()
            for p, v in role.permissions
            if v and p not in ("send_messages", "read_messages", "read_message_history", "view_channel", "connect", "speak")
        ]
        lines = [
            f"**{role.name}**", f"",
            f"> **ID** - `{role.id}`",
            f"> **Color** - `{role.color}`",
            f"> **Position** - {role.position}",
            f"> **Members** - {len(role.members)}",
            f"> **Mentionable** - {role.mentionable}",
            f"> **Hoisted** - {role.hoist}",
            f"> **Created** - {fmt_time(role.created_at)}",
        ]
        if perms:
            perms_str = ", ".join(perms[:12])
            if len(perms) > 12: perms_str += f" +{len(perms) - 12} more"
            lines += [f"", f"**Key Permissions**", f"> {perms_str}"]
        await self._v2(ctx, "\n".join(lines))

    @commands.hybrid_command(
        name="membercount", aliases=["mc"],
        description="Get the member count of the server",
        help="utility"
    )
    async def membercount(self, ctx: commands.Context):
        g      = ctx.guild
        bots   = sum(1 for m in g.members if m.bot)
        humans = g.member_count - bots
        online = sum(1 for m in g.members if m.status != discord.Status.offline)
        idle   = sum(1 for m in g.members if m.status == discord.Status.idle)
        dnd    = sum(1 for m in g.members if m.status == discord.Status.dnd)
        off    = sum(1 for m in g.members if m.status == discord.Status.offline)
        lines = [
            f"**{g.name} - Member Count**", f"",
            f"> **Total** - {g.member_count:,}",
            f"> **Humans** - {humans:,}",
            f"> **Bots** - {bots:,}", f"",
            f"> **Online** - {online:,}",
            f"> **Idle** - {idle:,}",
            f"> **DND** - {dnd:,}",
            f"> **Offline** - {off:,}",
        ]
        await self._v2(ctx, "\n".join(lines), thumb_url=str(g.icon.url) if g.icon else None)

    @commands.hybrid_command(
        name="remind", aliases=["reminder", "remindme"],
        description="Set a reminder",
        usage="<time> <message>", help="utility"
    )
    async def remind(self, ctx: commands.Context, duration: str, *, message: str):
        import time
        seconds = parse_time(duration)
        if not seconds:
            return await self._v2(ctx, "> **Invalid time format - use `1h30m`, `2d`, `45s` etc...**")
        if seconds > 2_592_000:
            return await self._v2(ctx, "> **Maximum reminder time is 30 days...**")
        fire_at = time.time() + seconds
        async with self.bot.db.acquire() as c:
            rec = await c.fetchrow(
                "INSERT INTO reminders(user_id, channel_id, message, fire_at) VALUES($1,$2,$3,$4) RETURNING *",
                ctx.author.id, ctx.channel.id, message, fire_at
            )
        self.bot.loop.create_task(self._fire_reminder(dict(rec)))
        ts = int(fire_at)
        await self._v2(ctx,
            f"**Reminder Set**\n\n"
            f"> **Message** - {message}\n"
            f"> **Fires** - <t:{ts}:F> (<t:{ts}:R>)",
            thumb_url=str(ctx.author.display_avatar.url)
        )

    @commands.hybrid_command(
        name="afk",
        description="Set yourself as AFK",
        usage="[reason]", help="utility"
    )
    async def afk(self, ctx: commands.Context, *, reason: str = "AFK"):
        import time
        self._afk[ctx.author.id] = {"reason": reason, "time": time.time()}
        await self._exec(
            "INSERT INTO afk(user_id, reason, time) VALUES($1,$2,$3) ON CONFLICT(user_id) DO UPDATE SET reason=EXCLUDED.reason, time=EXCLUDED.time",
            ctx.author.id, reason, time.time()
        )
        await self._v2(ctx, f"> **{ctx.author.mention} is now AFK** - {reason}", thumb_url=str(ctx.author.display_avatar.url))

    @commands.hybrid_command(
        name="snipe", aliases=["s"],
        description="Show the last deleted messages in this channel",
        help="utility"
    )
    async def snipe(self, ctx: commands.Context):
        entries = _snipe_cache.get(ctx.channel.id)
        if not entries:
            return await self._v2(ctx, "> **Nothing to snipe in this channel...**")

        embeds = []
        for i, data in enumerate(entries, 1):
            ts = int(data["time"].replace(tzinfo=timezone.utc).timestamp()) if data["time"].tzinfo is None else int(data["time"].timestamp())
            embed = discord.Embed(
                description=f"> {data['content']}",
                color=self.bot.color
            )
            embed.set_author(name=data["author"].name, icon_url=data["author"].display_avatar.url)
            embed.set_footer(text=f"{i}/{len(entries)}")
            embeds.append(embed)

        await ctx.paginator(embeds)

    @commands.hybrid_command(
        name="editsnipe", aliases=["es"],
        description="Show the last edited messages in this channel",
        help="utility"
    )
    async def editsnipe(self, ctx: commands.Context):
        entries = _editsnipe_cache.get(ctx.channel.id)
        if not entries:
            return await self._v2(ctx, "> **Nothing to editsnipe in this channel...**")

        embeds = []
        for i, data in enumerate(entries, 1):
            ts = int(data["time"].replace(tzinfo=timezone.utc).timestamp()) if data["time"].tzinfo is None else int(data["time"].timestamp())
            before_text = data["before"]
            after_text  = data["after"]
            embed = discord.Embed(
                description=f"> **Before** - {before_text}\n> **After** - {after_text}",
                color=self.bot.color
            )
            embed.set_author(name=data["author"].name, icon_url=data["author"].display_avatar.url)
            embed.set_footer(text=f"{i}/{len(entries)}")
            embeds.append(embed)

        await ctx.paginator(embeds)

    @commands.hybrid_command(
        name="clearsnipe", aliases=["cs"],
        description="Clear the snipe cache for this channel",
        help="utility"
    )
    async def clearsnipe(self, ctx: commands.Context):
        cleared = False
        if ctx.channel.id in _snipe_cache:
            del _snipe_cache[ctx.channel.id]
            cleared = True
        if ctx.channel.id in _editsnipe_cache:
            del _editsnipe_cache[ctx.channel.id]
            cleared = True
        if cleared:
            await self._v2(ctx, "> **Cleared the snipe cache for this channel...**")
        else:
            await self._v2(ctx, "> **Nothing to clear in this channel...**")

    @commands.hybrid_command(
        name="firstmessage", aliases=["firstmsg"],
        description="Get the first message in a channel",
        usage="[channel]", help="utility"
    )
    async def firstmessage(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        async for message in channel.history(limit=1, oldest_first=True):
            ts  = int(message.created_at.timestamp())
            url = message.jump_url
            await self._v2(ctx,
                f"**First Message in {channel.mention}**\n\n"
                f"> **Author** - {message.author.mention}\n"
                f"> **Content** - {message.content[:200] or '*No text content*'}\n"
                f"> **Sent** - <t:{ts}:F> (<t:{ts}:R>)",
                buttons=[{"type": 2, "style": 5, "label": "Jump to Message", "url": url}]
            )
            return
        await self._v2(ctx, "> **No messages found in this channel...**")

    @commands.hybrid_command(
        name="channelinfo", aliases=["ci"],
        description="Get information about a channel",
        usage="[channel]", help="utility"
    )
    async def channelinfo(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        ts      = int(channel.created_at.timestamp())
        lines = [
            f"**#{channel.name}**", f"",
            f"> **ID** - `{channel.id}`",
            f"> **Type** - {str(channel.type).replace('_', ' ').title()}",
            f"> **Category** - {channel.category.name if channel.category else 'None'}",
            f"> **Created** - <t:{ts}:F> (<t:{ts}:R>)",
            f"> **NSFW** - {channel.is_nsfw()}",
            f"> **Slowmode** - {fmt_delta(channel.slowmode_delay) if channel.slowmode_delay else 'Off'}",
            f"> **Topic** - {channel.topic or 'None'}",
        ]
        await self._v2(ctx, "\n".join(lines))


async def setup(bot):
    await bot.add_cog(info(bot))