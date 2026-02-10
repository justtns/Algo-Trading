"""Tests for the YAML-driven TradingOrchestrator."""
import textwrap
from pathlib import Path

import pytest

from trader.core.enums import InstrumentClass
from trader.capital.allocator import StrategyAllocationSpec
from trader.config.orchestrator import TradingOrchestrator, StrategySpec


# ---------------------------------------------------------------------------
# Python API tests
# ---------------------------------------------------------------------------


def test_orchestrator_allocate_and_build():
    from trader.strategy.gotobi import GotobiStrategy, GotobiConfig
    from trader.strategy.breakout import BreakoutStrategy, BreakoutConfig

    orch = TradingOrchestrator(total_capital=100_000)

    orch.add_strategy(
        StrategySpec(
            strategy_class=GotobiStrategy,
            config_class=GotobiConfig,
            config_kwargs={
                "instrument_id": "USD/JPY.SIM",
                "bar_type": "USD/JPY.SIM-1-MINUTE-MID-EXTERNAL",
                "contract_size": 100_000,
            },
            allocation_spec=StrategyAllocationSpec(
                strategy_name="gotobi",
                instrument_class=InstrumentClass.MARGIN_BASED,
                weight=0.6,
                margin_rate=0.02,
                safety_factor=1.5,
                contract_size=100_000,
            ),
        )
    )
    orch.add_strategy(
        StrategySpec(
            strategy_class=BreakoutStrategy,
            config_class=BreakoutConfig,
            config_kwargs={
                "instrument_id": "EUR/USD.SIM",
                "bar_type": "EUR/USD.SIM-1-MINUTE-MID-EXTERNAL",
                "contract_size": 100_000,
            },
            allocation_spec=StrategyAllocationSpec(
                strategy_name="breakout",
                instrument_class=InstrumentClass.MARGIN_BASED,
                weight=0.4,
                margin_rate=0.02,
                safety_factor=1.5,
                contract_size=100_000,
            ),
        )
    )

    allocations = orch.allocate()
    assert len(allocations) == 2
    assert allocations[0].allocated_capital == pytest.approx(60_000)
    assert allocations[1].allocated_capital == pytest.approx(40_000)

    strategies = orch.build_strategies()
    assert len(strategies) == 2
    # trade_size should be injected from allocation
    assert strategies[0].trade_qty > 0
    assert strategies[1].trade_qty > 0


# ---------------------------------------------------------------------------
# YAML loading tests
# ---------------------------------------------------------------------------


def test_from_yaml_loads_strategies(tmp_path):
    portfolio_yaml = tmp_path / "portfolio.yaml"
    portfolio_yaml.write_text(
        textwrap.dedent(
            """\
            total_capital: 200000
            strategies:
              - name: gotobi_test
                strategy: GotobiStrategy
                venue: SIM
                instrument_class: margin_based
                weight: 0.5
                margin_rate: 0.02
                safety_factor: 1.5
                config:
                  instrument_id: "USD/JPY.SIM"
                  bar_type: "USD/JPY.SIM-1-MINUTE-MID-EXTERNAL"
                  contract_size: 100000

              - name: breakout_test
                strategy: BreakoutStrategy
                venue: SIM
                instrument_class: margin_based
                weight: 0.5
                margin_rate: 0.02
                config:
                  instrument_id: "EUR/USD.SIM"
                  bar_type: "EUR/USD.SIM-1-MINUTE-MID-EXTERNAL"
                  contract_size: 100000
            """
        )
    )

    orch = TradingOrchestrator.from_yaml(portfolio_yaml)
    assert orch.total_capital == 200_000
    assert len(orch.specs) == 2

    allocations = orch.allocate()
    assert len(allocations) == 2
    assert allocations[0].allocated_capital == pytest.approx(100_000)
    assert allocations[1].allocated_capital == pytest.approx(100_000)

    strategies = orch.build_strategies()
    assert len(strategies) == 2


def test_from_yaml_with_accounts(tmp_path):
    portfolio_yaml = tmp_path / "portfolio.yaml"
    portfolio_yaml.write_text(
        textwrap.dedent(
            """\
            total_capital: 100000
            strategies:
              - name: test_strat
                strategy: GotobiStrategy
                venue: MT5
                instrument_class: margin_based
                weight: 1.0
                config:
                  instrument_id: "USD/JPY.MT5"
                  bar_type: "USD/JPY.MT5-1-MINUTE-MID-EXTERNAL"
                  contract_size: 100000
            """
        )
    )
    accounts_yaml = tmp_path / "accounts.yaml"
    accounts_yaml.write_text(
        textwrap.dedent(
            """\
            venues:
              MT5:
                mt5_login: 12345678
                mt5_password: "secret"
            """
        )
    )

    orch = TradingOrchestrator.from_yaml(portfolio_yaml, accounts_yaml)
    assert orch.account_credentials["MT5"]["mt5_login"] == 12345678


def test_from_yaml_unknown_strategy_raises(tmp_path):
    portfolio_yaml = tmp_path / "portfolio.yaml"
    portfolio_yaml.write_text(
        textwrap.dedent(
            """\
            total_capital: 100000
            strategies:
              - name: bad
                strategy: NonExistentStrategy
                venue: SIM
                config:
                  instrument_id: "X.SIM"
                  bar_type: "X.SIM-1-MINUTE-MID-EXTERNAL"
            """
        )
    )
    with pytest.raises(ValueError, match="Unknown strategy"):
        TradingOrchestrator.from_yaml(portfolio_yaml)


def test_from_yaml_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        TradingOrchestrator.from_yaml("/nonexistent/portfolio.yaml")


def test_from_yaml_capital_based_strategy(tmp_path):
    portfolio_yaml = tmp_path / "portfolio.yaml"
    portfolio_yaml.write_text(
        textwrap.dedent(
            """\
            total_capital: 300000
            strategies:
              - name: equity_mr
                strategy: MeanReversionStrategy
                venue: IDEALPRO
                instrument_class: capital_based
                weight: 1.0
                reference_price: 150.0
                config:
                  instrument_id: "AAPL.IDEALPRO"
                  bar_type: "AAPL.IDEALPRO-1-MINUTE-LAST-EXTERNAL"
                  contract_size: 1
            """
        )
    )

    orch = TradingOrchestrator.from_yaml(portfolio_yaml)
    allocations = orch.allocate()
    assert len(allocations) == 1
    assert allocations[0].instrument_class == InstrumentClass.CAPITAL_BASED
    # 300000 / 150 = 2000 shares
    assert allocations[0].trade_size == 2000
