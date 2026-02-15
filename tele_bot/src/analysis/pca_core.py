"""Shared PCA utilities for ETF and FX factor analysis."""
from __future__ import annotations

import numpy as np
import pandas as pd


def pca_on_correlation(
    returns_df: pd.DataFrame, n_components: int = 5,
) -> dict | None:
    """
    PCA via eigendecomposition of the correlation matrix.

    Parameters
    ----------
    returns_df : DataFrame
        Daily log returns with assets as columns.
    n_components : int
        Number of principal components to extract.

    Returns
    -------
    dict with eigenvalues, loadings, variance_explained, etc., or None
    if insufficient data.
    """
    clean = returns_df.dropna()
    if len(clean) < 30 or clean.shape[1] < 2:
        return None

    corr_matrix = clean.corr().values
    tickers = list(clean.columns)
    n = len(tickers)

    eigenvalues, eigenvectors = np.linalg.eigh(corr_matrix)

    # eigh returns ascending order; reverse to descending
    idx = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    # Clip negative eigenvalues (numerical noise)
    eigenvalues = np.maximum(eigenvalues, 0.0)

    k = min(n_components, n)
    eigenvalues_k = eigenvalues[:k]
    eigenvectors_k = eigenvectors[:, :k]

    total_var = eigenvalues.sum()
    if total_var == 0:
        return None
    var_explained = eigenvalues_k / total_var
    cum_var = np.cumsum(var_explained)

    pc_names = [f"PC{i + 1}" for i in range(k)]
    loadings = pd.DataFrame(eigenvectors_k, index=tickers, columns=pc_names)

    return {
        "eigenvalues": eigenvalues_k,
        "variance_explained": var_explained,
        "cumulative_variance": cum_var,
        "loadings": loadings,
        "tickers": tickers,
        "n_assets": n,
    }


def effective_dimensionality(eigenvalues: np.ndarray) -> float:
    """
    Participation ratio: measures effective number of independent factors.

    (sum(lambda_i))^2 / sum(lambda_i^2)

    Value near 1 = one factor dominates (risk-off).
    Value near N = fully diversified.
    """
    ev = np.maximum(eigenvalues, 0.0)
    total = ev.sum()
    if total == 0:
        return 0.0
    return float(total ** 2 / (ev ** 2).sum())


def detect_regime(
    var_explained_pc1: float,
    eff_dim: float,
    pc1_threshold: float = 0.60,
    dim_threshold: float = 3.0,
) -> str:
    """
    Classify market regime based on PCA concentration.

    Returns "Dimensionality Collapse" if PC1 dominance is high
    or effective dimensionality is low, else "Normal".
    """
    if var_explained_pc1 > pc1_threshold or eff_dim < dim_threshold:
        return "Dimensionality Collapse"
    return "Normal"


def top_bottom_loadings(
    loadings_df: pd.DataFrame, pc: str = "PC1", n: int = 3,
) -> tuple[pd.Series, pd.Series]:
    """Return top-N and bottom-N loadings for a given PC, sorted by value."""
    col = loadings_df[pc].sort_values(ascending=False)
    return col.head(n), col.tail(n)
