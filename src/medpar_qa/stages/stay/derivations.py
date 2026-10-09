from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from medpar_qa.models import SourceRecord
from medpar_qa.normalization.decimal_values import quantize_decimal, to_decimal
from medpar_qa.normalization.fields import FieldResolver


def collection_codes(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    codes: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            code = item.get("code")
        else:
            code = item
        if code is not None and str(code).strip():
            codes.add(str(code).strip())
    return codes


def derive_condition_switch(condition_codes: Any, code: str) -> str:
    return "Y" if str(code) in collection_codes(condition_codes) else "N"


def derive_value_code_amount(
    records: Iterable[SourceRecord],
    resolver: FieldResolver,
    *,
    code: str,
    scale: Decimal = Decimal("0.001"),
) -> Decimal:
    total = Decimal("0")
    for record in records:
        lines = resolver.get(record.data, "value_lines", []) or []
        if not isinstance(lines, list):
            raise ValueError("valueLines must be a list")
        for line in lines:
            if not isinstance(line, dict):
                raise ValueError("valueLines must contain objects")
            line_code = line.get("code", line.get("valueCode"))
            if str(line_code).strip() != str(code):
                continue
            amount = line.get("amount", line.get("valueAmount"))
            total += to_decimal(amount)
    return quantize_decimal(total, scale=scale)


def derive_sum_field(
    records: Iterable[SourceRecord],
    resolver: FieldResolver,
    field_name: str,
    *,
    scale: Decimal = Decimal("0.001"),
) -> Decimal | None:
    values: list[Decimal] = []
    for record in records:
        raw = resolver.get(record.data, field_name)
        if raw is None or str(raw).strip() == "":
            continue
        values.append(to_decimal(raw))
    if not values:
        return None
    return quantize_decimal(sum(values, Decimal("0")), scale=scale)
