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


def rsi_macd_ma_signal(
    bars: pd.DataFrame,
    *,
    rsi_period: int = 14,
    rsi_oversold: float = 30.0,
    rsi_overbought: float = 70.0,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    ma_fast: int = 20,
    ma_slow: int = 50,
) -> float:
    """
    Signal logic requested by user:
    - SELL when RSI is oversold, MACD histogram curls downward, and MAs are bearish.
    - BUY when RSI is overbought, MACD histogram curls upward, and MAs are bullish.
    """
    if bars is None or bars.empty:
        return 0.0

    required = max(rsi_period + 2, macd_slow + macd_signal + 2, ma_slow + 1, 4)
    if len(bars) < required:
        return 0.0

    close = bars["close"].astype(float)
    rsi = _rsi(close, period=rsi_period)
    hist = _macd_histogram(
        close,
        fast_period=macd_fast,
        slow_period=macd_slow,
        signal_period=macd_signal,
    )
    ma_fast_v = close.rolling(ma_fast).mean()
    ma_slow_v = close.rolling(ma_slow).mean()

    if (
        pd.isna(rsi.iloc[-1])
        or pd.isna(hist.iloc[-1])
        or pd.isna(hist.iloc[-2])
        or pd.isna(hist.iloc[-3])
        or pd.isna(ma_fast_v.iloc[-1])
        or pd.isna(ma_slow_v.iloc[-1])
    ):
        return 0.0

    rsi_last = float(rsi.iloc[-1])
    h0 = float(hist.iloc[-1])
    h1 = float(hist.iloc[-2])
    h2 = float(hist.iloc[-3])
    px = float(close.iloc[-1])
    ma_fast_last = float(ma_fast_v.iloc[-1])
    ma_slow_last = float(ma_slow_v.iloc[-1])

    # "Curling" is treated as an inflection over the last 3 histogram points.
    hist_curling_down = h0 < h1 and h1 >= h2
    hist_curling_up = h0 > h1 and h1 <= h2

    ma_supports_sell = ma_fast_last < ma_slow_last and px < ma_fast_last
    ma_supports_buy = ma_fast_last > ma_slow_last and px > ma_fast_last

    if rsi_last <= rsi_oversold and hist_curling_down and ma_supports_sell:
        return -1.0
    if rsi_last >= rsi_overbought and hist_curling_up and ma_supports_buy:
        return 1.0
    return 0.0


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()

    avg_loss_safe = avg_loss.where(avg_loss != 0.0, other=1e-12)
    rs = avg_gain / avg_loss_safe
    rsi = 100.0 - (100.0 / (1.0 + rs))

    flat_mask = (avg_gain == 0.0) & (avg_loss == 0.0)
    up_only_mask = (avg_loss == 0.0) & (avg_gain > 0.0)
    rsi = rsi.mask(flat_mask, 50.0)
    rsi = rsi.mask(up_only_mask, 100.0)
    return rsi


def _macd_histogram(
    close: pd.Series,
    *,
    fast_period: int,
    slow_period: int,
    signal_period: int,
) -> pd.Series:
    ema_fast = close.ewm(span=fast_period, adjust=False).mean()
    ema_slow = close.ewm(span=slow_period, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    return macd_line - signal_line
