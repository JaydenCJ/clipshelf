"""Deduplication of overlapping highlight revisions.

Kindle never edits My Clippings.txt in place. Nudge a highlight's edge to
grab one more sentence and the device *appends a second full entry*; do it
three times and the file holds four copies of the same passage. Naive
splitters copy every revision into the notes. clipshelf collapses them.

Two highlights are considered revisions of the same act of highlighting
when their location ranges overlap AND their normalized texts are related:

* identical            -> exact duplicate (re-synced sidecar, merged files)
* one contains the other -> the user extended or trimmed the highlight
* neither contains the other but they share a long common run
                        -> the user moved both edges (prefix/suffix drift)

The survivor is the *latest revision*: by "Added on" timestamp when both
entries carry one, otherwise by position in the file (Kindle appends, so
later in the file means later in time). Everything is pure and offline —
no fuzzy scoring against a service, just difflib on normalized text.
"""

from __future__ import annotations

import enum
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from .model import Clipping, Kind

#: Minimum (longest common run) / (shorter text length) for two
#: overlapping, non-contained texts to count as one revised highlight.
DEFAULT_OVERLAP_RATIO = 0.6

_WS = re.compile(r"\s+")


class Reason(enum.Enum):
    """Why a clipping was dropped in favor of another."""

    IDENTICAL = "identical"    # same text, same place
    CONTAINED = "contained"    # its text lies inside the survivor's text
    REVISED = "revised"        # overlapping ranges + shared run of text


@dataclass
class Dropped:
    """One clipping removed by dedupe, with its reason and survivor."""

    clipping: Clipping
    reason: Reason
    kept: Clipping


@dataclass
class DedupeResult:
    """Kept clippings (original order preserved) plus an audit trail."""

    kept: List[Clipping] = field(default_factory=list)
    dropped: List[Dropped] = field(default_factory=list)

    @property
    def removed_count(self) -> int:
        return len(self.dropped)


def normalize(text: str) -> str:
    """Canonical form used for all text comparison.

    NFKC folds typographic variants (curly quotes Kindle sometimes swaps
    for straight ones between firmware versions), casefold handles case,
    and whitespace collapses because revisions re-wrap line breaks.
    """
    text = unicodedata.normalize("NFKC", text)
    text = _WS.sub(" ", text).strip()
    return text.casefold()


def _longest_common_run(a: str, b: str) -> int:
    """Length of the longest common substring of two normalized texts."""
    if not a or not b:
        return 0
    match = SequenceMatcher(None, a, b, autojunk=False).find_longest_match(
        0, len(a), 0, len(b)
    )
    return match.size


def classify(
    a: Clipping, b: Clipping, overlap_ratio: float = DEFAULT_OVERLAP_RATIO
) -> Optional[Reason]:
    """Decide whether two highlights are revisions of one another.

    Both must have locations that overlap; text relation then picks the
    reason. Returns None when they are genuinely distinct highlights
    (e.g. adjacent passages that merely share a location boundary).
    """
    if a.location is None or b.location is None:
        return None
    if not a.location.overlaps(b.location):
        return None

    ta, tb = normalize(a.text), normalize(b.text)
    if not ta or not tb:
        # An empty revision (highlight cleared and re-made) still counts
        # as identical when both are empty; otherwise undecidable.
        return Reason.IDENTICAL if ta == tb else None
    if ta == tb:
        return Reason.IDENTICAL
    if ta in tb or tb in ta:
        return Reason.CONTAINED
    run = _longest_common_run(ta, tb)
    if run / min(len(ta), len(tb)) >= overlap_ratio:
        return Reason.REVISED
    return None


def _is_later(a: Clipping, b: Clipping) -> bool:
    """True when *a* is a later revision than *b*."""
    if a.added is not None and b.added is not None and a.added != b.added:
        return a.added > b.added
    return a.source_index > b.source_index


