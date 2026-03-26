import discord
from discord.ext import commands
from discord import app_commands
import pomice
import aiohttp
import re
from bs4 import BeautifulSoup
from stare.core.config import Config
from stare.core.tools.context import CustomContext as Context
from stare.core.tools.paginator import PaginatorView


def format_duration(ms) -> str:
    if not ms:
        return "Unknown"
    seconds = int(ms) // 1000
    if seconds < 3600:
        return f"{seconds // 60}:{seconds % 60:02d}"
    return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def get_track_title(track) -> str:
    """Get track title safely"""
    if hasattr(track, 'title') and track.title:
        return track.title
    return "Unknown Title"


def get_track_author(track) -> str:
    """Get track author/artist safely"""
    if hasattr(track, 'author') and track.author:
        return track.author
    if hasattr(track, 'artist') and track.artist:
        return track.artist
    return "Unknown Artist"


def get_track_artwork(track) -> str | None:
    """Get track artwork URL safely"""
    if hasattr(track, 'artwork') and track.artwork:
        return track.artwork
    if hasattr(track, 'thumb') and track.thumb:
        return track.thumb
    if hasattr(track, 'thumbnail') and track.thumbnail:
        return track.thumbnail
    return None


def get_track_uri(track) -> str | None:
    """Get track URI safely"""
    if hasattr(track, 'uri') and track.uri:
        return track.uri
    return None


def get_track_length(track) -> int:
    """Get track length in ms safely"""
    if hasattr(track, 'length') and track.length:
        return track.length
    if hasattr(track, 'duration') and track.duration:
        return track.duration
    return 0


