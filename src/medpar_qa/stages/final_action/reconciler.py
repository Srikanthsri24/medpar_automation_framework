"""Check one decision per input record and exact retained-output identity membership, including
duplicates, missing and unexpected records.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from medpar_qa.enums import RecordDecision, Stage, ValidationStatus
from medpar_qa.models import ClaimDecision, RuleResult, SourceRecord
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.fields import FieldResolver

from .settings import FinalActionSettings


def _canonical_value(field_name: str, value: Any) -> Any:
    """Normalize an identity component before Final Action output reconciliation."""
    if field_name in {"processing_date", "accrete_date"}:
        parsed = parse_date(value, allow_none=True)
        return parsed.isoformat() if parsed else None
    if field_name == "query_code" and value is not None:
        return int(value)
    return "" if value is None else str(value).strip()


def record_identity(
    record: SourceRecord,
    resolver: FieldResolver,
    settings: FinalActionSettings,
) -> tuple[Any, ...]:
    """Resolve and canonicalize the configured identity fields into the tuple used to match
    records.
    """
    return tuple(
        _canonical_value(field, resolver.get(record.data, field))
        for field in settings.identity_fields
    )


def validate_group_decisions(
    records: tuple[SourceRecord, ...],
    decisions: tuple[ClaimDecision, ...],
    group_key: dict[str, Any],
) -> RuleResult:
    """Ensure each source record receives one and only one KEEP/DROP decision."""
    input_ids = [record.record_id for record in records]
    decision_ids = [decision.record_id for decision in decisions]
    duplicate_decisions = sorted(
        record_id for record_id, count in Counter(decision_ids).items() if count > 1
    )
    missing = sorted(set(input_ids) - set(decision_ids))
    unexpected = sorted(set(decision_ids) - set(input_ids))

    passed = (
        len(decisions) == len(records)
        and not duplicate_decisions
        and not missing
        and not unexpected
    )
    return RuleResult(
        stage=Stage.FINAL_ACTION,
        rule_id="FA-GROUP-RECONCILIATION",
        status=ValidationStatus.PASS if passed else ValidationStatus.FAIL,
        message=(
            "Every group record received exactly one decision"
            if passed
            else "Group decisions are incomplete or duplicated"
        ),
        expected={"record_count": len(records), "one_decision_per_record": True},
        actual={
            "decision_count": len(decisions),
            "missing_record_ids": missing,
            "unexpected_record_ids": unexpected,
            "duplicate_decision_ids": duplicate_decisions,
        },
        record_ids=input_ids,
        source_files=sorted({record.source.file_path for record in records}),
        group_key=group_key,
    )


def reconcile_actual_output(
    source_records: list[SourceRecord],
    actual_records: list[SourceRecord],
    decisions: list[ClaimDecision],
    resolver: FieldResolver,
    settings: FinalActionSettings,
) -> RuleResult:
    """Compare actual retained identities against computed KEEP decisions and expose
    missing/unexpected/duplicate output.
    """
    source_by_id = {record.record_id: record for record in source_records}
    expected_kept = [
        source_by_id[item.record_id]
        for item in decisions
        if item.decision == RecordDecision.KEEP and item.record_id in source_by_id
    ]

    expected_counter = Counter(
        record_identity(record, resolver, settings) for record in expected_kept
    )
    actual_counter = Counter(
        record_identity(record, resolver, settings) for record in actual_records
    )

    missing = list((expected_counter - actual_counter).elements())
    unexpected = list((actual_counter - expected_counter).elements())
    passed = not missing and not unexpected

    return RuleResult(
        stage=Stage.FINAL_ACTION,
        rule_id="FA-ACTUAL-OUTPUT-RECONCILIATION",
        status=ValidationStatus.PASS if passed else ValidationStatus.FAIL,
        message=(
            "Actual Final Action output exactly matches expected KEEP records"
            if passed
            else "Actual Final Action output differs from expected KEEP records"
        ),
        expected={"kept_count": sum(expected_counter.values())},
        actual={"output_count": sum(actual_counter.values())},
        record_ids=[record.record_id for record in actual_records],
        source_files=sorted({record.source.file_path for record in actual_records}),
        evidence={
            "identity_fields": list(settings.identity_fields),
            "missing_expected_identities": missing,
            "unexpected_actual_identities": unexpected,
        },
    )
