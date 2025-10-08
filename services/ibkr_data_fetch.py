# services/ibkr_data_fetch.py
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timedelta, timezone

import pandas as pd
from ib_insync import IB, Stock, Forex, util

# ---------------- Helpers ----------------
def _to_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.set_index("date").sort_index()
    df.index.name = "datetime"
    return df

def _is_fx_symbol(sym: str) -> bool:
    s = sym.upper().replace(":", "")
    return (len(s) == 6 and s.isalpha()) or ("." in s)

def _fx_pair(sym: str) -> str:
    s = sym.upper().replace(":", "")
    return s.replace(".", "")  # e.g. USD.JPY -> USDJPY

def _bars_to_df(bars) -> pd.DataFrame:
    df = util.df(bars)
    if df is None or df.empty:
        return pd.DataFrame(columns=["open","high","low","close","volume"])
    df = _to_utc_index(df)
    return df[["open","high","low","close","volume"]]

# ---------------- Core: single call ----------------
async def fetch_ibkr_bars(
    symbol: str,
    *,
    exchange: Optional[str] = None,
    currency: Optional[str] = None,
    duration: str = "30 D",
    bar_size: str = "15 mins",
    what_to_show: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    client_id: Optional[int] = None,
    readonly: bool = True,
    outdir: str | Path = "../data",
    fname: Optional[str] = None,
    ib: Optional[IB] = None,
    end_datetime: Optional[datetime] = None,
) -> Path:
    """
    One-shot async fetch. For FX, auto-uses Forex(IDEALPRO) + whatToShow=MIDPOINT.
    Saves parquet and returns the Path.
    """
    host = host or os.getenv("IB_HOST", "127.0.0.1")
    port = int(port or os.getenv("IB_PORT", 7497))
    client_id = int(client_id or os.getenv("IB_CLIENT_ID", 1))
    end_datetime = end_datetime or datetime.now(timezone.utc)

    created_ib = False
    if ib is None:
        ib = IB()
        await ib.connectAsync(host, port, clientId=client_id, readonly=readonly)
        created_ib = True
    if "Y" in duration and "mins" in bar_size:
        ib.RequestTimeout = 60 * int(duration[0]) * 2 / (int("".join(ch for ch in bar_size if ch.isdigit())) / 15)

    try:
        if _is_fx_symbol(symbol):
            pair = _fx_pair(symbol)              # e.g. USDJPY
            contract = Forex(pair)               # secType=CASH, exchange='IDEALPRO'
            wtshow = what_to_show or "MIDPOINT"
        else:
            contract = Stock(symbol, exchange or "SMART", currency or "USD")
            wtshow = what_to_show or "TRADES"

        await ib.qualifyContractsAsync(contract)
        bars = await ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end_datetime,
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=wtshow,
            useRTH=False,
            formatDate=2,
            keepUpToDate=False,
        )

        df = _bars_to_df(bars)
        if df.empty:
            raise ValueError(f"No data returned for {symbol}")

        # filename with start/end
        start_date = df.index.min().strftime("%Y-%m-%d")
        end_date   = df.index.max().strftime("%Y-%m-%d")
        bar = bar_size.replace(" ", "")

        outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
        outpath = outdir / (fname or f"{symbol.lower().replace(':','').replace('.','')}_{bar}_{start_date}_{end_date}.parquet")
        df.to_parquet(outpath)
        print(f"Saved {len(df):,} rows → {outpath}")
        return outpath

    finally:
        if created_ib:
            ib.disconnect()

# ---------------- Range fetcher (chunked) ----------------
async def fetch_ibkr_bars_range_fx(
    symbol: str,                      # e.g. "USDJPY" or "USD.JPY"
    *,
    start: str,                       # "YYYY-MM-DD"
    end: str,                         # "YYYY-MM-DD"
    bar_size: str = "15 mins",
    what_to_show: str = "MIDPOINT",
    chunk_duration: str = "1 Y",      # IB limit-friendly chunk for 15-min bars
    host: Optional[str] = None,
    port: Optional[int] = None,
    client_id: Optional[int] = None,
    readonly: bool = True,
    outpath: str | Path = "data/usdjpy_15mins.parquet",
    ib: Optional[IB] = None,
) -> Path:
    """
    Chunked FX fetch from start..end. Stitches chunks newest->oldest.
    Saves a single parquet at `outpath`.
    """
    # Connect / reuse
    host = host or os.getenv("IB_HOST", "127.0.0.1")
    port = int(port or os.getenv("IB_PORT", 7497))
    client_id = int(client_id or os.getenv("IB_CLIENT_ID", 1))

    created_ib = False
    if ib is None:
        ib = IB()
        await ib.connectAsync(host, port, clientId=client_id, readonly=readonly)
        created_ib = True

    try:
        pair = _fx_pair(symbol)
        contract = Forex(pair)  # IDEALPRO
        await ib.qualifyContractsAsync(contract)

        end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
        start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)

        dfs: List[pd.DataFrame] = []
        cur_end = end_dt

        while True:
            bars = await ib.reqHistoricalDataAsync(
                contract,
                endDateTime=cur_end,
                durationStr=chunk_duration,    # e.g. "1 Y"
                barSizeSetting=bar_size,
                whatToShow=what_to_show,
                useRTH=False,
                formatDate=2,
                keepUpToDate=False,
            )
            df = _bars_to_df(bars)
            if df.empty:
                break

            # keep only within [start_dt, end_dt]
            df = df[(df.index >= start_dt) & (df.index <= end_dt)]
            if not df.empty:
                dfs.append(df)

            oldest = df.index.min()
            # stop when next chunk would go past start
            if oldest <= start_dt:
                break

            # step the end pointer just before oldest to avoid overlap
            cur_end = oldest - timedelta(seconds=1)

        if not dfs:
            raise ValueError(f"No data returned for {symbol} between {start} and {end}")

        full = pd.concat(dfs).sort_index()
        full = full[~full.index.duplicated(keep="first")]

        out = Path(outpath); out.parent.mkdir(parents=True, exist_ok=True)
        full.to_parquet(out)
        print(f"Saved {len(full):,} rows → {out}")
        return out

    finally:
        if created_ib:
            ib.disconnect()
