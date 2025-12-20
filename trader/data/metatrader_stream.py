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
from trader.exec.metatrader import MetaTraderBroker


@dataclass
class MetaTraderLiveStreamer:
    """
    Polls MetaTrader 5 ticks for the given symbols, aggregates them into bars, and
    forwards completed bars into a DataStreamer. Shares a broker session with the order router.
    """

    broker: MetaTraderBroker
    streamer: DataStreamer
    bar_seconds: int = 60
    poll_interval: float = 1.0
    max_batch: int = 500
    lookback_sec: int = 5
    shutdown_broker_on_close: bool = False

    _stopped: bool = field(init=False, default=False, repr=False)

    def stop(self) -> None:
        self._stopped = True

    def _mt5(self):
        return self.broker.mt5

    def _select_symbols(self, symbols: Iterable[str]) -> None:
        mt5 = self._mt5()
        for sym in symbols:
            if not mt5.symbol_select(sym, True):
                code, msg = mt5.last_error()
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
        self.broker.ensure_connected()

        symbols = list(dict.fromkeys(symbols))  # de-dup while preserving order
        self._select_symbols(symbols)
        mt5 = self._mt5()

        builder = BarBuilder(bar_seconds=self.bar_seconds)
        last_seen_ms = {sym: 0 for sym in symbols}
        from_times = {
            sym: datetime.now(timezone.utc) - timedelta(seconds=self.lookback_sec) for sym in symbols
        }

        try:
            while not self._stopped:
                for sym in symbols:
                    frm = from_times[sym].replace(tzinfo=None)
                    ticks = mt5.copy_ticks_from(sym, frm, self.max_batch, mt5.COPY_TICKS_ALL)
                    if ticks is None:
                        code, msg = mt5.last_error()
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
            if self.shutdown_broker_on_close:
                try:
                    self.broker.shutdown()
                except Exception:
                    pass


async def stream_metatrader_ticks(
    symbols: Sequence[str],
    streamer: DataStreamer,
    *,
    broker: MetaTraderBroker | None = None,
    login: int | None = None,
    password: str | None = None,
    server: str | None = None,
    path: str | None = None,
    bar_seconds: int = 60,
    poll_interval: float = 1.0,
    max_batch: int = 500,
    lookback_sec: int = 5,
    shutdown_broker_on_close: bool | None = None,
) -> None:
    """
    Convenience entrypoint to start streaming MetaTrader 5 ticks as bars.
    If no broker is supplied, one will be created (and optionally shut down on exit).
    """
    brk = broker or MetaTraderBroker(
        login=login,
        password=password,
        server=server,
        path=path,
    )
    shutdown_flag = shutdown_broker_on_close if shutdown_broker_on_close is not None else broker is None

    mt_streamer = MetaTraderLiveStreamer(
        broker=brk,
        streamer=streamer,
        bar_seconds=bar_seconds,
        poll_interval=poll_interval,
        max_batch=max_batch,
        lookback_sec=lookback_sec,
        shutdown_broker_on_close=shutdown_flag,
    )
    await mt_streamer.stream_ticks_to_bars(symbols)
