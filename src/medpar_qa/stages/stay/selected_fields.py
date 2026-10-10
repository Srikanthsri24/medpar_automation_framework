"""Validate selected Stay amount fields at configured Decimal scale."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.models import RuleResult, SourceRecord
from medpar_qa.normalization.decimal_values import quantize_decimal


STAY_DECIMAL_FIELDS = {
    "MEDPAR-TOT-CHRG-0400",
    "MEDPAR-DRG-PRICE-0380",
    "MEDPAR-SQSTRTN-RDCTN-AMT-1130",
}


def validate_stay_decimal_field(
    record: SourceRecord,
    *,
    field_name: str,
    expected_value: Any,
    actual_value: Any,
    scale: Decimal = Decimal("0.001"),
) -> RuleResult:
    """Validate one selected Stay amount at the configured calculation scale."""
    if field_name not in STAY_DECIMAL_FIELDS:
        return RuleResult(
            stage=Stage.STAY,
            rule_id="ST-SELECTED-DECIMAL",
            status=ValidationStatus.BLOCKED,
            message=f"Field {field_name} is not configured as a Stay selected decimal field",
            field_name=field_name,
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )

    try:
        expected = quantize_decimal(expected_value, scale=scale)
        actual = quantize_decimal(actual_value, scale=scale)
    except ValueError as exc:
        return RuleResult(
            stage=Stage.STAY,
            rule_id="ST-SELECTED-DECIMAL",
            status=ValidationStatus.FAIL,
            message=str(exc),
            expected=expected_value,
            actual=actual_value,
            field_name=field_name,
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )

    status = ValidationStatus.PASS if actual == expected else ValidationStatus.FAIL
    return RuleResult(
        stage=Stage.STAY,
        rule_id="ST-SELECTED-DECIMAL",
        status=status,
        message="Stay selected field matches" if status == ValidationStatus.PASS else "Stay selected field mismatch",
        expected=str(expected),
        actual=str(actual),
        field_name=field_name,
        record_ids=[record.record_id],
        source_files=[record.source.file_path],
    )
