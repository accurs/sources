from __future__ import annotations

import os
from typing import Any

import aiohttp
import asyncpg
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from bot.helpers.context import TormentContext

load_dotenv()
DB_DSN = os.getenv("DATABASE_URL")

EMBED_COLOR = discord.Color.from_str("#9FAB85")
LASTFM_API_KEY = "0ce850ce4cf35b2e8d49fcbfead6b829"
LASTFM_SECRET = "6ac7c96ce2cb518ff918e110032a8a2e"
LASTFM_BASE = "https://ws.audioscrobbler.com/2.0/"


async def lastfm_get(params: dict[str, Any]) -> dict[str, Any] | None:
    params["api_key"] = LASTFM_API_KEY
    params["format"] = "json"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(LASTFM_BASE, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        pass
    return None


class LastFM(commands.Cog):
    __cog_name__ = "lastfm"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.pool: asyncpg.Pool | None = None

    async def cog_load(self) -> None:
        self.pool = await asyncpg.create_pool(dsn=DB_DSN)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS lastfm_users (
                user_id     BIGINT PRIMARY KEY,
                username    TEXT NOT NULL,
                milestone   INTEGER
            )
        """)
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS lastfm_reactions (
                guild_id    BIGINT PRIMARY KEY,
                upvote      TEXT NOT NULL DEFAULT '👍',
                downvote    TEXT NOT NULL DEFAULT '👎'
            )
        """)

    async def cog_unload(self) -> None:
        if self.pool:
            await self.pool.close()

    async def get_username(self, user_id: int) -> str | None:
        row = await self.pool.fetchrow(
            "SELECT username FROM lastfm_users WHERE user_id = $1", user_id
        )
        return row["username"] if row else None

    async def require_lastfm(self, ctx: TormentContext, member: discord.Member | None = None) -> str | None:
        if member is None or member.id == ctx.author.id:
            username = await self.get_username(ctx.author.id)
            if not username:
                await ctx.warn("You don't have your **Last.fm** set.")
                return None
            return username
        else:
            username = await self.get_username(member.id)
            if not username:
                await ctx.warn(f"{member.mention} doesn't have their **Last.fm** set.")
                return None
            return username

    async def check_milestone(self, user: discord.User | discord.Member, total_scrobbles: int) -> None:
        row = await self.pool.fetchrow(
            "SELECT milestone FROM lastfm_users WHERE user_id = $1", user.id
        )
        if not row or not row["milestone"]:
            return
        milestone = row["milestone"]
        if total_scrobbles >= milestone:
            await self.pool.execute(
                "UPDATE lastfm_users SET milestone = NULL WHERE user_id = $1", user.id
            )
            embed = discord.Embed(
                description=(
                    f":tada: {user.mention}: You've reached your scrobble milestone of "
                    f"`{milestone:,}` on **Last.fm**!"
                ),
                color=EMBED_COLOR,
            )
            try:
                await user.send(embed=embed)
            except discord.Forbidden:
                pass

    @commands.hybrid_group(
        name="lastfm",
        aliases=["fm", "lf"],
        invoke_without_command=True,
        help="Last.fm integration commands.",
        extras={"parameters": "n/a", "usage": "lastfm"},
    )
    async def lastfm_group(self, ctx: TormentContext) -> None:
        await ctx.send_help_embed(ctx.command)

    @lastfm_group.command(
        name="set",
        aliases=["login"],
        help="Set your Last.fm username.",
        extras={"parameters": "username", "usage": "lastfm set (username)"},
    )
    @app_commands.describe(username="Your Last.fm username.")
    async def lastfm_set(self, ctx: TormentContext, *, username: str) -> None:
        data = await lastfm_get({"method": "user.getInfo", "user": username})
        if not data or "error" in data:
            await ctx.warn(f"Couldn't find a Last.fm user with the username **{username}**.")
            return

        await self.pool.execute("""
            INSERT INTO lastfm_users (user_id, username)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username
        """, ctx.author.id, username)

        embed = discord.Embed(
            description=f"{ctx.author.mention}: Set your **Last.fm** username to **{username}**.",
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @lastfm_group.command(
        name="refresh",
        aliases=["reload"],
        help="Refresh your Last.fm data.",
        extras={"parameters": "n/a", "usage": "lastfm refresh"},
    )
    async def lastfm_refresh(self, ctx: TormentContext) -> None:
        username = await self.require_lastfm(ctx)
        if not username:
            return

        data = await lastfm_get({"method": "user.getInfo", "user": username})
        if not data or "error" in data:
            await ctx.warn("Failed to refresh your Last.fm data.")
            return

        embed = discord.Embed(
            description=f"{ctx.author.mention}: Refreshed your **Last.fm** data for **{username}**.",
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @lastfm_group.command(
        name="nowplaying",
        aliases=["np"],
        help="View the song that you or another user is currently playing on Last.fm.",
        extras={"parameters": "user", "usage": "lastfm nowplaying (user)"},
    )
    @app_commands.describe(member="The user to check. Defaults to yourself.")
    async def lastfm_nowplaying(self, ctx: TormentContext, member: discord.Member | None = None) -> None:
        target = member or ctx.author
        username = await self.require_lastfm(ctx, target if target != ctx.author else None)
        if not username:
            return

        data = await lastfm_get({"method": "user.getRecentTracks", "user": username, "limit": 1, "extended": 1})
        if not data or "error" in data:
            await ctx.warn("Failed to fetch Last.fm data.")
            return

        tracks = data.get("recenttracks", {}).get("track", [])
        if not tracks:
            await ctx.warn(f"**{username}** hasn't scrobbled anything yet.")
            return

        track = tracks[0] if isinstance(tracks, list) else tracks

        song_name = track.get("name", "Unknown")
        artist_name = track.get("artist", {}).get("name", "Unknown")
        album_name = track.get("album", {}).get("#text", "Unknown")
        song_url = track.get("url", "https://last.fm/")
        images = track.get("image", [])
        cover_url = next((i["#text"] for i in reversed(images) if i.get("#text")), None)

        user_info = await lastfm_get({"method": "user.getInfo", "user": username})
        total_scrobbles = 0
        user_image = None
        if user_info and "user" in user_info:
            total_scrobbles = int(user_info["user"].get("playcount", 0))
            user_images = user_info["user"].get("image", [])
            user_image = next((i["#text"] for i in reversed(user_images) if i.get("#text")), None)

        reactions = await self.pool.fetchrow(
            "SELECT upvote, downvote FROM lastfm_reactions WHERE guild_id = $1", ctx.guild.id
        )
        upvote = reactions["upvote"] if reactions else "👍"
        downvote = reactions["downvote"] if reactions else "👎"

        embed = discord.Embed(color=EMBED_COLOR)
        embed.set_author(name=f"User: {username}", icon_url=user_image or None)
        embed.add_field(name="Track", value=f"[{song_name}]({song_url})", inline=True)
        embed.add_field(name="Album", value=f"[{album_name}]({song_url})", inline=True)
        if cover_url:
            embed.set_thumbnail(url=cover_url)
        embed.set_footer(text=f"Total Scrobbles: {total_scrobbles:,} • Artist: {artist_name}")

        msg = await ctx.reply(embed=embed, mention_author=False)
        await msg.add_reaction(upvote)
        await msg.add_reaction(downvote)

        if target == ctx.author:
            await self.check_milestone(ctx.author, total_scrobbles)

    @lastfm_group.command(
        name="profile",
        help="View your or another user's Last.fm profile.",
        extras={"parameters": "user", "usage": "lastfm profile (user)"},
    )
    @app_commands.describe(member="The user to check. Defaults to yourself.")
    async def lastfm_profile(self, ctx: TormentContext, member: discord.Member | None = None) -> None:
        target = member or ctx.author
        username = await self.require_lastfm(ctx, target if target != ctx.author else None)
        if not username:
            return

        async with ctx.typing():
            data = await lastfm_get({"method": "user.getInfo", "user": username})
            if not data or "error" in data:
                await ctx.warn(f"Failed to fetch **Last.fm** profile for **{username}**.")
                return

        user = data.get("user", {})
        scrobbles = int(user.get("playcount", 0))
        country = user.get("country") or "Unknown"
        registered_ts = int(user.get("registered", {}).get("unixtime", 0))
        images = user.get("image", [])
        avatar = next((i["#text"] for i in reversed(images) if i.get("#text")), None)

        embed = discord.Embed(
            description=f"[**View this profile on Last.fm**](https://last.fm/user/{username})",
            color=EMBED_COLOR,
        )
        embed.set_author(
            name=f"{target.display_name}'s Last.fm Profile",
            icon_url=avatar or target.display_avatar.url,
        )
        embed.add_field(name="Scrobbles", value=f"`{scrobbles:,}`", inline=True)
        embed.add_field(name="Country", value=f"**{country}**", inline=True)
        embed.add_field(name="Registered", value=f"<t:{registered_ts}:R>", inline=True)
        if avatar:
            embed.set_thumbnail(url=avatar)

        await ctx.reply(embed=embed, mention_author=False)

    @lastfm_group.command(
        name="toptracks",
        aliases=["tt"],
        help="View a user's top tracks.",
        extras={"parameters": "user", "usage": "lastfm toptracks (user)"},
    )
    @app_commands.describe(member="The user to check. Defaults to yourself.")
    async def lastfm_toptracks(self, ctx: TormentContext, member: discord.Member | None = None) -> None:
        target = member or ctx.author
        username = await self.require_lastfm(ctx, target if target != ctx.author else None)
        if not username:
            return

        async with ctx.typing():
            data = await lastfm_get({"method": "user.getTopTracks", "user": username, "limit": 100, "period": "overall"})
            if not data or "error" in data:
                await ctx.warn("Failed to fetch top tracks.")
                return

            tracks = data.get("toptracks", {}).get("track", [])
            if not tracks:
                await ctx.warn(f"No top tracks were found for **{username}**.")
                return

        lines = [
            f"`{'👑' if i == 1 else str(i).zfill(2)}` "
            f"[**{t['name']}**]({t['url']}) by **{t['artist']['name']}** "
            f"has {int(t['playcount']):,} plays"
            for i, t in enumerate(tracks[:10], 1)
        ]

        embed = discord.Embed(
            title=f"{target.display_name}'s top tracks",
            description="\n".join(lines),
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @lastfm_group.command(
        name="topartists",
        aliases=["ta"],
        help="View a user's top artists.",
        extras={"parameters": "user", "usage": "lastfm topartists (user)"},
    )
    @app_commands.describe(member="The user to check. Defaults to yourself.")
    async def lastfm_topartists(self, ctx: TormentContext, member: discord.Member | None = None) -> None:
        target = member or ctx.author
        username = await self.require_lastfm(ctx, target if target != ctx.author else None)
        if not username:
            return

        async with ctx.typing():
            data = await lastfm_get({"method": "user.getTopArtists", "user": username, "limit": 100, "period": "overall"})
            if not data or "error" in data:
                await ctx.warn("Failed to fetch top artists.")
                return

            artists = data.get("topartists", {}).get("artist", [])
            if not artists:
                await ctx.warn(f"No top artists were found for **{username}**.")
                return

        lines = [
            f"`{'👑' if i == 1 else str(i).zfill(2)}` "
            f"[**{a['name']}**]({a['url']}) "
            f"has {int(a['playcount']):,} plays"
            for i, a in enumerate(artists[:10], 1)
        ]

        embed = discord.Embed(
            title=f"{target.display_name}'s top artists",
            description="\n".join(lines),
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @lastfm_group.command(
        name="topalbums",
        help="View a user's top albums.",
        extras={"parameters": "user", "usage": "lastfm topalbums (user)"},
    )
    @app_commands.describe(member="The user to check. Defaults to yourself.")
    async def lastfm_topalbums(self, ctx: TormentContext, member: discord.Member | None = None) -> None:
        target = member or ctx.author
        username = await self.require_lastfm(ctx, target if target != ctx.author else None)
        if not username:
            return

        async with ctx.typing():
            data = await lastfm_get({"method": "user.getTopAlbums", "user": username, "limit": 100, "period": "overall"})
            if not data or "error" in data:
                await ctx.warn("Failed to fetch top albums.")
                return

            albums = data.get("topalbums", {}).get("album", [])
            if not albums:
                await ctx.warn(f"No top albums were found for **{username}**.")
                return

        lines = [
            f"`{'👑' if i == 1 else str(i).zfill(2)}` "
            f"[**{a['name']}**]({a['url']}) by **{a['artist']['name']}** "
            f"has {int(a['playcount']):,} plays"
            for i, a in enumerate(albums[:10], 1)
        ]

        embed = discord.Embed(
            title=f"{target.display_name}'s top albums",
            description="\n".join(lines),
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @lastfm_group.command(
        name="artist",
        help="View information on a music artist.",
        extras={"parameters": "artist", "usage": "lastfm artist (artist)"},
    )
    @app_commands.describe(artist="The artist to look up.")
    async def lastfm_artist(self, ctx: TormentContext, *, artist: str) -> None:
        data = await lastfm_get({"method": "artist.getInfo", "artist": artist})
        if not data or "error" in data:
            await ctx.warn(f"Couldn't find an artist named **{artist}**.")
            return

        info = data.get("artist", {})
        name = info.get("name", artist)
        url = info.get("url", "https://last.fm/")
        listeners = int(info.get("stats", {}).get("listeners", 0))
        playcount = int(info.get("stats", {}).get("playcount", 0))
        bio = info.get("bio", {}).get("summary", "No bio available.")
        bio = bio.split('<a href="https://www.last.fm')[0].strip()
        tags = [t["name"] for t in info.get("tags", {}).get("tag", [])[:5]]
        similar = [s["name"] for s in info.get("similar", {}).get("artist", [])[:5]]

        embed = discord.Embed(
            title=name,
            url=url,
            description=bio[:300] + "..." if len(bio) > 300 else bio,
            color=EMBED_COLOR,
        )
        embed.add_field(name="Listeners", value=f"{listeners:,}", inline=True)
        embed.add_field(name="Scrobbles", value=f"{playcount:,}", inline=True)
        if tags:
            embed.add_field(name="Tags", value=", ".join(tags), inline=False)
        if similar:
            embed.add_field(name="Similar Artists", value=", ".join(similar), inline=False)

        await ctx.reply(embed=embed, mention_author=False)

    @lastfm_group.command(
        name="reaction",
        aliases=["cr"],
        help="Set the Last.fm reactions for the embeds in your server.",
        extras={"parameters": "up, down", "usage": "lastfm reaction (up) (down)"},
    )
    @app_commands.describe(up="The upvote reaction.", down="The downvote reaction.")
    @commands.has_permissions(manage_guild=True)
    async def lastfm_reaction(self, ctx: TormentContext, up: str, down: str) -> None:
        def is_valid_emoji(emoji_str: str) -> bool:
            if len(emoji_str) <= 2:
                return True
            
            if emoji_str.startswith("<") and emoji_str.endswith(">"):
                emoji_id = emoji_str.split(":")[-1].rstrip(">")
                try:
                    emoji_id = int(emoji_id)
                    return discord.utils.get(ctx.guild.emojis, id=emoji_id) is not None
                except:
                    return False
            return False

        if not is_valid_emoji(up):
            return await ctx.warn("The upvote emoji must be from this server")
        
        if not is_valid_emoji(down):
            return await ctx.warn("The downvote emoji must be from this server")

        await self.pool.execute("""
            INSERT INTO lastfm_reactions (guild_id, upvote, downvote)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE
                SET upvote = EXCLUDED.upvote,
                    downvote = EXCLUDED.downvote
        """, ctx.guild.id, up, down)

        embed = discord.Embed(
            description=f"{ctx.author.mention}: Set the **Last.fm** reactions to {up} and {down}.",
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @lastfm_group.command(
        name="whoknows",
        aliases=["wk"],
        help="View what other users in the server listen to an artist.",
        extras={"parameters": "artist", "usage": "lastfm whoknows (artist)"},
    )
    @app_commands.describe(artist="The artist to look up.")
    async def lastfm_whoknows(self, ctx: TormentContext, *, artist: str) -> None:
        rows = await self.pool.fetch("SELECT user_id, username FROM lastfm_users")
        if not rows:
            await ctx.warn("No **Last.fm** users are registered in this server.")
            return

        async with ctx.typing():
            results: list[tuple[str, int, int]] = []
            for row in rows:
                member = ctx.guild.get_member(row["user_id"])
                if not member:
                    continue
                data = await lastfm_get({
                    "method": "artist.getInfo",
                    "artist": artist,
                    "username": row["username"],
                })
                if not data or "error" in data:
                    continue
                playcount = int(data.get("artist", {}).get("stats", {}).get("userplaycount", 0))
                if playcount > 0:
                    results.append((row["username"], playcount, row["user_id"]))

        if not results:
            await ctx.warn(f"Nobody in this server has listened to **{artist}**.")
            return

        results.sort(key=lambda x: x[1], reverse=True)

        lines = []
        for i, (username, plays, uid) in enumerate(results[:10], 1):
            rank = "👑" if i == 1 else str(i).zfill(2)
            lines.append(
                f"`{rank}` [**{username}**](https://last.fm/user/{username}) "
                f"has {plays:,} plays"
            )

        embed = discord.Embed(
            title=f"Who knows {artist}?",
            description="\n".join(lines),
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @lastfm_group.command(
        name="taste",
        help="Compare your music taste with another user.",
        extras={"parameters": "member, period", "usage": "lastfm taste (member) (period)"},
    )
    @app_commands.describe(member="The user to compare with.", period="The time period to compare.")
    @app_commands.choices(period=[
        app_commands.Choice(name="Overall", value="overall"),
        app_commands.Choice(name="7 Days", value="7day"),
        app_commands.Choice(name="1 Month", value="1month"),
        app_commands.Choice(name="3 Months", value="3month"),
        app_commands.Choice(name="6 Months", value="6month"),
        app_commands.Choice(name="12 Months", value="12month"),
    ])
    async def lastfm_taste(self, ctx: TormentContext, member: discord.Member, period: str = "overall") -> None:
        valid_periods = ["overall", "7day", "1month", "3month", "6month", "12month"]
        if period not in valid_periods:
            await ctx.warn(f"Invalid period. Choose from: {', '.join(f'`{p}`' for p in valid_periods)}")
            return

        my_username = await self.require_lastfm(ctx)
        if not my_username:
            return
        their_username = await self.require_lastfm(ctx, member)
        if not their_username:
            return

        async with ctx.typing():
            my_data = await lastfm_get({"method": "user.getTopArtists", "user": my_username, "limit": 50, "period": period})
            their_data = await lastfm_get({"method": "user.getTopArtists", "user": their_username, "limit": 50, "period": period})

        if not my_data or not their_data:
            await ctx.warn("Failed to fetch taste data.")
            return

        my_artists = {a["name"].lower(): int(a["playcount"]) for a in my_data.get("topartists", {}).get("artist", [])}
        their_artists = {a["name"].lower(): int(a["playcount"]) for a in their_data.get("topartists", {}).get("artist", [])}

        shared = set(my_artists.keys()) & set(their_artists.keys())
        if not shared:
            await ctx.warn(f"You and {member.mention} share no common artists in the **{period}** period.")
            return

        lines = [
            f"**{name.title()}** • You: {my_artists[name]:,} • Them: {their_artists[name]:,}"
            for name in sorted(shared, key=lambda n: my_artists[n] + their_artists[n], reverse=True)
        ]

        embed = discord.Embed(
            title=f"Taste comparison for you and {their_username}",
            description=f"You both share **{len(shared)}** mutual artists\n\n" + "\n".join(lines[:10]),
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @lastfm_group.command(
        name="recents",
        help="View what songs were recently listened to in the server.",
        extras={"parameters": "n/a", "usage": "lastfm recents"},
    )
    async def lastfm_recents(self, ctx: TormentContext) -> None:
        rows = await self.pool.fetch("SELECT user_id, username FROM lastfm_users")
        if not rows:
            await ctx.warn("No **Last.fm** users are registered in this server.")
            return

        async with ctx.typing():
            results: list[tuple[str, str, str, int, str]] = []
            for row in rows:
                member = ctx.guild.get_member(row["user_id"])
                if not member:
                    continue
                data = await lastfm_get({"method": "user.getRecentTracks", "user": row["username"], "limit": 1})
                if not data or "error" in data:
                    continue
                tracks = data.get("recenttracks", {}).get("track", [])
                if not tracks:
                    continue
                track = tracks[0] if isinstance(tracks, list) else tracks
                song = track.get("name", "Unknown")
                artist = track.get("artist", {}).get("#text", "Unknown")
                track_url = track.get("url", "https://last.fm/")
                results.append((row["username"], song, artist, row["user_id"], track_url))

        if not results:
            await ctx.warn("No recent activity found in this server.")
            return

        lines = [
            f"[**{username}**](https://last.fm/user/{username}): "
            f"[{song}]({track_url}) by **{artist}**"
            for username, song, artist, uid, track_url in results
        ]

        embed = discord.Embed(
            title="Recent Tracks",
            description="\n".join(lines[:10]),
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @lastfm_group.command(
        name="mostcrowns",
        aliases=["mc"],
        help="View users with the most crowns.",
        extras={"parameters": "n/a", "usage": "lastfm mostcrowns"},
    )
    async def lastfm_mostcrowns(self, ctx: TormentContext) -> None:
        rows = await self.pool.fetch("SELECT user_id, username FROM lastfm_users")
        if not rows:
            await ctx.warn("No **Last.fm** users are registered in this server.")
            return

        async with ctx.typing():
            crown_counts: list[tuple[str, int, int]] = []
            for row in rows:
                member = ctx.guild.get_member(row["user_id"])
                if not member:
                    continue
                data = await lastfm_get({"method": "user.getTopArtists", "user": row["username"], "limit": 200, "period": "overall"})
                if not data or "error" in data:
                    continue
                artists = data.get("topartists", {}).get("artist", [])
                crown_counts.append((row["username"], len(artists), row["user_id"]))

        if not crown_counts:
            await ctx.warn("No crown data available.")
            return

        crown_counts.sort(key=lambda x: x[1], reverse=True)

        lines = []
        for i, (username, count, uid) in enumerate(crown_counts[:10], 1):
            rank = "👑" if i == 1 else str(i).zfill(2)
            lines.append(
                f"`{rank}` [**{username}**](https://last.fm/user/{username}) "
                f"has {count:,} artists"
            )

        embed = discord.Embed(
            title="Most Crowns",
            description="\n".join(lines),
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)

    @lastfm_group.command(
        name="milestone",
        help="Set your scrobble milestone.",
        extras={"parameters": "number", "usage": "lastfm milestone (number)"},
    )
    @app_commands.describe(number="The scrobble count you want to be notified at.")
    async def lastfm_milestone(self, ctx: TormentContext, number: int) -> None:
        username = await self.require_lastfm(ctx)
        if not username:
            return

        data = await lastfm_get({"method": "user.getInfo", "user": username})
        if not data or "error" in data:
            await ctx.warn("Failed to fetch your Last.fm data.")
            return

        current_scrobbles = int(data["user"].get("playcount", 0))
        if number <= current_scrobbles:
            await ctx.warn(
                f"Your milestone must be **higher** than your current scrobble count of `{current_scrobbles:,}`."
            )
            return

        await self.pool.execute(
            "UPDATE lastfm_users SET milestone = $1 WHERE user_id = $2",
            number, ctx.author.id,
        )

        embed = discord.Embed(
            description=f"{ctx.author.mention}: Set your scrobble milestone to **{number:,}**.",
            color=EMBED_COLOR,
        )
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LastFM(bot))
