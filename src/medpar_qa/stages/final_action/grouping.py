from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from medpar_qa.models import SourceRecord
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.fields import FieldResolver


GroupKey = tuple[str, str, str, date, date]


def derive_record_type(transaction_code: Any) -> str:
    try:
        code = int(transaction_code)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid transaction code: {transaction_code!r}") from exc

    if code in {1, 2, 3}:
        return "I"
    if code in {0, 4, 6}:
        return "S"
    raise ValueError(f"Unsupported transaction code: {code}")


def build_group_key(record: SourceRecord, resolver: FieldResolver) -> GroupKey:
    rec_type = derive_record_type(resolver.get(record.data, "transaction_code"))
    hicn = str(resolver.get(record.data, "hicn", "")).strip()
    provider_id = str(resolver.get(record.data, "provider_id", "")).strip()
    stay_from = parse_date(resolver.get(record.data, "stay_from_date"))
    stay_thru = parse_date(resolver.get(record.data, "stay_thru_date"))
    return rec_type, hicn, provider_id, stay_from, stay_thru


def group_key_to_dict(key: GroupKey) -> dict[str, Any]:
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
    grouped: dict[GroupKey, list[SourceRecord]] = defaultdict(list)
    for record in records:
        grouped[build_group_key(record, resolver)].append(record)
    return dict(grouped)
