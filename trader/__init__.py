"""
NautilusTrader-based algorithmic trading system.

Provides strategies, broker adapters (MetaTrader 5, IBKR), data pipeline
utilities, and backtest/live node builders.
"""

from trader.data.pipeline import DataHandler, DataNormalizer, DataPackage
from trader.data.catalog import dataframe_to_nautilus_bars, load_parquet_to_bars, invert_ohlc
from trader.core.instruments import make_fx_pair, load_fx_instruments
from trader.core.constants import MT5, IDEALPRO, SIM
from trader.config.node import build_backtest_engine
from trader.exec.risk import RiskEstimator, RiskManager, RiskLimits
from trader.portfolio.store import TickerStore
from trader.strategy.gotobi import GotobiStrategy, GotobiConfig, GotobiWithSLStrategy, GotobiWithSLConfig
from trader.strategy.mean_reversion import MeanReversionStrategy, MeanReversionConfig
from trader.strategy.breakout import BreakoutStrategy, BreakoutConfig
from trader.strategy.rsi_macd_ma import RsiMacdMaStrategy, RsiMacdMaConfig
from trader.strategy.common import GotobiCalendar

__all__ = [
    # Data
    "DataHandler",
    "DataNormalizer",
    "DataPackage",
    "dataframe_to_nautilus_bars",
    "load_parquet_to_bars",
    "invert_ohlc",
    # Instruments
    "make_fx_pair",
    "load_fx_instruments",
    # Venues
    "MT5",
    "IDEALPRO",
    "SIM",
    # Engine
    "build_backtest_engine",
    # Risk
    "RiskEstimator",
    "RiskManager",
    "RiskLimits",
    # Portfolio
    "TickerStore",
    # Strategies
    "GotobiStrategy",
    "GotobiConfig",
    "GotobiWithSLStrategy",
    "GotobiWithSLConfig",
    "MeanReversionStrategy",
    "MeanReversionConfig",
    "BreakoutStrategy",
    "BreakoutConfig",
    "RsiMacdMaStrategy",
    "RsiMacdMaConfig",
    "GotobiCalendar",
]
