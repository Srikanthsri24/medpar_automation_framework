from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.models import RuleResult, SourceRecord
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.decimal_values import quantize_decimal
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.stages.common import normalize_collection


def required_fields_results(
    *,
    stage: Stage,
    rule_prefix: str,
    record: SourceRecord,
    resolver: FieldResolver,
    fields: Iterable[str],
) -> list[RuleResult]:
    results: list[RuleResult] = []
    for field_name in fields:
        value = resolver.get(record.data, field_name)
        supplied = value is not None and (not isinstance(value, str) or bool(value.strip()))
        results.append(
            RuleResult(
                stage=stage,
                rule_id=f"{rule_prefix}-REQUIRED-FIELD",
                status=ValidationStatus.PASS if supplied else ValidationStatus.FAIL,
                message=(
                    f"Required field {field_name} is supplied"
                    if supplied
                    else f"Required field {field_name} is missing or blank"
                ),
                expected="Non-blank value",
                actual=value,
                field_name=field_name,
                record_ids=[record.record_id],
                source_files=[record.source.file_path],
            )
        )
    return results


def optional_date_result(
    *,
    stage: Stage,
    rule_id: str,
    record: SourceRecord,
    resolver: FieldResolver,
    field_name: str,
    required: bool = False,
    window_start: date | None = None,
    window_end: date | None = None,
) -> RuleResult:
    raw = resolver.get(record.data, field_name)
    from medpar_qa.normalization.dates import is_missing_date
    if is_missing_date(raw):
        return RuleResult(
            stage=stage,
            rule_id=rule_id,
            status=ValidationStatus.FAIL if required else ValidationStatus.NOT_APPLICABLE,
            message=(
                f"Required date {field_name} is missing"
                if required
                else f"Optional date {field_name} is not populated"
            ),
            expected="Valid date" if required else None,
            actual=raw,
            field_name=field_name,
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    try:
        parsed = parse_date(raw, allow_none=False)
        assert parsed is not None
        in_window = True
        if window_start is not None and parsed < window_start:
            in_window = False
        if window_end is not None and parsed > window_end:
            in_window = False
        return RuleResult(
            stage=stage,
            rule_id=rule_id,
            status=ValidationStatus.PASS if in_window else ValidationStatus.FAIL,
            message=(
                f"Date {field_name} is valid"
                if in_window
                else f"Date {field_name} is outside the configured window"
            ),
            expected=(
                f"{window_start} through {window_end}"
                if window_start is not None or window_end is not None
                else "Valid date"
            ),
            actual=str(parsed),
            field_name=field_name,
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    except ValueError as exc:
        return RuleResult(
            stage=stage,
            rule_id=rule_id,
            status=ValidationStatus.FAIL,
            message=str(exc),
            expected="Valid date",
            actual=raw,
            field_name=field_name,
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )


def date_order_result(
    *,
    stage: Stage,
    rule_id: str,
    record: SourceRecord,
    resolver: FieldResolver,
    start_field: str,
    end_field: str,
    allow_missing: bool = True,
) -> RuleResult:
    start_raw = resolver.get(record.data, start_field)
    end_raw = resolver.get(record.data, end_field)
    if allow_missing and (start_raw in (None, "") or end_raw in (None, "")):
        return RuleResult(
            stage=stage,
            rule_id=rule_id,
            status=ValidationStatus.NOT_APPLICABLE,
            message=f"{start_field}/{end_field} relationship cannot be checked because one value is absent",
            expected=f"{start_field} <= {end_field}",
            actual={start_field: start_raw, end_field: end_raw},
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    try:
        start = parse_date(start_raw, allow_none=False)
        end = parse_date(end_raw, allow_none=False)
        assert start is not None and end is not None
        valid = start <= end
        return RuleResult(
            stage=stage,
            rule_id=rule_id,
            status=ValidationStatus.PASS if valid else ValidationStatus.FAIL,
            message="Date order is valid" if valid else "Date order is invalid",
            expected=f"{start_field} <= {end_field}",
            actual={start_field: str(start), end_field: str(end)},
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    except ValueError as exc:
        return RuleResult(
            stage=stage,
            rule_id=rule_id,
            status=ValidationStatus.FAIL,
            message=str(exc),
            expected=f"Valid {start_field} and {end_field}",
            actual={start_field: start_raw, end_field: end_raw},
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )


def allowed_value_result(
    *,
    stage: Stage,
    rule_id: str,
    record: SourceRecord,
    resolver: FieldResolver,
    field_name: str,
    allowed: Iterable[Any],
    required: bool = False,
) -> RuleResult:
    raw = resolver.get(record.data, field_name)
    allowed_values = tuple(allowed)
    if raw is None or raw == "":
        return RuleResult(
            stage=stage,
            rule_id=rule_id,
            status=ValidationStatus.FAIL if required else ValidationStatus.NOT_APPLICABLE,
            message=(
                f"Required field {field_name} is missing"
                if required
                else f"Optional field {field_name} is not populated"
            ),
            expected=list(allowed_values),
            actual=raw,
            field_name=field_name,
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    normalized_allowed = {str(value).strip() for value in allowed_values}
    valid = str(raw).strip() in normalized_allowed
    return RuleResult(
        stage=stage,
        rule_id=rule_id,
        status=ValidationStatus.PASS if valid else ValidationStatus.FAIL,
        message=f"{field_name} is valid" if valid else f"{field_name} is invalid",
        expected=sorted(normalized_allowed),
        actual=raw,
        field_name=field_name,
        record_ids=[record.record_id],
        source_files=[record.source.file_path],
    )


def decimal_field_result(
    *,
    stage: Stage,
    rule_id: str,
    record: SourceRecord,
    resolver: FieldResolver,
    field_name: str,
    scale: Decimal,
    required: bool = False,
) -> RuleResult:
    raw = resolver.get(record.data, field_name)
    if raw is None or raw == "":
        return RuleResult(
            stage=stage,
            rule_id=rule_id,
            status=ValidationStatus.FAIL if required else ValidationStatus.NOT_APPLICABLE,
            message=(
                f"Required amount {field_name} is missing"
                if required
                else f"Optional amount {field_name} is not populated"
            ),
            expected=f"Decimal quantized to {scale}",
            actual=raw,
            field_name=field_name,
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    try:
        normalized = quantize_decimal(raw, scale=scale)
        return RuleResult(
            stage=stage,
            rule_id=rule_id,
            status=ValidationStatus.PASS,
            message=f"{field_name} is a valid Decimal amount",
            expected=f"Decimal quantized to {scale}",
            actual=str(normalized),
            field_name=field_name,
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    except ValueError as exc:
        return RuleResult(
            stage=stage,
            rule_id=rule_id,
            status=ValidationStatus.FAIL,
            message=str(exc),
            expected=f"Decimal quantized to {scale}",
            actual=raw,
            field_name=field_name,
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )


def collection_structure_result(
    *,
    stage: Stage,
    rule_id: str,
    record: SourceRecord,
    resolver: FieldResolver,
    field_name: str,
    item_required_keys: Iterable[str] = (),
    required: bool = False,
) -> RuleResult:
    raw = resolver.get(record.data, field_name)
    if raw is None:
        return RuleResult(
            stage=stage,
            rule_id=rule_id,
            status=ValidationStatus.FAIL if required else ValidationStatus.NOT_APPLICABLE,
            message=(
                f"Required collection {field_name} is missing"
                if required
                else f"Optional collection {field_name} is not populated"
            ),
            expected="List",
            actual=None,
            field_name=field_name,
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    if not isinstance(raw, list):
        return RuleResult(
            stage=stage,
            rule_id=rule_id,
            status=ValidationStatus.FAIL,
            message=f"{field_name} must be a list",
            expected="List",
            actual=type(raw).__name__,
            field_name=field_name,
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    required_keys = tuple(item_required_keys)
    invalid: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if required_keys and not isinstance(item, dict):
            invalid.append({"index": index, "reason": "item is not an object"})
            continue
        if isinstance(item, dict):
            missing = [key for key in required_keys if item.get(key) in (None, "")]
            if missing:
                invalid.append({"index": index, "missing": missing})
    return RuleResult(
        stage=stage,
        rule_id=rule_id,
        status=ValidationStatus.PASS if not invalid else ValidationStatus.FAIL,
        message=(
            f"{field_name} structure is valid"
            if not invalid
            else f"{field_name} contains invalid items"
        ),
        expected={"type": "list", "item_required_keys": list(required_keys)},
        actual={"count": len(raw), "invalid": invalid},
        field_name=field_name,
        record_ids=[record.record_id],
        source_files=[record.source.file_path],
    )


def pattern_result(
    *,
    stage: Stage,
    rule_id: str,
    record: SourceRecord,
    resolver: FieldResolver,
    field_name: str,
    pattern: str,
    description: str,
    required: bool = False,
) -> RuleResult:
    raw = resolver.get(record.data, field_name)
    if raw is None or raw == "":
        return RuleResult(
            stage=stage,
            rule_id=rule_id,
            status=ValidationStatus.FAIL if required else ValidationStatus.NOT_APPLICABLE,
            message=f"{field_name} is not populated",
            expected=description,
            actual=raw,
            field_name=field_name,
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    valid = re.fullmatch(pattern, str(raw).strip()) is not None
    return RuleResult(
        stage=stage,
        rule_id=rule_id,
        status=ValidationStatus.PASS if valid else ValidationStatus.FAIL,
        message=f"{field_name} format is valid" if valid else f"{field_name} format is invalid",
        expected=description,
        actual=raw,
        field_name=field_name,
        record_ids=[record.record_id],
        source_files=[record.source.file_path],
    )
