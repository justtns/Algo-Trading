"""
NautilusTrader Gotobi strategies for Japanese FX settlement day trading.

GotobiStrategy: enters at entry_time on gotobi days, exits at exit_time.
GotobiWithSLStrategy: same as above with stop-loss order placed after entry fill.
"""
from __future__ import annotations

from datetime import date, time, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.datetime import unix_nanos_to_dt
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import OrderFilled, PositionChanged, PositionClosed
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from trader.strategy.common import GotobiCalendar


class GotobiConfig(StrategyConfig, frozen=True):
    instrument_id: str
    bar_type: str
    entry_time: str = "01:30:00"
    exit_time: str = "08:30:00"
    trade_size: float = 1.0
    contract_size: float = 100_000
    gotobi_days: tuple = (5, 10, 15, 20, 25, 30)
    use_holidays: bool = True
    trading_timezone: str = "Asia/Tokyo"


class GotobiStrategy(Strategy):
    """
    Enters a position on gotobi settlement days at a configured time and exits
    at a later time the same day. Gotobi days are the 5th, 10th, 15th, 20th,
    25th, and 30th of each month (with weekend/holiday rollback).
    """

    def __init__(self, config: GotobiConfig) -> None:
        super().__init__(config)
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.bar_type = BarType.from_str(config.bar_type)

        h, m, s = map(int, config.entry_time.split(":"))
        self.t_entry = time(h, m, s)
        h, m, s = map(int, config.exit_time.split(":"))
        self.t_exit = time(h, m, s)

        self.trade_qty = config.trade_size * config.contract_size
        self.trading_tz = ZoneInfo(config.trading_timezone)
        self.calendar = GotobiCalendar(
            gotobi_days=set(config.gotobi_days),
            use_holidays=config.use_holidays,
        )

        self.current_day: date | None = None
        self.is_trade_day = False
        self.entered_today = False

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        if self.instrument is None:
            self.log.error(f"Instrument {self.instrument_id} not found in cache")
            return
        self.subscribe_bars(self.bar_type)

    def on_bar(self, bar: Bar) -> None:
        dt = _bar_datetime_in_tz(bar.ts_event, self.trading_tz)
        now_d = dt.date()
        now_t = dt.time()

        if self.current_day is None or now_d != self.current_day:
            self.current_day = now_d
            self.is_trade_day = self.calendar.is_gotobi_trading_date(now_d)
            self.entered_today = False

        # Not a gotobi trading date — only ensure flat at exit
        if not self.is_trade_day:
            if now_t >= self.t_exit:
                self._close_position("DEFENSIVE-EXIT")
            return

        # Entry at entry_time (only once)
        if not self.entered_today and now_t >= self.t_entry and now_t < self.t_exit:
            side = OrderSide.BUY if self.trade_qty > 0 else OrderSide.SELL
            qty = Quantity(abs(self.trade_qty), self.instrument.size_precision)
            order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=side,
                quantity=qty,
                time_in_force=TimeInForce.FOK,
            )
            self.submit_order(order)
            self.entered_today = True

        # Exit at exit_time
        if self.entered_today and now_t >= self.t_exit:
            self._close_position("TIME-EXIT")

    def _close_position(self, tag: str) -> None:
        for position in self.cache.positions(venue=self.instrument_id.venue):
            if (
                position.instrument_id == self.instrument_id
                and not position.is_closed
                and position.strategy_id == self.id
            ):
                side = OrderSide.SELL if position.is_long else OrderSide.BUY
                order = self.order_factory.market(
                    instrument_id=self.instrument_id,
                    order_side=side,
                    quantity=Quantity(abs(position.quantity), self.instrument.size_precision),
                    time_in_force=TimeInForce.FOK,
                )
                self.submit_order(order, position_id=position.id)
                self.log.info(f"{tag} {self.instrument_id} qty={position.quantity}")

    def on_order_filled(self, event: OrderFilled) -> None:
        self.log.info(
            f"ORDER FILLED {event.order_side.name} {event.instrument_id} "
            f"qty={event.last_qty} px={event.last_px}"
        )

    def on_position_closed(self, event: PositionClosed) -> None:
        self.log.info(
            f"TRADE CLOSED {event.instrument_id} "
            f"realized_pnl={event.realized_pnl}"
        )

    def on_stop(self) -> None:
        self.unsubscribe_bars(self.bar_type)

    def on_reset(self) -> None:
        self.current_day = None
        self.is_trade_day = False
        self.entered_today = False


class GotobiWithSLConfig(GotobiConfig, frozen=True):
    stop_loss_pct: float | None = None


