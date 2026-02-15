"""Tests for the TradeReader (uses a real in-memory SQLite DB)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from live_bot.src.db.reader import TradeReader


# -- Schema (copied from trader/persistence/database.py) --
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    price REAL NOT NULL,
    fee REAL NOT NULL DEFAULT 0,
    ts TEXT NOT NULL,
    strategy_id TEXT,
    session_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS position_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    qty REAL NOT NULL,
    avg_price REAL NOT NULL,
    mtm_price REAL,
    unrealized_pnl REAL NOT NULL DEFAULT 0,
    ts TEXT NOT NULL,
    strategy_id TEXT,
    session_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS equity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    equity REAL NOT NULL,
    cash REAL NOT NULL DEFAULT 0,
    strategy_id TEXT,
    session_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
INSERT INTO schema_version VALUES (1);
"""


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Create a temporary SQLite DB with schema and sample data."""
    db_file = tmp_path / "test_trading.db"
    conn = sqlite3.connect(str(db_file))
    conn.executescript(SCHEMA_SQL)

    # Insert sample fills
    fills = [
        ("ord-1", "EURUSD", "BUY", 10000, 1.08500, 0.5, "2025-01-15T10:30:00", "momentum", "sess-1"),
        ("ord-2", "USDJPY", "SELL", 20000, 154.320, 0.8, "2025-01-15T11:00:00", "momentum", "sess-1"),
        ("ord-3", "GBPUSD", "BUY", 5000, 1.26100, 0.3, "2025-01-15T14:00:00", "mean_rev", "sess-1"),
        ("ord-4", "EURUSD", "SELL", 10000, 1.08600, 0.5, "2025-01-16T09:00:00", "momentum", "sess-2"),
    ]
    conn.executemany(
        "INSERT INTO fills (order_id, symbol, side, qty, price, fee, ts, strategy_id, session_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        fills,
    )

    # Insert position snapshots
    positions = [
        ("EURUSD", 10000, 1.08500, 1.08550, 5.0, "2025-01-15T10:30:00", "momentum", "sess-1"),
        ("USDJPY", -20000, 154.320, 154.280, 8.0, "2025-01-15T11:00:00", "momentum", "sess-1"),
        ("EURUSD", 0, 1.08500, 1.08600, 0.0, "2025-01-16T09:00:00", "momentum", "sess-2"),
    ]
    conn.executemany(
        "INSERT INTO position_snapshots (symbol, qty, avg_price, mtm_price, unrealized_pnl, "
        "ts, strategy_id, session_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        positions,
    )

    # Insert equity snapshots
    equities = [
        ("2025-01-15T10:30:00", 100000.0, 95000.0, "momentum", "sess-1"),
        ("2025-01-16T09:00:00", 100100.0, 95100.0, "momentum", "sess-2"),
    ]
    conn.executemany(
        "INSERT INTO equity_snapshots (ts, equity, cash, strategy_id, session_id) "
        "VALUES (?, ?, ?, ?, ?)",
        equities,
    )

    conn.commit()
    conn.close()
    return db_file


@pytest.fixture()
def reader(db_path: Path) -> TradeReader:
    r = TradeReader(db_path)
    r.connect()
    yield r
    r.close()


class TestTradeReaderFills:
    def test_get_recent_fills(self, reader: TradeReader):
        fills = reader.get_recent_fills(limit=10)
        assert len(fills) == 4
        # Most recent first
        assert fills[0]["order_id"] == "ord-4"
        assert fills[0]["symbol"] == "EURUSD"

    def test_get_recent_fills_limit(self, reader: TradeReader):
        fills = reader.get_recent_fills(limit=2)
        assert len(fills) == 2

    def test_get_max_fill_id(self, reader: TradeReader):
        assert reader.get_max_fill_id() == 4

    def test_get_fills_after(self, reader: TradeReader):
        fills = reader.get_fills_after(2)
        assert len(fills) == 2
        assert fills[0]["order_id"] == "ord-3"
        assert fills[1]["order_id"] == "ord-4"

    def test_get_fills_after_none_new(self, reader: TradeReader):
        fills = reader.get_fills_after(4)
        assert len(fills) == 0


class TestTradeReaderPositions:
    def test_get_latest_positions(self, reader: TradeReader):
        positions = reader.get_latest_positions()
        assert len(positions) == 2  # EURUSD (latest) and USDJPY

    def test_get_latest_positions_by_session(self, reader: TradeReader):
        positions = reader.get_latest_positions(session_id="sess-1")
        assert len(positions) == 2
        symbols = {p["symbol"] for p in positions}
        assert symbols == {"EURUSD", "USDJPY"}


class TestTradeReaderEquity:
    def test_get_latest_equity(self, reader: TradeReader):
        equity = reader.get_latest_equity()
        assert equity is not None
        assert equity["equity"] == 100100.0
        assert equity["cash"] == 95100.0

    def test_get_latest_equity_by_session(self, reader: TradeReader):
        equity = reader.get_latest_equity(session_id="sess-1")
        assert equity is not None
        assert equity["equity"] == 100000.0


class TestTradeReaderSession:
    def test_get_active_session_id(self, reader: TradeReader):
        assert reader.get_active_session_id() == "sess-2"

    def test_get_last_fill_ts(self, reader: TradeReader):
        assert reader.get_last_fill_ts() == "2025-01-16T09:00:00"

    def test_get_fill_count(self, reader: TradeReader):
        assert reader.get_fill_count() == 4


class TestTradeReaderConnection:
    def test_connected_property(self, db_path: Path):
        r = TradeReader(db_path)
        assert not r.connected
        r.connect()
        assert r.connected
        r.close()
        assert not r.connected

    def test_auto_connect(self, db_path: Path):
        r = TradeReader(db_path)
        # Should auto-connect on first query
        fills = r.get_recent_fills(limit=1)
        assert len(fills) == 1
        assert r.connected
        r.close()


class TestEmptyDatabase:
    def test_empty_fills(self, tmp_path: Path):
        db_file = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_file))
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        conn.close()

        r = TradeReader(db_file)
        r.connect()
        assert r.get_recent_fills() == []
        assert r.get_max_fill_id() == 0
        assert r.get_active_session_id() is None
        assert r.get_latest_equity() is None
        assert r.get_fill_count() == 0
        r.close()
