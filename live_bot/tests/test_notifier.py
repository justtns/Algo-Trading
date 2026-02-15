"""Tests for the FillNotifier."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from live_bot.src.db.reader import TradeReader
from live_bot.src.notifier import FillNotifier


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
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
INSERT INTO schema_version VALUES (1);
"""


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    db_file = tmp_path / "notifier_test.db"
    conn = sqlite3.connect(str(db_file))
    conn.executescript(SCHEMA_SQL)
    # Seed with 2 existing fills
    conn.executemany(
        "INSERT INTO fills (order_id, symbol, side, qty, price, fee, ts, strategy_id, session_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("ord-1", "EURUSD", "BUY", 10000, 1.085, 0.5, "2025-01-15T10:00:00", "strat1", "s1"),
            ("ord-2", "USDJPY", "SELL", 20000, 154.3, 0.8, "2025-01-15T11:00:00", "strat1", "s1"),
        ],
    )
    conn.commit()
    conn.close()
    return db_file


class TestFillNotifier:
    def test_init_cursor(self, db_path: Path):
        reader = TradeReader(db_path)
        reader.connect()
        notifier = FillNotifier(reader, send_fn=None, poll_interval=5)
        notifier.init_cursor()
        assert notifier._last_seen_id == 2
        reader.close()

    @pytest.mark.asyncio
    async def test_check_new_fills_none(self, db_path: Path):
        reader = TradeReader(db_path)
        reader.connect()

        sent = []
        async def mock_send(text):
            sent.append(text)

        notifier = FillNotifier(reader, send_fn=mock_send)
        notifier.init_cursor()

        await notifier.check_new_fills()
        assert len(sent) == 0  # no new fills
        reader.close()

    @pytest.mark.asyncio
    async def test_check_new_fills_detects_new(self, db_path: Path):
        reader = TradeReader(db_path)
        reader.connect()

        sent = []
        async def mock_send(text):
            sent.append(text)

        notifier = FillNotifier(reader, send_fn=mock_send)
        notifier.init_cursor()
        assert notifier._last_seen_id == 2

        # Insert a new fill directly
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO fills (order_id, symbol, side, qty, price, fee, ts, strategy_id, session_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ord-3", "GBPUSD", "BUY", 5000, 1.261, 0.3, "2025-01-15T14:00:00", "strat2", "s1"),
        )
        conn.commit()
        conn.close()

        await notifier.check_new_fills()
        assert len(sent) == 1
        assert "GBPUSD" in sent[0]
        assert "BUY" in sent[0]
        assert notifier._last_seen_id == 3

        # Calling again should find nothing new
        await notifier.check_new_fills()
        assert len(sent) == 1

        reader.close()

    @pytest.mark.asyncio
    async def test_check_new_fills_multiple(self, db_path: Path):
        reader = TradeReader(db_path)
        reader.connect()

        sent = []
        async def mock_send(text):
            sent.append(text)

        notifier = FillNotifier(reader, send_fn=mock_send)
        notifier.init_cursor()

        # Insert 3 new fills
        conn = sqlite3.connect(str(db_path))
        conn.executemany(
            "INSERT INTO fills (order_id, symbol, side, qty, price, fee, ts, strategy_id, session_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("ord-3", "GBPUSD", "BUY", 5000, 1.261, 0, "2025-01-15T14:00:00", "s", "s1"),
                ("ord-4", "AUDUSD", "SELL", 8000, 0.652, 0, "2025-01-15T14:01:00", "s", "s1"),
                ("ord-5", "NZDUSD", "BUY", 3000, 0.611, 0, "2025-01-15T14:02:00", "s", "s1"),
            ],
        )
        conn.commit()
        conn.close()

        await notifier.check_new_fills()
        assert len(sent) == 3
        assert notifier._last_seen_id == 5

        reader.close()
