# Trading System

NautilusTrader-based algorithmic trading system with MetaTrader 5 and Interactive Brokers support.

## Features

- **NautilusTrader engine** — Cython-optimized event-driven architecture for backtesting and live trading
- **Gotobi FX strategy** — Japanese settlement day trading with optional stop-loss
- **Mean reversion & breakout strategies** — Signal-based strategies
- **MetaTrader 5 adapter** — Custom adapter with tick polling, bar aggregation, and order execution
- **IBKR adapter** — Native NautilusTrader Interactive Brokers integration
- **FX instrument factory** — CurrencyPair builder from contracts.json config

## Quick Start

```bash
# Install
pip install -e ".[ibkr,notebooks]"

# Run backtest
jupyter lab tests/notebooks/backtest_demo.ipynb
```

## Project Structure

```
trader/
  core/           # event models, instruments, constants
  config/         # BacktestEngine / TradingNode builders
  adapters/       # MetaTrader 5 (custom) + IBKR (native) adapters
  data/           # pipeline, bar builder, data catalog
  strategy/       # Gotobi, mean reversion, breakout strategies
  exec/           # risk management
  portfolio/      # position tracking, PnL
  interfaces/     # Telegram/HTTP stubs
config/           # FX contract sizing (contracts.json)
historical_data_services/  # IBKR + Polygon data fetchers
tests/notebooks/  # backtest_demo, live_demo, data_fetch
docs/             # setup, architecture, strategies, adapters, migration
```

## Documentation

- [Setup Guide](docs/setup.md) — installation, broker setup, data sources
- [Architecture](docs/architecture.md) — system design and data flow
- [Strategies](docs/strategies.md) — Gotobi, mean reversion, breakout reference
- [Adapters](docs/adapters.md) — MT5 and IBKR configuration guide
- [Migration Notes](docs/migration.md) — Backtrader to NautilusTrader mapping

## Strategies

| Strategy | Description | Config |
|----------|-------------|--------|
| `GotobiStrategy` | FX settlement day entry/exit | `GotobiConfig` |
| `GotobiWithSLStrategy` | Gotobi with stop-loss | `GotobiWithSLConfig` |
| `MeanReversionStrategy` | Buy below MA, sell above MA | `MeanReversionConfig` |
| `BreakoutStrategy` | Buy new highs, sell new lows | `BreakoutConfig` |

## Broker Support

| Broker | Type | Data | Execution |
|--------|------|------|-----------|
| Interactive Brokers | Native adapter | Real-time bars | Full order types |
| MetaTrader 5 | Custom adapter | Tick polling → bars | Market/limit/stop |
