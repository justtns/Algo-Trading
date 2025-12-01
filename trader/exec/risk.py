"""
Risk utilities and sizing placeholders.
"""
from __future__ import annotations


class RiskManager:
    def __init__(self, max_leverage: float = 2.0):
        self.max_leverage = max_leverage

    def should_halt(self, pnl_bps: float) -> bool:
        return False
