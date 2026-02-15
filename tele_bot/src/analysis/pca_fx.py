"""PCA on FX rates — Dollar/Carry/Regional factor extraction."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .pca_core import (
    pca_on_correlation,
    effective_dimensionality,
    detect_regime,
)
from .indicators import log_returns, zscore
from ..data.tickers import return_vs_usd_sign, USD_QUOTE_PAIRS

logger = logging.getLogger(__name__)


def compute_fx_log_returns(
    fx_data: dict[str, pd.DataFrame],
    window: int = 120,
) -> pd.DataFrame:
    """
    Build daily log returns for FX pairs with consistent sign convention.

    All returns are sign-corrected so positive = foreign currency
    appreciation vs USD (e.g. EUR strengthening).
    """
    closes: dict[str, pd.Series] = {}
    for pair, df in fx_data.items():
        if df is not None and not df.empty and "close" in df.columns:
            closes[pair] = df["close"]

    if not closes:
        return pd.DataFrame()

    price_df = pd.DataFrame(closes).sort_index()

    if len(price_df) > window:
        price_df = price_df.iloc[-window:]

    returns = np.log(price_df / price_df.shift(1)).iloc[1:]

    # Apply sign correction: for USD-base pairs (USDJPY), negate returns
    for pair in returns.columns:
        sign = return_vs_usd_sign(pair)
        if sign == -1:
            returns[pair] = -returns[pair]

    # Drop pairs with insufficient data
    min_valid = int(len(returns) * 0.8)
    valid_cols = [c for c in returns.columns if returns[c].notna().sum() >= min_valid]
    returns = returns[valid_cols]

    return returns


def compute_pc_scores(
    returns_df: pd.DataFrame,
    eigenvectors: np.ndarray,
    n_components: int = 3,
) -> pd.DataFrame:
    """
    Project standardised returns onto eigenvectors to get PC score time series.
    """
    # Standardise (z-score each column)
    standardised = (returns_df - returns_df.mean()) / returns_df.std()
    standardised = standardised.fillna(0.0)

    k = min(n_components, eigenvectors.shape[1])
    scores = standardised.values @ eigenvectors[:, :k]

    pc_names = [f"PC{i + 1}" for i in range(k)]
    return pd.DataFrame(scores, index=returns_df.index, columns=pc_names)


def pc_score_zscores(
    pc_scores: pd.DataFrame,
    window: int = 60,
) -> pd.DataFrame:
    """Rolling z-scores of each PC score."""
    result = pd.DataFrame(index=pc_scores.index)
    for col in pc_scores.columns:
        result[col] = zscore(pc_scores[col], window)
    return result


def interpret_fx_pcs(loadings_df: pd.DataFrame) -> dict[str, str]:
    """
    Heuristic labelling of FX principal components.

    PC1: if most loadings have the same sign → "Dollar Factor"
    PC2: if loadings show high-yield vs low-yield split → "Carry Factor"
    PC3: default → "Regional / Momentum"
    """
    labels = {}
    if "PC1" in loadings_df.columns:
        pc1 = loadings_df["PC1"]
        same_sign_ratio = max(
            (pc1 > 0).sum() / len(pc1),
            (pc1 < 0).sum() / len(pc1),
        )
        labels["PC1"] = "Dollar Factor" if same_sign_ratio > 0.6 else "Market Factor"

    if "PC2" in loadings_df.columns:
        labels["PC2"] = "Carry Factor"

    if "PC3" in loadings_df.columns:
        labels["PC3"] = "Regional / Momentum"

    return labels


def build_pca_fx_report(
    fx_data: dict[str, pd.DataFrame],
    window: int = 120,
    n_components: int = 3,
    zscore_window: int = 60,
    pc1_threshold: float = 0.60,
    dim_threshold: float = 3.0,
) -> dict | None:
    """
    Run PCA on G10 FX returns and produce a structured report.

    Returns dict with loadings, variance_explained, pc_scores, pc_zscores,
    labels, effective_dim, regime, or None if insufficient data.
    """
    returns = compute_fx_log_returns(fx_data, window=window)
    if returns.empty or returns.shape[1] < 3:
        logger.warning("Insufficient FX data for PCA (%d pairs)", returns.shape[1])
        return None

    result = pca_on_correlation(returns, n_components=n_components)
    if result is None:
        return None

    eff_dim = effective_dimensionality(result["eigenvalues"])
    regime = detect_regime(
        result["variance_explained"][0], eff_dim,
        pc1_threshold=pc1_threshold, dim_threshold=dim_threshold,
    )

    # PC scores and z-scores
    scores = compute_pc_scores(returns, result["loadings"].values, n_components)
    zscores = pc_score_zscores(scores, window=zscore_window)

    labels = interpret_fx_pcs(result["loadings"])

    return {
        "loadings": result["loadings"],
        "eigenvalues": result["eigenvalues"],
        "variance_explained": result["variance_explained"],
        "cumulative_variance": result["cumulative_variance"],
        "effective_dim": eff_dim,
        "regime": regime,
        "labels": labels,
        "pc_scores": scores.iloc[-1] if not scores.empty else pd.Series(),
        "pc_zscores": zscores.iloc[-1] if not zscores.empty else pd.Series(),
        "n_assets": result["n_assets"],
        "window": window,
    }
