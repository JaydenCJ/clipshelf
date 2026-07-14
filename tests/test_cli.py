"""CLI tests: every subcommand, exit codes, flags, JSON output.

All tests call clipshelf.cli.main() in-process with capsys — no
subprocesses, no network, no installed console script required.
"""

import json

import pytest

from clipshelf import __version__
from clipshelf.cli import main

from conftest import entry, highlight_entry


@pytest.fixture
def clippings_file(tmp_path):
    """A small realistic file: one revision pair, a note, two books."""
    raw = (
        highlight_entry(
            loc="351-352",
            added="Tuesday, March 5, 2024 9:12:45 PM",
            text="Reading a book should be a conversation.",
        )
        + highlight_entry(
            loc="351-354",
            added="Tuesday, March 5, 2024 9:13:02 PM",
            text="Reading a book should be a conversation. He knows more.",
        )
        + entry(
            "How to Read a Book (Mortimer J. Adler)",
            "- Your Note on Location 353 | Added on Tuesday, March 5, 2024 9:13:40 PM",
            "reading is active",
        )
        + entry(
            "Meditations (Marcus Aurelius)",
            "- Your Highlight on Location 1480-1482 | Added on Monday, February 5, 2024 10:02:33 PM",
            "Waste no more time arguing what a good man should be. Be one.",
        )
    )
    path = tmp_path / "My Clippings.txt"
    path.write_text(raw, encoding="utf-8-sig")
    return path


