from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from aiohttp import ClientSession
from discord.ext.commands import CommandError
from yarl import URL

SWITCH_TOKEN = "OThmN2U0MmMyZTNhNGY4NmE3NGViNDNmYmI0MWVkMzk6MGEyNDQ5YTItMDAxYS00NTFlLWFmZWMtM2U4MTI5MDFjNGQ3"


@dataclass
class AuthSession:
    access_token: str
    device_code: str
    user_code: str


@dataclass
class AuthData:
    user_id: int
    display_name: str
    account_id: str
    device_id: str
    secret: str
    access_token: str
    expires_at: datetime
    avatar_url: Optional[str] = None


class CosmeticService:
    identifiers: dict[str, str] = {}

    def __init__(self) -> None:
        asyncio.create_task(self._load())

    async def _load(self) -> None:
        try:
            async with ClientSession() as client:
                async with client.get(
                    URL.build(scheme="https", host="fortnite.gg", path="/api/items.json")
                ) as resp:
                    data = await resp.json()
                    self.identifiers = {k.lower(): v for k, v in data.items()}
        except Exception:
            pass

    @staticmethod
    def create_variant(**kwargs: Any) -> List[Dict[str, Union[str, int]]]:
        config = {
            "pattern": "Mat{}", "numeric": "Numeric.{}", "clothing_color": "Mat{}",
            "jersey_color": "Color.{}", "parts": "Stage{}", "progressive": "Stage{}",
            "particle": "Emissive{}", "material": "Mat{}", "emissive": "Emissive{}",
            "profile_banner": "{}",
        }
        data = []
        for channel, value in kwargs.items():
            v = {"c": "".join(x.capitalize() for x in channel.split("_")), "dE": 0}
            v["v"] = config.get(channel, "{}").format(value)
            data.append(v)
        return data


class SessionManager:
    def __init__(self) -> None:
        self.client = ClientSession(
            headers={"User-Agent": "Fortnite/++Fortnite+Release-24.10-CL-24850983 Windows/10.0.22621.1.256.64bit"}
        )
        self.cosmetic_service = CosmeticService()
        self._avatar_cache: dict[str, str] = {}
        self._party_cache: dict[str, str] = {}

    async def initiate_login(self) -> AuthSession:
        async with self.client.post(
            URL.build(scheme="https", host="account-public-service-prod.ol.epicgames.com", path="/account/api/oauth/token"),
            data={"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {SWITCH_TOKEN}"},
        ) as resp:
            data = await resp.json()
        device_code, user_code = await self._create_device_code(data["access_token"])
        return AuthSession(access_token=data["access_token"], device_code=device_code, user_code=user_code)

    async def _create_device_code(self, access_token: str) -> tuple[str, str]:
        async with self.client.post(
            URL.build(scheme="https", host="account-public-service-prod03.ol.epicgames.com", path="/account/api/oauth/deviceAuthorization"),
            data={},
            headers={"Authorization": f"Bearer {access_token}"},
        ) as resp:
            data = await resp.json()
        return data["device_code"], data["user_code"]

    async def poll_device_code(self, device_code: str) -> Optional[AuthData]:
        start = datetime.now()
        while (datetime.now() - start).total_seconds() < 240:
            async with self.client.post(
                URL.build(scheme="https", host="account-public-service-prod03.ol.epicgames.com", path="/account/api/oauth/token"),
                data={"grant_type": "device_code", "device_code": device_code},
                headers={"Authorization": f"Basic {SWITCH_TOKEN}"},
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    break
                if not data.get("errorCode", "").endswith(("pending", "not_found")):
                    return None
            await asyncio.sleep(10)
        else:
            return None

        async with self.client.post(
            URL.build(scheme="https", host="account-public-service-prod.ol.epicgames.com", path=f"/account/api/public/account/{data['account_id']}/deviceAuth"),
            json={},
            headers={"Authorization": f"Bearer {data['access_token']}"},
        ) as resp:
            device = await resp.json()

        return AuthData(
            user_id=0,
            display_name=data["displayName"],
            account_id=data["account_id"],
            device_id=device["deviceId"],
            secret=device["secret"],
            access_token=data["access_token"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )

    async def revalidate(self, data: AuthData) -> AuthData:
        async with self.client.post(
            URL.build(scheme="https", host="account-public-service-prod.ol.epicgames.com", path="/account/api/oauth/token"),
            data={"grant_type": "device_auth", "account_id": data.account_id, "device_id": data.device_id, "secret": data.secret},
            headers={"Authorization": f"Basic {SWITCH_TOKEN}"},
        ) as resp:
            new = await resp.json()
        return AuthData(
            user_id=data.user_id,
            display_name=new["displayName"],
            account_id=new["account_id"],
            device_id=data.device_id,
            secret=data.secret,
            access_token=new["access_token"],
            expires_at=datetime.fromisoformat(new["expires_at"]),
        )

    async def get_avatar(self, auth: AuthData) -> str:
        if auth.account_id in self._avatar_cache:
            return self._avatar_cache[auth.account_id]
        async with self.client.get(
            URL.build(scheme="https", host="avatar-service-prod.identity.live.on.epicgames.com", path="/v1/avatar/fortnite/ids"),
            params={"accountIds": auth.account_id},
            headers={"Authorization": f"Bearer {auth.access_token}"},
        ) as resp:
            data = await resp.json()
        avatar_id = "CID_001_Athena_Commando_F_Default"
        if data and (aid := data[0].get("avatarId")):
            avatar_id = aid.replace("ATHENACHARACTER:", "")
        url = f"https://fortnite-api.com/images/cosmetics/br/{avatar_id}/icon.png"
        self._avatar_cache[auth.account_id] = url
        return url

    async def get_party(self, auth: AuthData) -> Optional[str]:
        async with self.client.get(
            URL.build(scheme="https", host="party-service-prod.ol.epicgames.com", path=f"/party/api/v1/Fortnite/user/{auth.account_id}"),
            headers={"Authorization": f"bearer {auth.access_token}"},
        ) as resp:
            data = await resp.json()
        if not data.get("current"):
            return None
        return data["current"][0]["id"]

    async def patch_party(self, auth: AuthData, payload: dict, revision: Optional[str] = None) -> bool:
        party_id = await self.get_party(auth)
        if not party_id:
            raise CommandError("You need to be in the lobby to use this command")
        async with self.client.patch(
            URL.build(scheme="https", host="party-service-prod.ol.epicgames.com", path=f"/party/api/v1/Fortnite/parties/{party_id}/members/{auth.account_id}/meta"),
            json={"delete": [], "revision": int(revision or 1), "update": payload},
            headers={"Authorization": f"Bearer {auth.access_token}"},
        ) as resp:
            if resp.status == 204:
                return True
            data = await resp.json()
            if "stale_revision" in data.get("errorCode", ""):
                return await self.patch_party(auth, payload, max(data["messageVars"]))
            if error := data.get("errorMessage"):
                raise CommandError(f"An error occurred while patching the party\n{error}")
        return True
