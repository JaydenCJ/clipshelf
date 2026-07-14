"""Rendering tests: slugs, book grouping, note attachment, Markdown shape.

Rendering must be deterministic — same clippings, byte-identical output —
so several tests assert on whole documents.
"""

from datetime import datetime

from clipshelf import (
    Clipping,
    Kind,
    Location,
    RenderOptions,
    group_books,
    render_book,
    slugify,
    unique_slugs,
)
from clipshelf.render import attach_notes


def clip(kind, text, start=None, end=None, added=None, index=0,
         title="How to Read a Book", author="Mortimer J. Adler", page=None):
    loc = Location(start, end if end is not None else start) if start is not None else None
    return Clipping(title=title, author=author, kind=kind, text=text,
                    location=loc, page=page, added=added, source_index=index)


# --- slugify ---------------------------------------------------------------


def test_slugify_ascii_unicode_and_punctuation():
    assert slugify("How to Read a Book") == "how-to-read-a-book"
    assert slugify("C++ / Rust: A Love Story?!") == "c-rust-a-love-story"
    assert slugify("Cien años de soledad") == "cien-años-de-soledad"
    assert slugify("こころ") == "こころ"


def test_slugify_empty_and_overlong_titles():
    assert slugify("???") == "untitled"
    long_title = "word " * 60
    assert len(slugify(long_title)) <= 80
    assert not slugify(long_title).endswith("-")


def test_unique_slugs_number_collisions_in_first_appearance_order():
    books = group_books([
        clip(Kind.HIGHLIGHT, "a", 1, 2, title="1984", author="George Orwell"),
        clip(Kind.HIGHLIGHT, "b", 1, 2, title="1984", author="Annotated Edition", index=1),
    ])
    slugs = unique_slugs(books)
    assert sorted(slugs.values()) == ["1984", "1984-2"]


# --- group_books -------------------------------------------------------------


def test_group_books_merges_case_variant_titles():
    a = clip(Kind.HIGHLIGHT, "a", 1, 2, title="Dune", author="Frank Herbert")
    b = clip(Kind.HIGHLIGHT, "b", 5, 6, title="DUNE", author="Frank Herbert", index=1)
    books = group_books([a, b])
    assert len(books) == 1
    assert len(books[0].clippings) == 2


def test_group_books_same_title_different_author_stay_separate():
    a = clip(Kind.HIGHLIGHT, "a", 1, 2, title="Collected Poems", author="A. Poet")
    b = clip(Kind.HIGHLIGHT, "b", 1, 2, title="Collected Poems", author="B. Poet", index=1)
    assert len(group_books([a, b])) == 2


def test_group_books_folds_authorless_entries_into_unambiguous_book():
    a = clip(Kind.HIGHLIGHT, "a", 1, 2, author=None)
    b = clip(Kind.HIGHLIGHT, "b", 5, 6, author="Mortimer J. Adler", index=1)
    (book,) = group_books([a, b])
    assert book.author == "Mortimer J. Adler"
    assert len(book.clippings) == 2


def test_group_books_authorless_stays_separate_when_ambiguous():
    # Two authored candidates share the title: folding would be a guess.
    a = clip(Kind.HIGHLIGHT, "a", 1, 2, title="Poems", author=None)
    b = clip(Kind.HIGHLIGHT, "b", 1, 2, title="Poems", author="A. Poet", index=1)
    c = clip(Kind.HIGHLIGHT, "c", 1, 2, title="Poems", author="B. Poet", index=2)
    assert len(group_books([a, b, c])) == 3


# --- attach_notes ------------------------------------------------------------


def test_attach_notes_inside_boundary_and_orphan():
    h = clip(Kind.HIGHLIGHT, "quoted text", 351, 354, index=0)
    inside = clip(Kind.NOTE, "my thought", 353, index=1)
    boundary = clip(Kind.NOTE, "boundary note", 354, index=2)  # Kindle anchors at the end
    orphan = clip(Kind.NOTE, "floating thought", 900, index=3)
    (book,) = group_books([h, inside, boundary, orphan])
    attached = attach_notes(book)
    assert attached[0] == [inside, boundary]
    assert attached[-1] == [orphan]


