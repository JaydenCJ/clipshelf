"""clipshelf — Kindle 'My Clippings.txt' to per-book Markdown, offline.

Public API:

    parse_file / parse_text  -> ParseResult (clippings + warnings)
    dedupe                   -> DedupeResult (kept + audit trail)
    group_books, render_book -> Markdown output
    slugify, unique_slugs    -> stable file naming

The CLI in clipshelf.cli is a thin layer over exactly these functions.
"""

from .dedupe import DEFAULT_OVERLAP_RATIO, DedupeResult, Dropped, Reason, dedupe, normalize
from .errors import ClipshelfError, ParseError
from .model import Book, Clipping, Kind, Location
from .parser import ParseResult, parse_file, parse_text
from .render import RenderOptions, group_books, render_book, slugify, unique_slugs

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "Book",
    "Clipping",
    "ClipshelfError",
    "DEFAULT_OVERLAP_RATIO",
    "DedupeResult",
    "Dropped",
    "Kind",
    "Location",
    "ParseError",
    "ParseResult",
    "Reason",
    "RenderOptions",
    "dedupe",
    "group_books",
    "normalize",
    "parse_file",
    "parse_text",
    "render_book",
    "slugify",
    "unique_slugs",
]
