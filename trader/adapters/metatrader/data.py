"""
MetaTrader 5 live data client for NautilusTrader.

Polls ticks via MT5 copy_ticks_from, aggregates into bars via BarBuilder,
and publishes NautilusTrader Bar objects to the message bus.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from nautilus_trader.data.messages import SubscribeBars, UnsubscribeBars
from nautilus_trader.config import LiveDataClientConfig
from nautilus_trader.live.data_client import LiveMarketDataClient
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import ClientId, Venue
from nautilus_trader.model.objects import Price, Quantity

from trader.adapters.metatrader.common import MetaTrader5Config, MetaTrader5Connection
from trader.adapters.metatrader.provider import MetaTrader5InstrumentProvider
from trader.core.constants import MT5
from trader.core.events import Tick
from trader.data.bar_builder import BarBuilder


class MetaTrader5DataClientConfig(LiveDataClientConfig, frozen=True):
    mt5_login: int | None = None
    mt5_password: str | None = None
    mt5_server: str | None = None
    mt5_path: str | None = None
    bar_seconds: int = 60
    poll_interval: float = 1.0
    max_batch: int = 5000
    lookback_sec: int = 5


class MetaTrader5DataClient(LiveMarketDataClient):
    """
    Polls MetaTrader 5 ticks for subscribed symbols, aggregates into bars,
    and publishes them to the NautilusTrader message bus.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        client_id: ClientId,
        venue: Venue,
        msgbus: Any,
        cache: Any,
        clock: Any,
        config: MetaTrader5DataClientConfig,
        connection: MetaTrader5Connection | None = None,
    ):
        mt5_config = MetaTrader5Config(
            login=config.mt5_login,
            password=config.mt5_password,
            server=config.mt5_server,
            path=config.mt5_path,
        )
        self._connection = connection or MetaTrader5Connection(mt5_config)
        instrument_provider = MetaTrader5InstrumentProvider(
            connection=self._connection,
            venue=venue,
        )
        super().__init__(
            loop=loop,
            client_id=client_id,
            venue=venue,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=instrument_provider,
        )
        self._bar_seconds = config.bar_seconds
        self._poll_interval = config.poll_interval
        self._max_batch = config.max_batch
        self._lookback_sec = config.lookback_sec
        self._bar_builder = BarBuilder(bar_seconds=self._bar_seconds)
        self._poll_tasks: dict[str, asyncio.Task] = {}
        self._subscribed_bar_types: dict[str, BarType] = {}

    @property
    def connection(self) -> MetaTrader5Connection:
        return self._connection

    async def _connect(self) -> None:
        self._connection.connect()
        self._log.info("MetaTrader5 data client connected")

    async def _disconnect(self) -> None:
        for task in self._poll_tasks.values():
            task.cancel()
        self._poll_tasks.clear()
        self._connection.shutdown()
        self._log.info("MetaTrader5 data client disconnected")

    async def _subscribe_bars(self, command: SubscribeBars) -> None:
        bar_type = command.bar_type
        symbol = bar_type.instrument_id.symbol.value
        if symbol in self._poll_tasks:
            return

        mt5 = self._connection.mt5
        if not mt5.symbol_select(symbol, True):
            code, msg = mt5.last_error()
            self._log.error(f"Failed to select symbol {symbol}: [{code}] {msg}")
            return

        self._subscribed_bar_types[symbol] = bar_type
        task = self._loop.create_task(self._poll_ticks(symbol, bar_type))
        self._poll_tasks[symbol] = task
        self._log.info(f"Subscribed to bars for {symbol}")

    async def _unsubscribe_bars(self, command: UnsubscribeBars) -> None:
        bar_type = command.bar_type
        symbol = bar_type.instrument_id.symbol.value
        task = self._poll_tasks.pop(symbol, None)
        if task:
            task.cancel()
        self._subscribed_bar_types.pop(symbol, None)
        self._log.info(f"Unsubscribed from bars for {symbol}")

    async def _poll_ticks(self, symbol: str, bar_type: BarType) -> None:
        """
        Main polling loop. Queries ticks anchored to last_seen_ms to avoid
        missing data under lag, and processes all ticks from the first poll
        onwards (no priming waste).
        """
        mt5 = self._connection.mt5
        last_seen_ms = 0

        try:
            while True:
                # Anchor query to last_seen_ms with a small safety margin,
                # falling back to lookback window on first poll.
                if last_seen_ms > 0:
                    query_from = datetime.fromtimestamp(
                        (last_seen_ms - 500) / 1000.0, tz=timezone.utc
                    )
                else:
                    query_from = datetime.now(timezone.utc) - timedelta(seconds=self._lookback_sec)

                ticks = mt5.copy_ticks_from(symbol, query_from, self._max_batch, mt5.COPY_TICKS_ALL)

                if ticks is None:
                    code, msg = mt5.last_error()
                    self._log.error(f"copy_ticks_from failed for {symbol}: [{code}] {msg}")
                    await asyncio.sleep(self._poll_interval)
                    continue

                if len(ticks) > 0:
                    has_time_msc = "time_msc" in ticks.dtype.names
                    has_volume_real = "volume_real" in ticks.dtype.names
                    has_bid = "bid" in ticks.dtype.names
                    has_ask = "ask" in ticks.dtype.names
                    has_last = "last" in ticks.dtype.names

                    if len(ticks) >= self._max_batch:
                        self._log.warning(
                            "Hit max_batch (%d) for %s — ticks may have been dropped",
                            self._max_batch, symbol,
                        )

                    for tick in ticks:
                        ts_ms = int(tick["time_msc"]) if has_time_msc else int(float(tick["time"]) * 1000)
                        if ts_ms <= last_seen_ms:
                            continue

                        last_seen_ms = ts_ms
                        ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
                        vol = float(tick["volume_real"] if has_volume_real else tick["volume"])

                        tick_obj = Tick(
                            ts=ts,
                            symbol=symbol,
                            bid=float(tick["bid"]) if has_bid else None,
                            ask=float(tick["ask"]) if has_ask else None,
                            last=float(tick["last"]) if has_last else None,
                            size=vol,
                            venue="MT5",
                        )

                        completed = self._bar_builder.on_tick(tick_obj)
                        for bar_evt in completed:
                            self._publish_bar(bar_evt, bar_type)

                await asyncio.sleep(self._poll_interval)

        except asyncio.CancelledError:
            # Flush remaining bars on shutdown
            for bar_evt in self._bar_builder.flush(force=True):
                self._publish_bar(bar_evt, bar_type)

    def _publish_bar(self, bar_evt: Any, bar_type: BarType) -> None:
        """Convert internal Bar event to NautilusTrader Bar and publish."""
        ts_ns = int(bar_evt.ts.timestamp() * 1_000_000_000)
        nautilus_bar = Bar(
            bar_type=bar_type,
            open=Price.from_str(f"{bar_evt.open:.10f}".rstrip("0").rstrip(".")),
            high=Price.from_str(f"{bar_evt.high:.10f}".rstrip("0").rstrip(".")),
            low=Price.from_str(f"{bar_evt.low:.10f}".rstrip("0").rstrip(".")),
            close=Price.from_str(f"{bar_evt.close:.10f}".rstrip("0").rstrip(".")),
            volume=Quantity.from_str(f"{bar_evt.volume:.6f}".rstrip("0").rstrip(".")),
            ts_event=ts_ns,
            ts_init=ts_ns,
        )
        self._handle_data(nautilus_bar)
