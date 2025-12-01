from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


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
    Tracks book, fills, and PnL in-memory. Intended as a thin stand-in for a DB.
    """

    def __init__(self):
        self.positions: Dict[str, Position] = {}
        self.fills: List[Fill] = []

    def record_fill(self, fill: Fill) -> None:
        self.fills.append(fill)
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

