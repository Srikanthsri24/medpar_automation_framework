"""Determine covered-days/LOS bypass, compare raw golden bytes and enforce exact 3050-to-3000
prefix/trailer removal.
"""
from __future__ import annotations

from medpar_qa.enums import Stage, ValidationStatus
from medpar_qa.models import RuleResult, SourceRecord
from medpar_qa.normalization.fields import FieldResolver
from medpar_qa.normalization.decimal_values import to_decimal


def bypass_required(source: SourceRecord, resolver: FieldResolver) -> bool | None:
    """Derive covered-days-greater-than-LOS bypass, falling back to warning 04=2 only when needed;
    return None when eligibility cannot be established.
    """
    covered = resolver.get(source.data, "utilization_days")
    if covered is None:
        covered = resolver.get(source.data, "covered_days")
    los = resolver.get(source.data, "medpar_lgth_stay_0260")
    if covered is not None and los is not None:
        return to_decimal(covered) > to_decimal(los)
    warning = resolver.get(source.data, "warning_indicator_04")
    return str(warning).strip() == "2" if warning is not None else None


def compare_final_bytes(expected: SourceRecord, actual: SourceRecord, resolver: FieldResolver,
                        encoding: str) -> RuleResult:
    """Compare every encoded byte of matched expected/actual Final records and report exact
    mismatch positions.
    """
    left = resolver.get(expected.data, "fixed_width_record")
    right = resolver.get(actual.data, "fixed_width_record")
    status = ValidationStatus.NOT_APPLICABLE
    evidence = {}
    if left is not None and right is not None:
        try:
            a = left if isinstance(left, bytes) else left.encode(encoding)
            b = right if isinstance(right, bytes) else right.encode(encoding)
            mismatch = [i+1 for i in range(max(len(a), len(b))) if a[i:i+1] != b[i:i+1]]
            status = ValidationStatus.FAIL if mismatch else ValidationStatus.PASS
            evidence = {"mismatch_count": len(mismatch), "first_mismatch_positions": mismatch[:100],
                        "expected_length": len(a), "actual_length": len(b)}
        except (UnicodeError, AttributeError) as exc:
            status = ValidationStatus.FAIL
            evidence = {"error": str(exc)}
    return RuleResult(stage=Stage.FINAL_MEDPAR, rule_id="FM-GOLDEN-BYTE-COMPARISON", status=status,
                      message="Compare every byte against supplied golden record", expected="Exact byte equality",
                      actual=evidence, record_ids=[expected.record_id, actual.record_id],
                      source_files=[expected.source.file_path, actual.source.file_path])


def validate_trailer_removal(source: SourceRecord, actual: SourceRecord, resolver: FieldResolver,
                             encoding: str) -> RuleResult:
    """Require a 3050-byte source, a 3000-byte target and exact equality to the first 3000 source
    bytes.
    """
    raw = resolver.get(source.data, "fixed_width_record")
    output = resolver.get(actual.data, "fixed_width_record")
    status = ValidationStatus.NOT_APPLICABLE
    lengths = None
    if raw is not None and output is not None:
        try:
            a = raw if isinstance(raw, bytes) else raw.encode(encoding)
            b = output if isinstance(output, bytes) else output.encode(encoding)
            lengths = {"source_bytes": len(a), "output_bytes": len(b)}
            status = ValidationStatus.PASS if len(a) == 3050 and len(b) == 3000 and a[:3000] == b else ValidationStatus.FAIL
        except (UnicodeError, AttributeError):
            status = ValidationStatus.FAIL
    return RuleResult(stage=Stage.FINAL_MEDPAR, rule_id="FM-TRAILER-REMOVAL", status=status,
                      message="Final must preserve first 3000 bytes and remove the 50-byte trailer",
                      expected="3050 -> 3000, exact prefix preserved", actual=lengths,
                      record_ids=[source.record_id, actual.record_id], source_files=[source.source.file_path, actual.source.file_path])
