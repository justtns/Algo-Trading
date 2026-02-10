"""
MetaTrader 5 live execution client for NautilusTrader.

Routes NautilusTrader orders to MT5 via order_send, mapping order types
and generating fill/reject events.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional

from nautilus_trader.config import LiveExecClientConfig
from nautilus_trader.execution.messages import SubmitOrder, CancelOrder
from nautilus_trader.live.execution_client import LiveExecutionClient
from nautilus_trader.model.enums import (
    LiquiditySide,
    OrderSide,
    OrderType,
    TimeInForce,
)
from nautilus_trader.model.identifiers import (
    AccountId,
    ClientId,
    ClientOrderId,
    InstrumentId,
    TradeId,
    Venue,
    VenueOrderId,
)
from nautilus_trader.model.objects import Money, Price, Quantity

from trader.adapters.metatrader.common import MetaTrader5Config, MetaTrader5Connection
from trader.core.constants import MT5


class MetaTrader5ExecClientConfig(LiveExecClientConfig, frozen=True):
    mt5_login: int | None = None
    mt5_password: str | None = None
    mt5_server: str | None = None
    mt5_path: str | None = None
    mt5_deviation: int = 20
    mt5_magic: int = 0
    mt5_comment: str = "nautilus-trader"


class MetaTrader5ExecutionClient(LiveExecutionClient):
    """
    Routes NautilusTrader orders to MetaTrader 5 via order_send.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        client_id: ClientId,
        venue: Venue,
        msgbus: Any,
        cache: Any,
        clock: Any,
        config: MetaTrader5ExecClientConfig,
        connection: MetaTrader5Connection | None = None,
    ):
        super().__init__(
            loop=loop,
            client_id=client_id,
            venue=venue,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
        )
        mt5_config = MetaTrader5Config(
            login=config.mt5_login,
            password=config.mt5_password,
            server=config.mt5_server,
            path=config.mt5_path,
            deviation=config.mt5_deviation,
            magic=config.mt5_magic,
            comment=config.mt5_comment,
        )
        self._connection = connection or MetaTrader5Connection(mt5_config)
        self._config = config

    @property
    def connection(self) -> MetaTrader5Connection:
        return self._connection

    async def _connect(self) -> None:
        self._connection.connect()
        self._log.info("MetaTrader5 execution client connected")

    async def _disconnect(self) -> None:
        self._connection.shutdown()
        self._log.info("MetaTrader5 execution client disconnected")

    async def _submit_order(self, command: SubmitOrder) -> None:
        order = command.order
        mt5 = self._connection.mt5

        symbol = order.instrument_id.symbol.value
        if not mt5.symbol_select(symbol, True):
            code, msg = mt5.last_error()
            self._log.error(f"Failed to select symbol {symbol}: [{code}] {msg}")
            self.generate_order_rejected(
                strategy_id=command.strategy_id,
                instrument_id=order.instrument_id,
                client_order_id=order.client_order_id,
                reason=f"Symbol select failed: [{code}] {msg}",
                ts_event=self._clock.timestamp_ns(),
            )
            return

        # Map order type
        action, mt5_type = self._map_order_type(order, mt5)

        # Determine price
        px = None
        if order.order_type == OrderType.LIMIT:
            px = float(order.price)
        elif order.order_type == OrderType.STOP_MARKET:
            px = float(order.trigger_price)
        elif order.order_type == OrderType.MARKET:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                px = tick.ask if order.side == OrderSide.BUY else tick.bid

        # Build MT5 request
        filling = self._connection.config.type_filling
        if order.time_in_force == TimeInForce.FOK:
            filling = mt5.ORDER_FILLING_FOK
        elif order.time_in_force == TimeInForce.IOC:
            filling = mt5.ORDER_FILLING_IOC

        request = {
            "action": action,
            "symbol": symbol,
            "volume": float(order.quantity),
            "type": mt5_type,
            "price": px,
            "deviation": self._config.mt5_deviation,
            "type_filling": filling,
            "type_time": self._connection.config.type_time,
            "comment": self._config.mt5_comment,
            "magic": self._config.mt5_magic,
        }

        result = mt5.order_send(request)
        ts_ns = self._clock.timestamp_ns()

        if result is None:
            code, msg = mt5.last_error()
            self.generate_order_rejected(
                strategy_id=command.strategy_id,
                instrument_id=order.instrument_id,
                client_order_id=order.client_order_id,
                reason=f"order_send failed: [{code}] {msg}",
                ts_event=ts_ns,
            )
            return

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            self.generate_order_rejected(
                strategy_id=command.strategy_id,
                instrument_id=order.instrument_id,
                client_order_id=order.client_order_id,
                reason=f"MT5 retcode={result.retcode}: {result.comment}",
                ts_event=ts_ns,
            )
            return

        venue_order_id = VenueOrderId(str(result.order))
        trade_id = TradeId(str(result.deal))

        self.generate_order_accepted(
            strategy_id=command.strategy_id,
            instrument_id=order.instrument_id,
            client_order_id=order.client_order_id,
            venue_order_id=venue_order_id,
            ts_event=ts_ns,
        )

        self.generate_order_filled(
            strategy_id=command.strategy_id,
            instrument_id=order.instrument_id,
            client_order_id=order.client_order_id,
            venue_order_id=venue_order_id,
            trade_id=trade_id,
            order_side=order.side,
            order_type=order.order_type,
            last_qty=order.quantity,
            last_px=Price(result.price, order.instrument_id.symbol.value.count(".")),
            quote_currency=self.cache.instrument(order.instrument_id).quote_currency
            if self.cache.instrument(order.instrument_id)
            else None,
            commission=Money(0, "USD"),
            liquidity_side=LiquiditySide.TAKER,
            ts_event=ts_ns,
        )

    async def _cancel_order(self, command: CancelOrder) -> None:
        mt5 = self._connection.mt5
        order = self.cache.order(command.client_order_id)
        if order is None or order.venue_order_id is None:
            self._log.warning(f"Cannot cancel unknown order {command.client_order_id}")
            return

        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": int(order.venue_order_id.value),
        }

        result = mt5.order_send(request)
        ts_ns = self._clock.timestamp_ns()

        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            self.generate_order_canceled(
                strategy_id=command.strategy_id,
                instrument_id=command.instrument_id,
                client_order_id=command.client_order_id,
                venue_order_id=order.venue_order_id,
                ts_event=ts_ns,
            )
        else:
            self._log.error(f"Cancel failed for {command.client_order_id}: {result}")

    @staticmethod
    def _map_order_type(order: Any, mt5: Any) -> tuple:
        """Map NautilusTrader order to MT5 action and type codes."""
        is_buy = order.side == OrderSide.BUY

        if order.order_type == OrderType.MARKET:
            return (
                mt5.TRADE_ACTION_DEAL,
                mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
            )
        elif order.order_type == OrderType.LIMIT:
            return (
                mt5.TRADE_ACTION_PENDING,
                mt5.ORDER_TYPE_BUY_LIMIT if is_buy else mt5.ORDER_TYPE_SELL_LIMIT,
            )
        elif order.order_type == OrderType.STOP_MARKET:
            return (
                mt5.TRADE_ACTION_PENDING,
                mt5.ORDER_TYPE_BUY_STOP if is_buy else mt5.ORDER_TYPE_SELL_STOP,
            )
        else:
            raise ValueError(f"Unsupported order type for MT5: {order.order_type}")
