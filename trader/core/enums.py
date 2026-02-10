"""Enums for instrument classification and allocation mode."""
from __future__ import annotations

from enum import Enum


class InstrumentClass(Enum):
    """How capital is allocated for this instrument type."""

    MARGIN_BASED = "margin_based"  # FX, futures, options
    CAPITAL_BASED = "capital_based"  # equities
