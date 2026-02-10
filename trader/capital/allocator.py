"""
Capital allocator: distributes total capital to strategies based on
instrument class (margin-based vs capital-based).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Sequence

from trader.core.enums import InstrumentClass


@dataclass(frozen=True)
class StrategyAllocationSpec:
    """
    Declares how much capital a strategy needs.

    Parameters
    ----------
    strategy_name : str
        Unique name matching the strategy_id tag.
    instrument_class : InstrumentClass
        MARGIN_BASED or CAPITAL_BASED.
    weight : float
        Relative weight for proportional allocation (e.g., 0.3 = 30%).
    venue_name : str
        Which venue this strategy routes orders to.
    margin_rate : float
        For MARGIN_BASED: fraction of notional required as margin (e.g., 0.02 = 2%).
        Ignored for CAPITAL_BASED.
    safety_factor : float
        Multiplier on margin requirement to provide buffer.
    contract_size : float
        Lot/contract size for the instrument (e.g., 100_000 for FX).
    reference_price : float or None
        Current price of the instrument. Required for CAPITAL_BASED.
    """

    strategy_name: str
    instrument_class: InstrumentClass
    weight: float = 1.0
    venue_name: str = "SIM"
    margin_rate: float = 0.02
    safety_factor: float = 1.5
    contract_size: float = 100_000
    reference_price: float | None = None


@dataclass
class StrategyAllocation:
    """Result of allocation: how much capital and trade size a strategy gets."""

    strategy_name: str
    allocated_capital: float
    trade_size: float  # lots for margin-based, shares for capital-based
    instrument_class: InstrumentClass
    venue_name: str


class CapitalAllocator:
    """
    Distributes total_capital across strategies.

    Two modes based on instrument class:
    - MARGIN_BASED:  trade_size (lots) = allocated / (margin_rate * contract_size * safety_factor)
    - CAPITAL_BASED: trade_size (shares) = allocated / reference_price
    """

    def __init__(self, total_capital: float):
        if total_capital <= 0:
            raise ValueError("total_capital must be positive")
        self.total_capital = total_capital

    def allocate(
        self,
        specs: Sequence[StrategyAllocationSpec],
    ) -> List[StrategyAllocation]:
        """
        Allocate capital proportionally by weight, then compute trade_size
        from allocated capital using the instrument class formula.
        """
        if not specs:
            return []

        total_weight = sum(s.weight for s in specs)
        if total_weight <= 0:
            raise ValueError("Total weight must be positive")

        results: List[StrategyAllocation] = []
        for spec in specs:
            allocated = self.total_capital * (spec.weight / total_weight)
            trade_size = self._compute_trade_size(spec, allocated)
            results.append(
                StrategyAllocation(
                    strategy_name=spec.strategy_name,
                    allocated_capital=allocated,
                    trade_size=trade_size,
                    instrument_class=spec.instrument_class,
                    venue_name=spec.venue_name,
                )
            )
        return results

    def _compute_trade_size(
        self, spec: StrategyAllocationSpec, allocated: float
    ) -> float:
        if spec.instrument_class == InstrumentClass.MARGIN_BASED:
            margin_per_lot = spec.margin_rate * spec.contract_size * spec.safety_factor
            if margin_per_lot <= 0:
                return 0.0
            return allocated / margin_per_lot
        else:  # CAPITAL_BASED
            if spec.reference_price is None or spec.reference_price <= 0:
                return 0.0
            return math.floor(allocated / spec.reference_price)

    def validate(self, allocations: List[StrategyAllocation]) -> None:
        """Raise if total allocated exceeds total capital."""
        total_used = sum(a.allocated_capital for a in allocations)
        if total_used > self.total_capital * 1.001:  # 0.1% tolerance
            raise ValueError(
                f"Allocated {total_used:.2f} exceeds total capital {self.total_capital:.2f}"
            )


class RiskParityAllocator(CapitalAllocator):
    """
    Allocates capital inversely proportional to volatility so each
    strategy contributes roughly equal risk.

    Usage:
        allocator = RiskParityAllocator(total_capital=500_000)
        vols = {"gotobi": 0.12, "breakout": 0.25, "mean_rev": 0.08}
        allocations = allocator.allocate_risk_parity(specs, vols)
    """

    def allocate_risk_parity(
        self,
        specs: Sequence[StrategyAllocationSpec],
        volatilities: Dict[str, float],
    ) -> List[StrategyAllocation]:
        """
        Compute inverse-volatility weights and allocate.

        Parameters
        ----------
        specs : list of StrategyAllocationSpec
            The weight field on each spec is ignored; weights are computed
            from inverse volatilities.
        volatilities : dict
            Maps strategy_name -> annualized volatility estimate.
        """
        if not specs:
            return []

        inv_vols: List[float] = []
        for spec in specs:
            vol = volatilities.get(spec.strategy_name)
            if vol is None or vol <= 0:
                raise ValueError(
                    f"Volatility for '{spec.strategy_name}' must be positive, got {vol}"
                )
            inv_vols.append(1.0 / vol)

        total_inv = sum(inv_vols)
        reweighted = []
        for spec, inv_v in zip(specs, inv_vols):
            new_spec = StrategyAllocationSpec(
                strategy_name=spec.strategy_name,
                instrument_class=spec.instrument_class,
                weight=inv_v / total_inv,
                venue_name=spec.venue_name,
                margin_rate=spec.margin_rate,
                safety_factor=spec.safety_factor,
                contract_size=spec.contract_size,
                reference_price=spec.reference_price,
            )
            reweighted.append(new_spec)

        return self.allocate(reweighted)
