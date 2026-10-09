from __future__ import annotations

from medpar_qa.enums import RecordDecision
from medpar_qa.models import ClaimDecision

from ..context import FinalActionGroupContext


def drop_all(context: FinalActionGroupContext, rule_id: str, reason: str) -> tuple[ClaimDecision, ...]:
    return tuple(
        ClaimDecision(record.record_id, RecordDecision.DROP, rule_id, reason)
        for record in context.records
    )


def keep_first_non_qc0(
    context: FinalActionGroupContext,
    rule_id: str,
    keep_reason: str,
    drop_reason: str,
) -> tuple[ClaimDecision, ...]:
    keep_index = next(
        (index for index, qc in enumerate(context.query_codes) if qc != 0),
        None,
    )
    return tuple(
        ClaimDecision(
            record.record_id,
            RecordDecision.KEEP if index == keep_index else RecordDecision.DROP,
            rule_id,
            keep_reason if index == keep_index else drop_reason,
        )
        for index, record in enumerate(context.records)
    )


def keep_unique_non_qc0_icns(
    context: FinalActionGroupContext,
    rule_id: str,
) -> tuple[ClaimDecision, ...]:
    """Keep only non-QC0 records whose ICN occurs once in the full group.

    This follows the supplied wording "non-QC0 records with non-matching
    control numbers". If the business owner later means "newest per ICN",
    this helper is the only place that needs changing for Rules 7/8/9/10A.
    """

    icn_counts = context.icn_counts
    decisions: list[ClaimDecision] = []
    for record, qc, icn in zip(context.records, context.query_codes, context.icns):
        if qc == 0:
            decision = RecordDecision.DROP
            reason = "QC0 records are dropped"
        elif icn_counts[icn] == 1:
            decision = RecordDecision.KEEP
            reason = "Non-QC0 record has a non-matching ICN"
        else:
            decision = RecordDecision.DROP
            reason = "ICN matches another record in the group"
        decisions.append(ClaimDecision(record.record_id, decision, rule_id, reason))
    return tuple(decisions)
