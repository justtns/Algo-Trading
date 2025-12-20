## TODO (wiring the full live stack)
- **Finalize live feed adapters**
  - IBKR: finish the `trader.data.ibkr_stream.IBKRLiveStreamer` wiring (token/env config, account selection, bar size) and test it end-to-end with `DataStreamer` and the `BarBuilder`.
  - cTrader: connect your quote source to `trader.data.ctrader_stream.stream_ctrader_quotes`, ensuring symbols and timezones match your `contracts.json` entries. # Changed to metatrader
- **Unify feed normalization**
  - Make sure both IBKR and cTrader produce identical `OHLCV` tuples by running them through `trader.data.bar_builder.BarBuilder` with matching bar sizes and through `trader.data. pipeline.DataNormalizer` if currency inversion is needed. # Changed to metatrader
- **Execution and routing**
  - Confirm the `trader.exec.router.OrderRouter` risk checks and sizing (`trader.exec.risk.RiskManager`) align with your margin rules; add broker-specific senders for production.
- **Persistence layer**
  - Extend `trader.portfolio.store.TickerStore` to persist fills/positions/MTM into a database (e.g., SQLite/Postgres) alongside parquet bar storage via `trader.data.store.DataStore`.
  - Add migration/seeding scripts for strategy configs and contract metadata (currently stored in `config/contracts.json`).
- **Interface hookups**
  - Wire the DB-backed portfolio and recent fills into `trader.interfaces.telegram_bot` and `trader.interfaces.http_api` so both surfaces can query live PnL/positions and trigger control actions.
- **Observability**
  - Add structured logging around the feed adapters, router decisions, and DB writes; consider a heartbeat for each feed.
- **Testing**
  - Add integration tests that spin up a mock feed, run a minimal strategy, and assert DB/portfolio state transitions.

## Using the live feeds
The live path mirrors the demo notebook but swaps in real-time adapters. At a high level:

1. **Choose a feed adapter**
   - IBKR: instantiate `trader.data.ibkr_stream.IBKRLiveStreamer` with your `ib_insync` client and desired `bar_size`/`whatToShow` options.
   - cTrader (custom bridge): call `trader.data.ctrader_stream.stream_ctrader_quotes` with your quote source and forward ticks into a shared asyncio queue.

2. **Build bars**
   - Wrap the raw quotes with `trader.data.bar_builder.BarBuilder` to aggregate into your target timeframe; the builder emits completed bars onto the queue consumed by `DataStreamer`.

3. **Normalize and invert if needed**
   - Feed the bar queue into `trader.data.pipeline.DataStreamer`, then into `StreamingOHLCVFeed`, which performs currency inversion via `DataNormalizer` based on your `RunnerConfig` so all strategies see a consistent base currency.

4. **Run the strategy**
   - Create `StrategySpec` objects (see `trader.strategy`) and hand them to `trader.exec.traderunner.TradeRunner`. The runner sets up Cerebro, analyzers, and risk sizing from `config/contracts.json`.

5. **Route and record trades**
   - `TradeRunner` forwards orders to `trader.exec.router.OrderRouter`, which applies `RiskManager` sizing and dispatches to your broker sender. Capture fills in `trader.portfolio.store.TickerStore`.

6. **Persist to the database**
   - Extend `TickerStore` to write each fill/position snapshot to your DB of choice (e.g., via SQLAlchemy). The DB becomes the source of truth for portfolio balances and recent executions.

7. **Expose via bots/APIs**
   - Point `trader.interfaces.telegram_bot` and `trader.interfaces.http_api` at the DB so chat/HTTP requests can fetch portfolio state, recent fills, or trigger safe controls.

### Minimal IBKR wiring example (pseudo-code)
```python
from trader.data.ibkr_stream import IBKRLiveStreamer
from trader.data.bar_builder import BarBuilder
from trader.data.pipeline import DataStreamer, StreamingOHLCVFeed
from trader.exec.traderunner import TradeRunner, StrategySpec

quote_q = asyncio.Queue()

# 1) start streaming
ib_streamer = IBKRLiveStreamer(ib_client, symbols=["USDJPY"], bar_size="5 mins")
asyncio.create_task(ib_streamer.stream_to_queue(quote_q))

# 2) build bars
bar_q = asyncio.Queue()
builder = BarBuilder(target_interval="5min", output_queue=bar_q)
asyncio.create_task(builder.run(quote_q))

# 3) normalize & feed to Cerebro
streamer = DataStreamer(bar_q)
feed = StreamingOHLCVFeed(streamer, invert_to="USD")

# 4) run strategy
spec = StrategySpec(strategy_cls=MyStrategy, params={})
runner = TradeRunner(feed=feed, strategy_specs=[spec])
await runner.run_live()
```

In production, add broker senders in the router, persist fills via the DB-backed `TickerStore`, and surface portfolio snapshots through the Telegram/HTTP interfaces.
