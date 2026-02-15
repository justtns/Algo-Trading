"""Tests for CARS cross-asset regime switching."""
import numpy as np
import pandas as pd
import pytest

from src.analysis.cars import (
    classify_regime,
    compute_factor_rankings,
    generate_cars_signals,
    SAFE_HAVEN_CURRENCIES,
)


def _make_daily_series(seed: int, n: int = 504, base: float = 100.0, drift: float = 0.0):
    """Helper to create a synthetic daily close series."""
    np.random.seed(seed)
    dates = pd.bdate_range(end="2026-02-13", periods=n, tz="UTC")
    returns = drift + np.random.randn(n) * 0.01
    close = base * np.exp(np.cumsum(returns))
    return pd.Series(close, index=dates)


class TestClassifyRegime:
    def test_normal_regime(self):
        eq = _make_daily_series(1, drift=0.001)  # mild uptrend
        bd = _make_daily_series(2, drift=0.0005)
        cm = _make_daily_series(3, drift=0.0003)

        regime = classify_regime(eq, bd, cm)
        assert "is_shock" in regime
        assert "regime" in regime
        assert regime["regime"] in ("Shock", "Normal")

    def test_shock_regime_equity_crash(self):
        """Inject a sharp equity decline at the end."""
        eq = _make_daily_series(1)
        # Make last week a crash
        eq.iloc[-5:] = eq.iloc[-6] * 0.90  # 10% drop in a week
        bd = _make_daily_series(2)
        cm = _make_daily_series(3)

        regime = classify_regime(eq, bd, cm, equity_shock_z=-1.0)
        # The sharp drop should register as a shock (z-score well below -1)
        assert regime["equity_z"] < 0


class TestFactorRankings:
    def test_rankings_structure(self):
        # Create synthetic G10 FX data
        from src.data.tickers import G10_PAIRS
        fx_data = {}
        for i, pair in enumerate(G10_PAIRS):
            dates = pd.bdate_range(end="2026-02-13", periods=504, tz="UTC")
            close = pd.Series(
                1.0 + np.cumsum(np.random.randn(504) * 0.005),
                index=dates,
            )
            fx_data[pair] = pd.DataFrame({"close": close})

        eq = _make_daily_series(100)
        bd = _make_daily_series(200)
        cm = _make_daily_series(300)

        rankings = compute_factor_rankings(fx_data, eq, bd, cm)
        assert "equity_rank" in rankings.columns
        assert "rates_rank" in rankings.columns
        assert "commodity_rank" in rankings.columns
        assert len(rankings) == len(G10_PAIRS)

    def test_ranks_are_unique(self):
        from src.data.tickers import G10_PAIRS
        np.random.seed(42)
        fx_data = {}
        for pair in G10_PAIRS:
            dates = pd.bdate_range(end="2026-02-13", periods=504, tz="UTC")
            close = pd.Series(1.0 + np.cumsum(np.random.randn(504) * 0.005), index=dates)
            fx_data[pair] = pd.DataFrame({"close": close})

        eq = _make_daily_series(100)
        bd = _make_daily_series(200)
        cm = _make_daily_series(300)

        rankings = compute_factor_rankings(fx_data, eq, bd, cm)
        # Ranks should be 1 through N
        assert sorted(rankings["equity_rank"].tolist()) == list(range(1, len(G10_PAIRS) + 1))


class TestGenerateSignals:
    def test_shock_defensive(self):
        from src.data.tickers import G10_PAIRS, currency_from_pair

        regime = {"is_shock": True, "equity_z": -2.0, "bond_z": -0.5, "commodity_z": -0.3, "regime": "Shock"}

        currencies = [currency_from_pair(p) for p in G10_PAIRS]
        rankings = pd.DataFrame({
            "equity_rank": range(1, len(currencies) + 1),
            "rates_rank": range(1, len(currencies) + 1),
            "commodity_rank": range(1, len(currencies) + 1),
        }, index=currencies)

        signals = generate_cars_signals(regime, rankings)

        for ccy in SAFE_HAVEN_CURRENCIES:
            if ccy in signals.index:
                assert signals.loc[ccy, "Bullish/Bearish"] == "Bullish"

        # Non-safe-haven should be bearish
        for ccy in signals.index:
            if ccy not in SAFE_HAVEN_CURRENCIES:
                assert signals.loc[ccy, "Bullish/Bearish"] == "Bearish"

    def test_normal_week_top_bottom(self):
        from src.data.tickers import G10_PAIRS, currency_from_pair

        regime = {"is_shock": False, "equity_z": 0.5, "bond_z": 0.3, "commodity_z": 0.1, "regime": "Normal"}

        currencies = [currency_from_pair(p) for p in G10_PAIRS]
        rankings = pd.DataFrame({
            "equity_rank": range(1, len(currencies) + 1),
            "rates_rank": range(1, len(currencies) + 1),
            "commodity_rank": range(1, len(currencies) + 1),
            "equity_corr": np.linspace(0.5, -0.5, len(currencies)),
            "rates_corr": np.linspace(0.5, -0.5, len(currencies)),
            "commodity_corr": np.linspace(0.3, -0.3, len(currencies)),
        }, index=currencies)

        signals = generate_cars_signals(regime, rankings, performing_factor="rates")

        # Top 3 should be Bullish
        bullish_count = (signals["Bullish/Bearish"] == "Bullish").sum()
        bearish_count = (signals["Bullish/Bearish"] == "Bearish").sum()
        assert bullish_count >= 3
        assert bearish_count >= 3
