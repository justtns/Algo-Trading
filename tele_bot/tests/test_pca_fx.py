"""Tests for PCA FX analysis module."""
import numpy as np
import pandas as pd
import pytest

from src.analysis.pca_fx import (
    compute_fx_log_returns,
    compute_pc_scores,
    pc_score_zscores,
    interpret_fx_pcs,
    build_pca_fx_report,
)


def _make_fx_data(n_days: int = 200) -> dict[str, pd.DataFrame]:
    """Create synthetic G10 FX price data."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B", tz="UTC")

    # Simulate a "dollar factor" + pair-specific noise
    dollar_factor = np.cumsum(np.random.randn(n_days) * 0.003)

    pairs = {
        "EURUSD": (1.08, 1),   # USD quote, sign=+1
        "GBPUSD": (1.26, 1),
        "AUDUSD": (0.65, 1),
        "NZDUSD": (0.61, 1),
        "USDJPY": (150.0, -1),  # USD base, sign=-1
        "USDCHF": (0.88, -1),
        "USDCAD": (1.36, -1),
        "USDSEK": (10.5, -1),
        "USDNOK": (10.8, -1),
    }

    data = {}
    for pair, (base_price, _sign) in pairs.items():
        noise = np.cumsum(np.random.randn(n_days) * 0.002)
        prices = base_price * np.exp(dollar_factor + noise)
        data[pair] = pd.DataFrame(
            {"open": prices, "high": prices * 1.005, "low": prices * 0.995,
             "close": prices, "volume": 0},
            index=dates,
        )
    return data


class TestComputeFxLogReturns:
    def test_sign_convention(self):
        """Positive return should mean foreign currency appreciation vs USD."""
        fx_data = _make_fx_data(n_days=200)
        returns = compute_fx_log_returns(fx_data, window=120)
        # All columns should be present
        assert "EURUSD" in returns.columns
        assert "USDJPY" in returns.columns
        # Returns should be finite
        assert returns.notna().all().all()

    def test_shape(self):
        fx_data = _make_fx_data(n_days=200)
        returns = compute_fx_log_returns(fx_data, window=120)
        assert returns.shape[0] == 119  # 120 - 1 for diff
        assert returns.shape[1] == 9

    def test_empty_input(self):
        returns = compute_fx_log_returns({}, window=120)
        assert returns.empty


class TestComputePcScores:
    def test_shape(self):
        fx_data = _make_fx_data(n_days=200)
        returns = compute_fx_log_returns(fx_data, window=120)
        n_components = 3
        eigenvectors = np.random.randn(returns.shape[1], n_components)
        scores = compute_pc_scores(returns, eigenvectors, n_components)
        assert scores.shape == (len(returns), n_components)
        assert list(scores.columns) == ["PC1", "PC2", "PC3"]


class TestPcScoreZscores:
    def test_output_shape(self):
        fx_data = _make_fx_data(n_days=200)
        returns = compute_fx_log_returns(fx_data, window=120)
        eigenvectors = np.eye(returns.shape[1])[:, :3]
        scores = compute_pc_scores(returns, eigenvectors, 3)
        zscores = pc_score_zscores(scores, window=30)
        assert zscores.shape == scores.shape


class TestInterpretFxPcs:
    def test_dollar_factor_label(self):
        # All same-sign loadings → "Dollar Factor"
        loadings = pd.DataFrame({
            "PC1": [0.3, 0.4, 0.35, 0.32, 0.38, 0.31, 0.29, 0.33, 0.36],
            "PC2": [0.5, -0.4, 0.3, -0.2, 0.1, -0.3, 0.4, -0.1, 0.2],
            "PC3": [0.1, 0.2, -0.3, 0.4, -0.1, 0.2, -0.3, 0.1, -0.2],
        })
        labels = interpret_fx_pcs(loadings)
        assert labels["PC1"] == "Dollar Factor"
        assert labels["PC2"] == "Carry Factor"
        assert labels["PC3"] == "Regional / Momentum"


class TestBuildPcaFxReport:
    def test_report_structure(self):
        fx_data = _make_fx_data(n_days=200)
        report = build_pca_fx_report(fx_data, window=120, n_components=3)
        assert report is not None
        assert "loadings" in report
        assert "variance_explained" in report
        assert "pc_scores" in report
        assert "pc_zscores" in report
        assert "labels" in report
        assert "effective_dim" in report
        assert "regime" in report

    def test_returns_none_for_insufficient_data(self):
        fx_data = _make_fx_data(n_days=20)
        report = build_pca_fx_report(fx_data, window=120)
        assert report is None

    def test_pc_scores_not_empty(self):
        fx_data = _make_fx_data(n_days=200)
        report = build_pca_fx_report(fx_data, window=120, n_components=3)
        assert report is not None
        assert not report["pc_scores"].empty
        assert len(report["pc_scores"]) == 3
