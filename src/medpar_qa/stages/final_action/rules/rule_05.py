from __future__ import annotations

from medpar_qa.enums import ValidationStatus

from ..context import FinalActionGroupContext
from .base import FinalActionRule, RuleEvaluation
from .helpers import drop_all, keep_first_non_qc0


class Rule05ThreeClaimsOneQC0NoQC5(FinalActionRule):
    rule_id = "FA-RULE-05"

    def applies(self, context: FinalActionGroupContext) -> bool:
        return (
            context.count == 3
            and not context.has_qc5
            and context.qc_count(0) == 1
        )

    def evaluate(self, context: FinalActionGroupContext) -> RuleEvaluation:
        if context.all_icns_same:
            decisions = drop_all(context, self.rule_id, "All ICNs are the same")
            message = "All ICNs matched; complete group dropped"
        else:
            decisions = keep_first_non_qc0(
                context,
                self.rule_id,
                "Newest non-QC0 record retained",
                "Remaining Rule 5 record dropped",
            )
            message = "Newest non-QC0 record retained after ICN comparison"

        keep_count = sum(item.decision.value == "KEEP" for item in decisions)
        return RuleEvaluation(
            self._result(
                context,
                status=ValidationStatus.PASS,
                message=message,
                expected={"keep": keep_count, "drop": context.count - keep_count},
                actual={"keep": keep_count, "drop": context.count - keep_count},
            ),
            decisions,
        )
