"""Tests for Time Zone analysis."""
import numpy as np
import pandas as pd
import pytest

from src.analysis.timezone import (
    _hour_mask,
    compute_timezone_returns,
    build_timezone_summary,
    build_timezone_heatmap,
    TIMEZONE_ZONES,
    GRANULAR_SLOTS,
)


class TestHourMask:
    def test_normal_range(self):
        """8am-1pm UTC: hours 8, 9, 10, 11, 12 should be True."""
        index = pd.date_range("2026-02-13 00:00", periods=24, freq="h", tz="UTC")
        mask = _hour_mask(index, 8, 13)
        assert mask.sum() == 5
        # Hours 8-12 should be True
        for h in [8, 9, 10, 11, 12]:
            assert mask.iloc[h] == True
        for h in [0, 7, 13, 23]:
            assert mask.iloc[h] == False

    def test_midnight_wrap(self):
        """America zone 1pm-12am: hours 13-23 should be True (11 hours)."""
        index = pd.date_range("2026-02-13 00:00", periods=24, freq="h", tz="UTC")
        mask = _hour_mask(index, 13, 0)
        assert mask.sum() == 11
        for h in range(13, 24):
            assert mask.iloc[h] == True
        for h in range(0, 13):
            assert mask.iloc[h] == False

    def test_slot_11pm_2am(self):
        """11pm-2am wraps midnight: hours 23, 0, 1 = 3 hours."""
        index = pd.date_range("2026-02-13 00:00", periods=24, freq="h", tz="UTC")
        mask = _hour_mask(index, 23, 2)
        assert mask.sum() == 3
        assert mask.iloc[23] == True
        assert mask.iloc[0] == True
        assert mask.iloc[1] == True
        assert mask.iloc[2] == False

    def test_asia_zone(self):
        """Asia 12am-8am: hours 0-7 = 8 hours."""
        index = pd.date_range("2026-02-13 00:00", periods=24, freq="h", tz="UTC")
        mask = _hour_mask(index, 0, 8)
        assert mask.sum() == 8


class TestTimezoneReturns:
    def test_returns_all_zones(self, synthetic_hourly):
        returns = compute_timezone_returns(synthetic_hourly, lookback_days=5)
        assert "America" in returns
        assert "Europe" in returns
        assert "Asia" in returns

    def test_returns_are_numeric(self, synthetic_hourly):
        returns = compute_timezone_returns(synthetic_hourly, lookback_days=5)
        for zone, val in returns.items():
            assert isinstance(val, float)

    def test_empty_data(self):
        returns = compute_timezone_returns(pd.DataFrame(), lookback_days=5)
        assert all(v == 0.0 for v in returns.values())


class TestBuildTimezoneSummary:
    def test_summary_structure(self, synthetic_hourly):
        data = {"EURUSD": synthetic_hourly, "USDJPY": synthetic_hourly}
        summary = build_timezone_summary(data, lookback_days=5)
        assert "America" in summary.columns
        assert "Europe" in summary.columns
        assert "Asia" in summary.columns
        assert len(summary) == 2


class TestBuildTimezoneHeatmap:
    def test_heatmap_structure(self, synthetic_hourly):
        data = {"EURUSD": synthetic_hourly}
        heatmap = build_timezone_heatmap(data, lookback_days=5)
        assert len(heatmap.columns) == 8  # 8 granular slots
        assert "EURUSD" in heatmap.index

    def test_heatmap_empty(self):
        data = {"USDTHB": pd.DataFrame()}
        heatmap = build_timezone_heatmap(data, lookback_days=5)
        assert len(heatmap) == 1
        # All values should be 0
        assert (heatmap.iloc[0] == 0.0).all()

    def test_all_slots_covered(self):
        """Verify that the 8 slots cover all 24 hours without gaps."""
        all_hours = set()
        for _, start_h, end_h in GRANULAR_SLOTS:
            if start_h < end_h:
                all_hours.update(range(start_h, end_h))
            else:
                all_hours.update(range(start_h, 24))
                all_hours.update(range(0, end_h))
        assert all_hours == set(range(24))
