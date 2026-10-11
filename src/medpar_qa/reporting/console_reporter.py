"""Format validation requirements, observed/expected values and conclusions for terminal output."""
from __future__ import annotations

import json
from typing import Iterable

from medpar_qa.models import RuleResult, StageResult
from medpar_qa.reporting.rule_catalog import conclusion_text, get_rule_metadata, stage_rule_catalog


def _pretty(value: object) -> str:
    """Format values as readable escaped/text JSON for this reporter."""
    try:
        return json.dumps(value, indent=2, default=str, ensure_ascii=False)
    except TypeError:
        return repr(value)


def validation_reason(status: str, message: str, expected: object, actual: object) -> str:
    """Backward-compatible concise reason used by older callers."""
    metadata = get_rule_metadata("unknown", "UNKNOWN")
    return conclusion_text(
        status=status,
        message=message,
        expected=expected,
        actual=actual,
        metadata=metadata,
    )


def _append_value(lines: list[str], label: str, value: object, indent: str = "    ") -> None:
    """Append a labeled nonempty evidence value to the text report."""
    lines.append(f"{indent}{label}:")
    rendered = _pretty(value) if value is not None else "Not supplied / not applicable"
    lines.extend(f"{indent}  {line}" for line in rendered.splitlines())


def render_rule_result(check: RuleResult, number: int) -> list[str]:
    """Render one rule with requirement, expected/observed data, reason and evidence."""
    status = check.status.value
    metadata = get_rule_metadata(check.stage.value, check.rule_id, check.field_name)
    conclusion = conclusion_text(
        status=status,
        message=check.message,
        expected=check.expected,
        actual=check.actual,
        metadata=metadata,
    )
    lines = [
        f"[{number}] {status} | {check.rule_id} | {metadata.title}",
        f"    Business requirement: {metadata.requirement}",
        f"    What was checked: {metadata.validation}",
        f"    Evaluation logic: {metadata.logic}",
    ]
    if check.field_name:
        lines.append(f"    Field: {check.field_name}")
    _append_value(lines, "Expected result", check.expected)
    _append_value(lines, "Observed result", check.actual)
    lines.append(f"    Final explanation: {conclusion}")
    if status in {"FAIL", "BLOCKED"}:
        lines.append(f"    Recommended action: {metadata.remediation}")
    if check.group_key:
        _append_value(lines, "Claim/group key", check.group_key)
    if check.record_ids:
        lines.append(f"    Record IDs ({len(check.record_ids)}): {', '.join(check.record_ids)}")
    if check.source_files:
        lines.append("    Relative source files:")
        lines.extend(f"      - {path}" for path in check.source_files)
    validator = check.evidence.get("validator_function")
    if validator:
        lines.append(f"    Validator function: {validator}")
    if check.evidence:
        _append_value(lines, "Technical evidence", check.evidence)
    return lines


def render_results_text(
    results: Iterable[StageResult],
    *,
    include_pass: bool = True,
    include_not_applicable: bool = True,
) -> str:
    """Render the stage results into a terminal/text report with the requested status filters."""
    stage_results = list(results)
    lines: list[str] = [
        "MEDPAR QA — DETAILED BUSINESS VALIDATION RESULTS",
        "=" * 118,
        "Every validation below explains the requirement, check performed, expected result, observed result, and conclusion.",
    ]

    for stage_result in stage_results:
        counts = stage_result.status_counts
        lines.extend(
            [
                "",
                "#" * 118,
                f"STAGE: {stage_result.stage.value.replace('_', ' ').upper()}",
                f"STAGE STATUS: {'WITH KNOWN DIFFERENCES' if stage_result.passed and counts['KNOWN_DIFFERENCE'] else 'PASS' if stage_result.passed else 'FAIL / BLOCKED'}",
                (
                    f"VALIDATION COUNTS: PASS={counts['PASS']} | FAIL={counts['FAIL']} | "
                    f"BLOCKED={counts['BLOCKED']} | NOT_APPLICABLE={counts['NOT_APPLICABLE']} | KNOWN_DIFFERENCE={counts['KNOWN_DIFFERENCE']}"
                ),
                "#" * 118,
            ]
        )

        shown_number = 0
        for check in stage_result.rule_results:
            status = check.status.value
            if status == "PASS" and not include_pass:
                continue
            if status == "NOT_APPLICABLE" and not include_not_applicable:
                continue
            shown_number += 1
            lines.extend(render_rule_result(check, shown_number))
            lines.append("-" * 118)

        executed = {item.rule_id for item in stage_result.rule_results}
        configured = stage_rule_catalog(stage_result.stage.value)
        not_triggered = [rule_id for rule_id, _ in configured if rule_id not in executed]
        lines.append("")
        lines.append("RULE COVERAGE SUMMARY")
        lines.append(f"    Configured/catalogued rules: {len(configured)}")
        lines.append(f"    Rules that emitted results: {len(executed)}")
        lines.append(
            "    Rules not triggered by this input: "
            + (", ".join(not_triggered) if not_triggered else "None")
        )
        lines.append(
            "    Note: 'not triggered' is not a PASS; its business prerequisites were absent in this data."
        )

        if stage_result.decisions:
            lines.extend(["", "RECORD-LEVEL FINAL ACTION DECISIONS", "-" * 118])
            for decision in stage_result.decisions:
                lines.append(
                    f"Record {decision.record_id}: {decision.decision.value} | "
                    f"Rule {decision.rule_id} | Explanation: {decision.reason}"
                )

    overall = all(result.passed for result in stage_results)
    lines.extend(["=" * 118, f"OVERALL RESULT: {'PASS' if overall else 'FAIL / BLOCKED'}"])
    return "\n".join(lines)
