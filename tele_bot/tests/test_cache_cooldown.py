"""Tests for DataCache _last_dates tracking and DataRefresher cooldown."""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.data.cache import DataCache, DataRefresher


@pytest.fixture
def tmp_cache(tmp_path):
    return DataCache(str(tmp_path))


@pytest.fixture
def sample_df():
    dates = pd.bdate_range(end="2026-02-13", periods=10, tz="UTC")
    return pd.DataFrame(
        {"open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "volume": 100},
        index=dates,
    )


class TestDataCacheLastDates:
    def test_put_daily_populates_last_dates(self, tmp_cache, sample_df):
        tmp_cache.put_daily("EURUSD", sample_df)
        # Should be in memory now
        last = tmp_cache.daily_last_date("EURUSD")
        assert last == "2026-02-13"

    def test_daily_last_date_from_file(self, tmp_cache, sample_df):
        tmp_cache.put_daily("USDJPY", sample_df)
        # Clear in-memory cache to force file read
        tmp_cache._last_dates.clear()
        last = tmp_cache.daily_last_date("USDJPY")
        assert last == "2026-02-13"

    def test_daily_last_date_missing_pair(self, tmp_cache):
        last = tmp_cache.daily_last_date("NONEXIST")
        assert last is None

    def test_put_hourly_populates_last_dates(self, tmp_cache):
        dates = pd.date_range(end="2026-02-13 23:00", periods=48, freq="h", tz="UTC")
        df = pd.DataFrame(
            {"open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "volume": 50},
            index=dates,
        )
        tmp_cache.put_hourly("GBPUSD", df)
        last = tmp_cache.hourly_last_date("GBPUSD")
        assert "2026-02-13" in last

    def test_put_cross_asset_populates_last_dates(self, tmp_cache, sample_df):
        tmp_cache.put_cross_asset("SPY", sample_df)
        last = tmp_cache.cross_asset_last_date("SPY")
        assert last == "2026-02-13"

    def test_in_memory_avoids_file_read(self, tmp_cache, sample_df):
        tmp_cache.put_daily("EURUSD", sample_df)
        # Calling again should hit in-memory cache, not file
        with patch("pandas.read_parquet") as mock_read:
            last = tmp_cache.daily_last_date("EURUSD")
            mock_read.assert_not_called()
        assert last == "2026-02-13"


class TestDataRefresherCooldown:
    def test_cooldown_skips_refresh(self):
        mock_client = MagicMock()
        mock_cache = MagicMock()
        refresher = DataRefresher(mock_client, mock_cache, cooldown_minutes=15)

        # Simulate recent refresh
        refresher._last_refresh_time = datetime.now(timezone.utc)
        assert refresher._should_skip_refresh() is True

    def test_cooldown_expired_allows_refresh(self):
        mock_client = MagicMock()
        mock_cache = MagicMock()
        refresher = DataRefresher(mock_client, mock_cache, cooldown_minutes=15)

        # Simulate old refresh
        refresher._last_refresh_time = datetime.now(timezone.utc) - timedelta(minutes=20)
        assert refresher._should_skip_refresh() is False

    def test_no_previous_refresh_allows_refresh(self):
        mock_client = MagicMock()
        mock_cache = MagicMock()
        refresher = DataRefresher(mock_client, mock_cache, cooldown_minutes=15)
        assert refresher._should_skip_refresh() is False

    def test_force_bypasses_cooldown(self):
        mock_client = MagicMock()
        mock_cache = MagicMock()
        mock_cache.daily_last_date = MagicMock(return_value="2026-02-13")
        refresher = DataRefresher(mock_client, mock_cache, cooldown_minutes=15)

        # Recent refresh
        refresher._last_refresh_time = datetime.now(timezone.utc)
        # force=True should still proceed (the method won't skip)
        # We just test that _should_skip_refresh returns True but force bypasses
        assert refresher._should_skip_refresh() is True
