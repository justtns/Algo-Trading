from datetime import date

from trader.strategy.common import GotobiCalendar


def test_resolve_trading_date_on_base_day():
    cal = GotobiCalendar(use_holidays=False)
    d = date(2025, 1, 10)
    assert cal.resolve_trading_date(d) == d


def test_is_gotobi_trading_date_on_weekend_rollover_day():
    # 2025-01-25 is Saturday, so gotobi trading date rolls back to Friday 24th.
    cal = GotobiCalendar(use_holidays=False)
    assert cal.is_gotobi_trading_date(date(2025, 1, 24))


def test_is_gotobi_trading_date_false_for_regular_day():
    cal = GotobiCalendar(use_holidays=False)
    assert not cal.is_gotobi_trading_date(date(2025, 1, 23))


def test_is_gotobi_trading_date_can_roll_back_from_next_month():
    # Force 2025-02-05 to roll back past Feb 1/2 weekend and custom holidays
    # on Feb 3/4/5, landing on 2025-01-31.
    cal = GotobiCalendar(
        use_holidays=False,
        notrade_days={
            date(2025, 2, 3),
            date(2025, 2, 4),
            date(2025, 2, 5),
        },
    )
    assert cal.resolve_trading_date(date(2025, 2, 5)) == date(2025, 1, 31)
    assert cal.is_gotobi_trading_date(date(2025, 1, 31))
