"""Convert finite amounts to Decimal, quantize with explicit rounding and sum amounts without
binary floating-point arithmetic.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


DEFAULT_SCALE = Decimal("0.001")


def to_decimal(value: Any, *, allow_none: bool = False) -> Decimal | None:
    """Convert via Decimal text representation and reject invalid/nonfinite values rather than
    using floating-point arithmetic.
    """
    if value is None or value == "":
        if allow_none:
            return None
        raise ValueError("Numeric value is required")
    if isinstance(value, bool):
        raise ValueError("Boolean is not a valid amount")
    try:
        result = Decimal(str(value).strip())
        if not result.is_finite():
            raise ValueError("Amount must be finite")
        return result
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc


def quantize_decimal(
    value: Any,
    *,
    scale: Decimal = DEFAULT_SCALE,
    rounding: str = ROUND_HALF_UP,
) -> Decimal:
    """Round a Decimal to the explicitly configured scale and rounding mode."""
    decimal_value = to_decimal(value)
    assert decimal_value is not None
    return decimal_value.quantize(scale, rounding=rounding)


def sum_decimal(
    values: list[Any],
    *,
    scale: Decimal = DEFAULT_SCALE,
    rounding: str = ROUND_HALF_UP,
) -> Decimal:
    """Convert each operand to Decimal, sum it and apply the explicit scale/rounding policy."""
    total = sum((to_decimal(value) or Decimal("0") for value in values), Decimal("0"))
    return total.quantize(scale, rounding=rounding)
