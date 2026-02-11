"""Tests for performance_metrics calculations."""
import numpy as np
import pandas as pd
import pytest

from trader.portfolio.pnl import performance_metrics


def _equity_series(values, freq="1min"):
    idx = pd.date_range("2025-01-01", periods=len(values), freq=freq, tz="UTC")
    return pd.Series(values, index=idx)


def test_empty_series_returns_empty():
    assert performance_metrics(pd.Series(dtype=float)) == {}


def test_single_value_returns_empty():
    s = _equity_series([100_000])
    assert performance_metrics(s) == {}


def test_flat_equity():
    s = _equity_series([100_000] * 10)
    m = performance_metrics(s)
    assert m["total_return"] == pytest.approx(0.0)
    assert m["max_drawdown"] == pytest.approx(0.0)


def test_upward_equity():
    values = [100_000 + i * 100 for i in range(100)]
    s = _equity_series(values)
    m = performance_metrics(s)
    assert m["total_return"] > 0
    assert m["annualized_return"] > 0
    assert m["max_drawdown"] == pytest.approx(0.0)
    assert m["sharpe_ratio"] > 0


def test_equity_with_drawdown():
    # 100k → 110k → 95k → 105k
    values = [100_000, 110_000, 95_000, 105_000]
    s = _equity_series(values)
    m = performance_metrics(s)
    assert m["total_return"] == pytest.approx(0.05)
    # Max drawdown: from 110k to 95k = -15k/110k ≈ -0.1364
    assert m["max_drawdown"] == pytest.approx(-15_000 / 110_000, rel=1e-3)


def test_keys_present():
    s = _equity_series([100_000, 101_000, 102_000])
    m = performance_metrics(s)
    expected_keys = {
        "total_return", "annualized_return", "volatility",
        "sharpe_ratio", "max_drawdown", "calmar_ratio",
    }
    assert expected_keys == set(m.keys())


def test_daily_frequency():
    values = [100_000 + i * 50 for i in range(252)]
    s = _equity_series(values, freq="1D")
    m = performance_metrics(s)
    # Should use ~252 periods per year for daily data
    assert m["total_return"] > 0
    assert m["annualized_return"] > 0
