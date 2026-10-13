"""Derive IP/SNF record type and group Final Action claims by approved identity; admission date is
deliberately absent from this Final Action key.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from medpar_qa.models import SourceRecord
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.fields import FieldResolver


GroupKey = tuple[str, str, str, date, date]


def derive_record_type(transaction_code: Any, *, validate_transaction_codes: bool = True) -> str:
    """Map the transaction code to the approved IP/SNF type for Final Action grouping."""
    try:
        code = int(transaction_code)
    except (TypeError, ValueError) as exc:
        if not validate_transaction_codes:
            return f"UNCLASSIFIED:{str(transaction_code).strip()}"
        raise ValueError(f"Invalid transaction code: {transaction_code!r}") from exc

    if code in {1, 2, 3}:
        return "I"
    if code in {0, 4}:
        return "S"
    if not validate_transaction_codes:
        return f"UNCLASSIFIED:{code}"
    raise ValueError(f"Unsupported transaction code: {code}")


def build_group_key(
    record: SourceRecord, resolver: FieldResolver, *, validate_transaction_codes: bool = True
) -> GroupKey:
    """Build the Final Action record-type/HICN/provider/from/thru identity; admission date does not
    split this claim group.
    """
    # While TC validation is deferred, TC cannot define different bill cohorts.
    # DEV RICID identifies IP/SNF independently. With no RICID, omit the type
    # discriminator rather than split a cancellation pair using an invalid TC.
    if not validate_transaction_codes:
        ricid = resolver.get(record.data, "ricid")
        rec_type = {"1": "I", "2": "S"}.get(str(ricid).strip(), "TYPE_NOT_USED")
    else:
        rec_type = derive_record_type(resolver.get(record.data, "transaction_code"))
    ric = resolver.get(record.data, "ric")
    if isinstance(ric, dict):
        ric = ric.get("code", ric.get("id"))
    if ric is None:
        ric = resolver.get(record.data, "ricid")
    if ric not in (None, ""):
        rec_type = "RIC:" + str(ric).strip()
    hicn = str(resolver.get(record.data, "hicn", "")).strip()
    provider_id = str(resolver.get(record.data, "provider_id", "")).strip()
    stay_from = parse_date(resolver.get(record.data, "stay_from_date"))
    stay_thru = parse_date(resolver.get(record.data, "stay_thru_date"))
    return rec_type, hicn, provider_id, stay_from, stay_thru


def group_key_to_dict(key: GroupKey) -> dict[str, Any]:
    """Label the Final Action identity tuple so the report explains each group-key component."""
    return {
        "rec_type": key[0],
        "hicn": key[1],
        "provider_id": key[2],
        "stay_from_date": key[3].isoformat(),
        "stay_thru_date": key[4].isoformat(),
    }


def group_records(
    records: list[SourceRecord], resolver: FieldResolver
) -> dict[GroupKey, list[SourceRecord]]:
    """Bucket source claims under their Final Action business group key."""
    grouped: dict[GroupKey, list[SourceRecord]] = defaultdict(list)
    for record in records:
        grouped[build_group_key(record, resolver)].append(record)
    return dict(grouped)
