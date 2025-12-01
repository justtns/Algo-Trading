"""
Signal functions: bars/features -> target positions.
"""
from __future__ import annotations

import pandas as pd


def mean_reversion_signal(bars: pd.DataFrame) -> float:
    if bars is None or bars.empty:
        return 0.0
    window = bars["close"].tail(20)
    ma = window.mean()
    px = window.iloc[-1]
    if px < ma * 0.999:
        return 1.0
    if px > ma * 1.001:
        return -1.0
    return 0.0


def breakout_signal(bars: pd.DataFrame) -> float:
    if bars is None or bars.empty or len(bars) < 50:
        return 0.0
    high = bars["high"].tail(50).max()
    low = bars["low"].tail(50).min()
    px = bars["close"].iloc[-1]
    if px >= high:
        return 1.0
    if px <= low:
        return -1.0
    return 0.0
