from __future__ import annotations

from decimal import Decimal
from typing import Any

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.models import RuleResult, SourceRecord
from medpar_qa.normalization.decimal_values import quantize_decimal
from medpar_qa.normalization.dates import in_date_window


INTERMEDIATE_DECIMAL_FIELDS = {
    "MEDPAR-COV-CHRG-0410",
    "MEDPAR-SERVICE-CHARGES-0470",
    "MEDPAR-TOT-DPT-CHRG-0440",
    "MEDPAR-TOT-ACC-CHRG-0430",
    "MEDPAR-DRG-PRICE-0380",
}


def validate_intermediate_decimal_field(
    record: SourceRecord,
    *,
    field_name: str,
    expected_value: Any,
    actual_value: Any,
    scale: Decimal = Decimal("0.001"),
) -> RuleResult:
    if field_name not in INTERMEDIATE_DECIMAL_FIELDS:
        return RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-SELECTED-DECIMAL",
            status=ValidationStatus.BLOCKED,
            message=f"Field {field_name} is not configured as an Intermediate decimal field",
            field_name=field_name,
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    try:
        expected = quantize_decimal(expected_value, scale=scale)
        actual = quantize_decimal(actual_value, scale=scale)
    except ValueError as exc:
        return RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-SELECTED-DECIMAL",
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
        stage=Stage.INTERMEDIATE,
        rule_id="INT-SELECTED-DECIMAL",
        status=status,
        message=(
            "Intermediate decimal field matches"
            if status == ValidationStatus.PASS
            else "Intermediate decimal field mismatch"
        ),
        expected=str(expected),
        actual=str(actual),
        field_name=field_name,
        record_ids=[record.record_id],
        source_files=[record.source.file_path],
    )


def validate_procedure_fields(
    record: SourceRecord,
    *,
    codes: list[Any],
    dates: list[Any],
    versions: list[Any] | Any,
    expected_surgical_indicator: str,
    actual_surgical_indicator: str,
    window_start,
    window_end,
) -> list[RuleResult]:
    results: list[RuleResult] = []
    normalized_codes = [str(code).strip() for code in codes if code is not None and str(code).strip()]
    normalized_dates = [value for value in dates if value is not None and str(value).strip()]

    results.append(
        RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-PROC-CODE-COUNT",
            status=ValidationStatus.PASS,
            message="Procedure code count calculated",
            expected=len(normalized_codes),
            actual=len(normalized_codes),
            field_name="MEDPAR-NO-SURG-CODES-0511",
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    )
    results.append(
        RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-PROC-DATE-COUNT",
            status=ValidationStatus.PASS,
            message="Procedure date count calculated",
            expected=len(normalized_dates),
            actual=len(normalized_dates),
            field_name="MEDPAR-NO-SURG-DATES-0512",
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    )

    version_values = versions if isinstance(versions, list) else [versions] * len(normalized_codes)
    aligned = len(version_values) >= len(normalized_codes)
    results.append(
        RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-PROC-VERSION-ALIGNMENT",
            status=ValidationStatus.PASS if aligned else ValidationStatus.FAIL,
            message="Procedure versions align" if aligned else "Procedure versions do not align",
            expected=f">= {len(normalized_codes)} version entries",
            actual=len(version_values),
            field_name="MEDPAR-SRGCL-PRCDR-VRSN-CD",
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    )

    invalid_dates: list[Any] = []
    for value in normalized_dates:
        try:
            if not in_date_window(value, window_start, window_end):
                invalid_dates.append(value)
        except ValueError:
            invalid_dates.append(value)
    results.append(
        RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-PROC-DATE-WINDOW",
            status=ValidationStatus.PASS if not invalid_dates else ValidationStatus.FAIL,
            message="Procedure dates are valid" if not invalid_dates else "Invalid procedure dates found",
            expected=f"between {window_start} and {window_end}",
            actual=invalid_dates,
            field_name="MEDPAR-SURG-DATE-0514",
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    )

    indicator_status = (
        ValidationStatus.PASS
        if actual_surgical_indicator == expected_surgical_indicator
        else ValidationStatus.FAIL
    )
    results.append(
        RuleResult(
            stage=Stage.INTERMEDIATE,
            rule_id="INT-PROC-SURGICAL-INDICATOR",
            status=indicator_status,
            message="Surgical indicator matches" if indicator_status == ValidationStatus.PASS else "Surgical indicator mismatch",
            expected=expected_surgical_indicator,
            actual=actual_surgical_indicator,
            field_name="MEDPAR-SURG-IND-0500",
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    )
    return results


def validate_diagnosis_fields(
    record: SourceRecord,
    *,
    diagnosis_codes: list[Any],
    version_codes: list[Any],
    poa_indicators: list[Any],
    actual_diagnosis_count: int,
    actual_poa_count: int,
) -> list[RuleResult]:
    populated_diagnoses = [item for item in diagnosis_codes if item is not None and str(item).strip()]
    populated_poa = [item for item in poa_indicators if item is not None and str(item).strip()]

    checks = [
        (
            "INT-DIAG-COUNT",
            "MEDPAR-NO-DIAG-CODES-0491",
            len(populated_diagnoses),
            actual_diagnosis_count,
        ),
        (
            "INT-POA-COUNT",
            "MEDPAR-POA-DGNS-CD-CNT",
            len(populated_poa),
            actual_poa_count,
        ),
        (
            "INT-DIAG-VERSION-ALIGNMENT",
            "MEDPAR-DGNS-VRSN-CD",
            len(populated_diagnoses),
            len(version_codes),
        ),
    ]

    results: list[RuleResult] = []
    for rule_id, field_name, expected, actual in checks:
        status = ValidationStatus.PASS if actual == expected else ValidationStatus.FAIL
        results.append(
            RuleResult(
                stage=Stage.INTERMEDIATE,
                rule_id=rule_id,
                status=status,
                message="Field count/alignment matches" if status == ValidationStatus.PASS else "Field count/alignment mismatch",
                expected=expected,
                actual=actual,
                field_name=field_name,
                record_ids=[record.record_id],
                source_files=[record.source.file_path],
            )
        )
    return results
