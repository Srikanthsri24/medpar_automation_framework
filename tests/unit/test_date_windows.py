from datetime import date

import pytest

from medpar_qa.normalization.dates import january_aligned_window


@pytest.mark.unit
def test_intermediate_five_year_window_starts_january():
    start, end = january_aligned_window(date(2026, 10, 21), 5)
    assert start == date(2022, 1, 1)
    assert end == date(2026, 10, 21)


@pytest.mark.unit
def test_split_four_year_window_starts_january():
    start, end = january_aligned_window(date(2026, 7, 19), 4)
    assert start == date(2023, 1, 1)
    assert end == date(2026, 7, 19)
