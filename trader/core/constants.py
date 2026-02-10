"""
Shared constants for venues, currencies, and default configuration values.
"""
from __future__ import annotations

from nautilus_trader.model.identifiers import Venue

MT5 = Venue("MT5")
IDEALPRO = Venue("IDEALPRO")
SIM = Venue("SIM")

DEFAULT_GOTOBI_DAYS = frozenset({5, 10, 15, 20, 25, 30})
