"""Tests for TickerStore write-through persistence."""
import pytest

from trader.persistence.database import Database
from trader.persistence.repositories import FillRepository, PositionRepository
from trader.portfolio.store import Fill, TickerStore


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "test.db")
    d.connect_sync()
    yield d
    d.close_sync()


def test_store_without_db_still_works():
    """Backwards compat: TickerStore with no DB works identically."""
    store = TickerStore()
    store.record_fill(Fill(symbol="USDJPY", side="BUY", size=100_000, price=150.0))
    assert len(store.fills) == 1
    assert "USDJPY" in store.positions
    assert store.positions["USDJPY"].size == 100_000


def test_record_fill_writes_to_db(db):
    store = TickerStore(db=db, session_id="s1")
    store.record_fill(Fill(
        symbol="USDJPY", side="BUY", size=100_000, price=150.0, strategy_id="gotobi"
    ))

    # Check in-memory
    assert len(store.fills) == 1
    assert "USDJPY" in store.positions

    # Check DB
    repo = FillRepository(db.connect_sync())
    db_fills = repo.get_by_session("s1")
    assert len(db_fills) == 1
    assert db_fills[0].symbol == "USDJPY"
    assert db_fills[0].qty == 100_000
    assert db_fills[0].strategy_id == "gotobi"


def test_multiple_fills_persisted(db):
    store = TickerStore(db=db, session_id="s1")
    store.record_fill(Fill(symbol="USDJPY", side="BUY", size=100_000, price=150.0))
    store.record_fill(Fill(symbol="EURUSD", side="SELL", size=50_000, price=1.10))
    store.record_fill(Fill(symbol="USDJPY", side="SELL", size=100_000, price=151.0))

    repo = FillRepository(db.connect_sync())
    db_fills = repo.get_by_session("s1")
    assert len(db_fills) == 3


def test_snapshot_positions(db):
    store = TickerStore(db=db, session_id="s1")
    store.record_fill(Fill(symbol="USDJPY", side="BUY", size=100_000, price=150.0))
    store.record_fill(Fill(symbol="EURUSD", side="BUY", size=50_000, price=1.10))

    store.snapshot_positions(strategy_id="gotobi")

    repo = PositionRepository(db.connect_sync())
    positions = repo.get_latest("s1")
    assert len(positions) == 2
    symbols = {p.symbol for p in positions}
    assert "USDJPY" in symbols
    assert "EURUSD" in symbols


def test_snapshot_without_db_is_noop():
    """snapshot_positions does nothing when db is None."""
    store = TickerStore()
    store.record_fill(Fill(symbol="USDJPY", side="BUY", size=100_000, price=150.0))
    store.snapshot_positions()  # should not raise


def test_session_id_auto_generated():
    store = TickerStore()
    assert len(store.session_id) > 0

    store2 = TickerStore(session_id="my-session")
    assert store2.session_id == "my-session"
