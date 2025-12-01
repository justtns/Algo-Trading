"""
Data store for persisting ticks/bars/fills to parquet. Lightweight helper.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd


class DataStore:
    def __init__(self, root: str | Path = "saved_data"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_bars(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Path:
        path = self.root / f"{symbol}_{timeframe}.parquet"
        df.to_parquet(path)
        return path

    def load_bars(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        path = self.root / f"{symbol}_{timeframe}.parquet"
        if not path.exists():
            return None
        return pd.read_parquet(path)
