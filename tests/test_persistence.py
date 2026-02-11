"""Tests for the SQLite persistence layer."""
import pytest

from trader.persistence.database import Database
from trader.persistence.models import (
    BacktestResultRow,
    EquitySnapshotRow,
    FillRow,
    OrderRow,
    PositionSnapshotRow,
)
from trader.persistence.repositories import (
    BacktestResultRepository,
    EquityRepository,
    FillRepository,
    OrderRepository,
    PositionRepository,
)


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "test.db")
    d.connect_sync()
    yield d
    d.close_sync()


def test_schema_creation(db):
    """All expected tables are created on first connect."""
    conn = db.connect_sync()
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    tables = {r["name"] for r in rows}
    assert "fills" in tables
    assert "equity_snapshots" in tables
    assert "position_snapshots" in tables
    assert "backtest_results" in tables
    assert "orders" in tables
    assert "schema_version" in tables


def test_schema_version_set(db):
    conn = db.connect_sync()
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    assert row is not None
    assert row["version"] == 1


def test_schema_idempotent(tmp_path):
    """Connecting twice to same DB doesn't error."""
    db = Database(tmp_path / "test.db")
    db.connect_sync()
    db.close_sync()
    db2 = Database(tmp_path / "test.db")
    db2.connect_sync()
    row = db2.connect_sync().execute("SELECT version FROM schema_version").fetchone()
    assert row["version"] == 1
    db2.close_sync()


# -- FillRepository --

def test_fill_insert_and_query(db):
    repo = FillRepository(db.connect_sync())
    fill = FillRow(
        id=None,
        order_id="ord-1",
        symbol="USDJPY",
        side="BUY",
        qty=100_000,
        price=150.50,
        fee=2.0,
        ts="2025-01-15T10:00:00+00:00",
        strategy_id="gotobi",
        session_id="session-1",
    )
    row_id = repo.insert(fill)
    assert row_id is not None

    fills = repo.get_by_session("session-1")
    assert len(fills) == 1
    assert fills[0].symbol == "USDJPY"
    assert fills[0].qty == 100_000
    assert fills[0].strategy_id == "gotobi"


def test_fill_get_by_symbol(db):
    repo = FillRepository(db.connect_sync())
    for sym in ("USDJPY", "EURUSD", "USDJPY"):
        repo.insert(FillRow(
            id=None, order_id="o", symbol=sym, side="BUY",
            qty=1, price=1.0, fee=0, ts="2025-01-01T00:00:00+00:00",
            strategy_id=None, session_id="s1",
        ))
    assert len(repo.get_by_symbol("USDJPY")) == 2
    assert len(repo.get_by_symbol("EURUSD")) == 1
    assert len(repo.get_by_symbol("USDJPY", session_id="s1")) == 2


def test_fill_batch_insert(db):
    repo = FillRepository(db.connect_sync())
    fills = [
        FillRow(id=None, order_id=f"o{i}", symbol="USDJPY", side="BUY",
                qty=1, price=1.0, fee=0, ts=f"2025-01-0{i+1}T00:00:00+00:00",
                strategy_id=None, session_id="s1")
        for i in range(5)
    ]
    repo.insert_batch(fills)
    assert len(repo.get_by_session("s1")) == 5


# -- EquityRepository --

def test_equity_insert_and_curve(db):
    repo = EquityRepository(db.connect_sync())
    for i in range(5):
        repo.insert(EquitySnapshotRow(
            id=None,
            ts=f"2025-01-01T0{i}:00:00+00:00",
            equity=100_000 + i * 1000,
            cash=50_000,
            strategy_id=None,
            session_id="s1",
        ))
    rows = repo.get_curve("s1")
    assert len(rows) == 5
    assert rows[0].equity == 100_000
    assert rows[4].equity == 104_000


def test_equity_curve_with_date_range(db):
    repo = EquityRepository(db.connect_sync())
    for i in range(10):
        repo.insert(EquitySnapshotRow(
            id=None,
            ts=f"2025-01-{i+1:02d}T00:00:00+00:00",
            equity=100_000 + i * 100,
            cash=50_000,
            strategy_id=None,
            session_id="s1",
        ))
    rows = repo.get_curve("s1", start="2025-01-03T00:00:00+00:00", end="2025-01-07T00:00:00+00:00")
    assert len(rows) == 5


def test_equity_curve_as_df(db):
    repo = EquityRepository(db.connect_sync())
    repo.insert(EquitySnapshotRow(
        id=None, ts="2025-01-01T00:00:00+00:00",
        equity=100_000, cash=50_000, strategy_id=None, session_id="s1",
    ))
    repo.insert(EquitySnapshotRow(
        id=None, ts="2025-01-02T00:00:00+00:00",
        equity=101_000, cash=50_000, strategy_id=None, session_id="s1",
    ))
    df = repo.get_curve_as_df("s1")
    assert len(df) == 2
    assert "equity" in df.columns
    assert df.index.name == "ts"


def test_equity_curve_by_strategy(db):
    repo = EquityRepository(db.connect_sync())
    repo.insert(EquitySnapshotRow(
        id=None, ts="2025-01-01T00:00:00+00:00",
        equity=100_000, cash=50_000, strategy_id="gotobi", session_id="s1",
    ))
    repo.insert(EquitySnapshotRow(
        id=None, ts="2025-01-01T00:00:00+00:00",
        equity=200_000, cash=100_000, strategy_id=None, session_id="s1",
    ))
    strat_rows = repo.get_curve("s1", strategy_id="gotobi")
    assert len(strat_rows) == 1
    assert strat_rows[0].equity == 100_000

    portfolio_rows = repo.get_curve("s1")
    assert len(portfolio_rows) == 1
    assert portfolio_rows[0].equity == 200_000


# -- PositionRepository --

def test_position_snapshot_roundtrip(db):
    repo = PositionRepository(db.connect_sync())
    repo.insert(PositionSnapshotRow(
        id=None, symbol="USDJPY", qty=100_000, avg_price=150.0,
        mtm_price=150.5, unrealized_pnl=50_000,
        ts="2025-01-01T00:00:00+00:00", strategy_id="gotobi", session_id="s1",
    ))
    latest = repo.get_latest("s1")
    assert len(latest) == 1
    assert latest[0].symbol == "USDJPY"
    assert latest[0].avg_price == 150.0


# -- BacktestResultRepository --

def test_backtest_result_roundtrip(db):
    repo = BacktestResultRepository(db.connect_sync())
    repo.insert(BacktestResultRow(
        id=None, session_id="bt-1", strategy_name="GotobiStrategy",
        started_at="2025-01-01", ended_at="2025-06-01",
        config_json='{"instrument_id": "USD/JPY.SIM"}',
        metrics_json='{"sharpe": 1.5}',
        total_return=0.15, sharpe=1.5, max_drawdown=-0.05,
    ))
    result = repo.get_by_session("bt-1")
    assert result is not None
    assert result.strategy_name == "GotobiStrategy"
    assert result.sharpe == 1.5

    all_results = repo.get_all()
    assert len(all_results) == 1


# -- OrderRepository --

def test_order_insert_and_query(db):
    repo = OrderRepository(db.connect_sync())
    repo.insert(OrderRow(
        id=None, client_order_id="co-1", symbol="USDJPY", side="BUY",
        qty=100_000, order_type="MARKET", limit_price=None, stop_price=None,
        tag="gotobi", tif="DAY", ts="2025-01-01T00:00:00+00:00",
        strategy_id="gotobi", session_id="s1",
    ))
    orders = repo.get_by_session("s1")
    assert len(orders) == 1
    assert orders[0].order_type == "MARKET"
