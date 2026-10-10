"""Regression tests and local fixtures for final medpar bytes. Tests describe controlled examples;
passing them does not certify all production files.
"""
import pytest

from medpar_qa.enums import ValidationStatus
from medpar_qa.stages.final_medpar.byte_layout import validate_encoded_length


@pytest.mark.unit
@pytest.mark.final_medpar
@pytest.mark.regression
@pytest.mark.byte_by_byte
def test_actual_encoded_record_is_exactly_3000_bytes():
    """Verify actual encoded record is exactly 3000 bytes. The assertions below state exactly what
    this test proves for its fixtures.
    """
    result = validate_encoded_length("A" * 3000)
    assert result.status == ValidationStatus.PASS


@pytest.mark.unit
@pytest.mark.final_medpar
@pytest.mark.byte_by_byte
def test_wrong_encoded_record_length_fails():
    """Verify wrong encoded record length fails. The assertions below state exactly what this test
    proves for its fixtures.
    """
    result = validate_encoded_length("A" * 2999)
    assert result.status == ValidationStatus.FAIL
