"""
Minimal buy/hold/exit loop for connection testing.
Buys, holds for the configured duration, exits, then repeats.
"""
from __future__ import annotations

import asyncio

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import (
    OrderCanceled,
    OrderDenied,
    OrderExpired,
    OrderFilled,
    OrderRejected,
    PositionClosed,
)
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy

from trader.strategy.live_helpers import LiveExecutionMixin, resolve_trade_quantity


class OneMinuteBuyHoldConfig(StrategyConfig, frozen=True):
    instrument_id: str
    bar_type: str
    trade_size: float = 1.0
    hold_seconds: int = 60
    time_in_force: str = "IOC"
    exec_client_id: str | None = None


class OneMinuteBuyHoldStrategy(LiveExecutionMixin, Strategy):
    def __init__(self, config: OneMinuteBuyHoldConfig) -> None:
        super().__init__(config)
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.bar_type = BarType.from_str(config.bar_type)
        self.hold_seconds = config.hold_seconds
        self.trade_size = config.trade_size
        self.trade_qty = config.trade_size  # rescaled once instrument is loaded
        self._configure_live_execution(
            exec_client_id=config.exec_client_id,
            time_in_force=config.time_in_force,
            default_tif=TimeInForce.IOC,
        )
        self._entry_ts_ns: int | None = None
        self._entered = False
        self._entry_order_id = None
        self._exit_order_id = None
        self._exit_task: asyncio.Task | None = None

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        if self.instrument is None:
            self.log.error(f"Instrument {self.instrument_id} not found in cache")
            return
        self.trade_qty = resolve_trade_quantity(
            instrument=self.instrument,
            configured_trade_size=self.trade_size,
        )
        self.subscribe_bars(self.bar_type)

    def on_bar(self, bar: Bar) -> None:
        if self._entry_ts_ns is None and self._entry_order_id is None and self._exit_order_id is None:
            qty = Quantity(abs(self.trade_qty), self.instrument.size_precision)
            order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.BUY,
                quantity=qty,
                time_in_force=getattr(self, "time_in_force", TimeInForce.IOC),
            )
            self._entry_order_id = order.client_order_id
            OneMinuteBuyHoldStrategy._submit_order(self, order)
            return

        if (
            self._entered
            and self._entry_ts_ns is not None
            and bar.ts_event - self._entry_ts_ns >= self.hold_seconds * 1_000_000_000
            and self._exit_order_id is None
        ):
            self._close_position("TIME-EXIT")

    def on_order_filled(self, event: OrderFilled) -> None:
        if self._entry_order_id is not None and event.client_order_id == self._entry_order_id:
            self._entry_order_id = None
            self._entry_ts_ns = event.ts_event
            self._entered = True
            self._schedule_time_exit()
            self.log.info(
                f"BUY-HOLD ENTRY FILLED {event.instrument_id} qty={event.last_qty} px={event.last_px}"
            )
            return

        if self._exit_order_id is not None and event.client_order_id == self._exit_order_id:
            self._exit_order_id = None
            self.log.info(
                f"BUY-HOLD EXIT ORDER FILLED {event.instrument_id} qty={event.last_qty} px={event.last_px}"
            )

    def on_order_rejected(self, event: OrderRejected) -> None:
        if self._entry_order_id is not None and event.client_order_id == self._entry_order_id:
            OneMinuteBuyHoldStrategy._reset_entry_state(self)
            reason = getattr(event, "reason", "no reason provided")
            self.log.warning(f"BUY-HOLD ENTRY REJECTED {reason}")
            return

        if self._exit_order_id is not None and event.client_order_id == self._exit_order_id:
            self._exit_order_id = None
            reason = getattr(event, "reason", "no reason provided")
            self.log.warning(f"BUY-HOLD EXIT REJECTED {reason}")

    def on_order_denied(self, event: OrderDenied) -> None:
        if self._entry_order_id is not None and event.client_order_id == self._entry_order_id:
            OneMinuteBuyHoldStrategy._reset_entry_state(self)
            reason = getattr(event, "reason", "no reason provided")
            self.log.warning(f"BUY-HOLD ENTRY DENIED {reason}")
            return

        if self._exit_order_id is not None and event.client_order_id == self._exit_order_id:
            self._exit_order_id = None
            reason = getattr(event, "reason", "no reason provided")
            self.log.warning(f"BUY-HOLD EXIT DENIED {reason}")

    def on_order_canceled(self, event: OrderCanceled) -> None:
        if self._entry_order_id is not None and event.client_order_id == self._entry_order_id:
            OneMinuteBuyHoldStrategy._reset_entry_state(self)
            self.log.warning(
                f"BUY-HOLD ENTRY CANCELED {event.instrument_id} client_order_id={event.client_order_id}"
            )
            return

        if self._exit_order_id is not None and event.client_order_id == self._exit_order_id:
            self._exit_order_id = None
            self.log.warning(
                f"BUY-HOLD EXIT CANCELED {event.instrument_id} client_order_id={event.client_order_id}"
            )

    def on_order_expired(self, event: OrderExpired) -> None:
        if self._entry_order_id is not None and event.client_order_id == self._entry_order_id:
            OneMinuteBuyHoldStrategy._reset_entry_state(self)
            self.log.warning(
                f"BUY-HOLD ENTRY EXPIRED {event.instrument_id} client_order_id={event.client_order_id}"
            )
            return

        if self._exit_order_id is not None and event.client_order_id == self._exit_order_id:
            self._exit_order_id = None
            self.log.warning(
                f"BUY-HOLD EXIT EXPIRED {event.instrument_id} client_order_id={event.client_order_id}"
            )

    def on_position_closed(self, event: PositionClosed) -> None:
        self._cancel_exit_task()
        self._entry_ts_ns = None
        self._entered = False
        self._entry_order_id = None
        self._exit_order_id = None
        self.log.info(
            f"BUY-HOLD EXIT {event.instrument_id} realized_pnl={event.realized_pnl}"
        )

    def on_stop(self) -> None:
        self._cancel_exit_task()
        self._close_position("STOP")
        self.unsubscribe_bars(self.bar_type)
        self._entry_ts_ns = None
        self._entered = False
        self._entry_order_id = None
        self._exit_order_id = None

    def on_reset(self) -> None:
        self._cancel_exit_task()
        self._entry_ts_ns = None
        self._entered = False
        self._entry_order_id = None
        self._exit_order_id = None

    def _close_position(self, tag: str) -> None:
        for pos in self._iter_open_strategy_positions():
            side = OrderSide.SELL if pos.is_long else OrderSide.BUY
            order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=side,
                quantity=Quantity(abs(pos.quantity), self.instrument.size_precision),
                time_in_force=getattr(self, "time_in_force", TimeInForce.IOC),
            )
            self._exit_order_id = order.client_order_id
            OneMinuteBuyHoldStrategy._submit_order(self, order, position_id=pos.id)
            self.log.info(f"{tag} {self.instrument_id} qty={pos.quantity}")
            return

    def _schedule_time_exit(self) -> None:
        if self.hold_seconds <= 0:
            self._close_position("TIME-EXIT")
            return
        if self._exit_task is not None and not self._exit_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._exit_task = loop.create_task(self._exit_after_hold())

    async def _exit_after_hold(self) -> None:
        try:
            await asyncio.sleep(self.hold_seconds)
            if self.is_running and self._entered and self._exit_order_id is None:
                self._close_position("TIME-EXIT")
        except asyncio.CancelledError:
            return

    def _cancel_exit_task(self) -> None:
        if self._exit_task is not None and not self._exit_task.done():
            self._exit_task.cancel()
        self._exit_task = None

    def _reset_entry_state(self) -> None:
        self._entry_order_id = None
        self._entry_ts_ns = None
        self._entered = False
        self._cancel_exit_task()
