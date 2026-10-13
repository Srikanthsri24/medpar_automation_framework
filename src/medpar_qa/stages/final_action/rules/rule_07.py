"""Implement the Final Action rule 07 applicability predicate and resulting record KEEP/DROP
decisions. Router precedence determines when this rule is reached.
"""
from __future__ import annotations

from medpar_qa.enums import RecordDecision, ValidationStatus

from ..context import FinalActionGroupContext
from .base import FinalActionRule, RuleEvaluation
from .helpers import keep_unique_non_qc0_icns


class Rule07NoQC5QC0Dominates(FinalActionRule):
    """No QC5 exists and QC0 count is at least QC1 plus QC3 counts, after earlier routes. Drop QC0
    and cancelled ICNs and older duplicates; keep only non-QC0 records selected newest per distinct non-cancelled ICN across the
    complete group.
    """
    rule_id = "FA-RULE-07"

    def applies(self, context: FinalActionGroupContext) -> bool:
        """Test this route prerequisite: No QC5 exists and QC0 count is at least QC1 plus QC3
        counts, after earlier routes. Earlier router matches take precedence.
        """
        return (
            not context.has_qc5
            and context.qc_count(0) >= context.qc_count(1) + context.qc_count(3)
        )

    def evaluate(self, context: FinalActionGroupContext) -> RuleEvaluation:
        """Drop QC0 and cancelled ICNs and older duplicates; keep only non-QC0 records selected newest per distinct non-cancelled ICN
        across the complete group. Return RuleEvaluation with its outcome and any explicit
        record decisions.
        """
        decisions = keep_unique_non_qc0_icns(context, self.rule_id)
        keep_count = sum(item.decision == RecordDecision.KEEP for item in decisions)
        return RuleEvaluation(
            self._result(
                context,
                status=ValidationStatus.PASS,
                message="No-QC5 group processed using QC0-dominance and ICN comparison",
                expected={"keep": keep_count, "drop": context.count - keep_count},
                actual={"keep": keep_count, "drop": context.count - keep_count},
                evidence={"qc_counts": dict(context.qc_counts)},
            ),
            decisions,
        )
