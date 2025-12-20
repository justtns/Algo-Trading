"""
Core event models for ticks, bars, signals, orders, and positions.
Lightweight dataclasses keep types consistent across data/exec layers.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class Tick:
    ts: datetime
    symbol: str
    bid: float | None  
    ask: float | None  
    last: float | None  
    size: float | None
    venue: str


@dataclass
class Bar:
    ts: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    n_ticks: Optional[int] = None


@dataclass
class Signal:
    ts: datetime
    symbol: str
    target_pos: float
    tag: Optional[str] = None
    meta: Optional[dict[str, Any]] = None


@dataclass
class Target:
    symbol: str
    target_qty: float
    tif: str = "DAY"
    tag: Optional[str] = None


@dataclass
class Order:
    client_order_id: str
    symbol: str
    side: str
    qty: float
    order_type: str
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    tag: Optional[str] = None
    tif: str = "DAY"


@dataclass
class Fill:
    order_id: str
    symbol: str
    side: str
    qty: float
    price: float
    fee: float
    ts: datetime
    tag: Optional[str] = None


@dataclass
class Position:
    symbol: str
    qty: float
    avg_price: float
    tag: Optional[str] = None


@dataclass
class AccountState:
    ts: datetime
    equity: float
    cash: float
    margin: Optional[float] = None
    buying_power: Optional[float] = None


@dataclass
class Heartbeat:
    ts: datetime
    source: str
    ok: bool
    latency_ms: float


@dataclass
class Command:
    ts: datetime
    name: str
    args: dict[str, Any]
