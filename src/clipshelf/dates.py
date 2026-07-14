"""Best-effort parsing of the "Added on ..." timestamp.

Kindle formats the timestamp with the device locale, and the exact shape
has changed across firmware generations:

    Added on Tuesday, March 5, 2024 9:12:45 AM        (US, current)
    Added on Tuesday, 5 March 2024 21:12:45           (UK, current)
    Added on Tuesday, March 05, 2024, 09:12 AM        (pre-2011)
    Añadido el martes, 5 de marzo de 2024 9:12:45
    Hinzugefügt am Dienstag, 5. März 2024 09:12:45
    添加于 2024年3月5日星期二 上午9:12:45
    追加日: 2024年3月5日火曜日 9:12:45

Rather than one strptime format per shape, this module extracts the pieces
(year, month by name or CJK marker, day, time, am/pm) independently. A
timestamp that cannot be understood yields None — the caller keeps the
clipping and falls back to file order, because losing a highlight over a
weird date would be the wrong trade.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from .locales import MONTH_NAMES, PM_MARKERS

# 2024年3月5日 — CJK dates carry explicit unit markers, easiest first.
_CJK_DATE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")

# "5 de marzo de 2024", "5. März 2024", "5 mars 2024", "March 5, 2024",
# "March 05, 2024" — a day and a month name in either order plus a year.
_MONTH_NAME = re.compile(r"[^\W\d_]+", re.UNICODE)
_DAY = re.compile(r"(?<!\d)(\d{1,2})(?!\d)")
_YEAR = re.compile(r"(?<!\d)(\d{4})(?!\d)")

# Numeric fallback: 05/03/2024 or 2024-03-05 (some third-party tools
# rewrite clippings files this way).
_NUMERIC_DMY = re.compile(r"(?<!\d)(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?!\d)")
_NUMERIC_YMD = re.compile(r"(?<!\d)(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})(?!\d)")

_TIME = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?(?!\d)")


def _find_month_by_name(text: str) -> Optional[int]:
    for word in _MONTH_NAME.findall(text):
        month = MONTH_NAMES.get(word.casefold())
        if month is not None:
            return month
    return None


def _find_pm_marker(text: str) -> Optional[bool]:
    folded = text.casefold()
    for marker, is_pm in PM_MARKERS.items():
        if marker in ("am", "pm"):
            # Bare am/pm must stand alone ("9:12:45 AM"), otherwise the
            # "am" inside German "Hinzugefügt am" would flip every entry.
            if re.search(rf"\b{marker}\b", folded):
                return is_pm
        elif marker in folded:
            return is_pm
    return None


def _extract_time(text: str) -> tuple:
    """Return (hour, minute, second) with am/pm applied, or midnight."""
    m = _TIME.search(text)
    if not m:
        return (0, 0, 0)
    hour = int(m.group(1))
    minute = int(m.group(2))
    second = int(m.group(3) or 0)
    if hour > 23 or minute > 59 or second > 59:
        return (0, 0, 0)
    is_pm = _find_pm_marker(text)
    if is_pm is True and hour < 12:
        hour += 12
    elif is_pm is False and hour == 12:
        hour = 0
    return (hour, minute, second)


def _build(year: int, month: int, day: int, text: str) -> Optional[datetime]:
    hour, minute, second = _extract_time(text)
    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None  # e.g. February 30 from a corrupted line


def parse_added(text: str) -> Optional[datetime]:
    """Parse the date portion of a metadata line; None when hopeless."""
    text = text.strip()
    if not text:
        return None

    # 1. CJK explicit-unit dates.
    m = _CJK_DATE.search(text)
    if m:
        return _build(int(m.group(1)), int(m.group(2)), int(m.group(3)), text)

    # 2. Month written as a name in any supported language.
    month = _find_month_by_name(text)
    year_match = _YEAR.search(text)
    if month is not None and year_match is not None:
        year = int(year_match.group(1))
        # The day is the first standalone 1-2 digit number before the year;
        # this skips weekday names and never confuses the year for a day.
        day = None
        for dm in _DAY.finditer(text[: year_match.start()]):
            candidate = int(dm.group(1))
            if 1 <= candidate <= 31:
                day = candidate
                break
        if day is not None:
            return _build(year, month, day, text)
        return None

    # 3. Numeric dates (ISO first, since d/m/y would misread 2024-03-05).
    m = _NUMERIC_YMD.search(text)
    if m:
        return _build(int(m.group(1)), int(m.group(2)), int(m.group(3)), text)
    m = _NUMERIC_DMY.search(text)
    if m:
        day, month_num, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if month_num > 12 and day <= 12:  # tolerate m/d/y files
            day, month_num = month_num, day
        return _build(year, month_num, day, text)

    return None
