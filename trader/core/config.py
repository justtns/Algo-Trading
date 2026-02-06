"""
Configuration loader for the trading system.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class MetaTraderConfig:
    """MetaTrader 5 connection configuration."""
    login: Optional[int] = None
    password: Optional[str] = None
    server: Optional[str] = None
    path: Optional[str] = None
    deviation: int = 20
    magic: int = 0


@dataclass
class TradingConfig:
    """Trading risk and sizing configuration."""
    base_currency: str = "USD"
    default_contract_size_fx: float = 100000.0
    max_position: Optional[float] = None
    max_notional: Optional[float] = None
    risk_fraction: float = 0.01
    stop_loss_pct: Optional[float] = None


@dataclass
class StreamingConfig:
    """Live streaming configuration."""
    bar_seconds: int = 60
    poll_interval: float = 1.0
    max_batch: int = 500
    lookback_sec: int = 5


@dataclass
class BacktestConfig:
    """Backtesting configuration."""
    initial_cash: float = 100000.0
    commission: float = 0.0
    leverage: Optional[float] = None
    cheat_on_open: bool = False


@dataclass
class SystemConfig:
    """Complete system configuration."""
    metatrader: MetaTraderConfig
    trading: TradingConfig
    streaming: StreamingConfig
    backtest: BacktestConfig

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any]) -> SystemConfig:
        """Create SystemConfig from a dictionary."""
        mt_dict = config_dict.get("metatrader", {})
        mt_dict.pop("comment", None)  # Remove comment field if present
        
        trading_dict = config_dict.get("trading", {})
        trading_dict.pop("comment_contract_size", None)  # Remove comment field if present
        
        return cls(
            metatrader=MetaTraderConfig(**mt_dict),
            trading=TradingConfig(**trading_dict),
            streaming=StreamingConfig(**config_dict.get("streaming", {})),
            backtest=BacktestConfig(**config_dict.get("backtest", {})),
        )

    @classmethod
    def load(cls, config_path: str | Path = "config/config.json") -> SystemConfig:
        """Load configuration from JSON file."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        with open(path, "r") as f:
            config_dict = json.load(f)
        
        return cls.from_dict(config_dict)

    def save(self, config_path: str | Path = "config/config.json") -> None:
        """Save configuration to JSON file."""
        path = Path(config_path)
        config_dict = {
            "metatrader": {
                "login": self.metatrader.login,
                "password": self.metatrader.password,
                "server": self.metatrader.server,
                "path": self.metatrader.path,
                "comment": "Set login, password, and server for remote MetaTrader 5 connections. Leave null for local terminal connections.",
                "deviation": self.metatrader.deviation,
                "magic": self.metatrader.magic,
            },
            "trading": {
                "base_currency": self.trading.base_currency,
                "default_contract_size_fx": self.trading.default_contract_size_fx,
                "comment_contract_size": "100000 represents a standard FX lot (100,000 units of base currency)",
                "max_position": self.trading.max_position,
                "max_notional": self.trading.max_notional,
                "risk_fraction": self.trading.risk_fraction,
                "stop_loss_pct": self.trading.stop_loss_pct,
            },
            "streaming": {
                "bar_seconds": self.streaming.bar_seconds,
                "poll_interval": self.streaming.poll_interval,
                "max_batch": self.streaming.max_batch,
                "lookback_sec": self.streaming.lookback_sec,
            },
            "backtest": {
                "initial_cash": self.backtest.initial_cash,
                "commission": self.backtest.commission,
                "leverage": self.backtest.leverage,
                "cheat_on_open": self.backtest.cheat_on_open,
            },
        }
        
        with open(path, "w") as f:
            json.dump(config_dict, f, indent=2)
