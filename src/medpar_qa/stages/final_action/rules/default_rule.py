"""Implement the Final Action default rule applicability predicate and resulting record KEEP/DROP
decisions. Router precedence determines when this rule is reached.
"""
from __future__ import annotations

from medpar_qa.enums import RecordDecision, ValidationStatus

from ..context import FinalActionGroupContext
from .base import FinalActionRule, RuleEvaluation
from .helpers import keep_first_non_qc0


class DefaultFinalActionRule(FinalActionRule):
    """The fallback always matches, but is selected only when all prior predicates are false.
    Return BLOCKED with no inferred record decisions; require an approved decision-tree route.
    """
    rule_id = "FA-DEFAULT"

    def applies(self, context: FinalActionGroupContext) -> bool:
        """Test this route prerequisite: The fallback always matches, but is selected only when all
        prior predicates are false. Earlier router matches take precedence.
        """
        return True

    def evaluate(self, context: FinalActionGroupContext) -> RuleEvaluation:
        """Return BLOCKED with no inferred record decisions; require an approved decision-tree
        route. Return RuleEvaluation with its outcome and any explicit record decisions.
        """
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