def test_version_flag_and_bare_invocation(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"clipshelf {__version__}"
    assert main([]) == 2  # no subcommand: help + exit 2
    assert "export" in capsys.readouterr().out


def test_export_writes_one_file_per_book(clippings_file, tmp_path, capsys):
    out_dir = tmp_path / "notes"
    assert main(["export", str(clippings_file), "-o", str(out_dir)]) == 0
    files = sorted(p.name for p in out_dir.glob("*.md"))
    assert files == ["how-to-read-a-book.md", "meditations.md"]
    out = capsys.readouterr().out
    assert "2 books" in out
    assert "1 duplicate removed" in out  # singular: no "1 duplicates" grammar slip


def test_export_dedupes_revision_and_keeps_final_text(clippings_file, tmp_path):
    out_dir = tmp_path / "notes"
    main(["export", str(clippings_file), "-o", str(out_dir)])
    doc = (out_dir / "how-to-read-a-book.md").read_text(encoding="utf-8")
    assert doc.count("Reading a book should be a conversation") == 1
    assert "He knows more." in doc  # the extended revision survived
    assert "**Note:** reading is active" in doc


def test_export_no_dedupe_keeps_both_revisions(clippings_file, tmp_path):
    out_dir = tmp_path / "raw"
    main(["export", str(clippings_file), "-o", str(out_dir), "--no-dedupe"])
    doc = (out_dir / "how-to-read-a-book.md").read_text(encoding="utf-8")
    assert doc.count("Reading a book should be a conversation") == 2


def test_export_book_filter_match_and_miss(clippings_file, tmp_path, capsys):
    out_dir = tmp_path / "notes"
    assert main(["export", str(clippings_file), "-o", str(out_dir), "--book", "meditations"]) == 0
    assert [p.name for p in out_dir.glob("*.md")] == ["meditations.md"]
    # The summary must describe only the exported books: the fixture's one
    # duplicate lives in the *other* book, so the filtered run reports zero.
    assert "1 book, 1 highlight, 0 notes, 0 duplicates removed" in capsys.readouterr().out
    assert main(["export", str(clippings_file), "-o", str(tmp_path / "x"), "--book", "moby dick"]) == 1
    assert "no book title contains" in capsys.readouterr().err


def test_export_dry_run_writes_nothing(clippings_file, tmp_path, capsys):
    out_dir = tmp_path / "notes"
    assert main(["export", str(clippings_file), "-o", str(out_dir), "--dry-run"]) == 0
    assert not out_dir.exists()
    assert "would write" in capsys.readouterr().out


def test_export_no_location_and_no_date_flags(clippings_file, tmp_path):
    out_dir = tmp_path / "bare"
    main(["export", str(clippings_file), "-o", str(out_dir), "--no-location", "--no-date"])
    doc = (out_dir / "meditations.md").read_text(encoding="utf-8")
    assert "location" not in doc
    assert "2024" not in doc


def test_export_missing_file_exits_1(tmp_path, capsys):
    assert main(["export", str(tmp_path / "nope.txt")]) == 1
    assert "error:" in capsys.readouterr().err


def test_list_table_and_json(clippings_file, capsys):
    assert main(["list", str(clippings_file)]) == 0
    out = capsys.readouterr().out
    assert "TITLE" in out
    assert "How to Read a Book" in out
    assert "Meditations" in out
    assert main(["list", str(clippings_file), "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    by_title = {r["title"]: r for r in rows}
    assert by_title["How to Read a Book"]["highlights"] == 1
    assert by_title["How to Read a Book"]["notes"] == 1
    assert by_title["How to Read a Book"]["duplicates_removed"] == 1
    assert by_title["Meditations"]["duplicates_removed"] == 0


def test_stats_text_and_json(clippings_file, capsys):
    assert main(["stats", str(clippings_file)]) == 0
    out = capsys.readouterr().out
    assert "entries             4" in out
    assert "books               2" in out
    assert "duplicates removed  1" in out
    assert main(["stats", str(clippings_file), "--json"]) == 0
    stats = json.loads(capsys.readouterr().out)
    assert stats["entries"] == 4
    assert stats["highlights"] == 2
    assert stats["notes"] == 1
    assert stats["duplicates_removed"] == 1
    assert stats["duplicates_by_reason"] == {"contained": 1}


def test_stats_no_dedupe_reports_zero_removed(clippings_file, capsys):
    assert main(["stats", str(clippings_file), "--no-dedupe", "--json"]) == 0
    stats = json.loads(capsys.readouterr().out)
    assert stats["duplicates_removed"] == 0
    assert stats["highlights"] == 3


def test_overlap_ratio_flag_reaches_the_engine(tmp_path, capsys):
    # Two highlights sharing a short run: merged at ratio 0.1, kept at 0.99.
    raw = highlight_entry(
        loc="100-110", text="alpha beta gamma delta",
        added="Monday, January 1, 2024 10:00:00 AM",
    ) + highlight_entry(
        loc="105-120", text="gamma delta epsilon zeta eta theta iota kappa",
        added="Monday, January 1, 2024 10:05:00 AM",
    )
    path = tmp_path / "c.txt"
    path.write_text(raw, encoding="utf-8")

    main(["stats", str(path), "--json", "--overlap-ratio", "0.1"])
    merged = json.loads(capsys.readouterr().out)
    main(["stats", str(path), "--json", "--overlap-ratio", "0.99"])
    kept = json.loads(capsys.readouterr().out)
    assert merged["duplicates_removed"] == 1
    assert kept["duplicates_removed"] == 0


def test_overlap_ratio_out_of_range_is_rejected(clippings_file, capsys):
    # A ratio above 1.0 can never be satisfied and below 0.0 always is;
    # both are user error, so argparse must refuse with a clear message
    # rather than silently doing something surprising.
    with pytest.raises(SystemExit) as exc:
        main(["stats", str(clippings_file), "--overlap-ratio", "1.5"])
    assert exc.value.code == 2
    assert "between 0.0 and 1.0" in capsys.readouterr().err


def test_warnings_go_to_stderr_not_stdout(tmp_path, capsys):
    raw = "Stray line without metadata\r\n==========\r\n" + highlight_entry()
    path = tmp_path / "c.txt"
    path.write_text(raw, encoding="utf-8")
    assert main(["stats", str(path)]) == 0
    captured = capsys.readouterr()
    assert "warning:" in captured.err
    assert "warning:" not in captured.out


def test_export_unicode_titles_produce_unicode_filenames(tmp_path):
    raw = entry(
        "こころ (夏目漱石)",
        "- 位置No. 152-155のハイライト | 追加日： 2024年4月2日火曜日 22:15:08",
        "私はその人を常に先生と呼んでいた。",
    )
    path = tmp_path / "c.txt"
    path.write_text(raw, encoding="utf-8")
    out_dir = tmp_path / "notes"
    assert main(["export", str(path), "-o", str(out_dir)]) == 0
    assert (out_dir / "こころ.md").exists()
