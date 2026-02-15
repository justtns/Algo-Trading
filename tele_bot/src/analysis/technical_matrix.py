"""
Technical Matrix: replicates BAML Exhibit 8.

Computes per-pair: MAA positioning trend, Bullish/Bearish signal (from MAA + UD + RS),
ADX trend, Bollinger band signal, and next support/resistance levels.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import (
    sma, adx_dmi, bollinger_bands, fibonacci_levels, percentile_rank,
)

# ---------------------------------------------------------------------------
# MAA: 28 short/long SMA comparison pairs
# ---------------------------------------------------------------------------

MA_PAIRS: list[tuple[int, int]] = [
    (5, 20), (5, 50), (5, 100), (5, 200),
    (10, 20), (10, 50), (10, 100), (10, 200),
    (15, 50), (15, 100), (15, 200),
    (20, 50), (20, 100), (20, 200),
    (25, 50), (25, 100), (25, 200),
    (30, 50), (30, 100), (30, 200),
    (35, 50), (35, 100), (35, 200),
    (40, 50), (40, 100), (40, 200),
    (50, 100), (50, 200),
]


def compute_maa(close: pd.Series) -> float:
    """
    Moving Average Aggregator.

    Average of 28 binary conditions: 1 if short SMA > long SMA, else 0.
    Returns percentage 0-100.  High = heavy long positioning (uptrend).
    """
    signals: list[int] = []
    for short_w, long_w in MA_PAIRS:
        short_val = sma(close, short_w).iloc[-1]
        long_val = sma(close, long_w).iloc[-1]
        if pd.notna(short_val) and pd.notna(long_val):
            signals.append(1 if short_val > long_val else 0)
    if not signals:
        return 50.0
    return 100.0 * sum(signals) / len(signals)


def positioning_trend_arrow(maa: float) -> str:
    """Arrow character for the positioning trend column."""
    if maa > 60:
        return "\u2191"  # ↑
    elif maa < 40:
        return "\u2193"  # ↓
    else:
        return "\u2194"  # ↔


# ---------------------------------------------------------------------------
# UD: Up/Down Volatility
# ---------------------------------------------------------------------------

def _compute_ud_raw(close: pd.Series, window: int = 21) -> pd.Series:
    """
    Rolling UD raw value: down_vol / (up_vol + down_vol) * 100.

    High value = greater down volatility relative to total = bearish signal.
    """
    log_ret = np.log(close / close.shift(1))
    results = pd.Series(np.nan, index=close.index)

    for i in range(window, len(close)):
        chunk = log_ret.iloc[i - window + 1 : i + 1].dropna()
        up = chunk[chunk > 0]
        down = chunk[chunk < 0]

        up_vol = up.std() * np.sqrt(252) if len(up) > 1 else 0.0
        down_vol = down.std() * np.sqrt(252) if len(down) > 1 else 0.0

        total = up_vol + down_vol
        if total > 0:
            results.iloc[i] = (down_vol / total) * 100
        else:
            results.iloc[i] = 50.0

    return results


def compute_ud(close: pd.Series, window: int = 21, percentile_lookback: int = 252) -> float:
    """UD indicator: 1-year percentile rank of the rolling UD raw value."""
    ud_raw = _compute_ud_raw(close, window)
    current = ud_raw.iloc[-1]
    if pd.isna(current):
        return 50.0
    history = ud_raw.iloc[-percentile_lookback:]
    return percentile_rank(current, history)


# ---------------------------------------------------------------------------
# RS: Residual Skew proxy (realized skewness)
# ---------------------------------------------------------------------------

def compute_rs_proxy(close: pd.Series, weekly_window: int = 26, percentile_weeks: int = 52) -> float:
    """
    Residual Skew proxy using realized distribution of weekly returns.

    Computes 26-week rolling skewness, then takes 1-year percentile rank.
    High RS = positive skew (stretched long). Low RS = light positioning.
    """
    weekly_close = close.resample("W-FRI").last().dropna()
    if len(weekly_close) < weekly_window + percentile_weeks:
        return 50.0

    weekly_ret = np.log(weekly_close / weekly_close.shift(1)).dropna()
    rolling_skew = weekly_ret.rolling(weekly_window).skew()

    current_skew = rolling_skew.iloc[-1]
    if pd.isna(current_skew):
        return 50.0

    history = rolling_skew.iloc[-percentile_weeks:]
    return percentile_rank(current_skew, history)


# ---------------------------------------------------------------------------
# Positioning signal
# ---------------------------------------------------------------------------

def positioning_signal(maa: float, ud: float, rs: float) -> str:
    """
    Derive Bullish/Bearish signal from MAA, UD, RS.

    Uptrend (MAA > 60):
      - Reversal (Bearish): UD > 80 AND RS > 80
      - Continuation (Bullish): UD < 50 AND RS < 50
      - Slightly Bearish/Bullish if only one supports

    Downtrend (MAA < 40):
      - Reversal (Bullish): UD < 20 AND RS < 20
      - Continuation (Bearish): UD > 50 AND RS > 50
      - Slightly variants if only one supports

    Neutral (40 <= MAA <= 60): No Signal
    """
    if maa > 60:
        if ud > 80 and rs > 80:
            return "Bearish"
        if ud < 50 and rs < 50:
            return "Bullish"
        if ud > 80 or rs > 80:
            return "Sl. Bearish"
        if ud < 50 or rs < 50:
            return "Sl. Bullish"
        return "No Signal"
    elif maa < 40:
        if ud < 20 and rs < 20:
            return "Bullish"
        if ud > 50 and rs > 50:
            return "Bearish"
        if ud < 20 or rs < 20:
            return "Sl. Bullish"
        if ud > 50 or rs > 50:
            return "Sl. Bearish"
        return "No Signal"
    else:
        return "No Signal"


# ---------------------------------------------------------------------------
# ADX trend classification
# ---------------------------------------------------------------------------

def adx_trend_label(adx_val: float, dmi_plus: float, dmi_minus: float) -> str:
    """
    ADX < 20: Range
    ADX 20-25: Transition
    ADX >= 25: Uptrend (DMI+ > DMI-) or Downtrend (DMI- > DMI+)
    """
    if pd.isna(adx_val):
        return "N/A"
    if adx_val < 20:
        return "Range"
    if adx_val < 25:
        return "Transition"
    if dmi_plus > dmi_minus:
        return "Uptrend"
    return "Downtrend"


# ---------------------------------------------------------------------------
# Bollinger band signal
# ---------------------------------------------------------------------------

def bollinger_signal(spot: float, upper: float, lower: float) -> str:
    if pd.isna(upper) or pd.isna(lower):
        return "None"
    if spot > upper:
        return "Upper"
    if spot < lower:
        return "Lower"
    return "None"


# ---------------------------------------------------------------------------
# Support / Resistance
# ---------------------------------------------------------------------------

def compute_support_resistance(
    close: pd.Series, high: pd.Series, low: pd.Series,
) -> dict[str, float | None]:
    """
    Gather candidate levels from SMAs, 1y/2y high-low, and Fibonacci.
    Return nearest support (below spot) and resistance (above spot).
    """
    spot = float(close.iloc[-1])
    candidates: list[float] = []

    # SMA levels
    for w in (50, 100, 200):
        val = sma(close, w).iloc[-1]
        if pd.notna(val):
            candidates.append(float(val))

    # 1-year and 2-year high/low + Fibonacci
    for lookback in (252, 504):
        n = min(lookback, len(close))
        h = float(high.iloc[-n:].max())
        l = float(low.iloc[-n:].min())
        candidates.extend([h, l])
        fibs = fibonacci_levels(h, l)
        candidates.extend(fibs.values())

    support_levels = sorted([c for c in candidates if c < spot], reverse=True)
    resist_levels = sorted([c for c in candidates if c > spot])

    return {
        "next_support": support_levels[0] if support_levels else None,
        "next_resistance": resist_levels[0] if resist_levels else None,
    }


# ---------------------------------------------------------------------------
# Full Technical Matrix builder
# ---------------------------------------------------------------------------

def build_technical_matrix(all_pair_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Build the full Technical Matrix (Exhibit 8) for all pairs.

    Parameters
    ----------
    all_pair_data : dict
        Mapping of pair name -> DataFrame with columns: open, high, low, close, volume.
        Must have at least ~250 rows for reliable indicators.

    Returns
    -------
    DataFrame with columns: Spot, Trend, Signal, ADX Trend, Bollinger,
                            Next Support, Next Resistance
    """
    rows: list[dict] = []

    for pair, df in all_pair_data.items():
        if df is None or df.empty or len(df) < 50:
            rows.append({
                "Pair": pair, "Spot": None, "Trend": "N/A",
                "Signal": "N/A", "ADX Trend": "N/A", "Bollinger": "N/A",
                "Next Support": None, "Next Resistance": None,
            })
            continue

        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)

        spot = float(close.iloc[-1])

        # MAA
        maa = compute_maa(close)
        trend = positioning_trend_arrow(maa)

        # UD + RS -> positioning signal
        ud = compute_ud(close) if len(close) >= 252 else 50.0
        rs = compute_rs_proxy(close) if len(close) >= 252 else 50.0
        signal = positioning_signal(maa, ud, rs)

        # ADX
        adx_df = adx_dmi(high, low, close, period=14)
        adx_label = adx_trend_label(
            float(adx_df["ADX"].iloc[-1]),
            float(adx_df["DMI_plus"].iloc[-1]),
            float(adx_df["DMI_minus"].iloc[-1]),
        )

        # Bollinger
        bb = bollinger_bands(close, 20, 2.0)
        bb_sig = bollinger_signal(spot, float(bb["upper"].iloc[-1]), float(bb["lower"].iloc[-1]))

        # Support / Resistance
        sr = compute_support_resistance(close, high, low)

        rows.append({
            "Pair": pair,
            "Spot": spot,
            "Trend": trend,
            "Signal": signal,
            "ADX Trend": adx_label,
            "Bollinger": bb_sig,
            "Next Support": sr["next_support"],
            "Next Resistance": sr["next_resistance"],
        })

    return pd.DataFrame(rows).set_index("Pair")
