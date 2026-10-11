"""Sort by processing date, accretion date, query code and source sequence in descending order;
flag identical complete ordering keys.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from medpar_qa.models import SourceRecord
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.fields import FieldResolver


@dataclass(frozen=True, order=True)
class BusinessOrderKey:
    """Represent business order key with the fields and methods declared below. Declared dataclass
    fields are the component contract.
    """
    processing_date: date
    accrete_date: date
    query_code: int
    source_sequence: int


@dataclass(frozen=True)
class OrderingResult:
    """Represent ordering result with the fields and methods declared below. Declared dataclass
    fields are the component contract.
    """
    ordered_records: tuple[SourceRecord, ...]
    ambiguous_record_ids: tuple[str, ...] = ()
    equivalent_tie_record_ids: tuple[str, ...] = ()

    @property
    def is_ambiguous(self) -> bool:
        """Determine whether identical business ordering keys were found."""
        return bool(self.ambiguous_record_ids)


def _as_sequence(value: Any) -> int:
    """Parse the optional source sequence; use the explicit missing sentinel and reject invalid
    sequence text.
    """
    if value is None or value == "":
        return -1
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid source sequence: {value!r}") from exc


def business_order_key(record: SourceRecord, resolver: FieldResolver) -> BusinessOrderKey:
    """Build descending precedence from processing date, accretion date, query code and source
    sequence.
    """
    processing = parse_date(resolver.get(record.data, "processing_date"))
    accrete = parse_date(
        resolver.get(record.data, "accrete_date"), allow_none=True
    ) or date.min
    sequence = _as_sequence(resolver.get(record.data, "source_sequence"))
    return BusinessOrderKey(processing, accrete, int(resolver.get(record.data, "query_code")), sequence)


def order_newest_first(
    records: list[SourceRecord], resolver: FieldResolver
) -> OrderingResult:
    """Sort by the complete business order key and return the record IDs sharing identical keys as
    ambiguity evidence.
    """
    decorated = [(business_order_key(record, resolver), record) for record in records]
    decorated.sort(key=lambda item: item[0], reverse=True)

    duplicate_keys: dict[BusinessOrderKey, list[SourceRecord]] = {}
    for key, record in decorated:
        duplicate_keys.setdefault(key, []).append(record)
    ambiguous, equivalent = [], []
    for records_with_key in duplicate_keys.values():
        if len(records_with_key) < 2:
            continue
        payloads = {json.dumps(record.data, sort_keys=True, default=str) for record in records_with_key}
        target = equivalent if len(payloads) == 1 else ambiguous
        target.extend(record.record_id for record in records_with_key)
    return OrderingResult(
        ordered_records=tuple(record for _, record in decorated),
        ambiguous_record_ids=tuple(ambiguous),
        equivalent_tie_record_ids=tuple(equivalent),
    )
