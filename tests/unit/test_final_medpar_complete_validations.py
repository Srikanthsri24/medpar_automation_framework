"""Regression tests and local fixtures for final medpar complete validations. Tests describe
controlled examples; passing them does not certify all production files.
"""
import pytest

from medpar_qa.enums import ValidationStatus
from medpar_qa.stages.final_medpar.byte_layout import (
    validate_encoded_length,
    validate_field_layout,
)


@pytest.mark.unit
@pytest.mark.final_medpar
@pytest.mark.byte_by_byte
@pytest.mark.regression
def test_configured_byte_field_layout_passes():
    """Verify configured byte field layout passes. The assertions below state exactly what this
    test proves for its fixtures.
    """
    record = "ABC" + " " * 7
    results = validate_field_layout(
        record,
        field_layout=[{"name": "prefix", "start": 1, "length": 3, "expected": "ABC"}],
    )
    assert results[0].status is ValidationStatus.PASS


@pytest.mark.unit
@pytest.mark.final_medpar
@pytest.mark.byte_by_byte
def test_configured_byte_field_layout_detects_wrong_value():
    """Verify configured byte field layout detects wrong value. The assertions below state exactly
    what this test proves for its fixtures.
    """
    results = validate_field_layout(
        "XYZ",
        field_layout=[{"name": "prefix", "start": 1, "length": 3, "expected": "ABC"}],
    )
    assert results[0].status is ValidationStatus.FAIL


@pytest.mark.unit
@pytest.mark.final_medpar
@pytest.mark.byte_by_byte
def test_non_ascii_fixed_width_record_fails_ascii_encoding():
    """Verify non ascii fixed width record fails ascii encoding. The assertions below state exactly
    what this test proves for its fixtures.
    """
    result = validate_encoded_length("é" * 3000, expected_bytes=3000, encoding="ascii")
    assert result.status is ValidationStatus.FAIL
