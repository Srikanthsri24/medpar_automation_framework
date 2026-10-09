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
        decisions = keep_first_non_qc0(
            context,
            self.rule_id,
            "Newest non-zero QC retained by default rule",
            "Remaining default-rule record dropped",
        )
        keep_count = sum(item.decision == RecordDecision.KEEP for item in decisions)
        status = ValidationStatus.PASS if keep_count == 1 else ValidationStatus.FAIL
        return RuleEvaluation(
            self._result(
                context,
                status=status,
                message=(
                    "Default rule retained the newest non-zero QC record"
                    if keep_count == 1
                    else "Default rule could not find a non-zero QC record"
                ),
                expected=1,
                actual=keep_count,
            ),
            decisions,
        )
