"""
Helpers to convert normalized OHLCV DataFrames to NautilusTrader Bar objects,
and to load parquet data into the Nautilus data catalog.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd

from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity


def dataframe_to_nautilus_bars(
    df: pd.DataFrame,
    bar_type: BarType,
) -> List[Bar]:
    """
    Convert a normalized OHLCV DataFrame to a list of NautilusTrader Bar objects.

    The DataFrame must have a DatetimeIndex and columns: open, high, low, close, volume.
    """
    if df is None or df.empty:
        return []

    price_prec = bar_type.instrument_id.symbol.value
    bars: List[Bar] = []

    for idx, row in df.iterrows():
        ts_ns = pd.Timestamp(idx).value  # nanoseconds since epoch
        bar = Bar(
            bar_type=bar_type,
            open=Price.from_str(f"{row['open']:.10f}".rstrip("0").rstrip(".")),
            high=Price.from_str(f"{row['high']:.10f}".rstrip("0").rstrip(".")),
            low=Price.from_str(f"{row['low']:.10f}".rstrip("0").rstrip(".")),
            close=Price.from_str(f"{row['close']:.10f}".rstrip("0").rstrip(".")),
            volume=Quantity.from_str(f"{row['volume']:.6f}".rstrip("0").rstrip(".")),
            ts_event=ts_ns,
            ts_init=ts_ns,
        )
        bars.append(bar)

    return bars


def load_parquet_to_bars(
    path: str | Path,
    bar_type: BarType,
    *,
    tz: str | None = "UTC",
) -> List[Bar]:
    """
    Load a parquet file and convert to NautilusTrader bars.
    """
    from trader.data.pipeline import DataHandler

    handler = DataHandler()
    df = handler.load_parquet(str(path), tz=tz)
    return dataframe_to_nautilus_bars(df, bar_type)


def invert_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """
    Invert an FX OHLCV DataFrame (e.g. USDJPY -> JPYUSD).
    High and low swap because 1/low > 1/high.
    """
    inv = df.copy()
    inv["open"] = 1.0 / df["open"]
    inv["high"] = 1.0 / df["low"]
    inv["low"] = 1.0 / df["high"]
    inv["close"] = 1.0 / df["close"]
    return inv
