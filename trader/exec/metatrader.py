"""
MetaTrader 5 broker sender wired for OrderRouter and shareable with streaming.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any, Optional

from trader.exec.router import OrderRequest, OrderRouter
from trader.exec.traderunner import RiskEstimator


@dataclass
class MetaTraderBroker:
    """
    Thin wrapper around MetaTrader5.order_send that also exposes the client for streaming.
    """

    login: Optional[int] = None
    password: Optional[str] = None
    server: Optional[str] = None
    path: Optional[str] = None
    deviation: int = 20
    type_filling: Any = None
    type_time: Any = None
    comment: str | None = "trader-engine"
    magic: int = 0
    auto_connect: bool = True

    _mt5: Any = None
    _connected: bool = False

    def __post_init__(self):
        try:
            import MetaTrader5 as mt5  # type: ignore
        except ImportError as exc:
            raise ImportError("MetaTrader5 package is required for MetaTraderBroker") from exc
        self._mt5 = mt5
        if self.type_filling is None:
            self.type_filling = mt5.ORDER_FILLING_IOC
        if self.type_time is None:
            self.type_time = mt5.ORDER_TIME_GTC
        if self.auto_connect:
            self.connect()

    def connect(self) -> None:
        # Validate credentials if login is provided (required for remote connections)
        if self.login is not None:
            if self.password is None:
                raise ValueError("Password is required when login is specified")
            if self.server is None:
                raise ValueError("Server is required when login is specified")
        
        ok = self._mt5.initialize(
            login=self.login,
            password=self.password,
            server=self.server,
            path=self.path,
        )
        if not ok:
            code, msg = self._mt5.last_error()
            raise RuntimeError(f"MetaTrader5 initialize failed: [{code}] {msg}")
        self._connected = True

    def ensure_connected(self) -> None:
        if not self._connected:
            self.connect()

    def shutdown(self) -> None:
        if self._mt5:
            try:
                self._mt5.shutdown()
            except Exception as e:
                # Log the error but still mark as disconnected
                warnings.warn(f"Error during MetaTrader5 shutdown: {e}")
        self._connected = False

    @property
    def mt5(self):
        """
        Expose the underlying MetaTrader5 module for shared use (e.g., streaming ticks).
        """
        self.ensure_connected()
        return self._mt5

    def _ensure_symbol(self, symbol: str) -> None:
        self.ensure_connected()
        if not self._mt5.symbol_select(symbol, True):
            code, msg = self._mt5.last_error()
            raise RuntimeError(f"Failed to select symbol {symbol}: [{code}] {msg}")

    def _map_order_type(self, side: str, order_type: str, price: float | None) -> tuple[int, int]:
        mt5 = self._mt5
        side_up = side.upper()
        is_buy = side_up == "BUY"

        ot = (order_type or "market").lower()
        if ot == "market":
            return mt5.TRADE_ACTION_DEAL, mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
        if ot == "limit":
            if price is None:
                raise ValueError("Limit order requires price")
            return mt5.TRADE_ACTION_PENDING, mt5.ORDER_TYPE_BUY_LIMIT if is_buy else mt5.ORDER_TYPE_SELL_LIMIT
        if ot == "stop":
            if price is None:
                raise ValueError("Stop order requires price")
            return mt5.TRADE_ACTION_PENDING, mt5.ORDER_TYPE_BUY_STOP if is_buy else mt5.ORDER_TYPE_SELL_STOP
        raise ValueError(f"Unsupported order_type for MT5: {order_type}")

    def send(self, req: OrderRequest, *, last_price: float | None = None) -> Any:
        """
        Build and dispatch a MetaTrader5 trade request from OrderRequest.
        """
        self.ensure_connected()

        self._ensure_symbol(req.symbol)
        mt5 = self._mt5

        action, typ = self._map_order_type(req.side, req.order_type, req.price)
        volume = float(req.size)
        tif = (req.time_in_force or "").lower()

        filling = self.type_filling
        if tif == "fok":
            filling = mt5.ORDER_FILLING_FOK
        elif tif == "ioc":
            filling = mt5.ORDER_FILLING_IOC

        px = req.price
        if px is None and action == mt5.TRADE_ACTION_DEAL:
            tick = mt5.symbol_info_tick(req.symbol)
            if tick:
                px = tick.ask if typ in (mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP) else tick.bid

        request = {
            "action": action,
            "symbol": req.symbol,
            "volume": volume,
            "type": typ,
            "price": px,
            "deviation": self.deviation,
            "type_filling": filling,
            "type_time": self.type_time,
            "comment": self.comment,
            "magic": self.magic,
        }

        result = mt5.order_send(request)
        if result is None:
            code, msg = mt5.last_error()
            raise RuntimeError(f"MetaTrader5 order_send failed: [{code}] {msg}")
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"MetaTrader5 order failed: {result}")
        return result


def build_metatrader_router(
    *,
    login: int | None = None,
    password: str | None = None,
    server: str | None = None,
    path: str | None = None,
    deviation: int = 20,
    risk: Optional[RiskEstimator] = None,
    broker: MetaTraderBroker | None = None,
) -> OrderRouter:
    """
    Convenience factory: create an OrderRouter that sends via MetaTrader5.
    """
    brk = broker or MetaTraderBroker(
        login=login,
        password=password,
        server=server,
        path=path,
        deviation=deviation,
    )
    return OrderRouter(brk.send, risk=risk or RiskEstimator())
