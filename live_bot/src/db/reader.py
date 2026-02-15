"""Read-only access to the NautilusTrader SQLite database."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class TradeReader:
    """Read-only connection to the NautilusTrader trading database.

    Opens the DB in read-only mode (WAL-safe for concurrent access while
    the trading engine writes).
    """

    def __init__(self, db_path: str | Path):
        self._path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        uri = f"file:{self._path}?mode=ro"
        self._conn = sqlite3.connect(uri, uri=True)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def connected(self) -> bool:
        return self._conn is not None

    def _ensure_connected(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        return self._conn

    # ------------------------------------------------------------------
    # Fills
    # ------------------------------------------------------------------

    def get_recent_fills(self, limit: int = 20) -> list[dict]:
        conn = self._ensure_connected()
        rows = conn.execute(
            "SELECT id, order_id, symbol, side, qty, price, fee, ts, "
            "strategy_id, session_id FROM fills ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_today_fills(self) -> list[dict]:
        conn = self._ensure_connected()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
        rows = conn.execute(
            "SELECT id, order_id, symbol, side, qty, price, fee, ts, "
            "strategy_id, session_id FROM fills WHERE ts >= ? ORDER BY id DESC",
            (today,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_max_fill_id(self) -> int:
        conn = self._ensure_connected()
        row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM fills").fetchone()
        return row[0]

    def get_fills_after(self, after_id: int) -> list[dict]:
        conn = self._ensure_connected()
        rows = conn.execute(
            "SELECT id, order_id, symbol, side, qty, price, fee, ts, "
            "strategy_id, session_id FROM fills WHERE id > ? ORDER BY id ASC",
            (after_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def get_latest_positions(self, session_id: str | None = None) -> list[dict]:
        conn = self._ensure_connected()
        if session_id:
            rows = conn.execute(
                "SELECT p.* FROM position_snapshots p "
                "INNER JOIN ("
                "  SELECT symbol, MAX(id) AS max_id FROM position_snapshots "
                "  WHERE session_id = ? GROUP BY symbol"
                ") latest ON p.id = latest.max_id",
                (session_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT p.* FROM position_snapshots p "
                "INNER JOIN ("
                "  SELECT symbol, MAX(id) AS max_id FROM position_snapshots "
                "  GROUP BY symbol"
                ") latest ON p.id = latest.max_id",
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Equity
    # ------------------------------------------------------------------

    def get_latest_equity(self, session_id: str | None = None) -> dict | None:
        conn = self._ensure_connected()
        if session_id:
            row = conn.execute(
                "SELECT * FROM equity_snapshots "
                "WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM equity_snapshots ORDER BY id DESC LIMIT 1",
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    def get_active_session_id(self) -> str | None:
        conn = self._ensure_connected()
        row = conn.execute(
            "SELECT session_id FROM fills ORDER BY id DESC LIMIT 1",
        ).fetchone()
        return row["session_id"] if row else None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_last_fill_ts(self) -> str | None:
        conn = self._ensure_connected()
        row = conn.execute(
            "SELECT ts FROM fills ORDER BY id DESC LIMIT 1",
        ).fetchone()
        return row["ts"] if row else None

    def get_fill_count(self) -> int:
        conn = self._ensure_connected()
        row = conn.execute("SELECT COUNT(*) FROM fills").fetchone()
        return row[0]
