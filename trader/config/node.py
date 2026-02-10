"""
NautilusTrader node builders for backtest and live trading.
Replaces the Backtrader Cerebro-based TradeRunner orchestration.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Sequence

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.currencies import Currency
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Money
from nautilus_trader.trading.strategy import Strategy


def build_backtest_engine(
    instruments: Sequence[Instrument],
    bars: Dict[BarType, List[Bar]],
    strategies: Sequence[Strategy],
    *,
    venue: Venue | None = None,
    venue_currency: str = "USD",
    starting_balance: float = 100_000,
    account_type: AccountType = AccountType.MARGIN,
    oms_type: OmsType = OmsType.HEDGING,
    leverage: float = 50.0,
    config: BacktestEngineConfig | None = None,
) -> BacktestEngine:
    """
    Build a BacktestEngine with venue, instruments, data, and strategies wired.

    Parameters
    ----------
    instruments : list of Instrument
        Instruments to register.
    bars : dict mapping BarType to list of Bar
        Historical bar data keyed by BarType.
    strategies : list of Strategy
        Strategies to add.
    venue : Venue or None
        Venue for the simulated exchange. If None, inferred from first instrument.
    venue_currency : str
        Account currency for the venue.
    starting_balance : float
        Starting cash balance.
    account_type : AccountType
        Margin or cash account.
    oms_type : OmsType
        Order management system type.
    leverage : float
        Default leverage for the venue.
    config : BacktestEngineConfig or None
        Custom engine configuration.
    """
    engine = BacktestEngine(config=config or BacktestEngineConfig())

    # Determine venue from instruments if not provided
    if venue is None and instruments:
        venue = instruments[0].id.venue

    # Add simulated venue
    engine.add_venue(
        venue=venue,
        oms_type=oms_type,
        account_type=account_type,
        starting_balances=[Money(starting_balance, Currency.from_str(venue_currency))],
        default_leverage=Decimal(str(leverage)),
    )

    # Add instruments
    for instrument in instruments:
        engine.add_instrument(instrument)

    # Add bar data
    for bar_type, bar_list in bars.items():
        engine.add_data(bar_list)

    # Add strategies
    for strategy in strategies:
        engine.add_strategy(strategy)

    return engine
