from __future__ import annotations

from medpar_qa.enums import RecordDecision, ValidationStatus

from ..context import FinalActionGroupContext
from .base import FinalActionRule, RuleEvaluation
from .helpers import keep_first_non_qc0


class DefaultFinalActionRule(FinalActionRule):
    rule_id = "FA-DEFAULT"

    def applies(self, context: FinalActionGroupContext) -> bool:
        return True

    def evaluate(self, context: FinalActionGroupContext) -> RuleEvaluation:
        decisions = ()
        keep_count = sum(item.decision == RecordDecision.KEEP for item in decisions)
        status = ValidationStatus.BLOCKED
        return RuleEvaluation(
            self._result(
                context,
                status=status,
                message=(
                    "No explicitly approved Final Action decision-tree path matches this group; manual review required"
                ),
                expected="Approved numbered rule",
                actual=keep_count,
            ),
            decisions,
        )
