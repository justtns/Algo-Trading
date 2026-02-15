"""Tests for PCA core utilities."""
import numpy as np
import pandas as pd
import pytest

from src.analysis.pca_core import (
    pca_on_correlation,
    effective_dimensionality,
    detect_regime,
    top_bottom_loadings,
)


@pytest.fixture
def correlated_returns():
    """Create synthetic returns with a known factor structure."""
    np.random.seed(42)
    n_obs = 200
    # One dominant factor + noise
    factor = np.random.randn(n_obs)
    data = {}
    for i in range(10):
        loading = 0.8 if i < 7 else 0.2
        noise = np.random.randn(n_obs) * 0.5
        data[f"ASSET{i}"] = factor * loading + noise
    return pd.DataFrame(data)


@pytest.fixture
def uncorrelated_returns():
    """Create independent returns (no common factor)."""
    np.random.seed(123)
    n_obs = 200
    data = {f"ASSET{i}": np.random.randn(n_obs) for i in range(5)}
    return pd.DataFrame(data)


class TestPCAOnCorrelation:
    def test_returns_none_for_insufficient_data(self):
        df = pd.DataFrame({"A": [1.0, 2.0], "B": [3.0, 4.0]})
        assert pca_on_correlation(df) is None

    def test_returns_none_for_single_column(self):
        df = pd.DataFrame({"A": np.random.randn(50)})
        assert pca_on_correlation(df) is None

    def test_eigenvalues_descending(self, correlated_returns):
        result = pca_on_correlation(correlated_returns, n_components=5)
        assert result is not None
        ev = result["eigenvalues"]
        assert all(ev[i] >= ev[i + 1] for i in range(len(ev) - 1))

    def test_variance_explained_sums_near_one(self, correlated_returns):
        result = pca_on_correlation(correlated_returns, n_components=10)
        assert result is not None
        total = result["variance_explained"].sum()
        assert abs(total - 1.0) < 0.01

    def test_loadings_shape(self, correlated_returns):
        result = pca_on_correlation(correlated_returns, n_components=3)
        assert result is not None
        assert result["loadings"].shape == (10, 3)
        assert list(result["loadings"].columns) == ["PC1", "PC2", "PC3"]

    def test_pc1_dominates_with_correlated_data(self, correlated_returns):
        result = pca_on_correlation(correlated_returns, n_components=3)
        assert result is not None
        # PC1 should explain >40% with a dominant factor
        assert result["variance_explained"][0] > 0.40

    def test_cumulative_variance_monotonic(self, correlated_returns):
        result = pca_on_correlation(correlated_returns, n_components=5)
        assert result is not None
        cum = result["cumulative_variance"]
        assert all(cum[i] <= cum[i + 1] for i in range(len(cum) - 1))


class TestEffectiveDimensionality:
    def test_single_dominant_eigenvalue(self):
        # One large eigenvalue, rest tiny
        ev = np.array([10.0, 0.01, 0.01, 0.01])
        dim = effective_dimensionality(ev)
        assert dim < 1.5

    def test_equal_eigenvalues(self):
        # All equal → effective dim ≈ N
        ev = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
        dim = effective_dimensionality(ev)
        assert abs(dim - 5.0) < 0.01

    def test_zero_eigenvalues(self):
        ev = np.array([0.0, 0.0, 0.0])
        assert effective_dimensionality(ev) == 0.0

    def test_realistic_values(self):
        # Typical market: PC1 dominant but not sole
        ev = np.array([5.0, 2.0, 1.0, 0.5, 0.3])
        dim = effective_dimensionality(ev)
        assert 2.0 < dim < 5.0


class TestDetectRegime:
    def test_collapse_high_pc1(self):
        assert detect_regime(0.70, 5.0) == "Dimensionality Collapse"

    def test_collapse_low_dim(self):
        assert detect_regime(0.40, 2.0) == "Dimensionality Collapse"

    def test_normal(self):
        assert detect_regime(0.30, 5.0) == "Normal"

    def test_borderline(self):
        assert detect_regime(0.60, 3.0) == "Normal"
        assert detect_regime(0.61, 3.0) == "Dimensionality Collapse"


class TestTopBottomLoadings:
    def test_returns_correct_count(self, correlated_returns):
        result = pca_on_correlation(correlated_returns, n_components=3)
        top, bottom = top_bottom_loadings(result["loadings"], "PC1", n=3)
        assert len(top) == 3
        assert len(bottom) == 3

    def test_top_sorted_descending(self, correlated_returns):
        result = pca_on_correlation(correlated_returns, n_components=3)
        top, _ = top_bottom_loadings(result["loadings"], "PC1", n=3)
        vals = top.values
        assert all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))
