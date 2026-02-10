"""
Factory classes for wiring MetaTrader 5 adapters into NautilusTrader TradingNode.
"""
from __future__ import annotations

import asyncio
from typing import Any

from nautilus_trader.live.factories import LiveDataClientFactory, LiveExecClientFactory
from nautilus_trader.model.identifiers import ClientId, Venue

from trader.adapters.metatrader.common import MetaTrader5Connection
from trader.adapters.metatrader.data import MetaTrader5DataClient, MetaTrader5DataClientConfig
from trader.adapters.metatrader.execution import MetaTrader5ExecutionClient, MetaTrader5ExecClientConfig
from trader.core.constants import MT5


class MetaTrader5LiveDataClientFactory(LiveDataClientFactory):

    @staticmethod
    def create(
        loop: asyncio.AbstractEventLoop,
        name: str,
        config: MetaTrader5DataClientConfig,
        msgbus: Any,
        cache: Any,
        clock: Any,
    ) -> MetaTrader5DataClient:
        return MetaTrader5DataClient(
            loop=loop,
            client_id=ClientId(name),
            venue=MT5,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            config=config,
        )


class MetaTrader5LiveExecClientFactory(LiveExecClientFactory):

    @staticmethod
    def create(
        loop: asyncio.AbstractEventLoop,
        name: str,
        config: MetaTrader5ExecClientConfig,
        msgbus: Any,
        cache: Any,
        clock: Any,
    ) -> MetaTrader5ExecutionClient:
        return MetaTrader5ExecutionClient(
            loop=loop,
            client_id=ClientId(name),
            venue=MT5,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            config=config,
        )
