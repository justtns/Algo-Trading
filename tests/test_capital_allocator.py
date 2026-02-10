import math

import pytest

from trader.core.enums import InstrumentClass
from trader.capital.allocator import (
    CapitalAllocator,
    RiskParityAllocator,
    StrategyAllocation,
    StrategyAllocationSpec,
)


# ---------------------------------------------------------------------------
# CapitalAllocator basics
# ---------------------------------------------------------------------------


def test_single_margin_based_allocation():
    allocator = CapitalAllocator(total_capital=100_000)
    specs = [
        StrategyAllocationSpec(
            strategy_name="gotobi",
            instrument_class=InstrumentClass.MARGIN_BASED,
            weight=1.0,
            margin_rate=0.02,
            safety_factor=1.5,
            contract_size=100_000,
        ),
    ]
    results = allocator.allocate(specs)
    assert len(results) == 1
    alloc = results[0]
    assert alloc.allocated_capital == pytest.approx(100_000)
    # trade_size = 100000 / (0.02 * 100000 * 1.5) = 100000 / 3000 = 33.33
    assert alloc.trade_size == pytest.approx(100_000 / 3_000)


def test_single_capital_based_allocation():
    allocator = CapitalAllocator(total_capital=150_000)
    specs = [
        StrategyAllocationSpec(
            strategy_name="equity_mr",
            instrument_class=InstrumentClass.CAPITAL_BASED,
            weight=1.0,
            reference_price=150.0,
            contract_size=1,
        ),
    ]
    results = allocator.allocate(specs)
    assert len(results) == 1
    alloc = results[0]
    assert alloc.allocated_capital == pytest.approx(150_000)
    # trade_size = floor(150000 / 150.0) = 1000 shares
    assert alloc.trade_size == 1000


def test_mixed_allocation():
    allocator = CapitalAllocator(total_capital=500_000)
    specs = [
        StrategyAllocationSpec(
            strategy_name="fx_gotobi",
            instrument_class=InstrumentClass.MARGIN_BASED,
            weight=0.6,
            margin_rate=0.02,
            safety_factor=1.5,
            contract_size=100_000,
        ),
        StrategyAllocationSpec(
            strategy_name="equity_mr",
            instrument_class=InstrumentClass.CAPITAL_BASED,
            weight=0.4,
            reference_price=200.0,
            contract_size=1,
        ),
    ]
    results = allocator.allocate(specs)
    assert len(results) == 2

    fx = results[0]
    eq = results[1]

    assert fx.allocated_capital == pytest.approx(300_000)
    assert eq.allocated_capital == pytest.approx(200_000)

    # FX: 300000 / (0.02 * 100000 * 1.5) = 100 lots
    assert fx.trade_size == pytest.approx(100.0)
    # Equity: floor(200000 / 200) = 1000 shares
    assert eq.trade_size == 1000


def test_proportional_weights():
    """Weights are relative, not absolute percentages."""
    allocator = CapitalAllocator(total_capital=100_000)
    specs = [
        StrategyAllocationSpec(
            strategy_name="a",
            instrument_class=InstrumentClass.MARGIN_BASED,
            weight=3.0,
            margin_rate=0.02,
            safety_factor=1.0,
            contract_size=100_000,
        ),
        StrategyAllocationSpec(
            strategy_name="b",
            instrument_class=InstrumentClass.MARGIN_BASED,
            weight=1.0,
            margin_rate=0.02,
            safety_factor=1.0,
            contract_size=100_000,
        ),
    ]
    results = allocator.allocate(specs)
    assert results[0].allocated_capital == pytest.approx(75_000)
    assert results[1].allocated_capital == pytest.approx(25_000)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_specs():
    allocator = CapitalAllocator(total_capital=100_000)
    assert allocator.allocate([]) == []


def test_zero_total_weight_raises():
    allocator = CapitalAllocator(total_capital=100_000)
    specs = [
        StrategyAllocationSpec(
            strategy_name="x",
            instrument_class=InstrumentClass.MARGIN_BASED,
            weight=0.0,
        ),
    ]
    with pytest.raises(ValueError, match="Total weight"):
        allocator.allocate(specs)


def test_negative_total_capital_raises():
    with pytest.raises(ValueError, match="total_capital must be positive"):
        CapitalAllocator(total_capital=-100)


def test_zero_reference_price_returns_zero_trade_size():
    allocator = CapitalAllocator(total_capital=100_000)
    specs = [
        StrategyAllocationSpec(
            strategy_name="eq",
            instrument_class=InstrumentClass.CAPITAL_BASED,
            weight=1.0,
            reference_price=0.0,
        ),
    ]
    results = allocator.allocate(specs)
    assert results[0].trade_size == 0.0


