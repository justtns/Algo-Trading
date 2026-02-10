"""
Gotobi calendar logic: resolves settlement trading dates for Japanese FX markets.
Framework-agnostic, shared by all Gotobi strategy implementations.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import AbstractSet, Callable, Optional

from trader.core.constants import DEFAULT_GOTOBI_DAYS


class GotobiCalendar:
    """
    Resolves gotobi settlement trading dates with weekend/holiday rollback.

    Gotobi days are the 5th, 10th, 15th, 20th, 25th, and 30th of each month.
    If a gotobi day falls on a weekend, it shifts to the previous Friday.
    If that Friday is a holiday, it rolls backward until a business day is found.
    """

    def __init__(
        self,
        gotobi_days: AbstractSet[int] | None = None,
        use_holidays: bool = True,
        notrade_days: AbstractSet[date] | None = None,
    ):
        self.gotobi_days = frozenset(gotobi_days) if gotobi_days else DEFAULT_GOTOBI_DAYS
        self._holiday_checker = _build_holiday_checker(use_holidays, notrade_days)

    def is_holiday(self, d: date) -> bool:
        return self._holiday_checker(d)

    def is_gotobi_base(self, d: date) -> bool:
        return d.day in self.gotobi_days

    def resolve_trading_date(self, d: date) -> date | None:
        """
        From a calendar date, returns the effective gotobi trading date, or None
        if the date is not a gotobi base date.
        """
        if not self.is_gotobi_base(d):
            return None
        shifted = _weekend_to_prev_friday(d)
        return _prev_business_day(shifted, self._holiday_checker)

    def is_gotobi_trading_date(self, d: date) -> bool:
        """Check if today is the resolved trading date for any gotobi base date."""
        resolved = self.resolve_trading_date(d)
        return resolved == d


def _weekend_to_prev_friday(d: date) -> date:
    if d.weekday() == 5:  # Saturday -> Friday
        return d - timedelta(days=1)
    if d.weekday() == 6:  # Sunday -> Friday
        return d - timedelta(days=2)
    return d


def _prev_business_day(d: date, is_holiday: Callable[[date], bool]) -> date:
    cur = d
    while cur.weekday() >= 5 or is_holiday(cur):
        cur -= timedelta(days=1)
    return cur


def _build_holiday_checker(
    use_holidays: bool,
    notrade_days: Optional[AbstractSet[date]],
) -> Callable[[date], bool]:
    if not use_holidays and notrade_days is not None:
        s = frozenset(notrade_days)
        return lambda d: d in s

    try:
        import holidays as hol_pkg  # type: ignore

        jp_holidays = hol_pkg.country_holidays("JP")
        extra = frozenset(notrade_days) if notrade_days else frozenset()
        return lambda d: (d in jp_holidays) or (d in extra)
    except Exception:
        s = frozenset(notrade_days) if notrade_days else frozenset()
        return lambda d: d in s
