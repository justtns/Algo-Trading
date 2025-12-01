"""
Placeholder for cTrader streaming adapter.
Hook up your cTrader OpenAPI client here and push quotes into DataStreamer.
"""
from __future__ import annotations

from typing import AsyncIterator

# TODO: integrate actual cTrader client


async def stream_quotes(symbols: list[str]) -> AsyncIterator[dict]:
    """
    Async generator yielding quote dicts: {symbol, bid, ask, ts}
    Replace with real cTrader streaming logic.
    """
    if False:
        yield {}
