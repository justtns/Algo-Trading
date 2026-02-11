"""Data quality utilities: gap detection and stale feed alerting."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class GapInfo:
    symbol: str
    expected_ts: pd.Timestamp
    actual_ts: pd.Timestamp
    gap_seconds: float


@dataclass
class StaleDataAlert:
    symbol: str
    last_ts: pd.Timestamp
    staleness_seconds: float


def detect_gaps(
    df: pd.DataFrame,
    expected_freq: str = "1min",
    tolerance_factor: float = 1.5,
    symbol: str = "unknown",
) -> list[GapInfo]:
    """
    Detect gaps in a bar DataFrame (datetime index).

    A gap is any interval > tolerance_factor * expected_freq.
    Weekend gaps (Friday→Sunday/Monday) are excluded.
    """
    if df.empty or len(df) < 2:
        return []

    expected_delta = pd.tseries.frequencies.to_offset(expected_freq)
    threshold = expected_delta * tolerance_factor

    gaps: list[GapInfo] = []
    diffs = df.index.to_series().diff()

    for i in range(1, len(diffs)):
        delta = diffs.iloc[i]
        if pd.isna(delta):
            continue
        if delta <= threshold:
            continue

        prev_ts = df.index[i - 1]
        curr_ts = df.index[i]

        # Skip weekend gaps (Friday→Sunday/Monday)
        if _is_weekend_gap(prev_ts, curr_ts):
            continue

        gaps.append(
            GapInfo(
                symbol=symbol,
                expected_ts=prev_ts + expected_delta,
                actual_ts=curr_ts,
                gap_seconds=delta.total_seconds(),
            )
        )

    return gaps


def _is_weekend_gap(start: pd.Timestamp, end: pd.Timestamp) -> bool:
    """True if the gap spans a weekend (Friday close → Sunday/Monday open)."""
    # Friday = 4, Saturday = 5, Sunday = 6
    return start.dayofweek == 4 and end.dayofweek in (0, 6)


def check_stale(
    last_timestamps: dict[str, pd.Timestamp],
    threshold_seconds: float = 300,
    on_stale: Optional[Callable[[StaleDataAlert], None]] = None,
) -> list[StaleDataAlert]:
    """
    Check if any symbol's last update is older than threshold.

    Parameters
    ----------
    last_timestamps : dict
        Mapping of symbol to its most recent bar/tick timestamp.
    threshold_seconds : float
        Staleness threshold in seconds (default 5 minutes).
    on_stale : callable, optional
        Called for each stale symbol with a StaleDataAlert.
    """
    now = pd.Timestamp.now(tz="UTC")
    alerts: list[StaleDataAlert] = []

    for symbol, last_ts in last_timestamps.items():
        delta = (now - last_ts).total_seconds()
        if delta > threshold_seconds:
            alert = StaleDataAlert(
                symbol=symbol, last_ts=last_ts, staleness_seconds=delta
            )
            alerts.append(alert)
            if on_stale:
                on_stale(alert)
            else:
                logger.warning(
                    "Stale data for %s: last update %.0fs ago", symbol, delta
                )

    return alerts
