from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any, Literal, Optional

import aiohttp

_Mode = Literal["json", "text", "bytes"]


class _RequestContextManager(AbstractAsyncContextManager[Any]):
    """Wraps an aiohttp request context manager, optionally consuming the response body."""

    def __init__(
        self,
        cm: AbstractAsyncContextManager[aiohttp.ClientResponse],
        mode: _Mode | None,
    ) -> None:
        self._cm = cm
        self._mode = mode
        self._resp: Optional[aiohttp.ClientResponse] = None

    async def __aenter__(self) -> Any:
        self._resp = await self._cm.__aenter__()
        match self._mode:
            case None:
                return self._resp
            case "json":
                if self._resp.content_type != "application/json":
                    text = await self._resp.text()

                    raise RuntimeError(
                        f"unexpected content type "
                        f"{self._resp.content_type} "
                        f"(status={self._resp.status})\n{text}"
                    )

                return await self._resp.json()
                
            case "text":
                return await self._resp.text()  # type: ignore
            case "bytes":
                return await self._resp.read()  # type: ignore
            case _:
                raise ValueError(f"invalid mode: {self._mode!r}")

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool | None:
        return await self._cm.__aexit__(exc_type, exc, tb)


class HTTP:
    """Wraps aiohttp.ClientSession with a managed connect/close lifecycle."""

    def __init__(self, version: float) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self.version = version

    @property
    def session(self) -> aiohttp.ClientSession:
        """Returns the underlying ClientSession.

        Raises:
            RuntimeError: If ``connect()`` has not been called yet.
        """
        if self._session is None:
            raise RuntimeError(
                "HTTP.connect() must be called before accessing session."
            )
        return self._session

    async def connect(self, **kwargs: Any) -> "HTTP":
        """Initializes the aiohttp ClientSession.

        Args:
            **kwargs: Extra keyword arguments forwarded to ``aiohttp.ClientSession``.

        Returns:
            The ``HTTP`` instance (``self``).
        """
        headers: dict[str, str] = {
            "User-Agent": f"Mist-Bot/{self.version}",
            **kwargs.pop("headers", {}),
        }
        timeout: aiohttp.ClientTimeout = kwargs.pop(
            "timeout", aiohttp.ClientTimeout(total=10)
        )
        self._session = aiohttp.ClientSession(
            headers=headers,
            timeout=timeout,
            **kwargs,
        )
        return self

    async def close(self) -> None:
        """Closes the underlying ClientSession and resets internal state."""
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> "HTTP":
        return await self.connect()

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    def _wrap(
        self,
        cm: AbstractAsyncContextManager[aiohttp.ClientResponse],
        mode: _Mode | None,
    ) -> _RequestContextManager:
        return _RequestContextManager(cm, mode)

    def get(
        self, url: str, *, mode: _Mode | None = None, **kwargs: Any
    ) -> _RequestContextManager:
        """Proxy for ``ClientSession.get``."""
        return self._wrap(self.session.get(url, **kwargs), mode)

    def post(
        self, url: str, *, mode: _Mode | None = None, **kwargs: Any
    ) -> _RequestContextManager:
        """Proxy for ``ClientSession.post``."""
        return self._wrap(self.session.post(url, **kwargs), mode)

    def put(
        self, url: str, *, mode: _Mode | None = None, **kwargs: Any
    ) -> _RequestContextManager:
        """Proxy for ``ClientSession.put``."""
        return self._wrap(self.session.put(url, **kwargs), mode)

    def delete(
        self, url: str, *, mode: _Mode | None = None, **kwargs: Any
    ) -> _RequestContextManager:
        """Proxy for ``ClientSession.delete``."""
        return self._wrap(self.session.delete(url, **kwargs), mode)

    def patch(
        self, url: str, *, mode: _Mode | None = None, **kwargs: Any
    ) -> _RequestContextManager:
        """Proxy for ``ClientSession.patch``."""
        return self._wrap(self.session.patch(url, **kwargs), mode)
