"""Core data types for clipshelf.

Everything downstream (parser, dedupe, renderer, CLI) speaks in terms of
these small immutable-ish dataclasses. Keeping them free of behavior beyond
cheap derived properties makes every other module unit-testable in isolation.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple


class Kind(enum.Enum):
    """The type of a single clipping entry."""

    HIGHLIGHT = "highlight"
    NOTE = "note"
    BOOKMARK = "bookmark"
    CLIP = "clip"  # "Clip This Article" entries from periodicals
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Location:
    """A Kindle location range. Single-point locations have start == end."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError(f"invalid location range {self.start}-{self.end}")

    def overlaps(self, other: "Location") -> bool:
        """True when the two ranges share at least one location number."""
        return self.start <= other.end and other.start <= self.end

    def contains(self, other: "Location") -> bool:
        """True when *other* lies entirely within this range."""
        return self.start <= other.start and other.end <= self.end

    @property
    def span(self) -> int:
        return self.end - self.start + 1

    def __str__(self) -> str:
        if self.start == self.end:
            return str(self.start)
        return f"{self.start}-{self.end}"


@dataclass
class Clipping:
    """One parsed entry from My Clippings.txt."""

    title: str
    author: Optional[str]
    kind: Kind
    text: str
    location: Optional[Location] = None
    page: Optional[str] = None  # kept as text: Kindle uses roman numerals ("ix")
    added: Optional[datetime] = None
    source_index: int = 0  # 0-based position of the entry in the source file

    @property
    def book_key(self) -> Tuple[str, str]:
        """Grouping key for a book: normalized title + author."""
        return (self.title.strip().casefold(), (self.author or "").strip().casefold())

    @property
    def sort_key(self) -> Tuple[int, int, int]:
        """Stable reading-order key: location first, then file order."""
        if self.location is not None:
            return (self.location.start, self.location.end, self.source_index)
        return (1 << 30, 1 << 30, self.source_index)


@dataclass
class Book:
    """All clippings that belong to one title/author pair."""

    title: str
    author: Optional[str]
    clippings: List[Clipping] = field(default_factory=list)

    @property
    def book_key(self) -> Tuple[str, str]:
        """Grouping key for this book; matches Clipping.book_key."""
        return (self.title.strip().casefold(), (self.author or "").strip().casefold())

    def of_kind(self, kind: Kind) -> List[Clipping]:
        return [c for c in self.clippings if c.kind is kind]

    @property
    def highlights(self) -> List[Clipping]:
        return self.of_kind(Kind.HIGHLIGHT)

    @property
    def notes(self) -> List[Clipping]:
        return self.of_kind(Kind.NOTE)

    @property
    def bookmarks(self) -> List[Clipping]:
        return self.of_kind(Kind.BOOKMARK)

    @property
    def last_added(self) -> Optional[datetime]:
        """Most recent timestamp across the book's clippings, if any."""
        stamps = [c.added for c in self.clippings if c.added is not None]
        return max(stamps) if stamps else None
