"""
Event Analysis: vol-guided decision proxy.

Since FX options/implied vol data is not available, we proxy using:
- FX realized volatility (1-week and 1-month)
- VIX as risk sentiment indicator
- Week-over-week changes in vol and spot

Derives 4 scenario signals matching BAML's framework:
  Bearish Continuation, Bearish Contrarian,
  Bullish Continuation, Bullish Contrarian.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..data.tickers import return_vs_usd_sign, spot_decimals


def _realized_vol_pct(close: pd.Series, window: int) -> pd.Series:
    """Annualized realized vol as percentage."""
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window).std() * np.sqrt(252) * 100


def compute_event_signal(
    fx_close: pd.Series,
    vix_close: pd.Series | None = None,
    *,
    spot_threshold: float = 1.0,
    rv_rise_threshold: float = 0.5,
    rv_sharp_rise: float = 1.0,
    rv_fall_threshold: float = -0.2,
) -> dict:
    """
    Compute event analysis signal for a single FX pair.

    Parameters
    ----------
    fx_close : pd.Series
        Daily close prices for the FX pair.
    vix_close : pd.Series or None
        Daily VIX close (for risk sentiment).

    Returns
    -------
    dict with keys: old_spot, new_spot, rv_1m, rv_1m_chg, rv_1w, rv_1w_chg,
                    spot_return_pct, vix_level, vix_chg, signal
    """
    if len(fx_close) < 30:
        return _empty_result()

    rv_1w = _realized_vol_pct(fx_close, 5)
    rv_1m = _realized_vol_pct(fx_close, 21)

    # Current values
    rv_1w_now = rv_1w.iloc[-1]
    rv_1m_now = rv_1m.iloc[-1]

    # Week-over-week change (vs 5 trading days ago)
    rv_1w_chg = rv_1w_now - rv_1w.iloc[-6] if len(rv_1w) >= 6 else 0.0
    rv_1m_chg = rv_1m_now - rv_1m.iloc[-6] if len(rv_1m) >= 6 else 0.0

    # Spot return over past week
    old_spot = float(fx_close.iloc[-6]) if len(fx_close) >= 6 else float(fx_close.iloc[0])
    new_spot = float(fx_close.iloc[-1])
    spot_ret = (new_spot / old_spot - 1) * 100

    # VIX
    vix_level = None
    vix_chg = 0.0
    if vix_close is not None and len(vix_close) >= 6:
        vix_level = float(vix_close.iloc[-1])
        vix_chg = float(vix_close.iloc[-1] - vix_close.iloc[-6])

    # Signal determination
    signal = _classify_signal(
        spot_ret, rv_1m_chg, vix_chg,
        spot_threshold=spot_threshold,
        rv_rise_threshold=rv_rise_threshold,
        rv_sharp_rise=rv_sharp_rise,
        rv_fall_threshold=rv_fall_threshold,
    )

    return {
        "old_spot": old_spot,
        "new_spot": new_spot,
        "rv_1m": _safe_round(rv_1m_now, 2),
        "rv_1m_chg": _safe_round(rv_1m_chg, 2),
        "rv_1w": _safe_round(rv_1w_now, 2),
        "rv_1w_chg": _safe_round(rv_1w_chg, 2),
        "spot_return_pct": round(spot_ret, 2),
        "vix_level": _safe_round(vix_level, 1) if vix_level else None,
        "vix_chg": round(vix_chg, 2),
        "signal": signal,
    }


def _classify_signal(
    spot_ret: float,
    rv_1m_chg: float,
    vix_chg: float,
    *,
    spot_threshold: float,
    rv_rise_threshold: float,
    rv_sharp_rise: float,
    rv_fall_threshold: float,
) -> str:
    """
    [1] Bearish Continuation: spot down, vol rising, VIX rising
    [2] Bearish Contrarian: spot up, vol rising sharply
    [3] Bullish Continuation: spot up, vol falling
    [4] Bullish Contrarian: spot down, vol falling, VIX falling
    """
    if spot_ret < -spot_threshold and rv_1m_chg > rv_rise_threshold and vix_chg > 0:
        return "Bearish Cont."
    if spot_ret > spot_threshold and rv_1m_chg > rv_sharp_rise:
        return "Bearish Contr."
    if spot_ret > spot_threshold and rv_1m_chg < rv_fall_threshold:
        return "Bullish Cont."
    if spot_ret < -spot_threshold and rv_1m_chg < rv_fall_threshold and vix_chg < 0:
        return "Bullish Contr."
    return "No Signal"


def _safe_round(val, decimals: int):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return round(float(val), decimals)


def _empty_result() -> dict:
    return {
        "old_spot": None, "new_spot": None,
        "rv_1m": None, "rv_1m_chg": None,
        "rv_1w": None, "rv_1w_chg": None,
        "spot_return_pct": None, "vix_level": None, "vix_chg": None,
        "signal": "N/A",
    }


def build_event_table(
    all_pair_data: dict[str, pd.DataFrame],
    vix_data: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Build event analysis table for all pairs.

    Parameters
    ----------
    all_pair_data : dict
        pair -> DataFrame with OHLCV.
    vix_data : DataFrame or None
        VIX/VIXY daily OHLCV.

    Returns
    -------
    DataFrame indexed by pair with event analysis columns.
    """
    vix_close = vix_data["close"] if vix_data is not None and not vix_data.empty else None

    rows: list[dict] = []
    for pair, df in all_pair_data.items():
        if df is None or df.empty:
            result = _empty_result()
        else:
            result = compute_event_signal(df["close"], vix_close)

        # Compute return vs USD with correct sign convention
        sign = return_vs_usd_sign(pair)
        ret_vs_usd = result["spot_return_pct"]
        if ret_vs_usd is not None:
            ret_vs_usd = round(ret_vs_usd * sign, 2)

        rows.append({
            "Pair": pair,
            "Old Spot": result["old_spot"],
            "New Spot": result["new_spot"],
            "1m Vol": result["rv_1m"],
            "1m Vol Chg": result["rv_1m_chg"],
            "1w Vol": result["rv_1w"],
            "1w Vol Chg": result["rv_1w_chg"],
            "Ret vs USD": ret_vs_usd,
            "Signal": result["signal"],
        })

    return pd.DataFrame(rows).set_index("Pair")
