from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from medpar_qa.models import SourceRecord
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.fields import FieldResolver


@dataclass(frozen=True, order=True)
class BusinessOrderKey:
    processing_date: date
    accrete_date: date
    source_sequence: int


@dataclass(frozen=True)
class OrderingResult:
    ordered_records: tuple[SourceRecord, ...]
    ambiguous_record_ids: tuple[str, ...] = ()

    @property
    def is_ambiguous(self) -> bool:
        return bool(self.ambiguous_record_ids)


def _as_sequence(value: Any) -> int:
    if value is None or value == "":
        return -1
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid source sequence: {value!r}") from exc


def business_order_key(record: SourceRecord, resolver: FieldResolver) -> BusinessOrderKey:
    processing = parse_date(resolver.get(record.data, "processing_date"))
    accrete = parse_date(
        resolver.get(record.data, "accrete_date"), allow_none=True
    ) or date.min
    sequence = _as_sequence(resolver.get(record.data, "source_sequence"))
    return BusinessOrderKey(processing, accrete, sequence)


def order_newest_first(
    records: list[SourceRecord], resolver: FieldResolver
) -> OrderingResult:
    decorated = [(business_order_key(record, resolver), record) for record in records]
    decorated.sort(key=lambda item: item[0], reverse=True)

    duplicate_keys: dict[BusinessOrderKey, list[str]] = {}
    for key, record in decorated:
        duplicate_keys.setdefault(key, []).append(record.record_id)

    ambiguous = tuple(
        record_id
        for ids in duplicate_keys.values()
        if len(ids) > 1
        for record_id in ids
    )
    return OrderingResult(
        ordered_records=tuple(record for _, record in decorated),
        ambiguous_record_ids=ambiguous,
    )
