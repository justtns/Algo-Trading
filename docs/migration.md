# Backtrader to NautilusTrader Migration Notes

This document records the architectural mapping from the previous Backtrader-based system to the current NautilusTrader implementation.

## Component Mapping

| Backtrader | NautilusTrader | Notes |
|------------|----------------|-------|
| `bt.Cerebro` | `BacktestEngine` / `TradingNode` | Engine orchestration |
| `bt.Strategy` | `nautilus_trader.trading.strategy.Strategy` | Strategy base class |
| `bt.feeds.PandasData` | `BarType` + `add_data()` | Data feeds |
| `bt.feeds.DataBase` (streaming) | `LiveDataClient` subclass | Live data |
| `self.buy()` / `self.sell()` | `self.submit_order(order_factory.market(...))` | Order submission |
| `self.close()` | Submit opposite market order for position qty | Position close |
| `self.position.size` | `self.cache.positions(venue)` | Position query |
| `self.data.datetime.datetime(0)` | `unix_nanos_to_dt(bar.ts_event)` | Bar timestamp |
| `notify_order()` | `on_order_filled()` | Order events |
| `notify_trade()` | `on_position_closed()` | Trade events |
| `OrderRouter` + broker sender | `LiveExecutionClient` | Order routing |
| `StreamingOHLCVFeed` (Queue) | `LiveDataClient.subscribe_bars()` | Live streaming |
| `RiskEstimator.to_sizer()` | Strategy-level sizing | Position sizing |
| `DataNormalizer.to_bt_feed()` | `dataframe_to_nautilus_bars()` | Data conversion |

## Deleted Files

- `trader/strategy/gotobi_bt.py` — replaced by `trader/strategy/gotobi.py`
- `trader/data/metatrader_stream.py` — replaced by `trader/adapters/metatrader/data.py`
- `trader/data/ibkr_stream.py` — replaced by NautilusTrader native IB adapter
- `trader/data/ctrader_stream.py` — removed (placeholder)
- `trader/exec/traderunner.py` — replaced by `trader/config/node.py`
- `trader/exec/router.py` — replaced by NautilusTrader execution client
- `trader/exec/metatrader.py` — replaced by `trader/adapters/metatrader/execution.py`

## Key API Differences

### Strategy Lifecycle

**Backtrader:**
```python
class MyStrategy(bt.Strategy):
    def __init__(self): ...      # setup
    def next(self): ...          # called every bar
    def notify_order(self, o): ...
    def notify_trade(self, t): ...
```

**NautilusTrader:**
```python
class MyStrategy(Strategy):
    def __init__(self, config): ...
    def on_start(self): ...          # subscribe to data
    def on_bar(self, bar): ...       # called every bar
    def on_order_filled(self, e): ...
    def on_position_closed(self, e): ...
    def on_stop(self): ...           # cleanup
```

### Order Submission

**Backtrader:**
```python
self.buy(size=100)
self.sell(exectype=bt.Order.Stop, price=145.0, size=100)
self.close()
```

**NautilusTrader:**
```python
order = self.order_factory.market(
    instrument_id=self.instrument_id,
    order_side=OrderSide.BUY,
    quantity=Quantity(100, 0),
)
self.submit_order(order)

stop = self.order_factory.stop_market(
    instrument_id=self.instrument_id,
    order_side=OrderSide.SELL,
    quantity=Quantity(100, 0),
    trigger_price=Price(145.0, 3),
)
self.submit_order(stop)
```

### Data Types

**Backtrader:** Uses Python floats and `bt.date2num()` for timestamps.

**NautilusTrader:** Uses Cython-optimized `Price`, `Quantity`, `Money` types and nanosecond timestamps (`uint64`).
