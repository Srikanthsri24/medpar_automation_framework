from __future__ import annotations

from medpar_qa.enums import RecordDecision, ValidationStatus

from ..context import FinalActionGroupContext
from ..settings import FinalActionSettings
from .base import FinalActionRule, RuleEvaluation


class Rule01SingleClaim(FinalActionRule):
    rule_id = "FA-RULE-01"

    def __init__(self, settings: FinalActionSettings) -> None:
        self.settings = settings

    def applies(self, context: FinalActionGroupContext) -> bool:
        return context.count == 1

    def evaluate(self, context: FinalActionGroupContext) -> RuleEvaluation:
        qc = context.query_codes[0]
        if qc == 0:
            decision = RecordDecision.DROP
        elif qc in self.settings.rule1_keep_qcs:
            decision = RecordDecision.KEEP
        else:
            return RuleEvaluation(
                self._result(
                    context,
                    status=ValidationStatus.FAIL,
                    message=f"Single-record query code {qc} is not approved",
                    expected=list(self.settings.rule1_keep_qcs),
                    actual=qc,
                )
            )

        claim_decision = self._decision(
            context,
            0,
            decision,
            f"Single-record QC={qc}",
        )
        return RuleEvaluation(
            self._result(
                context,
                status=ValidationStatus.PASS,
                message=f"Single-record claim routed to {decision.value}",
                expected=decision.value,
                actual=decision.value,
                evidence={"query_code": qc},
            ),
            (claim_decision,),
        )
