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
from nautilus_trader.model.identifiers import InstrumentId


def ibkr_data_config(
    host: str = "127.0.0.1",
    port: int = 7497,
    client_id: int = 1,
    market_data_type: IBMarketDataTypeEnum = IBMarketDataTypeEnum.REALTIME,
    instrument_ids: list[str] | None = None,
    instrument_provider: InteractiveBrokersInstrumentProviderConfig | None = None,
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

    return InteractiveBrokersDataClientConfig(
        ibg_host=host,
        ibg_port=port,
        ibg_client_id=client_id,
        market_data_type=market_data_type,
        instrument_provider=instrument_provider,
        **kwargs,
    )


def ibkr_exec_config(
    host: str = "127.0.0.1",
    port: int = 7497,
    client_id: int = 1,
    account: str = "",
    instrument_ids: list[str] | None = None,
    instrument_provider: InteractiveBrokersInstrumentProviderConfig | None = None,
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

    return InteractiveBrokersExecClientConfig(
        ibg_host=host,
        ibg_port=port,
        ibg_client_id=client_id,
        account_id=account,
        instrument_provider=instrument_provider,
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
