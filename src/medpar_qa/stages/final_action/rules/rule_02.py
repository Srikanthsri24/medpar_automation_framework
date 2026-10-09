from __future__ import annotations

from medpar_qa.enums import RecordDecision, ValidationStatus

from ..context import FinalActionGroupContext
from .base import FinalActionRule, RuleEvaluation


class Rule02ThreeClaimSequence(FinalActionRule):
    rule_id = "FA-RULE-02"
    _VALID_SEQUENCES = {(5, 0, 3), (5, 0, 1)}

    def applies(self, context: FinalActionGroupContext) -> bool:
        if context.count != 3 or context.query_codes not in self._VALID_SEQUENCES:
            return False
        # V3 page 20 requires QC5 to have the greatest accretion date.
        # If accretion ordering is not established, do not apply Rule 2.
        from medpar_qa.normalization.dates import parse_date
        # The records are ordered by processing date; the schema exposes
        # canonical accretion aliases via the same resolver used by processor.
        def accrete(record):
            for key in ("accreteDate", "accrete_date", "accretionDate"):
                if key in record.data and record.data[key] not in (None, ""):
                    return parse_date(record.data[key])
            return None
        dates = [accrete(record) for record in context.records]
        return all(value is not None for value in dates) and dates[0] == max(dates)

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
