from dataclasses import dataclass
from typing import Optional

@dataclass
class BibleTranslation:
    identifier: str
    name: str
    language: str
    language_code: str
    license: str

    @classmethod
    def from_dict(cls, data: dict) -> 'BibleTranslation':
        return cls(
            identifier=data.get('identifier', ''),
            name=data.get('name', ''),
            language=data.get('language', ''),
            language_code=data.get('language_code', ''),
            license=data.get('license', '')
        )

@dataclass
class BibleVerse:
    book_id: str
    book: str
    chapter: int
    verse: int
    text: str

    @classmethod
    def from_dict(cls, data: dict) -> 'BibleVerse':
        return cls(
            book_id=data.get('book_id', ''),
            book=data.get('book', ''),
            chapter=data.get('chapter', 0),
            verse=data.get('verse', 0),
            text=data.get('text', '')
        )

@dataclass
class BibleResponse:
    translation: BibleTranslation
    random_verse: BibleVerse

    @classmethod
    def from_dict(cls, data: dict) -> 'BibleResponse':
        translation = BibleTranslation.from_dict(data.get('translation', {}))
        random_verse = BibleVerse.from_dict(data.get('random_verse', {}))
        
        return cls(
            translation=translation,
            random_verse=random_verse
        )

