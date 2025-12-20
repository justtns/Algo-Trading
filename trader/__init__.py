"""
Primary package entrypoint for the trading system.
Exposes data pipeline helpers, TradeRunner, routing, and portfolio store.
"""

from trader.data.pipeline import DataHandler, DataNormalizer, DataStreamer, StreamingOHLCVFeed, DataPackage
from trader.data.metatrader_stream import MetaTraderLiveStreamer, stream_metatrader_ticks
from trader.exec.traderunner import (
    TradeRunner,
    TradeRunnerBuilder,
    TradeRunnerPool,
    RiskEstimator,
    StrategySpec,
    RunnerConfig,
)
from trader.exec.router import OrderRouter
from trader.portfolio.store import TickerStore

__all__ = [
    "DataHandler",
    "DataNormalizer",
    "DataStreamer",
    "StreamingOHLCVFeed",
    "DataPackage",
    "MetaTraderLiveStreamer",
    "stream_metatrader_ticks",
    "TradeRunner",
    "TradeRunnerBuilder",
    "TradeRunnerPool",
    "RiskEstimator",
    "StrategySpec",
    "RunnerConfig",
    "OrderRouter",
    "TickerStore",
]
