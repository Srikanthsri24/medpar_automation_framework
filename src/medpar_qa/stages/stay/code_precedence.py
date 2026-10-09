from __future__ import annotations

from datetime import date
from typing import Any, Iterable

from medpar_qa.models import SourceRecord
from medpar_qa.normalization.dates import parse_date
from medpar_qa.normalization.fields import FieldResolver, nested_get


def _record_sort_key(
    record: SourceRecord,
    date_paths: tuple[str, ...],
    resolver: FieldResolver | None = None,
) -> tuple[date, ...]:
    values: list[date] = []
    for path in date_paths:
        raw = resolver.get(record.data, path) if resolver else nested_get(record.data, path)
        values.append(parse_date(raw, allow_none=True) or date.min)
    return tuple(values)


def latest_values_by_code(
    records: Iterable[SourceRecord],
    *,
    collection_path: str,
    code_path: str = "code",
    date_paths: tuple[str, ...] = ("nchWeeklyProcessingDate", "accreteDate"),
    resolver: FieldResolver | None = None,
) -> list[dict[str, Any]]:
    """Take duplicate code details from the newest claim and retain older unique codes."""
    ordered = sorted(
        records,
        key=lambda item: _record_sort_key(item, date_paths, resolver),
        reverse=True,
    )
    selected: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for record in ordered:
        collection = (
            resolver.get(record.data, collection_path, [])
            if resolver
            else nested_get(record.data, collection_path, default=[])
        ) or []
        if not isinstance(collection, list):
            raise ValueError(f"{collection_path} must be a list")
        for item in collection:
            if not isinstance(item, dict):
                raise ValueError(f"{collection_path} must contain objects")
            code = nested_get(item, code_path)
            if code is None:
                for candidate in (
                    "conditionCode", "occurrenceCode", "spanCode", "valueCode",
                    "codeId", "id",
                ):
                    code = nested_get(item, candidate)
                    if code is not None:
                        break
            if code is None or str(code).strip() == "":
                continue
            key = str(code).strip()
            if key not in selected:
                enriched = dict(item)
                enriched["_source_record_id"] = record.record_id
                selected[key] = enriched
                order.append(key)

    return [selected[key] for key in order]


def strip_lineage(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in item.items() if key != "_source_record_id"}
        for item in items
    ]
