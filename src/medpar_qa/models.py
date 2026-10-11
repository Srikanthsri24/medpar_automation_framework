"""Shared dataclasses for source lineage, validation evidence, record decisions, manifests and
stage results. They carry evidence between components.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
import inspect

from .enums import FileRole, RecordDecision, Stage, ValidationStatus


@dataclass(frozen=True)
class SourceLocation:
    """Represent source location with the fields and methods declared below. Declared dataclass
    fields are the component contract.
    """
    file_path: str
    row_number: int
    file_format: str
    stage: Stage
    role: FileRole


@dataclass
class SourceRecord:
    """Represent source record with the fields and methods declared below. Declared dataclass
    fields are the component contract.
    """
    data: dict[str, Any]
    source: SourceLocation
    record_id: str


@dataclass
class RuleResult:
    """Represent one Final Action decision-tree route; applies tests eligibility and evaluate
    returns auditable group/record decisions.
    """
    stage: Stage
    rule_id: str
    status: ValidationStatus
    message: str
    expected: Any = None
    actual: Any = None
    field_name: str | None = None
    record_ids: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    group_key: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Capture the real Python function that emitted this validation. This gives
        # reports function-level traceability without forcing every validator call
        # to repeat its own function name.
        """Capture construction-time validation provenance/events for reporting; reporting
        exceptions are contained so evidence capture cannot change business decisions.
        """
        if "validator_function" not in self.evidence:
            frame = inspect.currentframe()
            caller = frame.f_back if frame is not None else None
            call_chain: list[str] = []
            first_project_caller = None
            first_any_caller = None
            while caller is not None and len(call_chain) < 8:
                module = caller.f_globals.get("__name__", "unknown")
                function_name = caller.f_code.co_name
                is_useful = (
                    function_name not in {"__init__", "__post_init__"}
                    and not module.startswith("dataclasses")
                )
                if is_useful and first_any_caller is None:
                    first_any_caller = caller
                if is_useful and module.startswith("medpar_qa"):
                    call_chain.append(f"{module}.{function_name}:{caller.f_lineno}")
                    if first_project_caller is None:
                        first_project_caller = caller
                caller = caller.f_back
            selected_caller = first_project_caller or first_any_caller
            if selected_caller is not None:
                module = selected_caller.f_globals.get("__name__", "unknown")
                self.evidence["validator_function"] = (
                    f"{module}.{selected_caller.f_code.co_name}"
                )
                self.evidence["source_line"] = selected_caller.f_lineno
                if not call_chain:
                    call_chain = [
                        f"{module}.{selected_caller.f_code.co_name}:{selected_caller.f_lineno}"
                    ]
                self.evidence["validator_call_chain"] = call_chain
        try:
            from .reporting.event_recorder import record_event

            payload = self.to_dict()
            payload["event_type"] = "validation"
            record_event(payload)
        except Exception:
            # Reporting must never alter business-rule execution.
            pass

        from .orchestration.execution_control import observe
        observe(self)

    def to_dict(self) -> dict[str, Any]:
        """Convert this evidence model into JSON-ready data with enum values represented as
        strings.
        """
        payload = asdict(self)
        payload["stage"] = self.stage.value
        payload["status"] = self.status.value
        return payload


@dataclass
class ClaimDecision:
    """Represent claim decision with the fields and methods declared below. Declared dataclass
    fields are the component contract.
    """
    record_id: str
    decision: RecordDecision
    rule_id: str
    reason: str

    def __post_init__(self) -> None:
        """Capture construction-time validation provenance/events for reporting; reporting
        exceptions are contained so evidence capture cannot change business decisions.
        """
        try:
            from .reporting.event_recorder import record_event

            record_event(
                {
                    "event_type": "decision",
                    "record_id": self.record_id,
                    "decision": self.decision.value,
                    "rule_id": self.rule_id,
                    "reason": self.reason,
                }
            )
        except Exception:
            pass

        from .orchestration.execution_control import observe
        observe(self)


@dataclass
class StageResult:
    """Represent stage result with the fields and methods declared below. Declared fields document
    the component contract.
    """
    stage: Stage
    rule_results: list[RuleResult] = field(default_factory=list)
    decisions: list[ClaimDecision] = field(default_factory=list)

    @property
    def status_counts(self) -> dict[str, int]:
        """Count each validation status across this stage; counts are rule outcomes, not patient
        counts.
        """
        counts = {status.value: 0 for status in ValidationStatus}
        for result in self.rule_results:
            counts[result.status.value] += 1
        return counts

    @property
    def passed(self) -> bool:
        """Return true only when this stage has neither FAIL nor BLOCKED results; N/A is not a
        successful calculation.
        """
        return not any(
            result.status in {ValidationStatus.FAIL, ValidationStatus.BLOCKED}
            for result in self.rule_results
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert this evidence model into JSON-ready data with enum values represented as
        strings.
        """
        return {
            "stage": self.stage.value,
            "passed": self.passed,
            "rule_results": [item.to_dict() for item in self.rule_results],
            "decisions": [
                {
                    "record_id": item.record_id,
                    "decision": item.decision.value,
                    "rule_id": item.rule_id,
                    "reason": item.reason,
                }
                for item in self.decisions
            ],
        }


@dataclass(frozen=True)
class ManifestFile:
    """Represent manifest file with the fields and methods declared below. Declared dataclass
    fields are the component contract.
    """
    path: str
    stage: Stage
    role: FileRole
    format: str | None = None


@dataclass
class RunManifest:
    """Represent run manifest with the fields and methods declared below. Declared fields document
    the component contract.
    """
    run_id: str
    run_date: date
    files: list[ManifestFile]
    settings: dict[str, Any] = field(default_factory=dict)
    base_directory: Path = field(default_factory=Path.cwd)
