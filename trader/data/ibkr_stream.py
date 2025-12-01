"""
Thin wrappers around IBKR historical fetch utilities.
"""
from __future__ import annotations

from historical_data_services.ibkr_data_fetch import fetch_ibkr_bars, fetch_ibkr_bars_range_fx

__all__ = ["fetch_ibkr_bars", "fetch_ibkr_bars_range_fx"]
