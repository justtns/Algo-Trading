"""
CARS: Cross-Asset Regime Switching.

Replicates the BAML CARS model (Exhibit 11) using cross-asset proxies:
- Equity: SPY
- Bonds/Rates: TLT (inverted for yield proxy)
- Commodities: DBC

Decision tree:
1. Detect macro shock (sharp cross-asset declines)
2. Shock week -> Defensive strategy (buy JPY/CHF, sell rest vs USD)
3. Normal week -> Rank currencies by performing factor (equity or rates),
   top 3 bullish, bottom 3 bearish.  Commodity overlay if extreme.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import zscore
from ..data.tickers import G10_PAIRS, currency_from_pair, USD_QUOTE_PAIRS


SAFE_HAVEN_CURRENCIES = {"JPY", "CHF"}


def _weekly_returns(daily_close: pd.Series) -> pd.Series:
    """Resample to weekly Friday close, compute simple returns."""
    weekly = daily_close.resample("W-FRI").last().dropna()
    return weekly.pct_change().dropna()


def _weekly_zscore(daily_close: pd.Series, lookback_weeks: int = 52) -> float:
    """Z-score of the most recent weekly return over a rolling window."""
    weekly_ret = _weekly_returns(daily_close)
    if len(weekly_ret) < lookback_weeks:
        return 0.0
    z = zscore(weekly_ret, lookback_weeks)
    val = z.iloc[-1]
    return float(val) if pd.notna(val) else 0.0


def classify_regime(
    equity_close: pd.Series,
    bond_close: pd.Series,
    commodity_close: pd.Series,
    *,
    equity_shock_z: float = -1.0,
    bond_shock_z: float = -1.0,
    commodity_shock_z: float = -2.0,
) -> dict:
    """
    Classify current week as macro shock or normal.

    Shock = any cross-asset weekly return z-score below threshold.
    For bonds: TLT dropping sharply = yields spiking = shock.
    """
    eq_z = _weekly_zscore(equity_close)
    bd_z = _weekly_zscore(bond_close)
    cm_z = _weekly_zscore(commodity_close)

    is_shock = (eq_z < equity_shock_z or bd_z < bond_shock_z or cm_z < commodity_shock_z)

    return {
        "is_shock": is_shock,
        "equity_z": round(eq_z, 2),
        "bond_z": round(bd_z, 2),
        "commodity_z": round(cm_z, 2),
        "regime": "Shock" if is_shock else "Normal",
    }


def _fx_weekly_return(fx_close: pd.Series, pair: str) -> pd.Series:
    """Weekly return with sign convention: positive = foreign ccy strengthened vs USD."""
    weekly = fx_close.resample("W-FRI").last().dropna()
    ret = weekly.pct_change().dropna()
    if pair in USD_QUOTE_PAIRS:
        return ret  # rising spot = foreign ccy stronger
    return -ret  # rising USDXXX = foreign ccy weaker


def compute_factor_rankings(
    fx_pair_data: dict[str, pd.DataFrame],
    equity_close: pd.Series,
    bond_close: pd.Series,
    commodity_close: pd.Series,
    *,
    corr_window: int = 52,
) -> pd.DataFrame:
    """
    Rank G10 currencies by rolling correlation with cross-asset factors.

    Returns DataFrame indexed by currency with columns:
    equity_corr, rates_corr, commodity_corr, equity_rank, rates_rank, commodity_rank
    """
    eq_weekly = _weekly_returns(equity_close)
    bd_weekly = _weekly_returns(bond_close)
    cm_weekly = _weekly_returns(commodity_close)

    records: list[dict] = []

    for pair in G10_PAIRS:
        ccy = currency_from_pair(pair)
        df = fx_pair_data.get(pair)
        if df is None or df.empty:
            records.append({"Currency": ccy, "equity_corr": 0, "rates_corr": 0, "commodity_corr": 0})
            continue

        fx_ret = _fx_weekly_return(df["close"], pair)

        # Align indices
        common_eq = fx_ret.index.intersection(eq_weekly.index)
        common_bd = fx_ret.index.intersection(bd_weekly.index)
        common_cm = fx_ret.index.intersection(cm_weekly.index)

        eq_corr = fx_ret.loc[common_eq].rolling(corr_window).corr(eq_weekly.loc[common_eq]).iloc[-1] if len(common_eq) > corr_window else 0.0
        bd_corr = fx_ret.loc[common_bd].rolling(corr_window).corr(bd_weekly.loc[common_bd]).iloc[-1] if len(common_bd) > corr_window else 0.0
        cm_corr = fx_ret.loc[common_cm].rolling(corr_window).corr(cm_weekly.loc[common_cm]).iloc[-1] if len(common_cm) > corr_window else 0.0

        records.append({
            "Currency": ccy,
            "equity_corr": round(float(eq_corr) if pd.notna(eq_corr) else 0.0, 3),
            "rates_corr": round(float(bd_corr) if pd.notna(bd_corr) else 0.0, 3),
            "commodity_corr": round(float(cm_corr) if pd.notna(cm_corr) else 0.0, 3),
        })

    df = pd.DataFrame(records).set_index("Currency")
    df["equity_rank"] = df["equity_corr"].rank(ascending=False).astype(int)
    df["rates_rank"] = df["rates_corr"].rank(ascending=False).astype(int)
    df["commodity_rank"] = df["commodity_corr"].rank(ascending=False).astype(int)
    return df


def generate_cars_signals(
    regime: dict,
    factor_rankings: pd.DataFrame,
    *,
    performing_factor: str = "rates",
    commodity_overlay_threshold: float = 2.0,
) -> pd.DataFrame:
    """
    Generate CARS buy/sell signals per currency.

    Shock week: Buy JPY/CHF, Sell rest vs USD.
    Normal week: Use performing factor ranking. Top 3 = Bullish, Bottom 3 = Bearish.
    Commodity overlay if |commodity_z| > threshold.
    """
    results: list[dict] = []
    n_currencies = len(factor_rankings)

    if regime["is_shock"]:
        for ccy in factor_rankings.index:
            signal = "Bullish" if ccy in SAFE_HAVEN_CURRENCIES else "Bearish"
            results.append({
                "Currency": ccy,
                "Bullish/Bearish": signal,
                "Equity": int(factor_rankings.loc[ccy, "equity_rank"]),
                "Rates": int(factor_rankings.loc[ccy, "rates_rank"]),
                "Commodity": int(factor_rankings.loc[ccy, "commodity_rank"]),
            })
    else:
        rank_col = f"{performing_factor}_rank"
        ranked = factor_rankings.sort_values(rank_col)

        for i, (ccy, row) in enumerate(ranked.iterrows()):
            if i < 3:
                signal = "Bullish"
            elif i >= n_currencies - 3:
                signal = "Bearish"
            else:
                signal = ""

            # Commodity overlay
            if abs(regime["commodity_z"]) > commodity_overlay_threshold:
                cm_rank = int(row["commodity_rank"])
                if regime["commodity_z"] > commodity_overlay_threshold and cm_rank <= 3:
                    signal = signal or "Bullish"
                elif regime["commodity_z"] < -commodity_overlay_threshold and cm_rank <= 3:
                    signal = signal or "Bearish"

            results.append({
                "Currency": ccy,
                "Bullish/Bearish": signal,
                "Equity": int(row["equity_rank"]),
                "Rates": int(row["rates_rank"]),
                "Commodity": int(row["commodity_rank"]),
            })

    df = pd.DataFrame(results).set_index("Currency")

    # Add metadata columns
    df.attrs["regime"] = regime["regime"]
    df.attrs["performing_factor"] = performing_factor if not regime["is_shock"] else "defensive"
    df.attrs["equity_z"] = regime["equity_z"]
    df.attrs["bond_z"] = regime["bond_z"]
    df.attrs["commodity_z"] = regime["commodity_z"]

    return df


def build_cars_report(
    fx_pair_data: dict[str, pd.DataFrame],
    equity_data: pd.DataFrame | None,
    bond_data: pd.DataFrame | None,
    commodity_data: pd.DataFrame | None,
) -> pd.DataFrame | None:
    """
    End-to-end CARS analysis.

    Returns signals DataFrame or None if insufficient data.
    """
    if equity_data is None or bond_data is None or commodity_data is None:
        return None
    if equity_data.empty or bond_data.empty or commodity_data.empty:
        return None

    eq_close = equity_data["close"]
    bd_close = bond_data["close"]
    cm_close = commodity_data["close"]

    regime = classify_regime(eq_close, bd_close, cm_close)
    rankings = compute_factor_rankings(fx_pair_data, eq_close, bd_close, cm_close)

    # Default to rates (most prevalent regime per BAML data)
    return generate_cars_signals(regime, rankings, performing_factor="rates")
