from __future__ import annotations

from datetime import date, datetime
from typing import Any


DATE_FORMATS = ("%Y%m%d", "%Y-%m-%d", "%m/%d/%Y", "%Y%j", "%y%j")


def parse_date(value: Any, *, allow_none: bool = True) -> date | None:
    if value is None or value == "":
        if allow_none:
            return None
        raise ValueError("Date is required")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    for pattern in DATE_FORMATS:
        # strptime accepts variable-width months/days. A seven-digit Julian
        # value such as 2026064 must not be mistaken for Gregorian June 4.
        widths = {"%Y%m%d": 8, "%Y%j": 7, "%y%j": 5}
        if pattern in widths and (len(text) != widths[pattern] or not text.isdigit()):
            continue
        try:
            result = datetime.strptime(text, pattern).date()
            if pattern in ("%Y%j", "%y%j"):
                expected_year = int(text[:4]) if pattern == "%Y%j" else int(text[:2])
                if pattern == "%y%j":
                    expected_year += 2000 if expected_year <= 68 else 1900
                if result.year != expected_year:
                    continue
            return result
        except ValueError:
            continue
    raise ValueError(f"Unsupported date value: {value!r}")


def january_aligned_window(run_date: date, years: int) -> tuple[date, date]:
    if years < 1:
        raise ValueError("years must be at least 1")
    return date(run_date.year - (years - 1), 1, 1), run_date


def in_date_window(value: Any, start: date, end: date) -> bool:
    parsed = parse_date(value, allow_none=False)
    assert parsed is not None
    return start <= parsed <= end
