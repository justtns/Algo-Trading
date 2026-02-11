"""Tests for the EquityTracker."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from trader.persistence.database import Database
from trader.portfolio.equity import EquityTracker


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "test.db")
    d.connect_sync()
    yield d
    d.close_sync()


def _utc(year=2025, month=1, day=1, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def test_snaps_at_interval(db):
    tracker = EquityTracker(db, session_id="s1", snap_interval_seconds=60)
    t0 = _utc(hour=10, minute=0)
    t1 = _utc(hour=10, minute=1)
    t2 = _utc(hour=10, minute=2)

    tracker.on_bar(t0, 100_000)
    tracker.on_bar(t1, 101_000)
    tracker.on_bar(t2, 102_000)

    df = tracker.get_curve()
    assert len(df) == 3
    assert df["equity"].iloc[0] == 100_000
    assert df["equity"].iloc[2] == 102_000


def test_no_snap_within_interval(db):
    tracker = EquityTracker(db, session_id="s1", snap_interval_seconds=120)
    t0 = _utc(hour=10, minute=0)
    t1 = _utc(hour=10, minute=1)  # only 60s later, below 120s interval

    tracker.on_bar(t0, 100_000)
    tracker.on_bar(t1, 101_000)

    df = tracker.get_curve()
    assert len(df) == 1  # only first snap, second skipped


def test_force_snap_ignores_interval(db):
    tracker = EquityTracker(db, session_id="s1", snap_interval_seconds=3600)
    t0 = _utc(hour=10, minute=0)
    t1 = _utc(hour=10, minute=1)

    tracker.on_bar(t0, 100_000)
    tracker.force_snap(t1, 101_000)

    df = tracker.get_curve()
    assert len(df) == 2


def test_drawdown_series(db):
    tracker = EquityTracker(db, session_id="s1", snap_interval_seconds=60)
    # equity: 100 → 110 → 105 → 115
    for i, eq in enumerate([100_000, 110_000, 105_000, 115_000]):
        tracker.on_bar(_utc(minute=i), eq)

    dd = tracker.drawdown_series()
    assert len(dd) == 4
    # At t=2 (105k), drawdown from peak 110k = (105-110)/110 ≈ -0.0454
    assert dd.iloc[2] == pytest.approx(-5000 / 110_000, rel=1e-3)
    # At t=3 (115k, new peak), drawdown = 0
    assert dd.iloc[3] == 0.0


def test_get_curve_returns_dataframe(db):
    tracker = EquityTracker(db, session_id="s1", snap_interval_seconds=60)
    tracker.on_bar(_utc(), 100_000)

    df = tracker.get_curve()
    assert isinstance(df, pd.DataFrame)
    assert "equity" in df.columns
    assert "cash" in df.columns


def test_strategy_id_filtering(db):
    tracker = EquityTracker(db, session_id="s1", snap_interval_seconds=60)
    tracker.on_bar(_utc(minute=0), 100_000, strategy_id="gotobi")
    tracker.on_bar(_utc(minute=1), 50_000, strategy_id="breakout")
    tracker.force_snap(_utc(minute=2), 150_000, strategy_id=None)  # portfolio

    gotobi_df = tracker.get_curve(strategy_id="gotobi")
    assert len(gotobi_df) == 1
    assert gotobi_df["equity"].iloc[0] == 100_000

    portfolio_df = tracker.get_curve()
    assert len(portfolio_df) == 1
    assert portfolio_df["equity"].iloc[0] == 150_000
