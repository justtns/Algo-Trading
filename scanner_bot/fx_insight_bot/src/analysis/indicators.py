"""Shared technical indicator functions used across all analysis components."""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Moving averages
# ---------------------------------------------------------------------------

def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------

def realized_vol(close: pd.Series, window: int = 21) -> pd.Series:
    """Annualized realized volatility from log returns (as percentage)."""
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window).std() * np.sqrt(252) * 100


def log_returns(close: pd.Series) -> pd.Series:
    return np.log(close / close.shift(1))


def weekly_returns(close: pd.Series) -> pd.Series:
    """Resample to weekly (Friday) and compute log returns."""
    weekly_close = close.resample("W-FRI").last().dropna()
    return np.log(weekly_close / weekly_close.shift(1)).dropna()


# ---------------------------------------------------------------------------
# ADX / DMI (Wilder smoothing)
# ---------------------------------------------------------------------------

def adx_dmi(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14,
) -> pd.DataFrame:
    """
    Average Directional Index with DMI+ and DMI-.
    Returns DataFrame with columns: ADX, DMI_plus, DMI_minus.
    """
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    # True Range
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Directional Movement
    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = pd.Series(0.0, index=high.index)
    minus_dm = pd.Series(0.0, index=high.index)

    plus_mask = (up_move > down_move) & (up_move > 0)
    minus_mask = (down_move > up_move) & (down_move > 0)

    plus_dm[plus_mask] = up_move[plus_mask]
    minus_dm[minus_mask] = down_move[minus_mask]

    # Wilder smoothing (EMA with alpha = 1/period)
    alpha = 1.0 / period
    atr = tr.ewm(alpha=alpha, adjust=False).mean()
    smooth_plus_dm = plus_dm.ewm(alpha=alpha, adjust=False).mean()
    smooth_minus_dm = minus_dm.ewm(alpha=alpha, adjust=False).mean()

    # Directional Indicators
    atr_safe = atr.where(atr != 0, other=1e-12)
    dmi_plus = 100 * smooth_plus_dm / atr_safe
    dmi_minus = 100 * smooth_minus_dm / atr_safe

    # DX and ADX
    di_sum = dmi_plus + dmi_minus
    di_sum_safe = di_sum.where(di_sum != 0, other=1e-12)
    dx = 100 * (dmi_plus - dmi_minus).abs() / di_sum_safe
    adx_val = dx.ewm(alpha=alpha, adjust=False).mean()

    return pd.DataFrame({
        "ADX": adx_val,
        "DMI_plus": dmi_plus,
        "DMI_minus": dmi_minus,
    }, index=high.index)


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def bollinger_bands(
    close: pd.Series, window: int = 20, num_std: float = 2.0,
) -> pd.DataFrame:
    mid = sma(close, window)
    std = close.rolling(window).std()
    return pd.DataFrame({
        "middle": mid,
        "upper": mid + num_std * std,
        "lower": mid - num_std * std,
    }, index=close.index)


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()

    avg_loss_safe = avg_loss.where(avg_loss != 0.0, other=1e-12)
    rs = avg_gain / avg_loss_safe
    rsi_val = 100.0 - (100.0 / (1.0 + rs))

    flat_mask = (avg_gain == 0.0) & (avg_loss == 0.0)
    up_only_mask = (avg_loss == 0.0) & (avg_gain > 0.0)
    rsi_val = rsi_val.mask(flat_mask, 50.0)
    rsi_val = rsi_val.mask(up_only_mask, 100.0)
    return rsi_val


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def macd_histogram(
    close: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> pd.Series:
    ema_fast = close.ewm(span=fast_period, adjust=False).mean()
    ema_slow = close.ewm(span=slow_period, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    return macd_line - signal_line


# ---------------------------------------------------------------------------
# Fibonacci levels
# ---------------------------------------------------------------------------

def fibonacci_levels(high: float, low: float) -> dict[str, float]:
    """Retracement levels between a high and low."""
    diff = high - low
    return {
        "fib_382": high - 0.382 * diff,
        "fib_500": high - 0.500 * diff,
        "fib_618": high - 0.618 * diff,
    }


# ---------------------------------------------------------------------------
# Z-score
# ---------------------------------------------------------------------------

def zscore(series: pd.Series, window: int) -> pd.Series:
    """Rolling z-score."""
    mu = series.rolling(window).mean()
    sigma = series.rolling(window).std()
    sigma_safe = sigma.where(sigma != 0, other=1e-12)
    return (series - mu) / sigma_safe


def percentile_rank(value: float, history: pd.Series) -> float:
    """Percentile rank of value within history (0-100)."""
    valid = history.dropna()
    if len(valid) == 0:
        return 50.0
    return float((valid < value).sum()) / len(valid) * 100.0
