"""Parser tests: entry splitting, title/author, metadata, robustness.

These cover the shapes a real My Clippings.txt accumulates over years:
BOM, CRLF, multi-line highlights, authorless titles, nested parentheses,
pre-2011 firmware metadata, and malformed entries that must degrade to
warnings instead of exceptions.
"""

import pytest

from clipshelf import Kind, ParseError, parse_file, parse_text
from clipshelf.parser import expand_abbreviated_end

from conftest import SEPARATOR, entry, highlight_entry


def test_single_highlight_parses_all_fields():
    result = parse_text(highlight_entry())
    assert result.warnings == []
    (c,) = result.clippings
    assert c.title == "How to Read a Book"
    assert c.author == "Mortimer J. Adler"
    assert c.kind is Kind.HIGHLIGHT
    assert (c.location.start, c.location.end) == (351, 352)
    assert c.page == "23"
    assert (c.added.year, c.added.month, c.added.day) == (2024, 3, 5)
    assert (c.added.hour, c.added.minute, c.added.second) == (21, 12, 45)
    assert c.text.startswith("Reading a book")


def test_bom_and_line_ending_variants_parse_identically():
    crlf = "﻿" + highlight_entry()  # UTF-8 BOM on the first title, CRLF body
    lf = highlight_entry().replace("\r\n", "\n")
    a = parse_text(crlf).clippings[0]
    b = parse_text(lf).clippings[0]
    assert a.title == b.title == "How to Read a Book"
    assert (a.text, a.location) == (b.text, b.location)


def test_multiple_entries_get_sequential_source_indexes():
    raw = highlight_entry(loc="10-12") + highlight_entry(loc="20-22") + highlight_entry(loc="30-32")
    result = parse_text(raw)
    assert [c.source_index for c in result.clippings] == [0, 1, 2]


def test_title_without_author():
    raw = entry("Standalone Pamphlet", "- Your Highlight on Location 5-6 | Added on Monday, January 1, 2024 10:00:00 AM", "text")
    (c,) = parse_text(raw).clippings
    assert c.title == "Standalone Pamphlet"
    assert c.author is None


def test_nested_parentheses_keep_inner_group_in_title():
    # Only the LAST parenthesized group is the author.
    raw = entry(
        "Ficciones (Spanish Edition) (Jorge Luis Borges)",
        "- Your Highlight on Location 100-101 | Added on Monday, January 1, 2024 10:00:00 AM",
        "text",
    )
    (c,) = parse_text(raw).clippings
    assert c.title == "Ficciones (Spanish Edition)"
    assert c.author == "Jorge Luis Borges"


def test_note_and_bookmark_entries():
    raw = entry(
        "A Book (Author)",
        "- Your Note on Location 353 | Added on Tuesday, March 5, 2024 9:13:40 PM",
        "my thought",
    ) + entry(
        "A Book (Author)",
        "- Your Bookmark on Location 703 | Added on Wednesday, March 6, 2024 8:10:00 AM",
    )
    note, bookmark = parse_text(raw).clippings
    assert note.kind is Kind.NOTE
    assert (note.location.start, note.location.end) == (353, 353)  # single point
    assert bookmark.kind is Kind.BOOKMARK
    assert bookmark.text == ""


def test_multiline_highlight_text_is_preserved():
    text = "First paragraph.\r\n\r\nSecond paragraph, after a blank line."
    raw = entry("A Book (Author)", "- Your Highlight on Location 1-2 | Added on Monday, January 1, 2024 10:00:00 AM", text)
    (c,) = parse_text(raw).clippings
    assert c.text == "First paragraph.\n\nSecond paragraph, after a blank line."


