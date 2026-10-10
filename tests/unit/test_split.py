from datetime import date

import pytest

from medpar_qa.enums import Stage
from medpar_qa.stages.split.processor import SplitProcessor


@pytest.mark.unit
@pytest.mark.split
@pytest.mark.regression
def test_split_indicator_january_to_september(resolver, make_record):
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
