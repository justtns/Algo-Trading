"""
Report Generator: orchestrates all 4 analysis components and produces
structured report data ready for Telegram formatting.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from ..data.cache import DataCache, DataRefresher
from ..data.tickers import ALL_FX_PAIRS, G10_PAIRS, EM_ASIA_PAIRS, CROSS_ASSET
from ..analysis.technical_matrix import build_technical_matrix
from ..analysis.event_analysis import build_event_table
from ..analysis.cars import build_cars_report
from ..analysis.timezone import build_timezone_summary, build_timezone_heatmap

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Orchestrates data refresh and report generation."""

    def __init__(self, cache: DataCache, refresher: DataRefresher):
        self._cache = cache
        self._refresher = refresher

    # ------------------------------------------------------------------
    # Data loading helpers
    # ------------------------------------------------------------------

    def _load_all_daily(self) -> dict[str, pd.DataFrame]:
        result = {}
        for pair in ALL_FX_PAIRS:
            df = self._cache.get_daily(pair)
            if df is not None and not df.empty:
                result[pair] = df
            else:
                logger.warning("No daily data for %s", pair)
        return result

    def _load_g10_daily(self) -> dict[str, pd.DataFrame]:
        return {p: df for p, df in self._load_all_daily().items() if p in G10_PAIRS}

    def _load_cross_asset(self, symbol: str) -> pd.DataFrame | None:
        return self._cache.get_cross_asset(symbol)

    def _load_all_hourly(self) -> dict[str, pd.DataFrame]:
        result = {}
        for pair in ALL_FX_PAIRS:
            df = self._cache.get_hourly(pair)
            if df is not None and not df.empty:
                result[pair] = df
        return result

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh_data(self, include_hourly: bool = True) -> None:
        """Incremental data refresh from Polygon."""
        self._refresher.refresh_daily_fx()
        self._refresher.refresh_cross_asset()
        if include_hourly:
            self._refresher.refresh_hourly_fx()

    # ------------------------------------------------------------------
    # Report builders
    # ------------------------------------------------------------------

    def generate_technical_matrix(self) -> pd.DataFrame:
        data = self._load_all_daily()
        return build_technical_matrix(data)

    def generate_event_table(self) -> pd.DataFrame:
        data = self._load_all_daily()
        vix = self._load_cross_asset(CROSS_ASSET["vix"])
        return build_event_table(data, vix)

    def generate_cars(self) -> pd.DataFrame | None:
        fx_data = self._load_g10_daily()
        eq = self._load_cross_asset(CROSS_ASSET["equity"])
        bd = self._load_cross_asset(CROSS_ASSET["bonds"])
        cm = self._load_cross_asset(CROSS_ASSET["commodities"])
        return build_cars_report(fx_data, eq, bd, cm)

    def generate_timezone_summary(self, lookback_days: int = 5) -> pd.DataFrame:
        hourly = self._load_all_hourly()
        return build_timezone_summary(hourly, lookback_days)

    def generate_timezone_heatmap(self, lookback_days: int = 5) -> pd.DataFrame:
        hourly = self._load_all_hourly()
        return build_timezone_heatmap(hourly, lookback_days)

    # ------------------------------------------------------------------
    # Composite reports
    # ------------------------------------------------------------------

    def generate_morning_brief(self) -> dict:
        """
        Full morning brief with all 4 components.

        Returns dict with keys: timestamp, technical_matrix, event_table,
        cars, timezone_summary, timezone_heatmap
        """
        return {
            "timestamp": self._timestamp(),
            "report_type": "Morning FX Brief",
            "technical_matrix": self.generate_technical_matrix(),
            "event_table": self.generate_event_table(),
            "cars": self.generate_cars(),
            "timezone_summary": self.generate_timezone_summary(lookback_days=5),
            "timezone_heatmap": self.generate_timezone_heatmap(lookback_days=5),
        }

    def generate_eod_recap(self) -> dict:
        """End-of-day recap focusing on technicals and event analysis."""
        return {
            "timestamp": self._timestamp(),
            "report_type": "EOD FX Recap",
            "technical_matrix": self.generate_technical_matrix(),
            "event_table": self.generate_event_table(),
            "cars": self.generate_cars(),
            "timezone_summary": self.generate_timezone_summary(lookback_days=1),
            "timezone_heatmap": None,
        }
