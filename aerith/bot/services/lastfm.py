from __future__ import annotations

from typing import Optional
from .session import HTTP 


class LastFMHandler:
    base = "https://ws.audioscrobbler.com/2.0/"

    def __init__(self, key: str, version: float = 1.0) -> None:
        self.key = key
        self.http = HTTP(version)

    def _params(self, **kwargs: str | int) -> dict:
        return {"api_key": self.key, "format": "json", **kwargs}

    async def get_recent_tracks(self, user: str, limit: int = 1) -> dict:
        async with self.http.get(
            self.base,
            mode="json",
            params=self._params(method="user.getrecenttracks", user=user, limit=limit),
        ) as data:
            return data

    async def get_user_info(self, user: str) -> dict:
        async with self.http.get(
            self.base,
            mode="json",
            params=self._params(method="user.getinfo", user=user),
        ) as data:
            return data

    async def get_artist_playcount(self, user: str, artist: str) -> int:
        async with self.http.get(
            self.base,
            mode="json",
            params=self._params(method="artist.getinfo", artist=artist, username=user),
        ) as data:
            return int(data["artist"]["stats"]["userplaycount"])

    async def get_album_playcount(self, user: str, track_info: dict) -> Optional[int]:
        if not track_info.get("album", {}).get("#text"):
            return None
        try:
            async with self.http.get(
                self.base,
                mode="json",
                params=self._params(
                    method="album.getinfo",
                    artist=track_info["artist"]["#text"],
                    album=track_info["album"]["#text"],
                    username=user,
                ),
            ) as data:
                return int(data["album"]["userplaycount"])
        except Exception:
            return None

    async def get_track_playcount(self, user: str, track_info: dict) -> Optional[int]:
        try:
            async with self.http.get(
                self.base,
                mode="json",
                params=self._params(
                    method="track.getInfo",
                    artist=track_info["artist"]["#text"],
                    track=track_info["name"],
                    username=user,
                ),
            ) as data:
                return int(data["track"]["userplaycount"])
        except Exception:
            return None