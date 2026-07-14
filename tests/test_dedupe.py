"""Dedupe engine tests: the reason clipshelf exists.

Every revision pattern Kindle actually produces is covered: extend, trim,
move-both-edges, exact re-sync duplicates, plus the negative cases where
two highlights merely touch and must NOT merge.
"""

from datetime import datetime

from clipshelf import Clipping, Kind, Location, Reason, dedupe, normalize
from clipshelf.dedupe import classify


def hl(text, start, end, added=None, index=0, title="Book", author="Author"):
    return Clipping(
        title=title,
        author=author,
        kind=Kind.HIGHLIGHT,
        text=text,
        location=Location(start, end),
        added=added,
        source_index=index,
    )


def note(text, loc, index=0, title="Book", author="Author"):
    return Clipping(
        title=title,
        author=author,
        kind=Kind.NOTE,
        text=text,
        location=Location(loc, loc),
        source_index=index,
    )


# --- normalize -----------------------------------------------------------


def test_normalize_whitespace_case_and_nfkc():
    assert normalize("The  Quick\n\nBrown  FOX") == "the quick brown fox"
    # NFKC + casefold makes firmware glyph swaps invisible to dedupe.
    assert normalize("ﬁnal") == normalize("final")  # ligature fi


# --- classify ------------------------------------------------------------


def test_identical_text_and_location_is_identical():
    a = hl("Same words.", 100, 105)
    b = hl("Same words.", 100, 105, index=1)
    assert classify(a, b) is Reason.IDENTICAL


def test_extended_highlight_is_contained():
    a = hl("Reading a book should be a conversation.", 351, 352)
    b = hl(
        "Reading a book should be a conversation. Presumably he knows more.",
        351,
        354,
        index=1,
    )
    assert classify(a, b) is Reason.CONTAINED


def test_moved_both_edges_is_revised():
    # Overlapping ranges, neither text contains the other, but the shared
    # middle run dominates: the classic "nudged both ends" revision.
    a = hl("power over your mind - not outside events.", 210, 212)
    b = hl("You have power over your mind - not outside events, always", 209, 213, index=1)
    assert classify(a, b) is Reason.REVISED


def test_distinct_highlights_never_merge():
    # The same sentence highlighted in two chapters is two highlights.
    assert classify(hl("So it goes.", 100, 101), hl("So it goes.", 900, 901, index=1)) is None
    # Adjacent highlights can share a boundary location number.
    a = hl("The first idea ends here.", 100, 110)
    b = hl("A totally different second idea begins.", 110, 120, index=1)
    assert classify(a, b) is None


def test_overlap_ratio_threshold_is_respected():
    a = hl("alpha beta gamma delta", 100, 110)
    b = hl("gamma delta epsilon zeta eta theta iota kappa", 105, 120, index=1)
    # Shared run "gamma delta" is short relative to the shorter text.
    assert classify(a, b, overlap_ratio=0.9) is None
    assert classify(a, b, overlap_ratio=0.3) is Reason.REVISED


def test_missing_location_disables_merging():
    a = hl("Same words.", 1, 2)
    b = Clipping(title="Book", author="Author", kind=Kind.HIGHLIGHT, text="Same words.")
    assert classify(a, b) is None


# --- dedupe: survivor choice ---------------------------------------------


def test_extension_keeps_the_longer_revision():
    short = hl("A conversation.", 351, 352, added=datetime(2024, 3, 5, 21, 12), index=0)
    long = hl("A conversation. He knows more.", 351, 354, added=datetime(2024, 3, 5, 21, 13), index=1)
    result = dedupe([short, long])
    assert result.kept == [long]
    assert result.dropped[0].clipping is short
    assert result.dropped[0].reason is Reason.CONTAINED


def test_later_trim_wins_over_length():
    # The user deliberately shrank the highlight afterwards: honor it.
    long = hl("A conversation. He knows more.", 351, 354, added=datetime(2024, 3, 5, 21, 12), index=0)
    trimmed = hl("A conversation.", 351, 352, added=datetime(2024, 3, 5, 21, 15), index=1)
    result = dedupe([long, trimmed])
    assert result.kept == [trimmed]


def test_containment_without_timestamps_keeps_longer_text():
    # No clock evidence -> keep more of the user's words.
    long = hl("A conversation. He knows more.", 351, 354, index=0)
    short = hl("A conversation.", 351, 352, index=1)  # later in file but shorter
    result = dedupe([long, short])
    assert result.kept == [long]


def test_identical_duplicates_collapse_and_audit_trail_points_at_survivor():
    a = hl("Every book has a skeleton.", 622, 624, index=0)
    b = hl("Every book has a skeleton.", 622, 624, index=5)
    result = dedupe([a, b])
    assert len(result.kept) == 1
    assert result.removed_count == 1
    d = result.dropped[0]
    assert d.reason is Reason.IDENTICAL
    assert d.kept in result.kept
    assert d.clipping is not d.kept


def test_revision_chain_collapses_to_final_version():
    # Three successive extensions -> exactly one survivor, two dropped.
    v1 = hl("Reading a book", 351, 351, added=datetime(2024, 3, 5, 21, 10), index=0)
    v2 = hl("Reading a book should be", 351, 352, added=datetime(2024, 3, 5, 21, 11), index=1)
    v3 = hl("Reading a book should be a conversation.", 351, 354, added=datetime(2024, 3, 5, 21, 12), index=2)
    result = dedupe([v1, v2, v3])
    assert result.kept == [v3]
    assert result.removed_count == 2


def test_no_timestamps_falls_back_to_file_order():
    # Kindle appends: later in the file means later in time.
    a = hl("power over your mind - not outside events.", 210, 212, index=0)
    b = hl("have power over your mind - not outside events, and", 209, 213, index=1)
    result = dedupe([a, b])
    assert result.kept == [b]
    assert result.dropped[0].reason is Reason.REVISED


def test_same_text_different_books_is_not_a_duplicate():
    a = hl("To be or not to be.", 100, 101, title="Hamlet")
    b = hl("To be or not to be.", 100, 101, title="Anthology", index=1)
    result = dedupe([a, b])
    assert len(result.kept) == 2
    assert result.removed_count == 0


def test_kept_order_is_source_order_and_empty_input_is_fine():
    a = hl("first", 500, 501, index=0)
    b = hl("second", 100, 101, index=1)
    result = dedupe([a, b])
    assert [c.text for c in result.kept] == ["first", "second"]
    assert dedupe([]).kept == []


# --- dedupe: notes and bookmarks ------------------------------------------


def test_exact_duplicate_notes_collapse():
    a = note("my thought", 353, index=0)
    b = note("my thought", 353, index=1)
    result = dedupe([a, b])
    assert len(result.kept) == 1
    assert result.dropped[0].reason is Reason.IDENTICAL


def test_different_notes_at_same_location_both_survive():
    # Notes are the user's own words; never fuzzy-merge them.
    a = note("first reading: skeptical", 353, index=0)
    b = note("second reading: convinced", 353, index=1)
    result = dedupe([a, b])
    assert len(result.kept) == 2


def test_unknown_kind_passes_through_untouched():
    mystery = Clipping(title="Book", author=None, kind=Kind.UNKNOWN, text="???", source_index=0)
    twin = Clipping(title="Book", author=None, kind=Kind.UNKNOWN, text="???", source_index=1)
    result = dedupe([mystery, twin])
    assert len(result.kept) == 2  # dedupe never guesses on unreadable entries
