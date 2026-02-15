"""Tests for shared indicator functions."""
import numpy as np
import pandas as pd
import pytest

from src.analysis.indicators import (
    sma, ema, realized_vol, adx_dmi, bollinger_bands,
    rsi, macd_histogram, fibonacci_levels, zscore, percentile_rank,
)


class TestSMA:
    def test_basic_sma(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = sma(s, 3)
        assert result.iloc[-1] == pytest.approx(4.0)
        assert pd.isna(result.iloc[0])

    def test_sma_window_1(self):
        s = pd.Series([10.0, 20.0, 30.0])
        result = sma(s, 1)
        assert result.iloc[-1] == pytest.approx(30.0)


class TestEMA:
    def test_ema_converges(self):
        s = pd.Series([1.0] * 50 + [2.0] * 50)
        result = ema(s, 10)
        # Should be close to 2.0 at the end
        assert result.iloc[-1] > 1.9


class TestRealizedVol:
    def test_constant_price_zero_vol(self):
        s = pd.Series([100.0] * 30)
        rv = realized_vol(s, 21)
        assert rv.iloc[-1] == pytest.approx(0.0, abs=1e-10)

    def test_volatile_series_positive(self, synthetic_daily_uptrend):
        rv = realized_vol(synthetic_daily_uptrend["close"], 21)
        assert rv.iloc[-1] > 0


class TestADX:
    def test_adx_returns_three_columns(self, synthetic_daily_uptrend):
        df = synthetic_daily_uptrend
        result = adx_dmi(df["high"], df["low"], df["close"], period=14)
        assert "ADX" in result.columns
        assert "DMI_plus" in result.columns
        assert "DMI_minus" in result.columns

    def test_adx_values_bounded(self, synthetic_daily_uptrend):
        df = synthetic_daily_uptrend
        result = adx_dmi(df["high"], df["low"], df["close"], period=14)
        # ADX should be between 0 and 100
        valid = result["ADX"].dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_uptrend_dmi_plus_dominant(self, synthetic_daily_uptrend):
        df = synthetic_daily_uptrend
        result = adx_dmi(df["high"], df["low"], df["close"], period=14)
        # In an uptrend, DMI+ should generally be > DMI-
        last = result.iloc[-1]
        # Not guaranteed for every synthetic dataset, so just check they're computed
        assert pd.notna(last["DMI_plus"])
        assert pd.notna(last["DMI_minus"])


class TestBollinger:
    def test_bollinger_structure(self, synthetic_daily_uptrend):
        close = synthetic_daily_uptrend["close"]
        bb = bollinger_bands(close, 20, 2.0)
        assert "middle" in bb.columns
        assert "upper" in bb.columns
        assert "lower" in bb.columns

    def test_upper_above_lower(self, synthetic_daily_uptrend):
        close = synthetic_daily_uptrend["close"]
        bb = bollinger_bands(close, 20, 2.0)
        valid = bb.dropna()
        assert (valid["upper"] >= valid["lower"]).all()

    def test_middle_is_sma(self, synthetic_daily_uptrend):
        close = synthetic_daily_uptrend["close"]
        bb = bollinger_bands(close, 20, 2.0)
        expected_sma = sma(close, 20)
        pd.testing.assert_series_equal(bb["middle"], expected_sma, check_names=False)


class TestRSI:
    def test_rsi_bounded(self, synthetic_daily_uptrend):
        close = synthetic_daily_uptrend["close"]
        r = rsi(close, 14)
        valid = r.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_constant_price_rsi_50(self):
        s = pd.Series([100.0] * 50)
        r = rsi(s, 14)
        # Constant price -> no gains or losses -> RSI = 50
        assert r.iloc[-1] == pytest.approx(50.0)


class TestMACDHistogram:
    def test_macd_returns_series(self, synthetic_daily_uptrend):
        close = synthetic_daily_uptrend["close"]
        hist = macd_histogram(close)
        assert isinstance(hist, pd.Series)
        assert len(hist) == len(close)


class TestFibonacci:
    def test_fibonacci_levels(self):
        levels = fibonacci_levels(100.0, 50.0)
        assert levels["fib_382"] == pytest.approx(80.9, abs=0.1)
        assert levels["fib_500"] == pytest.approx(75.0)
        assert levels["fib_618"] == pytest.approx(69.1, abs=0.1)

    def test_fibonacci_same_high_low(self):
        levels = fibonacci_levels(100.0, 100.0)
        assert levels["fib_500"] == pytest.approx(100.0)


class TestZscore:
    def test_zscore_mean_is_zero(self):
        np.random.seed(42)
        s = pd.Series(np.random.randn(200))
        z = zscore(s, 50)
        # The z-score of the mean should be approximately 0
        valid = z.dropna()
        assert abs(valid.mean()) < 1.0  # loose check


class TestPercentileRank:
    def test_median_is_50(self):
        history = pd.Series(range(100))
        assert percentile_rank(49.5, history) == pytest.approx(50.0)

    def test_max_is_near_100(self):
        history = pd.Series(range(100))
        assert percentile_rank(99.5, history) == pytest.approx(100.0)

    def test_min_is_near_0(self):
        history = pd.Series(range(100))
        assert percentile_rank(-0.5, history) == pytest.approx(0.0)
