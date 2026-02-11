from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd
import yaml

logger = logging.getLogger(__name__)


def _get_polygon_rest_client_class():
    """
    Resolve Polygon REST client across package variants/versions.

    Supports:
    - polygon-api-client modern: `from polygon import RESTClient`
    - polygon-api-client older:  `from polygon.rest import RESTClient`
    """
    try:
        from polygon import RESTClient as client_cls  # type: ignore

        return client_cls
    except Exception:
        try:
            from polygon.rest import RESTClient as client_cls  # type: ignore

            return client_cls
        except Exception as exc:
            raise ImportError(
                "Polygon REST client import failed. This usually means the wrong "
                "`polygon` package is installed. Install/repair with:\n"
                "  pip uninstall -y polygon\n"
                "  pip install -U polygon-api-client"
            ) from exc


def _make_polygon_client(api_key: str):
    return _get_polygon_rest_client_class()(api_key)


def _mapping_get_case_insensitive(mapping: dict, key: str):
    if key in mapping:
        return mapping[key]
    key_l = key.lower()
    for cur_key, cur_value in mapping.items():
        if isinstance(cur_key, str) and cur_key.lower() == key_l:
            return cur_value
    return None


def _nested_get_case_insensitive(data: dict, path: tuple[str, ...]):
    cur = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = _mapping_get_case_insensitive(cur, key)
        if cur is None:
            return None
    return cur


def _load_polygon_key_from_yaml(yaml_path: str | Path) -> str | None:
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Polygon key YAML file not found: {path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        return None
    if isinstance(payload, str):
        candidate = payload.strip()
        return candidate or None
    if not isinstance(payload, dict):
        return None

    candidate_paths = (
        ("POLYGON_API_KEY",),
        ("POLYGON_KEY",),
        ("polygon_api_key",),
        ("polygon_key",),
        ("polygon",),
        ("polygon", "api_key"),
        ("polygon", "key"),
        ("api_keys", "polygon"),
        ("keys", "polygon"),
        ("credentials", "polygon", "api_key"),
        ("credentials", "polygon", "key"),
    )
    for candidate_path in candidate_paths:
        value = _nested_get_case_insensitive(payload, candidate_path)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _resolve_polygon_api_key(
    api_key: str | None,
    *,
    api_key_yaml: str | Path | None = None,
) -> str:
    key = api_key or os.getenv("POLYGON_API_KEY") or os.getenv("POLYGON_KEY")
    if not key and api_key_yaml is not None:
        key = _load_polygon_key_from_yaml(api_key_yaml)
    if not key:
        raise ValueError(
            "No Polygon API key. Pass api_key, pass api_key_yaml, or set "
            "POLYGON_API_KEY (or POLYGON_KEY)."
        )
    return key


def _normalize_polygon_ticker(symbol: str, market: str = "auto") -> str:
    raw = symbol.strip().upper()
    if not raw:
        raise ValueError("Ticker symbol cannot be empty.")
    if raw.startswith(("C:", "X:", "I:", "O:")):
        return raw

    compact = raw.replace("/", "").replace(".", "").replace(" ", "")
    market_norm = market.strip().lower()

    if market_norm in {"fx", "forex"}:
        if len(compact) != 6 or not compact.isalpha():
            raise ValueError(
                f"FX symbol must be a 6-letter pair (e.g. USDJPY). Got: '{symbol}'"
            )
        return f"C:{compact}"

    if market_norm in {"crypto", "cryptocurrency"}:
        if len(compact) < 6 or not compact.isalnum():
            raise ValueError(
                f"Crypto symbol should be base+quote (e.g. BTCUSD). Got: '{symbol}'"
            )
        return f"X:{compact}"

    if market_norm not in {"auto", "stock", "stocks", "equity", "equities"}:
        raise ValueError(
            "Unsupported market. Use one of: auto, stocks, fx, crypto."
        )

    if len(compact) == 6 and compact.isalpha():
        return f"C:{compact}"
    return raw


def _ticker_file_token(ticker: str) -> str:
    return (
        ticker.lower()
        .replace(":", "")
        .replace("/", "")
        .replace(".", "")
        .replace(" ", "")
    )


def _bars_to_df(bars: Iterable) -> pd.DataFrame:
    rows = []
    for bar in bars:
        rows.append(
            {
                "datetime": pd.to_datetime(bar.timestamp, unit="ms", utc=True),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
        )
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows).set_index("datetime").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def _to_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def _drange(start_d, end_d, chunk_days: int = 30):
    cur = start_d
    one = timedelta(days=1)
    step = timedelta(days=chunk_days)
    while cur <= end_d:
        chunk_end = min(cur + step - one, end_d)
        yield cur, chunk_end
        cur = chunk_end + one


def _adaptive_pause(rate_limit: int = 5, window_sec: float = 60.0) -> float:
    if rate_limit <= 0:
        return 0.0
    return window_sec / float(rate_limit)


def _fetch_aggs_with_retry(
    client: Any,
    max_retries: int = 5,
    base_delay: float = 2.0,
    **kwargs,
) -> list:
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
                attempt + 1,
                max_retries,
                e,
                delay,
            )
            time.sleep(delay)
    return []


