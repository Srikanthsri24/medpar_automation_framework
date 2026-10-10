"""Capture emitted validation and decision events during a command/test. Reporting capture is
separate from the business decision itself.
"""
from __future__ import annotations

import json
from contextvars import ContextVar, Token
from copy import deepcopy
from typing import Any

from .rule_catalog import conclusion_text, get_rule_metadata

_CAPTURED_EVENTS: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "medpar_captured_validation_events", default=None
)


def start_capture() -> Token:
    """Start a scoped validation-event buffer for one command or pytest test."""
    return _CAPTURED_EVENTS.set([])


def finish_capture(token: Token) -> list[dict[str, Any]]:
    """Finish event capture and return the collected validation/decision evidence."""
    events = _CAPTURED_EVENTS.get() or []
    _CAPTURED_EVENTS.reset(token)
    return events


def record_event(event: dict[str, Any]) -> None:
    """Append an evidence event when capture is active; this does not determine the business
    outcome.
    """
    events = _CAPTURED_EVENTS.get()
    if events is not None:
        events.append(deepcopy(event))


def _pretty(value: Any) -> str:
    """Format values as readable escaped/text JSON for this reporter."""
    if value is None:
        return "Not supplied / not applicable"
    return json.dumps(value, indent=2, default=str, ensure_ascii=False)


def format_events_text(events: list[dict[str, Any]]) -> str:
    """Render captured events into readable test evidence."""
    if not events:
        return ""
    lines = ["", "MEDPAR RULE-WISE VALIDATION DETAILS", "=" * 110]
    for index, event in enumerate(events, start=1):
        if event.get("event_type") == "decision":
            lines.extend(
                [
                    f"[{index}] RECORD DECISION: {event.get('decision')}",
                    f"    Rule: {event.get('rule_id')}",
                    f"    Record: {event.get('record_id')}",
                    f"    Explanation: {event.get('reason')}",
                    "-" * 110,
                ]
            )
            continue

        stage = str(event.get("stage", "unknown"))
        rule_id = str(event.get("rule_id", "UNKNOWN"))
        status = str(event.get("status", "UNKNOWN"))
        field = event.get("field_name")
        metadata = get_rule_metadata(stage, rule_id, field)
        expected = event.get("expected")
        actual = event.get("actual")
        message = str(event.get("message", ""))
        lines.extend(
            [
                f"[{index}] {status} | {rule_id} | {metadata.title}",
                f"    Stage: {stage}",
                f"    Business requirement: {metadata.requirement}",
                f"    What was checked: {metadata.validation}",
                f"    Evaluation logic: {metadata.logic}",
            ]
        )
        if field:
            lines.append(f"    Field: {field}")
        lines.append("    Expected result:")
        lines.extend(f"      {line}" for line in _pretty(expected).splitlines())
        lines.append("    Observed result:")
        lines.extend(f"      {line}" for line in _pretty(actual).splitlines())
        lines.append(
            "    Conclusion: "
            + conclusion_text(
                status=status,
                message=message,
                expected=expected,
                actual=actual,
                metadata=metadata,
            )
        )
        if status in {"FAIL", "BLOCKED"}:
            lines.append(f"    Recommended action: {metadata.remediation}")
        if event.get("source_files"):
            lines.append(f"    Relative source files: {event.get('source_files')}")
        if event.get("record_ids"):
            lines.append(f"    Record IDs: {event.get('record_ids')}")
        if event.get("group_key"):
            lines.append(f"    Group key: {event.get('group_key')}")
        if event.get("evidence"):
            lines.append(f"    Technical evidence: {event.get('evidence')}")
        lines.append("-" * 110)
    lines.append("=" * 110)
    return "\n".join(lines)
