from types import SimpleNamespace

import pytest

from nautilus_trader.model.enums import TimeInForce

from trader.adapters.metatrader.execution import MetaTrader5ExecutionClient


class _DummyMT5:
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2


class _DummyLog:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def warning(self, msg: str) -> None:
        self.messages.append(msg)


def _make_client_for_helpers(
    *,
    lot_size: float | None = 100.0,
    configured_filling: int = _DummyMT5.ORDER_FILLING_IOC,
    position_exists: bool = True,
    venue_position_id: str | None = "241712932",
    opening_order_venue_order_id: str | None = None,
) -> SimpleNamespace:
    instrument = SimpleNamespace(lot_size=lot_size) if lot_size is not None else None
    opening_order_id = "O-TEST-1" if opening_order_venue_order_id is not None else None

    position = None
    if position_exists:
        position = SimpleNamespace(
            venue_position_id=(
                SimpleNamespace(value=venue_position_id)
                if venue_position_id is not None
                else None
            ),
            opening_order_id=opening_order_id,
        )

    opening_order = (
        SimpleNamespace(
            venue_order_id=SimpleNamespace(value=opening_order_venue_order_id),
        )
        if opening_order_venue_order_id is not None
        else None
    )
    cache = SimpleNamespace(
        instrument=lambda _instrument_id: instrument,
        position=lambda _position_id: position,
        order=lambda _order_id: opening_order if _order_id == opening_order_id else None,
    )
    log = _DummyLog()
    connection = SimpleNamespace(config=SimpleNamespace(type_filling=configured_filling))
    client = SimpleNamespace(_cache=cache, _connection=connection, _log=log)
    client._convert_quantity_to_mt5_volume = MetaTrader5ExecutionClient._convert_quantity_to_mt5_volume
    client._round_to_step = MetaTrader5ExecutionClient._round_to_step
    client._extract_supported_fillings = MetaTrader5ExecutionClient._extract_supported_fillings
    client._resolve_mt5_position_ticket = MetaTrader5ExecutionClient._resolve_mt5_position_ticket
    return client


def test_extract_supported_fillings_from_bitmask() -> None:
    supported = MetaTrader5ExecutionClient._extract_supported_fillings(
        raw_filling_mode=2,  # IOC in bitmask style
        mt5=_DummyMT5,
    )
    assert supported == {_DummyMT5.ORDER_FILLING_IOC}


def test_extract_supported_fillings_from_direct_enum() -> None:
    supported = MetaTrader5ExecutionClient._extract_supported_fillings(
        raw_filling_mode=_DummyMT5.ORDER_FILLING_FOK,
        mt5=_DummyMT5,
    )
    assert supported == {_DummyMT5.ORDER_FILLING_FOK}


def test_resolve_mt5_volume_converts_quantity_to_lots() -> None:
    client = _make_client_for_helpers(lot_size=100.0)
    order = SimpleNamespace(quantity=10.0, instrument_id="XAUUSD.MT5")
    symbol_info = SimpleNamespace(volume_step=0.01, volume_min=0.01, volume_max=50.0)

    volume, error = MetaTrader5ExecutionClient._resolve_mt5_volume(
        client,
        order=order,
        symbol_info=symbol_info,
    )

    assert error is None
    assert volume == pytest.approx(0.10)


def test_resolve_mt5_volume_rejects_below_minimum() -> None:
    client = _make_client_for_helpers(lot_size=100.0)
    order = SimpleNamespace(quantity=1.0, instrument_id="XAUUSD.MT5")
    symbol_info = SimpleNamespace(volume_step=0.01, volume_min=0.10, volume_max=50.0)

    volume, error = MetaTrader5ExecutionClient._resolve_mt5_volume(
        client,
        order=order,
        symbol_info=symbol_info,
    )

    assert volume is None
    assert error is not None
    assert "below broker minimum" in error


def test_resolve_mt5_filling_mode_falls_back_when_fok_unsupported() -> None:
    client = _make_client_for_helpers(
        configured_filling=_DummyMT5.ORDER_FILLING_IOC,
    )
    order = SimpleNamespace(time_in_force=TimeInForce.FOK)
    symbol_info = SimpleNamespace(filling_mode=2)  # IOC only in bitmask style

    filling = MetaTrader5ExecutionClient._resolve_mt5_filling_mode(
        client,
        order=order,
        symbol="XAUUSD",
        symbol_info=symbol_info,
        mt5=_DummyMT5,
    )

    assert filling == _DummyMT5.ORDER_FILLING_IOC
    assert client._log.messages
    assert "unsupported" in client._log.messages[0].lower()


def test_resolve_mt5_position_ticket_from_cached_position() -> None:
    client = _make_client_for_helpers(venue_position_id="241712932")
    ticket, error = MetaTrader5ExecutionClient._resolve_mt5_position_ticket(
        client,
        position_id="P-TEST-1",
    )
    assert error is None
    assert ticket == 241712932


def test_resolve_mt5_position_ticket_rejects_when_missing() -> None:
    client = _make_client_for_helpers(position_exists=False, venue_position_id=None)
    ticket, error = MetaTrader5ExecutionClient._resolve_mt5_position_ticket(
        client,
        position_id="P-TEST-1",
    )
    assert ticket is None
    assert error is not None
    assert "not found in cache" in error


def test_resolve_mt5_position_ticket_falls_back_to_opening_order_ticket() -> None:
    client = _make_client_for_helpers(
        venue_position_id=None,
        opening_order_venue_order_id="241714853",
    )
    ticket, error = MetaTrader5ExecutionClient._resolve_mt5_position_ticket(
        client,
        position_id="P-TEST-1",
    )
    assert error is None
    assert ticket == 241714853
    assert client._log.messages
    assert "using opening order ticket" in client._log.messages[0].lower()


def test_resolve_mt5_position_ticket_rejects_without_fallback() -> None:
    client = _make_client_for_helpers(
        venue_position_id=None,
        opening_order_venue_order_id=None,
    )
    ticket, error = MetaTrader5ExecutionClient._resolve_mt5_position_ticket(
        client,
        position_id="P-TEST-1",
    )
    assert ticket is None
    assert error is not None
    assert "missing venue_position_id" in error
