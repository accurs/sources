import discord
import aiohttp
from discord.ext import commands

API  = "https://ws.audioscrobbler.com/2.0/"
KEY  = "1b6567ff20617da36b3f7e5b335651c8"
ICON = "https://www.last.fm/static/images/lastfm_avatar_twitter.52a5d69a85ac.png"


class lastfm(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _exec(self, q: str, *a):
        async with self.bot.db.acquire() as c:
            await c.execute(q, *a)

    async def _row(self, q: str, *a):
        async with self.bot.db.acquire() as c:
            return await c.fetchrow(q, *a)

    async def _rows(self, q: str, *a):
        async with self.bot.db.acquire() as c:
            return await c.fetch(q, *a)

    async def ensure_table(self):
        await self._exec("""
            CREATE TABLE IF NOT EXISTS lastfm (
                user_id  BIGINT PRIMARY KEY,
                username TEXT NOT NULL
            )
        """)

    async def cog_load(self):
        await self.ensure_table()

    async def get_lfm(self, uid: int) -> str | None:
        row = await self._row("SELECT username FROM lastfm WHERE user_id=$1", uid)
        return row["username"] if row else None

    async def _api(self, **params) -> dict | None:
        params["api_key"] = KEY
        params["format"]  = "json"
        async with aiohttp.ClientSession() as s:
            async with s.get(API, params=params) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                if "error" in data:
                    return None
                return data

    async def _require_lfm(self, ctx: commands.Context, user: discord.Member | None = None) -> tuple[str | None, discord.Member]:
        target  = user or ctx.author
        username = await self.get_lfm(target.id)
        if not username:
            who = "You haven't" if target == ctx.author else f"{target.name} hasn't"
            embed = discord.Embed(
                description=f"> **{who} linked a Last.fm account — use `lastfm set <username>`...**",
                color=self.bot.color
            )
            await ctx.send(embed=embed)
            return None, target
        return username, target

    def _period_label(self, p: str) -> str:
        return {
            "7day": "Last 7 Days", "1month": "Last Month",
            "3month": "Last 3 Months", "6month": "Last 6 Months",
            "12month": "Last Year", "overall": "All Time"
        }.get(p, "All Time")

    @commands.group(name="lastfm", aliases=["lf", "fm"], invoke_without_command=True, help="lastfm")
    async def lastfm_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            return await ctx.create_pages()

    @lastfm_group.command(name="set", usage="<username>", help="lastfm")
    async def lfm_set(self, ctx: commands.Context, username: str):
        data = await self._api(method="user.getinfo", user=username)
        if not data:
            embed = discord.Embed(
                description=f"> **Last.fm user `{username}` not found...**",
                color=self.bot.color
            )
            return await ctx.send(embed=embed)

        await self._exec(
            "INSERT INTO lastfm(user_id, username) VALUES($1,$2)"
            " ON CONFLICT(user_id) DO UPDATE SET username=EXCLUDED.username",
            ctx.author.id, username
        )
        info   = data["user"]
        avatar = info.get("image", [{}])[-1].get("#text") or ICON
        embed  = discord.Embed(
            description=f"> **Linked your Last.fm account to `{username}`...**",
            color=self.bot.color
        )
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
        embed.set_thumbnail(url=avatar)
        await ctx.send(embed=embed)

    @lastfm_group.command(name="nowplaying", aliases=["np"], usage="[user]", help="lastfm")
    async def lfm_np(self, ctx: commands.Context, user: discord.Member = None):
        username, target = await self._require_lfm(ctx, user)
        if not username: return

        data = await self._api(method="user.getrecenttracks", user=username, limit=1)
        if not data:
            embed = discord.Embed(description="> **Could not fetch recent tracks...**", color=self.bot.color)
            return await ctx.send(embed=embed)

        tracks = data["recenttracks"].get("track", [])
        if not tracks:
            embed = discord.Embed(description="> **No recent tracks found...**", color=self.bot.color)
            return await ctx.send(embed=embed)

        track  = tracks[0] if isinstance(tracks, list) else tracks
        now    = track.get("@attr", {}).get("nowplaying") == "true"
        name   = track.get("name", "Unknown")
        artist = track.get("artist", {}).get("#text", "Unknown")
        album  = track.get("album", {}).get("#text", "")
        url    = track.get("url", "")
        cover  = track.get("image", [{}])[-1].get("#text") or ICON

        tdata  = await self._api(method="track.getInfo", track=name, artist=artist, username=username)
        plays  = tdata["track"]["userplaycount"] if tdata and "track" in tdata else "?"

        status = "Now Playing" if now else "Last Played"
        embed  = discord.Embed(
            title=f"{name}",
            url=url,
            description=f"**{artist}**" + (f"\n{album}" if album else ""),
            color=self.bot.color
        )
        embed.set_author(name=f"{target.name} — {status}", icon_url=target.display_avatar.url)
        embed.set_thumbnail(url=cover)
        embed.set_footer(text=f"{plays} plays  ·  {username}", icon_url=ICON)
        await ctx.send(embed=embed)
    @lastfm_group.command(name="profile", usage="[user]", help="lastfm")
    async def lfm_profile(self, ctx: commands.Context, user: discord.Member = None):
        username, target = await self._require_lfm(ctx, user)
        if not username: return

        data = await self._api(method="user.getinfo", user=username)
        if not data:
            embed = discord.Embed(description="> **Could not fetch profile...**", color=self.bot.color)
            return await ctx.send(embed=embed)

        info      = data["user"]
        scrobbles = int(info.get("playcount", 0))
        country   = info.get("country", "Unknown")
        registered = info.get("registered", {}).get("#text", "Unknown")
        avatar    = info.get("image", [{}])[-1].get("#text") or ICON
        url       = info.get("url", "")

        embed = discord.Embed(
            title=username,
            url=url,
            color=self.bot.color
        )
        embed.set_author(name=target.name, icon_url=target.display_avatar.url)
        embed.set_thumbnail(url=avatar)
        embed.add_field(name="Scrobbles", value=f"{scrobbles:,}", inline=True)
        embed.add_field(name="Country",   value=country,          inline=True)
        embed.add_field(name="Registered",value=registered,       inline=True)
        embed.set_footer(text="Last.fm", icon_url=ICON)
        await ctx.send(embed=embed)

    @lastfm_group.command(name="recent", aliases=["re"], usage="[user]", help="lastfm")
    async def lfm_recent(self, ctx: commands.Context, user: discord.Member = None):
        username, target = await self._require_lfm(ctx, user)
        if not username: return

        data = await self._api(method="user.getrecenttracks", user=username, limit=10)
        if not data:
            embed = discord.Embed(description="> **Could not fetch recent tracks...**", color=self.bot.color)
            return await ctx.send(embed=embed)

        tracks = data["recenttracks"].get("track", [])
        if not tracks:
            embed = discord.Embed(description="> **No recent tracks found...**", color=self.bot.color)
            return await ctx.send(embed=embed)

        lines = []
        for i, t in enumerate(tracks[:10], 1):
            name   = t.get("name", "Unknown")
            artist = t.get("artist", {}).get("#text", "Unknown")
            now    = t.get("@attr", {}).get("nowplaying") == "true"
            prefix = "▶" if now else f"`{i}`"
            lines.append(f"> {prefix}  **{name}** — {artist}")

        embed = discord.Embed(
            description="\n".join(lines),
            color=self.bot.color
        )
        embed.set_author(name=f"{target.name}'s Recent Tracks", icon_url=target.display_avatar.url)
        embed.set_footer(text=f"{username}  ·  Last.fm", icon_url=ICON)
        await ctx.send(embed=embed)

    @lastfm_group.command(name="topartists", aliases=["ta"], usage="[user] [period]", help="lastfm")
    async def lfm_topartists(self, ctx: commands.Context, user: discord.Member = None, period: str = "overall"):
        username, target = await self._require_lfm(ctx, user)
        if not username: return

        data = await self._api(method="user.gettopartists", user=username, period=period, limit=10)
        if not data:
            embed = discord.Embed(description="> **Could not fetch top artists...**", color=self.bot.color)
            return await ctx.send(embed=embed)

        artists = data.get("topartists", {}).get("artist", [])
        if not artists:
            embed = discord.Embed(description="> **No top artists found...**", color=self.bot.color)
            return await ctx.send(embed=embed)

        lines = []
        for i, a in enumerate(artists[:10], 1):
            name   = a.get("name", "Unknown")
            plays  = int(a.get("playcount", 0))
            url    = a.get("url", "")
            lines.append(f"> `{i}`  [{name}]({url}) — **{plays:,} plays**")

        embed = discord.Embed(
            description="\n".join(lines),
            color=self.bot.color
        )
        embed.set_author(name=f"{target.name}'s Top Artists — {self._period_label(period)}", icon_url=target.display_avatar.url)
        embed.set_footer(text=f"{username}  ·  Last.fm", icon_url=ICON)
        await ctx.send(embed=embed)

    @lastfm_group.command(name="toptracks", aliases=["tt"], usage="[user] [period]", help="lastfm")
    async def lfm_toptracks(self, ctx: commands.Context, user: discord.Member = None, period: str = "overall"):
        username, target = await self._require_lfm(ctx, user)
        if not username: return

        data = await self._api(method="user.gettoptracks", user=username, period=period, limit=10)
        if not data:
            embed = discord.Embed(description="> **Could not fetch top tracks...**", color=self.bot.color)
            return await ctx.send(embed=embed)

        tracks = data.get("toptracks", {}).get("track", [])
        if not tracks:
            embed = discord.Embed(description="> **No top tracks found...**", color=self.bot.color)
            return await ctx.send(embed=embed)

        lines = []
        for i, t in enumerate(tracks[:10], 1):
            name   = t.get("name", "Unknown")
            artist = t.get("artist", {}).get("name", "Unknown")
            plays  = int(t.get("playcount", 0))
            url    = t.get("url", "")
            lines.append(f"> `{i}`  [{name}]({url}) — {artist} — **{plays:,} plays**")

        embed = discord.Embed(
            description="\n".join(lines),
            color=self.bot.color
        )
        embed.set_author(name=f"{target.name}'s Top Tracks — {self._period_label(period)}", icon_url=target.display_avatar.url)
        embed.set_footer(text=f"{username}  ·  Last.fm", icon_url=ICON)
        await ctx.send(embed=embed)

    @lastfm_group.command(name="topalbums", aliases=["tal"], usage="[user] [period]", help="lastfm")
    async def lfm_topalbums(self, ctx: commands.Context, user: discord.Member = None, period: str = "overall"):
        username, target = await self._require_lfm(ctx, user)
        if not username: return

        data = await self._api(method="user.gettopalbums", user=username, period=period, limit=10)
        if not data:
            embed = discord.Embed(description="> **Could not fetch top albums...**", color=self.bot.color)
            return await ctx.send(embed=embed)

        albums = data.get("topalbums", {}).get("album", [])
        if not albums:
            embed = discord.Embed(description="> **No top albums found...**", color=self.bot.color)
            return await ctx.send(embed=embed)

        lines = []
        for i, a in enumerate(albums[:10], 1):
            name   = a.get("name", "Unknown")
            artist = a.get("artist", {}).get("name", "Unknown")
            plays  = int(a.get("playcount", 0))
            url    = a.get("url", "")
            lines.append(f"> `{i}`  [{name}]({url}) — {artist} — **{plays:,} plays**")

        embed = discord.Embed(
            description="\n".join(lines),
            color=self.bot.color
        )
        embed.set_author(name=f"{target.name}'s Top Albums — {self._period_label(period)}", icon_url=target.display_avatar.url)
        embed.set_footer(text=f"{username}  ·  Last.fm", icon_url=ICON)
        await ctx.send(embed=embed)

    @lastfm_group.command(name="artist", usage="<name>", help="lastfm")
    async def lfm_artist(self, ctx: commands.Context, *, name: str):
        data = await self._api(method="artist.getinfo", artist=name)
        if not data or "artist" not in data:
            embed = discord.Embed(description=f"> **Artist `{name}` not found...**", color=self.bot.color)
            return await ctx.send(embed=embed)

        a         = data["artist"]
        a_name    = a.get("name", name)
        url       = a.get("url", "")
        listeners = int(a.get("stats", {}).get("listeners", 0))
        plays     = int(a.get("stats", {}).get("playcount", 0))
        bio       = a.get("bio", {}).get("summary", "")
        if bio:
            bio = bio.split("<a href")[0].strip()
            if len(bio) > 300:
                bio = bio[:300].rsplit(" ", 1)[0] + "..."

        tags  = a.get("tags", {}).get("tag", [])
        tag_s = "  ".join(f"`{t['name']}`" for t in tags[:5]) if tags else ""

        similar = a.get("similar", {}).get("artist", [])
        sim_s   = "  ".join(f"[{s['name']}]({s['url']})" for s in similar[:4]) if similar else ""

        embed = discord.Embed(title=a_name, url=url, color=self.bot.color)
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
        embed.add_field(name="Listeners",    value=f"{listeners:,}", inline=True)
        embed.add_field(name="Scrobbles",    value=f"{plays:,}",     inline=True)
        if tag_s:
            embed.add_field(name="Tags",     value=tag_s,            inline=False)
        if bio:
            embed.add_field(name="Bio",      value=bio,              inline=False)
        if sim_s:
            embed.add_field(name="Similar",  value=sim_s,            inline=False)
        embed.set_footer(text="Last.fm", icon_url=ICON)
        await ctx.send(embed=embed)

    @lastfm_group.command(name="compare", usage="<user>", help="lastfm")
    async def lfm_compare(self, ctx: commands.Context, user: discord.Member):
        if user.id == ctx.author.id:
            embed = discord.Embed(description="> **You can't compare with yourself...**", color=self.bot.color)
            return await ctx.send(embed=embed)

        u1 = await self.get_lfm(ctx.author.id)
        u2 = await self.get_lfm(user.id)

        if not u1:
            embed = discord.Embed(description="> **You haven't linked a Last.fm account — use `lastfm set <username>`...**", color=self.bot.color)
            return await ctx.send(embed=embed)
        if not u2:
            embed = discord.Embed(description=f"> **{user.name} hasn't linked a Last.fm account...**", color=self.bot.color)
            return await ctx.send(embed=embed)

        d1 = await self._api(method="user.gettopartists", user=u1, period="overall", limit=100)
        d2 = await self._api(method="user.gettopartists", user=u2, period="overall", limit=100)

        a1 = {a["name"].lower() for a in (d1 or {}).get("topartists", {}).get("artist", [])}
        a2 = {a["name"].lower() for a in (d2 or {}).get("topartists", {}).get("artist", [])}

        common    = a1 & a2
        compat    = int(len(common) / max(len(a1 | a2), 1) * 100)
        common_s  = ", ".join(sorted(common)[:8]) if common else "None"

        i1 = await self._api(method="user.getinfo", user=u1)
        i2 = await self._api(method="user.getinfo", user=u2)
        sc1 = int((i1 or {}).get("user", {}).get("playcount", 0))
        sc2 = int((i2 or {}).get("user", {}).get("playcount", 0))

        embed = discord.Embed(
            title="Music Compatibility",
            description=f"> **{ctx.author.name}** vs **{user.name}**",
            color=self.bot.color
        )
        embed.add_field(name=f"{ctx.author.name}", value=f"**{sc1:,}** scrobbles\n`{u1}`", inline=True)
        embed.add_field(name=f"{user.name}",       value=f"**{sc2:,}** scrobbles\n`{u2}`", inline=True)
        embed.add_field(name="Compatibility",      value=f"**{compat}%**",                 inline=True)
        embed.add_field(name=f"Common Artists ({len(common)})", value=common_s,            inline=False)
        embed.set_footer(text="Last.fm", icon_url=ICON)
        await ctx.send(embed=embed)

    @lastfm_group.command(name="leaderboard", aliases=["lb"], help="lastfm")
    async def lfm_leaderboard(self, ctx: commands.Context):
        rows = await self._rows("SELECT user_id, username FROM lastfm")
        if not rows:
            embed = discord.Embed(description="> **No Last.fm accounts linked in this server...**", color=self.bot.color)
            return await ctx.send(embed=embed)

        members = {m.id for m in ctx.guild.members}
        linked  = [(r["user_id"], r["username"]) for r in rows if r["user_id"] in members]

        if not linked:
            embed = discord.Embed(description="> **No Last.fm accounts linked in this server...**", color=self.bot.color)
            return await ctx.send(embed=embed)

        scores = []
        for uid, uname in linked:
            data = await self._api(method="user.getinfo", user=uname)
            if data and "user" in data:
                sc = int(data["user"].get("playcount", 0))
                scores.append((uid, uname, sc))

        scores.sort(key=lambda x: x[2], reverse=True)

        medals = {1: "1st", 2: "2nd", 3: "3rd"}
        lines  = [f"**Last.fm Leaderboard — {ctx.guild.name}**", ""]
        for i, (uid, uname, sc) in enumerate(scores[:10], 1):
            member = ctx.guild.get_member(uid)
            name   = member.name if member else "Unknown"
            rank   = medals.get(i, f"{i}th")
            lines.append(f"> **{rank}**  {name}  —  **{sc:,}** scrobbles  `{uname}`")

        embed = discord.Embed(description="\n".join(lines), color=self.bot.color)
        embed.set_footer(text="Last.fm", icon_url=ICON)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(lastfm(bot))