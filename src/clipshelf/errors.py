"""Exception types for clipshelf."""


class ClipshelfError(Exception):
    """Base class for all clipshelf errors."""


class ParseError(ClipshelfError):
    """Raised when a clippings file cannot be read at all.

    Individual malformed entries never raise: they become warnings on the
    ParseResult so one broken entry cannot hold years of highlights hostage.
    """
