"""
NautilusTrader mean reversion strategy.

Buys when price drops below MA(20) * 0.999, sells when price rises above
MA(20) * 1.001. Uses the existing mean_reversion_signal() function.
"""
from __future__ import annotations

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import (
    OrderDenied,
    OrderFilled,
    OrderRejected,
    PositionClosed,
)
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy

from trader.strategy.signals import mean_reversion_signal


class MeanReversionConfig(StrategyConfig, frozen=True):
    instrument_id: str
    bar_type: str
    trade_size: float = 1.0
    allocated_capital: float | None = None
    margin_rate: float = 0.02
    max_bars: int = 100


class MeanReversionStrategy(Strategy):
    """
    Mean reversion strategy that accumulates bars, computes a signal via
    mean_reversion_signal(), and enters/exits positions accordingly.
    """

    def __init__(self, config: MeanReversionConfig) -> None:
        super().__init__(config)
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.bar_type = BarType.from_str(config.bar_type)
        self._configured_trade_size = config.trade_size
        self._allocated_capital = config.allocated_capital
        self.margin_rate = config.margin_rate
        self.trade_qty = config.trade_size  # scaled once instrument is loaded
        self.max_bars = config.max_bars
        self._bars: list[dict] = []
        self._entry_order_id = None
        self._pending_close_position_ids: set = set()

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        if self.instrument is None:
            self.log.error(f"Instrument {self.instrument_id} not found in cache")
            return
        self._refresh_trade_qty()
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

        df = pd.DataFrame(self._bars)
        signal = mean_reversion_signal(df)

        if signal == 0:
            return

        target_side = OrderSide.BUY if signal > 0 else OrderSide.SELL
        position = self._current_position()

        if position is None:
            if self._entry_order_id is None:
                self._enter(target_side)
            return

        if (target_side == OrderSide.BUY and position.is_long) or (
            target_side == OrderSide.SELL and position.is_short
        ):
            return

        if position.id in self._pending_close_position_ids:
            return

        self._close_position(position, tag="SIGNAL-FLIP")

    def _has_position(self) -> bool:
        return self._current_position() is not None

    def _current_position(self):
        for pos in self.cache.positions(venue=self.instrument_id.venue):
            if (
                pos.instrument_id == self.instrument_id
                and not pos.is_closed
                and pos.strategy_id == self.id
            ):
                return pos
        return None

    def _enter(self, side: OrderSide) -> None:
        qty = Quantity(abs(self.trade_qty), self.instrument.size_precision)
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=qty,
            time_in_force=TimeInForce.FOK,
        )
        self._entry_order_id = order.client_order_id
        self.submit_order(order)

    def _close_position(self, position, tag: str) -> None:
        side = OrderSide.SELL if position.is_long else OrderSide.BUY
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=Quantity(abs(position.quantity), self.instrument.size_precision),
            time_in_force=TimeInForce.FOK,
        )
        self.submit_order(order, position_id=position.id)
        self._pending_close_position_ids.add(position.id)
        self.log.info(f"{tag} {self.instrument_id} qty={position.quantity}")

    def on_order_filled(self, event: OrderFilled) -> None:
        if self._entry_order_id is not None and event.client_order_id == self._entry_order_id:
            self._entry_order_id = None
        self.log.info(
            f"MEAN-REV FILLED {event.order_side.name} {event.instrument_id} "
            f"qty={event.last_qty} px={event.last_px}"
        )

    def on_order_rejected(self, event: OrderRejected) -> None:
        if self._entry_order_id is not None and event.client_order_id == self._entry_order_id:
            self._entry_order_id = None

    def on_order_denied(self, event: OrderDenied) -> None:
        if self._entry_order_id is not None and event.client_order_id == self._entry_order_id:
            self._entry_order_id = None

    def on_position_closed(self, event: PositionClosed) -> None:
        self._pending_close_position_ids.discard(event.position_id)
        self.log.info(
            f"MEAN-REV CLOSED {event.instrument_id} "
            f"realized_pnl={event.realized_pnl}"
        )

    def on_stop(self) -> None:
        position = self._current_position()
        if position is not None and position.id not in self._pending_close_position_ids:
            self._close_position(position, tag="STOP")
        self.unsubscribe_bars(self.bar_type)
        self._entry_order_id = None

    def on_reset(self) -> None:
        self._bars.clear()
        self._entry_order_id = None
        self._pending_close_position_ids.clear()

    def _refresh_trade_qty(self) -> None:
        lot_size = float(getattr(self.instrument, "lot_size", 1.0) or 1.0)
        if self._allocated_capital is not None and self.margin_rate > 0:
            self.trade_qty = self._allocated_capital / self.margin_rate
        else:
            self.trade_qty = self._configured_trade_size * lot_size
