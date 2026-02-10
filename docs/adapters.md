# Adapter Guide

## MetaTrader 5 Adapter (Custom)

The MT5 adapter is a custom NautilusTrader integration located in `trader/adapters/metatrader/`.

### Components

| Module | Class | Purpose |
|--------|-------|---------|
| `common.py` | `MetaTrader5Config` | Connection configuration |
| `common.py` | `MetaTrader5Connection` | Shared connection manager |
| `provider.py` | `MetaTrader5InstrumentProvider` | Loads instruments from MT5 |
| `data.py` | `MetaTrader5DataClient` | Live bar data via tick polling |
| `execution.py` | `MetaTrader5ExecutionClient` | Order execution via `order_send` |
| `factories.py` | `MetaTrader5LiveDataClientFactory` | TradingNode data factory |
| `factories.py` | `MetaTrader5LiveExecClientFactory` | TradingNode exec factory |

### Data Client

Polls ticks from MT5 using `copy_ticks_from()`, aggregates them into bars using `BarBuilder`, and publishes NautilusTrader `Bar` objects to the message bus.

**Configuration (`MetaTrader5DataClientConfig`):**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `mt5_login` | None | MT5 account number |
| `mt5_password` | None | Account password |
| `mt5_server` | None | Broker server name |
| `mt5_path` | None | MT5 terminal path |
| `bar_seconds` | 60 | Bar aggregation period |
| `poll_interval` | 1.0 | Tick polling interval (seconds) |
| `max_batch` | 500 | Max ticks per poll |
| `lookback_sec` | 5 | Initial lookback window |

### Execution Client

Maps NautilusTrader orders to MT5 trade requests and submits via `order_send()`.

**Supported order types:**
- Market orders → `TRADE_ACTION_DEAL`
- Limit orders → `TRADE_ACTION_PENDING` + `ORDER_TYPE_BUY_LIMIT` / `ORDER_TYPE_SELL_LIMIT`
- Stop orders → `TRADE_ACTION_PENDING` + `ORDER_TYPE_BUY_STOP` / `ORDER_TYPE_SELL_STOP`

### Usage Example

```python
from nautilus_trader.live.node import TradingNode
from nautilus_trader.config import TradingNodeConfig
from trader.adapters.metatrader import (
    MetaTrader5DataClientConfig,
    MetaTrader5ExecClientConfig,
    MetaTrader5LiveDataClientFactory,
    MetaTrader5LiveExecClientFactory,
)

data_config = MetaTrader5DataClientConfig(
    mt5_login=12345678,
    mt5_password="password",
    mt5_server="Broker-Demo",
)

exec_config = MetaTrader5ExecClientConfig(
    mt5_login=12345678,
    mt5_password="password",
    mt5_server="Broker-Demo",
)

node = TradingNode(config=TradingNodeConfig(
    data_clients={"MT5": data_config},
    exec_clients={"MT5": exec_config},
))
node.add_data_client_factory("MT5", MetaTrader5LiveDataClientFactory)
node.add_exec_client_factory("MT5", MetaTrader5LiveExecClientFactory)
```

---

## Interactive Brokers Adapter (Built-in)

Uses NautilusTrader's built-in `nautilus_trader.adapters.interactive_brokers` adapter. Configuration helpers are in `trader/adapters/ibkr/config.py`.

### Configuration Helpers

```python
from trader.adapters.ibkr import ibkr_data_config, ibkr_exec_config

# Paper trading
data_cfg = ibkr_data_config(host="127.0.0.1", port=7497, client_id=1)
exec_cfg = ibkr_exec_config(host="127.0.0.1", port=7497, client_id=1, account="DU1234567")

# Live trading
data_cfg = ibkr_data_config(host="127.0.0.1", port=7496, client_id=1)
exec_cfg = ibkr_exec_config(host="127.0.0.1", port=7496, client_id=1, account="U1234567")
```

### Port Reference

| Port | Mode |
|------|------|
| 7497 | TWS Paper Trading |
| 7496 | TWS Live Trading |
| 4002 | IB Gateway Paper |
| 4001 | IB Gateway Live |

### Usage Example

```python
from nautilus_trader.live.node import TradingNode
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.adapters.interactive_brokers.factories import (
    InteractiveBrokersLiveDataClientFactory,
    InteractiveBrokersLiveExecClientFactory,
)
from trader.adapters.ibkr import ibkr_data_config, ibkr_exec_config

node = TradingNode(config=TradingNodeConfig(
    data_clients={"IB": ibkr_data_config(port=7497)},
    exec_clients={"IB": ibkr_exec_config(port=7497, account="DU1234567")},
))
node.add_data_client_factory("IB", InteractiveBrokersLiveDataClientFactory)
node.add_exec_client_factory("IB", InteractiveBrokersLiveExecClientFactory)
```

---

## Historical Data Services

Standalone data fetchers that are independent of the NautilusTrader engine. Useful for populating the data catalog.

### IBKR Historical (`historical_data_services/ibkr_data_fetch.py`)

- `fetch_ibkr_bars()` — one-shot async fetch for a single duration
- `fetch_ibkr_bars_range_fx()` — chunked fetch for long date ranges (1-year chunks)

### Polygon.io (`historical_data_services/polygon_data_fetch.py`)

- Fetches bars from Polygon.io REST API
- Requires `POLYGON_API_KEY` environment variable
