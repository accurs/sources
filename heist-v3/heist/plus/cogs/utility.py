import discord
from discord import app_commands, Interaction, User, Embed
from discord.ext import commands
import requests
from heist.plus.utils import permissions
from heist.plus.utils.error import error_handler
from heist.plus.utils.cache import get_embed_color
from datetime import datetime
import os, asyncio, time, psutil
from shazamio import Shazam
import aiofiles
import aiohttp
import ujson as json
from io import BytesIO

class Utility(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.session = aiohttp.ClientSession()
        self.ctx_raw = app_commands.ContextMenu(
            name='Get Raw',
            callback=self.getraw,
        )
        self.client.tree.add_command(self.ctx_raw)
        # self.ctx_shazam = app_commands.ContextMenu(
        #     name='Shazam This',
        #     callback=self.shazam_context,
        # )
        # self.client.tree.add_command(self.ctx_shazam)
        
    # @app_commands.allowed_installs(guilds=True, users=True)
    # @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    # @app_commands.check(permissions.is_blacklisted)
    # async def shazam_context(self, interaction: discord.Interaction, message: discord.Message) -> None:
    #     try:
    #         if not message.attachments:
    #             await interaction.response.send_message("No attachment found in this message.", ephemeral=True)
    #             return

    #         attachment = message.attachments[0]
    #         SUPPORTED_EXTENSIONS = ['mp3', 'wav', 'ogg', 'm4a', 'flac', 'mp4', 'mov', 'avi', 'mkv', 'opus']
    #         file_extension = attachment.filename.split('.')[-1].lower()

    #         if file_extension not in SUPPORTED_EXTENSIONS:
    #             await interaction.response.send_message("Unsupported file format for Shazam.", ephemeral=True)
    #             return

    #         await interaction.response.defer(thinking=True)

    #         async def convert_audio(data, ext):
    #             if ext in ['mp4', 'mov', 'avi', 'mkv']:
    #                 process = await asyncio.create_subprocess_exec(
    #                     'ffmpeg', '-i', 'pipe:0', '-f', 'mp3', '-vn', '-ac', '2', '-ar', '44100', '-b:a', '192k', 'pipe:1',
    #                     stdin=asyncio.subprocess.PIPE,
    #                     stdout=asyncio.subprocess.PIPE,
    #                     stderr=asyncio.subprocess.PIPE
    #                 )
    #                 stdout, stderr = await process.communicate(input=data)
    #                 if process.returncode != 0:
    #                     raise Exception(f"FFmpeg error: {stderr.decode()}")
    #                 return stdout, 'mp3'
    #             elif ext in ['opus', 'ogg']:
    #                 process = await asyncio.create_subprocess_exec(
    #                     'ffmpeg', '-i', 'pipe:0', '-f', 'wav', '-ac', '2', '-ar', '44100', 'pipe:1',
    #                     stdin=asyncio.subprocess.PIPE,
    #                     stdout=asyncio.subprocess.PIPE,
    #                     stderr=asyncio.subprocess.PIPE
    #                 )
    #                 stdout, stderr = await process.communicate(input=data)
    #                 if process.returncode != 0:
    #                     raise Exception(f"FFmpeg error: {stderr.decode()}")
    #                 return stdout, 'wav'
    #             return data, ext

    #         async with self.session.get(attachment.url) as response:
    #             audio_data = await response.read()

    #         converted_data, new_ext = await convert_audio(audio_data, file_extension)

    #         async with aiofiles.tempfile.NamedTemporaryFile(prefix='shazam_', suffix=f'.{new_ext}', delete=True) as temp_file:
    #             await temp_file.write(converted_data)
    #             await temp_file.flush()
                
    #             shazam = Shazam()
    #             result = await shazam.recognize(temp_file.name)

    #             if not result or 'track' not in result:
    #                 await interaction.followup.send("Could not recognize this song.", ephemeral=True)
    #                 return

    #             track = result['track']
    #             title = track.get('title', 'Unknown Title')
    #             artist = track.get('subtitle', 'Unknown Artist')

    #             apple_music_url = None
    #             spotify_url = None
    #             apple_music_image = None
    #             spotify_image = None

    #             if 'hub' in track and track['hub'].get('type') == 'APPLEMUSIC':
    #                 for action in track['hub'].get('actions', []):
    #                     if action.get('type') == 'applemusicplay':
    #                         apple_music_url = action.get('uri')
    #                     if action.get('type') == 'uri' and 'image' in action:
    #                         apple_music_image = action.get('image')

    #             if 'providers' in track:
    #                 for provider in track['providers']:
    #                     if provider.get('type') == 'SPOTIFY':
    #                         for action in provider.get('actions', []):
    #                             if action.get('type') == 'uri':
    #                                 spotify_url = action.get('uri')
    #                         if 'images' in provider:
    #                             spotify_image = provider['images'].get('default')

    #             shazam_image = track.get('images', {}).get('coverart', 'https://i.imgur.com/3sgezz7.png')
    #             thumbnail_url = apple_music_image or spotify_image or shazam_image

    #             description_parts = [f"Song: **{title}**\nArtist(s): **{artist}**"]
    #             if apple_music_url:
    #                 description_parts.append(f"[Listen on Apple Music]({apple_music_url})")
    #             if spotify_url:
    #                 description_parts.append(f"[Listen on Spotify]({spotify_url})")

    #             description = '\n'.join(description_parts)
    #             embed_color = await get_embed_color(str(interaction.user.id))
    #             embed = discord.Embed(
    #                 title="<:check:1397233931513757697> Song recognised",
    #                 description=description or "No additional links available.",
    #                 color=embed_color
    #             )

    #             if thumbnail_url:
    #                 embed.set_thumbnail(url=thumbnail_url)
                
    #             embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)
    #             embed.set_footer(text="shazam.com", icon_url="https://git.cursi.ng/shazam_logo.png")
                
    #             await interaction.followup.send(embed=embed)

    #     except Exception as e:
    #         await interaction.followup.send(f"Error recognizing song: {str(e)[:1500]}", ephemeral=True)

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.check(permissions.is_blacklisted)
    async def getraw(self, interaction: discord.Interaction, message: discord.Message):
        try:
            author = message.author
            member = message.guild.get_member(author.id) if message.guild else None

            raw_data = {
                "id": str(message.id),
                "channel_id": str(message.channel.id),
                "content": message.content,
                "attachments": [
                    {
                        "id": str(a.id),
                        "filename": a.filename,
                        "size": a.size,
                        "url": a.url,
                        "proxy_url": a.proxy_url,
                        "width": a.width,
                        "height": a.height,
                        "content_type": a.content_type,
                        "spoiler": a.is_spoiler()
                    } for a in message.attachments
                ],
                "embeds": [e.to_dict() for e in message.embeds],
                "components": [c.to_dict() for c in message.components],
                "stickerItems": [s.to_dict() for s in message.stickers],
                "author": {
                    "id": str(author.id),
                    "username": author.name,
                    "discriminator": author.discriminator,
                    "globalName": author.global_name,
                    "avatar": author.avatar.key if author.avatar else None,
                    "bot": author.bot,
                    "system": author.system,
                    "publicFlags": author.public_flags.value,
                    "guildAvatar": member.avatar.key if member and member.avatar else None,
                    "nick": member.nick if member else None,
                    "joinedAt": member.joined_at.isoformat() if member and member.joined_at else None,
                    "pending": member.pending if member else None,
                    "communicationDisabledUntil": getattr(member, "communication_disabled_until", None).isoformat() if member and getattr(member, "communication_disabled_until", None) else None
                },
                "timestamp": message.created_at.isoformat(),
                "editedTimestamp": message.edited_at.isoformat() if message.edited_at else None,
                "pinned": message.pinned,
                "type": message.type.value,
                "mentionEveryone": message.mention_everyone,
                "mentions": [m.id for m in message.mentions],
                "mentionRoles": [str(r.id) for r in message.role_mentions],
                "flags": message.flags.value,
                "tts": message.tts,
                "reference": message.reference.to_message_reference_dict() if message.reference else None,
                "activity": None,
                "application": None,
                "webhookId": None
            }

            data = await asyncio.to_thread(json.dumps, raw_data, indent=4)
            file = discord.File(BytesIO(data.encode()), filename="rawdata.json")
            await interaction.response.send_message(file=file, ephemeral=True)
        except Exception as gyat:
            print('got the following error in get_raw:', gyat)

async def setup(client):
    await client.add_cog(Utility(client))