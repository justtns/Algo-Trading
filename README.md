# Trading System Overview

## Directory Layout

```text
trader/
  core/           # clocks, event models
  data/           # streams + normalization (pipeline.py), bar builder stubs
  strategy/       # strategies, features, signals (Gotobi lives here)
  exec/           # TradeRunner, router, risk/reconcile stubs
  portfolio/      # store/book/PnL helpers
  interfaces/     # control surfaces (Telegram/HTTP stubs)
  research/       # notebooks/scripts (e.g., tests/traderunner_demo.ipynb)
config/           # contract sizing (e.g., contracts.json)
historical_data_services/  # historical fetch utilities (IBKR, Polygon)
data/             # sample parquet data (not tracked)
tests/            # demo notebook
```

## Architecture (maps to the diagram)

1) **Data Handler**  
   - `trader.data.pipeline.DataNormalizer/DataHandler` normalize parquet/CSV to OHLCV; `DataStreamer` + `StreamingOHLCVFeed` convert queues into Backtrader feeds.  
   - Optional FX inversion to keep account in a base currency (RunnerConfig).

2) **Strategy**  
   - User strategies in `trader.strategy` (e.g., `GotobiBT`), shared features/signals stubs in `features.py` / `signals.py`.

3) **TradeRunner Builder/Pool**  
   - `trader.exec.traderunner` builds Cerebro per `StrategySpec`, supports multiple strategies/analyzers per runner, contract sizing from `config/contracts.json`, FX inversion, and async execution.  
   - `RiskEstimator` enforces simple limits / sizer selection.

4) **Router (exec phase)**  
   - `trader.exec.router.OrderRouter` performs risk check then forwards to a broker sender callable (stub to be wired to IBKR/cTrader).

5) **Store/Book (DB phase)**  
   - `trader.portfolio.store.TickerStore` tracks fills/positions/MTM; `book.py` and `pnl.py` are placeholders for richer rollups.

## Quick Start (demo)

1. Ensure `backtrader` and `pandas` are installed.  
2. Add repo root to `PYTHONPATH`.  
3. Run the streaming demo notebook: `tests/traderunner_demo.ipynb`  
   - Streams the USDJPY parquet via `DataStreamer` queue.  
   - Uses two `GotobiBT` legs; trade_size is in **contracts** and scaled by `config/contracts.json` (default 100k lots).  
   - `RunnerConfig` can invert FX to base USD if quote currency differs.

## Notes
- Backward-compat: `backend/__init__.py` re-exports the new modules under `trader/`.
- Populate stubs in `trader/core`, `trader/data/*_stream.py`, `trader/exec/risk.py`, `trader/interfaces/*` with your live wiring and controls.
- Historical fetchers remain in `historical_data_services/` and are re-exported via `trader.data.ibkr_stream`.
