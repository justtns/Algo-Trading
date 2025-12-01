"""
IBKR helpers: historical fetch + optional streaming adapter placeholder.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from historical_data_services.ibkr_data_fetch import fetch_ibkr_bars, fetch_ibkr_bars_range_fx
from trader.data.pipeline import DataHandler


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


__all__ = ["fetch_ibkr_bars", "fetch_ibkr_bars_range_fx", "IBKRHistoryService"]
