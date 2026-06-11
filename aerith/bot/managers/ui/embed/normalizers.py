from __future__ import annotations

import re
from enum import Enum
from typing import List, Mapping, Optional, Sequence, Tuple, Union

from .redex import RedexHandler
from .entries import AuthorEntry, FieldEntry
from discord import ui, SeparatorSpacing

class SeparatorSize(str, Enum):
    SMALL = "small"
    LARGE = "large"

    @property
    def spacing(self) -> SeparatorSpacing:
        return (
            SeparatorSpacing.large
            if self is SeparatorSize.LARGE
            else SeparatorSpacing.small
        )

    @classmethod
    def from_raw(cls, raw: str) -> "SeparatorSize":
        return cls.LARGE if raw == cls.LARGE.value else cls.SMALL

class DataNormalizer:
    """Utility for cleaning up strings and nested objects."""

    @staticmethod
    def text(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @classmethod
    def author(cls, author: Optional[AuthorEntry]) -> Optional[AuthorEntry]:
        if not isinstance(author, AuthorEntry):
            return None
        name = cls.text(author.name)
        if not name:
            return None
        return AuthorEntry(
            name=name,
            icon_url=cls.text(author.icon_url),
            url=cls.text(author.url),
        )

    @classmethod
    def fields(
        cls, fields: Optional[Union[Mapping[str, str], Sequence[FieldEntry]]]
    ) -> Tuple[FieldEntry, ...]:
        if not fields:
            return ()

        normalized: List[FieldEntry] = []
        if isinstance(fields, Mapping):
            for name, value in fields.items():
                n_name = cls.text(str(name))
                n_val = cls.text(str(value))
                if n_name or n_val:
                    normalized.append(FieldEntry(n_name or "", n_val or ""))
            return tuple(normalized)

        for entry in fields:
            if not isinstance(entry, FieldEntry):
                continue
            n_name = cls.text(entry.name)
            n_val = cls.text(entry.value)
            if n_name or n_val:
                normalized.append(
                    FieldEntry(n_name or "", n_val or "", bool(entry.inline))
                )
        return tuple(normalized)

class DescriptionCompiler:
    """Handles tokenizing and converting description text into UI items."""

    _SEP_PATTERN = re.compile(r"\{separator\.(small|large)\}")

    def compile(self, text: str) -> List[ui.Item]:
        if not text:
            return []

        parts = self._SEP_PATTERN.split(text)
        handler = RedexHandler()

        for i in range(0, len(parts), 2):
            if chunk := parts[i]:
                handler.add(chunk, lambda c: ui.TextDisplay(content=c))

            if i + 1 < len(parts):
                size = SeparatorSize.from_raw(parts[i + 1])
                handler.add(size.value, lambda _: ui.Separator(spacing=size.spacing))

        return [
            item
            for item in handler.reduce_all(strategy="normal")
            if isinstance(item, ui.Item)
        ]
