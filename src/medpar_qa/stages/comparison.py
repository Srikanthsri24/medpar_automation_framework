"""Compare expected/actual values and matched record fields, using normalized scalars/collections
and explicit Decimal handling.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.models import RuleResult, SourceRecord
from medpar_qa.normalization.decimal_values import quantize_decimal
from medpar_qa.normalization.fields import FieldResolver


def compare_values(
    *,
    stage: Stage,
    rule_id: str,
    field_name: str,
    expected: Any,
    actual: Any,
    record_ids: list[str],
    source_files: list[str],
    decimal_scale: Decimal | None = None,
) -> RuleResult:
    """Compare normalized values with explicit numeric/collection handling and return equality plus
    comparison evidence.
    """
    normalized_expected = expected
    normalized_actual = actual
    try:
        if decimal_scale is not None and expected is not None and actual is not None:
            normalized_expected = quantize_decimal(expected, scale=decimal_scale)
            normalized_actual = quantize_decimal(actual, scale=decimal_scale)
    except ValueError as exc:
        return RuleResult(
            stage=stage,
            rule_id=rule_id,
            status=ValidationStatus.FAIL,
            message=f"Invalid Decimal value: {exc}",
            expected=expected,
            actual=actual,
            field_name=field_name,
            record_ids=record_ids,
            source_files=source_files,
        )

    status = (
        ValidationStatus.PASS
        if normalized_actual == normalized_expected
        else ValidationStatus.FAIL
    )
    return RuleResult(
        stage=stage,
        rule_id=rule_id,
        status=status,
        message=(
            f"{field_name} matches expected"
            if status == ValidationStatus.PASS
            else f"{field_name} mismatch"
        ),
        expected=(
            str(normalized_expected)
            if isinstance(normalized_expected, Decimal)
            else normalized_expected
        ),
        actual=(
            str(normalized_actual)
            if isinstance(normalized_actual, Decimal)
            else normalized_actual
        ),
        field_name=field_name,
        record_ids=record_ids,
        source_files=source_files,
    )


def compare_expected_actual_fields(
    *,
    stage: Stage,
    expected_record: SourceRecord,
    actual_record: SourceRecord,
    resolver: FieldResolver,
    fields: Iterable[str],
    decimal_fields: set[str] | None = None,
    decimal_scale: Decimal = Decimal("0.001"),
    rule_prefix: str,
) -> list[RuleResult]:
    """Match expected and actual record identities, detect membership problems and compare selected
    fields.
    """
    decimal_fields = decimal_fields or set()
    results: list[RuleResult] = []
    for field_name in fields:
        expected = resolver.get(expected_record.data, field_name)
        actual = resolver.get(actual_record.data, field_name)
        record_ids = [expected_record.record_id, actual_record.record_id]
        source_files = [
            expected_record.source.file_path,
            actual_record.source.file_path,
        ]
        expected_blank = expected is None or (isinstance(expected, str) and not expected.strip())
        actual_blank = actual is None or (isinstance(actual, str) and not actual.strip())
        if expected_blank and actual_blank:
            results.append(
                RuleResult(
                    stage=stage,
                    rule_id=f"{rule_prefix}-{field_name}",
                    status=ValidationStatus.NOT_APPLICABLE,
                    message=(
                        f"{field_name} is absent from both approved expected and actual output; "
                        "no PASS is claimed for this field"
                    ),
                    expected=expected,
                    actual=actual,
                    field_name=field_name,
                    record_ids=record_ids,
                    source_files=source_files,
                    evidence={
                        "coverage_status": "NOT_TESTED_NO_EXPECTED_VALUE",
                        "required_action": "Populate approved expected data when this field is applicable",
                    },
                )
            )
            continue
        results.append(
            compare_values(
                stage=stage,
                rule_id=f"{rule_prefix}-{field_name}",
                field_name=field_name,
                expected=expected,
                actual=actual,
                record_ids=record_ids,
                source_files=source_files,
                decimal_scale=decimal_scale if field_name in decimal_fields else None,
            )
        )
    return results
