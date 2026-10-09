from __future__ import annotations

from medpar_qa.enums import RecordDecision, ValidationStatus

from ..context import FinalActionGroupContext
from .base import FinalActionRule, RuleEvaluation
from .helpers import keep_first_non_qc0


class Rule10BQC5Fallback(FinalActionRule):
    rule_id = "FA-RULE-10B"

    def applies(self, context: FinalActionGroupContext) -> bool:
        simple_rule6_group = context.count == 2 and set(context.query_codes) == {0, 5}
        rule10a_condition = (
            context.latest_qc == 0 and context.qc_count(0) > context.qc_count(5)
        )
        return context.has_qc5 and not simple_rule6_group and not rule10a_condition

    def evaluate(self, context: FinalActionGroupContext) -> RuleEvaluation:
        decisions = keep_first_non_qc0(
            context,
            self.rule_id,
            "Newest non-QC0 record retained by Rule 10B",
            "Remaining Rule 10B record dropped",
        )
        keep_count = sum(item.decision == RecordDecision.KEEP for item in decisions)
        return RuleEvaluation(
            self._result(
                context,
                status=ValidationStatus.PASS,
                message="Rule 10B retained the newest non-QC0 record without ICN comparison",
                expected={"keep": 1, "drop": context.count - 1},
                actual={"keep": keep_count, "drop": context.count - keep_count},
            ),
            decisions,
        )
