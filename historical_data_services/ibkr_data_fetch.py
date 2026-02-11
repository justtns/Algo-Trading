# services/ibkr_data_fetch.py
from __future__ import annotations
import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timedelta, timezone

import pandas as pd
from ib_insync import IB, Stock, Forex, util

from trader.data.retry import RetryConfig, retry_async

logger = logging.getLogger(__name__)

_IBKR_RETRY = RetryConfig(
    max_retries=3,
    base_delay=5.0,
    max_delay=120.0,
    backoff_factor=2.0,
    retryable_exceptions=(asyncio.TimeoutError, ConnectionError, OSError),
)

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


def _compute_timeout(duration: str, bar_size: str) -> float:
    """Estimate reasonable request timeout based on data volume.

    Parses IB duration strings (e.g. '1 Y', '30 D', '3600 S') and bar size
    strings (e.g. '15 mins', '1 hour', '1 day') to approximate the number
    of bars, then scales the timeout accordingly.
    """
    # Parse duration to seconds
    match = re.match(r"(\d+)\s*([YDWMS])", duration.strip(), re.IGNORECASE)
    if not match:
        return 60.0
    val, unit = int(match.group(1)), match.group(2).upper()
    unit_map = {"S": 1, "D": 86400, "W": 604800, "M": 2592000, "Y": 31536000}
    duration_sec = val * unit_map.get(unit, 86400)

    # Parse bar size to seconds
    bar_match = re.match(r"(\d+)\s*(sec|min|hour|day|week|month)", bar_size.strip(), re.IGNORECASE)
    if not bar_match:
        return 60.0
    bar_val = int(bar_match.group(1))
    bar_unit = bar_match.group(2).lower()
    bar_unit_map = {"sec": 1, "min": 60, "hour": 3600, "day": 86400, "week": 604800, "month": 2592000}
    # Handle plural forms
    for key in bar_unit_map:
        if bar_unit.startswith(key):
            bar_sec = bar_val * bar_unit_map[key]
            break
    else:
        bar_sec = 60

    estimated_bars = duration_sec / bar_sec
    # ~500 bars per 10 seconds of timeout, minimum 30s, maximum 300s
    return max(30.0, min(300.0, estimated_bars / 500 * 10))


async def _connect_with_retry(
    ib: IB,
    host: str,
    port: int,
    client_id: int,
    readonly: bool,
) -> None:
    """Connect to IB Gateway/TWS with retry on transient failures."""
    for attempt in range(3):
        try:
            await ib.connectAsync(host, port, clientId=client_id, readonly=readonly)
            return
        except (ConnectionError, OSError, asyncio.TimeoutError) as e:
            if attempt == 2:
                raise
            delay = 5 * (2 ** attempt)
            logger.warning(
                "IBKR connection attempt %d failed: %s. Retrying in %ds",
                attempt + 1, e, delay,
            )
            await asyncio.sleep(delay)


@retry_async(_IBKR_RETRY)
async def _fetch_bars_with_retry(ib: IB, contract, **kwargs):
    """Wrap reqHistoricalDataAsync with retry logic."""
    return await ib.reqHistoricalDataAsync(contract, **kwargs)


@retry_async(_IBKR_RETRY)
async def _qualify_with_retry(ib: IB, contract):
    """Wrap qualifyContractsAsync with retry logic."""
    return await ib.qualifyContractsAsync(contract)


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
        await _connect_with_retry(ib, host, port, client_id, readonly)
        created_ib = True

    ib.RequestTimeout = _compute_timeout(duration, bar_size)

    try:
        if _is_fx_symbol(symbol):
            pair = _fx_pair(symbol)              # e.g. USDJPY
            contract = Forex(pair)               # secType=CASH, exchange='IDEALPRO'
            wtshow = what_to_show or "MIDPOINT"
        else:
            contract = Stock(symbol, exchange or "SMART", currency or "USD")
            wtshow = what_to_show or "TRADES"

        await _qualify_with_retry(ib, contract)
        bars = await _fetch_bars_with_retry(
            ib,
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
        logger.info("Saved %s rows -> %s", f"{len(df):,}", outpath)
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
        await _connect_with_retry(ib, host, port, client_id, readonly)
        created_ib = True

    ib.RequestTimeout = _compute_timeout(chunk_duration, bar_size)

    try:
        pair = _fx_pair(symbol)
        contract = Forex(pair)  # IDEALPRO
        await _qualify_with_retry(ib, contract)

        end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
        start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)

        dfs: List[pd.DataFrame] = []
        cur_end = end_dt

        while True:
            try:
                bars = await _fetch_bars_with_retry(
                    ib,
                    contract,
                    endDateTime=cur_end,
                    durationStr=chunk_duration,
                    barSizeSetting=bar_size,
                    whatToShow=what_to_show,
                    useRTH=False,
                    formatDate=2,
                    keepUpToDate=False,
                )
            except Exception as e:
                logger.warning("Chunk fetch failed at %s: %s. Stopping.", cur_end, e)
                break

            df = _bars_to_df(bars)
            if df.empty:
                logger.warning("Empty chunk at %s, stopping.", cur_end)
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

            # Pace requests to avoid IB pacing violations
            await asyncio.sleep(3)

        if not dfs:
            raise ValueError(f"No data returned for {symbol} between {start} and {end}")

        full = pd.concat(dfs).sort_index()
        full = full[~full.index.duplicated(keep="first")]

        out = Path(outpath); out.parent.mkdir(parents=True, exist_ok=True)
        full.to_parquet(out)
        logger.info("Saved %s rows -> %s", f"{len(full):,}", out)
        return out

    finally:
        if created_ib:
            ib.disconnect()
