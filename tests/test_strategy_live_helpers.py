from types import SimpleNamespace

import pytest
from nautilus_trader.model.enums import TimeInForce

from trader.strategy.live_helpers import (
    LiveExecutionMixin,
    parse_exec_client_id,
    parse_time_in_force,
    resolve_trade_quantity,
)


class _DummyLiveStrategy(LiveExecutionMixin):
    def __init__(self) -> None:
        self.exec_client_id = None
        self.submitted: list[tuple[object, object, object]] = []
        self._pending_close_position_ids: set = set()
        self._close_order_to_position_id: dict = {}

    def submit_order(self, order, position_id=None, client_id=None) -> None:
        self.submitted.append((order, position_id, client_id))


def test_parse_time_in_force_defaults_and_values() -> None:
    assert parse_time_in_force(None, default=TimeInForce.IOC) == TimeInForce.IOC
    assert parse_time_in_force("day", default=TimeInForce.FOK) == TimeInForce.DAY


def test_parse_time_in_force_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="Unsupported time_in_force"):
        parse_time_in_force("not-a-tif")


def test_parse_exec_client_id_handles_blank() -> None:
    assert parse_exec_client_id(None) is None
    assert parse_exec_client_id("  ") is None
    assert str(parse_exec_client_id("IDEALPRO")) == "IDEALPRO"


def test_resolve_trade_quantity_uses_lot_size_when_not_capital_allocated() -> None:
    instrument = SimpleNamespace(lot_size=100_000)
    qty = resolve_trade_quantity(instrument=instrument, configured_trade_size=0.01)
    assert qty == pytest.approx(1_000)


def test_resolve_trade_quantity_uses_allocated_capital_when_provided() -> None:
    instrument = SimpleNamespace(lot_size=100_000)
    qty = resolve_trade_quantity(
        instrument=instrument,
        configured_trade_size=0.01,
        allocated_capital=50_000,
        margin_rate=0.02,
    )
    assert qty == pytest.approx(2_500_000)


def test_submit_order_uses_client_id_when_configured() -> None:
    strategy = _DummyLiveStrategy()
    strategy.exec_client_id = parse_exec_client_id("IDEALPRO")
    order = SimpleNamespace(client_order_id="O-1")

    LiveExecutionMixin._submit_order(strategy, order)

    assert str(strategy.submitted[-1][2]) == "IDEALPRO"


def test_pending_close_release_on_failed_close_order() -> None:
    strategy = _DummyLiveStrategy()
    strategy._track_pending_close(position_id="P-1", client_order_id="O-1")

    released = strategy._release_pending_close_on_failed_order(client_order_id="O-1")

    assert released is True
    assert strategy._pending_close_position_ids == set()


def test_pending_close_release_on_position_closed() -> None:
    strategy = _DummyLiveStrategy()
    strategy._track_pending_close(position_id="P-1", client_order_id="O-1")
    strategy._track_pending_close(position_id="P-2", client_order_id="O-2")

    strategy._release_pending_close_on_position_closed(position_id="P-1")

    assert strategy._pending_close_position_ids == {"P-2"}
    assert strategy._close_order_to_position_id == {"O-2": "P-2"}
