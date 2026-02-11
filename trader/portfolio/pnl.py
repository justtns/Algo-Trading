"""Performance metrics from equity time series."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _infer_periods_per_year(index: pd.DatetimeIndex) -> float:
    """Estimate annualization factor from a datetime index."""
    if len(index) < 2:
        return 252  # default to daily
    median_delta = pd.Series(index).diff().dropna().median()
    seconds = median_delta.total_seconds()
    if seconds <= 0:
        return 252
    seconds_per_year = 365.25 * 86400
    return seconds_per_year / seconds


def performance_metrics(
    equity_series: pd.Series,
    risk_free_rate: float = 0.0,
) -> dict:
    """
    Compute standard performance metrics from an equity time series.

    Parameters
    ----------
    equity_series : pd.Series
        Equity values indexed by datetime.
    risk_free_rate : float
        Annualized risk-free rate for Sharpe calculation.

    Returns
    -------
    dict with keys: total_return, annualized_return, volatility,
    sharpe_ratio, max_drawdown, calmar_ratio.
    """
    if equity_series.empty or len(equity_series) < 2:
        return {}

    returns = equity_series.pct_change().dropna()
    if returns.empty:
        return {}

    total_return = (equity_series.iloc[-1] / equity_series.iloc[0]) - 1
    periods = _infer_periods_per_year(equity_series.index)

    n = len(returns)
    exponent = periods / n
    if exponent > 1000:
        # Avoid overflow when annualizing very short series (e.g. 3 minute bars)
        annualized_return = float("inf") if total_return > 0 else float("-inf")
    else:
        annualized_return = (1 + total_return) ** exponent - 1

    volatility = float(returns.std() * np.sqrt(periods))
    sharpe = (
        (annualized_return - risk_free_rate) / volatility if volatility > 0 else 0.0
    )

    # Drawdown
    cummax = equity_series.cummax()
    drawdown = (equity_series - cummax) / cummax
    max_dd = float(drawdown.min())

    calmar = (
        annualized_return / abs(max_dd) if max_dd != 0 else float("inf")
    )

    return {
        "total_return": float(total_return),
        "annualized_return": float(annualized_return),
        "volatility": volatility,
        "sharpe_ratio": float(sharpe),
        "max_drawdown": max_dd,
        "calmar_ratio": float(calmar),
    }
