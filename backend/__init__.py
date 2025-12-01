"""
Lightweight backend scaffolding for running strategies with Backtrader.
Exposes TradeRunner, TradeRunnerPool, and helpers for streaming data.
"""

from .data import DataHandler, DataNormalizer, DataStreamer, StreamingOHLCVFeed
from .traderunner import (
    TradeRunner,
    TradeRunnerBuilder,
    TradeRunnerPool,
    RiskEstimator,
    StrategySpec,
    RunnerConfig,
)
from .router import OrderRouter
from .store import TickerStore

__all__ = [
    "DataHandler",
    "DataNormalizer",
    "DataStreamer",
    "StreamingOHLCVFeed",
    "TradeRunner",
    "TradeRunnerBuilder",
    "TradeRunnerPool",
    "RiskEstimator",
    "StrategySpec",
    "RunnerConfig",
    "OrderRouter",
    "TickerStore",
]
