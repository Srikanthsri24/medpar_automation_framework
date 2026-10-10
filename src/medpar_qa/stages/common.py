"""Shared identities, role separation, duplicate detection, collection normalization, presence
checks and LD-3137 sort/group evidence.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from medpar_qa.enums import FileRole, Stage, ValidationStatus
from medpar_qa.models import RuleResult, SourceRecord
from medpar_qa.normalization.fields import FieldResolver


def split_records_by_role(records: Iterable[SourceRecord]) -> dict[FileRole, list[SourceRecord]]:
    """Separate source, actual-output and expected-output records so a target is not substituted
    for a source operand.
    """
    grouped: dict[FileRole, list[SourceRecord]] = defaultdict(list)
    for record in records:
        grouped[record.source.role].append(record)
    return dict(grouped)


def canonical_scalar(value: Any) -> Any:
    """Normalize identity scalar representations, including configured composite identifiers and
    date forms.
    """
    if isinstance(value, str):
        return value.strip()
    return value


def record_identity(
    record: SourceRecord,
    resolver: FieldResolver,
    identity_fields: Iterable[str],
) -> tuple[Any, ...]:
    """Resolve and canonicalize the configured identity fields into the tuple used to match
    records.
    """
    from medpar_qa.normalization.dates import parse_date
    values=[]
    for field in identity_fields:
        value=canonical_scalar(resolver.get(record.data,field))
        if field.endswith("_date") and value not in (None,""):
            try:
                value=parse_date(value,allow_none=False).isoformat()
            except ValueError:
                pass  # Stage preconditions report malformed dates.
        values.append(value)
    return tuple(values)


def index_unique_records(
    records: Iterable[SourceRecord],
    resolver: FieldResolver,
    identity_fields: Iterable[str],
) -> tuple[dict[tuple[Any, ...], SourceRecord], dict[tuple[Any, ...], list[SourceRecord]]]:
    """Index records by canonical identity and report duplicates separately rather than silently
    certifying uniqueness.
    """
    buckets: dict[tuple[Any, ...], list[SourceRecord]] = defaultdict(list)
    for record in records:
        buckets[record_identity(record, resolver, identity_fields)].append(record)
    unique = {key: values[0] for key, values in buckets.items() if len(values) == 1}
    duplicates = {key: values for key, values in buckets.items() if len(values) > 1}
    return unique, duplicates


def duplicate_identity_result(
    *,
    stage: Stage,
    rule_id: str,
    duplicates: dict[tuple[Any, ...], list[SourceRecord]],
    identity_fields: Iterable[str],
    role_name: str,
) -> RuleResult:
    """Create a PASS/FAIL result describing duplicate output identities and affected evidence."""
    duplicate_evidence = {
        str(key): [record.record_id for record in records]
        for key, records in duplicates.items()
    }
    return RuleResult(
        stage=stage,
        rule_id=rule_id,
        status=ValidationStatus.FAIL if duplicates else ValidationStatus.PASS,
        message=(
            f"Duplicate {role_name} identities found"
            if duplicates
            else f"No duplicate {role_name} identities"
        ),
        expected="One record per identity",
        actual=duplicate_evidence,
        evidence={"identity_fields": list(identity_fields)},
        record_ids=[
            record.record_id
            for records in duplicates.values()
            for record in records
        ],
        source_files=sorted(
            {
                record.source.file_path
                for records in duplicates.values()
                for record in records
            }
        ),
    )


def presence_result(
    *,
    stage: Stage,
    rule_id: str,
    supplied: bool,
    role_name: str,
    required: bool,
) -> RuleResult:
    """Report whether a required or optional file role was supplied; optional absence must not
    become a false calculation PASS.
    """
    if supplied:
        return RuleResult(
            stage=stage,
            rule_id=rule_id,
            status=ValidationStatus.PASS,
            message=f"{role_name} records were supplied",
        )
    return RuleResult(
        stage=stage,
        rule_id=rule_id,
        status=ValidationStatus.FAIL if required else ValidationStatus.NOT_APPLICABLE,
        message=(
            f"Required {role_name} records were not supplied"
            if required
            else f"{role_name} records were not supplied"
        ),
    )


def normalize_collection(value: Any) -> list[Any]:
    """Convert supported scalar/list/object collection shapes into a consistent sequence for
    validators.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def nonblank_values(value: Any) -> list[Any]:
    """Filter absent/blank collection values without conflating every zero value with missing data."""
    return [item for item in normalize_collection(value) if item is not None and str(item).strip()]


