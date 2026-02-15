"""
Time Zone Analysis: cumulative FX returns by trading session.

Splits 24-hour trading day into 3 regional zones and 8 granular 3-hour slots.
Matches BAML Exhibits 16-17.

Zone definitions (UTC):
  America: 1pm - 12am (13:00 - 00:00)
  Europe:  8am - 1pm  (08:00 - 13:00)
  Asia:    12am - 8am (00:00 - 08:00)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..data.tickers import return_vs_usd_sign


# Three major trading sessions
TIMEZONE_ZONES: dict[str, tuple[int, int]] = {
    "America": (13, 0),   # 1pm to midnight UTC (wraps)
    "Europe": (8, 13),    # 8am to 1pm UTC
    "Asia": (0, 8),       # midnight to 8am UTC
}

# Eight 3-hour granular slots (UTC hours)
GRANULAR_SLOTS: list[tuple[str, int, int]] = [
    ("8am-11am", 8, 11),
    ("11am-2pm", 11, 14),
    ("2pm-5pm", 14, 17),
    ("5pm-8pm", 17, 20),
    ("8pm-11pm", 20, 23),
    ("11pm-2am", 23, 2),    # wraps midnight
    ("2am-5am", 2, 5),
    ("5am-8am", 5, 8),
]


def _hour_mask(index: pd.DatetimeIndex, start_h: int, end_h: int) -> pd.Series:
    """Boolean mask for hours within [start_h, end_h). Handles midnight wrap."""
    hours = pd.Series(index.hour, index=index)
    if start_h < end_h:
        return (hours >= start_h) & (hours < end_h)
    else:
        # Wraps midnight: e.g., 23 -> 2 means hour >= 23 OR hour < 2
        return (hours >= start_h) | (hours < end_h)


def _cumulative_return(hourly_df: pd.DataFrame, mask: pd.Series) -> float:
    """
    Compute cumulative return for the masked hours.
    Uses close-to-close chain: product of (1 + hourly_return) - 1.
    """
    subset = hourly_df.loc[mask]
    if len(subset) < 2:
        return 0.0
    returns = subset["close"].pct_change().dropna()
    cum = (1 + returns).prod() - 1
    return float(cum) * 100  # as percentage


def compute_timezone_returns(
    hourly_df: pd.DataFrame,
    lookback_days: int = 5,
) -> dict[str, float]:
    """
    Cumulative returns by timezone zone over the lookback period.

    Returns dict mapping zone name -> cumulative return (%).
    """
    if hourly_df is None or hourly_df.empty:
        return {zone: 0.0 for zone in TIMEZONE_ZONES}

    # Approximate: last N*24 hours of data
    n_rows = lookback_days * 24
    recent = hourly_df.iloc[-n_rows:] if len(hourly_df) > n_rows else hourly_df

    results = {}
    for zone_name, (start_h, end_h) in TIMEZONE_ZONES.items():
        mask = _hour_mask(recent.index, start_h, end_h)
        results[zone_name] = round(_cumulative_return(recent, mask), 3)

    return results


def build_timezone_summary(
    all_pair_hourly: dict[str, pd.DataFrame],
    lookback_days: int = 5,
) -> pd.DataFrame:
    """
    Build timezone return summary: rows = pairs, columns = America/Europe/Asia.
    """
    rows: list[dict] = []
    for pair, df in all_pair_hourly.items():
        tz_ret = compute_timezone_returns(df, lookback_days)
        sign = return_vs_usd_sign(pair)
        rows.append({
            "Pair": pair,
            "America": round(tz_ret.get("America", 0.0) * sign, 3),
            "Europe": round(tz_ret.get("Europe", 0.0) * sign, 3),
            "Asia": round(tz_ret.get("Asia", 0.0) * sign, 3),
        })

    return pd.DataFrame(rows).set_index("Pair")


def build_timezone_heatmap(
    all_pair_hourly: dict[str, pd.DataFrame],
    lookback_days: int = 5,
) -> pd.DataFrame:
    """
    Build 8-slot granular heatmap (Exhibit 17).
    Rows = pairs, Columns = 8 three-hour UTC slots.
    Values = cumulative % change.
    """
    rows: list[dict] = []
    for pair, df in all_pair_hourly.items():
        if df is None or df.empty:
            row = {"Pair": pair}
            for slot_name, _, _ in GRANULAR_SLOTS:
                row[slot_name] = 0.0
            rows.append(row)
            continue

        n_rows = lookback_days * 24
        recent = df.iloc[-n_rows:] if len(df) > n_rows else df
        sign = return_vs_usd_sign(pair)

        row = {"Pair": pair}
        for slot_name, start_h, end_h in GRANULAR_SLOTS:
            mask = _hour_mask(recent.index, start_h, end_h)
            ret = _cumulative_return(recent, mask) * sign
            row[slot_name] = round(ret, 2)
        rows.append(row)

    return pd.DataFrame(rows).set_index("Pair")
