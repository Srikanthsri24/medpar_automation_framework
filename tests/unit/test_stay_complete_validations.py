"""Regression tests and local fixtures for stay complete validations. Tests describe controlled
examples; passing them does not certify all production files.
"""
from decimal import Decimal

import pytest

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.stages.stay.code_precedence import latest_values_by_code
from medpar_qa.stages.stay.structural import (
    validate_latest_selected_value,
    validate_stay_output_record,
    validate_stay_source_record,
)


def valid_stay_source():
    """Test helper for valid stay source. It constructs or summarizes controlled fixture data for
    the assertions in this file.
    """
    return {
        "claimCanNchEquatable": "H001",
        "provider": {"providerId": "P1"},
        "admissionDate": "20260101",
        "stayFromDate": "20260101",
        "stayThruDate": "20260110",
        "nchWeeklyProcessingDate": "20260120",
        "accreteDate": "20260121",
        "conditionCodes": [],
        "occurrenceCodes": [],
        "occurrenceSpanLines": [],
        "valueLines": [],
        "revenueLines": [],
    }


@pytest.mark.unit
@pytest.mark.stay
@pytest.mark.regression
def test_stay_source_required_identity_and_dates_pass(resolver, make_record):
    """Verify stay source required identity and dates pass. The assertions below state exactly what
    this test proves for its fixtures.
    """
    record = make_record(valid_stay_source(), stage=Stage.STAY)
    results = validate_stay_source_record(record, resolver, decimal_scale=Decimal("0.001"))
    failures = [item for item in results if item.status in {ValidationStatus.FAIL, ValidationStatus.BLOCKED}]
    assert not failures


@pytest.mark.unit
@pytest.mark.stay
def test_stay_source_rejects_reversed_stay_dates(resolver, make_record):
    """Verify stay source rejects reversed stay dates. The assertions below state exactly what this
    test proves for its fixtures.
    """
    data = valid_stay_source()
    data["stayFromDate"] = "20260111"
    data["stayThruDate"] = "20260110"
    record = make_record(data, stage=Stage.STAY)
    results = validate_stay_source_record(record, resolver, decimal_scale=Decimal("0.001"))
    date_order = next(item for item in results if item.rule_id == "ST-STAY-DATE-ORDER")
    assert date_order.status is ValidationStatus.FAIL


@pytest.mark.unit
@pytest.mark.stay
@pytest.mark.regression
def test_latest_value_code_object_wins(resolver, make_record):
    """Verify latest value code object wins. The assertions below state exactly what this test
    proves for its fixtures.
    """
    older = make_record(
        {**valid_stay_source(), "nchWeeklyProcessingDate": "20260101", "valueLines": [{"valueCode": "73", "amount": "1.000"}]},
        row=1,
        stage=Stage.STAY,
    )
    newer = make_record(
        {**valid_stay_source(), "nchWeeklyProcessingDate": "20260102", "valueLines": [{"valueCode": "73", "amount": "2.000"}]},
        row=2,
        stage=Stage.STAY,
    )
    result = latest_values_by_code([older, newer], collection_path="value_lines", resolver=resolver)
    assert result[0]["amount"] == "3.000"
    assert result[0]["_source_record_id"] == "record-2"


@pytest.mark.unit
@pytest.mark.stay
@pytest.mark.regression
def test_latest_span_code_object_wins(resolver, make_record):
    """Verify latest span code object wins. The assertions below state exactly what this test
    proves for its fixtures.
    """
    older = make_record(
        {**valid_stay_source(), "nchWeeklyProcessingDate": "20260101", "occurrenceSpanLines": [{"spanCode": "70", "fromDate": "20260101", "thruDate": "20260102"}]},
        row=1,
        stage=Stage.STAY,
    )
    newer = make_record(
        {**valid_stay_source(), "nchWeeklyProcessingDate": "20260102", "occurrenceSpanLines": [{"spanCode": "70", "fromDate": "20260103", "thruDate": "20260104"}]},
        row=2,
        stage=Stage.STAY,
    )
    result = latest_values_by_code([older, newer], collection_path="occurrence_span_lines", resolver=resolver)
    assert result[0]["fromDate"] == "20260103"


@pytest.mark.unit
@pytest.mark.stay
def test_snf_qualification_date_order_fails(resolver, make_record):
    """Verify snf qualification date order fails. The assertions below state exactly what this test
    proves for its fixtures.
    """
    record = make_record(
        {
            "MEDPAR-SNF-QUAL-FROM-DATE-0180": "20260110",
            "MEDPAR-SNF-QUAL-THRU-DATE-0190": "20260101",
        },
        stage=Stage.STAY,
    )
    results = validate_stay_output_record(record, resolver, decimal_scale=Decimal("0.001"))
    relationship = next(item for item in results if item.rule_id == "ST-SNF-QUAL-DATE-ORDER")
    assert relationship.status is ValidationStatus.FAIL


@pytest.mark.unit
@pytest.mark.stay
@pytest.mark.regression
def test_drg_price_uses_latest_nonblank_source_value(resolver, make_record):
    """Verify drg price uses latest nonblank source value. The assertions below state exactly what
    this test proves for its fixtures.
    """
    source_old = make_record(
        {**valid_stay_source(), "nchWeeklyProcessingDate": "20260101", "MEDPAR-DRG-PRICE-0380": "10.000"},
        row=1,
        stage=Stage.STAY,
    )
    source_new = make_record(
        {**valid_stay_source(), "nchWeeklyProcessingDate": "20260102", "MEDPAR-DRG-PRICE-0380": "20.000"},
        row=2,
        stage=Stage.STAY,
    )
    actual = make_record(
        {"MEDPAR-DRG-PRICE-0380": "20.000"},
        row=3,
        stage=Stage.STAY,
    )
    result = validate_latest_selected_value(
        source_group=[source_old, source_new],
        actual=actual,
        resolver=resolver,
        field_name="medpar_drg_price_0380",
        rule_id="ST-DRG-PRICE-LATEST-RECORD",
        decimal_scale=Decimal("0.001"),
    )
    assert result.status is ValidationStatus.PASS
