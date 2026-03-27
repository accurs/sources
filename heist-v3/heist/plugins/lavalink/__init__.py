import discord
from discord.ext import commands
import wavelink
from collections import deque
import random
import asyncio
import os
from dotenv import load_dotenv
import io
from heist.framework.tools.separator import makeseparator

load_dotenv()

LAVALINK_HOST = os.getenv("LAVALINK_HOST")
LAVALINK_PORT = int(os.getenv("LAVALINK_PORT"))
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD")
LAVALINK_SSL = os.getenv("LAVALINK_SSL", "false").lower() == "true"

class DJRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Select a DJ role...", max_values=1, min_values=0)
    
    async def callback(self, interaction: discord.Interaction):
        if not self.values:
            await interaction.client.pool.execute("DELETE FROM dj_roles WHERE guild_id = $1", interaction.guild.id)
            await interaction.response.edit_message(content="DJ role removed.", view=None, embed=None)
            await asyncio.sleep(3)
            await interaction.delete_original_response()
            return
        
        role = self.values[0]
        await interaction.client.pool.execute(
            "INSERT INTO dj_roles (guild_id, role_id) VALUES ($1, $2) ON CONFLICT (guild_id) DO UPDATE SET role_id = $2",
            interaction.guild.id, role.id
        )
        
        embed = discord.Embed(
            description=f"DJ role set to {role.mention}",
            color=interaction.client.config.colors.information
        )
        await interaction.response.edit_message(content=None, embed=embed, view=None)
        await asyncio.sleep(3)
        await interaction.delete_original_response()

class DJRoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(DJRoleSelect())
    
    async def on_timeout(self):
        if self.message:
            try:
                await self.message.delete()
            except:
                pass

class MusicPlayerView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    async def check_dj_role(self, interaction: discord.Interaction):
        if interaction.user.guild_permissions.manage_guild:
            return True
            
        result = await self.cog.bot.pool.fetchrow("SELECT role_id FROM dj_roles WHERE guild_id = $1", interaction.guild.id)
        if not result:
            return True
            
        dj_role = interaction.guild.get_role(result['role_id'])
        if not dj_role:
            return True
            
        return dj_role in interaction.user.roles

    @discord.ui.button(emoji=discord.PartialEmoji(name="playerleft", id=1434732248984195093), style=discord.ButtonStyle.gray)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_dj_role(interaction):
            return await interaction.response.warn("You need the DJ role to use this button.", ephemeral=True)
            
        vc: wavelink.Player = interaction.guild.voice_client
        if not vc or not vc.playing:
            return await interaction.response.warn("Nothing is playing right now.", ephemeral=True)
        
        queue = self.cog.get_queue(self.guild_id)
        if len(queue) < 1:
            return await interaction.response.warn("No previous track available.", ephemeral=True)
        
        await vc.stop()
        await interaction.response.approve("Playing previous track.", ephemeral=True)

    @discord.ui.button(emoji=discord.PartialEmoji(name="playerpause", id=1434732250641207386), style=discord.ButtonStyle.gray)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_dj_role(interaction):
            return await interaction.response.warn("You need the DJ role to use this button.", ephemeral=True)
            
        vc: wavelink.Player = interaction.guild.voice_client
        if not vc or not vc.playing:
            return await interaction.response.warn("Nothing is playing right now.", ephemeral=True)
        
        if vc.paused:
            await vc.pause(False)
            await interaction.response.approve("Resumed the player.", ephemeral=True)
        else:
            await vc.pause(True)
            await interaction.response.approve("Paused the player.", ephemeral=True)

    @discord.ui.button(emoji=discord.PartialEmoji(name="playerright", id=1434732252331507862), style=discord.ButtonStyle.gray)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_dj_role(interaction):
            return await interaction.response.warn("You need the DJ role to use this button.", ephemeral=True)
            
        vc: wavelink.Player = interaction.guild.voice_client
        if not vc or not vc.playing:
            return await interaction.response.warn("Nothing is playing right now.", ephemeral=True)
        
        await vc.stop()
        queue = self.cog.get_queue(self.guild_id)
        if len(queue) == 0:
            await interaction.response.approve("Skipped track. Queue is empty.", ephemeral=True)
        else:
            await interaction.response.approve("Skipped to next track.", ephemeral=True)

