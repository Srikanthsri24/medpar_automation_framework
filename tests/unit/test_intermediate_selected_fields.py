"""Regression tests and local fixtures for intermediate selected fields. Tests describe controlled
examples; passing them does not certify all production files.
"""
from datetime import date

import pytest

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.stages.intermediate.selected_fields import (
    validate_diagnosis_fields,
    validate_intermediate_decimal_field,
    validate_procedure_fields,
)


@pytest.mark.unit
@pytest.mark.intermediate
@pytest.mark.regression
@pytest.mark.decimal_precision
@pytest.mark.parametrize(
    "field_name",
    [
        "MEDPAR-COV-CHRG-0410",
        "MEDPAR-SERVICE-CHARGES-0470",
        "MEDPAR-TOT-DPT-CHRG-0440",
    ],
)
def test_intermediate_charge_precision(make_record, field_name):
    """Verify intermediate charge precision. The assertions below state exactly what this test
    proves for its fixtures.
    """
    record = make_record({}, stage=Stage.INTERMEDIATE)
    result = validate_intermediate_decimal_field(
        record,
        field_name=field_name,
        expected_value="0.1",
        actual_value="0.1004",
    )
    assert result.status == ValidationStatus.PASS
    assert result.actual == "0.100"


@pytest.mark.unit
@pytest.mark.intermediate
@pytest.mark.regression
@pytest.mark.decimal_precision
def test_negative_amount_rounding_is_preserved(make_record):
    """Verify negative amount rounding is preserved. The assertions below state exactly what this
    test proves for its fixtures.
    """
    record = make_record({}, stage=Stage.INTERMEDIATE)
    result = validate_intermediate_decimal_field(
        record,
        field_name="MEDPAR-COV-CHRG-0410",
        expected_value="-1.2345",
        actual_value="-1.235",
    )
    assert result.status == ValidationStatus.PASS


@pytest.mark.unit
@pytest.mark.intermediate
@pytest.mark.regression
@pytest.mark.procedure_codes
def test_procedure_codes_dates_versions_and_indicator(make_record):
    """Verify procedure codes dates versions and indicator. The assertions below state exactly what
    this test proves for its fixtures.
    """
    record = make_record({}, stage=Stage.INTERMEDIATE)
    results = validate_procedure_fields(
        record,
        codes=["0ABC", "0XYZ"],
        dates=["20220101", "20260701"],
        versions=["10", "10"],
        expected_surgical_indicator="Y",
        actual_surgical_indicator="Y",
        window_start=date(2022, 1, 1),
        window_end=date(2026, 7, 19),
    )
    assert all(item.status == ValidationStatus.PASS for item in results)


@pytest.mark.unit
@pytest.mark.intermediate
@pytest.mark.regression
@pytest.mark.diagnosis_codes
def test_diagnosis_counts_versions_and_poa_alignment(make_record):
    """Verify diagnosis counts versions and poa alignment. The assertions below state exactly what
    this test proves for its fixtures.
    """
    record = make_record({}, stage=Stage.INTERMEDIATE)
    results = validate_diagnosis_fields(
        record,
        diagnosis_codes=["A01", "B02"],
        version_codes=["10", "10"],
        poa_indicators=["Y", "N"],
        actual_diagnosis_count=2,
        actual_poa_count=2,
    )
    assert all(item.status == ValidationStatus.PASS for item in results)
