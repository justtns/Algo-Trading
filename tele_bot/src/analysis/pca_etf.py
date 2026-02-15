"""PCA on ETF universe — geographic/sector factor decomposition."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .pca_core import (
    pca_on_correlation,
    effective_dimensionality,
    detect_regime,
    top_bottom_loadings,
)
from .indicators import log_returns

logger = logging.getLogger(__name__)


def compute_etf_log_returns(
    etf_data: dict[str, pd.DataFrame],
    window: int = 120,
) -> pd.DataFrame:
    """
    Build a DataFrame of daily log returns for the ETF universe.

    Drops symbols with fewer than 80% non-NaN values in the window.
    """
    closes: dict[str, pd.Series] = {}
    for symbol, df in etf_data.items():
        if df is not None and not df.empty and "close" in df.columns:
            closes[symbol] = df["close"]

    if not closes:
        return pd.DataFrame()

    price_df = pd.DataFrame(closes).sort_index()

    # Trim to last `window` rows
    if len(price_df) > window:
        price_df = price_df.iloc[-window:]

    # Compute log returns
    returns = np.log(price_df / price_df.shift(1)).iloc[1:]

    # Drop symbols with insufficient coverage (<80%)
    min_valid = int(len(returns) * 0.8)
    valid_cols = [c for c in returns.columns if returns[c].notna().sum() >= min_valid]
    returns = returns[valid_cols]

    return returns


def build_pca_etf_report(
    etf_data: dict[str, pd.DataFrame],
    window: int = 120,
    n_components: int = 5,
    pc1_threshold: float = 0.60,
    dim_threshold: float = 3.0,
) -> dict | None:
    """
    Run PCA on ETF returns and produce a structured report.

    Returns dict with loadings, variance_explained, regime, effective_dim,
    top_loadings_per_pc, or None if insufficient data.
    """
    returns = compute_etf_log_returns(etf_data, window=window)
    if returns.empty or returns.shape[1] < 3:
        logger.warning("Insufficient ETF data for PCA (%d symbols)", returns.shape[1])
        return None

    result = pca_on_correlation(returns, n_components=n_components)
    if result is None:
        return None

    eff_dim = effective_dimensionality(result["eigenvalues"])
    regime = detect_regime(
        result["variance_explained"][0], eff_dim,
        pc1_threshold=pc1_threshold, dim_threshold=dim_threshold,
    )

    # Top/bottom loadings for PC1-PC3
    n_pcs = min(3, len(result["eigenvalues"]))
    top_loadings_per_pc = {}
    for i in range(n_pcs):
        pc = f"PC{i + 1}"
        top, bottom = top_bottom_loadings(result["loadings"], pc, n=3)
        top_loadings_per_pc[pc] = {"top": top, "bottom": bottom}

    return {
        "loadings": result["loadings"],
        "eigenvalues": result["eigenvalues"],
        "variance_explained": result["variance_explained"],
        "cumulative_variance": result["cumulative_variance"],
        "effective_dim": eff_dim,
        "regime": regime,
        "n_assets": result["n_assets"],
        "window": window,
        "top_loadings_per_pc": top_loadings_per_pc,
    }
