"""
Data pipeline utilities: normalization, IO helpers, and resampling.
Framework-agnostic — works with any engine consuming pandas DataFrames.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd


class DataNormalizer:
    """
    Normalizes raw DataFrames into OHLCV frames indexed by UTC datetime.
    """

    required_cols = ("open", "high", "low", "close", "volume")

    def __call__(self, df: pd.DataFrame, *, tz: str | None = "UTC") -> pd.DataFrame:
        return self.to_ohlcv(df, tz=tz)

    def to_ohlcv(self, df: pd.DataFrame, *, tz: str | None = "UTC") -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=self.required_cols)

        cols = {c: c.lower() for c in df.columns}
        df = df.rename(columns=cols)
        missing = [c for c in self.required_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Missing columns: {missing}")

        if "datetime" in df.columns:
            dt_index = pd.to_datetime(df["datetime"], utc=True)
        else:
            dt_index = pd.to_datetime(df.index, utc=True)

        if tz:
            dt_index = dt_index.tz_convert(tz)

        ohlcv = df[list(self.required_cols)].copy()
        ohlcv.index = dt_index
        ohlcv.index.name = "datetime"
        return ohlcv.sort_index()


class DataHandler:
    """
    Provides IO helpers to read parquet/csv and resample into normalized OHLCV.
    """

    def __init__(self, normalizer: Optional[DataNormalizer] = None):
        self.normalizer = normalizer or DataNormalizer()

    def load_parquet(self, path: str, *, tz: str | None = "UTC") -> pd.DataFrame:
        df = pd.read_parquet(path)
        return self.normalizer.to_ohlcv(df, tz=tz)

    def load_csv(self, path: str, *, tz: str | None = "UTC") -> pd.DataFrame:
        df = pd.read_csv(path)
        return self.normalizer.to_ohlcv(df, tz=tz)

    def resample(
        self,
        df: pd.DataFrame,
        *,
        rule: str,
        label: str = "right",
        closed: str = "right",
    ) -> pd.DataFrame:
        agg = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
        return df.resample(rule, label=label, closed=closed).agg(agg).dropna()  # type: ignore


@dataclass
class DataPackage:
    """
    Small wrapper to pass normalized OHLCV and metadata around.
    """

    symbol: str
    dataframe: pd.DataFrame
    source: Optional[str] = None
    timeframe: str | None = None
    normalized_at: datetime | None = None

