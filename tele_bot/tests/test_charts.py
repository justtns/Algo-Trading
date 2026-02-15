"""Tests for chart generation — verify each function returns valid PNG bytes."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest

from src.report.charts import (
    chart_technical_matrix,
    chart_event_table,
    chart_cars,
    chart_timezone_summary,
    chart_timezone_heatmap,
    chart_pca_etf,
    chart_pca_fx,
)

# PNG magic bytes
PNG_HEADER = b"\x89PNG\r\n\x1a\n"

PAIRS = ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "NZDUSD"]
G10 = ["EUR", "JPY", "GBP", "AUD", "NZD", "CAD", "CHF", "NOK", "SEK"]


def _assert_png(buf: io.BytesIO) -> None:
    data = buf.getvalue()
    assert len(data) > 1000, "PNG too small"
    assert data[:8] == PNG_HEADER, "Not a valid PNG"


@pytest.fixture
def tech_df():
    np.random.seed(42)
    rows = []
    signals = ["Bullish", "Sl. Bullish", "Bearish", "Sl. Bearish", "No Signal"]
    trends = ["↑", "↓", "↔"]
    adx = ["Uptrend", "Downtrend", "Range", "Transition"]
    boll = ["Upper", "Lower", "None"]
    for p in PAIRS:
        rows.append({
            "Pair": p, "Spot": np.random.uniform(0.6, 160),
            "Trend": np.random.choice(trends),
            "Signal": np.random.choice(signals),
            "ADX Trend": np.random.choice(adx),
            "Bollinger": np.random.choice(boll),
            "Next Support": 1.0, "Next Resistance": 1.1,
        })
    return pd.DataFrame(rows).set_index("Pair")


@pytest.fixture
def event_df():
    np.random.seed(42)
    rows = []
    sigs = ["Bullish Cont.", "Bullish Contr.", "Bearish Cont.", "Bearish Contr.", "No Signal"]
    for p in PAIRS:
        rows.append({
            "Pair": p, "Old Spot": 1.05, "New Spot": 1.06,
            "1m Vol": np.random.uniform(5, 20),
            "1m Vol Chg": np.random.uniform(-2, 2),
            "1w Vol": np.random.uniform(4, 18),
            "1w Vol Chg": np.random.uniform(-3, 3),
            "Ret vs USD": np.random.uniform(-3, 3),
            "Signal": np.random.choice(sigs),
        })
    return pd.DataFrame(rows).set_index("Pair")


@pytest.fixture
def cars_df():
    np.random.seed(42)
    rows = [{"Currency": c, "Bullish/Bearish": np.random.choice(["Bullish", "Bearish"]),
             "Equity": np.random.randint(1, 11),
             "Rates": np.random.randint(1, 11),
             "Commodity": np.random.randint(1, 11)} for c in G10]
    df = pd.DataFrame(rows).set_index("Currency")
    df.attrs["regime"] = "Normal"
    df.attrs["performing_factor"] = "equity"
    df.attrs["equity_z"] = 0.5
    df.attrs["bond_z"] = -0.3
    df.attrs["commodity_z"] = 1.2
    return df


@pytest.fixture
def tz_summary():
    np.random.seed(42)
    rows = [{"Pair": p, "America": np.random.uniform(-1, 1),
             "Europe": np.random.uniform(-1, 1),
             "Asia": np.random.uniform(-1, 1)} for p in PAIRS]
    return pd.DataFrame(rows).set_index("Pair")


@pytest.fixture
def tz_heatmap():
    np.random.seed(42)
    slots = ["8am-11am", "11am-2pm", "2pm-5pm", "5pm-8pm",
             "8pm-11pm", "11pm-2am", "2am-5am", "5am-8am"]
    rows = []
    for p in PAIRS:
        row = {"Pair": p}
        for s in slots:
            row[s] = np.random.uniform(-0.5, 0.5)
        rows.append(row)
    return pd.DataFrame(rows).set_index("Pair")


@pytest.fixture
def pca_etf_report():
    np.random.seed(42)
    etfs = ["SPY", "QQQ", "IWM", "TLT", "GLD", "DBC"]
    var_exp = [0.35, 0.15, 0.10, 0.07, 0.05]
    return {
        "loadings": pd.DataFrame(
            np.random.uniform(-0.5, 0.5, (len(etfs), 5)),
            index=etfs, columns=[f"PC{i+1}" for i in range(5)]),
        "eigenvalues": [v * 10 for v in var_exp],
        "variance_explained": var_exp,
        "cumulative_variance": np.cumsum(var_exp).tolist(),
        "effective_dim": 4.2,
        "regime": "Diversified",
        "n_assets": len(etfs),
        "window": 120,
        "top_loadings_per_pc": {},
    }


@pytest.fixture
def pca_fx_report():
    np.random.seed(42)
    var_exp = [0.45, 0.20, 0.12]
    return {
        "loadings": pd.DataFrame(
            np.random.uniform(-0.6, 0.6, (len(G10), 3)),
            index=G10, columns=["PC1", "PC2", "PC3"]),
        "eigenvalues": [v * 10 for v in var_exp],
        "variance_explained": var_exp,
        "cumulative_variance": np.cumsum(var_exp).tolist(),
        "effective_dim": 2.8,
        "regime": "Concentrated",
        "labels": {"PC1": "Dollar Factor", "PC2": "Carry Factor", "PC3": "Regional"},
        "pc_scores": pd.Series([1.5, -0.8, 0.3], index=["PC1", "PC2", "PC3"]),
        "pc_zscores": pd.Series([2.3, -1.1, 0.5], index=["PC1", "PC2", "PC3"]),
        "n_assets": len(G10),
        "window": 120,
    }


class TestChartTechnicalMatrix:
    def test_returns_png(self, tech_df):
        buf = chart_technical_matrix(tech_df, data_date="2026-02-16", frequency="Daily")
        _assert_png(buf)

    def test_single_pair(self):
        df = pd.DataFrame([{
            "Pair": "EURUSD", "Spot": 1.08, "Trend": "↑",
            "Signal": "Bullish", "ADX Trend": "Uptrend",
            "Bollinger": "None", "Next Support": 1.07, "Next Resistance": 1.09,
        }]).set_index("Pair")
        buf = chart_technical_matrix(df)
        _assert_png(buf)

    def test_no_metadata(self, tech_df):
        """Charts should work without data_date/frequency."""
        buf = chart_technical_matrix(tech_df)
        _assert_png(buf)


class TestChartEventTable:
    def test_returns_png(self, event_df):
        buf = chart_event_table(event_df, data_date="2026-02-16", frequency="Daily (5d return window)")
        _assert_png(buf)


class TestChartCars:
    def test_returns_png(self, cars_df):
        buf = chart_cars(cars_df, data_date="2026-02-16", frequency="Weekly (52w rolling)")
        assert buf is not None
        _assert_png(buf)

    def test_none_input(self):
        assert chart_cars(None) is None

    def test_empty_df(self):
        df = pd.DataFrame()
        assert chart_cars(df) is None

    def test_shock_regime(self, cars_df):
        cars_df.attrs["regime"] = "Shock"
        buf = chart_cars(cars_df)
        assert buf is not None
        _assert_png(buf)


class TestChartTimezoneSummary:
    def test_returns_png(self, tz_summary):
        buf = chart_timezone_summary(tz_summary, data_date="2026-02-16", frequency="Hourly (5d lookback)")
        _assert_png(buf)


class TestChartTimezoneHeatmap:
    def test_returns_png(self, tz_heatmap):
        buf = chart_timezone_heatmap(tz_heatmap, data_date="2026-02-16", frequency="Hourly (5d lookback)")
        _assert_png(buf)


class TestChartPcaEtf:
    def test_returns_two_pngs(self, pca_etf_report):
        bufs = chart_pca_etf(pca_etf_report, data_date="2026-02-16")
        assert len(bufs) == 2
        for buf in bufs:
            _assert_png(buf)

    def test_none_input(self):
        assert chart_pca_etf(None) == []


class TestChartPcaFx:
    def test_returns_two_pngs(self, pca_fx_report):
        bufs = chart_pca_fx(pca_fx_report, data_date="2026-02-16")
        assert len(bufs) == 2
        for buf in bufs:
            _assert_png(buf)

    def test_none_input(self):
        assert chart_pca_fx(None) == []

    def test_without_scores(self, pca_fx_report):
        del pca_fx_report["pc_scores"]
        del pca_fx_report["pc_zscores"]
        bufs = chart_pca_fx(pca_fx_report)
        assert len(bufs) == 1  # only loadings heatmap
        _assert_png(bufs[0])
