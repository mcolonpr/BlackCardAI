"""Filter the option chain to monthly contracts and bucket by DTE."""

from __future__ import annotations

from datetime import date, timedelta

from .models import Contract

# Sentiment buckets: (sentiment, target DTE) per the spec.
DTE_TARGETS: list[tuple[str, int]] = [
    ("Long", 320),
    ("Long", 120),
    ("Short", 90),
    ("Short", 30),
]


def _third_friday(year: int, month: int) -> date:
    """The third Friday of `year`/`month`."""
    first = date(year, month, 1)
    days_to_first_friday = (4 - first.weekday()) % 7  # weekday(): Mon=0 .. Fri=4
    return first + timedelta(days=days_to_first_friday + 14)  # +2 weeks


def _easter_sunday(year: int) -> date:
    """Easter Sunday (Gregorian), via the Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _expiration_holidays(year: int) -> set[date]:
    """Market holidays that can land on a monthly-expiration Friday.

    Only two NYSE holidays ever fall on a third Friday (day 15..21): Good
    Friday (movable, in April) and Juneteenth (June 19, an exchange holiday
    since 2022). Every other market holiday is a Monday, a Thursday in the
    fourth week, or a fixed date outside the 15..21 window, so it can never
    coincide with a monthly expiration.
    """
    holidays = {_easter_sunday(year) - timedelta(days=2)}  # Good Friday
    if year >= 2022:  # NYSE first observed Juneteenth in 2022.
        juneteenth = date(year, 6, 19)
        weekday = juneteenth.weekday()
        if weekday == 5:      # Saturday -> observed the preceding Friday
            juneteenth = date(year, 6, 18)
        elif weekday == 6:    # Sunday -> observed the following Monday
            juneteenth = date(year, 6, 20)
        holidays.add(juneteenth)
    return holidays


def monthly_expiration(year: int, month: int) -> date:
    """The standard monthly options expiration for `year`/`month`.

    Normally the third Friday. When that Friday is a market holiday (Good
    Friday or Juneteenth), the exchange is closed, so the last trading day —
    and thus the listed expiration — rolls back to the previous business day
    (the Thursday before).
    """
    exp = _third_friday(year, month)
    holidays = _expiration_holidays(year)
    while exp in holidays or exp.weekday() >= 5:  # skip holidays and weekends
        exp -= timedelta(days=1)
    return exp


def is_monthly_expiration(exp: date) -> bool:
    """True if `exp` is the standard monthly expiration for its month.

    Standard equity/ETF monthlies expire on the third Friday of the month —
    or, when that Friday is a market holiday (e.g. Juneteenth), on the
    Thursday before. Weeklys land on other dates and are excluded.
    """
    return exp == monthly_expiration(exp.year, exp.month)


def monthly_expirations(contracts: list[Contract]) -> list[date]:
    """Sorted unique monthly expiration dates present in the chain."""
    exps = {c.expiration for c in contracts if is_monthly_expiration(c.expiration)}
    return sorted(exps)


def nearest_expiration(expirations: list[date], target_dte: int, as_of: date) -> date | None:
    """Pick the monthly expiration whose DTE is closest to `target_dte`.

    Only future expirations are considered. Returns None if the list is empty.
    """
    future = [e for e in expirations if (e - as_of).days >= 0]
    if not future:
        return None
    return min(future, key=lambda e: abs((e - as_of).days - target_dte))


def select_buckets(
    contracts: list[Contract], as_of: date
) -> list[tuple[str, int, date]]:
    """Resolve each (sentiment, target_dte) to a concrete monthly expiration.

    Returns a list of (sentiment, target_dte, expiration). Targets with no
    available monthly expiration are skipped. The same expiration may serve
    more than one target if the chain is sparse.
    """
    monthlies = monthly_expirations(contracts)
    resolved: list[tuple[str, int, date]] = []
    for sentiment, target in DTE_TARGETS:
        exp = nearest_expiration(monthlies, target, as_of)
        if exp is not None:
            resolved.append((sentiment, target, exp))
    return resolved


def contracts_for_expiration(contracts: list[Contract], exp: date) -> list[Contract]:
    """All contracts (calls and puts) for a given expiration."""
    return [c for c in contracts if c.expiration == exp]
