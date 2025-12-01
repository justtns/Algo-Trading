"""
Shared feature engineering utilities.
"""
from __future__ import annotations

import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n).mean()


def zscore(series: pd.Series, n: int) -> pd.Series:
    mean = series.rolling(n).mean()
    std = series.rolling(n).std()
    return (series - mean) / std


def feature_pipeline(bars: pd.DataFrame) -> pd.DataFrame:
    feats = pd.DataFrame(index=bars.index)
    feats["ema_20"] = ema(bars["close"], 20)
    feats["ema_50"] = ema(bars["close"], 50)
    feats["atr_14"] = atr(bars["high"], bars["low"], bars["close"], 14)
    feats["z_20"] = zscore(bars["close"], 20)
    return feats
