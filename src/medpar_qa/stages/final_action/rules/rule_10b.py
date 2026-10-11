"""Implement the Final Action rule 10b applicability predicate and resulting record KEEP/DROP
decisions. Router precedence determines when this rule is reached.
"""
from __future__ import annotations

from medpar_qa.enums import RecordDecision, ValidationStatus

from ..context import FinalActionGroupContext
from .base import FinalActionRule, RuleEvaluation
from .helpers import keep_first_non_qc0


class Rule10BQC5Fallback(FinalActionRule):
    """QC5 exists, the group is not the simple Rule-6 pair and Rule-10A count condition is false.
    Keep the newest non-QC0 only and drop the rest, without comparing ICNs.
    """
    rule_id = "FA-RULE-10B"

    def __init__(self, settings=None):
        self.requires_latest_qc0 = bool(settings and settings.rule10a_requires_latest_qc0)

    def applies(self, context: FinalActionGroupContext) -> bool:
        """Test this route prerequisite: QC5 exists, the group is not the simple Rule-6 pair and
        Rule-10A count condition is false. Earlier router matches take precedence.
        """
        simple_rule6_group = context.count == 2 and set(context.query_codes) == {0, 5}
        rule10a_condition = (
            context.qc_count(0) > context.qc_count(5)
            and (not self.requires_latest_qc0 or context.latest_qc == 0)
        )
        return context.has_qc5 and not simple_rule6_group and not rule10a_condition

    def evaluate(self, context: FinalActionGroupContext) -> RuleEvaluation:
        """Keep the newest non-QC0 only and drop the rest, without comparing ICNs. Return
        RuleEvaluation with its outcome and any explicit record decisions.
        """
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
