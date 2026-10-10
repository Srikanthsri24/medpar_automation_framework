"""Regression tests and local fixtures for split. Tests describe controlled examples; passing them
does not certify all production files.
"""
from datetime import date

import pytest

from medpar_qa.enums import Stage
from medpar_qa.stages.split.processor import SplitProcessor


@pytest.mark.unit
@pytest.mark.split
@pytest.mark.regression
def test_split_indicator_january_to_september(resolver, make_record):
    """Verify split indicator january to september. The assertions below state exactly what this
    test proves for its fixtures.
    """
    record = make_record(
        {
            "admissionDate": "20260403",
            "stayFromDate": "20260403",
            "stayThruDate": "20260405",
        },
        stage=Stage.SPLIT,
    )
    processor = SplitProcessor(resolver, date(2026, 7, 19), window_years=4)
    assert processor.calculate_indicator(record) == "Y00109"


@pytest.mark.unit
@pytest.mark.split
@pytest.mark.regression
def test_split_indicator_outside_window(resolver, make_record):
    """Verify split indicator outside window. The assertions below state exactly what this test
    proves for its fixtures.
    """
    record = make_record(
        {
            "admissionDate": "20220101",
            "stayFromDate": "20220101",
            "stayThruDate": "20220105",
        },
        stage=Stage.SPLIT,
    )
    processor = SplitProcessor(resolver, date(2026, 7, 19), window_years=4)
    assert processor.calculate_indicator(record) == "Y99999"
