"""
IBKR helpers: historical fetch + live streaming into DataStreamer using ib_insync.
"""
from __future__ import annotations

import asyncio
from typing import Iterable, Optional

import pandas as pd

from historical_data_services.ibkr_data_fetch import fetch_ibkr_bars, fetch_ibkr_bars_range_fx
from trader.data.pipeline import DataHandler, DataStreamer


class IBKRHistoryService:
    def __init__(self, handler: Optional[DataHandler] = None):
        self.handler = handler or DataHandler()

    async def fetch_range_fx(
        self,
        symbol: str,
        start: str,
        end: str,
        *,
        bar_size: str = "15 mins",
        outpath: str | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        path = await fetch_ibkr_bars_range_fx(
            symbol,
            start=start,
            end=end,
            bar_size=bar_size,
            outpath=outpath or f"saved_data/{symbol.lower()}_{bar_size.replace(' ','')}.parquet",
            **kwargs,
        )
        return self.handler.load_parquet(path)


class IBKRLiveStreamer:
    """
    Live streaming adapter using ib_insync real-time bars (5s native cadence).
    Pushes bars into a DataStreamer.
    """

    def __init__(
        self,
        streamer: DataStreamer,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        client_id: Optional[int] = None,
        readonly: bool = True,
    ):
        self.streamer = streamer
        self.host = host
        self.port = port
        self.client_id = client_id
        self.readonly = readonly
        self.ib = None
        self._subscriptions = []

    async def connect(self):
        try:
            from ib_insync import IB
        except ImportError as e:
            raise ImportError("ib_insync is required for IBKRLiveStreamer") from e

        self.ib = IB()
        await self.ib.connectAsync(
            self.host or "127.0.0.1",
            int(self.port or 7497),
            clientId=int(self.client_id or 1),
            readonly=self.readonly,
        )
        return self

    async def _contract(self, symbol: str):
        from ib_insync import Forex, Stock

        s = symbol.upper().replace(":", "").replace(".", "")
        if len(s) == 6 and s.isalpha():
            c = Forex(s)
        else:
            c = Stock(symbol, "SMART", "USD")
        await self.ib.qualifyContractsAsync(c)  # type: ignore
        return c

    async def stream_realtime_bars(
        self,
        symbols: Iterable[str],
        *,
        what_to_show: str = "MIDPOINT",
        use_rth: bool = False,
    ):
        """
        Subscribe to real-time bars and push into DataStreamer until cancelled.
        """
        if self.ib is None:
            await self.connect()

        for sym in symbols:
            c = await self._contract(sym)
            bars = self.ib.reqRealTimeBars(c, 5, what_to_show, useRTH=use_rth)  # type: ignore
            self._subscriptions.append(bars)

        try:
            while True:
                await asyncio.sleep(0.5)
                for sub in list(self._subscriptions):
                    for bar in sub:
                        payload = {
                            "datetime": pd.to_datetime(bar.time, utc=True),
                            "open": float(bar.open),
                            "high": float(bar.high),
                            "low": float(bar.low),
                            "close": float(bar.close),
                            "volume": float(bar.volume),
                        }
                        self.streamer.push_bar(payload)
                    sub.clear()
        except asyncio.CancelledError:
            pass

    def close(self):
        for sub in self._subscriptions:
            try:
                sub.cancel()
            except Exception:
                pass
        if self.ib:
            self.ib.disconnect()
        self._subscriptions = []


__all__ = [
    "fetch_ibkr_bars",
    "fetch_ibkr_bars_range_fx",
    "IBKRHistoryService",
    "IBKRLiveStreamer",
]
