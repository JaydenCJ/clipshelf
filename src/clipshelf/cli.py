"""Command-line interface for clipshelf.

Three subcommands, all offline:

    clipshelf export  — write per-book Markdown files
    clipshelf list    — show books with highlight/note/duplicate counts
    clipshelf stats   — file-wide totals, as text or JSON

Everything is a thin layer over the library modules; no logic lives here
that a script importing clipshelf could not reach.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import __version__
from .dedupe import DEFAULT_OVERLAP_RATIO, DedupeResult, dedupe
from .errors import ClipshelfError
from .model import Book, Clipping, Kind
from .parser import ParseResult, parse_file
from .render import RenderOptions, group_books, render_book, unique_slugs


def _plural(count: int, noun: str) -> str:
    """Human-friendly count: '1 note', '2 notes'."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _ratio(value: str) -> float:
    """argparse type for --overlap-ratio: a float in [0.0, 1.0]."""
    try:
        ratio = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number") from None
    if not 0.0 <= ratio <= 1.0:
        raise argparse.ArgumentTypeError(
            f"must be between 0.0 and 1.0, got {value}"
        )
    return ratio


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clipshelf",
        description="Turn a Kindle 'My Clippings.txt' into per-book Markdown notes.",
    )
    parser.add_argument(
        "--version", action="version", version=f"clipshelf {__version__}"
    )
    sub = parser.add_subparsers(dest="command", metavar="command")

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("clippings", help="path to My Clippings.txt")
        p.add_argument(
            "--no-dedupe",
            action="store_true",
            help="keep every raw entry, including overlapping revisions",
        )
        p.add_argument(
            "--overlap-ratio",
            type=_ratio,
            default=DEFAULT_OVERLAP_RATIO,
            metavar="R",
            help="minimum shared-text ratio for two overlapping highlights "
            f"to merge (default {DEFAULT_OVERLAP_RATIO})",
        )

    p_export = sub.add_parser(
        "export", help="write one Markdown file per book"
    )
    add_common(p_export)
    p_export.add_argument(
        "-o",
        "--output",
        default="notes",
        metavar="DIR",
        help="output directory (default: notes/)",
    )
    p_export.add_argument(
        "--book",
        metavar="SUBSTRING",
        help="only export books whose title contains SUBSTRING (case-insensitive)",
    )
    p_export.add_argument(
        "--include-bookmarks",
        action="store_true",
        help="add a Bookmarks section to each file",
    )
    p_export.add_argument(
        "--no-location",
        action="store_true",
        help="omit location numbers from the output",
    )
    p_export.add_argument(
        "--no-date",
        action="store_true",
        help="omit timestamps from the output",
    )
    p_export.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be written without touching the filesystem",
    )

    p_list = sub.add_parser("list", help="list books found in the file")
    add_common(p_list)
    p_list.add_argument("--json", action="store_true", help="emit JSON")

    p_stats = sub.add_parser("stats", help="show file-wide totals")
    add_common(p_stats)
    p_stats.add_argument("--json", action="store_true", help="emit JSON")

    return parser


def _load(
    path: str, no_dedupe: bool, overlap_ratio: float
) -> Tuple[ParseResult, DedupeResult]:
    parsed = parse_file(path)
    if no_dedupe:
        result = DedupeResult(kept=list(parsed.clippings), dropped=[])
    else:
        result = dedupe(parsed.clippings, overlap_ratio=overlap_ratio)
    return parsed, result


def _dropped_per_book(result: DedupeResult) -> Dict[Tuple[str, str], int]:
    counts: Dict[Tuple[str, str], int] = {}
    for d in result.dropped:
        key = d.clipping.book_key
        counts[key] = counts.get(key, 0) + 1
    return counts


def _print_warnings(parsed: ParseResult, out) -> None:
    for warning in parsed.warnings:
        print(f"warning: {warning}", file=out)


