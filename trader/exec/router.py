from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .traderunner import RiskEstimator


@dataclass
class OrderRequest:
    symbol: str
    side: str                          # "BUY" or "SELL"
    size: float
    order_type: str = "market"
    price: float | None = None
    time_in_force: str | None = None
    strategy_id: str | None = None


class OrderRouter:
    """
    Minimal order router. Delegates to a broker client callable.
    """

    def __init__(
        self,
        broker_sender: Callable[[OrderRequest], Any],
        *,
        risk: Optional[RiskEstimator] = None,
    ):
        self.broker_sender = broker_sender
        self.risk = risk or RiskEstimator()

    def send(self, req: OrderRequest, *, last_price: float | None = None) -> Any:
        """
        Run risk checks then forward the order to the broker layer.
        """
        px = req.price or (last_price if last_price is not None else 0.0)
        self.risk.validate(price=px, size=req.size, cash=req.size * px if px else None)
        return self.broker_sender(req, last_price=last_price)

