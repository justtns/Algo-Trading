import logging
import os
import time
from pathlib import Path
from typing import Optional, Iterable
from datetime import datetime, timedelta

import pandas as pd
from polygon import RESTClient

logger = logging.getLogger(__name__)

# --- Helpers -----------------------------------------------------------------
def _fx_symbol_to_polygon(symbol: str) -> str:
    s = symbol.strip().upper()
    if s.startswith(("C:", "X:")):
        return s
    if len(s) == 6 and s.isalpha():
        return f"C:{s}"
    return s

def _bars_to_df(bars: Iterable) -> pd.DataFrame:
    rows = []
    for b in bars:
        rows.append(
            dict(
                datetime=pd.to_datetime(b.timestamp, unit="ms", utc=True),
                open=b.open,
                high=b.high,
                low=b.low,
                close=b.close,
                volume=b.volume,
            )
        )
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows).set_index("datetime").sort_index()
    return df[["open", "high", "low", "close", "volume"]]

def _to_dates(s):  # "YYYY-MM-DD" -> date
    return datetime.strptime(s, "%Y-%m-%d").date()

def _drange(start_d, end_d, chunk_days=30):
    cur = start_d
    one = timedelta(days=1)
    step = timedelta(days=chunk_days)
    while cur <= end_d:
        chunk_end = min(cur + step - one, end_d)
        yield cur, chunk_end
        cur = chunk_end + one


def _adaptive_pause(rate_limit: int = 5, window_sec: float = 60.0) -> float:
    """Calculate pause to stay under rate limit with headroom."""
    return window_sec / rate_limit


def _fetch_aggs_with_retry(
    client: RESTClient,
    max_retries: int = 5,
    base_delay: float = 2.0,
    **kwargs,
) -> list:
    """Fetch aggs with retry on transient failures and rate limits."""
    for attempt in range(max_retries + 1):
        try:
            return list(client.list_aggs(**kwargs))
        except Exception as e:
            error_str = str(e)
            is_retryable = any(
                code in error_str for code in ("429", "500", "502", "503", "504")
            )
            if not is_retryable or attempt == max_retries:
                raise
            delay = min(base_delay * (2 ** attempt), 60.0)
            logger.warning(
                "Polygon API error (attempt %d/%d): %s. Retrying in %.1fs",
                attempt + 1, max_retries, e, delay,
            )
            time.sleep(delay)
    return []  # unreachable, but satisfies type checker


# --- Function ----------------------------------------------------------------
def fetch_polygon_bars(
    symbol: str,
    start: str,
    end: str,
    api_key: Optional[str] = None,
    multiplier: int = 1,
    timespan: str = "minute",
    outdir: 'str | Path' = "data",
    fname: Optional[str] = None,
) -> Path:
    """
    Fetch historical bars from Polygon.io and save to parquet.
    Returns path to saved parquet file.
    """
    api_key = api_key or os.getenv("POLYGON_KEY")
    if not api_key:
        raise ValueError("No API key. Pass api_key or set POLYGON_KEY env variable.")

    ticker = _fx_symbol_to_polygon(symbol)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    client = RESTClient(api_key)
    bars = _fetch_aggs_with_retry(
        client,
        ticker=ticker,
        multiplier=multiplier,
        timespan=timespan,
        from_=start,
        to=end,
        limit=50_000,
        adjusted=True,
        sort="asc",
    )

    df = _bars_to_df(bars)
    if df.empty:
        raise ValueError(f"No data returned for {ticker} between {start} and {end}")

    if fname:
        outpath = outdir / fname
    else:
        base = symbol.lower().replace(":", "")
        outpath = outdir / f"{base}_{multiplier}{timespan}_{start}_{end}.parquet"

    df.to_parquet(outpath)
    logger.info("Saved %s rows -> %s", f"{len(df):,}", outpath)
    return outpath

def fetch_polygon_bars_chunked(
    symbol: str,
    start: str,
    end: str,
    api_key: str,
    multiplier: int = 1,
    timespan: str = "minute",
    outpath: str = "data/usdjpy_1min.parquet",
    chunk_days: int = 30,
    rate_limit: int = 5,
) -> Path:
    """
    Download [start, end] in chunks and save one merged parquet.
    Returns Path to outpath.
    """
    # normalize ticker for FX
    if not symbol.upper().startswith(("C:", "X:")):
        ticker = f"C:{symbol.upper()}"
    else:
        ticker = symbol.upper()

    client = RESTClient(api_key)
    s, e = _to_dates(start), _to_dates(end)
    pause = _adaptive_pause(rate_limit=rate_limit)

    dfs = []
    for cstart, cend in _drange(s, e, chunk_days=chunk_days):
        logger.info("Fetching %s %s %s from %s to %s ...", ticker, timespan, multiplier, cstart, cend)
        rows_data = _fetch_aggs_with_retry(
            client,
            ticker=ticker,
            multiplier=multiplier,
            timespan=timespan,
            from_=str(cstart),
            to=str(cend),
            limit=50_000,
            adjusted=True,
            sort="asc",
        )
        rows = []
        for b in rows_data:
            rows.append({
                "datetime": pd.to_datetime(b.timestamp, unit="ms", utc=True),
                "open": b.open, "high": b.high, "low": b.low, "close": b.close,
                "volume": b.volume,
            })
        if rows:
            df = pd.DataFrame(rows).set_index("datetime").sort_index()
            dfs.append(df)

        # Adaptive rate-limited pause
        time.sleep(pause)

    if not dfs:
        raise ValueError("No data returned across all chunks.")

    full = pd.concat(dfs).sort_index()
    # drop duplicates in case of any overlap
    full = full[~full.index.duplicated(keep="first")]

    out = Path(outpath)
    out.parent.mkdir(parents=True, exist_ok=True)
    full.to_parquet(out)
    logger.info("Saved %s rows -> %s", f"{len(full):,}", out)
    return out
