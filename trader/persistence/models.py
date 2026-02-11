"""Row-level dataclasses that map 1:1 to database rows."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FillRow:
    id: int | None
    order_id: str
    symbol: str
    side: str
    qty: float
    price: float
    fee: float
    ts: str  # ISO-8601 UTC
    strategy_id: str | None
    session_id: str


@dataclass
class PositionSnapshotRow:
    id: int | None
    symbol: str
    qty: float
    avg_price: float
    mtm_price: float | None
    unrealized_pnl: float
    ts: str
    strategy_id: str | None
    session_id: str


@dataclass
class EquitySnapshotRow:
    id: int | None
    ts: str
    equity: float
    cash: float
    strategy_id: str | None  # None = portfolio-level
    session_id: str


@dataclass
class BacktestResultRow:
    id: int | None
    session_id: str
    strategy_name: str
    started_at: str
    ended_at: str | None
    config_json: str | None
    metrics_json: str | None
    total_return: float | None
    sharpe: float | None
    max_drawdown: float | None


@dataclass
class OrderRow:
    id: int | None
    client_order_id: str
    symbol: str
    side: str
    qty: float
    order_type: str
    limit_price: float | None
    stop_price: float | None
    tag: str | None
    tif: str
    ts: str
    strategy_id: str | None
    session_id: str
