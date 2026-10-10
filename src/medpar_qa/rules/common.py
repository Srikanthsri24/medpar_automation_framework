"""Shared identities, role separation, duplicate detection, collection normalization, presence
checks and LD-3137 sort/group evidence.
"""
from __future__ import annotations

from typing import Any

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.models import RuleResult, SourceRecord


def required_fields_result(
    stage: Stage,
    rule_id: str,
    record: SourceRecord,
    values: dict[str, Any],
) -> RuleResult:
    """Return a validation result listing required fields that are absent from the resolved record."""
    missing = [name for name, value in values.items() if value is None or value == ""]
    if missing:
        return RuleResult(
            stage=stage,
            rule_id=rule_id,
            status=ValidationStatus.FAIL,
            message=f"Missing required fields: {', '.join(missing)}",
            expected="all required fields populated",
            actual=missing,
            record_ids=[record.record_id],
            source_files=[record.source.file_path],
        )
    return RuleResult(
        stage=stage,
        rule_id=rule_id,
        status=ValidationStatus.PASS,
        message="Required fields are populated",
        record_ids=[record.record_id],
        source_files=[record.source.file_path],
    )
