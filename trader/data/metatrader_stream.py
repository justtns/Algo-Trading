"""
MetaTrader 5 streaming adapter: poll ticks, build bars, and push into DataStreamer.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

from trader.core.events import Tick
from trader.data.bar_builder import BarBuilder
from trader.data.pipeline import DataStreamer

import MetaTrader5 as mt5

@dataclass
class MetaTraderLiveStreamer:
    """
    Polls MetaTrader 5 ticks for the given symbols, aggregates them into bars, and
    forwards completed bars into a DataStreamer.
    """

    streamer: DataStreamer
    login: int | None = None
    password: str | None = None
    server: str | None = None
    path: str | None = None
    bar_seconds: int = 60
    poll_interval: float = 1.0
    max_batch: int = 500
    lookback_sec: int = 5

    _mt5: Any = field(init=False, default=None, repr=False)
    _stopped: bool = field(init=False, default=False, repr=False)

    def connect(self) -> MetaTraderLiveStreamer:
        initialized = mt5.initialize( # type: ignore
            path=self.path,
            login=self.login,
            password=self.password,
            server=self.server,
        )
        if not initialized:
            code, msg = mt5.last_error() # type: ignore
            raise RuntimeError(f"MetaTrader5 initialize failed: [{code}] {msg}")

        self._mt5 = mt5
        return self

    def stop(self) -> None:
        self._stopped = True

    def _shutdown(self) -> None:
        if self._mt5:
            try:
                self._mt5.shutdown()
            except Exception:
                pass
        self._mt5 = None

    def _select_symbols(self, symbols: Iterable[str]) -> None:
        assert self._mt5 is not None
        for sym in symbols:
            if not self._mt5.symbol_select(sym, True):
                code, msg = self._mt5.last_error()
                raise RuntimeError(f"Failed to select symbol {sym}: [{code}] {msg}")

    @staticmethod
    def _to_timestamp_ms(tick: Any, has_time_msc: bool) -> int:
        return int(tick["time_msc"]) if has_time_msc else int(float(tick["time"]) * 1000)

    @staticmethod
    def _tick_volume(tick: Any, has_volume_real: bool) -> float:
        return float(tick["volume_real"] if has_volume_real else tick["volume"])

    async def stream_ticks_to_bars(self, symbols: Sequence[str]) -> None:
        """
        Start polling ticks for `symbols` and emitting completed bars to the DataStreamer.
        """
        if self._mt5 is None:
            self.connect()

        symbols = list(dict.fromkeys(symbols))  # de-dup while preserving order
        self._select_symbols(symbols)

        builder = BarBuilder(bar_seconds=self.bar_seconds)
        last_seen_ms = {sym: 0 for sym in symbols}
        from_times = {
            sym: datetime.now(timezone.utc) - timedelta(seconds=self.lookback_sec) for sym in symbols
        }

        try:
            while not self._stopped:
                for sym in symbols:
                    frm = from_times[sym].replace(tzinfo=None)
                    ticks = self._mt5.copy_ticks_from(sym, frm, self.max_batch, self._mt5.COPY_TICKS_ALL)
                    if ticks is None:
                        code, msg = self._mt5.last_error()
                        raise RuntimeError(f"copy_ticks_from failed for {sym}: [{code}] {msg}")
                    if len(ticks) == 0:
                        continue

                    has_time_msc = "time_msc" in ticks.dtype.names
                    has_volume_real = "volume_real" in ticks.dtype.names
                    has_bid = "bid" in ticks.dtype.names
                    has_ask = "ask" in ticks.dtype.names
                    has_last = "last" in ticks.dtype.names

                    for tick in ticks:
                        ts_ms = self._to_timestamp_ms(tick, has_time_msc)
                        if ts_ms <= last_seen_ms[sym]:
                            continue

                        last_seen_ms[sym] = ts_ms
                        ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
                        tick_obj = Tick(
                            ts=ts,
                            symbol=sym,
                            bid=float(tick["bid"]) if has_bid else None,
                            ask=float(tick["ask"]) if has_ask else None,
                            last=float(tick["last"]) if has_last else None,
                            size=self._tick_volume(tick, has_volume_real),
                            venue="MT5",
                        )
                        completed = builder.on_tick(tick_obj)
                        for bar in completed:
                            self.streamer.push_bar(
                                {
                                    "datetime": bar.ts,
                                    "open": bar.open,
                                    "high": bar.high,
                                    "low": bar.low,
                                    "close": bar.close,
                                    "volume": bar.volume,
                                }
                            )

                    if last_seen_ms[sym]:
                        from_times[sym] = datetime.fromtimestamp(last_seen_ms[sym] / 1000.0, tz=timezone.utc)

                await asyncio.sleep(self.poll_interval)
        finally:
            for bar in builder.flush(force=True):
                self.streamer.push_bar(
                    {
                        "datetime": bar.ts,
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                    }
                )
            self.streamer.close()
            self._shutdown()


async def stream_metatrader_ticks(
    symbols: Sequence[str],
    streamer: DataStreamer,
    *,
    login: int | None = None,
    password: str | None = None,
    server: str | None = None,
    path: str | None = None,
    bar_seconds: int = 60,
    poll_interval: float = 1.0,
    max_batch: int = 500,
    lookback_sec: int = 5,
) -> None:
    """
    Convenience entrypoint to start streaming MetaTrader 5 ticks as bars.
    """
    mt_streamer = MetaTraderLiveStreamer(
        streamer,
        login=login,
        password=password,
        server=server,
        path=path,
        bar_seconds=bar_seconds,
        poll_interval=poll_interval,
        max_batch=max_batch,
        lookback_sec=lookback_sec,
    )
    await mt_streamer.stream_ticks_to_bars(symbols)
