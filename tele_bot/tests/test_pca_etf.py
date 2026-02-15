"""Tests for PCA ETF analysis module."""
import numpy as np
import pandas as pd
import pytest

from src.analysis.pca_etf import compute_etf_log_returns, build_pca_etf_report


def _make_etf_data(n_symbols: int = 10, n_days: int = 200) -> dict[str, pd.DataFrame]:
    """Create synthetic ETF price data with a common factor."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B", tz="UTC")
    factor = np.cumsum(np.random.randn(n_days) * 0.01) + 5.0  # trending

    data = {}
    for i in range(n_symbols):
        loading = 0.7 + 0.3 * np.random.rand()
        noise = np.cumsum(np.random.randn(n_days) * 0.005)
        prices = np.exp(np.log(100) + factor * loading + noise)
        data[f"ETF{i}"] = pd.DataFrame(
            {"open": prices, "high": prices * 1.01, "low": prices * 0.99,
             "close": prices, "volume": 1000000},
            index=dates,
        )
    return data


class TestComputeEtfLogReturns:
    def test_basic_shape(self):
        etf_data = _make_etf_data(n_symbols=5, n_days=200)
        returns = compute_etf_log_returns(etf_data, window=120)
        # window=120 minus 1 for diff
        assert returns.shape[0] == 119
        assert returns.shape[1] == 5

    def test_drops_insufficient_symbols(self):
        etf_data = _make_etf_data(n_symbols=3, n_days=200)
        # Add a symbol with only 10 days of data
        short_dates = pd.date_range("2024-09-01", periods=10, freq="B", tz="UTC")
        etf_data["SHORT"] = pd.DataFrame(
            {"close": np.random.rand(10) * 100}, index=short_dates,
        )
        returns = compute_etf_log_returns(etf_data, window=120)
        assert "SHORT" not in returns.columns

    def test_empty_input(self):
        returns = compute_etf_log_returns({}, window=120)
        assert returns.empty

    def test_window_trimming(self):
        etf_data = _make_etf_data(n_symbols=3, n_days=500)
        returns = compute_etf_log_returns(etf_data, window=60)
        assert returns.shape[0] == 59  # 60 - 1 for diff


class TestBuildPcaEtfReport:
    def test_report_structure(self):
        etf_data = _make_etf_data(n_symbols=10, n_days=200)
        report = build_pca_etf_report(etf_data, window=120, n_components=5)
        assert report is not None
        assert "loadings" in report
        assert "variance_explained" in report
        assert "effective_dim" in report
        assert "regime" in report
        assert "top_loadings_per_pc" in report
        assert report["n_assets"] == 10

    def test_returns_none_for_insufficient_data(self):
        etf_data = _make_etf_data(n_symbols=2, n_days=20)
        report = build_pca_etf_report(etf_data, window=120)
        assert report is None

    def test_variance_explained_values(self):
        etf_data = _make_etf_data(n_symbols=10, n_days=200)
        report = build_pca_etf_report(etf_data, window=120, n_components=5)
        assert report is not None
        # All values should be between 0 and 1
        for v in report["variance_explained"]:
            assert 0 <= v <= 1

    def test_top_loadings_per_pc(self):
        etf_data = _make_etf_data(n_symbols=10, n_days=200)
        report = build_pca_etf_report(etf_data, window=120, n_components=3)
        assert report is not None
        assert "PC1" in report["top_loadings_per_pc"]
        assert "top" in report["top_loadings_per_pc"]["PC1"]
        assert "bottom" in report["top_loadings_per_pc"]["PC1"]
        assert len(report["top_loadings_per_pc"]["PC1"]["top"]) == 3
