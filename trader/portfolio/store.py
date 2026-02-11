from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from trader.persistence.database import Database


@dataclass
class Position:
    symbol: str
    size: float
    avg_price: float
    mtm_price: float | None = None

    @property
    def notional(self) -> float:
        px = self.mtm_price or self.avg_price
        return px * self.size


@dataclass
class Fill:
    symbol: str
    side: str
    size: float
    price: float
    strategy_id: str | None = None


class TickerStore:
    """
    Tracks book, fills, and PnL in-memory with optional SQLite write-through.

    When *db* is provided, every fill is also persisted to the database.
    When *db* is ``None``, behaviour is identical to the original in-memory-only store.
    """

    def __init__(
        self,
        db: Database | None = None,
        session_id: str | None = None,
    ):
        self.positions: Dict[str, Position] = {}
        self.fills: List[Fill] = []
        self._db = db
        self.session_id: str = session_id or uuid.uuid4().hex

        # Lazy-init persistence repos
        self._fill_repo = None
        self._position_repo = None
        if db is not None:
            from trader.persistence.repositories import (
                FillRepository,
                PositionRepository,
            )

            conn = db.connect_sync()
            self._fill_repo = FillRepository(conn)
            self._position_repo = PositionRepository(conn)

    def record_fill(self, fill: Fill) -> None:
        self.fills.append(fill)

        # Persist to DB if configured
        if self._fill_repo is not None:
            from trader.persistence.models import FillRow

            self._fill_repo.insert(
                FillRow(
                    id=None,
                    order_id=getattr(fill, "order_id", ""),
                    symbol=fill.symbol,
                    side=fill.side,
                    qty=fill.size,
                    price=fill.price,
                    fee=getattr(fill, "fee", 0.0),
                    ts=datetime.now(timezone.utc).isoformat(),
                    strategy_id=fill.strategy_id,
                    session_id=self.session_id,
                )
            )

        # Update in-memory position
        pos = self.positions.get(fill.symbol)
        signed_size = fill.size if fill.side.upper() == "BUY" else -fill.size

        if pos is None:
            self.positions[fill.symbol] = Position(
                symbol=fill.symbol,
                size=signed_size,
                avg_price=fill.price,
                mtm_price=fill.price,
            )
            return

        new_size = pos.size + signed_size
        if new_size == 0:
            # flat
            self.positions.pop(fill.symbol, None)
            return

        # weighted average price
        new_notional = (pos.avg_price * pos.size) + (fill.price * signed_size)
        self.positions[fill.symbol] = Position(
            symbol=fill.symbol,
            size=new_size,
            avg_price=new_notional / new_size,
            mtm_price=fill.price,
        )

    def mark_price(self, symbol: str, price: float) -> None:
        pos = self.positions.get(symbol)
        if pos:
            pos.mtm_price = price

    def unrealized_pnl(self) -> float:
        return sum(pos.notional for pos in self.positions.values())

    def snapshot_positions(self, strategy_id: str | None = None) -> None:
        """Persist current positions to the database."""
        if self._position_repo is None:
            return

        from trader.persistence.models import PositionSnapshotRow

        ts = datetime.now(timezone.utc).isoformat()
        for pos in self.positions.values():
            self._position_repo.insert(
                PositionSnapshotRow(
                    id=None,
                    symbol=pos.symbol,
                    qty=pos.size,
                    avg_price=pos.avg_price,
                    mtm_price=pos.mtm_price,
                    unrealized_pnl=pos.notional,
                    ts=ts,
                    strategy_id=strategy_id,
                    session_id=self.session_id,
                )
            )
