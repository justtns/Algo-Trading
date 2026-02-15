"""Tests for Technical Matrix analysis."""
import numpy as np
import pandas as pd
import pytest

from src.analysis.technical_matrix import (
    compute_maa,
    positioning_trend_arrow,
    compute_ud,
    compute_rs_proxy,
    positioning_signal,
    adx_trend_label,
    bollinger_signal,
    compute_support_resistance,
    build_technical_matrix,
)


class TestMAA:
    def test_strong_uptrend_high_maa(self, synthetic_daily_uptrend):
        """Strong uptrend should have most short SMAs above long SMAs."""
        maa = compute_maa(synthetic_daily_uptrend["close"])
        assert maa > 50  # should be well above 50 in uptrend

    def test_strong_downtrend_low_maa(self, synthetic_daily_downtrend):
        """Strong downtrend should have most short SMAs below long SMAs."""
        maa = compute_maa(synthetic_daily_downtrend["close"])
        assert maa < 50  # should be below 50 in downtrend

    def test_maa_bounded(self, synthetic_daily_flat):
        maa = compute_maa(synthetic_daily_flat["close"])
        assert 0 <= maa <= 100

    def test_maa_insufficient_data(self):
        """Short series should return neutral."""
        short = pd.Series([1.0, 1.1, 1.2])
        maa = compute_maa(short)
        assert maa == 50.0  # default for no valid signals


class TestPositioningTrendArrow:
    def test_uptrend_arrow(self):
        assert positioning_trend_arrow(75) == "\u2191"

    def test_downtrend_arrow(self):
        assert positioning_trend_arrow(25) == "\u2193"

    def test_sideways_arrow(self):
        assert positioning_trend_arrow(50) == "\u2194"


class TestUD:
    def test_ud_returns_bounded(self, synthetic_daily_uptrend):
        ud = compute_ud(synthetic_daily_uptrend["close"])
        assert 0 <= ud <= 100

    def test_ud_short_series(self):
        """Series shorter than percentile lookback should still return bounded value."""
        short = pd.Series(np.linspace(1.0, 1.1, 100))
        short.index = pd.bdate_range(end="2026-02-13", periods=100, tz="UTC")
        ud = compute_ud(short, percentile_lookback=252)
        assert 0 <= ud <= 100


class TestRSProxy:
    def test_rs_bounded(self, synthetic_daily_uptrend):
        rs = compute_rs_proxy(synthetic_daily_uptrend["close"])
        assert 0 <= rs <= 100

    def test_rs_short_data(self):
        """Insufficient data should return neutral 50."""
        short = pd.Series([1.0] * 50)
        short.index = pd.bdate_range(end="2026-02-13", periods=50, tz="UTC")
        rs = compute_rs_proxy(short)
        assert rs == 50.0


class TestPositioningSignal:
    def test_uptrend_reversal(self):
        assert positioning_signal(maa=75, ud=85, rs=85) == "Bearish"

    def test_uptrend_continuation(self):
        assert positioning_signal(maa=75, ud=40, rs=40) == "Bullish"

    def test_downtrend_reversal(self):
        assert positioning_signal(maa=25, ud=15, rs=15) == "Bullish"

    def test_downtrend_continuation(self):
        assert positioning_signal(maa=25, ud=60, rs=60) == "Bearish"

    def test_neutral_zone(self):
        assert positioning_signal(maa=50, ud=50, rs=50) == "No Signal"

    def test_slightly_bearish_uptrend(self):
        assert positioning_signal(maa=75, ud=85, rs=40) == "Sl. Bearish"

    def test_slightly_bullish_uptrend(self):
        assert positioning_signal(maa=75, ud=40, rs=60) == "Sl. Bullish"

    def test_slightly_bullish_downtrend(self):
        assert positioning_signal(maa=25, ud=15, rs=60) == "Sl. Bullish"

    def test_slightly_bearish_downtrend(self):
        assert positioning_signal(maa=25, ud=60, rs=40) == "Sl. Bearish"


class TestADXTrendLabel:
    def test_range(self):
        assert adx_trend_label(15, 30, 20) == "Range"

    def test_transition(self):
        assert adx_trend_label(22, 30, 20) == "Transition"

    def test_uptrend(self):
        assert adx_trend_label(30, 35, 20) == "Uptrend"

    def test_downtrend(self):
        assert adx_trend_label(30, 15, 25) == "Downtrend"

    def test_nan(self):
        assert adx_trend_label(float("nan"), 0, 0) == "N/A"


class TestBollingerSignal:
    def test_upper(self):
        assert bollinger_signal(1.10, 1.09, 1.05) == "Upper"

    def test_lower(self):
        assert bollinger_signal(1.04, 1.09, 1.05) == "Lower"

    def test_none(self):
        assert bollinger_signal(1.07, 1.09, 1.05) == "None"


class TestSupportResistance:
    def test_returns_dict(self, synthetic_daily_uptrend):
        df = synthetic_daily_uptrend
        sr = compute_support_resistance(df["close"], df["high"], df["low"])
        assert "next_support" in sr
        assert "next_resistance" in sr

    def test_support_below_spot(self, synthetic_daily_uptrend):
        df = synthetic_daily_uptrend
        sr = compute_support_resistance(df["close"], df["high"], df["low"])
        spot = float(df["close"].iloc[-1])
        if sr["next_support"] is not None:
            assert sr["next_support"] < spot

    def test_resistance_above_spot(self, synthetic_daily_uptrend):
        df = synthetic_daily_uptrend
        sr = compute_support_resistance(df["close"], df["high"], df["low"])
        spot = float(df["close"].iloc[-1])
        if sr["next_resistance"] is not None:
            assert sr["next_resistance"] > spot


class TestBuildTechnicalMatrix:
    def test_full_matrix(self, synthetic_daily_uptrend, synthetic_daily_downtrend):
        data = {
            "EURUSD": synthetic_daily_uptrend,
            "USDJPY": synthetic_daily_downtrend,
        }
        matrix = build_technical_matrix(data)
        assert len(matrix) == 2
        assert "Spot" in matrix.columns
        assert "Signal" in matrix.columns
        assert matrix.loc["EURUSD", "Spot"] is not None

    def test_empty_data_handled(self):
        data = {"USDTHB": pd.DataFrame()}
        matrix = build_technical_matrix(data)
        assert matrix.loc["USDTHB", "Signal"] == "N/A"