def _cmd_export(args: argparse.Namespace) -> int:
    parsed, result = _load(args.clippings, args.no_dedupe, args.overlap_ratio)
    _print_warnings(parsed, sys.stderr)

    books = group_books(c for c in result.kept if c.kind is not Kind.UNKNOWN)
    if args.book:
        needle = args.book.casefold()
        books = [b for b in books if needle in b.title.casefold()]
        if not books:
            print(f"error: no book title contains {args.book!r}", file=sys.stderr)
            return 1

    opts = RenderOptions(
        include_bookmarks=args.include_bookmarks,
        include_location=not args.no_location,
        include_date=not args.no_date,
    )
    slugs = unique_slugs(books)
    dropped_counts = _dropped_per_book(result)

    out_dir = Path(args.output)
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    total_highlights = 0
    total_notes = 0
    total_removed = 0
    for book in books:
        key = book.book_key
        removed = dropped_counts.get(key, 0)
        total_removed += removed
        markdown = render_book(book, opts, duplicates_removed=removed)
        target = out_dir / f"{slugs[key]}.md"
        if not args.dry_run:
            target.write_text(markdown, encoding="utf-8")

        n_highlights = len([c for c in book.highlights if c.text.strip()])
        n_notes = len(book.notes)
        total_highlights += n_highlights
        total_notes += n_notes
        detail = _plural(n_highlights, "highlight")
        if n_notes:
            detail += f", {_plural(n_notes, 'note')}"
        if removed:
            detail += f", {_plural(removed, 'duplicate')} removed"
        verb = "would write" if args.dry_run else "wrote"
        print(f"{verb} {target} ({detail})")

    print(
        f"{_plural(len(books), 'book')}, {_plural(total_highlights, 'highlight')}, "
        f"{_plural(total_notes, 'note')}, {_plural(total_removed, 'duplicate')} removed"
    )
    return 0


def _book_row(book: Book, removed: int) -> Dict[str, object]:
    return {
        "title": book.title,
        "author": book.author,
        "highlights": len([c for c in book.highlights if c.text.strip()]),
        "notes": len(book.notes),
        "bookmarks": len(book.bookmarks),
        "duplicates_removed": removed,
    }


def _cmd_list(args: argparse.Namespace) -> int:
    parsed, result = _load(args.clippings, args.no_dedupe, args.overlap_ratio)
    if not args.json:
        _print_warnings(parsed, sys.stderr)

    books = group_books(c for c in result.kept if c.kind is not Kind.UNKNOWN)
    dropped_counts = _dropped_per_book(result)
    rows = [_book_row(b, dropped_counts.get(b.book_key, 0)) for b in books]

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if not rows:
        print("no books found")
        return 0

    title_width = min(max(len(str(r["title"])) for r in rows), 48)
    header = f"{'TITLE':<{title_width}}  {'HIGHLIGHTS':>10}  {'NOTES':>5}  {'DUPES':>5}"
    print(header)
    for r in rows:
        title = str(r["title"])
        if len(title) > title_width:
            title = title[: title_width - 1] + "…"
        print(
            f"{title:<{title_width}}  {r['highlights']:>10}  "
            f"{r['notes']:>5}  {r['duplicates_removed']:>5}"
        )
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    parsed, result = _load(args.clippings, args.no_dedupe, args.overlap_ratio)

    def count(kind: Kind, items: List[Clipping]) -> int:
        return sum(1 for c in items if c.kind is kind)

    books = group_books(c for c in result.kept if c.kind is not Kind.UNKNOWN)
    reasons: Dict[str, int] = {}
    for d in result.dropped:
        reasons[d.reason.value] = reasons.get(d.reason.value, 0) + 1

    stats = {
        "entries": parsed.entry_count,
        "books": len(books),
        "highlights": count(Kind.HIGHLIGHT, result.kept),
        "notes": count(Kind.NOTE, result.kept),
        "bookmarks": count(Kind.BOOKMARK, result.kept),
        "article_clips": count(Kind.CLIP, result.kept),
        "unrecognized": count(Kind.UNKNOWN, result.kept),
        "duplicates_removed": result.removed_count,
        "duplicates_by_reason": reasons,
        "warnings": len(parsed.warnings),
    }

    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0

    _print_warnings(parsed, sys.stderr)
    print(f"entries             {stats['entries']}")
    print(f"books               {stats['books']}")
    print(f"highlights          {stats['highlights']}")
    print(f"notes               {stats['notes']}")
    print(f"bookmarks           {stats['bookmarks']}")
    if stats["article_clips"]:
        print(f"article clips       {stats['article_clips']}")
    if stats["unrecognized"]:
        print(f"unrecognized        {stats['unrecognized']}")
    print(f"duplicates removed  {stats['duplicates_removed']}")
    for reason, n in sorted(reasons.items()):
        print(f"  {reason:<17} {n}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2

    handlers = {"export": _cmd_export, "list": _cmd_list, "stats": _cmd_stats}
    try:
        return handlers[args.command](args)
    except ClipshelfError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
