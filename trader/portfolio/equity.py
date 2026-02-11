"""Equity curve tracker with configurable snapping interval and persistence."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from trader.persistence.database import Database

from trader.persistence.models import EquitySnapshotRow
from trader.persistence.repositories import EquityRepository


class EquityTracker:
    """
    Tracks equity over time per-strategy and at portfolio level.

    Snaps equity at configurable intervals and persists to SQLite.
    """

    def __init__(
        self,
        db: Database,
        session_id: str,
        snap_interval_seconds: int = 60,
        initial_cash: float = 0.0,
    ):
        self._session_id = session_id
        self._interval = snap_interval_seconds
        self._cash: float = initial_cash
        self._last_snap: dict[str | None, datetime] = {}
        self._equity_repo = EquityRepository(db.connect_sync())

    @property
    def session_id(self) -> str:
        return self._session_id

    def on_bar(
        self,
        ts: datetime,
        equity: float,
        strategy_id: str | None = None,
    ) -> None:
        """Called on each bar. Snaps if interval has elapsed."""
        last = self._last_snap.get(strategy_id)
        if last is None or (ts - last).total_seconds() >= self._interval:
            self._snap(ts, equity, strategy_id)
            self._last_snap[strategy_id] = ts

    def force_snap(
        self,
        ts: datetime,
        equity: float,
        strategy_id: str | None = None,
    ) -> None:
        """Force a snapshot regardless of interval."""
        self._snap(ts, equity, strategy_id)
        self._last_snap[strategy_id] = ts

    def _snap(
        self, ts: datetime, equity: float, strategy_id: str | None
    ) -> None:
        row = EquitySnapshotRow(
            id=None,
            ts=ts.isoformat(),
            equity=equity,
            cash=self._cash,
            strategy_id=strategy_id,
            session_id=self._session_id,
        )
        self._equity_repo.insert(row)

    def update_cash(self, cash: float) -> None:
        self._cash = cash

    def get_curve(
        self,
        strategy_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Query equity curve as a DataFrame with datetime index."""
        return self._equity_repo.get_curve_as_df(
            session_id=self._session_id,
            strategy_id=strategy_id,
            start=start.isoformat() if start else None,
            end=end.isoformat() if end else None,
        )

    def drawdown_series(
        self, strategy_id: str | None = None
    ) -> pd.Series:
        """Compute drawdown from equity curve."""
        df = self.get_curve(strategy_id=strategy_id)
        if df.empty:
            return pd.Series(dtype=float)
        cummax = df["equity"].cummax()
        dd = (df["equity"] - cummax) / cummax
        return dd
