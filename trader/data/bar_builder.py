"""
BarBuilder: convert ticks to bars with consistent rules across backtest/live.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from trader.core.events import Tick, Bar


@dataclass
class BarState:
    start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    n_ticks: int = 0


@dataclass
class BarBuilder:
    bar_seconds: int = 60
    _state: Dict[str, BarState] = field(default_factory=dict)

    def _bucket_start(self, ts: datetime) -> datetime:
        ts = ts.astimezone(timezone.utc)
        floored = ts.replace(second=0, microsecond=0)
        delta = (ts - floored).seconds
        bucket_offset = (delta // self.bar_seconds) * self.bar_seconds
        return floored + timedelta(seconds=bucket_offset)

    def on_tick(self, tick: Tick) -> List[Bar]:
        completed: List[Bar] = []
        bucket = self._bucket_start(tick.ts)
        key = tick.symbol
        state = self._state.get(key)

        if state is None or bucket > state.start:
            if state:
                completed.append(
                    Bar(
                        ts=state.start,
                        symbol=key,
                        open=state.open,
                        high=state.high,
                        low=state.low,
                        close=state.close,
                        volume=state.volume,
                        n_ticks=state.n_ticks,
                    )
                )
            self._state[key] = BarState(
                start=bucket,
                open=tick.last or tick.bid or tick.ask,
                high=tick.last or tick.bid or tick.ask,
                low=tick.last or tick.bid or tick.ask,
                close=tick.last or tick.bid or tick.ask,
                volume=tick.size or 0.0,
                n_ticks=1,
            )
            return completed

        # update existing bar
        px = tick.last or tick.bid or tick.ask
        if px is None:
            return completed
        state.open = state.open if state.n_ticks > 0 else px
        state.high = max(state.high, px)
        state.low = min(state.low, px)
        state.close = px
        state.volume += tick.size or 0.0
        state.n_ticks += 1
        return completed

    def flush(self, force: bool = False) -> List[Bar]:
        if not force:
            return []
        completed = []
        for key, state in list(self._state.items()):
            completed.append(
                Bar(
                    ts=state.start,
                    symbol=key,
                    open=state.open,
                    high=state.high,
                    low=state.low,
                    close=state.close,
                    volume=state.volume,
                    n_ticks=state.n_ticks,
                )
            )
            self._state.pop(key, None)
        return completed
