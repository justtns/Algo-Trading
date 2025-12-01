from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from queue import Empty, Queue
from typing import Iterable, Optional

import backtrader as bt
import pandas as pd


class DataNormalizer:
    """
    Normalizes raw dataframes into Backtrader-friendly OHLCV frames indexed by UTC datetime.
    """

    required_cols = ("open", "high", "low", "close", "volume")

    def __call__(self, df: pd.DataFrame, *, tz: str | None = "UTC") -> pd.DataFrame:
        return self.to_ohlcv(df, tz=tz)

    def to_ohlcv(self, df: pd.DataFrame, *, tz: str | None = "UTC") -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=self.required_cols)

        # Lower-case column names and keep only OHLCV
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

    def to_bt_feed(
        self,
        df: pd.DataFrame,
        *,
        name: Optional[str] = None,
        tz: str | None = "UTC",
    ) -> bt.feeds.PandasData:
        normalized = self.to_ohlcv(df, tz=tz)
        return bt.feeds.PandasData(dataname=normalized, name=name)


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
        """
        Resamples OHLCV into a new timeframe.
        """
        agg = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
        return df.resample(rule, label=label, closed=closed).agg(agg).dropna()


class DataStreamer:
    """
    Broadcasts normalized bar dictionaries to subscribed queues.
    """

    def __init__(self):
        self._subscribers: list[Queue] = []
        self._closed = False

    def subscribe(self, maxsize: int = 10_000) -> Queue:
        q: Queue = Queue(maxsize=maxsize)
        self._subscribers.append(q)
        return q

    def push_bar(self, bar: dict) -> None:
        if self._closed:
            return
        required = {"datetime", "open", "high", "low", "close", "volume"}
        if not required.issubset(bar.keys()):
            missing = required.difference(bar.keys())
            raise ValueError(f"Missing bar keys: {missing}")
        for q in self._subscribers:
            q.put_nowait(bar)

    def from_dataframe(self, df: pd.DataFrame, delay_sec: float = 0.0) -> None:
        """
        Stream bars from a dataframe sequentially. Useful for backtesting with live-like flow.
        """
        if df is None or df.empty:
            return
        for idx, row in df.iterrows():
            bar = {
                "datetime": pd.to_datetime(idx, utc=True),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
            self.push_bar(bar)
            if delay_sec:
                time.sleep(delay_sec)
        self.close()

    def close(self) -> None:
        self._closed = True
        for q in self._subscribers:
            q.put_nowait(None)


class StreamingOHLCVFeed(bt.feeds.DataBase):
    """
    Backtrader data feed that consumes OHLCV bars from a Queue provided by DataStreamer.
    Put a sentinel None on the queue to stop the feed.
    """

    params = (("name", None),)
    lines = ("open", "high", "low", "close", "volume", "openinterest")
    datafields = lines

    def __init__(self, source_queue: Queue, *, name: Optional[str] = None):
        super().__init__()
        self._queue = source_queue
        self._stopped = False
        self.p.name = name

    def _load(self):
        if self._stopped:
            return False
        try:
            bar = self._queue.get(timeout=0.5)
        except Empty:
            return None

        if bar is None:
            self._stopped = True
            return False

        dt = pd.to_datetime(bar["datetime"]).to_pydatetime()
        self.lines.datetime[0] = bt.date2num(dt)
        self.lines.open[0] = float(bar["open"])
        self.lines.high[0] = float(bar["high"])
        self.lines.low[0] = float(bar["low"])
        self.lines.close[0] = float(bar["close"])
        self.lines.volume[0] = float(bar.get("volume", 0))
        self.lines.openinterest[0] = float(bar.get("openinterest", 0))
        return True


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

