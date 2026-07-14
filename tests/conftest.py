"""Shared fixtures and entry-building helpers for the clipshelf tests."""

import sys
from pathlib import Path

import pytest

# Run the tests straight from a checkout, no install needed.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

SEPARATOR = "==========\r\n"


def entry(title: str, meta: str, text: str = "") -> str:
    """Build one raw My Clippings.txt entry, CRLF endings like the device."""
    return f"{title}\r\n{meta}\r\n\r\n{text}\r\n{SEPARATOR}"


def highlight_entry(
    title: str = "How to Read a Book (Mortimer J. Adler)",
    loc: str = "351-352",
    page: str = "23",
    added: str = "Tuesday, March 5, 2024 9:12:45 PM",
    text: str = "Reading a book should be a conversation between you and the author.",
) -> str:
    meta = f"- Your Highlight on page {page} | Location {loc} | Added on {added}"
    return entry(title, meta, text)


@pytest.fixture
def examples_clippings() -> Path:
    """Path to the shipped example clippings file."""
    return Path(__file__).resolve().parent.parent / "examples" / "My Clippings.txt"
