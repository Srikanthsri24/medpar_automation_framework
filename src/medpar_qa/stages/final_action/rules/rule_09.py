from __future__ import annotations

from medpar_qa.enums import RecordDecision, ValidationStatus

from ..context import FinalActionGroupContext
from .base import FinalActionRule, RuleEvaluation
from .helpers import keep_unique_non_qc0_icns


class Rule09NoQC5LatestNonQC0(FinalActionRule):
    rule_id = "FA-RULE-09"

    def applies(self, context: FinalActionGroupContext) -> bool:
        return (
            not context.has_qc5
            and context.latest_qc != 0
            and context.qc_count(0) < context.qc_count(1) + context.qc_count(3)
        )

    def evaluate(self, context: FinalActionGroupContext) -> RuleEvaluation:
        decisions = keep_unique_non_qc0_icns(context, self.rule_id)
        keep_count = sum(item.decision == RecordDecision.KEEP for item in decisions)
        return RuleEvaluation(
            self._result(
                context,
                status=ValidationStatus.PASS,
                message="No-QC5 group with latest non-QC0 processed using ICN comparison",
                expected={"keep": keep_count, "drop": context.count - keep_count},
                actual={"keep": keep_count, "drop": context.count - keep_count},
                evidence={"qc_counts": dict(context.qc_counts)},
            ),
            decisions,
        )
