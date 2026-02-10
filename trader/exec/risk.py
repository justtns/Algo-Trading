"""
Risk utilities and sizing helpers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from trader.core.events import Target, Order


@dataclass
class RiskEstimator:
    """
    Basic risk helper for position sizing and validation.
    """

    max_position: float | None = None
    max_notional: float | None = None
    risk_fraction: float = 0.01
    stop_loss_pct: float | None = None

    def validate(self, price: float, size: float, cash: float | None = None) -> None:
        if self.max_position is not None and abs(size) > self.max_position:
            raise ValueError(f"Size {size} exceeds max_position {self.max_position}")
        if self.max_notional is not None and abs(price * size) > self.max_notional:
            raise ValueError(f"Notional {price * size} exceeds max_notional {self.max_notional}")
        if cash is not None and cash <= 0:
            raise ValueError("Cash must be positive for risk checks")

    def suggested_size(self, price: float, cash: float) -> float:
        if price <= 0:
            return 0.0
        if self.stop_loss_pct and self.stop_loss_pct > 0:
            risk_amt = cash * self.risk_fraction
            per_unit_risk = price * self.stop_loss_pct
            return max(0.0, risk_amt / per_unit_risk)
        return (cash * self.risk_fraction) / price


@dataclass
class RiskLimits:
    max_leverage: float = 5.0
    max_loss_day_bps: Optional[float] = None
    per_symbol_limit: Optional[Dict[str, float]] = None  # notional caps
    lot_size: Optional[Dict[str, float]] = None


class RiskManager:
    def __init__(self, limits: RiskLimits):
        self.limits = limits

    def size_orders(self, equity: float, targets: Iterable[Target], prices: Dict[str, float]) -> List[Order]:
        """
        Convert targets to orders respecting leverage and per-symbol caps.
        """
        orders: List[Order] = []
        for t in targets:
            px = prices.get(t.symbol)
            if px is None or px <= 0:
                continue
            qty = t.target_qty
            if self.limits.lot_size and t.symbol in self.limits.lot_size:
                lot = self.limits.lot_size[t.symbol]
                qty = round(qty / lot) * lot
            notional = abs(qty * px)
            if self.limits.per_symbol_limit:
                cap = self.limits.per_symbol_limit.get(t.symbol)
                if cap and notional > cap:
                    qty = (cap / px) * (1 if qty >= 0 else -1)
            orders.append(
                Order(
                    client_order_id=f"{t.symbol}-{t.tag or 'target'}",
                    symbol=t.symbol,
                    side="BUY" if qty >= 0 else "SELL",
                    qty=abs(qty),
                    order_type="MKT",
                    tag=t.tag,
                )
            )
        # leverage check (simple gross)
        gross = sum(prices.get(o.symbol, 0) * o.qty for o in orders)
        if equity > 0 and self.limits.max_leverage and gross / equity > self.limits.max_leverage:
            scale = (self.limits.max_leverage * equity) / gross
            for o in orders:
                o.qty = o.qty * scale
        return orders

    def should_halt(self, pnl_today_bps: float) -> bool:
        if self.limits.max_loss_day_bps is None:
            return False
        return pnl_today_bps <= -abs(self.limits.max_loss_day_bps)
