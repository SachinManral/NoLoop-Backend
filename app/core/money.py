"""Money formatting helpers, matching the JS used in the NestJS backend."""

from __future__ import annotations

from math import floor


def js_round(x: float) -> int:
    """Math.round semantics: round half UP (not banker's rounding)."""
    return floor(x + 0.5)


def _group_indian(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    last3, rest = s[-3:], s[:-3]
    parts: list[str] = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return ",".join(parts) + "," + last3


def inr(paise: float) -> str:
    """Match JS `(paise / 100).toLocaleString("en-IN")`."""
    rupees = paise / 100
    neg = rupees < 0
    rupees = abs(rupees)
    intpart = int(rupees)
    if rupees == intpart:
        body = _group_indian(intpart)
    else:
        frac = ("%.3f" % (rupees - intpart))[2:].rstrip("0")
        body = _group_indian(intpart) + (f".{frac}" if frac else "")
    return ("-" if neg else "") + body
