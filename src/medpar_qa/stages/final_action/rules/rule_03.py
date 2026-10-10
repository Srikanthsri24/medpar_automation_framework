"""Implement the Final Action rule 03 applicability predicate and resulting record KEEP/DROP
decisions. Router precedence determines when this rule is reached.
"""
from __future__ import annotations

from medpar_qa.enums import RecordDecision, ValidationStatus

from ..context import FinalActionGroupContext
from .base import FinalActionRule, RuleEvaluation


class Rule03SameQueryCode(FinalActionRule):
    """More than one claim has the same QC, after earlier router matches. Keep the newest
    occurrence of each distinct ICN and drop older occurrences of that ICN.
    """
    rule_id = "FA-RULE-03"

    def applies(self, context: FinalActionGroupContext) -> bool:
        """Test this route prerequisite: More than one claim has the same QC, after earlier router
        matches. Earlier router matches take precedence.
        """
        return context.count > 1 and context.all_query_codes_same

    def evaluate(self, context: FinalActionGroupContext) -> RuleEvaluation:
        """Keep the newest occurrence of each distinct ICN and drop older occurrences of that ICN.
        Return RuleEvaluation with its outcome and any explicit record decisions.
        """
        seen_icns: set[str] = set()
        decisions = []
        for index, icn in enumerate(context.icns):
            if icn in seen_icns:
                decision = RecordDecision.DROP
                reason = "Older duplicate ICN"
            else:
                seen_icns.add(icn)
                decision = RecordDecision.KEEP
                reason = "Newest record for this ICN"
            decisions.append(self._decision(context, index, decision, reason))

        keep_count = len(seen_icns)
        return RuleEvaluation(
            self._result(
                context,
                status=ValidationStatus.PASS,
                message="Same-QC group retained newest record for each unique ICN",
                expected=keep_count,
                actual=sum(item.decision == RecordDecision.KEEP for item in decisions),
                evidence={
                    "query_code": context.query_codes[0],
                    "unique_icns": sorted(seen_icns),
                },
            ),
            tuple(decisions),
        )
