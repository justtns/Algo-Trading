"""Tests for data quality utilities."""
import pandas as pd
import pytest

from trader.data.quality import GapInfo, StaleDataAlert, check_stale, detect_gaps


def _make_bar_df(timestamps):
    idx = pd.DatetimeIndex(timestamps, tz="UTC")
    return pd.DataFrame(
        {"close": [1.0] * len(idx)},
        index=idx,
    )


def test_detect_gaps_finds_missing_bars():
    # 1-minute bars with a 5-minute gap
    ts = pd.date_range("2025-01-06 10:00", periods=3, freq="1min", tz="UTC").tolist()
    ts.append(pd.Timestamp("2025-01-06 10:08", tz="UTC"))  # 5-min gap
    df = _make_bar_df(ts)

    gaps = detect_gaps(df, expected_freq="1min", symbol="USDJPY")
    assert len(gaps) == 1
    assert gaps[0].symbol == "USDJPY"
    assert gaps[0].gap_seconds == 360  # 6 minutes (10:02 → 10:08)


def test_no_gaps_in_clean_data():
    ts = pd.date_range("2025-01-06 10:00", periods=10, freq="1min", tz="UTC")
    df = _make_bar_df(ts)

    gaps = detect_gaps(df, expected_freq="1min")
    assert len(gaps) == 0


def test_detect_gaps_ignores_weekends():
    # Friday 17:00 → Monday 00:00 is a weekend gap, should be ignored
    ts = [
        pd.Timestamp("2025-01-03 16:59", tz="UTC"),  # Friday
        pd.Timestamp("2025-01-06 00:00", tz="UTC"),  # Monday
    ]
    df = _make_bar_df(ts)

    gaps = detect_gaps(df, expected_freq="1min")
    assert len(gaps) == 0


def test_detect_gaps_empty_df():
    df = pd.DataFrame(columns=["close"])
    gaps = detect_gaps(df)
    assert len(gaps) == 0


def test_check_stale_detects_old_data():
    old_ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=10)
    alerts = check_stale({"USDJPY": old_ts}, threshold_seconds=300)
    assert len(alerts) == 1
    assert alerts[0].symbol == "USDJPY"
    assert alerts[0].staleness_seconds > 300


def test_check_stale_fresh_data():
    fresh_ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(seconds=10)
    alerts = check_stale({"USDJPY": fresh_ts}, threshold_seconds=300)
    assert len(alerts) == 0


def test_check_stale_callback():
    old_ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=10)
    callback_alerts = []

    def on_stale(alert):
        callback_alerts.append(alert)

    check_stale({"USDJPY": old_ts}, threshold_seconds=300, on_stale=on_stale)
    assert len(callback_alerts) == 1
    assert callback_alerts[0].symbol == "USDJPY"
