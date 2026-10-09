from decimal import Decimal

import pytest

from medpar_qa.normalization.decimal_values import quantize_decimal, sum_decimal


@pytest.mark.unit
@pytest.mark.decimal_precision
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.2344", Decimal("1.234")),
        ("1.2345", Decimal("1.235")),
        ("-1.2345", Decimal("-1.235")),
        (0, Decimal("0.000")),
    ],
)
def test_explicit_three_decimal_rounding(value, expected):
    assert quantize_decimal(value) == expected


@pytest.mark.unit
def test_sum_decimal_never_uses_binary_float_error():
    assert sum_decimal(["0.1", "0.2"]) == Decimal("0.300")


@pytest.mark.unit
def test_invalid_decimal_fails():
    with pytest.raises(ValueError):
        quantize_decimal("not-a-number")
