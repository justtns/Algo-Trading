"""Virtual book with optional equity tracking per strategy."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from trader.portfolio.store import TickerStore

if TYPE_CHECKING:
    from trader.portfolio.equity import EquityTracker


@dataclass
class VirtualBook:
    name: str
    store: TickerStore = field(default_factory=TickerStore)
    equity_tracker: EquityTracker | None = None

    def equity(self) -> float:
        return self.store.unrealized_pnl()

    def on_bar(self, ts: datetime) -> None:
        """Called after each bar to snap equity if tracker is configured."""
        if self.equity_tracker is not None:
            self.equity_tracker.on_bar(
                ts, self.equity(), strategy_id=self.name
            )
