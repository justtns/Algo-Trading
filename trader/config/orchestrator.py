"""
YAML-driven orchestrator: loads portfolio config, allocates capital,
builds strategies with correct trade sizes, and wires venues.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

import yaml

from trader.capital.allocator import (
    CapitalAllocator,
    StrategyAllocation,
    StrategyAllocationSpec,
)
from trader.core.enums import InstrumentClass

# Strategy class registry — maps YAML string names to (strategy_class, config_class)
_STRATEGY_REGISTRY: Dict[str, tuple[type, type]] = {}


def _ensure_registry() -> None:
    """Lazily populate the strategy registry from trader.strategy modules."""
    if _STRATEGY_REGISTRY:
        return
    from trader.strategy.gotobi import (
        GotobiConfig,
        GotobiStrategy,
        GotobiWithSLConfig,
        GotobiWithSLStrategy,
    )
    from trader.strategy.breakout import BreakoutConfig, BreakoutStrategy
    from trader.strategy.mean_reversion import MeanReversionConfig, MeanReversionStrategy
    from trader.strategy.buy_and_hold import (
        OneMinuteBuyHoldConfig,
        OneMinuteBuyHoldStrategy,
    )

    _STRATEGY_REGISTRY.update(
        {
            "GotobiStrategy": (GotobiStrategy, GotobiConfig),
            "GotobiWithSLStrategy": (GotobiWithSLStrategy, GotobiWithSLConfig),
            "BreakoutStrategy": (BreakoutStrategy, BreakoutConfig),
            "MeanReversionStrategy": (MeanReversionStrategy, MeanReversionConfig),
            "OneMinuteBuyHoldStrategy": (OneMinuteBuyHoldStrategy, OneMinuteBuyHoldConfig),
        }
    )


@dataclass
class StrategySpec:
    """Full specification for one strategy in the orchestrator."""

    strategy_class: type
    config_class: type
    config_kwargs: Dict[str, Any]
    allocation_spec: StrategyAllocationSpec


class TradingOrchestrator:
    """
    Orchestrates capital allocation and strategy construction.

    Usage via Python API::

        orch = TradingOrchestrator(total_capital=500_000)
        orch.add_strategy(spec)
        allocations = orch.allocate()
        strategies = orch.build_strategies()

    Usage via YAML::

        orch = TradingOrchestrator.from_yaml("config/portfolio.yaml")
        allocations = orch.allocate()
        strategies = orch.build_strategies()
    """

    def __init__(
        self,
        total_capital: float,
        db_path: str | Path | None = None,
    ):
        self.total_capital = total_capital
        self._specs: List[StrategySpec] = []
        self._allocations: List[StrategyAllocation] | None = None
        self.db: Database | None = None
        if db_path is not None:
            from trader.persistence.database import Database

            self.db = Database(db_path)

    def add_strategy(self, spec: StrategySpec) -> None:
        self._specs.append(spec)

    @property
    def specs(self) -> List[StrategySpec]:
        return list(self._specs)

    def allocate(self) -> List[StrategyAllocation]:
        """Run the capital allocator and return per-strategy allocations."""
        allocator = CapitalAllocator(self.total_capital)
        alloc_specs = [s.allocation_spec for s in self._specs]
        self._allocations = allocator.allocate(alloc_specs)
        allocator.validate(self._allocations)
        return self._allocations

    @property
    def allocations(self) -> List[StrategyAllocation] | None:
        return self._allocations

    def build_strategies(self) -> List:
        """
        Instantiate strategies with allocated trade_size injected into config.

        Returns list of NautilusTrader Strategy instances.
        """
        if self._allocations is None:
            self.allocate()

        strategies = []
        for spec, alloc in zip(self._specs, self._allocations):
            kwargs = dict(spec.config_kwargs)
            kwargs["trade_size"] = alloc.trade_size
            kwargs.pop("contract_size", None)
            config = spec.config_class(**kwargs)
            strategies.append(spec.strategy_class(config=config))
        return strategies

    @classmethod
    def from_yaml(
        cls,
        portfolio_path: str | Path,
        accounts_path: str | Path | None = None,
        db_path: str | Path | None = None,
    ) -> TradingOrchestrator:
        """
        Load orchestrator from a YAML portfolio config file.

        Parameters
        ----------
        portfolio_path : str or Path
            Path to portfolio.yaml defining strategies, weights, and venues.
        accounts_path : str or Path or None
            Optional path to accounts.yaml with broker credentials.
            Stored on the orchestrator for use by node builders.
        db_path : str or Path or None
            Optional path to SQLite database for persistence.
        """
        _ensure_registry()

        path = Path(portfolio_path)
        if not path.exists():
            raise FileNotFoundError(f"Portfolio config not found: {path}")

        data = yaml.safe_load(path.read_text())
        total_capital = float(data["total_capital"])
        orch = cls(total_capital=total_capital, db_path=db_path)

        # Load account credentials if provided
        orch.account_credentials: Dict[str, Dict[str, Any]] = {}
        if accounts_path is not None:
            acc_path = Path(accounts_path)
            if acc_path.exists():
                acc_data = yaml.safe_load(acc_path.read_text())
                orch.account_credentials = acc_data.get("venues", {})

        for entry in data.get("strategies", []):
            strategy_name = entry["name"]
            strategy_str = entry["strategy"]

            if strategy_str not in _STRATEGY_REGISTRY:
                raise ValueError(
                    f"Unknown strategy '{strategy_str}'. "
                    f"Available: {list(_STRATEGY_REGISTRY.keys())}"
                )

            strategy_cls, config_cls = _STRATEGY_REGISTRY[strategy_str]

            instrument_class_str = entry.get("instrument_class", "margin_based")
            instrument_class = InstrumentClass(instrument_class_str)

            alloc_spec = StrategyAllocationSpec(
                strategy_name=strategy_name,
                instrument_class=instrument_class,
                weight=float(entry.get("weight", 1.0)),
                venue_name=entry.get("venue", "SIM"),
                margin_rate=float(entry.get("margin_rate", 0.02)),
                safety_factor=float(entry.get("safety_factor", 1.5)),
                contract_size=float(
                    entry.get(
                        "contract_size",
                        entry.get("config", {}).get("contract_size", 100_000),
                    )
                ),
                reference_price=entry.get("reference_price"),
            )

            config_kwargs = dict(entry.get("config", {}))
            # Backwards-compat: drop contract_size now that strategies derive lot size from instruments.
            config_kwargs.pop("contract_size", None)

            spec = StrategySpec(
                strategy_class=strategy_cls,
                config_class=config_cls,
                config_kwargs=config_kwargs,
                allocation_spec=alloc_spec,
            )
            orch.add_strategy(spec)

        return orch