def test_pre_2011_firmware_metadata():
    # Old firmware: no "Your", "Page" capitalized, "Loc." abbreviated,
    # trailing comma before the time.
    raw = entry(
        "Meditations (Marcus Aurelius)",
        "- Highlight on Page ix | Loc. 210-12 | Added on Sunday, February 04, 2024, 07:45 AM",
        "You have power over your mind.",
    )
    (c,) = parse_text(raw).clippings
    assert c.kind is Kind.HIGHLIGHT
    assert c.page == "ix"
    assert (c.location.start, c.location.end) == (210, 212)
    assert (c.added.hour, c.added.minute) == (7, 45)
    # The page-less variant drops "on" entirely ("- Highlight Loc. ...");
    # it must not degrade to UNKNOWN and vanish from the export.
    pageless = entry(
        "Meditations (Marcus Aurelius)",
        "- Highlight Loc. 1085-86 | Added on Wednesday, June 09, 2010, 11:12 PM",
        "Waste no more time arguing about what a good man should be.",
    )
    result = parse_text(pageless)
    assert result.warnings == []
    (p,) = result.clippings
    assert p.kind is Kind.HIGHLIGHT
    assert p.page is None
    assert (p.location.start, p.location.end) == (1085, 1086)


def test_expand_abbreviated_end():
    # "Loc. 351-52" means 351-352: the end borrows the start's prefix.
    assert expand_abbreviated_end(351, 52) == 352
    assert expand_abbreviated_end(1480, 82) == 1482
    assert expand_abbreviated_end(210, 12) == 212
    # Normal ranges pass through untouched.
    assert expand_abbreviated_end(351, 354) == 354
    assert expand_abbreviated_end(5, 5) == 5


def test_highlight_without_page_still_parses():
    raw = entry(
        "A Book (Author)",
        "- Your Highlight on Location 1480-1482 | Added on Monday, February 5, 2024 10:02:33 PM",
        "text",
    )
    (c,) = parse_text(raw).clippings
    assert c.page is None
    assert (c.location.start, c.location.end) == (1480, 1482)


def test_malformed_entry_becomes_warning_not_exception():
    good = highlight_entry()
    broken = "Just a stray line with no metadata\r\n" + SEPARATOR
    result = parse_text(broken + good)
    assert len(result.clippings) == 1  # the good one survives
    assert len(result.warnings) == 1
    assert "no metadata line" in result.warnings[0]


def test_unrecognized_metadata_is_kept_as_unknown_kind():
    raw = entry("A Book (Author)", "- Something the parser has never seen | xyzzy", "orphan text")
    result = parse_text(raw)
    (c,) = result.clippings
    assert c.kind is Kind.UNKNOWN
    assert c.text == "orphan text"
    assert any("unrecognized metadata" in w for w in result.warnings)


def test_edge_file_shapes():
    # Empty file: nothing, quietly.
    assert parse_text("").clippings == []
    # Missing trailing separator: the last entry still counts.
    assert len(parse_text(highlight_entry().replace(SEPARATOR, "")).clippings) == 1
    # Separator with trailing whitespace still splits.
    raw = highlight_entry().replace(SEPARATOR, "==========   \r\n") + highlight_entry(loc="500-501")
    assert len(parse_text(raw).clippings) == 2


def test_parse_file_handles_kindle_encodings(tmp_path):
    for name, encoding in [("sig.txt", "utf-8-sig"), ("u16.txt", "utf-16")]:
        path = tmp_path / name
        path.write_bytes(highlight_entry().encode(encoding))
        assert parse_file(path).clippings[0].title == "How to Read a Book"


def test_parse_file_missing_raises_parse_error(tmp_path):
    with pytest.raises(ParseError):
        parse_file(tmp_path / "does-not-exist.txt")


def test_unparseable_date_keeps_clipping_with_none_added():
    raw = entry(
        "A Book (Author)",
        "- Your Highlight on Location 1-2 | Added on the thirty-second of Junetober",
        "text survives bad dates",
    )
    (c,) = parse_text(raw).clippings
    assert c.added is None
    assert c.text == "text survives bad dates"