class Lavalink(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = {}
        self.text_channels = {}
        self.loop_status = {}
        self.inactivity_tasks = {}
        self.now_playing_messages = {}
        self.bot.loop.create_task(self.connect_nodes())

    def get_queue(self, guild_id):
        if guild_id not in self.queue:
            self.queue[guild_id] = deque()
        return self.queue[guild_id]

    async def update_voice_status(self, player: wavelink.Player, track: wavelink.Playable):
        try:
            if player.channel:
                status_text = f"Playing: {track.title[:28]}..." if len(track.title) > 28 else track.title
                await player.channel.edit(status=status_text)
        except Exception as e:
            print(f"[VOICE STATUS] Failed to update status: {e}")

    async def clear_voice_status(self, player: wavelink.Player):
        try:
            if player.channel:
                await player.channel.edit(status=None)
        except Exception as e:
            print(f"[VOICE STATUS] Failed to clear status: {e}")

    def cancel_inactivity_task(self, guild_id):
        if guild_id in self.inactivity_tasks:
            self.inactivity_tasks[guild_id].cancel()
            del self.inactivity_tasks[guild_id]

    async def cleanup_player(self, guild_id):
        if guild_id in self.now_playing_messages:
            try:
                await self.now_playing_messages[guild_id].delete()
            except:
                pass
            del self.now_playing_messages[guild_id]
        
        self.cancel_inactivity_task(guild_id)
        
        if guild_id in self.queue:
            self.queue[guild_id].clear()
        
        if guild_id in self.loop_status:
            self.loop_status[guild_id] = False

    async def start_inactivity_timer(self, guild_id):
        self.cancel_inactivity_task(guild_id)
        
        async def inactivity_check():
            try:
                await asyncio.sleep(180)
                guild = self.bot.get_guild(guild_id)
                if guild and guild.voice_client:
                    vc: wavelink.Player = guild.voice_client
                    await self.clear_voice_status(vc)
                    await vc.disconnect()
                    
                    if guild_id in self.text_channels:
                        channel = self.text_channels[guild_id]
                        try:
                            await channel.warn("Left due to 3 minutes of inactivity.")
                        except:
                            pass
                    
                    await self.cleanup_player(guild_id)
            except asyncio.CancelledError:
                pass
        
        self.inactivity_tasks[guild_id] = self.bot.loop.create_task(inactivity_check())

    async def send_now_playing(self, channel, track, requester=None):
        guild_id = channel.guild.id
        if guild_id in self.now_playing_messages:
            try:
                old_msg = self.now_playing_messages[guild_id]
                await old_msg.delete()
            except:
                pass
        
        mins = track.length // 60000
        secs = (track.length // 1000) % 60
        duration = f"{mins}:{secs:02d}"
        
        author_name = "Now Playing"
        author_icon = None
        
        if "youtube.com" in track.uri or "youtu.be" in track.uri:
            author_icon = "https://git.cursi.ng/youtube_logo.png"
        elif "spotify.com" in track.uri:
            author_icon = "https://git.cursi.ng/spotify_logo_white_small.png"
        
        embed = discord.Embed(color=0xd3d6f1)
        embed.set_author(name=author_name, icon_url=author_icon)
        
        description = f"- [`{track.title} - {track.author}`]({track.uri})\n"
        description += f"- Duration: `{duration}`"
        if requester:
            description += f" - ({requester.mention})"
        
        embed.description = description
        
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)
        
        view = MusicPlayerView(self, guild_id)
        message = await channel.send(embed=embed, view=view)
        self.now_playing_messages[guild_id] = message

    async def _play_next(self, player: wavelink.Player):
        if player is None or not hasattr(player, 'guild') or player.guild is None:
            return

        guild_id = player.guild.id
        queue = self.get_queue(guild_id)

        if not player or player.guild is None:
            return

        if queue:
            try:
                track = queue.popleft()
                await player.play(track)
                await self.update_voice_status(player, track)
                self.cancel_inactivity_task(guild_id)
            except Exception as e:
                print(f"Error playing next track: {e}")
                if queue:
                    await self._play_next(player)

        elif player.current:
            if guild_id in self.text_channels:
                channel = self.text_channels[guild_id]
                try:
                    await self.send_now_playing(channel, player.current)
                except Exception as e:
                    print(f"Failed to send now playing for current: {e}")

        else:
            await self.cleanup_player(guild_id)
            await self.start_inactivity_timer(guild_id)
            
    async def connect_nodes(self):
        await self.bot.wait_until_ready()

        scheme = "https" if LAVALINK_SSL else "http"
        uri = f"{scheme}://{LAVALINK_HOST}:{LAVALINK_PORT}"

        try:
            node = wavelink.Node(
                uri=uri,
                password=LAVALINK_PASSWORD
            )

            await wavelink.Pool.connect(
                nodes=[node],
                client=self.bot,
                cache_capacity=100
            )

            print(f"[WAVELINK] ✅ Connected to Lavalink → {uri}")

        except Exception as e:
            print(f"[WAVELINK] ❌ Failed to connect: {e}")

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        print(f"[WAVELINK] Node {payload.node.identifier} is ready!")
            
    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player = payload.player
        guild_id = player.guild.id
        track = payload.track

        if getattr(player, "_loop_restart", False):
            player._loop_restart = False
            return

        self.cancel_inactivity_task(guild_id)

        if guild_id in self.text_channels:
            channel = self.text_channels[guild_id]
            try:
                await self.send_now_playing(channel, track)
            except Exception as e:
                print(f"Failed to send now playing on start: {e}")

        await self.update_voice_status(player, track)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        try:
            player = payload.player

            if player is None or not hasattr(player, 'guild') or player.guild is None:
                return

            guild_id = player.guild.id

            if self.loop_status.get(guild_id, False):
                current = payload.track
                if current and player and player.guild:
                    try:
                        await asyncio.sleep(0.1)
                        player._loop_restart = True
                        await player.play(current)
                        await self.update_voice_status(player, current)
                        self.cancel_inactivity_task(guild_id)
                    except Exception as e:
                        print(f"Error replaying track: {e}")
                return

            await self._play_next(player)
        except Exception as e:
            print(f"Error in track_end: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.id == self.bot.user.id and before.channel and not after.channel:
            guild_id = before.channel.guild.id
            await self.cleanup_player(guild_id)

    async def check_dj_role(self, ctx):
        if ctx.author.guild_permissions.manage_guild:
            return True
            
        result = await self.bot.pool.fetchrow("SELECT role_id FROM dj_roles WHERE guild_id = $1", ctx.guild.id)
        if not result:
            return True
            
        dj_role = ctx.guild.get_role(result['role_id'])
        if not dj_role:
            return True
            
        return dj_role in ctx.author.roles

    @commands.command(name='djrole', aliases=['dj'])
    @commands.has_permissions(manage_guild=True)
    async def djrole(self, ctx):
        embed = discord.Embed(
            title="DJ Role Setup",
            description="Please provide the DJ role (mention, ID, or name). Type `none` to remove the DJ role.\n\n**Tip:** Select nothing to remove the DJ role.",
            color=ctx.config.colors.information
        )
        
        view = DJRoleView()
        message = await ctx.send(embed=embed, view=view)
        view.message = message

    @commands.command(name='nowplaying', aliases=['np'])
    async def nowplaying(self, ctx):
        vc: wavelink.Player = ctx.voice_client
        if not vc or not vc.current:
            return await ctx.deny("Nothing is playing right now.")
        
        await self.send_now_playing(ctx.channel, vc.current)

    @commands.command()
    async def join(self, ctx):
        if not ctx.author.voice:
            return await ctx.deny("You are not in a voice channel.")

        channel = ctx.author.voice.channel
        try:
            player: wavelink.Player = await channel.connect(cls=wavelink.Player, self_deaf=True)
        except:
            player: wavelink.Player = ctx.voice_client
            await player.move_to(channel)

        self.cancel_inactivity_task(ctx.guild.id)
        return await ctx.approve(f"Joined **{channel.name}**")
    
    @commands.command(name='play', aliases=["p"])
    async def play(self, ctx, *, query: str):
        if not await self.check_dj_role(ctx):
            return await ctx.deny("You need the DJ role to use this command.")
            
        try:
            await ctx.message.delete()
        except:
            pass
            
        self.text_channels[ctx.guild.id] = ctx.channel
        
        if not ctx.voice_client:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect(cls=wavelink.Player, self_deaf=True)
            else:
                return await ctx.deny("You need to be in a voice channel!")
        
        vc: wavelink.Player = ctx.voice_client
        self.cancel_inactivity_task(ctx.guild.id)
        
        async with ctx.typing():
            try:
                tracks = await wavelink.Playable.search(query)
                
                if not tracks:
                    return await ctx.deny("No results found.")
                
                guild_id = ctx.guild.id
                queue = self.get_queue(guild_id)
                
                if isinstance(tracks, wavelink.Playlist):
                    playlist = tracks
                    
                    if vc.playing:
                        queue.extend(playlist.tracks)
                        position = len(queue) - len(playlist.tracks) + 1
                        msg = await ctx.approve(f"Added [`{playlist.name}`]({playlist.url}) to `{position}` in queue.")
                        await asyncio.sleep(5)
                        await msg.delete()
                    else:
                        await vc.play(playlist.tracks[0])
                        await self.update_voice_status(vc, playlist.tracks[0])
                        if len(playlist.tracks) > 1:
                            queue.extend(playlist.tracks[1:])
                else:
                    if isinstance(tracks, list):
                        track = tracks[0]
                    else:
                        track = tracks
                    
                    if vc.playing:
                        queue.append(track)
                        position = len(queue)
                        msg = await ctx.approve(f"Added [`{track.title}`]({track.uri}) to `{position}` in queue.")
                        await asyncio.sleep(5)
                        await msg.delete()
                    else:
                        await vc.play(track)
                        await self.update_voice_status(vc, track)
                    
            except Exception as e:
                await ctx.deny(f"An error occurred: {str(e)}")

    @commands.command(name='pause')
    async def pause(self, ctx):
        if not await self.check_dj_role(ctx):
            return await ctx.deny("You need the DJ role to use this command.")
            
        vc: wavelink.Player = ctx.voice_client
        
        if vc and vc.playing:
            await vc.pause(True)
            await self.start_inactivity_timer(ctx.guild.id)
            await ctx.approve("Paused the player.")
        else:
            await ctx.warn("Nothing is playing right now.")

    @commands.command(name='resume')
    async def resume(self, ctx):
        if not await self.check_dj_role(ctx):
            return await ctx.deny("You need the DJ role to use this command.")
            
        vc: wavelink.Player = ctx.voice_client
        
        if vc and vc.paused:
            await vc.pause(False)
            self.cancel_inactivity_task(ctx.guild.id)
            await ctx.approve("Resumed the player.")
        else:
            await ctx.warn("Nothing is paused right now.")

    @commands.command(name='skip')
    async def skip(self, ctx):
        if not await self.check_dj_role(ctx):
            return await ctx.deny("You need the DJ role to use this command.")
            
        vc: wavelink.Player = ctx.voice_client
        if not vc or not vc.playing:
            return await ctx.warn("Nothing is playing right now.")
        
        self.cancel_inactivity_task(ctx.guild.id)
        
        queue = self.get_queue(ctx.guild.id)
        
        await vc.stop()

        if len(queue) == 0 and not vc.current:
            return await ctx.approve("Skipped track. Queue is empty.")
        
        await ctx.approve("Skipped to next track.")

    @commands.command(name='stop')
    async def stop(self, ctx):
        if not await self.check_dj_role(ctx):
            return await ctx.deny("You need the DJ role to use this command.")
            
        vc: wavelink.Player = ctx.voice_client
        guild_id = ctx.guild.id
        
        await self.cleanup_player(guild_id)
        
        if vc:
            await vc.stop()
            await self.clear_voice_status(vc)
            await self.start_inactivity_timer(guild_id)
            await ctx.approve("Stopped and cleared queue")
        else:
            await ctx.deny("Not connected to a voice channel.")

    @commands.command(name='queue')
    async def show_queue(self, ctx):
        vc = ctx.voice_client
        queue = self.get_queue(ctx.guild.id)
        
        description = ">>> Now Playing:\n"
        
        if vc and vc.current:
            current = vc.current
            current_mins = vc.position // 60000
            current_secs = (vc.position // 1000) % 60
            total_mins = current.length // 60000
            total_secs = (current.length // 1000) % 60
            
            description += f"[`{current.title}`]({current.uri}) - [`{current_mins}:{current_secs:02d}/{total_mins}:{total_secs:02d}`]({current.uri})\n"
        else:
            description += "*Nothing playing*\n"
        
        if queue:
            description += "Up Next:\n"
            for i, track in enumerate(queue, 1):
                mins = track.length // 60000
                secs = (track.length // 1000) % 60
                description += f"`{i}.` [`{track.title}`]({track.uri}) - [`{mins}:{secs:02d}`]({track.uri})\n"
        else:
            description += "Up Next:\n*Queue is empty*"
        
        embed = discord.Embed(
            title="<:spotify:1274904265114124308> Music Queue",
            description=description,
            color=0xd3d6f1
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        sepbyte = await makeseparator(self.bot, ctx.author.id)
        sep = discord.File(io.BytesIO(sepbyte), filename="separator.png")

        embed.set_image(url="attachment://separator.png")
        
        await ctx.send(embed=embed, file=sep)

    @commands.command(name='leave')
    async def leave(self, ctx):
        if not await self.check_dj_role(ctx):
            return await ctx.deny("You need the DJ role to use this command.")
            
        vc: wavelink.Player = ctx.voice_client
        
        if vc:
            guild_id = ctx.guild.id
            await self.cleanup_player(guild_id)
            await self.clear_voice_status(vc)
            await vc.disconnect()
            await ctx.approve("Disconnected")
        else:
            await ctx.deny("I'm not in a voice channel.")

    @commands.command(name='volume')
    async def volume(self, ctx, volume: int):
        if not await self.check_dj_role(ctx):
            return await ctx.deny("You need the DJ role to use this command.")
            
        vc: wavelink.Player = ctx.voice_client
        
        if not vc:
            return await ctx.deny("Not connected to a voice channel.")
        
        if 0 <= volume <= 100:
            await vc.set_volume(volume)
            await ctx.approve(f"Volume set to **{volume}%**")
        else:
            await ctx.deny("Volume must be between 0 and 100.")

    @commands.command(name='loop')
    async def loop(self, ctx, mode: str = None):
        if not await self.check_dj_role(ctx):
            return await ctx.deny("You need the DJ role to use this command.")
            
        guild_id = ctx.guild.id

        if not ctx.voice_client or not ctx.voice_client.playing:
            return await ctx.deny("Nothing is currently playing.")

        if mode is None:
            current_state = self.loop_status.get(guild_id, False)
            status = "enabled" if current_state else "disabled"
            embed = discord.Embed(
                description=f"🔁 Loop is currently **{status}**.\nUse `loop on` or `loop off` to change it.",
                color=0xd3d6f1
            )
            await ctx.send(embed=embed)
            return

        if mode.lower() == "on":
            self.loop_status[guild_id] = True
            await ctx.approve("Looping **enabled** — the current song will repeat!")

        elif mode.lower() == "off":
            self.loop_status[guild_id] = False
            await ctx.approve("Looping **disabled.**")

        else:
            await ctx.deny("Invalid option. Use `on` or `off`.")

    @commands.command(name='shuffle')
    async def shuffle(self, ctx):
        if not await self.check_dj_role(ctx):
            return await ctx.deny("You need the DJ role to use this command.")
            
        vc = ctx.voice_client
        
        if not vc:
            return await ctx.deny("I'm not connected to a voice channel!")
        
        queue = self.get_queue(ctx.guild.id)
        
        if len(queue) < 2:
            return await ctx.deny("Not enough tracks in queue to shuffle!")
        
        random.shuffle(queue)
        
        embed = discord.Embed(
            title="🔀 Queue Shuffled",
            description=f"Shuffled **{len(queue)}** tracks",
            color=0xd3d6f1
        )
        await ctx.send(embed=embed)
    
    @commands.command(name='bassboost')
    async def bassboost(self, ctx, level: int = None):
        if not await self.check_dj_role(ctx):
            return await ctx.deny("You need the DJ role to use this command.")
            
        vc = ctx.voice_client
        
        if not vc:
            return await ctx.deny("I'm not connected to a voice channel!")
        
        if not vc.playing:
            return await ctx.deny("Nothing is currently playing!")
        
        if level is None:
            filters = vc.filters
            filters.equalizer.reset()
            await vc.set_filters(filters)
            
            embed = discord.Embed(
                title="🔊 Bass Boost Disabled",
                description="Bass boost has been turned off",
                color=0xd3d6f1
            )
            return await ctx.send(embed=embed)
        
        if level < 1 or level > 5:
            return await ctx.deny("Bass boost level must be between 1-5!")
        
        filters = vc.filters
        
        boost_values = {
            1: 0.15,
            2: 0.25,
            3: 0.35,
            4: 0.45,
            5: 0.60
        }
        
        boost = boost_values[level]
        
        filters.equalizer.set(band=0, gain=boost)
        filters.equalizer.set(band=1, gain=boost)
        filters.equalizer.set(band=2, gain=boost * 0.75)
        filters.equalizer.set(band=3, gain=boost * 0.5)
        
        await vc.set_filters(filters)
        
        embed = discord.Embed(
            title="🔊 Bass Boost Enabled",
            description=f"Bass boost set to level **{level}**/5",
            color=0xd3d6f1
        )
        await ctx.send(embed=embed)

    @commands.group(name="filters", invoke_without_command=True)
    async def filters(self, ctx):
        embed = discord.Embed(
            title="🎛️ Available Filters",
            description=(
                "**Usage:** `,filters <filter>`\n\n"
                "🔹 `nightcore` — Speeds up and raises pitch (1.2x)\n"
                "🔹 `karaoke` — Removes vocals for karaoke-style playback"
            ),
            color=0xd3d6f1
        )
        await ctx.send(embed=embed)

    @filters.command(name="nightcore")
    async def nightcore(self, ctx):
        if not await self.check_dj_role(ctx):
            return await ctx.deny("You need the DJ role to use this command.")
            
        vc: wavelink.Player = ctx.voice_client

        if not vc or not vc.playing:
            return await ctx.deny("Nothing is currently playing!")

        try:
            filters = wavelink.Filters()
            filters.timescale.set(pitch=1.1, rate=1.1, speed=1.1)
            await vc.set_filters(filters)
            await ctx.approve("Nightcore filter enabled.")
        except Exception as e:
            await ctx.deny(f"Failed to apply filter:\n```{e}```")

    @filters.command(name="karaoke")
    async def karaoke(self, ctx):
        if not await self.check_dj_role(ctx):
            return await ctx.deny("You need the DJ role to use this command.")
            
        vc: wavelink.Player = ctx.voice_client

        if not vc or not vc.playing:
            return await ctx.deny("Nothing is currently playing!")

        try:
            filters = wavelink.Filters()
            filters.karaoke.set(level=1.0, mono_level=1.0, filter_band=220.0, filter_width=100.0)
            await vc.set_filters(filters)
            await ctx.approve("**Karaoke filter enabled!** 🎤 Vocals removed.")
        except Exception as e:
            await ctx.deny(f"Failed to apply filter:\n```{e}```")

    @filters.command(name="reset")
    async def reset_filter(self, ctx):
        if not await self.check_dj_role(ctx):
            return await ctx.deny("You need the DJ role to use this command.")
            
        vc: wavelink.Player = ctx.voice_client

        if not vc:
            return await ctx.deny("Not connected to a voice channel.")

        try:
            filters = wavelink.Filters()
            await vc.set_filters(filters)
            await ctx.approve("All filters reset.")
        except Exception as e:
            await ctx.deny(f"Failed to reset filters:\n```{e}```")

async def setup(bot):
    await bot.add_cog(Lavalink(bot))