def test_none_reference_price_returns_zero_trade_size():
    allocator = CapitalAllocator(total_capital=100_000)
    specs = [
        StrategyAllocationSpec(
            strategy_name="eq",
            instrument_class=InstrumentClass.CAPITAL_BASED,
            weight=1.0,
            reference_price=None,
        ),
    ]
    results = allocator.allocate(specs)
    assert results[0].trade_size == 0.0


def test_zero_margin_rate_returns_zero_trade_size():
    allocator = CapitalAllocator(total_capital=100_000)
    specs = [
        StrategyAllocationSpec(
            strategy_name="fx",
            instrument_class=InstrumentClass.MARGIN_BASED,
            weight=1.0,
            margin_rate=0.0,
        ),
    ]
    results = allocator.allocate(specs)
    assert results[0].trade_size == 0.0


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_passes_for_valid_allocation():
    allocator = CapitalAllocator(total_capital=100_000)
    allocations = [
        StrategyAllocation("a", 60_000, 10.0, InstrumentClass.MARGIN_BASED, "SIM"),
        StrategyAllocation("b", 40_000, 200, InstrumentClass.CAPITAL_BASED, "SIM"),
    ]
    allocator.validate(allocations)  # should not raise


def test_validate_raises_when_over_allocated():
    allocator = CapitalAllocator(total_capital=100_000)
    allocations = [
        StrategyAllocation("a", 80_000, 10.0, InstrumentClass.MARGIN_BASED, "SIM"),
        StrategyAllocation("b", 30_000, 200, InstrumentClass.CAPITAL_BASED, "SIM"),
    ]
    with pytest.raises(ValueError, match="exceeds total capital"):
        allocator.validate(allocations)


# ---------------------------------------------------------------------------
# RiskParityAllocator
# ---------------------------------------------------------------------------


def test_risk_parity_equal_volatility():
    """Equal volatilities should produce equal weights."""
    allocator = RiskParityAllocator(total_capital=100_000)
    specs = [
        StrategyAllocationSpec(
            strategy_name="a",
            instrument_class=InstrumentClass.MARGIN_BASED,
            weight=999,  # ignored by risk parity
            margin_rate=0.02,
            safety_factor=1.0,
            contract_size=100_000,
        ),
        StrategyAllocationSpec(
            strategy_name="b",
            instrument_class=InstrumentClass.MARGIN_BASED,
            weight=1,  # ignored
            margin_rate=0.02,
            safety_factor=1.0,
            contract_size=100_000,
        ),
    ]
    vols = {"a": 0.15, "b": 0.15}
    results = allocator.allocate_risk_parity(specs, vols)
    assert results[0].allocated_capital == pytest.approx(50_000)
    assert results[1].allocated_capital == pytest.approx(50_000)


def test_risk_parity_inverse_volatility():
    """Lower vol strategy gets more capital."""
    allocator = RiskParityAllocator(total_capital=100_000)
    specs = [
        StrategyAllocationSpec(
            strategy_name="low_vol",
            instrument_class=InstrumentClass.MARGIN_BASED,
            margin_rate=0.02,
            safety_factor=1.0,
            contract_size=100_000,
        ),
        StrategyAllocationSpec(
            strategy_name="high_vol",
            instrument_class=InstrumentClass.MARGIN_BASED,
            margin_rate=0.02,
            safety_factor=1.0,
            contract_size=100_000,
        ),
    ]
    vols = {"low_vol": 0.10, "high_vol": 0.30}
    results = allocator.allocate_risk_parity(specs, vols)
    # inv(0.10) = 10, inv(0.30) = 3.33, total = 13.33
    # low_vol weight = 10/13.33 = 0.75
    assert results[0].allocated_capital > results[1].allocated_capital
    assert results[0].allocated_capital == pytest.approx(75_000)
    assert results[1].allocated_capital == pytest.approx(25_000)


def test_risk_parity_missing_volatility_raises():
    allocator = RiskParityAllocator(total_capital=100_000)
    specs = [
        StrategyAllocationSpec(strategy_name="a", instrument_class=InstrumentClass.MARGIN_BASED),
    ]
    with pytest.raises(ValueError, match="Volatility"):
        allocator.allocate_risk_parity(specs, {})


def test_risk_parity_zero_volatility_raises():
    allocator = RiskParityAllocator(total_capital=100_000)
    specs = [
        StrategyAllocationSpec(strategy_name="a", instrument_class=InstrumentClass.MARGIN_BASED),
    ]
    with pytest.raises(ValueError, match="Volatility"):
        allocator.allocate_risk_parity(specs, {"a": 0.0})
