"""
Clock utilities for consistent bar timing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd


def now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz=timezone.utc)


class MarketClock:
    def __init__(self, calendar: str = "24x5", bar_seconds: int = 60):
        self.calendar = calendar
        self.bar_seconds = bar_seconds

    def next_bar_time(self, last_ts: datetime) -> datetime:
        return last_ts + timedelta(seconds=self.bar_seconds)

    def is_trading_time(self, ts: datetime) -> bool:
        # Simplified: always true for 24x5 markets
        return True