def fetch_polygon_bars(
    symbol: str,
    start: str,
    end: str,
    api_key: Optional[str] = None,
    *,
    api_key_yaml: str | Path | None = None,
    market: str = "auto",
    multiplier: int = 1,
    timespan: str = "minute",
    outdir: str | Path = "data",
    fname: Optional[str] = None,
    max_retries: int = 5,
    base_delay: float = 2.0,
) -> Path:
    """
    Fetch historical bars from Polygon.io and save to parquet.

    Parameters
    ----------
    symbol
        Requested symbol/ticker (e.g. AAPL, USDJPY, BTCUSD, C:USDJPY, X:BTCUSD).
    start, end
        Date strings in YYYY-MM-DD format.
    market
        One of auto, stocks, fx, crypto. Used only when `symbol` has no Polygon prefix.
    """
    key = _resolve_polygon_api_key(api_key, api_key_yaml=api_key_yaml)
    ticker = _normalize_polygon_ticker(symbol, market=market)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    client = _make_polygon_client(key)
    bars = _fetch_aggs_with_retry(
        client,
        max_retries=max_retries,
        base_delay=base_delay,
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
        raise ValueError(f"No data returned for {ticker} between {start} and {end}.")

    if fname:
        outpath = outdir / fname
    else:
        token = _ticker_file_token(ticker)
        outpath = outdir / f"{token}_{multiplier}{timespan}_{start}_{end}.parquet"

    df.to_parquet(outpath)
    logger.info("Saved %s rows -> %s", f"{len(df):,}", outpath)
    return outpath


def fetch_polygon_bars_chunked(
    symbol: str,
    start: str,
    end: str,
    api_key: Optional[str] = None,
    *,
    api_key_yaml: str | Path | None = None,
    market: str = "auto",
    multiplier: int = 1,
    timespan: str = "minute",
    outpath: str | Path | None = None,
    outdir: str | Path = "data",
    fname: Optional[str] = None,
    chunk_days: int = 30,
    rate_limit: int = 5,
    max_retries: int = 5,
    base_delay: float = 2.0,
) -> Path:
    """
    Download [start, end] in chunks and save one merged parquet file.
    """
    key = _resolve_polygon_api_key(api_key, api_key_yaml=api_key_yaml)
    ticker = _normalize_polygon_ticker(symbol, market=market)
    client = _make_polygon_client(key)
    start_d, end_d = _to_date(start), _to_date(end)
    pause = _adaptive_pause(rate_limit=rate_limit)

    dfs = []
    for cstart, cend in _drange(start_d, end_d, chunk_days=chunk_days):
        logger.info(
            "Fetching %s %s %s from %s to %s ...",
            ticker,
            timespan,
            multiplier,
            cstart,
            cend,
        )
        bars = _fetch_aggs_with_retry(
            client,
            max_retries=max_retries,
            base_delay=base_delay,
            ticker=ticker,
            multiplier=multiplier,
            timespan=timespan,
            from_=str(cstart),
            to=str(cend),
            limit=50_000,
            adjusted=True,
            sort="asc",
        )
        chunk_df = _bars_to_df(bars)
        if not chunk_df.empty:
            dfs.append(chunk_df)

        if pause > 0 and cend < end_d:
            time.sleep(pause)

    if not dfs:
        raise ValueError(f"No data returned for {ticker} between {start} and {end}.")

    full = pd.concat(dfs).sort_index()
    full = full[~full.index.duplicated(keep="first")]

    if outpath is not None:
        out = Path(outpath)
    else:
        outdir_path = Path(outdir)
        token = _ticker_file_token(ticker)
        out = outdir_path / (
            fname or f"{token}_{multiplier}{timespan}_{start}_{end}.parquet"
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    full.to_parquet(out)
    logger.info("Saved %s rows -> %s", f"{len(full):,}", out)
    return out
