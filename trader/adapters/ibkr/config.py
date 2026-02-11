"""
Configuration helpers for NautilusTrader's built-in Interactive Brokers adapter.

These functions provide sensible defaults and simplify configuration
for FX trading via IBKR.
"""
from __future__ import annotations

from ibapi.common import MarketDataTypeEnum as IBMarketDataTypeEnum
from nautilus_trader.adapters.interactive_brokers.config import (
    InteractiveBrokersDataClientConfig,
    InteractiveBrokersExecClientConfig,
    InteractiveBrokersInstrumentProviderConfig,
)
from nautilus_trader.live.config import RoutingConfig
from nautilus_trader.model.identifiers import InstrumentId


def ibkr_data_config(
    host: str = "127.0.0.1",
    port: int = 7497,
    client_id: int = 1,
    market_data_type: IBMarketDataTypeEnum = IBMarketDataTypeEnum.REALTIME,
    instrument_ids: list[str] | None = None,
    instrument_provider: InteractiveBrokersInstrumentProviderConfig | None = None,
    routing: RoutingConfig | None = None,
    routing_venues: list[str] | None = None,
    **kwargs,
) -> InteractiveBrokersDataClientConfig:
    """
    Create an IBKR data client config with FX-friendly defaults.

    Parameters
    ----------
    host : str
        TWS/Gateway host address.
    port : int
        TWS/Gateway port. 7497 for paper, 7496 for live.
    client_id : int
        TWS client ID.
    market_data_type : IBMarketDataTypeEnum
        Data entitlement mode. Use ``IBMarketDataTypeEnum.DELAYED_FROZEN`` when
        the account has no real-time market data subscription.
    instrument_ids : list[str], optional
        Instrument IDs to preload via the instrument provider
        (e.g. ``\"USD/JPY.IDEALPRO\"``). If omitted, the provider will
        not load anything by default and strategies will fail to start.
    instrument_provider : InteractiveBrokersInstrumentProviderConfig, optional
        Fully customised provider configuration to use instead of the
        simple ``instrument_ids`` shortcut.
    """
    if instrument_provider is None:
        instrument_provider = _ibkr_instrument_provider(instrument_ids)
    if routing is None:
        routing = _ibkr_routing(
            instrument_ids=instrument_ids,
            instrument_provider=instrument_provider,
            routing_venues=routing_venues,
        )

    return InteractiveBrokersDataClientConfig(
        ibg_host=host,
        ibg_port=port,
        ibg_client_id=client_id,
        market_data_type=market_data_type,
        instrument_provider=instrument_provider,
        routing=routing,
        **kwargs,
    )


def ibkr_exec_config(
    host: str = "127.0.0.1",
    port: int = 7497,
    client_id: int = 1,
    account: str = "",
    instrument_ids: list[str] | None = None,
    instrument_provider: InteractiveBrokersInstrumentProviderConfig | None = None,
    routing: RoutingConfig | None = None,
    routing_venues: list[str] | None = None,
    **kwargs,
) -> InteractiveBrokersExecClientConfig:
    """
    Create an IBKR execution client config.

    Parameters
    ----------
    host : str
        TWS/Gateway host address.
    port : int
        TWS/Gateway port. 7497 for paper, 7496 for live.
    client_id : int
        TWS client ID.
    account : str
        IB account ID (e.g. "DU1234567").
    instrument_ids : list[str], optional
        Instrument IDs to preload via the instrument provider. Must match
        the IDs your strategies use.
    instrument_provider : InteractiveBrokersInstrumentProviderConfig, optional
        Fully customised provider configuration to use instead of the
        ``instrument_ids`` shortcut.
    """
    if instrument_provider is None:
        instrument_provider = _ibkr_instrument_provider(instrument_ids)
    if routing is None:
        routing = _ibkr_routing(
            instrument_ids=instrument_ids,
            instrument_provider=instrument_provider,
            routing_venues=routing_venues,
        )

    return InteractiveBrokersExecClientConfig(
        ibg_host=host,
        ibg_port=port,
        ibg_client_id=client_id,
        account_id=account,
        instrument_provider=instrument_provider,
        routing=routing,
        **kwargs,
    )


def ibkr_instrument_config(
    **kwargs,
) -> InteractiveBrokersInstrumentProviderConfig:
    """
    Create an IBKR instrument provider config.
    """
    return InteractiveBrokersInstrumentProviderConfig(**kwargs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ibkr_instrument_provider(
    instrument_ids: list[str] | None,
) -> InteractiveBrokersInstrumentProviderConfig:
    """
    Convenience helper to build a provider that preloads the given
    instrument IDs. If ``instrument_ids`` is ``None`` or empty, returns
    the default provider config to preserve existing behaviour.
    """
    load_ids = (
        frozenset(InstrumentId.from_str(instr) for instr in instrument_ids)
        if instrument_ids
        else None
    )
    return InteractiveBrokersInstrumentProviderConfig(load_ids=load_ids)


def _ibkr_routing(
    *,
    instrument_ids: list[str] | None,
    instrument_provider: InteractiveBrokersInstrumentProviderConfig | None,
    routing_venues: list[str] | None,
) -> RoutingConfig:
    """
    Build a routing config which maps the loaded instrument venues to this client.

    This avoids implicit venue inference mismatches in live routing, while
    preserving the old behavior when no venues can be inferred.
    """
    venues: set[str] = set()

    if routing_venues:
        venues.update(v for v in routing_venues if v)

    if instrument_ids:
        for instr in instrument_ids:
            venues.add(str(InstrumentId.from_str(instr).venue))

    if instrument_provider is not None:
        load_ids = getattr(instrument_provider, "load_ids", None)
        if load_ids:
            for instrument_id in load_ids:
                venues.add(str(instrument_id.venue))

    if not venues:
        return RoutingConfig(default=False, venues=None)

    return RoutingConfig(default=False, venues=frozenset(venues))
