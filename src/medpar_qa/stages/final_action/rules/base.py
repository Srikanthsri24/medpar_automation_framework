"""Rule interface and constructors for per-record ClaimDecision and per-group
RuleResult/RuleEvaluation.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from medpar_qa.enums import RecordDecision, Stage, ValidationStatus
from medpar_qa.models import ClaimDecision, RuleResult

from ..context import FinalActionGroupContext


@dataclass(frozen=True)
class RuleEvaluation:
    """Carry one selected rule result and its explicit claim KEEP/DROP decisions.
    An unresolved evaluation can have no decisions.
    """
    rule_result: RuleResult
    decisions: tuple[ClaimDecision, ...] = ()


class FinalActionRule(ABC):
    """Declare the abstract rule interface and shared result/decision constructors.
    Concrete rules must implement applies and evaluate.
    """
    rule_id: str

    @abstractmethod
    def applies(self, context: FinalActionGroupContext) -> bool:
        """Declare the eligibility predicate returning bool; concrete rules implement it.
        """
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, context: FinalActionGroupContext) -> RuleEvaluation:
        """Declare the evaluation contract returning RuleEvaluation; concrete rules implement it.
        """
        raise NotImplementedError

    def _decision(
        self,
        context: FinalActionGroupContext,
        index: int,
        decision: RecordDecision,
        reason: str,
    ) -> ClaimDecision:
        """Create one auditable KEEP/DROP decision with the selected rule ID and reason."""
        return ClaimDecision(
            record_id=context.records[index].record_id,
            decision=decision,
            rule_id=self.rule_id,
            reason=reason,
        )

    def _result(
        self,
        context: FinalActionGroupContext,
        *,
        status: ValidationStatus,
        message: str,
        expected=None,
        actual=None,
        evidence=None,
    ) -> RuleResult:
        """Create the selected rule outcome with group, record and source-file evidence."""
        return RuleResult(
            stage=Stage.FINAL_ACTION,
            rule_id=self.rule_id,
            status=status,
            message=message,
            expected=expected,
            actual=actual,
            record_ids=[record.record_id for record in context.records],
            source_files=sorted({record.source.file_path for record in context.records}),
            group_key=context.group_key,
            evidence=evidence or {},
        )
