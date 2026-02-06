# Trading System Overview

## Directory Layout

```text
trader/
  core/           # clocks, event models, configuration loader
  data/           # streams + normalization (pipeline.py), bar builder, store, IBKR/MT5 adapters
  strategy/       # strategies, features, signals (Gotobi lives here)
  exec/           # TradeRunner, router, risk/reconcile helpers, MetaTrader broker
  portfolio/      # store/book/PnL helpers
  interfaces/     # control surfaces (Telegram/HTTP stubs)
  research/       # notebooks/scripts (e.g., tests/traderunner_demo.ipynb)
config/           # system configuration (config.json), contract sizing (contracts.json)
historical_data_services/  # historical fetch utilities (IBKR, Polygon)
examples/         # demo scripts for MetaTrader and other integrations
data/             # sample parquet data (not tracked)
tests/            # demo notebook
```

## Architecture (mapped to the phases)

1) **Data Handler**  
   - `trader.data.pipeline.DataNormalizer/DataHandler` normalize parquet/CSV to OHLCV; `DataStreamer` + `StreamingOHLCVFeed` convert queues into Backtrader feeds.  
   - `trader.data.bar_builder` turns ticks into bars with consistent rules.  
   - Optional FX inversion to keep account in a base currency (RunnerConfig).  
   - Historical pulls via `trader.data.ibkr_stream.IBKRHistoryService` (wraps `historical_data_services/ibkr_data_fetch.py`).
   - Live streams: `trader.data.ibkr_stream.IBKRLiveStreamer` (ib_insync real-time bars), `trader.data.ctrader_stream.stream_ctrader_quotes` (bridge your cTrader quote source into `DataStreamer` via the `BarBuilder`), and `trader.data.metatrader_stream.MetaTraderLiveStreamer` (poll ticks from an MT5 terminal and roll them into bars using the shared broker session).
   - Live orders: `trader.exec.metatrader.MetaTraderBroker/build_metatrader_router` forward signals through `OrderRouter` into MT5; reuse the same broker instance for streaming + orders to keep a single session.

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

## MetaTrader 5 Integration

The system includes full MetaTrader 5 support for live trading:

### Setup

1. **Install MetaTrader 5 package:**
   ```bash
   pip install MetaTrader5
   ```

2. **Configure connection:**
   Edit `config/config.json` with your MT5 credentials:
   ```json
   {
     "metatrader": {
       "login": 12345678,
       "password": "your_password",
       "server": "YourBroker-Server",
       "path": null
     }
   }
   ```
   - For local terminal connections, set all credentials to `null`
   - For remote connections, provide login, password, and server

3. **Run the demo:**
   ```bash
   python examples/metatrader_demo.py
   ```

### Features

- **Connection Management:** Automatic connection handling with credential validation
- **Live Data Streaming:** Real-time tick data aggregated into OHLCV bars
- **Order Execution:** Market, limit, and stop orders via `OrderRouter`
- **Risk Management:** Built-in position and notional limits
- **Shared Sessions:** Single broker instance for streaming and trading

### Usage Example

```python
from trader.core.config import SystemConfig
from trader.exec.metatrader import build_metatrader_router
from trader.data.metatrader_stream import stream_metatrader_ticks
from trader.data.pipeline import DataStreamer

# Load configuration
config = SystemConfig.load("config/config.json")

# Create router for order execution
router = build_metatrader_router(
    login=config.metatrader.login,
    password=config.metatrader.password,
    server=config.metatrader.server,
)

# Stream live data
streamer = DataStreamer()
await stream_metatrader_ticks(
    symbols=["EURUSD", "GBPUSD"],
    streamer=streamer,
    login=config.metatrader.login,
    password=config.metatrader.password,
    server=config.metatrader.server,
)
```

## Notes
- `backend/__init__.py` is a compatibility shim that re-exports modules from `trader/`.
- Fill in live wiring for cTrader/IBKR streaming, risk rules, and interfaces as needed.
- Historical fetchers remain in `historical_data_services/` and are re-exported via `trader.data.ibkr_stream`.
