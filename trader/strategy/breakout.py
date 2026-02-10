"""
NautilusTrader breakout strategy.

Buys when price reaches the 50-bar high, sells when price reaches the
50-bar low. Uses the existing breakout_signal() function.
"""
from __future__ import annotations

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import OrderFilled, PositionClosed
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy

from trader.strategy.signals import breakout_signal


class BreakoutConfig(StrategyConfig, frozen=True):
    instrument_id: str
    bar_type: str
    trade_size: float = 1.0
    contract_size: float = 100_000
    allocated_capital: float | None = None
    margin_rate: float = 0.02
    max_bars: int = 100


class BreakoutStrategy(Strategy):
    """
    Breakout strategy that accumulates bars, computes a signal via
    breakout_signal(), and enters positions on new highs/lows.
    """

    def __init__(self, config: BreakoutConfig) -> None:
        super().__init__(config)
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.bar_type = BarType.from_str(config.bar_type)
        if config.allocated_capital is not None:
            margin_per_lot = config.margin_rate * config.contract_size
            self.trade_qty = (config.allocated_capital / margin_per_lot) if margin_per_lot > 0 else 0.0
        else:
            self.trade_qty = config.trade_size * config.contract_size
        self.max_bars = config.max_bars
        self._bars: list[dict] = []

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.instrument_id)
        if self.instrument is None:
            self.log.error(f"Instrument {self.instrument_id} not found in cache")
            return
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
        signal = breakout_signal(df)

        if signal == 0:
            return

        has_position = self._has_position()

        if signal > 0 and not has_position:
            self._enter(OrderSide.BUY)
        elif signal < 0 and not has_position:
            self._enter(OrderSide.SELL)

    def _has_position(self) -> bool:
        for pos in self.cache.positions(venue=self.instrument_id.venue):
            if pos.instrument_id == self.instrument_id and not pos.is_closed:
                return True
        return False

    def _enter(self, side: OrderSide) -> None:
        qty = Quantity(abs(self.trade_qty), self.instrument.size_precision)
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=qty,
            time_in_force=TimeInForce.FOK,
        )
        self.submit_order(order)

    def on_order_filled(self, event: OrderFilled) -> None:
        self.log.info(
            f"BREAKOUT FILLED {event.order_side.name} {event.instrument_id} "
            f"qty={event.last_qty} px={event.last_px}"
        )

    def on_position_closed(self, event: PositionClosed) -> None:
        self.log.info(
            f"BREAKOUT CLOSED {event.instrument_id} "
            f"realized_pnl={event.realized_pnl}"
        )

    def on_stop(self) -> None:
        self.unsubscribe_bars(self.bar_type)

    def on_reset(self) -> None:
        self._bars.clear()
