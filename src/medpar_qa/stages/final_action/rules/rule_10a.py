"""Implement the Final Action rule 10a applicability predicate and resulting record KEEP/DROP
decisions. Router precedence determines when this rule is reached.
"""
from __future__ import annotations

from medpar_qa.enums import RecordDecision, ValidationStatus

from ..context import FinalActionGroupContext
from .base import FinalActionRule, RuleEvaluation
from .helpers import keep_unique_non_qc0_icns


class Rule10AQC5QC0Dominates(FinalActionRule):
    """QC5 exists, the group is not the simple Rule-6 pair and QC0 count exceeds QC5 count,
    irrespective of newest QC. Drop QC0 and repeated ICNs; keep only non-QC0 records whose ICN
    occurs exactly once across the complete group.
    """
    rule_id = "FA-RULE-10A"

    def applies(self, context: FinalActionGroupContext) -> bool:
        """Test this route prerequisite: QC5 exists, the group is not the simple Rule-6 pair and
        QC0 count exceeds QC5 count, irrespective of newest QC. Earlier router matches take
        precedence.
        """
        simple_rule6_group = context.count == 2 and set(context.query_codes) == {0, 5}
        return (
            context.has_qc5
            and not simple_rule6_group
            and context.qc_count(0) > context.qc_count(5)
        )

    def evaluate(self, context: FinalActionGroupContext) -> RuleEvaluation:
        """Drop QC0 and repeated ICNs; keep only non-QC0 records whose ICN occurs exactly once
        across the complete group. Return RuleEvaluation with its outcome and any explicit
        record decisions.
        """
        decisions = keep_unique_non_qc0_icns(context, self.rule_id)
        keep_count = sum(item.decision == RecordDecision.KEEP for item in decisions)
        return RuleEvaluation(
            self._result(
                context,
                status=ValidationStatus.PASS,
                message="QC5 group processed using Rule 10A ICN comparison",
                expected={"keep": keep_count, "drop": context.count - keep_count},
                actual={"keep": keep_count, "drop": context.count - keep_count},
                evidence={"qc_counts": dict(context.qc_counts),
                          "requirement": "MM-FINAC-16A/B" if context.latest_qc == 0 else "MM-FINAC-16C/D/E",
                          "precedence": "Specific QC0>QC5 condition precedes general MM-FINAC-14 fallback"},
            ),
            decisions,
        )
