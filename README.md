# Trading System

NautilusTrader-based algorithmic trading system with MetaTrader 5 and Interactive Brokers support.

## Quick Start

```bash
# Core install
pip install -e .

# Optional extras for IBKR + notebooks
pip install -e ".[ibkr,notebooks]"

# Run tests
pytest -q

# Open backtest example
jupyter lab tests/notebooks/backtest_demo.ipynb
```

## Documentation

- [Project Guide](docs/project_guide.md) - Full system documentation, trade execution lifecycle, and new strategy workflow
- [Setup Guide](docs/setup.md) - Installation and broker setup
- [Architecture](docs/architecture.md) - System components and data flow
- [Strategies](docs/strategies.md) - Strategy reference
- [Adapters](docs/adapters.md) - MT5 and IBKR adapter guide
- [Migration Notes](docs/migration.md) - Backtrader to NautilusTrader mapping

## Features

- NautilusTrader engine for backtest and live trading
- MT5 custom data/execution adapter
- IBKR native adapter integration
- Strategy library (Gotobi, mean reversion, breakout, RSI/MACD/MA, buy-hold test strategy)
- Capital allocation and orchestration support
- SQLite persistence for fills, positions, and equity snapshots

## Project Structure

```text
trader/
  core/                    # venues, enums, instruments, event models
  config/                  # backtest/live node builders, YAML orchestrator
  adapters/                # MetaTrader 5 custom adapter, IBKR config helpers
  data/                    # normalization, tick->bar builder, catalog, quality
  strategy/                # strategies, signals, feature helpers
  capital/                 # capital allocation and risk parity
  exec/                    # risk manager utilities
  portfolio/               # store, equity tracking, pnl metrics, charts
  persistence/             # SQLite schema and repositories
  interfaces/              # HTTP/Telegram placeholders
historical_data_services/  # IBKR and Polygon historical fetchers
config/                    # contracts and portfolio YAML
tests/                     # unit and integration tests
docs/                      # all docs
```

## Strategies

| Strategy | Description | Config |
|----------|-------------|--------|
| `GotobiStrategy` | Time-based Gotobi entry/exit | `GotobiConfig` |
| `GotobiWithSLStrategy` | Gotobi with stop-market protection | `GotobiWithSLConfig` |
| `MeanReversionStrategy` | Mean reversion using MA deviation | `MeanReversionConfig` |
| `BreakoutStrategy` | 50-bar breakout logic | `BreakoutConfig` |
| `RsiMacdMaStrategy` | RSI + MACD histogram curl + MA confirmation | `RsiMacdMaConfig` |
| `OneMinuteBuyHoldStrategy` | Connectivity/smoke test loop | `OneMinuteBuyHoldConfig` |

## Broker Support

| Broker | Type | Data | Execution |
|--------|------|------|-----------|
| Interactive Brokers | Nautilus built-in adapter | Real-time bars | Full order types |
| MetaTrader 5 | Custom adapter | Tick polling to bars | Market, limit, stop-market |