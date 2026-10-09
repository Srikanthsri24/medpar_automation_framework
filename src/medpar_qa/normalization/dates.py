from __future__ import annotations

from datetime import date, datetime
from typing import Any


DATE_FORMATS = ("%Y%m%d", "%Y-%m-%d", "%m/%d/%Y")


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
        try:
            return datetime.strptime(text, pattern).date()
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
