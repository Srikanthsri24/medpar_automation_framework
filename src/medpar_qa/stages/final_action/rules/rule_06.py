from __future__ import annotations

from medpar_qa.enums import RecordDecision, ValidationStatus
from medpar_qa.models import ClaimDecision

from ..context import FinalActionGroupContext
from ..settings import FinalActionSettings
from .base import FinalActionRule, RuleEvaluation


class Rule06TwoClaimsQC0QC5(FinalActionRule):
    rule_id = "FA-RULE-06"

    def __init__(self, settings: FinalActionSettings) -> None:
        self.settings = settings

    def applies(self, context: FinalActionGroupContext) -> bool:
        return context.count == 2 and set(context.query_codes) == {0, 5}

    def evaluate(self, context: FinalActionGroupContext) -> RuleEvaluation:
        if not self.settings.rule6_enabled:
            return RuleEvaluation(
                self._result(
                    context,
                    status=ValidationStatus.BLOCKED,
                    message="Rule 6 is disabled in configuration",
                    expected="Enable Rule 6 after business approval",
                    actual={"rule6_enabled": False},
                )
            )

        qc0_index = context.query_codes.index(0)
        qc5_index = context.query_codes.index(5)
        qc0_record = context.records[qc0_index]
        qc5_record = context.records[qc5_index]
        same_control_number = context.icns[qc0_index] == context.icns[qc5_index]

        # The latest story calls this transactionCode, while the earlier flow
        # calls it Action Code. Because transactionCode can also determine the
        # record type/group, prefer an explicit 4/6 actionCode when present;
        # otherwise evaluate transactionCode. Both values remain in evidence.
        qc0_transaction = context.transaction_codes[qc0_index]
        qc0_action = context.action_codes[qc0_index]
        approved_drop_codes = set(self.settings.rule6_drop_codes)
        if qc0_action is not None and str(qc0_action) in approved_drop_codes:
            effective_code = qc0_action
            effective_code_source = "action_code"
        else:
            effective_code = qc0_transaction
            effective_code_source = "transaction_code"
        drop_both = same_control_number and str(effective_code) in approved_drop_codes

        if drop_both:
            decisions = [
                ClaimDecision(
                    record_id=record.record_id,
                    decision=RecordDecision.DROP,
                    rule_id=self.rule_id,
                    reason=(
                        "Rule 6: QC0 and QC5 control numbers match and the QC0 "
                        f"transaction/action code is {effective_code}; drop both"
                    ),
                )
                for record in context.records
            ]
            message = "Rule 6 dropped both records for matching control number and configured cancellation code"
        else:
            decisions = [
                ClaimDecision(
                    record_id=qc5_record.record_id,
                    decision=RecordDecision.KEEP,
                    rule_id=self.rule_id,
                    reason="Rule 6 keeps QC5 unless the matching-control-number cancellation condition applies",
                ),
                ClaimDecision(
                    record_id=qc0_record.record_id,
                    decision=RecordDecision.DROP,
                    rule_id=self.rule_id,
                    reason="Rule 6 drops QC0 when the drop-both cancellation condition does not apply",
                ),
            ]
            message = "Rule 6 kept QC5 and dropped QC0"

        return RuleEvaluation(
            self._result(
                context,
                status=ValidationStatus.PASS,
                message=message,
                expected={
                    "same_control_number_and_qc0_code_in": list(self.settings.rule6_drop_codes),
                    "then": "DROP BOTH",
                    "otherwise": "KEEP QC5 / DROP QC0",
                },
                actual={
                    "query_codes": list(context.query_codes),
                    "icns": list(context.icns),
                    "transaction_codes": list(context.transaction_codes),
                    "action_codes": list(context.action_codes),
                    "effective_qc0_code": effective_code,
                    "effective_qc0_code_source": effective_code_source,
                    "same_control_number": same_control_number,
                    "drop_both": drop_both,
                },
            ),
            decisions,
        )
