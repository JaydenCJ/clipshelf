"""Model invariants and the date parser's edge cases."""

from datetime import datetime

import pytest

from clipshelf import Clipping, Kind, Location
from clipshelf.dates import parse_added


# --- Location ----------------------------------------------------------------


def test_location_str_and_span():
    assert str(Location(351, 354)) == "351-354"
    assert str(Location(353, 353)) == "353"
    assert Location(351, 354).span == 4
    assert Location(353, 353).span == 1


def test_location_overlap_containment_and_boundaries():
    a, b = Location(100, 110), Location(105, 120)
    assert a.overlaps(b) and b.overlaps(a)  # symmetric
    assert Location(100, 110).overlaps(Location(110, 120))  # boundary touch
    assert not Location(100, 110).overlaps(Location(111, 120))
    assert Location(100, 110).contains(Location(100, 110))  # endpoints inclusive
    assert Location(100, 110).contains(Location(105, 105))
    assert not Location(100, 110).contains(Location(105, 111))


def test_location_rejects_reversed_range():
    with pytest.raises(ValueError):
        Location(10, 5)


# --- Clipping keys -------------------------------------------------------------


def test_book_key_ignores_case_and_padding():
    a = Clipping(title=" Dune ", author="Frank Herbert", kind=Kind.HIGHLIGHT, text="x")
    b = Clipping(title="dune", author="FRANK HERBERT", kind=Kind.HIGHLIGHT, text="y")
    assert a.book_key == b.book_key


def test_sort_key_without_location_sorts_after_located_entries():
    located = Clipping(title="T", author=None, kind=Kind.HIGHLIGHT, text="x",
                       location=Location(999999, 999999))
    floating = Clipping(title="T", author=None, kind=Kind.HIGHLIGHT, text="y")
    assert located.sort_key < floating.sort_key


# --- parse_added ---------------------------------------------------------------


def test_english_date_shapes():
    # US current firmware, PM.
    assert parse_added("Tuesday, March 5, 2024 9:12:45 PM") == datetime(2024, 3, 5, 21, 12, 45)
    # UK order: day before month.
    assert parse_added("Tuesday, 5 March 2024 21:12:45") == datetime(2024, 3, 5, 21, 12, 45)
    # Pre-2011: zero-padded day, trailing comma, no seconds.
    assert parse_added("Sunday, February 04, 2024, 07:45 AM") == datetime(2024, 2, 4, 7, 45, 0)
    # No time at all -> midnight.
    assert parse_added("Tuesday, March 5, 2024") == datetime(2024, 3, 5, 0, 0, 0)


def test_twelve_hour_clock_noon_and_midnight():
    assert parse_added("Monday, January 1, 2024 12:05:00 AM") == datetime(2024, 1, 1, 0, 5, 0)
    assert parse_added("Monday, January 1, 2024 12:05:00 PM") == datetime(2024, 1, 1, 12, 5, 0)


def test_non_english_date_shapes():
    # German dotted day; "Dienstag" must not read as a month or day.
    assert parse_added("Dienstag, 5. März 2024 09:12:45") == datetime(2024, 3, 5, 9, 12, 45)
    # CJK explicit-unit date with an afternoon marker.
    assert parse_added("2024年3月5日星期二 下午9:12:45") == datetime(2024, 3, 5, 21, 12, 45)


def test_numeric_fallback_dates():
    assert parse_added("2024-03-05 21:12:45") == datetime(2024, 3, 5, 21, 12, 45)
    assert parse_added("05/03/2024 21:12") == datetime(2024, 3, 5, 21, 12, 0)
    # 03/25/2024 cannot be d/m/y (month 25); read it as m/d/y.
    assert parse_added("03/25/2024 10:00") == datetime(2024, 3, 25, 10, 0, 0)


def test_unparseable_dates_return_none():
    assert parse_added("the thirty-second of Junetober") is None
    assert parse_added("") is None
    # A month name + year but an impossible calendar day.
    assert parse_added("Friday, February 30, 2024 10:00:00 AM") is None
