from __future__ import annotations

from medpar_qa.enums import ValidationStatus

from ..context import FinalActionGroupContext
from .base import FinalActionRule, RuleEvaluation
from .helpers import drop_all


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
            qc0_icn = context.icns[context.query_codes.index(0)]
            keep_index = next(
                (i for i, (qc, icn) in enumerate(zip(context.query_codes, context.icns))
                 if qc != 0 and icn != qc0_icn),
                None,
            )
            if keep_index is None:
                return RuleEvaluation(self._result(
                    context, status=ValidationStatus.BLOCKED,
                    message="Rule 5: differing ICNs but no non-QC0 ICN distinct from QC0",
                    evidence={"icns": list(context.icns)},
                ))
            from medpar_qa.enums import RecordDecision
            decisions = tuple(self._decision(
                context, i,
                RecordDecision.KEEP if i == keep_index else RecordDecision.DROP,
                "Rule 5: newest non-QC0 with ICN different from QC0"
                if i == keep_index else "Rule 5: not selected",
            ) for i in range(context.count))
            message = "Newest non-QC0 with ICN different from QC0 retained"

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
