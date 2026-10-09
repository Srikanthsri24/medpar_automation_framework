from __future__ import annotations

from medpar_qa.enums import RecordDecision, ValidationStatus

from ..context import FinalActionGroupContext
from .base import FinalActionRule, RuleEvaluation
from .helpers import keep_unique_non_qc0_icns


class Rule10AQC5QC0Dominates(FinalActionRule):
    rule_id = "FA-RULE-10A"

    def applies(self, context: FinalActionGroupContext) -> bool:
        simple_rule6_group = context.count == 2 and set(context.query_codes) == {0, 5}
        return (
            context.has_qc5
            and not simple_rule6_group
            and context.latest_qc == 0
            and context.qc_count(0) > context.qc_count(5)
        )

    def evaluate(self, context: FinalActionGroupContext) -> RuleEvaluation:
        decisions = keep_unique_non_qc0_icns(context, self.rule_id)
        keep_count = sum(item.decision == RecordDecision.KEEP for item in decisions)
        return RuleEvaluation(
            self._result(
                context,
                status=ValidationStatus.PASS,
                message="QC5 group processed using Rule 10A ICN comparison",
                expected={"keep": keep_count, "drop": context.count - keep_count},
                actual={"keep": keep_count, "drop": context.count - keep_count},
                evidence={"qc_counts": dict(context.qc_counts)},
            ),
            decisions,
        )
