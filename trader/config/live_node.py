"""
Live TradingNode builder for multi-venue concurrent trading.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.trading.strategy import Strategy


@dataclass
class LiveVenueClientConfig:
    """Pairs a venue with its data and execution client configs."""

    venue_name: str
    data_client_config: Any
    exec_client_config: Any
    data_client_factory: Any | None = None  # for custom adapters (MT5)
    exec_client_factory: Any | None = None


def build_live_trading_node(
    venue_clients: Sequence[LiveVenueClientConfig],
    strategies: Sequence[Strategy],
    *,
    node_config: TradingNodeConfig | None = None,
) -> TradingNode:
    """
    Build a TradingNode with multiple venue data/exec clients.

    NautilusTrader's TradingNode natively supports multiple clients.
    This function wires them together.

    Parameters
    ----------
    venue_clients : list of LiveVenueClientConfig
        One per venue, each with data and execution client configs.
    strategies : list of Strategy
        Trading strategies to add.
    node_config : TradingNodeConfig or None
        Custom node configuration. If None, built from venue_clients.
    """
    if node_config is None:
        data_clients = {}
        exec_clients = {}
        for vc in venue_clients:
            data_clients[vc.venue_name] = vc.data_client_config
            if vc.exec_client_config is not None:
                exec_clients[vc.venue_name] = vc.exec_client_config
        node_config = TradingNodeConfig(
            data_clients=data_clients,
            exec_clients=exec_clients,
        )

    node = TradingNode(config=node_config)

    for vc in venue_clients:
        if vc.data_client_factory is not None:
            node.add_data_client_factory(vc.venue_name, vc.data_client_factory)
        if vc.exec_client_factory is not None:
            node.add_exec_client_factory(vc.venue_name, vc.exec_client_factory)

    for strategy in strategies:
        node.trader.add_strategy(strategy)

    return node
