"""
Shared helpers for live strategy order submission and position lifecycle.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import ClientId, InstrumentId


def parse_time_in_force(
    value: str | TimeInForce | None,
    *,
    default: TimeInForce = TimeInForce.FOK,
) -> TimeInForce:
    """
    Parse a string enum name into ``TimeInForce``.

    Empty values fall back to ``default``.
    """
    if isinstance(value, TimeInForce):
        return value
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return getattr(TimeInForce, text.upper())
    except AttributeError as exc:  # pragma: no cover - config validation guard
        raise ValueError(f"Unsupported time_in_force '{value}'") from exc


def parse_exec_client_id(value: str | ClientId | None) -> ClientId | None:
    if isinstance(value, ClientId):
        return value
    if value is None:
        return None
    text = str(value).strip()
    return ClientId(text) if text else None


def resolve_trade_quantity(
    *,
    instrument: Any,
    configured_trade_size: float,
    allocated_capital: float | None = None,
    margin_rate: float = 0.02,
) -> float:
    lot_size = float(getattr(instrument, "lot_size", 1.0) or 1.0)
    if allocated_capital is not None and margin_rate > 0:
        return float(allocated_capital) / float(margin_rate)
    return float(configured_trade_size) * lot_size


class LiveExecutionMixin:
    """
    Mixin for venue-specific execution routing and position lifecycle helpers.

    Strategies using this mixin should define:
    - ``instrument_id``
    - ``id`` (strategy id)
    - ``cache`` and ``submit_order`` methods from Nautilus ``Strategy``
    """

    exec_client_id: ClientId | None
    time_in_force: TimeInForce
    _pending_close_position_ids: set
    _close_order_to_position_id: dict

    def _configure_live_execution(
        self,
        *,
        exec_client_id: str | ClientId | None,
        time_in_force: str | TimeInForce | None,
        default_tif: TimeInForce = TimeInForce.FOK,
    ) -> None:
        self.exec_client_id = parse_exec_client_id(exec_client_id)
        self.time_in_force = parse_time_in_force(time_in_force, default=default_tif)

    def _submit_order(self, order, position_id=None) -> None:
        client_id = getattr(self, "exec_client_id", None)
        if client_id is None:
            self.submit_order(order, position_id=position_id)
            return
        self.submit_order(order, position_id=position_id, client_id=client_id)

    def _iter_open_strategy_positions(self) -> Iterable[Any]:
        instrument_id: InstrumentId = self.instrument_id
        for position in self.cache.positions(venue=instrument_id.venue):
            if (
                position.instrument_id == instrument_id
                and not position.is_closed
                and position.strategy_id == self.id
            ):
                yield position

    def _current_position(self):
        for position in self._iter_open_strategy_positions():
            return position
        return None

    def _track_pending_close(self, *, position_id, client_order_id) -> None:
        self._pending_close_position_ids.add(position_id)
        self._close_order_to_position_id[client_order_id] = position_id

    def _release_pending_close_on_failed_order(self, *, client_order_id) -> bool:
        position_id = self._close_order_to_position_id.pop(client_order_id, None)
        if position_id is None:
            return False
        self._pending_close_position_ids.discard(position_id)
        return True

    def _release_pending_close_on_position_closed(self, *, position_id) -> None:
        self._pending_close_position_ids.discard(position_id)
        stale_order_ids = [
            client_order_id
            for client_order_id, tracked_position_id in self._close_order_to_position_id.items()
            if tracked_position_id == position_id
        ]
        for client_order_id in stale_order_ids:
            self._close_order_to_position_id.pop(client_order_id, None)
