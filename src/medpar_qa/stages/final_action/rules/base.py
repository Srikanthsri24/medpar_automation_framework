from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from medpar_qa.enums import RecordDecision, Stage, ValidationStatus
from medpar_qa.models import ClaimDecision, RuleResult

from ..context import FinalActionGroupContext


@dataclass(frozen=True)
class RuleEvaluation:
    rule_result: RuleResult
    decisions: tuple[ClaimDecision, ...] = ()


class FinalActionRule(ABC):
    rule_id: str

    @abstractmethod
    def applies(self, context: FinalActionGroupContext) -> bool:
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, context: FinalActionGroupContext) -> RuleEvaluation:
        raise NotImplementedError

    def _decision(
        self,
        context: FinalActionGroupContext,
        index: int,
        decision: RecordDecision,
        reason: str,
    ) -> ClaimDecision:
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