class NowPlayingControls(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=60)
        self.player = player

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def rewind_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player and self.player.current:
            await self.player.seek(0)
            await interaction.response.send_message("Restarted", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing playing", ephemeral=True)

    @discord.ui.button(label="▐▐", style=discord.ButtonStyle.secondary)
    async def pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player:
            if self.player.is_paused:
                await self.player.set_pause(False)
                await interaction.response.send_message("Resumed", ephemeral=True)
            else:
                await self.player.set_pause(True)
                await interaction.response.send_message("Paused", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing playing", ephemeral=True)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player and self.player.is_playing:
            await self.player.stop()
            await interaction.response.send_message("Skipped", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing playing", ephemeral=True)


class Music(commands.Cog):
    """Music player and audio controls"""

    def __init__(self, bot):
        self.bot = bot
        self.loop_mode = {}
        self.requesters = {}
        self.twentyfourseven = {}
        self.active_filters = {}
        self.music_channels = {}
        self.pomice_node = None
        self.queues = {}  # guild_id: list of tracks

    async def cog_load(self):
        """Setup Pomice node connection"""
        # Don't block bot startup - connect to Lavalink after bot is ready
        pass
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Connect to Lavalink after bot is ready"""
        if not self.pomice_node:
            try:
                self.pomice_node = await pomice.NodePool.create_node(
                    bot=self.bot,
                    host="lavahatry4.techbyte.host",
                    port=3000,
                    password="naig.is-a.dev",
                    identifier="MAIN",
                    secure=False,
                    spotify_client_id=Config.KEYS.SPOTIFY_CLIENT_ID,
                    spotify_client_secret=Config.KEYS.SPOTIFY_CLIENT_SECRET
                )
                print("✅ Connected to Lavalink (Pomice)")
            except Exception as e:
                print(f"❌ Failed to connect to Lavalink: {e}")

    async def cog_unload(self):
        """Cleanup on unload"""
        try:
            if self.pomice_node:
                await self.pomice_node.disconnect()
        except:
            pass

    async def check_channel(self, ctx):
        """Check if command is in allowed music channel"""
        music_channel_id = self.music_channels.get(ctx.guild.id)
        if music_channel_id and ctx.channel.id != music_channel_id:
            await ctx.deny(f"Music commands only allowed in <#{music_channel_id}>")
            return False
        return True

    async def set_vc_status(self, player, track):
        """Set the voice channel status to show currently playing"""
        try:
            if player and player.channel:
                title = get_track_title(track)
                artist = get_track_author(track)
                status = f"Currently Playing {artist} - {title}"
                if len(status) > 100:
                    status = status[:97] + "..."
                await player.channel.edit(status=status)
        except Exception as e:
            print(f"[Music] Failed to set VC status: {e}")

    async def clear_vc_status(self, player):
        """Clear the voice channel status"""
        try:
            if player and player.channel:
                await player.channel.edit(status=None)
        except Exception as e:
            print(f"[Music] Failed to clear VC status: {e}")

    async def send_now_playing(self, ctx, track):
        """Send the now playing embed with controls"""
        player = ctx.voice_client
        requester = self.requesters.get(ctx.guild.id, {}).get(track.track_id if hasattr(track, 'track_id') else track.uri)

        title = get_track_title(track)
        duration = format_duration(get_track_length(track))
        artwork = get_track_artwork(track)

        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(
            name="Now Playing",
            icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/8/84/Spotify_icon.svg/1982px-Spotify_icon.svg.png"
        )

        desc = f"• {title}\n• Duration: `{duration}`"
        if requester:
            desc += f" - ( {requester.mention} )"
        embed.description = desc

        if artwork:
            embed.set_thumbnail(url=artwork)

        await ctx.send(embed=embed, view=NowPlayingControls(player))

    @commands.Cog.listener()
    async def on_pomice_track_end(self, player: pomice.Player, track, reason):
        """Handle track end events"""
        if not player or not player.guild:
            return

        guild_id = player.guild.id
        loop_mode = self.loop_mode.get(guild_id, "off")
        queue = self.queues.get(guild_id, [])

        if loop_mode == "song" and track:
            await player.play(track)
            await self.set_vc_status(player, track)
            return

        if loop_mode == "queue" and track:
            queue.append(track)
            self.queues[guild_id] = queue

        if queue:
            next_track = queue.pop(0)
            self.queues[guild_id] = queue
            await player.play(next_track)
            await self.set_vc_status(player, next_track)
        else:
            await self.clear_vc_status(player)

    @commands.Cog.listener()
    async def on_pomice_track_exception(self, player: pomice.Player, track, exception):
        """Handle track playback errors"""
        if player and hasattr(player, 'text_channel') and player.text_channel:
            await player.text_channel.send(f"❌ Error playing track: {exception}")
        print(f"[Music] Track exception: {exception}")

    @commands.Cog.listener()
    async def on_pomice_track_stuck(self, player: pomice.Player, track, threshold):
        """Handle stuck tracks"""
        if player:
            print(f"[Music] Track stuck, skipping...")
            await player.stop()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Handle 24/7 mode - stay in VC even when alone"""
        if member.id == self.bot.user.id:
            return

        if not before.channel:
            return

        guild_id = before.channel.guild.id
        player = before.channel.guild.voice_client

        if not player or not isinstance(player, pomice.Player):
            return

        if self.twentyfourseven.get(guild_id, False):
            return

        if player.channel and player.channel == before.channel:
            human_members = [m for m in player.channel.members if not m.bot]
            if len(human_members) == 0:
                await self.clear_vc_status(player)
                await player.disconnect()

    @commands.hybrid_command()
    @app_commands.describe(search="Song name, artist, or URL to play")
    async def play(self, ctx: Context, *, search: str = None):
        """Play a song or add it to the queue"""
        if not search:
            return await ctx.deny("Please provide a song to search")

        if not await self.check_channel(ctx):
            return

        if not ctx.author.voice:
            return await ctx.deny("Join a voice channel first")

        if not self.pomice_node:
            return await ctx.deny("Music server not connected. Try again in a moment.")

        player = ctx.voice_client

        if not player:
            try:
                player = await ctx.author.voice.channel.connect(cls=pomice.Player)
                player.text_channel = ctx.channel
            except Exception as e:
                return await ctx.deny(f"Could not join voice channel: {e}")

        guild_id = ctx.guild.id
        self.loop_mode.setdefault(guild_id, "off")
        self.requesters.setdefault(guild_id, {})
        self.queues.setdefault(guild_id, [])

        try:
            tracks = None

            if search.startswith(("http://", "https://")):
                tracks = await player.get_tracks(search)
            else:
                # Try Deezer first
                try:
                    tracks = await player.get_tracks(f"dzsearch:{search}")
                except:
                    pass

                # Fallback to SoundCloud
                if not tracks:
                    try:
                        tracks = await player.get_tracks(f"scsearch:{search}")
                    except:
                        pass

        except Exception as e:
            print(f"[Music] Search error: {e}")
            return await ctx.deny(f"Search error: {e}")

        if not tracks:
            return await ctx.deny("Could not find that song")

        try:
            await ctx.message.delete()
        except:
            pass

        if isinstance(tracks, pomice.Playlist):
            for track in tracks.tracks:
                track_id = track.track_id if hasattr(track, 'track_id') else track.uri
                self.requesters[guild_id][track_id] = ctx.author
                self.queues[guild_id].append(track)

            await ctx.approve(f"Added playlist **{tracks.name}**")

            if not player.is_playing:
                first_track = self.queues[guild_id].pop(0)
                await player.play(first_track)
                await self.set_vc_status(player, first_track)
        else:
            track = tracks[0]
            track_id = track.track_id if hasattr(track, 'track_id') else track.uri
            self.requesters[guild_id][track_id] = ctx.author

            if player.is_playing:
                self.queues[guild_id].append(track)
                await ctx.approve(f"Added **{track.title}** to queue")
            else:
                await player.play(track)
                await self.set_vc_status(player, track)
                await self.send_now_playing(ctx, track)

    @commands.hybrid_command()
    async def pause(self, ctx: Context):
        """Pause the current track"""
        if not await self.check_channel(ctx):
            return

        player = ctx.voice_client
        if player and player.is_playing:
            await player.set_pause(True)
            track = player.current
            if track:
                await ctx.approve(f"Paused **{get_track_title(track)}**")
            else:
                await ctx.approve("Paused")
        else:
            await ctx.deny("Nothing is playing")

    @commands.hybrid_command()
    async def resume(self, ctx: Context):
        """Resume the paused track"""
        if not await self.check_channel(ctx):
            return

        player = ctx.voice_client
        if player and player.is_paused:
            await player.set_pause(False)
            track = player.current
            if track:
                await ctx.approve(f"Resumed **{get_track_title(track)}**")
            else:
                await ctx.approve("Resumed")
        else:
            await ctx.deny("Nothing to resume")

    @commands.hybrid_command()
    async def skip(self, ctx: Context):
        """Skip the current track"""
        if not await self.check_channel(ctx):
            return

        player = ctx.voice_client
        if player and player.is_playing:
            await player.stop()
            await ctx.approve("Skipped")
        else:
            await ctx.deny("Nothing is playing")

    @commands.hybrid_command()
    async def stop(self, ctx: Context):
        """Stop playback and clear the queue"""
        if not await self.check_channel(ctx):
            return

        player = ctx.voice_client
        if player:
            track = player.current
            guild_id = ctx.guild.id
            self.queues[guild_id] = []
            await player.stop()
            await self.clear_vc_status(player)

            if track:
                await ctx.approve(f"**{get_track_title(track)}** has been stopped")
            else:
                await ctx.approve("Stopped")
        else:
            await ctx.deny("Nothing is playing")

    @commands.hybrid_command(aliases=["leave"])
    async def disconnect(self, ctx: Context):
        """Disconnect from the voice channel"""
        if not await self.check_channel(ctx):
            return

        player = ctx.voice_client
        if player:
            await self.clear_vc_status(player)
            await player.disconnect()
            await ctx.message.add_reaction("👍")
        else:
            await ctx.deny("Not connected")

    @commands.hybrid_command()
    async def volume(self, ctx: Context, vol: int = None):
        """Set the player volume (0-100)"""
        if not await self.check_channel(ctx):
            return

        player = ctx.voice_client

        if vol is None:
            return await ctx.approve(f"Volume: **{player.volume if player else 100}%**")

        if not player:
            return await ctx.deny("Not connected")

        await player.set_volume(max(0, min(vol, 100)))
        await ctx.approve(f"Volume set to **{vol}%**")

    @commands.hybrid_command()
    async def loop(self, ctx: Context, mode: str = None):
        """Set loop mode (off/song/queue)"""
        if not await self.check_channel(ctx):
            return

        if mode not in ["off", "song", "queue"]:
            return await ctx.deny("Use `off`, `song`, or `queue`")

        self.loop_mode[ctx.guild.id] = mode
        await ctx.approve(f"Loop: **{mode}**")

    @commands.hybrid_command(aliases=["q"])
    async def queue(self, ctx: Context):
        """View the current queue"""
        if not await self.check_channel(ctx):
            return

        player = ctx.voice_client

        if not player or not player.current:
            return await ctx.deny("Queue is empty")

        current = player.current
        guild_id = ctx.guild.id
        queue = self.queues.get(guild_id, [])
        queue_list = queue[:10]
        total_in_queue = len(queue)

        track_id = current.track_id if hasattr(current, 'track_id') else current.uri
        requester = self.requesters.get(ctx.guild.id, {}).get(track_id)

        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name="Queue", icon_url=self.bot.user.display_avatar.url)

        title = get_track_title(current)
        duration = format_duration(get_track_length(current))
        artwork = get_track_artwork(current)

        now_playing_value = f"• {title}\n• Duration: `{duration}`"
        if requester:
            now_playing_value += f" - ( {requester.mention} )"

        embed.add_field(name="Now Playing", value=now_playing_value, inline=False)

        if queue_list:
            upcoming = []
            for i, track in enumerate(queue_list, 1):
                t_title = get_track_title(track)
                t_duration = format_duration(get_track_length(track))
                upcoming.append(f"`{i}.` {t_title} • `{t_duration}`")

            embed.add_field(name=f"Up Next ({total_in_queue})", value="\n".join(upcoming), inline=False)

            if total_in_queue > 10:
                embed.set_footer(text=f"+{total_in_queue - 10} more songs in queue")
        else:
            embed.set_footer(text="No songs in queue")

        if artwork:
            embed.set_thumbnail(url=artwork)

        await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["np"])
    async def nowplaying(self, ctx: Context):
        """Show the currently playing track"""
        if not await self.check_channel(ctx):
            return

        player = ctx.voice_client

        if not player or not player.current:
            return await ctx.deny("Nothing is playing")

        track = player.current
        track_id = track.track_id if hasattr(track, 'track_id') else track.uri
        requester = self.requesters.get(ctx.guild.id, {}).get(track_id)

        title = get_track_title(track)
        duration = format_duration(get_track_length(track))
        artwork = get_track_artwork(track)

        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(
            name="Now Playing",
            icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/8/84/Spotify_icon.svg/1982px-Spotify_icon.svg.png"
        )

        desc = f"• {title}\n• Duration: `{duration}`"
        if requester:
            desc += f" - ( {requester.mention} )"
        embed.description = desc

        if artwork:
            embed.set_thumbnail(url=artwork)

        await ctx.send(embed=embed, view=NowPlayingControls(player))

    @commands.hybrid_command()
    async def shuffle(self, ctx: Context):
        """Shuffle the queue"""
        if not await self.check_channel(ctx):
            return

        player = ctx.voice_client
        guild_id = ctx.guild.id
        queue = self.queues.get(guild_id, [])

        if player and len(queue) >= 2:
            import random
            random.shuffle(queue)
            self.queues[guild_id] = queue
            await ctx.approve("Shuffled")
        else:
            await ctx.deny("Not enough songs")

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def musicchannel(self, ctx: Context, channel: discord.TextChannel = None):
        """Set the music commands channel"""
        if not channel:
            return await ctx.deny("Mention a channel")

        self.music_channels[ctx.guild.id] = channel.id
        await ctx.approve(f"Music channel set to {channel.mention}")

    @commands.hybrid_command(name="twentyfourseven", aliases=["247", "stay"])
    @commands.has_permissions(manage_guild=True)
    async def twentyfourseven_cmd(self, ctx: Context):
        """Toggle 24/7 mode (bot stays in VC even when alone)"""
        if not await self.check_channel(ctx):
            return

        guild_id = ctx.guild.id
        current = self.twentyfourseven.get(guild_id, False)

        if current:
            self.twentyfourseven[guild_id] = False
            await ctx.approve("**24/7 mode** disabled - I'll leave when alone")
        else:
            self.twentyfourseven[guild_id] = True
            await ctx.approve("**24/7 mode** enabled - I'll stay in VC 🌙")

    @commands.hybrid_command(name="clearfilters", aliases=["resetfilters"])
    async def clearfilters(self, ctx: Context):
        """Clear all audio filters"""
        if not await self.check_channel(ctx):
            return

        player = ctx.voice_client

        if not player:
            return await ctx.deny("Not connected")

        guild_id = ctx.guild.id
        self.active_filters[guild_id] = set()

        try:
            await player.reset_filters()
            await ctx.approve("All filters cleared")
        except Exception as e:
            await ctx.deny(f"Failed to clear filters: {e}")

    @commands.hybrid_command(name="filters")
    async def filters(self, ctx: Context):
        """Show currently active filters"""
        if not await self.check_channel(ctx):
            return

        guild_id = ctx.guild.id
        filters = self.active_filters.get(guild_id, set())

        if not filters:
            return await ctx.approve("No filters active")

        filter_list = ", ".join([f"**{f}**" for f in filters])
        await ctx.approve(f"Active filters: {filter_list}")


async def setup(bot):
    await bot.add_cog(Music(bot))
