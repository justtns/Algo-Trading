# ToDo Rebaseline (Feb 11, 2026 to Mar 11, 2026): Live Reliability First

## Summary
- Rebaseline `ToDo.md` around live reliability first, keeping section-based structure.
- Mark already-delivered items as done (`[x]`) based on current code and tests.
- Prioritize the next month as reliability hardening -> observability -> read-only interfaces -> control interfaces.

## Validation Baseline
- [x] `pytest -q` passed (`104 passed`) on Feb 11, 2026.

## Live Reliability (P0)
- [ ] Enforce IBKR/IDEALPRO minimum effective FX order size in live strategies and demo configs (avoid repeated odd-lot warnings on small sizes).
- [ ] Add deterministic shutdown flatten flow so strategy stop waits for close-order completion and leaves no residual open positions/orders.
- [ ] Add explicit handling/classification for IBKR warnings/errors seen in logs (code `399` odd-lot warning, code `162` historical-query cancellation during stop).
- [ ] Add live smoke acceptance check: zero residual orders/positions at node shutdown across 3 consecutive runs.
- [ ] Document live runbook constraints in docs (minimum sizes, expected broker warnings, shutdown behavior).

## Market Data
- [x] Add retry logic and error handling to IBKR data fetcher.
- [x] Fix MT5 tick polling 5-second lookback gap risk.
- [x] Improve IBKR request timeout scaling for large historical ranges.
- [x] Add data quality checks (gap detection, stale data alerts).
- [ ] Evaluate additional data sources (Databento, Tiingo, Yahoo fallback) for redundancy.
- [ ] Centralize provider routing into a unified `DataService`.
- [ ] Wire gap/stale detection into runtime heartbeat alerting (not only offline helpers).

## HTTP Frontend
- [ ] Implement FastAPI app in `trader/interfaces/http_api.py`.
- [ ] Ship read-only endpoints first: `GET /health`, `GET /status`, `GET /equity`.
- [ ] Add dashboard page for overall/per-strategy equity curves and drawdown.
- [ ] Add WebSocket stream for equity/position updates.
- [ ] Add auth (API key) before control endpoints.
- [ ] Add control endpoints only after P0 reliability tasks are complete.

## Telegram Bot
- [ ] Implement bot in `trader/interfaces/telegram_bot.py`.
- [ ] Ship read-only commands first: `/status`, `/equity`.
- [ ] Add alerting commands: `/signals` subscription, feed stale/error alerts.
- [ ] Add control commands (`/start`, `/stop`, `/allocate`) after reliability hardening is complete.
- [ ] Add periodic PnL summary with configurable interval.

## Scanner
- [ ] Add abilty to calculate residuals and plot against different time frame residuals for PCA moves. 

## Multi-Strategy Orchestration
- [ ] Add runtime strategy lifecycle manager (start/stop/pause idempotent operations).
- [ ] Add dynamic capital reallocation at runtime.
- [ ] Add cross-strategy risk limits (max exposure, concentration/correlation checks).
- [x] Keep per-strategy and portfolio equity tracking with persistence as baseline.
- [ ] Add orchestration-level health/status snapshot for API/bot consumption.

## Equity Curves & Visualization
- [x] Build equity curve tracker (per-strategy + portfolio).
- [x] Persist equity snapshots to database.
- [x] Generate Plotly charts (equity/drawdown).
- [ ] Expose chart outputs through HTTP and Telegram export paths.

## Persistence
- [x] Extend store to persist fills/positions to SQLite.
- [x] Store equity curve history for charting.
- [x] Store backtest results with metadata.
- [ ] Finalize parquet bar storage workflow and retention/indexing rules in docs/tests.
- [ ] Add migration/versioning notes for schema evolution.

## Testing
- [ ] Add unit tests for `make_fx_pair` instrument construction.
- [ ] Add integration backtest round-trip test on USDJPY parquet with `BacktestEngine`.
- [ ] Add regression test comparing Gotobi trade dates/PnL vs legacy baseline.
- [ ] Add tests for minimum-order-size enforcement and quantity normalization.
- [ ] Add stop/partial-fill/shutdown reconciliation integration tests (no residual position/order).

## Live Testing
- [x] Smoke test IBKR adapter completed (log artifact available).
- [x] Smoke test MT5 adapter completed (log artifact available).
- [ ] Re-run smoke tests after P0 reliability fixes; require clean shutdown with no residuals.
- [ ] Add automated post-run log assertions in notebook workflow.

## Observability
- [ ] Add structured logging around adapter connectivity, order lifecycle, and data-quality alerts.
- [ ] Add feed heartbeat monitoring for all active venues.
- [ ] Expose health endpoint backed by adapter/feed freshness state.
- [ ] Add severity mapping for known broker codes so expected warnings are not treated as unknown failures.

## One-Month Execution Sequence
1. Week of Feb 11, 2026: complete all `Live Reliability (P0)` items.
2. Week of Feb 18, 2026: add heartbeat/observability and reliability integration tests.
3. Week of Feb 25, 2026: implement HTTP read-only API (`/health`, `/status`, `/equity`) and chart exposure.
4. Week of Mar 4, 2026: implement Telegram read-only + alerting; defer control commands unless all P0 acceptance criteria remain green.

## Important API/Interface/Type Additions Planned
- `trader/interfaces/http_api.py`: add `GET /health`, `GET /status`, `GET /equity` (public read API baseline).
- `trader/interfaces/telegram_bot.py`: add `/status`, `/equity`, `/signals` command handlers first.
- Strategy/config surface: add explicit minimum-order-size enforcement policy and shutdown flatten timeout settings for live strategies.
- Observability contract: add normalized broker warning/error classification output for downstream API/bot health reporting.

## Test Cases and Acceptance Scenarios
1. Minimum-size guard: submitting below broker minimum is either auto-adjusted deterministically or rejected with a clear strategy log/error.
2. Partial-fill lifecycle: entry partial fill + timed exit + stop sequence leaves no stale pending state.
3. Shutdown reconciliation: strategy stop always exits flat and no residual accepted/open orders remain.
4. Broker-code handling: code `399` and stop-time `162` are classified correctly and not emitted as unknown/unhandled.
5. Health endpoint: returns degraded status when feed heartbeat or stale-data check fails.
6. End-to-end smoke: 3 consecutive live demo runs complete with zero residual orders/positions and expected log signatures only.

## Assumptions and Defaults
- Planning horizon is one month (Feb 11, 2026 to Mar 11, 2026).
- `ToDo.md` remains section-based (not converted to top-10 only).
- Live reliability has precedence over new control interfaces.
- Already-implemented capabilities stay visible in `ToDo.md` as checked items (`[x]`) rather than being removed.
