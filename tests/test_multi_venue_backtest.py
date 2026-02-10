"""Integration tests for multi-venue backtest engine builder."""
from decimal import Decimal

import pytest

from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue

from trader.config.node import VenueConfig, build_multi_venue_backtest_engine, StrategyVenueMapping
from trader.core.instruments import make_fx_pair, make_equity


SIM_FX = Venue("SIM_FX")
SIM_EQ = Venue("SIM_EQ")


def test_venue_config_defaults():
    vc = VenueConfig(venue=SIM_FX, starting_balance=100_000)
    assert vc.currency == "USD"
    assert vc.account_type == AccountType.MARGIN
    assert vc.oms_type == OmsType.HEDGING
    assert vc.leverage == 50.0


def test_build_multi_venue_engine_creates_engine():
    """Build engine with two venues, no strategies — verify it doesn't error."""
    venue_configs = [
        VenueConfig(venue=SIM_FX, starting_balance=200_000, currency="USD", leverage=50.0),
        VenueConfig(venue=SIM_EQ, starting_balance=100_000, currency="USD", leverage=1.0),
    ]
    engine = build_multi_venue_backtest_engine(
        venue_configs=venue_configs,
        strategy_mappings=[],
    )
    assert engine is not None


def test_make_equity_creates_valid_instrument():
    eq = make_equity("AAPL", SIM_EQ)
    assert str(eq.id) == "AAPL.SIM_EQ"
    assert eq.price_precision == 2
    assert str(eq.quote_currency) == "USD"


def test_make_equity_with_isin():
    eq = make_equity("AAPL", SIM_EQ, isin="US0378331005")
    assert eq.isin == "US0378331005"
