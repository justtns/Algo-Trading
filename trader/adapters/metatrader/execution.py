"""
MetaTrader 5 live execution client for NautilusTrader.

Routes NautilusTrader orders to MT5 via order_send, mapping order types
and generating fill/reject events.
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from typing import Any, Optional

from nautilus_trader.config import LiveExecClientConfig
from nautilus_trader.execution.messages import SubmitOrder, CancelOrder
from nautilus_trader.live.execution_client import LiveExecutionClient
from nautilus_trader.model.currencies import Currency
from nautilus_trader.model.enums import (
    AccountType,
    LiquiditySide,
    OmsType,
    OrderSide,
    OrderType,
    TimeInForce,
)
from nautilus_trader.model.identifiers import (
    AccountId,
    ClientId,
    ClientOrderId,
    InstrumentId,
    PositionId,
    TradeId,
    Venue,
    VenueOrderId,
)
from nautilus_trader.model.objects import AccountBalance, MarginBalance, Money, Price, Quantity

from trader.adapters.metatrader.common import MetaTrader5Config, MetaTrader5Connection
from trader.adapters.metatrader.provider import MetaTrader5InstrumentProvider
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
        instrument_provider = MetaTrader5InstrumentProvider(
            connection=self._connection,
            venue=venue,
        )

        oms_type = getattr(config, "oms_type", OmsType.HEDGING)
        account_type = getattr(config, "account_type", AccountType.MARGIN)
        base_currency = getattr(config, "base_currency", "USD")
        if isinstance(base_currency, str):
            base_currency = Currency.from_str(base_currency)

        super().__init__(
            loop=loop,
            client_id=client_id,
            venue=venue,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            oms_type=oms_type,
            account_type=account_type,
            base_currency=base_currency,
            instrument_provider=instrument_provider,
        )
        self._config = config

    @property
    def connection(self) -> MetaTrader5Connection:
        return self._connection

    async def _connect(self) -> None:
        self._connection.connect()
        self._log.info("MetaTrader5 execution client connected")

        # Publish initial account state so order events have a valid account_id.
        mt5 = self._connection.mt5
        account = mt5.account_info()
        if account is None:
            code, msg = mt5.last_error()
            self._log.error(f"Failed to read MT5 account info: [{code}] {msg}")
            return

        self._set_account_id(AccountId(f"{self.id.value}-{account.login}"))

        currency_code = str(getattr(account, "currency", "") or "USD")
        currency = Currency.from_str(currency_code)

        precision = currency.precision
        quantum = Decimal("1").scaleb(-precision)

        total_raw = Decimal(str(getattr(account, "equity", 0.0) or 0.0))
        locked_raw = Decimal(str(getattr(account, "margin", 0.0) or 0.0))
        if locked_raw < 0:
            locked_raw = Decimal("0")

        total = total_raw.quantize(quantum)
        locked = min(locked_raw, total).quantize(quantum)
        free = (total - locked).quantize(quantum)

        balances = [
            AccountBalance(
                total=Money(total, currency),
                locked=Money(locked, currency),
                free=Money(free, currency),
            )
        ]
        margins = [
            MarginBalance(
                initial=Money(locked, currency),
                maintenance=Money(locked, currency),
            )
        ]

        self.generate_account_state(
            balances=balances,
            margins=margins,
            reported=True,
            ts_event=self._clock.timestamp_ns(),
            info={
                "login": int(account.login),
                "server": str(getattr(account, "server", "")),
                "leverage": int(getattr(account, "leverage", 0) or 0),
            },
        )
        await self._await_account_registered()

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

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            code, msg = mt5.last_error()
            self.generate_order_rejected(
                strategy_id=command.strategy_id,
                instrument_id=order.instrument_id,
                client_order_id=order.client_order_id,
                reason=f"symbol_info failed for {symbol}: [{code}] {msg}",
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

        volume, volume_error = self._resolve_mt5_volume(order=order, symbol_info=symbol_info)
        if volume_error is not None:
            self.generate_order_rejected(
                strategy_id=command.strategy_id,
                instrument_id=order.instrument_id,
                client_order_id=order.client_order_id,
                reason=volume_error,
                ts_event=self._clock.timestamp_ns(),
            )
            return

        # Build MT5 request with broker-supported filling mode.
        filling = self._resolve_mt5_filling_mode(
            order=order,
            symbol=symbol,
            symbol_info=symbol_info,
            mt5=mt5,
        )

        request = {
            "action": action,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_type,
            "price": px,
            "deviation": self._config.mt5_deviation,
            "type_filling": filling,
            "type_time": self._connection.config.type_time,
            "comment": self._config.mt5_comment,
            "magic": self._config.mt5_magic,
        }

        if action == mt5.TRADE_ACTION_DEAL and command.position_id is not None:
            position_ticket, position_error = self._resolve_mt5_position_ticket(command.position_id)
            if position_error is not None:
                self.generate_order_rejected(
                    strategy_id=command.strategy_id,
                    instrument_id=order.instrument_id,
                    client_order_id=order.client_order_id,
                    reason=position_error,
                    ts_event=self._clock.timestamp_ns(),
                )
                return
            request["position"] = position_ticket

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
                reason=(
                    f"MT5 retcode={result.retcode}: {result.comment} "
                    f"(volume={volume}, filling={filling})"
                ),
                ts_event=ts_ns,
            )
            return

        venue_order_id = VenueOrderId(str(result.order))
        trade_id = TradeId(str(result.deal))
        venue_position_id = (
            PositionId(str(result.position))
            if getattr(result, "position", 0)
            else None
        )
        instrument = self._cache.instrument(order.instrument_id)
        price_precision = instrument.price_precision if instrument is not None else 5
        quote_currency = (
            instrument.quote_currency
            if instrument is not None
            else Currency.from_str("USD")
        )

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
            venue_position_id=venue_position_id,
            trade_id=trade_id,
            order_side=order.side,
            order_type=order.order_type,
            last_qty=order.quantity,
            last_px=Price(result.price, price_precision),
            quote_currency=quote_currency,
            commission=Money(0, quote_currency),
            liquidity_side=LiquiditySide.TAKER,
            ts_event=ts_ns,
        )

    async def _cancel_order(self, command: CancelOrder) -> None:
        mt5 = self._connection.mt5
        order = self._cache.order(command.client_order_id)
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
    def _extract_supported_fillings(raw_filling_mode: Any, mt5: Any) -> set[int]:
        """
        Translate MT5 symbol_info.filling_mode into ORDER_FILLING_* values.

        Some brokers expose filling_mode as a bitmask flag set (1/2/4), while
        others return a direct enum value (0/1/2). This handles both.
        """
        try:
            raw = int(raw_filling_mode)
        except (TypeError, ValueError):
            return set()

        mode_to_flag = {
            int(mt5.ORDER_FILLING_FOK): getattr(mt5, "SYMBOL_FILLING_FOK", 1),
            int(mt5.ORDER_FILLING_IOC): getattr(mt5, "SYMBOL_FILLING_IOC", 2),
            int(mt5.ORDER_FILLING_RETURN): getattr(mt5, "SYMBOL_FILLING_RETURN", 4),
        }

        supported: set[int] = set()
        for mode, flag in mode_to_flag.items():
            try:
                flag_value = int(flag)
            except (TypeError, ValueError):
                continue
            if raw & flag_value:
                supported.add(mode)

        # Fallback for brokers exposing filling mode as a direct enum.
        if not supported and raw in mode_to_flag:
            supported.add(raw)

        return supported

    @staticmethod
    def _round_to_step(value: float, step: float | None) -> float:
        if step is None or step <= 0:
            return value

        steps = round(value / step)
        rounded = steps * step
        step_str = f"{step:.10f}".rstrip("0")
        precision = len(step_str.split(".")[1]) if "." in step_str else 0
        return round(rounded, precision)

    @staticmethod
    def _convert_quantity_to_mt5_volume(quantity: float, lot_size: float | None) -> float:
        if lot_size is None or lot_size <= 0:
            return quantity
        return quantity / lot_size

    def _resolve_mt5_volume(
        self,
        order: Any,
        symbol_info: Any,
    ) -> tuple[float | None, str | None]:
        instrument = self._cache.instrument(order.instrument_id)
        lot_size = float(getattr(instrument, "lot_size", 0.0) or 0.0) if instrument else None

        requested_qty = float(order.quantity)
        volume = self._convert_quantity_to_mt5_volume(requested_qty, lot_size)

        step = float(getattr(symbol_info, "volume_step", 0.0) or 0.0)
        min_volume = float(getattr(symbol_info, "volume_min", 0.0) or 0.0)
        max_volume = float(getattr(symbol_info, "volume_max", 0.0) or 0.0)
        volume = self._round_to_step(volume, step)

        if volume <= 0:
            return None, f"Invalid MT5 volume {volume} computed from quantity {requested_qty}"

        if min_volume > 0 and volume < min_volume:
            return None, f"Computed MT5 volume {volume} below broker minimum {min_volume}"

        if max_volume > 0 and volume > max_volume:
            return None, f"Computed MT5 volume {volume} above broker maximum {max_volume}"

        return volume, None

    def _resolve_mt5_filling_mode(
        self,
        order: Any,
        symbol: str,
        symbol_info: Any,
        mt5: Any,
    ) -> int:
        configured = int(self._connection.config.type_filling)
        requested = configured
        if order.time_in_force == TimeInForce.FOK:
            requested = int(mt5.ORDER_FILLING_FOK)
        elif order.time_in_force == TimeInForce.IOC:
            requested = int(mt5.ORDER_FILLING_IOC)

        supported = self._extract_supported_fillings(
            raw_filling_mode=getattr(symbol_info, "filling_mode", None),
            mt5=mt5,
        )
        if not supported or requested in supported:
            return requested

        if configured in supported:
            fallback = configured
        else:
            fallback = next(
                (
                    int(candidate)
                    for candidate in (
                        getattr(mt5, "ORDER_FILLING_IOC", None),
                        getattr(mt5, "ORDER_FILLING_FOK", None),
                        getattr(mt5, "ORDER_FILLING_RETURN", None),
                    )
                    if candidate is not None and int(candidate) in supported
                ),
                requested,
            )

        if fallback != requested:
            self._log.warning(
                f"Requested MT5 filling mode {requested} unsupported for {symbol}; "
                f"using {fallback} instead"
            )

        return fallback

    def _resolve_mt5_position_ticket(
        self,
        position_id: PositionId | None,
    ) -> tuple[int | None, str | None]:
        if position_id is None:
            return None, None

        position = self._cache.position(position_id)
        if position is None:
            return None, f"Position {position_id} not found in cache for MT5 close order"

        venue_position_id = getattr(position, "venue_position_id", None)
        if venue_position_id is None:
            opening_order_id = getattr(position, "opening_order_id", None)
            if opening_order_id is not None:
                opening_order = self._cache.order(opening_order_id)
                opening_venue_order_id = (
                    getattr(opening_order, "venue_order_id", None)
                    if opening_order is not None
                    else None
                )
                if opening_venue_order_id is not None:
                    opening_raw = getattr(opening_venue_order_id, "value", opening_venue_order_id)
                    try:
                        ticket = int(str(opening_raw))
                        self._log.warning(
                            f"Position {position_id} missing venue_position_id; "
                            f"using opening order ticket {ticket} for MT5 close order"
                        )
                        return ticket, None
                    except (TypeError, ValueError):
                        pass

            return None, f"Position {position_id} missing venue_position_id for MT5 close order"

        raw_id = getattr(venue_position_id, "value", venue_position_id)
        try:
            return int(str(raw_id)), None
        except (TypeError, ValueError):
            return None, (
                f"Invalid venue_position_id '{raw_id}' for position {position_id} in MT5 close order"
            )

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
