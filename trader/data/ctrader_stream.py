"""
cTrader streaming adapter: bridge a quote async-iterator into DataStreamer via BarBuilder.
You must supply a client that yields tick dicts: {symbol, bid, ask, ts, size?}.
"""
from __future__ import annotations

from typing import AsyncIterator, Callable, Iterable, Optional

from trader.core.events import Tick
from trader.data.bar_builder import BarBuilder
from trader.data.pipeline import DataStreamer


async def pump_ticks_to_bars(
    tick_stream: AsyncIterator[dict],
    streamer: DataStreamer,
    *,
    bar_seconds: int = 60,
) -> None:
    """
    Consume ticks and emit completed bars to DataStreamer.
    """
    builder = BarBuilder(bar_seconds=bar_seconds)
    async for t in tick_stream:
        tick = Tick(
            ts=t["ts"],
            symbol=t["symbol"],
            bid=t.get("bid"),
            ask=t.get("ask"),
            last=t.get("last"),
            size=t.get("size"),
            venue=t.get("venue"),
        )
        completed = builder.on_tick(tick)
        for bar in completed:
            streamer.push_bar(
                {
                    "datetime": bar.ts,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
            )
    # flush remaining bars
    for bar in builder.flush(force=True):
        streamer.push_bar(
            {
                "datetime": bar.ts,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
        )
    streamer.close()


async def stream_ctrader_quotes(
    quote_source: Callable[[Iterable[str]], AsyncIterator[dict]],
    symbols: Iterable[str],
    streamer: DataStreamer,
    *,
    bar_seconds: int = 60,
):
    """
    High-level entry: pass a quote_source (your cTrader client) and symbols; bars are pushed to DataStreamer.
    """
    tick_stream = quote_source(symbols)
    await pump_ticks_to_bars(tick_stream, streamer, bar_seconds=bar_seconds)


__all__ = ["pump_ticks_to_bars", "stream_ctrader_quotes"]
