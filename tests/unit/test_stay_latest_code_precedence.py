import pytest

from medpar_qa.enums import Stage
from medpar_qa.stages.stay.code_precedence import latest_values_by_code


@pytest.mark.unit
@pytest.mark.stay
@pytest.mark.regression
@pytest.mark.condition_codes
def test_duplicate_condition_code_uses_latest_claim(make_record):
    older = make_record(
        {
            "nchWeeklyProcessingDate": "20260101",
            "conditionCodes": [{"code": "04", "value": "OLD"}, {"code": "69", "value": "KEEP"}],
        },
        row=1,
        stage=Stage.STAY,
    )
    newer = make_record(
        {
            "nchWeeklyProcessingDate": "20260103",
            "conditionCodes": [{"code": "04", "value": "NEW"}],
        },
        row=2,
        stage=Stage.STAY,
    )

    result = latest_values_by_code([older, newer], collection_path="conditionCodes")

    assert result == [
        {"code": "04", "value": "NEW", "_source_record_id": "record-2"},
        {"code": "69", "value": "KEEP", "_source_record_id": "record-1"},
    ]


@pytest.mark.unit
@pytest.mark.stay
@pytest.mark.regression
@pytest.mark.occurrence_codes
def test_duplicate_occurrence_code_uses_latest_claim(make_record):
    older = make_record(
        {
            "nchWeeklyProcessingDate": "20260101",
            "occurrenceCodes": [{"code": "11", "date": "20250101"}],
        },
        row=1,
        stage=Stage.STAY,
    )
    newer = make_record(
        {
            "nchWeeklyProcessingDate": "20260102",
            "occurrenceCodes": [{"code": "11", "date": "20250202"}],
        },
        row=2,
        stage=Stage.STAY,
    )

    result = latest_values_by_code([older, newer], collection_path="occurrenceCodes")

    assert result[0]["date"] == "20250202"
    assert result[0]["_source_record_id"] == "record-2"
