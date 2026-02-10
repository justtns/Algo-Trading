## TODO (remaining work)

### Testing
- Add unit tests for `GotobiCalendar` date resolution (weekends, holidays, month boundaries)
- Add unit tests for `make_fx_pair` instrument construction
- Add integration test: full backtest round-trip with `BacktestEngine` on USDJPY parquet data
- Add integration test: MT5 adapter with mocked `MetaTrader5` module
- Run backtest regression: compare Gotobi trade dates/PnL between old Backtrader and new NautilusTrader

### Live Testing
- Smoke test IBKR adapter: connect TradingNode to paper account, verify bar subscription and order submission
- Smoke test MT5 adapter: connect TradingNode to demo account, verify tick streaming and order routing

### Persistence
- Extend `TickerStore` to persist fills/positions to a database (SQLite/Postgres)
- Add parquet bar storage via data catalog

### Interface Hookups
- Wire portfolio to `trader.interfaces.telegram_bot` for live PnL/positions
- Wire portfolio to `trader.interfaces.http_api` for REST queries

### Observability
- Add structured logging around adapter connections, order events, and data gaps
- Add heartbeat monitoring for each data feed
