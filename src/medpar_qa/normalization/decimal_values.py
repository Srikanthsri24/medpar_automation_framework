from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


DEFAULT_SCALE = Decimal("0.001")


def to_decimal(value: Any, *, allow_none: bool = False) -> Decimal | None:
    if value is None or value == "":
        if allow_none:
            return None
        raise ValueError("Numeric value is required")
    if isinstance(value, bool):
        raise ValueError("Boolean is not a valid amount")
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc


def quantize_decimal(
    value: Any,
    *,
    scale: Decimal = DEFAULT_SCALE,
    rounding: str = ROUND_HALF_UP,
) -> Decimal:
    decimal_value = to_decimal(value)
    assert decimal_value is not None
    return decimal_value.quantize(scale, rounding=rounding)


def sum_decimal(
    values: list[Any],
    *,
    scale: Decimal = DEFAULT_SCALE,
    rounding: str = ROUND_HALF_UP,
) -> Decimal:
    total = sum((to_decimal(value) or Decimal("0") for value in values), Decimal("0"))
    return total.quantize(scale, rounding=rounding)
