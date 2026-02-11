"""
NautilusTrader RSI + MACD-histogram-curl + moving-average confirmation strategy.
"""
from __future__ import annotations

from datetime import date, time
from zoneinfo import ZoneInfo

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.datetime import unix_nanos_to_dt
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
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from trader.strategy.live_helpers import LiveExecutionMixin, resolve_trade_quantity
from trader.strategy.signals import rsi_macd_ma_signal


class RsiMacdMaConfig(StrategyConfig, frozen=True):
    instrument_id: str
    bar_type: str
    trade_size: float = 1.0
    max_bars: int = 300
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    ma_fast: int = 20
    ma_slow: int = 50
    stop_loss_pct: float | None = None
    close_on_neutral: bool = True
    exit_time: str | None = None
    trading_timezone: str = "UTC"
    time_in_force: str = "FOK"
    exec_client_id: str | None = None


class RsiMacdMaStrategy(LiveExecutionMixin, Strategy):
    """
    Strategy behavior:
    - SELL when RSI is oversold + MACD histogram curls down + MAs bearish.
    - BUY when RSI is overbought + MACD histogram curls up + MAs bullish.
    - If signal is opposite an open position, close that position.
    - If signal is neutral and close_on_neutral=True, close position.
    - If exit_time is set, close any open position at/after that time.
    - If stop_loss_pct is set, place a stop-market order after entry fill.
    """

    def __init__(self, config: RsiMacdMaConfig) -> None:
        super().__init__(config)
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.bar_type = BarType.from_str(config.bar_type)
        self.trade_size = config.trade_size
        self.trade_qty = config.trade_size  # will be rescaled once instrument is loaded
        self._configure_live_execution(
            exec_client_id=config.exec_client_id,
            time_in_force=config.time_in_force,
            default_tif=TimeInForce.FOK,
        )
        self.max_bars = config.max_bars

        self.rsi_period = config.rsi_period
        self.rsi_oversold = config.rsi_oversold
        self.rsi_overbought = config.rsi_overbought
        self.macd_fast = config.macd_fast
        self.macd_slow = config.macd_slow
        self.macd_signal = config.macd_signal
        self.ma_fast = config.ma_fast
        self.ma_slow = config.ma_slow

        self.stop_loss_pct = config.stop_loss_pct
        self.close_on_neutral = config.close_on_neutral
        self.trading_tz = ZoneInfo(config.trading_timezone)
        self.t_exit = _parse_time_or_none(config.exit_time)

        self._bars: list[dict] = []
        self.current_day: date | None = None
        self._entry_order_id = None
        self._stop_order_id = None
        self._stop_filled = False
        self._pending_close_position_ids: set = set()
        self._close_order_to_position_id: dict = {}

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
        self._bars.append({
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": float(bar.volume),
        })
        if len(self._bars) > self.max_bars:
            self._bars = self._bars[-self.max_bars:]

        dt = _bar_datetime_in_tz(bar.ts_event, self.trading_tz)
        now_d = dt.date()
        now_t = dt.time()
        if self.current_day is None or now_d != self.current_day:
            self.current_day = now_d

        pos = self._current_position()

        if self.t_exit is not None and now_t >= self.t_exit:
            if pos is not None and pos.id not in self._pending_close_position_ids:
                self._cancel_stop()
                self._close_position(pos, tag="TIME-EXIT")
            return

        signal = rsi_macd_ma_signal(
            pd.DataFrame(self._bars),
            rsi_period=self.rsi_period,
            rsi_oversold=self.rsi_oversold,
            rsi_overbought=self.rsi_overbought,
            macd_fast=self.macd_fast,
            macd_slow=self.macd_slow,
            macd_signal=self.macd_signal,
            ma_fast=self.ma_fast,
            ma_slow=self.ma_slow,
        )

        if signal == 0:
            if (
                self.close_on_neutral
                and pos is not None
                and pos.id not in self._pending_close_position_ids
            ):
                self._cancel_stop()
                self._close_position(pos, tag="NEUTRAL-EXIT")
            return

        target_side = OrderSide.BUY if signal > 0 else OrderSide.SELL
        if pos is None:
            if self._entry_order_id is None:
                self._enter(target_side)
            return

        if (target_side == OrderSide.BUY and pos.is_long) or (
            target_side == OrderSide.SELL and pos.is_short
        ):
            return

        if pos.id in self._pending_close_position_ids:
            return

        self._cancel_stop()
        self._close_position(pos, tag="SIGNAL-FLIP")

    def _enter(self, side: OrderSide) -> None:
        qty = Quantity(abs(self.trade_qty), self.instrument.size_precision)
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=qty,
            time_in_force=self.time_in_force,
        )
        self._entry_order_id = order.client_order_id
        self._submit_order(order)

    def _close_position(self, pos, tag: str) -> None:
        side = OrderSide.SELL if pos.is_long else OrderSide.BUY
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=Quantity(abs(pos.quantity), self.instrument.size_precision),
            time_in_force=self.time_in_force,
        )
        self._submit_order(order, position_id=pos.id)
        self._track_pending_close(position_id=pos.id, client_order_id=order.client_order_id)
        self.log.info(f"{tag} {self.instrument_id} qty={pos.quantity}")

    def on_order_filled(self, event: OrderFilled) -> None:
        self.log.info(
            f"RSI-MACD-MA FILLED {event.order_side.name} {event.instrument_id} "
            f"qty={event.last_qty} px={event.last_px}"
        )

        if self._entry_order_id is not None and event.client_order_id == self._entry_order_id:
            self._entry_order_id = None
            if self.stop_loss_pct and self.stop_loss_pct > 0:
                entry_px = float(event.last_px)
                entry_qty = float(event.last_qty)
                if event.order_side == OrderSide.BUY:
                    stop_side = OrderSide.SELL
                    stop_px = entry_px * (1.0 - self.stop_loss_pct)
                else:
                    stop_side = OrderSide.BUY
                    stop_px = entry_px * (1.0 + self.stop_loss_pct)

                stop_order = self.order_factory.stop_market(
                    instrument_id=self.instrument_id,
                    order_side=stop_side,
                    quantity=Quantity(entry_qty, self.instrument.size_precision),
                    trigger_price=Price(stop_px, self.instrument.price_precision),
                    time_in_force=TimeInForce.GTC,
                )
                self._stop_order_id = stop_order.client_order_id
                self._submit_order(stop_order)
                self.log.info(f"STOP {stop_side.name} placed at {stop_px:.5f}")

        if self._stop_order_id is not None and event.client_order_id == self._stop_order_id:
            self._stop_order_id = None
            self._stop_filled = True
            self.log.info(f"STOP FILLED px={event.last_px}")

    def on_order_rejected(self, event: OrderRejected) -> None:
        if self._entry_order_id is not None and event.client_order_id == self._entry_order_id:
            self._entry_order_id = None
        if self._stop_order_id is not None and event.client_order_id == self._stop_order_id:
            self._stop_order_id = None
            return
        self._release_pending_close_on_failed_order(client_order_id=event.client_order_id)

    def on_order_denied(self, event: OrderDenied) -> None:
        if self._entry_order_id is not None and event.client_order_id == self._entry_order_id:
            self._entry_order_id = None
        if self._stop_order_id is not None and event.client_order_id == self._stop_order_id:
            self._stop_order_id = None
            return
        self._release_pending_close_on_failed_order(client_order_id=event.client_order_id)

    def on_order_canceled(self, event: OrderCanceled) -> None:
        if self._entry_order_id is not None and event.client_order_id == self._entry_order_id:
            self._entry_order_id = None
            return
        if self._stop_order_id is not None and event.client_order_id == self._stop_order_id:
            self._stop_order_id = None
            return
        self._release_pending_close_on_failed_order(client_order_id=event.client_order_id)

    def on_order_expired(self, event: OrderExpired) -> None:
        if self._entry_order_id is not None and event.client_order_id == self._entry_order_id:
            self._entry_order_id = None
            return
        if self._stop_order_id is not None and event.client_order_id == self._stop_order_id:
            self._stop_order_id = None
            return
        self._release_pending_close_on_failed_order(client_order_id=event.client_order_id)

    def on_position_closed(self, event: PositionClosed) -> None:
        self._release_pending_close_on_position_closed(position_id=event.position_id)
        tag = "STOP-OUT" if self._stop_filled else "EXIT"
        self.log.info(
            f"RSI-MACD-MA {tag} {event.instrument_id} "
            f"realized_pnl={event.realized_pnl}"
        )
        self._stop_filled = False
        self._entry_order_id = None
        self._stop_order_id = None

    def on_stop(self) -> None:
        self._cancel_stop()
        position = self._current_position()
        if position is not None and position.id not in self._pending_close_position_ids:
            self._close_position(position, tag="STOP")
        self.unsubscribe_bars(self.bar_type)
        self._entry_order_id = None

    def on_reset(self) -> None:
        self._bars.clear()
        self.current_day = None
        self._entry_order_id = None
        self._stop_order_id = None
        self._stop_filled = False
        self._pending_close_position_ids.clear()
        self._close_order_to_position_id.clear()

    def _cancel_stop(self) -> None:
        if self._stop_order_id is None:
            return
        order = self.cache.order(self._stop_order_id)
        if order and order.is_open:
            self.cancel_order(order)
        self._stop_order_id = None


def _bar_datetime_in_tz(ts_event_ns: int, tz: ZoneInfo):
    dt = unix_nanos_to_dt(ts_event_ns)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(tz)


def _parse_time_or_none(value: str | None) -> time | None:
    if value is None:
        return None
    h, m, s = map(int, value.split(":"))
    return time(h, m, s)
