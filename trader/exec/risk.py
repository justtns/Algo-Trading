"""
Risk utilities and sizing helpers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from trader.core.events import Target, Order


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
