
---

# Trading System 

A production-oriented layout for:

* **Backtests** in Backtrader (research only)
* **Live streaming & execution** with IBKR (equities) and cTrader (FX)
* **Risk, sizing, routing, and PnL** per strategy via virtual books
* **Control** via Telegram bot and optional HTTP API

---

## Directory Layout

```text
trader/
  core/
    events.py
    clock.py
  data/
    ibkr_stream.py
    ctrader_stream.py
    bar_builder.py
    store.py
  strategy/
    features.py
    signals.py
  exec/
    risk.py
    router.py
    reconcile.py
  portfolio/
    book.py
    pnl.py
  interfaces/
    telegram_bot.py
    http_api.py
  research/               # your Backtrader notebooks/scripts live here
```

---

## Core

### `core/events.py`

Canonical, broker-agnostic event models.

```python
@dataclass
class Tick: ts, symbol, venue, bid, ask, last, size

@dataclass
class Bar: ts, symbol, open, high, low, close, volume, n_ticks

@dataclass
class Signal: ts, symbol, target_pos, tag, meta=None

@dataclass
class Target: symbol, target_qty, tif="DAY", tag=None

@dataclass
class Order:
    client_order_id, symbol, side, qty, order_type,
    limit_price=None, stop_price=None, tag=None, tif="DAY"

@dataclass
class Fill: order_id, symbol, side, qty, price, fee, ts, tag

@dataclass
class Position: symbol, qty, avg_price, tag
@dataclass
class AccountState: ts, equity, cash, margin, buying_power
@dataclass
class Heartbeat: ts, source, ok: bool, latency_ms: float
@dataclass
class Command: ts, name, args: dict
```

### `core/clock.py`

Unified timekeeping and trading calendar helpers.

* `now_utc() -> pd.Timestamp`
* `MarketClock(calendar="24x5", bar_seconds=60)`

  * `next_bar_time(last_ts) -> pd.Timestamp`
  * `is_trading_time(ts) -> bool`
  * `sleep_until(ts)` *(async)*

---

## Data

### `data/ibkr_stream.py`

IBKR connectivity via `ib_insync`.

* `IBKRStream.connect(host, port, client_id, readonly=True)`
* `IBKRStream.subscribe_quotes(contracts) -> AsyncIterator[Tick]`
* `IBKRStream.req_tickbypick(kind)` *(optional granular stream)*
* `IBKRStream.normalize_contract(symbol, exchange, currency) -> Contract`
* `IBKRStream.close()`
* Helpers: `ibkr_error_handler(e)`, pacing/throttle utilities

### `data/ctrader_stream.py`

cTrader Open API (WS + OAuth). Use for quotes; optionally for orders (or FIX if available).

* `CTraderStream.auth(client_id, client_secret, account_id)`
* `CTraderStream.connect_ws()`
* `CTraderStream.subscribe_quotes(symbols) -> AsyncIterator[Tick]`
* `CTraderStream.place_order(order: Order) -> broker_order_id`
* `CTraderStream.cancel_order(broker_order_id)`
* `CTraderStream.positions() -> list[Position]`
* `CTraderStream.close()`

### `data/bar_builder.py`

Resample ticks into bars with the **same rules** as backtests.

* `BarBuilder(bar_seconds=60, method="last", vwap=False)`

  * `on_tick(tick: Tick) -> list[Bar]` *(emits completed bars)*
  * `flush(force=False) -> list[Bar]`
  * `set_clock(clock: MarketClock)`

### `data/store.py`

Persistence layer (Parquet/DB) for ticks, bars, fills, marks.

* `append_tick(tick: Tick)`
* `append_bar(bar: Bar)`
* `append_fill(fill: Fill)`
* `load_bars(symbol, start, end, timeframe) -> pd.DataFrame`
* `last_bar(symbol, timeframe) -> Bar | None`

---

## Strategy

### `strategy/features.py`

Shared feature engineering (research & live).

* `ema(series, span)`
* `atr(high, low, close, n)`
* `vol_park(close, n)` *(realized vol)*
* `zscore(series, n)`
* `feature_pipeline(bars_df) -> pd.DataFrame`

### `strategy/signals.py`

Pure signal functions: **bars/features → target positions**.

* `mean_reversion_signal(bars: pd.DataFrame, state: dict) -> dict[symbol, target_pos]`
* `breakout_signal(bars, state) -> dict[...]`
* `registry() -> dict[str, Callable]` *(name → function)*
* `stateful_reset()` *(optional, after reconnect)*

> ✅ Keep these functions *stateless or light-state* so backtest/live parity holds.

---

## Execution

### `exec/risk.py`

Sizing and risk limits.

* `RiskManager(max_leverage=2.0, max_loss_day_bps=150, per_symbol_limit=None, lot_size: dict=None)`

  * `size_orders(equity, targets: list[Target], prices: dict) -> list[Order]`
  * `apply_hard_limits(orders) -> list[Order]`
  * `round_to_lot(order: Order, lot_size) -> Order`
  * `should_halt(pnl_today_bps) -> bool`
