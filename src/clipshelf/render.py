"""Markdown rendering: books in, per-book .md files out.

Rendering is deliberately deterministic: the same clippings always produce
byte-identical Markdown (no wall-clock timestamps, sorted ordering, stable
slugs), so exported notes diff cleanly in git and tests can assert whole
files.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .model import Book, Clipping, Kind

_SLUG_STRIP = re.compile(r"[^\w\s-]", re.UNICODE)
_SLUG_DASH = re.compile(r"[\s_-]+")


def slugify(title: str, max_length: int = 80) -> str:
    """Filesystem-safe, human-readable file stem for a book title.

    Unicode letters survive (CJK titles stay readable); punctuation and
    path separators do not. Falls back to "untitled" rather than emitting
    an empty stem.
    """
    value = unicodedata.normalize("NFKC", title)
    value = _SLUG_STRIP.sub("", value)
    value = _SLUG_DASH.sub("-", value).strip("-").casefold()
    value = value[:max_length].rstrip("-")
    return value or "untitled"


def group_books(clippings: Iterable[Clipping]) -> List[Book]:
    """Group clippings by (title, author), ordered by first appearance.

    Sideloaded documents sometimes lose their author metadata mid-library,
    so an authorless group is folded into the authored group when exactly
    one book shares its title — an unambiguous match. Same title under two
    different authors always stays two books.
    """
    books: Dict[Tuple[str, str], Book] = {}
    for c in clippings:
        book = books.get(c.book_key)
        if book is None:
            book = Book(title=c.title, author=c.author)
            books[c.book_key] = book
        book.clippings.append(c)

    merged: List[Book] = []
    by_title: Dict[str, List[Tuple[Tuple[str, str], Book]]] = {}
    for key, book in books.items():
        by_title.setdefault(key[0], []).append((key, book))

    absorbed = set()
    for group in by_title.values():
        authorless = [(k, b) for k, b in group if not k[1]]
        authored = [(k, b) for k, b in group if k[1]]
        if len(authorless) == 1 and len(authored) == 1:
            _, host = authored[0]
            orphan_key, orphan = authorless[0]
            host.clippings.extend(orphan.clippings)
            host.clippings.sort(key=lambda c: c.source_index)
            absorbed.add(orphan_key)

    for key, book in books.items():
        if key not in absorbed:
            merged.append(book)
    return merged


def attach_notes(book: Book) -> Dict[int, List[Clipping]]:
    """Map highlight source_index -> notes that annotate it.

    A Kindle note is anchored at a single location; when that location
    falls inside a highlight's range, the user wrote the note *about* that
    highlight, so it renders beneath the quote instead of floating alone.
    Notes matching no highlight are returned under key -1.
    """
    highlights = sorted(book.highlights, key=lambda c: c.sort_key)
    attached: Dict[int, List[Clipping]] = {}
    for note in sorted(book.notes, key=lambda c: c.sort_key):
        home = -1
        if note.location is not None:
            for h in highlights:
                if h.location is not None and h.location.contains(note.location):
                    home = h.source_index
                    break
        attached.setdefault(home, []).append(note)
    return attached


@dataclass
class RenderOptions:
    """Knobs for the Markdown output."""

    include_bookmarks: bool = False
    include_location: bool = True
    include_page: bool = True
    include_date: bool = True


def _meta_line(c: Clipping, opts: RenderOptions) -> str:
    parts: List[str] = []
    if opts.include_location and c.location is not None:
        parts.append(f"location {c.location}")
    if opts.include_page and c.page is not None:
        parts.append(f"page {c.page}")
    if opts.include_date and c.added is not None:
        parts.append(c.added.strftime("%Y-%m-%d %H:%M"))
    return " · ".join(parts)


def _blockquote(text: str) -> str:
    return "\n".join(f"> {line}".rstrip() for line in text.split("\n"))


def render_book(
    book: Book,
    opts: Optional[RenderOptions] = None,
    duplicates_removed: int = 0,
) -> str:
    """Render one book to a Markdown document."""
    opts = opts or RenderOptions()
    # Cleared highlights leave empty husks in the file; they carry no words
    # worth exporting, so they neither render nor count.
    highlights = sorted(
        (c for c in book.highlights + book.of_kind(Kind.CLIP) if c.text.strip()),
        key=lambda c: c.sort_key,
    )
    notes_by_highlight = attach_notes(book)
    bookmarks = sorted(book.bookmarks, key=lambda c: c.sort_key)

    lines: List[str] = [f"# {book.title}", ""]
    if book.author:
        lines += [f"*{book.author}*", ""]

    counts = [f"{len(highlights)} highlight{'s' if len(highlights) != 1 else ''}"]
    note_total = len(book.notes)
    if note_total:
        counts.append(f"{note_total} note{'s' if note_total != 1 else ''}")
    if opts.include_bookmarks and bookmarks:
        counts.append(f"{len(bookmarks)} bookmark{'s' if len(bookmarks) != 1 else ''}")
    summary = " · ".join(counts)
    if duplicates_removed:
        summary += f" ({duplicates_removed} duplicate{'s' if duplicates_removed != 1 else ''} removed)"
    lines += [summary, ""]

    if highlights:
        lines += ["## Highlights", ""]
        for h in highlights:
            lines.append(_blockquote(h.text))
            meta = _meta_line(h, opts)
            if meta:
                lines += ["", f"<sub>{meta}</sub>"]
            for note in notes_by_highlight.get(h.source_index, []):
                lines += ["", f"**Note:** {note.text}"]
            lines.append("")

    orphan_notes = notes_by_highlight.get(-1, [])
    if orphan_notes:
        lines += ["## Notes", ""]
        for note in orphan_notes:
            lines.append(note.text)
            meta = _meta_line(note, opts)
            if meta:
                lines += ["", f"<sub>{meta}</sub>"]
            lines.append("")

    if opts.include_bookmarks and bookmarks:
        lines += ["## Bookmarks", ""]
        for b in bookmarks:
            meta = _meta_line(b, opts)
            lines.append(f"- {meta or 'bookmark'}")
        lines.append("")

    # Collapse any accidental double blank lines and end with one newline.
    out: List[str] = []
    for line in lines:
        if line == "" and out and out[-1] == "":
            continue
        out.append(line)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


def unique_slugs(books: List[Book]) -> Dict[Tuple[str, str], str]:
    """Assign collision-free file stems to every book.

    Two books that slugify identically ("1984" by two editions) get
    numeric suffixes in first-appearance order, so exports are stable
    run to run.
    """
    result: Dict[Tuple[str, str], str] = {}
    used: Dict[str, int] = {}
    for book in books:
        base = slugify(book.title)
        n = used.get(base, 0)
        used[base] = n + 1
        result[book.book_key] = base if n == 0 else f"{base}-{n + 1}"
    return result
