"""Implement the Final Action all qc0 applicability predicate and resulting record KEEP/DROP
decisions. Router precedence determines when this rule is reached.
"""
from __future__ import annotations

from medpar_qa.enums import ValidationStatus

from ..context import FinalActionGroupContext
from .base import FinalActionRule, RuleEvaluation
from .helpers import drop_all


class AllQC0Rule(FinalActionRule):
    """More than one claim and every QC is zero. Drop every claim in the group."""
    rule_id = "FA-ALL-QC0"

    def applies(self, context: FinalActionGroupContext) -> bool:
        """Test this route prerequisite: More than one claim and every QC is zero. Earlier router
        matches take precedence.
        """
        return context.count > 1 and set(context.query_codes) == {0}

    def evaluate(self, context: FinalActionGroupContext) -> RuleEvaluation:
        """Drop every claim in the group. Return RuleEvaluation with its outcome and any explicit
        record decisions.
        """
        decisions = drop_all(context, self.rule_id, "All records in the group are QC0")
        return RuleEvaluation(
            self._result(
                context,
                status=ValidationStatus.PASS,
                message="All-QC0 group dropped",
                expected={"keep": 0, "drop": context.count},
                actual={"keep": 0, "drop": context.count},
            ),
            decisions,
        )
