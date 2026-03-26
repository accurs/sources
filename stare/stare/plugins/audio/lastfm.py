import discord
from discord.ext import commands
import aiohttp
from stare.core.config import Config
from stare.core.tools.context import CustomContext as Context
from stare.core.tools.paginator import PaginatorView


class LastFM(commands.Cog):
    """Track your music listening with Last.fm integration and Spotify links"""
    
    def __init__(self, bot):
        self.bot = bot
        self.api_key = Config.KEYS.LASTFM if hasattr(Config, 'KEYS') and hasattr(Config.KEYS, 'LASTFM') else None
    
    async def cog_load(self):
        """Create lastfm table"""
        if not hasattr(self.bot, 'db_pool') or not self.bot.db_pool:
            return
        
        try:
            await self.bot.db_pool.execute("""
                CREATE TABLE IF NOT EXISTS lastfm (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT
                )
            """)
            print("✅ LastFM table created/verified")
        except Exception as e:
            print(f"❌ Error creating lastfm table: {e}")
    
    async def get_user(self, user_id):
        result = await self.bot.db_pool.fetchrow("SELECT username FROM lastfm WHERE user_id = $1", user_id)
        return result['username'] if result else None
    
    async def set_user(self, user_id, username):
        await self.bot.db_pool.execute("""
            INSERT INTO lastfm (user_id, username) VALUES ($1, $2) 
            ON CONFLICT (user_id) DO UPDATE SET username = $2
        """,
        user_id, username)
    
    async def fetch_lastfm(self, method, params):
        params.update({"method": method, "api_key": self.api_key, "format": "json"})
        async with aiohttp.ClientSession() as session:
            async with session.get("http://ws.audioscrobbler.com/2.0/", params=params) as resp:
                return await resp.json()
    
    async def fetch_album_art(self, artist, track, album=None):
        """Fetch album artwork with fallback to iTunes"""
        # Try iTunes API as fallback
        try:
            search_term = f"{artist} {track}"
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://itunes.apple.com/search",
                    params={"term": search_term, "media": "music", "entity": "song", "limit": 1}
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get("results", [])
                        if results:
                            # Get high quality artwork (600x600)
                            artwork_url = results[0].get("artworkUrl100", "")
                            if artwork_url:
                                # Replace 100x100 with 600x600 for better quality
                                return artwork_url.replace("100x100", "600x600")
        except:
            pass
        return None
    
    @commands.group(invoke_without_command=True, aliases=["fm", "lf"])
    async def lastfm(self, ctx: Context, *, user: discord.Member = None):
        """View currently playing track"""
        user = user or ctx.author
        username = await self.get_user(user.id)
        
        if not username:
            return await ctx.warn(f"{user.mention} hasn't set their last.fm")
        
        data = await self.fetch_lastfm("user.getrecenttracks", {"user": username, "limit": 4})
        
        if "error" in data:
            return await ctx.warn("couldn't fetch data")
        
        tracks = data.get("recenttracks", {}).get("track", [])
        if not tracks:
            return await ctx.send("no recent tracks")
        
        # Ensure tracks is a list
        if not isinstance(tracks, list):
            tracks = [tracks]
        
        # Create embeds for each track
        embeds = []
        for track in tracks[:4]:
            artist = track["artist"]["#text"]
            name = track["name"]
            album = track.get("album", {}).get("#text", "")
            track_url = track.get("url", "")
            image = track.get("image", [{}])[-1].get("#text", "")
            
            # Check if now playing
            is_playing = "@attr" in track and "nowplaying" in track["@attr"]
            status = "Now playing" if is_playing else "Last played"
            
            # Build artist and album URLs directly from Last.fm format
            artist_url = f"https://last.fm/music/{artist.replace(' ', '+')}"
            album_url = f"https://www.last.fm/music/{artist.replace(' ', '+')}/{album.replace(' ', '+')}" if album else ""
            
            # Build description
            desc_parts = []
            desc_parts.append(f"> By: [**{artist}**]({artist_url})")
            
            if album:
                desc_parts.append(f"> On: [**{album}**]({album_url})")
            
            e = discord.Embed(
                color=Config.COLORS.DEFAULT,
                title=name,
                url=track_url,
                description="\n".join(desc_parts)
            )
            
            # Try to get duration from track data if available
            duration_text = "Unknown"
            if "duration" in track and track["duration"] and int(track["duration"]) > 0:
                duration_sec = int(track["duration"])
                minutes = duration_sec // 60
                seconds = duration_sec % 60
                duration_text = f"{minutes}:{seconds:02d}"
            
            e.set_author(
                name=f"{status} for {username}",
                icon_url=user.display_avatar.url
            )
            
            # Set thumbnail - use Last.fm image or fallback
            if image:
                e.set_thumbnail(url=image)
            
            # Add duration footer with Last.fm icon
            e.set_footer(
                text=duration_text,
                icon_url="https://cdn.discordapp.com/attachments/1472371956165902449/1472753890612088973/ezgif-frame-001.png"
            )
            
            embeds.append(e)
        
        # Use paginator if multiple tracks
        if len(embeds) > 1:
            view = PaginatorView(embeds, user=ctx.author)
            msg = await ctx.send(embed=embeds[0], view=view)
        else:
            msg = await ctx.send(embed=embeds[0])
        
        # Add reactions for voting
        try:
            await msg.add_reaction('👍')
            await msg.add_reaction('👎')
        except:
            pass
    
    @lastfm.command(name='login', aliases=["set"])
    async def lastfm_login(self, ctx: Context, username: str):
        """Set your Last.fm username"""
        await self.set_user(ctx.author.id, username)
        await ctx.approve(f"set your last.fm to **{username}**")
    
    @lastfm.command(name='remove', aliases=["logout"])
    async def lastfm_remove(self, ctx: Context):
        """Remove your Last.fm username"""
        username = await self.get_user(ctx.author.id)
        if not username:
            return await ctx.warn("you don't have a last.fm set")
        
        await self.bot.db_pool.execute("DELETE FROM lastfm WHERE user_id = $1", ctx.author.id)
        await ctx.approve("removed your last.fm")
    
    @lastfm.command(name='toptracks', aliases=['tt'])
    async def lastfm_toptracks(self, ctx: Context, user: discord.Member = None, period: str = "overall"):
        """View top tracks"""
        user = user or ctx.author
        username = await self.get_user(user.id)
        
        if not username:
            return await ctx.warn(f"{user.mention} hasn't set their last.fm")
        
        periods = {"7day": "7day", "1month": "1month", "3month": "3month", "6month": "6month", "12month": "12month", "overall": "overall"}
        period = periods.get(period, "overall")
        
        data = await self.fetch_lastfm("user.gettoptracks", {"user": username, "period": period, "limit": 10})
        
        if "error" in data:
            return await ctx.warn("couldn't fetch data")
        
        tracks = data.get("toptracks", {}).get("track", [])
        if not tracks:
            return await ctx.send("no top tracks")
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name=f"{user.name}'s top tracks", icon_url=user.display_avatar.url)
        
        desc = []
        for i, track in enumerate(tracks[:10], 1):
            desc.append(f"`{i}` **{track['name']}** by {track['artist']['name']} ({track['playcount']} plays)")
        
        embed.description = "\n".join(desc)
        await ctx.send(embed=embed)
    
    @lastfm.command(name='topartists', aliases=['ta'])
    async def lastfm_topartists(self, ctx: Context, user: discord.Member = None, period: str = "overall"):
        """View top artists"""
        user = user or ctx.author
        username = await self.get_user(user.id)
        
        if not username:
            return await ctx.warn(f"{user.mention} hasn't set their last.fm")
        
        periods = {"7day": "7day", "1month": "1month", "3month": "3month", "6month": "6month", "12month": "12month", "overall": "overall"}
        period = periods.get(period, "overall")
        
        data = await self.fetch_lastfm("user.gettopartists", {"user": username, "period": period, "limit": 10})
        
        if "error" in data:
            return await ctx.warn("couldn't fetch data")
        
        artists = data.get("topartists", {}).get("artist", [])
        if not artists:
            return await ctx.send("no top artists")
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name=f"{user.name}'s top artists", icon_url=user.display_avatar.url)
        
        desc = []
        for i, artist in enumerate(artists[:10], 1):
            desc.append(f"`{i}` **{artist['name']}** ({artist['playcount']} plays)")
        
        embed.description = "\n".join(desc)
        await ctx.send(embed=embed)

    
    @lastfm.command(name='topalbums', aliases=['tab'])
    async def lastfm_topalbums(self, ctx: Context, user: discord.Member = None, period: str = "overall"):
        """View top albums"""
        user = user or ctx.author
        username = await self.get_user(user.id)
        
        if not username:
            return await ctx.warn(f"{user.mention} hasn't set their last.fm")
        
        periods = {"7day": "7day", "1month": "1month", "3month": "3month", "6month": "6month", "12month": "12month", "overall": "overall"}
        period = periods.get(period, "overall")
        
        data = await self.fetch_lastfm("user.gettopalbums", {"user": username, "period": period, "limit": 10})
        
        if "error" in data:
            return await ctx.warn("couldn't fetch data")
        
        albums = data.get("topalbums", {}).get("album", [])
        if not albums:
            return await ctx.send("no top albums")
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name=f"{user.name}'s top albums", icon_url=user.display_avatar.url)
        
        desc = []
        for i, album in enumerate(albums[:10], 1):
            desc.append(f"`{i}` **{album['name']}** by {album['artist']['name']} ({album['playcount']} plays)")
        
        embed.description = "\n".join(desc)
        await ctx.send(embed=embed)
    
    @lastfm.command(name='recent', aliases=['recents'])
    async def lastfm_recent(self, ctx: Context, user: discord.Member = None):
        """View recent tracks"""
        user = user or ctx.author
        username = await self.get_user(user.id)
        
        if not username:
            return await ctx.warn(f"{user.mention} hasn't set their last.fm")
        
        data = await self.fetch_lastfm("user.getrecenttracks", {"user": username, "limit": 10})
        
        if "error" in data:
            return await ctx.warn("couldn't fetch data")
        
        tracks = data.get("recenttracks", {}).get("track", [])
        if not tracks:
            return await ctx.send("no recent tracks")
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name=f"{user.name}'s recent tracks", icon_url=user.display_avatar.url)
        
        desc = []
        for i, track in enumerate(tracks[:10], 1):
            nowplaying = "@attr" in track and "nowplaying" in track["@attr"]
            prefix = "🎵" if nowplaying else f"`{i}`"
            desc.append(f"{prefix} **{track['name']}** by {track['artist']['#text']}")
        
        embed.description = "\n".join(desc)
        await ctx.send(embed=embed)
    
    @lastfm.command(name='whoknows', aliases=['wk'])
    async def lastfm_whoknows(self, ctx: Context, *, artist: str):
        """Who knows an artist in this server"""
        members = []
        rows = await self.bot.db_pool.fetch("SELECT user_id, username FROM lastfm")
        
        for row in rows:
            user_id = row['user_id']
            username = row['username']
            member = ctx.guild.get_member(user_id)
            
            if member:
                data = await self.fetch_lastfm("artist.getinfo", {"user": username, "artist": artist})
                if "error" not in data and "artist" in data:
                    plays = int(data['artist']['stats']['userplaycount'])
                    if plays > 0:
                        members.append((member, plays))
        
        if not members:
            return await ctx.send("nobody knows this artist")
        
        members.sort(key=lambda x: x[1], reverse=True)
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name=f"who knows {artist}")
        
        desc = []
        for i, (member, plays) in enumerate(members[:10], 1):
            desc.append(f"`{i}` **{member.name}** - {plays} plays")
        
        embed.description = "\n".join(desc)
        await ctx.send(embed=embed)
    
    @lastfm.command(name='now', aliases=['np'])
    async def lastfm_now(self, ctx: Context, user: discord.Member = None):
        """Shows your current song playing from Last.fm"""
        await ctx.invoke(self.lastfm, user=user)
    
    @lastfm.command(name='taste')
    async def lastfm_taste(self, ctx: Context, member: discord.Member, period: str = "overall"):
        """Compare your music taste between you and someone else"""
        user1 = await self.get_user(ctx.author.id)
        user2 = await self.get_user(member.id)
        
        if not user1:
            return await ctx.warn("you haven't set your last.fm")
        if not user2:
            return await ctx.warn(f"{member.mention} hasn't set their last.fm")
        
        data = await self.fetch_lastfm("tasteometer.compare", {"type1": "user", "type2": "user", "value1": user1, "value2": user2})
        
        if "error" in data:
            return await ctx.warn("couldn't fetch data")
        
        score = float(data.get("comparison", {}).get("result", {}).get("score", 0)) * 100
        artists = data.get("comparison", {}).get("result", {}).get("artists", {}).get("artist", [])
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name=f"taste comparison")
        embed.description = f"**{ctx.author.name}** and **{member.name}** have **{score:.1f}%** compatibility"
        
        if artists:
            common = ", ".join([a["name"] for a in artists[:5]])
            embed.add_field(name="common artists", value=common, inline=False)
        
        await ctx.send(embed=embed)
    
    @lastfm.command(name='count')
    async def lastfm_count(self, ctx: Context, user: discord.Member = None):
        """View your total Last.fm scrobbles"""
        user = user or ctx.author
        username = await self.get_user(user.id)
        
        if not username:
            return await ctx.warn(f"{user.mention} hasn't set their last.fm")
        
        data = await self.fetch_lastfm("user.getinfo", {"user": username})
        
        if "error" in data:
            return await ctx.warn("couldn't fetch data")
        
        playcount = data.get("user", {}).get("playcount", "0")
        await ctx.send(f"**{user.name}** has **{playcount}** scrobbles")
    
    @lastfm.command(name='plays')
    async def lastfm_plays(self, ctx: Context, member: discord.Member = None, *, artist: str):
        """Check how many plays you have for an artist"""
        user = member or ctx.author
        username = await self.get_user(user.id)
        
        if not username:
            return await ctx.warn(f"{user.mention} hasn't set their last.fm")
        
        data = await self.fetch_lastfm("artist.getinfo", {"user": username, "artist": artist})
        
        if "error" in data:
            return await ctx.warn("couldn't find that artist")
        
        plays = data.get("artist", {}).get("stats", {}).get("userplaycount", "0")
        artist_name = data.get("artist", {}).get("name", artist)
        
        await ctx.send(f"**{user.name}** has **{plays}** plays for **{artist_name}**")
    
    @lastfm.command(name='playstrack', aliases=['pt'])
    async def lastfm_playstrack(self, ctx: Context, member: discord.Member = None, *, query: str):
        """Check how many plays you have for a specific track"""
        user = member or ctx.author
        username = await self.get_user(user.id)
        
        if not username:
            return await ctx.warn(f"{user.mention} hasn't set their last.fm")
        
        parts = query.split(" - ")
        if len(parts) != 2:
            return await ctx.warn("use format: artist - track")
        
        artist, track = parts[0].strip(), parts[1].strip()
        
        data = await self.fetch_lastfm("track.getinfo", {"user": username, "artist": artist, "track": track})
        
        if "error" in data:
            return await ctx.warn("couldn't find that track")
        
        plays = data.get("track", {}).get("userplaycount", "0")
        track_name = data.get("track", {}).get("name", track)
        artist_name = data.get("track", {}).get("artist", {}).get("name", artist)
        
        await ctx.send(f"**{user.name}** has **{plays}** plays for **{track_name}** by **{artist_name}**")
    
    @lastfm.command(name='whois', aliases=['profile'])
    async def lastfm_whois(self, ctx: Context, user: discord.Member = None):
        """View Last.fm profile information"""
        user = user or ctx.author
        username = await self.get_user(user.id)
        
        if not username:
            return await ctx.warn(f"{user.mention} hasn't set their last.fm")
        
        data = await self.fetch_lastfm("user.getinfo", {"user": username})
        
        if "error" in data:
            return await ctx.warn("couldn't fetch data")
        
        user_data = data.get("user", {})
        playcount = user_data.get("playcount", "0")
        registered = user_data.get("registered", {}).get("unixtime", "0")
        country = user_data.get("country", "Unknown")
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name=f"{username}'s profile", url=user_data.get("url", ""))
        embed.add_field(name="scrobbles", value=playcount)
        embed.add_field(name="country", value=country)
        embed.add_field(name="registered", value=f"<t:{registered}:R>")
        
        await ctx.send(embed=embed)
    
    @lastfm.command(name='wktrack', aliases=['wkt'])
    async def lastfm_wktrack(self, ctx: Context, *, track: str):
        """View the top listeners for a specific song by an artist"""
        parts = track.split(" - ")
        if len(parts) != 2:
            return await ctx.warn("use format: artist - track")
        
        artist, track_name = parts[0].strip(), parts[1].strip()
        members = []
        rows = await self.bot.db_pool.fetch("SELECT user_id, username FROM lastfm")
        
        for row in rows:
            user_id = row['user_id']
            username = row['username']
            member = ctx.guild.get_member(user_id)
            
            if member:
                data = await self.fetch_lastfm("track.getinfo", {"user": username, "artist": artist, "track": track_name})
                if "error" not in data and "track" in data:
                    plays = int(data['track'].get('userplaycount', 0))
                    if plays > 0:
                        members.append((member, plays))
        
        if not members:
            return await ctx.send("nobody knows this track")
        
        members.sort(key=lambda x: x[1], reverse=True)
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name=f"who knows {track_name}")
        
        desc = []
        for i, (member, plays) in enumerate(members[:10], 1):
            desc.append(f"`{i}` **{member.name}** - {plays} plays")
        
        embed.description = "\n".join(desc)
        await ctx.send(embed=embed)
    
    @lastfm.command(name='wkalbum', aliases=['wka'])
    async def lastfm_wkalbum(self, ctx: Context, *, album: str):
        """View the top listeners for an album by an artist"""
        parts = album.split(" - ")
        if len(parts) != 2:
            return await ctx.warn("use format: artist - album")
        
        artist, album_name = parts[0].strip(), parts[1].strip()
        members = []
        rows = await self.bot.db_pool.fetch("SELECT user_id, username FROM lastfm")
        
        for row in rows:
            user_id = row['user_id']
            username = row['username']
            member = ctx.guild.get_member(user_id)
            
            if member:
                data = await self.fetch_lastfm("album.getinfo", {"user": username, "artist": artist, "album": album_name})
                if "error" not in data and "album" in data:
                    plays = int(data['album'].get('userplaycount', 0))
                    if plays > 0:
                        members.append((member, plays))
        
        if not members:
            return await ctx.send("nobody knows this album")
        
        members.sort(key=lambda x: x[1], reverse=True)
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name=f"who knows {album_name}")
        
        desc = []
        for i, (member, plays) in enumerate(members[:10], 1):
            desc.append(f"`{i}` **{member.name}** - {plays} plays")
        
        embed.description = "\n".join(desc)
        await ctx.send(embed=embed)
    
    @lastfm.command(name='recentfor', aliases=['rf'])
    async def lastfm_recentfor(self, ctx: Context, *, artist: str):
        """View your recent tracks for an artist"""
        username = await self.get_user(ctx.author.id)
        
        if not username:
            return await ctx.warn("you haven't set your last.fm")
        
        data = await self.fetch_lastfm("user.getrecenttracks", {"user": username, "limit": 200})
        
        if "error" in data:
            return await ctx.warn("couldn't fetch data")
        
        tracks = data.get("recenttracks", {}).get("track", [])
        filtered = [t for t in tracks if t['artist']['#text'].lower() == artist.lower()][:10]
        
        if not filtered:
            return await ctx.send(f"no recent tracks for **{artist}**")
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name=f"recent tracks for {artist}", icon_url=ctx.author.display_avatar.url)
        
        desc = []
        for i, track in enumerate(filtered, 1):
            desc.append(f"`{i}` **{track['name']}**")
        
        embed.description = "\n".join(desc)
        await ctx.send(embed=embed)
    
    @lastfm.command(name='toptenalbums', aliases=['tta'])
    async def lastfm_toptenalbums(self, ctx: Context, member: discord.Member = None, *, artist: str):
        """View your top ten albums for an artist"""
        user = member or ctx.author
        username = await self.get_user(user.id)
        
        if not username:
            return await ctx.warn(f"{user.mention} hasn't set their last.fm")
        
        data = await self.fetch_lastfm("artist.gettopalbums", {"user": username, "artist": artist, "limit": 10})
        
        if "error" in data:
            return await ctx.warn("couldn't find that artist")
        
        albums = data.get("topalbums", {}).get("album", [])
        if not albums:
            return await ctx.send(f"no albums found for **{artist}**")
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name=f"{user.name}'s top albums for {artist}", icon_url=user.display_avatar.url)
        
        desc = []
        for i, album in enumerate(albums[:10], 1):
            desc.append(f"`{i}` **{album['name']}** ({album['playcount']} plays)")
        
        embed.description = "\n".join(desc)
        await ctx.send(embed=embed)
    
    @lastfm.command(name='toptentracks', aliases=['ttt'])
    async def lastfm_toptentracks(self, ctx: Context, member: discord.Member = None, *, artist: str):
        """View your top ten tracks for an artist"""
        user = member or ctx.author
        username = await self.get_user(user.id)
        
        if not username:
            return await ctx.warn(f"{user.mention} hasn't set their last.fm")
        
        data = await self.fetch_lastfm("artist.gettoptracks", {"user": username, "artist": artist, "limit": 10})
        
        if "error" in data:
            return await ctx.warn("couldn't find that artist")
        
        tracks = data.get("toptracks", {}).get("track", [])
        if not tracks:
            return await ctx.send(f"no tracks found for **{artist}**")
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name=f"{user.name}'s top tracks for {artist}", icon_url=user.display_avatar.url)
        
        desc = []
        for i, track in enumerate(tracks[:10], 1):
            desc.append(f"`{i}` **{track['name']}** ({track['playcount']} plays)")
        
        embed.description = "\n".join(desc)
        await ctx.send(embed=embed)
    
    @lastfm.command(name='overview', aliases=['ov'])
    async def lastfm_overview(self, ctx: Context, member: discord.Member = None, *, artist: str):
        """See your statistics for an artist"""
        user = member or ctx.author
        username = await self.get_user(user.id)
        
        if not username:
            return await ctx.warn(f"{user.mention} hasn't set their last.fm")
        
        data = await self.fetch_lastfm("artist.getinfo", {"user": username, "artist": artist})
        
        if "error" in data:
            return await ctx.warn("couldn't find that artist")
        
        artist_data = data.get("artist", {})
        plays = artist_data.get("stats", {}).get("userplaycount", "0")
        artist_name = artist_data.get("name", artist)
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name=f"{user.name}'s overview for {artist_name}", icon_url=user.display_avatar.url)
        embed.add_field(name="plays", value=plays)
        
        await ctx.send(embed=embed)
    
    @lastfm.command(name='playsalbum', aliases=['pa'])
    async def lastfm_playsalbum(self, ctx: Context, member: discord.Member = None, *, query: str):
        """Check how many plays you have for an album"""
        user = member or ctx.author
        username = await self.get_user(user.id)
        
        if not username:
            return await ctx.warn(f"{user.mention} hasn't set their last.fm")
        
        parts = query.split(" - ")
        if len(parts) != 2:
            return await ctx.warn("use format: artist - album")
        
        artist, album = parts[0].strip(), parts[1].strip()
        
        data = await self.fetch_lastfm("album.getinfo", {"user": username, "artist": artist, "album": album})
        
        if "error" in data:
            return await ctx.warn("couldn't find that album")
        
        plays = data.get("album", {}).get("userplaycount", "0")
        album_name = data.get("album", {}).get("name", album)
        
        await ctx.send(f"**{user.name}** has **{plays}** plays for **{album_name}**")
    
    @lastfm.command(name='spotify', aliases=['sp'])
    async def lastfm_spotify(self, ctx: Context, user: discord.Member = None):
        """Gives Spotify link for the current song playing"""
        user = user or ctx.author
        username = await self.get_user(user.id)
        
        if not username:
            return await ctx.warn(f"{user.mention} hasn't set their last.fm")
        
        data = await self.fetch_lastfm("user.getrecenttracks", {"user": username, "limit": 1})
        
        if "error" in data:
            return await ctx.warn("couldn't fetch data")
        
        tracks = data.get("recenttracks", {}).get("track", [])
        if not tracks:
            return await ctx.send("no recent tracks")
        
        track = tracks[0] if isinstance(tracks, list) else tracks
        artist = track["artist"]["#text"]
        name = track["name"]
        
        # Search Spotify
        search_query = f"{artist} {name}"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.spotify.com/v1/search",
                params={"q": search_query, "type": "track", "limit": 1},
                headers={"Authorization": f"Bearer {await self.get_spotify_token()}"}
            ) as resp:
                if resp.status != 200:
                    return await ctx.warn("couldn't search spotify")
                
                spotify_data = await resp.json()
                items = spotify_data.get("tracks", {}).get("items", [])
                
                if not items:
                    return await ctx.send(f"couldn't find **{name}** by **{artist}** on spotify")
                
                spotify_url = items[0]["external_urls"]["spotify"]
                await ctx.send(f"**{name}** by **{artist}**\n{spotify_url}")
    
    async def get_spotify_token(self):
        """Get Spotify access token"""
        if not hasattr(Config, 'KEYS') or not hasattr(Config.KEYS, 'SPOTIFY_CLIENT_ID') or not hasattr(Config.KEYS, 'SPOTIFY_CLIENT_SECRET'):
            return None
        
        client_id = Config.KEYS.SPOTIFY_CLIENT_ID
        client_secret = Config.KEYS.SPOTIFY_CLIENT_SECRET
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://accounts.spotify.com/api/token",
                data={"grant_type": "client_credentials"},
                auth=aiohttp.BasicAuth(client_id, client_secret)
            ) as resp:
                data = await resp.json()
                return data.get("access_token")
    
    @commands.command(name='spotify', aliases=['sp'])
    async def spotify_standalone(self, ctx: Context, *, arg: str = None):
        """Gives Spotify link for the current song playing, from a Last.fm URL, or YouTube link"""
        # Check if arg is a YouTube URL
        if arg and ("youtube.com" in arg or "youtu.be" in arg):
            import re
            
            # Extract video ID from YouTube URL
            video_id = None
            if "youtu.be/" in arg:
                video_id = arg.split("youtu.be/")[1].split("?")[0].split("&")[0]
            elif "youtube.com" in arg:
                match = re.search(r'[?&]v=([^&]+)', arg)
                if match:
                    video_id = match.group(1)
            
            if not video_id:
                return await ctx.warn("couldn't extract video ID from YouTube URL")
            
            try:
                # Fetch video info from YouTube API (using oembed which doesn't require API key)
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
                    ) as resp:
                        if resp.status != 200:
                            return await ctx.warn("couldn't fetch YouTube video info")
                        
                        yt_data = await resp.json()
                        title = yt_data.get("title", "")
                        
                        if not title:
                            return await ctx.warn("couldn't get video title")
                        
                        # Search Spotify with the video title
                        async with session.get(
                            "https://api.spotify.com/v1/search",
                            params={"q": title, "type": "track", "limit": 1},
                            headers={"Authorization": f"Bearer {await self.get_spotify_token()}"}
                        ) as spotify_resp:
                            if spotify_resp.status != 200:
                                return await ctx.warn("couldn't search spotify")
                            
                            spotify_data = await spotify_resp.json()
                            items = spotify_data.get("tracks", {}).get("items", [])
                            
                            if not items:
                                return await ctx.send(f"couldn't find **{title}** on spotify")
                            
                            track_name = items[0]["name"]
                            artist_name = items[0]["artists"][0]["name"]
                            spotify_url = items[0]["external_urls"]["spotify"]
                            return await ctx.send(f"**{track_name}** by **{artist_name}**\n{spotify_url}")
            except Exception as e:
                return await ctx.warn(f"error processing YouTube link: {str(e)}")
        
        # Check if arg is a Last.fm URL
        if arg and ("last.fm" in arg or "lastfm" in arg):
            # Extract track info from URL
            # URL formats: 
            # https://www.last.fm/music/Artist/_/Track
            # https://last.fm/music/Artist/_/Track
            import urllib.parse
            
            try:
                # Parse the URL
                if "/music/" in arg:
                    parts = arg.split("/music/")[1].split("/")
                    if len(parts) >= 3 and parts[1] == "_":
                        # Decode URL encoding
                        artist = urllib.parse.unquote(parts[0]).replace("+", " ")
                        track = urllib.parse.unquote(parts[2]).replace("+", " ")
                        
                        # Search Spotify
                        search_query = f"{artist} {track}"
                        async with aiohttp.ClientSession() as session:
                            async with session.get(
                                "https://api.spotify.com/v1/search",
                                params={"q": search_query, "type": "track", "limit": 1},
                                headers={"Authorization": f"Bearer {await self.get_spotify_token()}"}
                            ) as resp:
                                if resp.status != 200:
                                    return await ctx.warn("couldn't search spotify")
                                
                                spotify_data = await resp.json()
                                items = spotify_data.get("tracks", {}).get("items", [])
                                
                                if not items:
                                    return await ctx.send(f"couldn't find **{track}** by **{artist}** on spotify")
                                
                                spotify_url = items[0]["external_urls"]["spotify"]
                                return await ctx.send(f"**{track}** by **{artist}**\n{spotify_url}")
                    else:
                        return await ctx.warn("invalid last.fm URL format")
                else:
                    return await ctx.warn("invalid last.fm URL")
            except Exception as e:
                return await ctx.warn(f"couldn't parse last.fm URL: {e}")
        
        # Otherwise, treat as user mention or get current user's track
        user = None
        if arg:
            try:
                # Try to convert to member
                user = await commands.MemberConverter().convert(ctx, arg)
            except:
                return await ctx.warn("invalid user or URL")
        
        await ctx.invoke(self.lastfm_spotify, user=user)


async def setup(bot):
    await bot.add_cog(LastFM(bot))
