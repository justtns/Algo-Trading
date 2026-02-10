"""
Shared MetaTrader 5 configuration and connection management.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MetaTrader5Config:
    """
    Configuration for MetaTrader 5 connection.
    """

    login: Optional[int] = None
    password: Optional[str] = None
    server: Optional[str] = None
    path: Optional[str] = None
    deviation: int = 20
    magic: int = 0
    comment: str = "nautilus-trader"
    type_filling: Any = None
    type_time: Any = None


class MetaTrader5Connection:
    """
    Manages a shared MetaTrader 5 connection. Thread-safe lazy initialization.
    """

    def __init__(self, config: MetaTrader5Config):
        self.config = config
        self._mt5: Any = None
        self._connected = False

    @property
    def mt5(self) -> Any:
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5  # type: ignore
            except ImportError as exc:
                raise ImportError(
                    "MetaTrader5 package is required. Install with: pip install MetaTrader5"
                ) from exc
            self._mt5 = mt5
        return self._mt5

    def connect(self) -> None:
        if self._connected:
            return
        mt5 = self.mt5
        ok = mt5.initialize(
            login=self.config.login,
            password=self.config.password,
            server=self.config.server,
            path=self.config.path,
        )
        if not ok:
            code, msg = mt5.last_error()
            raise RuntimeError(f"MetaTrader5 initialize failed: [{code}] {msg}")

        if self.config.type_filling is None:
            self.config.type_filling = mt5.ORDER_FILLING_IOC
        if self.config.type_time is None:
            self.config.type_time = mt5.ORDER_TIME_GTC

        self._connected = True

    def ensure_connected(self) -> None:
        if not self._connected:
            self.connect()

    def shutdown(self) -> None:
        if self._mt5 and self._connected:
            try:
                self._mt5.shutdown()
            except Exception:
                pass
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected
