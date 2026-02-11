from types import SimpleNamespace

from trader.strategy.buy_and_hold import OneMinuteBuyHoldStrategy


class _DummyStrategy:
    def __init__(self) -> None:
        self._entry_ts_ns = 123
        self._entered = True
        self._entry_order_id = None
        self._exit_order_id = None
        self.exit_task_canceled = False
        self.log_messages: list[str] = []
        self.log = SimpleNamespace(
            info=self.log_messages.append,
            warning=self.log_messages.append,
        )

    def _cancel_exit_task(self) -> None:
        self.exit_task_canceled = True


class _DummyStopStrategy(_DummyStrategy):
    def __init__(self) -> None:
        super().__init__()
        self.bar_type = "EURUSD.MT5-5-SECOND-MID-EXTERNAL"
        self.close_tags: list[str] = []
        self.unsubscribed: list[str] = []

    def _close_position(self, tag: str) -> None:
        self.close_tags.append(tag)

    def unsubscribe_bars(self, bar_type: str) -> None:
        self.unsubscribed.append(bar_type)


class _DummyLoopStrategy(_DummyStrategy):
    def __init__(self) -> None:
        super().__init__()
        self._entry_ts_ns = None
        self._entry_order_id = None
        self._exit_order_id = None
        self.trade_qty = 10.0
        self.instrument = SimpleNamespace(size_precision=2)
        self.instrument_id = "EURUSD.MT5"
        self.submitted: list[object] = []
        self._order_counter = 0
        self.order_factory = SimpleNamespace(market=self._build_order)

    def _build_order(self, **kwargs):
        self._order_counter += 1
        return SimpleNamespace(client_order_id=f"O-{self._order_counter}", **kwargs)

    def submit_order(self, order, position_id=None, client_id=None) -> None:
        self.submitted.append((order, position_id, client_id))

    def _schedule_time_exit(self) -> None:
        return


def test_on_position_closed_resets_state_for_next_entry_cycle() -> None:
    strategy = _DummyStrategy()
    event = SimpleNamespace(
        instrument_id="EURUSD.MT5",
        realized_pnl="0.10 USD",
    )

    OneMinuteBuyHoldStrategy.on_position_closed(strategy, event)

    assert strategy.exit_task_canceled is True
    assert strategy._entry_ts_ns is None
    assert strategy._entered is False
    assert strategy.log_messages


def test_on_stop_resets_state_for_restart_cycle() -> None:
    strategy = _DummyStopStrategy()

    OneMinuteBuyHoldStrategy.on_stop(strategy)

    assert strategy.exit_task_canceled is True
    assert strategy.close_tags == ["STOP"]
    assert strategy.unsubscribed == [strategy.bar_type]
    assert strategy._entry_ts_ns is None
    assert strategy._entered is False


def test_reenters_after_position_closed_event() -> None:
    strategy = _DummyLoopStrategy()

    first_bar = SimpleNamespace(ts_event=1_000_000_000)
    second_bar = SimpleNamespace(ts_event=2_000_000_000)
    close_event = SimpleNamespace(
        instrument_id="EURUSD.MT5",
        realized_pnl="0.10 USD",
    )

    OneMinuteBuyHoldStrategy.on_bar(strategy, first_bar)
    assert len(strategy.submitted) == 1
    assert strategy._entry_order_id == "O-1"
    assert strategy.submitted[0][1] is None

    OneMinuteBuyHoldStrategy.on_position_closed(strategy, close_event)
    assert strategy._entry_ts_ns is None

    OneMinuteBuyHoldStrategy.on_bar(strategy, second_bar)
    assert len(strategy.submitted) == 2
    assert strategy._entry_order_id == "O-2"
    assert strategy.submitted[1][1] is None


def test_retries_entry_after_rejection() -> None:
    strategy = _DummyLoopStrategy()
    first_bar = SimpleNamespace(ts_event=1_000_000_000)
    second_bar = SimpleNamespace(ts_event=2_000_000_000)

    OneMinuteBuyHoldStrategy.on_bar(strategy, first_bar)
    assert strategy._entry_order_id == "O-1"

    reject_event = SimpleNamespace(client_order_id="O-1", reason="broker reject")
    OneMinuteBuyHoldStrategy.on_order_rejected(strategy, reject_event)
    assert strategy._entry_order_id is None
    assert strategy._entry_ts_ns is None
    assert strategy._entered is False

    OneMinuteBuyHoldStrategy.on_bar(strategy, second_bar)
    assert strategy._entry_order_id == "O-2"


def test_submit_order_uses_explicit_exec_client_id_when_configured() -> None:
    strategy = _DummyLoopStrategy()
    strategy.exec_client_id = "IDEALPRO"
    order = strategy._build_order(
        instrument_id=strategy.instrument_id,
        order_side="BUY",
        quantity=1,
        time_in_force="IOC",
    )

    OneMinuteBuyHoldStrategy._submit_order(strategy, order)

    assert strategy.submitted[-1][2] == "IDEALPRO"


def test_retries_entry_after_canceled() -> None:
    strategy = _DummyLoopStrategy()
    first_bar = SimpleNamespace(ts_event=1_000_000_000)
    second_bar = SimpleNamespace(ts_event=2_000_000_000)

    OneMinuteBuyHoldStrategy.on_bar(strategy, first_bar)
    assert strategy._entry_order_id == "O-1"

    cancel_event = SimpleNamespace(
        client_order_id="O-1",
        instrument_id="EURUSD.MT5",
    )
    OneMinuteBuyHoldStrategy.on_order_canceled(strategy, cancel_event)
    assert strategy._entry_order_id is None
    assert strategy._entry_ts_ns is None
    assert strategy._entered is False

    OneMinuteBuyHoldStrategy.on_bar(strategy, second_bar)
    assert strategy._entry_order_id == "O-2"
