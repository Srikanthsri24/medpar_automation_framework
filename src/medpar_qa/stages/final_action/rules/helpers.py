"""Shared DROP-all, newest non-QC0 and eligible unique non-QC0 ICN decision constructors."""
from __future__ import annotations

from medpar_qa.enums import RecordDecision
from medpar_qa.models import ClaimDecision

from ..context import FinalActionGroupContext


def drop_all(context: FinalActionGroupContext, rule_id: str, reason: str) -> tuple[ClaimDecision, ...]:
    """Construct DROP decisions for every claim in the supplied group."""
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
    """Retain the newest eligible non-QC0 claim and drop the remaining claims."""
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
    """Keep the newest claim per distinct ICN not present on a QC0 cancellation.

    User decision: revised tree precedence and newest-per-distinct non-cancelled ICN.
    """

    cancelled = {icn for qc,icn in zip(context.query_codes,context.icns) if qc==0}
    seen=set()
    decisions: list[ClaimDecision] = []
    for record, qc, icn in zip(context.records, context.query_codes, context.icns):
        if qc == 0:
            decision = RecordDecision.DROP
            reason = "QC0 records are dropped"
        elif icn not in cancelled and icn not in seen:
            decision = RecordDecision.KEEP
            seen.add(icn)
            reason = "Newest non-QC0 record for this distinct non-cancelled ICN"
        else:
            decision = RecordDecision.DROP
            reason = "ICN cancelled by QC0 or superseded by a newer non-QC0 claim"
        decisions.append(ClaimDecision(record.record_id, decision, rule_id, reason))
    return tuple(decisions)
