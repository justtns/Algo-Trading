"""Shared test fixtures with synthetic OHLC data."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def synthetic_daily_uptrend() -> pd.DataFrame:
    """504 days of synthetic uptrending OHLC data (like a strengthening pair)."""
    np.random.seed(42)
    n = 504
    dates = pd.bdate_range(end=pd.Timestamp("2026-02-13", tz="UTC"), periods=n)
    # Uptrend: starts at 1.05, trends to ~1.15
    trend = np.linspace(0, 0.10, n)
    noise = np.cumsum(np.random.randn(n) * 0.002)
    close = 1.05 + trend + noise
    close = np.maximum(close, 0.5)  # floor

    high = close + np.abs(np.random.randn(n) * 0.003)
    low = close - np.abs(np.random.randn(n) * 0.003)
    open_ = close + np.random.randn(n) * 0.001

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": np.random.randint(1000, 10000, n),
    }, index=dates)


@pytest.fixture
def synthetic_daily_downtrend() -> pd.DataFrame:
    """504 days of synthetic downtrending OHLC data."""
    np.random.seed(123)
    n = 504
    dates = pd.bdate_range(end=pd.Timestamp("2026-02-13", tz="UTC"), periods=n)
    trend = np.linspace(0, -0.10, n)
    noise = np.cumsum(np.random.randn(n) * 0.002)
    close = 1.15 + trend + noise
    close = np.maximum(close, 0.5)

    high = close + np.abs(np.random.randn(n) * 0.003)
    low = close - np.abs(np.random.randn(n) * 0.003)
    open_ = close + np.random.randn(n) * 0.001

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": np.random.randint(1000, 10000, n),
    }, index=dates)


@pytest.fixture
def synthetic_daily_flat() -> pd.DataFrame:
    """504 days of range-bound OHLC data."""
    np.random.seed(99)
    n = 504
    dates = pd.bdate_range(end=pd.Timestamp("2026-02-13", tz="UTC"), periods=n)
    close = 1.10 + np.cumsum(np.random.randn(n) * 0.001)
    close = np.maximum(close, 0.5)

    high = close + np.abs(np.random.randn(n) * 0.003)
    low = close - np.abs(np.random.randn(n) * 0.003)
    open_ = close + np.random.randn(n) * 0.001

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": np.random.randint(1000, 10000, n),
    }, index=dates)


@pytest.fixture
def synthetic_hourly() -> pd.DataFrame:
    """30 days of hourly OHLC data (720 bars)."""
    np.random.seed(77)
    n = 720
    dates = pd.date_range(
        end=pd.Timestamp("2026-02-13 23:00", tz="UTC"),
        periods=n,
        freq="h",
    )
    close = 1.08 + np.cumsum(np.random.randn(n) * 0.0005)
    close = np.maximum(close, 0.5)

    high = close + np.abs(np.random.randn(n) * 0.001)
    low = close - np.abs(np.random.randn(n) * 0.001)
    open_ = close + np.random.randn(n) * 0.0003

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": np.random.randint(100, 1000, n),
    }, index=dates)


@pytest.fixture
def synthetic_vix() -> pd.DataFrame:
    """504 days of synthetic VIX-like data."""
    np.random.seed(55)
    n = 504
    dates = pd.bdate_range(end=pd.Timestamp("2026-02-13", tz="UTC"), periods=n)
    # VIX tends to be mean-reverting around 15-20
    close = 18 + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 9)
    close = np.minimum(close, 80)

    high = close + np.abs(np.random.randn(n) * 0.5)
    low = close - np.abs(np.random.randn(n) * 0.5)
    open_ = close + np.random.randn(n) * 0.2

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": np.random.randint(1000, 50000, n),
    }, index=dates)
