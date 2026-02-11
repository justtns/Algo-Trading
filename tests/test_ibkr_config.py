from nautilus_trader.live.config import RoutingConfig
from nautilus_trader.model.identifiers import InstrumentId

from trader.adapters.ibkr import ibkr_data_config, ibkr_exec_config, ibkr_instrument_config


def test_ibkr_config_infers_routing_venue_from_loaded_instrument_ids() -> None:
    provider = ibkr_instrument_config(
        load_ids=frozenset({InstrumentId.from_str("EUR/USD.IDEALPRO")}),
    )

    data_cfg = ibkr_data_config(instrument_provider=provider)
    exec_cfg = ibkr_exec_config(instrument_provider=provider)

    assert data_cfg.routing.venues == frozenset({"IDEALPRO"})
    assert exec_cfg.routing.venues == frozenset({"IDEALPRO"})


def test_ibkr_config_respects_explicit_routing_override() -> None:
    explicit = RoutingConfig(default=True, venues=None)
    cfg = ibkr_exec_config(
        instrument_ids=["EUR/USD.IDEALPRO"],
        routing=explicit,
    )

    assert cfg.routing == explicit