* Sizers:

  * `atr_based_size(equity, risk_bps, atr, point_value, stop_mult=1.5) -> int`
  * `vol_target_scale(sigma_target, current_sigma, gross_exposure) -> float`

### `exec/router.py`

Order routing and tagging across venues.

* `OrderRouter(ibkr_client, ctrader_client, tag_builder)`

  * `route(order: Order, venue_hint=None) -> broker_order_id`
  * `cancel(broker_order_id)`
  * `poll_fills() -> list[Fill]`
  * `rebuild_after_restart()`
* Converters:

  * `to_ibkr(order) -> IBKROrderSpec`
  * `to_ctrader(order) -> CTraderOrderSpec`
  * `build_tag(strategy, book, dt) -> str` *(e.g., `STRAT|BOOK|YYYYMMDD`)*

### `exec/reconcile.py`

Cold-start sync between broker reality and local book.

* `fetch_broker_state() -> (list[Position], AccountState)`
* `reconcile(local_positions, broker_positions) -> list[Order]`
* `sync_targets_after_restart(targets) -> list[Order]`

---

## Portfolio & PnL

### `portfolio/book.py`

Virtual sub-portfolios (“books”) by tag.

* `VirtualBook.apply_fill(fill: Fill)`
* `VirtualBook.mark_to_market(prices: dict[symbol, price])`
* `VirtualBook.equity(tag=None) -> float`
* `VirtualBook.positions(tag=None) -> dict[symbol, Position]`
* `VirtualBook.as_dataframe() -> pd.DataFrame`

### `portfolio/pnl.py`

PnL rollups and metrics.

* `compute_intraday_mtm(book: VirtualBook, prices) -> pd.DataFrame`
* `rollup_daily_pnl(fills, marks, fees) -> pd.DataFrame`
* `performance_metrics(returns_series) -> dict`

  * *CAGR, Sharpe, Sortino, max DD, hit rate, avg trade, turnover, fees %*
* `by_tag(returns_df) -> pd.DataFrame`

---

## Interfaces

### `interfaces/telegram_bot.py`

Guarded control surface (allow-list + confirmations).

* `start_bot(token, allow_users: list[str], engine)`
* Commands:

  * `/status` – health, latency, equity by tag, positions
  * `/strategies` – list states
  * `/start <name>` / `/stop <name>`
  * `/risk <name> <bps>`
  * `/alloc <name> <weight>`
  * `/orders <n>`
  * `/panic` – global flat (double-confirm)

### `interfaces/http_api.py`

Optional internal REST.

* `GET /health`
* `GET /status`
* `POST /strategy/start {name}`
* `POST /strategy/stop {name}`
* `POST /risk {name, bps}`
* `POST /panic`

---

## Data Flow (TL;DR)

1. **Streams**: `ibkr_stream.py` / `ctrader_stream.py` → `Tick`
2. **Bars**: `bar_builder.py` → `Bar` (same rules as backtests)
3. **Signals**: `signals.py` → `Signal/Target`
4. **Sizing & Risk**: `risk.py` → `Order`
5. **Routing**: `router.py` → IBKR / cTrader (tagged)
6. **Fills/Positions** → `book.py` → `pnl.py` (metrics)
7. **Control**: Telegram/HTTP → engine commands

---

## Configuration

* **IBKR**: host/port/clientId; make sure market-data subscriptions exist.
* **cTrader**: OAuth client id/secret + account id; WS endpoint; (optional FIX creds).
* **Env Vars** (example):
  `IB_HOST`, `IB_PORT`, `IB_CLIENT_ID`, `CTRADER_CLIENT_ID`, `CTRADER_SECRET`, `CTRADER_ACCOUNT_ID`

---

## Backtrader → Live Parity Tips

* One **symbol map & point-value** source of truth.
* Same **bar-building** and **trading hours**.
* Model **slippage & fees** similarly in research.
* Export **pure signal functions**; avoid Backtrader order objects in live.

---

## Risk & Safety

* **Hard stops**: max daily loss (bps), max leverage, per-symbol caps.
* **Kill-switch**: `/panic` → set all targets flat.
* **Stale feed** detection (e.g., >2s without tick), auto-pause strategies.
* **Reconciliation** on restart before new orders go out.

---

## Metrics to Track (per tag/strategy)

* Daily returns, CAGR, Sharpe/Sortino
* Max drawdown & length
* Hit rate, avg win/loss, payoff
* Turnover, implicit/explicit costs

---

## Appendix — Order Lifecycle (Narrative)

1. **Bar t** arrives → **Signal** computes target pos.
2. **RiskManager** sizes & checks limits → **Order(s)**.
3. **Router** tags & routes to the right venue → **Ack**.
4. **Broker** fills → **VirtualBook** updates positions & MTM.
5. **PnL** rolls intraday/daily; metrics update.
6. **Telegram/HTTP** can pause/start, tweak risk, or trigger `/panic`.

---

