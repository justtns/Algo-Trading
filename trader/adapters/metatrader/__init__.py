"""
MetaTrader 5 adapter for NautilusTrader.

Provides a custom LiveDataClient and LiveExecutionClient for connecting
to MetaTrader 5 terminals.
"""
from trader.adapters.metatrader.common import MetaTrader5Config
from trader.adapters.metatrader.data import MetaTrader5DataClient, MetaTrader5DataClientConfig
from trader.adapters.metatrader.execution import MetaTrader5ExecutionClient, MetaTrader5ExecClientConfig
from trader.adapters.metatrader.factories import (
    MetaTrader5LiveDataClientFactory,
    MetaTrader5LiveExecClientFactory,
)
from trader.adapters.metatrader.provider import MetaTrader5InstrumentProvider

__all__ = [
    "MetaTrader5Config",
    "MetaTrader5DataClient",
    "MetaTrader5DataClientConfig",
    "MetaTrader5ExecutionClient",
    "MetaTrader5ExecClientConfig",
    "MetaTrader5LiveDataClientFactory",
    "MetaTrader5LiveExecClientFactory",
    "MetaTrader5InstrumentProvider",
]
