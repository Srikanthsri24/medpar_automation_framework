from __future__ import annotations

from medpar_qa.enums import RecordDecision, ValidationStatus

from ..context import FinalActionGroupContext
from .base import FinalActionRule, RuleEvaluation


class Rule02ThreeClaimSequence(FinalActionRule):
    rule_id = "FA-RULE-02"
    _VALID_SEQUENCES = {(5, 0, 3), (5, 0, 1)}

    def applies(self, context: FinalActionGroupContext) -> bool:
        return context.count == 3 and context.query_codes in self._VALID_SEQUENCES

    def evaluate(self, context: FinalActionGroupContext) -> RuleEvaluation:
        decisions = tuple(
            self._decision(
                context,
                index,
                RecordDecision.KEEP if index == 0 else RecordDecision.DROP,
                "Newest QC5 retained" if index == 0 else "Non-final transaction dropped",
            )
            for index in range(context.count)
        )
        return RuleEvaluation(
            self._result(
                context,
                status=ValidationStatus.PASS,
                message="Valid 5-0-3/5-0-1 sequence; newest QC5 retained",
                expected={"sequence": list(context.query_codes), "keep_index": 0},
                actual={"sequence": list(context.query_codes), "keep_index": 0},
            ),
            decisions,
        )
