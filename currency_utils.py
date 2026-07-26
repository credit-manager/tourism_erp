from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Union

CURRENCY_PRECISION = 2
DECIMAL_ZERO = Decimal("0.00")


def D(value: Union[str, int, float, Decimal, None]) -> Decimal:
    if value is None:
        return DECIMAL_ZERO
    if isinstance(value, Decimal):
        return value.quantize(DECIMAL_ZERO, rounding=ROUND_HALF_UP)
    if isinstance(value, float):
        return Decimal(str(value)).quantize(DECIMAL_ZERO, rounding=ROUND_HALF_UP)
    if isinstance(value, int):
        return Decimal(value).quantize(DECIMAL_ZERO, rounding=ROUND_HALF_UP)
    try:
        return Decimal(str(value)).quantize(DECIMAL_ZERO, rounding=ROUND_HALF_UP)
    except Exception:
        return DECIMAL_ZERO


d = D


def round_currency(value: Union[str, int, float, Decimal, None]) -> Decimal:
    return D(value)


def sum_decimals(values) -> Decimal:
    total = DECIMAL_ZERO
    for v in values:
        total += D(v)
    return total


def parse_float_safe(value) -> Decimal:
    try:
        return D(value)
    except Exception:
        return DECIMAL_ZERO
