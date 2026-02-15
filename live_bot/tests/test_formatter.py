"""Tests for live bot formatters."""
from __future__ import annotations

from live_bot.src.bot.formatter import (
    format_fill_alert,
    format_fills,
    format_positions,
    format_equity,
    format_status,
)


class TestFormatFillAlert:
    def test_basic_alert(self):
        fill = {
            "side": "BUY", "symbol": "EURUSD", "qty": 10000,
            "price": 1.085, "strategy_id": "momentum", "ts": "2025-01-15T10:30:00",
        }
        msg = format_fill_alert(fill)
        assert "FILL" in msg
        assert "BUY" in msg
        assert "10,000" in msg
        assert "EURUSD" in msg
        assert "momentum" in msg

    def test_no_strategy(self):
        fill = {
            "side": "SELL", "symbol": "USDJPY", "qty": 5000.5,
            "price": 154.32, "strategy_id": None, "ts": "2025-01-15T11:00:00",
        }
        msg = format_fill_alert(fill)
        assert "—" in msg  # em dash for missing strategy


class TestFormatFills:
    def test_empty_fills(self):
        messages = format_fills([])
        assert len(messages) == 1
        assert "No fills found" in messages[0]

    def test_with_fills(self):
        fills = [
            {"ts": "2025-01-15T10:30:00", "side": "BUY", "qty": 10000,
             "symbol": "EURUSD", "price": 1.085, "strategy_id": "momentum"},
            {"ts": "2025-01-15T11:00:00", "side": "SELL", "qty": 20000,
             "symbol": "USDJPY", "price": 154.32, "strategy_id": "mean_rev"},
        ]
        messages = format_fills(fills)
        assert len(messages) >= 1
        assert "Recent Fills" in messages[0]
        assert "EURUSD" in messages[0]
        assert "USDJPY" in messages[0]


class TestFormatPositions:
    def test_empty(self):
        messages = format_positions([])
        assert "No open positions" in messages[0]

    def test_with_positions(self):
        positions = [
            {"symbol": "EURUSD", "qty": 10000, "avg_price": 1.085,
             "mtm_price": 1.086, "unrealized_pnl": 10.0},
        ]
        messages = format_positions(positions)
        assert "Open Positions" in messages[0]
        assert "EURUSD" in messages[0]
        assert "+10.00" in messages[0]


class TestFormatEquity:
    def test_none(self):
        msg = format_equity(None)
        assert "No equity data" in msg

    def test_with_data(self):
        equity = {"equity": 100000.0, "cash": 95000.0,
                  "ts": "2025-01-15T10:30:00", "strategy_id": "momentum"}
        msg = format_equity(equity)
        assert "100,000.00" in msg
        assert "95,000.00" in msg


class TestFormatStatus:
    def test_connected(self):
        msg = format_status(
            db_path="/path/to/db",
            connected=True,
            last_fill_ts="2025-01-15T10:30:00",
            fill_count=42,
            active_session="sess-1",
        )
        assert "Yes" in msg
        assert "42" in msg
        assert "sess-1" in msg

    def test_disconnected(self):
        msg = format_status(
            db_path="/path/to/db",
            connected=False,
            last_fill_ts=None,
            fill_count=0,
            active_session=None,
        )
        assert "No" in msg
        assert "None" in msg
