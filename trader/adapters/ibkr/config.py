"""
Configuration helpers for NautilusTrader's built-in Interactive Brokers adapter.

These functions provide sensible defaults and simplify configuration
for FX trading via IBKR.
"""
from __future__ import annotations

from nautilus_trader.adapters.interactive_brokers.config import (
    InteractiveBrokersDataClientConfig,
    InteractiveBrokersExecClientConfig,
    InteractiveBrokersInstrumentProviderConfig,
)


def ibkr_data_config(
    host: str = "127.0.0.1",
    port: int = 7497,
    client_id: int = 1,
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
    """
    return InteractiveBrokersDataClientConfig(
        ibg_host=host,
        ibg_port=port,
        ibg_client_id=client_id,
        **kwargs,
    )


def ibkr_exec_config(
    host: str = "127.0.0.1",
    port: int = 7497,
    client_id: int = 1,
    account: str = "",
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
    """
    return InteractiveBrokersExecClientConfig(
        ibg_host=host,
        ibg_port=port,
        ibg_client_id=client_id,
        account_id=account,
        **kwargs,
    )


def ibkr_instrument_config(
    **kwargs,
) -> InteractiveBrokersInstrumentProviderConfig:
    """
    Create an IBKR instrument provider config.
    """
    return InteractiveBrokersInstrumentProviderConfig(**kwargs)
