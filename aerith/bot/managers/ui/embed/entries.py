from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True, frozen=True)
class AuthorEntry:
    name: str
    icon_url: Optional[str] = None
    url: Optional[str] = None


@dataclass(slots=True, frozen=True)
class FieldEntry:
    name: str
    value: str
    inline: bool = False


@dataclass(slots=True, frozen=True)
class FooterEntry:
    text: str
    icon_url: Optional[str] = None
