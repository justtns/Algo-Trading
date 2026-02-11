"""CRUD repositories for each persisted entity."""
from __future__ import annotations

import sqlite3
from typing import List

import pandas as pd

from trader.persistence.models import (
    BacktestResultRow,
    EquitySnapshotRow,
    FillRow,
    OrderRow,
    PositionSnapshotRow,
)


class FillRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert(self, fill: FillRow) -> int:
        cur = self.conn.execute(
            """INSERT INTO fills
               (order_id, symbol, side, qty, price, fee, ts, strategy_id, session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fill.order_id,
                fill.symbol,
                fill.side,
                fill.qty,
                fill.price,
                fill.fee,
                fill.ts,
                fill.strategy_id,
                fill.session_id,
            ),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def insert_batch(self, fills: List[FillRow]) -> None:
        self.conn.executemany(
            """INSERT INTO fills
               (order_id, symbol, side, qty, price, fee, ts, strategy_id, session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    f.order_id,
                    f.symbol,
                    f.side,
                    f.qty,
                    f.price,
                    f.fee,
                    f.ts,
                    f.strategy_id,
                    f.session_id,
                )
                for f in fills
            ],
        )
        self.conn.commit()

    def get_by_session(self, session_id: str) -> List[FillRow]:
        rows = self.conn.execute(
            "SELECT * FROM fills WHERE session_id = ? ORDER BY ts", (session_id,)
        ).fetchall()
        return [self._row_to_fill(r) for r in rows]

    def get_by_symbol(
        self, symbol: str, session_id: str | None = None
    ) -> List[FillRow]:
        if session_id:
            rows = self.conn.execute(
                "SELECT * FROM fills WHERE symbol = ? AND session_id = ? ORDER BY ts",
                (symbol, session_id),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM fills WHERE symbol = ? ORDER BY ts", (symbol,)
            ).fetchall()
        return [self._row_to_fill(r) for r in rows]

    @staticmethod
    def _row_to_fill(row: sqlite3.Row) -> FillRow:
        return FillRow(
            id=row["id"],
            order_id=row["order_id"],
            symbol=row["symbol"],
            side=row["side"],
            qty=row["qty"],
            price=row["price"],
            fee=row["fee"],
            ts=row["ts"],
            strategy_id=row["strategy_id"],
            session_id=row["session_id"],
        )


class EquityRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert(self, snap: EquitySnapshotRow) -> int:
        cur = self.conn.execute(
            """INSERT INTO equity_snapshots (ts, equity, cash, strategy_id, session_id)
               VALUES (?, ?, ?, ?, ?)""",
            (snap.ts, snap.equity, snap.cash, snap.strategy_id, snap.session_id),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_curve(
        self,
        session_id: str,
        strategy_id: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> List[EquitySnapshotRow]:
        query = "SELECT * FROM equity_snapshots WHERE session_id = ?"
        params: list = [session_id]

        if strategy_id is not None:
            query += " AND strategy_id = ?"
            params.append(strategy_id)
        else:
            query += " AND strategy_id IS NULL"

        if start:
            query += " AND ts >= ?"
            params.append(start)
        if end:
            query += " AND ts <= ?"
            params.append(end)

        query += " ORDER BY ts"
        rows = self.conn.execute(query, params).fetchall()
        return [
            EquitySnapshotRow(
                id=r["id"],
                ts=r["ts"],
                equity=r["equity"],
                cash=r["cash"],
                strategy_id=r["strategy_id"],
                session_id=r["session_id"],
            )
            for r in rows
        ]

    def get_curve_as_df(
        self,
        session_id: str,
        strategy_id: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        rows = self.get_curve(session_id, strategy_id, start, end)
        if not rows:
            return pd.DataFrame(columns=["equity", "cash"])
        data = [{"ts": r.ts, "equity": r.equity, "cash": r.cash} for r in rows]
        df = pd.DataFrame(data)
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        df = df.set_index("ts").sort_index()
        return df


class PositionRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert(self, snap: PositionSnapshotRow) -> int:
        cur = self.conn.execute(
            """INSERT INTO position_snapshots
               (symbol, qty, avg_price, mtm_price, unrealized_pnl, ts, strategy_id, session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snap.symbol,
                snap.qty,
                snap.avg_price,
                snap.mtm_price,
                snap.unrealized_pnl,
                snap.ts,
                snap.strategy_id,
                snap.session_id,
            ),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_latest(self, session_id: str) -> List[PositionSnapshotRow]:
        rows = self.conn.execute(
            """SELECT ps.* FROM position_snapshots ps
               INNER JOIN (
                   SELECT symbol, MAX(ts) as max_ts
                   FROM position_snapshots
                   WHERE session_id = ?
                   GROUP BY symbol
               ) latest ON ps.symbol = latest.symbol AND ps.ts = latest.max_ts
               WHERE ps.session_id = ?""",
            (session_id, session_id),
        ).fetchall()
        return [
            PositionSnapshotRow(
                id=r["id"],
                symbol=r["symbol"],
                qty=r["qty"],
                avg_price=r["avg_price"],
                mtm_price=r["mtm_price"],
                unrealized_pnl=r["unrealized_pnl"],
                ts=r["ts"],
                strategy_id=r["strategy_id"],
                session_id=r["session_id"],
            )
            for r in rows
        ]


class BacktestResultRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert(self, result: BacktestResultRow) -> int:
        cur = self.conn.execute(
            """INSERT INTO backtest_results
               (session_id, strategy_name, started_at, ended_at,
                config_json, metrics_json, total_return, sharpe, max_drawdown)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.session_id,
                result.strategy_name,
                result.started_at,
                result.ended_at,
                result.config_json,
                result.metrics_json,
                result.total_return,
                result.sharpe,
                result.max_drawdown,
            ),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_all(self) -> List[BacktestResultRow]:
        rows = self.conn.execute(
            "SELECT * FROM backtest_results ORDER BY started_at DESC"
        ).fetchall()
        return [self._row_to_result(r) for r in rows]

    def get_by_session(self, session_id: str) -> BacktestResultRow | None:
        row = self.conn.execute(
            "SELECT * FROM backtest_results WHERE session_id = ?", (session_id,)
        ).fetchone()
        return self._row_to_result(row) if row else None

    @staticmethod
    def _row_to_result(row: sqlite3.Row) -> BacktestResultRow:
        return BacktestResultRow(
            id=row["id"],
            session_id=row["session_id"],
            strategy_name=row["strategy_name"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            config_json=row["config_json"],
            metrics_json=row["metrics_json"],
            total_return=row["total_return"],
            sharpe=row["sharpe"],
            max_drawdown=row["max_drawdown"],
        )


class OrderRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert(self, order: OrderRow) -> int:
        cur = self.conn.execute(
            """INSERT INTO orders
               (client_order_id, symbol, side, qty, order_type,
                limit_price, stop_price, tag, tif, ts, strategy_id, session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                order.client_order_id,
                order.symbol,
                order.side,
                order.qty,
                order.order_type,
                order.limit_price,
                order.stop_price,
                order.tag,
                order.tif,
                order.ts,
                order.strategy_id,
                order.session_id,
            ),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_by_session(self, session_id: str) -> List[OrderRow]:
        rows = self.conn.execute(
            "SELECT * FROM orders WHERE session_id = ? ORDER BY ts", (session_id,)
        ).fetchall()
        return [
            OrderRow(
                id=r["id"],
                client_order_id=r["client_order_id"],
                symbol=r["symbol"],
                side=r["side"],
                qty=r["qty"],
                order_type=r["order_type"],
                limit_price=r["limit_price"],
                stop_price=r["stop_price"],
                tag=r["tag"],
                tif=r["tif"],
                ts=r["ts"],
                strategy_id=r["strategy_id"],
                session_id=r["session_id"],
            )
            for r in rows
        ]
