import os
import base64
import aiohttp
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import (
    Channel, Chat, User, 
    UserStatusOnline, UserStatusOffline, 
    UserStatusEmpty, UserStatusRecently,
    UserStatusLastWeek, UserStatusLastMonth
)
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from typing import Dict, Any, List, Optional

class AsyncTelegramExtractor:
    def __init__(self, max_concurrent_requests: int = 10):
        self.max_concurrent_requests = max_concurrent_requests
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
        self.api_id = int(os.getenv('TELEGRAM_API_ID', '27723828'))
        self.api_hash = os.getenv('TELEGRAM_API_HASH', '7b93aac968da7d7f67541de840745ad2')
        self.session_string = os.getenv('TELEGRAM_SESSION', '')
        self.phone = os.getenv('TELEGRAM_PHONE', '+14694071190')
        self.client = None
        self._initialized = False

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            await self.shutdown()
        except GeneratorExit:
            pass
        except Exception as e:
            print(f"[AsyncTelegramExtractor] Cleanup failed: {e}")

    async def initialize(self):
        if self._initialized:
            return

        if not self.session_string:
            raise ValueError("Telegram session string not configured")
            
        self.client = TelegramClient(StringSession(self.session_string), self.api_id, self.api_hash)
        await self.client.connect()
        
        if not await self.client.is_user_authorized():
            if not self.phone:
                raise ValueError("Phone number required for authorization")
                
            await self.client.send_code_request(self.phone)
            code = input('Enter the Telegram code: ')
            await self.client.sign_in(self.phone, code)
            
            self.session_string = self.client.session.save()
            os.environ['TELEGRAM_SESSION'] = self.session_string

        self._initialized = True

    async def shutdown(self):
        if self.client:
            await self.client.disconnect()
            self.client = None
        self._initialized = False

    async def extract_user(self, username: str) -> Dict[str, Any]:
        async with self.semaphore:
            try:
                if not self.client or not self._initialized:
                    await self.initialize()
                
                entity = await self.client.get_entity(username)
                
                if isinstance(entity, (Channel, Chat)):
                    return await self._extract_channel_info(entity)
                else:
                    return await self._extract_user_info(entity)
                    
            except Exception as e:
                return {"error": f"Failed to extract user: {str(e)}"}

    async def _extract_channel_info(self, entity) -> Dict[str, Any]:
        full_chat = await self.client(GetFullChannelRequest(entity))
        photos = await self.client.get_profile_photos(entity)
        
        return {
            'type': 'channel',
            'id': entity.id,
            'title': entity.title,
            'username': entity.username,
            'description': getattr(full_chat.full_chat, 'about', None),
            'members': getattr(full_chat.full_chat, 'participants_count', 0),
            'profile_photos': await self._process_photos(photos)
        }

    async def _extract_user_info(self, entity) -> Dict[str, Any]:
        full_user = await self.client(GetFullUserRequest(entity))
        photos = await self.client.get_profile_photos(entity)
        
        is_premium = getattr(full_user.users[0], 'premium', False)
        bio = getattr(full_user.full_user, 'about', None)
        
        last_seen = await self._get_last_seen_status(entity)
        
        profile_photos = await self._process_photos(photos)
        
        if not profile_photos:
            profile_photos = [await self._get_default_avatar()]
        
        return {
            'type': 'user',
            'id': entity.id,
            'first_name': getattr(entity, 'first_name', None),
            'last_name': getattr(entity, 'last_name', None),
            'is_premium': is_premium,
            'bio': bio,
            'username': entity.username,
            'last_seen': last_seen,
            'profile_photos': profile_photos
        }

    async def _get_last_seen_status(self, entity) -> Optional[str]:
        if not hasattr(entity, 'status'):
            return None
            
        if isinstance(entity.status, UserStatusOnline):
            return "now"
        elif isinstance(entity.status, UserStatusOffline):
            return int(entity.status.was_online.timestamp())
        elif isinstance(entity.status, UserStatusEmpty):
            return "never"
        elif isinstance(entity.status, UserStatusRecently):
            return "recently"
        elif isinstance(entity.status, UserStatusLastWeek):
            return "last week"
        elif isinstance(entity.status, UserStatusLastMonth):
            return "last month"
        return None

    async def _process_photos(self, photos) -> List[Dict[str, Any]]:
        processed_photos = []
        for photo in photos:
            processed_photo = await self._get_telegram_media(photo)
            if processed_photo:
                processed_photos.append(processed_photo)
        return processed_photos

    async def _get_telegram_media(self, photo) -> Optional[Dict[str, Any]]:
        try:
            file = await self.client.download_media(photo, file=bytes)
            if not file:
                return None
                
            is_video = hasattr(photo, 'video') and photo.video is not None
            return {
                'type': 'video' if is_video else 'image',
                'data': base64.b64encode(file).decode('utf-8'),
                'extension': '.mp4' if is_video else '.png',
                'size': len(file)
            }
        except Exception:
            return None

    async def _get_default_avatar(self) -> Dict[str, Any]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://git.cursi.ng/telegram_logo.png") as response:
                    if response.status == 200:
                        logo_bytes = await response.read()
                        return {
                            'type': 'image',
                            'data': base64.b64encode(logo_bytes).decode('utf-8'),
                            'extension': '.png',
                            'size': len(logo_bytes),
                            'is_default': True
                        }
        except Exception:
            pass
            
        return {
            'type': 'image',
            'data': '',
            'extension': '.png',
            'size': 0,
            'is_default': True
        }

    async def extract_multiple_users(self, usernames: List[str]) -> List[Dict[str, Any]]:
        tasks = [self.extract_user(username) for username in usernames]
        return await asyncio.gather(*tasks, return_exceptions=True)