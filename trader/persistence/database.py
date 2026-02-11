"""SQLite database: connection management, schema creation, sync + async APIs."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import aiosqlite

SCHEMA_VERSION = 1

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

CREATE TABLE IF NOT EXISTS backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    strategy_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    config_json TEXT,
    metrics_json TEXT,
    total_return REAL,
    sharpe REAL,
    max_drawdown REAL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    order_type TEXT NOT NULL,
    limit_price REAL,
    stop_price REAL,
    tag TEXT,
    tif TEXT NOT NULL DEFAULT 'DAY',
    ts TEXT NOT NULL,
    strategy_id TEXT,
    session_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fills_session ON fills(session_id);
CREATE INDEX IF NOT EXISTS idx_fills_symbol ON fills(symbol);
CREATE INDEX IF NOT EXISTS idx_fills_strategy ON fills(strategy_id);
CREATE INDEX IF NOT EXISTS idx_equity_session_ts ON equity_snapshots(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_equity_strategy ON equity_snapshots(strategy_id, ts);
CREATE INDEX IF NOT EXISTS idx_positions_session ON position_snapshots(session_id);
CREATE INDEX IF NOT EXISTS idx_orders_session ON orders(session_id);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
"""


class Database:
    """Sync + async SQLite access. Schema auto-created on first connect."""

    def __init__(self, path: str | Path = "trading.db"):
        self.path = Path(path)
        self._sync_conn: sqlite3.Connection | None = None

    # -- Sync API (for backtests, scripts) --

    def connect_sync(self) -> sqlite3.Connection:
        if self._sync_conn is not None:
            return self._sync_conn
        self._sync_conn = sqlite3.connect(str(self.path))
        self._sync_conn.row_factory = sqlite3.Row
        self._sync_conn.execute("PRAGMA journal_mode=WAL")
        self._sync_conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema_sync(self._sync_conn)
        return self._sync_conn

    def close_sync(self) -> None:
        if self._sync_conn is not None:
            self._sync_conn.close()
            self._sync_conn = None

    @contextmanager
    def session_sync(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self.connect_sync()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_schema_sync(self, conn: sqlite3.Connection) -> None:
        conn.executescript(SCHEMA_SQL)
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,)
            )
            conn.commit()

    # -- Async API (for live trading) --

    async def connect_async(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(str(self.path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.executescript(SCHEMA_SQL)
        # Check/set version
        async with conn.execute(
            "SELECT version FROM schema_version"
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            await conn.execute(
                "INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,)
            )
        await conn.commit()
        return conn
