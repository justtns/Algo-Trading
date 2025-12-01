# Trading System Overview

## Directory Layout

```text
trader/
  core/           # clocks, event models
  data/           # streams + normalization (pipeline.py), bar builder, store, IBKR adapter
  strategy/       # strategies, features, signals (Gotobi lives here)
  exec/           # TradeRunner, router, risk/reconcile helpers
  portfolio/      # store/book/PnL helpers
  interfaces/     # control surfaces (Telegram/HTTP stubs)
  research/       # notebooks/scripts (e.g., tests/traderunner_demo.ipynb)
config/           # contract sizing (e.g., contracts.json)
historical_data_services/  # historical fetch utilities (IBKR, Polygon)
data/             # sample parquet data (not tracked)
tests/            # demo notebook
```

## Architecture (mapped to the phases)

1) **Data Handler**  
   - `trader.data.pipeline.DataNormalizer/DataHandler` normalize parquet/CSV to OHLCV; `DataStreamer` + `StreamingOHLCVFeed` convert queues into Backtrader feeds.  
   - `trader.data.bar_builder` turns ticks into bars with consistent rules.  
   - Optional FX inversion to keep account in a base currency (RunnerConfig).  
   - Historical pulls via `trader.data.ibkr_stream.IBKRHistoryService` (wraps `historical_data_services/ibkr_data_fetch.py`).
   - Live streams: `trader.data.ibkr_stream.IBKRLiveStreamer` (ib_insync real-time bars) and `trader.data.ctrader_stream.stream_ctrader_quotes` (bridge your cTrader quote source into `DataStreamer` via the `BarBuilder`).

2) **Strategy**  
   - User strategies in `trader.strategy` (e.g., `GotobiBT`), shared features/signals in `features.py` / `signals.py`.

3) **TradeRunner Builder/Pool**  
   - `trader.exec.traderunner` builds Cerebro per `StrategySpec`, supports multiple strategies/analyzers per runner, contract sizing from `config/contracts.json`, FX inversion, and async execution.  
   - `RiskEstimator` enforces simple limits / sizer selection.

4) **Router (exec phase)**  
   - `trader.exec.router.OrderRouter` performs risk check then forwards to a broker sender callable.  
   - Additional risk sizing helpers live in `trader.exec.risk.RiskManager`.

5) **Store/Book (DB phase)**  
   - `trader.portfolio.store.TickerStore` tracks fills/positions/MTM; `book.py` and `pnl.py` placeholders for richer rollups; `data.store.DataStore` can persist bars to parquet.

6) **Interfaces**  
   - Stubs in `trader.interfaces.telegram_bot` and `http_api` to wire control surfaces to your engine.

## Quick Start (demo)

1. Install `backtrader` and `pandas`.  
2. Add repo root to `PYTHONPATH`.  
3. Run `tests/traderunner_demo.ipynb`: streams the USDJPY parquet via `DataStreamer` queue, runs two `GotobiBT` legs. Trade size is in **contracts** scaled by `config/contracts.json` (default 100k lots). FX inversion keeps account in USD if quote differs.

## Notes
- `backend/__init__.py` is a compatibility shim that re-exports modules from `trader/`.
- Fill in live wiring for cTrader/IBKR streaming, risk rules, and interfaces as needed.
- Historical fetchers remain in `historical_data_services/` and are re-exported via `trader.data.ibkr_stream`.