class GotobiWithSLStrategy(Strategy):
    """
    Gotobi strategy with stop-loss protection. After entry, a stop-market order
    is placed. At exit time, the stop is cancelled and position is closed.
    """

    def __init__(self, config: GotobiWithSLConfig) -> None:
        super().__init__(config)
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.bar_type = BarType.from_str(config.bar_type)

        h, m, s = map(int, config.entry_time.split(":"))
        self.t_entry = time(h, m, s)
        h, m, s = map(int, config.exit_time.split(":"))
        self.t_exit = time(h, m, s)

        self.trade_qty = config.trade_size * config.contract_size
        self.stop_loss_pct = config.stop_loss_pct
        self.trading_tz = ZoneInfo(config.trading_timezone)
        self.calendar = GotobiCalendar(
            gotobi_days=set(config.gotobi_days),
            use_holidays=config.use_holidays,
        )

        self.current_day: date | None = None
        self.is_trade_day = False
        self.entered_today = False
        self._entry_order_id = None
        self._stop_order_id = None
        self._stop_filled = False
        self._stop_fill_px = None

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        if self.instrument is None:
            self.log.error(f"Instrument {self.instrument_id} not found in cache")
            return
        self.subscribe_bars(self.bar_type)

    def on_bar(self, bar: Bar) -> None:
        dt = _bar_datetime_in_tz(bar.ts_event, self.trading_tz)
        now_d = dt.date()
        now_t = dt.time()

        if self.current_day is None or now_d != self.current_day:
            self.current_day = now_d
            self.is_trade_day = self.calendar.is_gotobi_trading_date(now_d)
            self.entered_today = False
            self._entry_order_id = None
            self._stop_order_id = None

        if not self.is_trade_day:
            if now_t >= self.t_exit:
                self._cancel_stop()
                self._close_position("DEFENSIVE-EXIT")
            return

        # Entry
        if (
            not self.entered_today
            and now_t >= self.t_entry
            and now_t < self.t_exit
            and self._entry_order_id is None
        ):
            side = OrderSide.BUY if self.trade_qty > 0 else OrderSide.SELL
            qty = Quantity(abs(self.trade_qty), self.instrument.size_precision)
            order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=side,
                quantity=qty,
                time_in_force=TimeInForce.FOK,
            )
            self._entry_order_id = order.client_order_id
            self.submit_order(order)

        # Scheduled exit
        if now_t >= self.t_exit:
            self._cancel_stop()
            self._close_position("TIME-EXIT")
            self._entry_order_id = None
            self.entered_today = False

    def on_order_filled(self, event: OrderFilled) -> None:
        self.log.info(
            f"ORDER FILLED {event.order_side.name} {event.instrument_id} "
            f"qty={event.last_qty} px={event.last_px}"
        )

        # Entry fill -> place stop
        if self._entry_order_id is not None and event.client_order_id == self._entry_order_id:
            self.entered_today = True

            if self.stop_loss_pct and self.stop_loss_pct > 0:
                entry_px = float(event.last_px)
                entry_qty = float(event.last_qty)

                # Determine stop side and price
                if self.trade_qty > 0:  # long entry
                    stop_px = entry_px * (1.0 - self.stop_loss_pct)
                    stop_side = OrderSide.SELL
                else:  # short entry
                    stop_px = entry_px * (1.0 + self.stop_loss_pct)
                    stop_side = OrderSide.BUY

                stop_order = self.order_factory.stop_market(
                    instrument_id=self.instrument_id,
                    order_side=stop_side,
                    quantity=Quantity(entry_qty, self.instrument.size_precision),
                    trigger_price=Price(stop_px, self.instrument.price_precision),
                    time_in_force=TimeInForce.GTC,
                )
                self._stop_order_id = stop_order.client_order_id
                self.submit_order(stop_order)
                self.log.info(f"STOP {stop_side.name} placed at {stop_px:.5f}")

        # Stop fill
        if self._stop_order_id is not None and event.client_order_id == self._stop_order_id:
            self._stop_filled = True
            self._stop_fill_px = float(event.last_px)
            self.log.info(f"STOP FILLED px={event.last_px}")
            self._entry_order_id = None
            self._stop_order_id = None

    def on_position_closed(self, event: PositionClosed) -> None:
        tag = "STOP-OUT" if self._stop_filled else "TIME-EXIT"
        self.log.info(
            f"TRADE {tag} {event.instrument_id} "
            f"realized_pnl={event.realized_pnl}"
        )
        self._stop_filled = False
        self._stop_fill_px = None

    def _cancel_stop(self) -> None:
        if self._stop_order_id is None:
            return
        order = self.cache.order(self._stop_order_id)
        if order and order.is_open:
            self.cancel_order(order)
        self._stop_order_id = None

    def _close_position(self, tag: str) -> None:
        for position in self.cache.positions(venue=self.instrument_id.venue):
            if (
                position.instrument_id == self.instrument_id
                and not position.is_closed
                and position.strategy_id == self.id
            ):
                side = OrderSide.SELL if position.is_long else OrderSide.BUY
                order = self.order_factory.market(
                    instrument_id=self.instrument_id,
                    order_side=side,
                    quantity=Quantity(abs(position.quantity), self.instrument.size_precision),
                    time_in_force=TimeInForce.FOK,
                )
                self.submit_order(order, position_id=position.id)
                self.log.info(f"{tag} {self.instrument_id} qty={position.quantity}")

    def on_stop(self) -> None:
        self.unsubscribe_bars(self.bar_type)

    def on_reset(self) -> None:
        self.current_day = None
        self.is_trade_day = False
        self.entered_today = False
        self._entry_order_id = None
        self._stop_order_id = None
        self._stop_filled = False
        self._stop_fill_px = None


def _bar_datetime_in_tz(ts_event_ns: int, tz: ZoneInfo):
    dt = unix_nanos_to_dt(ts_event_ns)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)
