"""
Virtual book placeholder; extend with MTM logic per strategy/tag.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from trader.portfolio.store import TickerStore


@dataclass
class VirtualBook:
    name: str
    store: TickerStore = field(default_factory=TickerStore)

    def equity(self) -> float:
        return self.store.unrealized_pnl()
