"""
BarBuilder: convert ticks to bars with consistent rules across backtest/live.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from trader.core.events import Tick, Bar


@dataclass
class BarBuilder:
    bar_seconds: int = 60

    def on_tick(self, tick: Tick) -> List[Bar]:
        # Placeholder: plug in your tick-to-bar logic.
        return []

    def flush(self, force: bool = False) -> List[Bar]:
        return []