def _pick_survivor(a: Clipping, b: Clipping, reason: Reason) -> Clipping:
    """Choose which of two related highlights to keep.

    For containment the longer text wins even against the clock: a later
    entry that *trims* the highlight is treated as the final intent only
    when timestamps prove it came later; with equal or missing evidence,
    keeping more of the user's words is the safer default.
    """
    if reason is Reason.CONTAINED:
        na, nb = normalize(a.text), normalize(b.text)
        if len(na) != len(nb):
            longer, shorter = (a, b) if len(na) > len(nb) else (b, a)
            # A strictly later, strictly shorter revision is a deliberate trim.
            if (
                shorter.added is not None
                and longer.added is not None
                and shorter.added > longer.added
            ):
                return shorter
            return longer
    return a if _is_later(a, b) else b


def _dedupe_highlights(
    highlights: List[Clipping], overlap_ratio: float
) -> Tuple[List[Clipping], List[Dropped]]:
    """Collapse one book's highlights; order of survivors = reading order."""
    ordered = sorted(highlights, key=lambda c: c.sort_key)
    kept: List[Clipping] = []
    dropped: List[Dropped] = []

    for candidate in ordered:
        merged = False
        # Compare against every kept highlight whose range could overlap.
        # Ranges are sorted by start, but survivors' ends vary, so scan all;
        # per-book highlight counts make this comfortably cheap.
        for i, existing in enumerate(kept):
            reason = classify(existing, candidate, overlap_ratio)
            if reason is None:
                continue
            survivor = _pick_survivor(existing, candidate, reason)
            loser = candidate if survivor is existing else existing
            kept[i] = survivor
            dropped.append(Dropped(clipping=loser, reason=reason, kept=survivor))
            merged = True
            break
        if not merged:
            kept.append(candidate)

    return kept, dropped


def _dedupe_exact(
    clippings: List[Clipping],
) -> Tuple[List[Clipping], List[Dropped]]:
    """Exact-duplicate removal for notes/bookmarks (no fuzzy merging).

    Notes are the user's own words; two different notes at one location
    are both kept. Only byte-equivalent repeats (same normalized text at
    the same location) collapse — these come from merged clippings files.
    """
    kept: List[Clipping] = []
    dropped: List[Dropped] = []
    seen: Dict[Tuple, Clipping] = {}
    for c in sorted(clippings, key=lambda c: c.sort_key):
        key = (
            c.location.start if c.location else None,
            c.location.end if c.location else None,
            normalize(c.text),
        )
        if key in seen:
            dropped.append(Dropped(clipping=c, reason=Reason.IDENTICAL, kept=seen[key]))
        else:
            seen[key] = c
            kept.append(c)
    return kept, dropped


def dedupe(
    clippings: List[Clipping], overlap_ratio: float = DEFAULT_OVERLAP_RATIO
) -> DedupeResult:
    """Deduplicate a full parse across all books.

    Highlights get the revision-collapsing treatment per book; notes,
    bookmarks, and article clips only lose exact repeats. Clippings of
    unknown kind pass through untouched — dedupe never guesses on
    entries it could not read.
    """
    by_book: Dict[Tuple[str, str], Dict[Kind, List[Clipping]]] = {}
    passthrough: List[Clipping] = []
    for c in clippings:
        if c.kind is Kind.UNKNOWN:
            passthrough.append(c)
            continue
        by_book.setdefault(c.book_key, {}).setdefault(c.kind, []).append(c)

    result = DedupeResult()
    for groups in by_book.values():
        for kind, items in groups.items():
            if kind is Kind.HIGHLIGHT:
                kept, dropped = _dedupe_highlights(items, overlap_ratio)
            else:
                kept, dropped = _dedupe_exact(items)
            result.kept.extend(kept)
            result.dropped.extend(dropped)

    result.kept.extend(passthrough)
    # Restore global file order so downstream grouping is deterministic.
    result.kept.sort(key=lambda c: c.source_index)
    result.dropped.sort(key=lambda d: d.clipping.source_index)
    return result
