"""End-to-end tests against the shipped example file.

The examples/ clippings file is the one the README quickstart uses; these
tests pin its behavior so docs, examples, and code cannot drift apart.
"""

import json

from clipshelf import Kind, dedupe, group_books, parse_file, render_book
from clipshelf.cli import main


def test_example_file_parses_cleanly_and_dedupes_three_entries(examples_clippings):
    parsed = parse_file(examples_clippings)
    assert parsed.entry_count == 11
    assert parsed.warnings == []
    result = dedupe(parsed.clippings)
    assert result.removed_count == 3
    reasons = sorted(d.reason.value for d in result.dropped)
    assert reasons == ["contained", "contained", "identical"]


def test_example_file_books_and_kinds(examples_clippings):
    parsed = parse_file(examples_clippings)
    result = dedupe(parsed.clippings)
    books = group_books(result.kept)
    assert len(books) == 4
    titles = {b.title for b in books}
    assert titles == {
        "How to Read a Book",
        "Meditations",
        "Cien años de soledad",
        "こころ",
    }
    kinds = {c.kind for c in result.kept}
    assert Kind.HIGHLIGHT in kinds and Kind.NOTE in kinds and Kind.BOOKMARK in kinds


def test_example_meditations_keeps_extended_revision(examples_clippings):
    parsed = parse_file(examples_clippings)
    result = dedupe(parsed.clippings)
    books = {b.title: b for b in group_books(result.kept)}
    texts = [h.text for h in books["Meditations"].highlights]
    # The pre-2011 abbreviated entry (Loc. 210-12) merged into the later,
    # longer revision at Location 209-213.
    assert any(t.startswith("Remember:") for t in texts)
    assert not any(t.startswith("You have power") for t in texts)


def test_example_note_attaches_under_its_highlight(examples_clippings):
    parsed = parse_file(examples_clippings)
    result = dedupe(parsed.clippings)
    books = {b.title: b for b in group_books(result.kept)}
    doc = render_book(books["How to Read a Book"])
    quote_pos = doc.index("Presumably he knows more")
    note_pos = doc.index("**Note:** The core idea")
    assert quote_pos < note_pos


def test_example_full_pipeline_via_cli_is_deterministic(examples_clippings, tmp_path, capsys):
    out_a, out_b = tmp_path / "a", tmp_path / "b"
    assert main(["export", str(examples_clippings), "-o", str(out_a)]) == 0
    assert main(["export", str(examples_clippings), "-o", str(out_b)]) == 0
    capsys.readouterr()
    files_a = sorted(p.name for p in out_a.glob("*.md"))
    files_b = sorted(p.name for p in out_b.glob("*.md"))
    assert files_a == files_b == [
        "cien-años-de-soledad.md",
        "how-to-read-a-book.md",
        "meditations.md",
        "こころ.md",
    ]
    for name in files_a:
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes()


def test_example_stats_json_snapshot(examples_clippings, capsys):
    assert main(["stats", str(examples_clippings), "--json"]) == 0
    stats = json.loads(capsys.readouterr().out)
    assert stats == {
        "entries": 11,
        "books": 4,
        "highlights": 6,
        "notes": 1,
        "bookmarks": 1,
        "article_clips": 0,
        "unrecognized": 0,
        "duplicates_removed": 3,
        "duplicates_by_reason": {"contained": 2, "identical": 1},
        "warnings": 0,
    }
