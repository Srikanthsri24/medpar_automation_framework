"""Implement the Final Action rule 01 applicability predicate and resulting record KEEP/DROP
decisions. Router precedence determines when this rule is reached.
"""
from __future__ import annotations

from medpar_qa.enums import RecordDecision, ValidationStatus

from ..context import FinalActionGroupContext
from ..settings import FinalActionSettings
from .base import FinalActionRule, RuleEvaluation


class Rule01SingleClaim(FinalActionRule):
    """The group contains exactly one claim. Keep default-approved QC1/3/5, drop QC0, and fail a QC
    outside the configured keep domain.
    """
    rule_id = "FA-RULE-01"

    def __init__(self, settings: FinalActionSettings) -> None:
        """Initialize this Rule01SingleClaim with the supplied dependencies/configuration and the
        assignments in its constructor.
        """
        self.settings = settings

    def applies(self, context: FinalActionGroupContext) -> bool:
        """Test this route prerequisite: The group contains exactly one claim. Earlier router
        matches take precedence.
        """
        return context.count == 1

    def evaluate(self, context: FinalActionGroupContext) -> RuleEvaluation:
        """Keep default-approved QC1/3/5, drop QC0, and fail a QC outside the configured keep
        domain. Return RuleEvaluation with its outcome and any explicit record decisions.
        """
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