def ld3137_sort_order_result(
    *,
    stage: Stage,
    rule_id: str,
    sort_fields: Iterable[str],
) -> RuleResult:
    """Verify LD-3137: admissionDate is excluded from the stage sort/group key."""
    normalized = tuple(str(field) for field in sort_fields)
    forbidden = [field for field in normalized if field in {"admission_date", "admissionDate"}] if stage == Stage.FINAL_ACTION else []
    return RuleResult(
        stage=stage,
        rule_id=rule_id,
        status=ValidationStatus.FAIL if forbidden else ValidationStatus.PASS,
        message=(
            "admissionDate is present in the configured sort/group key"
            if forbidden
            else "Configured admission-date policy matches the stage-specific requirement"
        ),
        expected="Final Action excludes admissionDate; later stages may use stay admission",
        actual={"sort_fields": list(normalized), "forbidden_fields": forbidden},
        field_name="admission_date",
        evidence={
            "change_request": "LD-3137",
            "reason": "Claims sharing the legacy grouping key must remain contiguous and must not be split because admission dates differ",
        },
    )


def ld3137_grouping_result(
    *,
    stage: Stage,
    rule_id: str,
    records: Iterable[SourceRecord],
    resolver: FieldResolver,
    identity_fields: Iterable[str],
) -> RuleResult:
    """Show dictionary/index grouping under the stage-specific configured identity.

    Only Final Action forbids admission date in its identity. Stay and Final retain
    admission date so separate stays do not merge. This reports multi-admission buckets
    when the configured key permits them; it does not prove physical file sort order.
    """
    configured = tuple(str(field) for field in identity_fields)
    forbidden = [field for field in configured if field in {"admission_date", "admissionDate"}] if stage == Stage.FINAL_ACTION else []
    buckets: dict[tuple[Any, ...], list[SourceRecord]] = defaultdict(list)
    for record in records:
        buckets[record_identity(record, resolver, configured)].append(record)

    multiple_admission_dates: dict[str, dict[str, Any]] = {}
    for identity, bucket in buckets.items():
        dates = sorted(
            {
                str(value).strip()
                for record in bucket
                if (value := resolver.get(record.data, "admission_date")) not in (None, "")
            }
        )
        if len(dates) > 1:
            multiple_admission_dates[str(identity)] = {
                "admission_dates": dates,
                "record_ids": [record.record_id for record in bucket],
            }

    valid = not forbidden
    return RuleResult(
        stage=stage,
        rule_id=rule_id,
        status=ValidationStatus.PASS if valid else ValidationStatus.FAIL,
        message=(
            "Claims are bucketed by the configured stage-specific business identity"
            if valid
            else "admissionDate is still present in the configured business identity"
        ),
        expected={
            "admission_date_forbidden": stage == Stage.FINAL_ACTION,
            "same_business_key_processed_as_one_bucket": True,
        },
        actual={
            "identity_fields": list(configured),
            "business_group_count": len(buckets),
            "groups_with_multiple_admission_dates": multiple_admission_dates,
            "forbidden_fields": forbidden,
            "admission_date_in_identity": any(f in {"admission_date","admissionDate"} for f in configured),
        },
        field_name="admission_date",
        record_ids=[record.record_id for record in records],
        source_files=sorted({record.source.file_path for record in records}),
        evidence={
            "change_request": "LD-3137",
            "grouping_implementation": "Dictionary/index grouping; physical file adjacency is not required",
        },
    )
