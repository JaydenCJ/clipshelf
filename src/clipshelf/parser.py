"""Parser for Kindle's My Clippings.txt.

The file is a flat log: every highlight, note, and bookmark ever made is
appended as one entry, and entries are separated by a line of ten equals
signs. An entry looks like this (CRLF line endings, possibly a UTF-8 BOM
on the very first line):

    How to Read a Book (Mortimer J. Adler)
    - Your Highlight on page 23 | Location 351-352 | Added on Tuesday, ...

    The text of the highlight, which may span several lines.
    ==========

The parser is deliberately forgiving: a malformed entry becomes a warning,
never an exception, because a clippings file accumulated over years of
firmware updates is guaranteed to contain at least one oddity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Union

from . import dates, locales
from .errors import ParseError
from .model import Clipping, Kind, Location

SEPARATOR = "=========="

# "Title (Author)" — the author is the LAST parenthesized group at the end
# of the line, so "Ficciones (spanish) (Jorge Luis Borges)" keeps
# "(spanish)" inside the title.
_TITLE_AUTHOR = re.compile(r"^(?P<title>.*?)\s*\((?P<author>[^()]*)\)\s*$")

# A location range after a location keyword: "351-352", "#351-352",
# "351-52" (pre-2011 abbreviated end), or a single "351".
_RANGE = re.compile(r"#?\s*(\d+)(?:\s*-\s*(\d+))?")

# Page numbers may be arabic or roman ("page ix" in front matter). The
# value is anchored right after the keyword so stray letters in the rest
# of the segment can never masquerade as a roman numeral.
_PAGE_VALUE = re.compile(r"\s*#?\s*([0-9]+|[ivxlcdm]+)\b", re.IGNORECASE)
_PAGE_SUFFIX = re.compile(r"(\d+)\s*(?:ページ|页)")


@dataclass
class ParseResult:
    """Outcome of parsing one clippings file."""

    clippings: List[Clipping] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def entry_count(self) -> int:
        return len(self.clippings)


def expand_abbreviated_end(start: int, end: int) -> int:
    """Expand pre-2011 abbreviated range ends.

    Old firmware wrote "Loc. 351-52" meaning 351-352: the end shares the
    start's leading digits. When the written end is smaller than the start,
    splice the start's prefix onto it. Ends that are already >= start pass
    through untouched.
    """
    if end >= start:
        return end
    end_digits = str(end)
    start_digits = str(start)
    if len(end_digits) >= len(start_digits):
        return end  # genuinely reversed; caller will flag it
    candidate = int(start_digits[: len(start_digits) - len(end_digits)] + end_digits)
    return candidate if candidate >= start else end


def _parse_title_line(line: str) -> Tuple[str, Optional[str]]:
    """Split "Title (Author)" into its parts; author may be absent."""
    line = line.lstrip("﻿").strip()
    m = _TITLE_AUTHOR.match(line)
    if m and m.group("title"):
        return m.group("title").strip(), m.group("author").strip() or None
    return line, None


def _find_after_keyword(segment: str, keywords) -> Optional[str]:
    """Return the text following the first matching keyword, else None."""
    folded = segment.casefold()
    best_pos, best_end = -1, -1
    for word in keywords:
        pos = folded.find(word)
        if pos != -1 and (best_pos == -1 or pos < best_pos):
            best_pos, best_end = pos, pos + len(word)
    if best_pos == -1:
        return None
    return segment[best_end:]


def _parse_location(segment: str) -> Optional[Location]:
    tail = _find_after_keyword(segment, locales.LOCATION_WORDS)
    if tail is None:
        return None
    m = _RANGE.search(tail)
    if not m:
        return None
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else start
    end = expand_abbreviated_end(start, end)
    if end < start:
        return None
    return Location(start, end)


def _parse_page(segment: str) -> Optional[str]:
    tail = _find_after_keyword(segment, locales.PAGE_WORDS)
    if tail is not None:
        m = _PAGE_VALUE.match(tail)
        if m:
            return m.group(1)
    m = _PAGE_SUFFIX.search(segment)
    if m:
        return m.group(1)
    return None


def _parse_added(meta_line: str) -> Optional[str]:
    """Return the text after the 'Added on' marker, else None."""
    return _find_after_keyword(meta_line, locales.ADDED_WORDS)


def parse_metadata(meta_line: str) -> Tuple[Kind, Optional[Location], Optional[str], Optional[object]]:
    """Parse the '- Your Highlight on ...' line.

    Returns (kind, location, page, added). Unknown pieces come back as
    None / Kind.UNKNOWN; the caller decides how loud to be about it.
    """
    kind = locales.kind_of(meta_line) or Kind.UNKNOWN

    location: Optional[Location] = None
    page: Optional[str] = None
    for segment in meta_line.split("|"):
        if location is None:
            location = _parse_location(segment)
        if page is None:
            page = _parse_page(segment)

    added = None
    added_text = _parse_added(meta_line)
    if added_text is not None:
        added = dates.parse_added(added_text)

    return kind, location, page, added


def _split_entries(raw: str) -> List[str]:
    """Split file content on separator lines, tolerating stray whitespace."""
    entries: List[str] = []
    current: List[str] = []
    for line in raw.split("\n"):
        if line.strip().rstrip("=") == "" and line.count("=") >= 8:
            entries.append("\n".join(current))
            current = []
        else:
            current.append(line)
    if any(line.strip() for line in current):
        entries.append("\n".join(current))
    return [e for e in entries if e.strip()]


def parse_text(raw: str) -> ParseResult:
    """Parse the full text of a My Clippings.txt file."""
    raw = raw.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    result = ParseResult()

    for index, entry in enumerate(_split_entries(raw)):
        lines = entry.split("\n")
        # Drop leading blank lines within the entry.
        while lines and not lines[0].strip():
            lines.pop(0)
        if not lines:
            continue

        title, author = _parse_title_line(lines[0])
        if not title:
            result.warnings.append(f"entry {index}: empty title line, skipped")
            continue

        meta_index = next(
            (i for i, ln in enumerate(lines[1:], start=1) if ln.lstrip().startswith("-")),
            None,
        )
        if meta_index is None:
            result.warnings.append(
                f"entry {index} ({title!r}): no metadata line, skipped"
            )
            continue

        kind, location, page, added = parse_metadata(lines[meta_index])
        if kind is Kind.UNKNOWN:
            result.warnings.append(
                f"entry {index} ({title!r}): unrecognized metadata "
                f"{lines[meta_index].strip()!r}"
            )

        text = "\n".join(lines[meta_index + 1 :]).strip()

        result.clippings.append(
            Clipping(
                title=title,
                author=author,
                kind=kind,
                text=text,
                location=location,
                page=page,
                added=added,
                source_index=index,
            )
        )

    return result


def parse_file(path: Union[str, Path]) -> ParseResult:
    """Read and parse a clippings file from disk.

    Kindle writes UTF-8 with a BOM; some very old devices wrote UTF-16.
    Both are handled. A missing or undecodable file raises ParseError.
    """
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ParseError(f"cannot read {path}: {exc}") from exc

    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        text = data.decode("utf-16")
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = data.decode("latin-1")
            except UnicodeDecodeError as exc:  # pragma: no cover - latin-1 total
                raise ParseError(f"cannot decode {path}: {exc}") from exc

    return parse_text(text)