# --- render_book -------------------------------------------------------------


def test_render_full_document_is_byte_stable():
    h1 = clip(Kind.HIGHLIGHT, "Reading is active.", 351, 354, page="23",
              added=datetime(2024, 3, 5, 21, 13), index=0)
    n1 = clip(Kind.NOTE, "the core idea", 353, index=1)
    h2 = clip(Kind.HIGHLIGHT, "Find the skeleton.", 622, 624, page="41",
              added=datetime(2024, 3, 6, 8, 3), index=2)
    (book,) = group_books([h1, n1, h2])
    expected = (
        "# How to Read a Book\n"
        "\n"
        "*Mortimer J. Adler*\n"
        "\n"
        "2 highlights · 1 note\n"
        "\n"
        "## Highlights\n"
        "\n"
        "> Reading is active.\n"
        "\n"
        "<sub>location 351-354 · page 23 · 2024-03-05 21:13</sub>\n"
        "\n"
        "**Note:** the core idea\n"
        "\n"
        "> Find the skeleton.\n"
        "\n"
        "<sub>location 622-624 · page 41 · 2024-03-06 08:03</sub>\n"
    )
    assert render_book(book) == expected
    assert render_book(book) == render_book(book)  # deterministic


def test_render_orders_highlights_by_location_not_file_order():
    late = clip(Kind.HIGHLIGHT, "chapter nine", 900, 901, index=0)
    early = clip(Kind.HIGHLIGHT, "chapter one", 100, 101, index=1)
    (book,) = group_books([late, early])
    out = render_book(book)
    assert out.index("chapter one") < out.index("chapter nine")


def test_render_multiline_highlight_becomes_multiline_blockquote():
    h = clip(Kind.HIGHLIGHT, "line one\nline two", 10, 12)
    (book,) = group_books([h])
    out = render_book(book)
    assert "> line one\n> line two" in out


def test_render_summary_counts_and_plurals():
    h = clip(Kind.HIGHLIGHT, "text", 1, 2)
    (book,) = group_books([h])
    assert "1 highlight (1 duplicate removed)" in render_book(book, duplicates_removed=1)
    assert "(3 duplicates removed)" in render_book(book, duplicates_removed=3)


def test_render_empty_highlight_husks_are_dropped():
    husk = clip(Kind.HIGHLIGHT, "   ", 1, 2, index=0)
    real = clip(Kind.HIGHLIGHT, "actual words", 5, 6, index=1)
    (book,) = group_books([husk, real])
    out = render_book(book)
    assert "1 highlight" in out
    assert ">   " not in out


def test_render_bookmarks_only_when_opted_in():
    h = clip(Kind.HIGHLIGHT, "text", 1, 2, index=0)
    b = clip(Kind.BOOKMARK, "", 703, index=1)
    (book,) = group_books([h, b])
    assert "Bookmarks" not in render_book(book)
    out = render_book(book, RenderOptions(include_bookmarks=True))
    assert "## Bookmarks" in out
    assert "location 703" in out


def test_render_options_can_hide_location_and_date():
    h = clip(Kind.HIGHLIGHT, "text", 351, 354, added=datetime(2024, 3, 5, 21, 13))
    (book,) = group_books([h])
    out = render_book(book, RenderOptions(include_location=False, include_date=False))
    assert "location" not in out
    assert "2024" not in out


def test_render_orphan_notes_and_layout_edges():
    # No author line, orphan notes get a section, no double blank lines.
    h = clip(Kind.HIGHLIGHT, "quoted", 100, 105, title="Pamphlet", author=None, index=0)
    n = clip(Kind.NOTE, "standalone reflection", 900, title="Pamphlet", author=None, index=1)
    (book,) = group_books([h, n])
    out = render_book(book)
    assert "## Notes" in out
    assert "standalone reflection" in out
    assert "*" not in out.split("\n")[2]  # no author italics line
    assert "\n\n\n" not in out
