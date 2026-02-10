# Architecture

## Overview

The trading system is built on [NautilusTrader](https://nautilustrader.io/), a high-performance algorithmic trading platform written in Cython/Python. It provides a unified architecture for both backtesting and live trading.

## System Components

```
┌─────────────────────────────────────────────────────────┐
│                    TradingNode / BacktestEngine          │
│                                                         │
│  ┌──────────┐   ┌───────────┐   ┌──────────────────┐   │
│  │ Strategy │──▶│ OrderBook │──▶│ ExecutionClient   │   │
│  │          │   │  / Cache  │   │ (MT5 / IBKR)     │   │
│  │ on_bar() │   │           │   │                   │   │
│  └────▲─────┘   └───────────┘   └──────────────────┘   │
│       │                                                  │
│  ┌────┴─────────────────────┐                           │
│  │     DataClient           │                           │
│  │  (MT5 / IBKR / Backtest) │                           │
│  └──────────────────────────┘                           │
└─────────────────────────────────────────────────────────┘
```

## Data Flow

### Backtest Mode

```
Parquet/CSV → DataHandler → DataFrame → dataframe_to_nautilus_bars()
    → BacktestEngine.add_data() → Strategy.on_bar()
    → order_factory.market() → simulated fill → Strategy.on_order_filled()
```

### Live Mode (MetaTrader 5)

```
MT5 Terminal → copy_ticks_from() → BarBuilder → Nautilus Bar
    → MetaTrader5DataClient → message bus → Strategy.on_bar()
    → submit_order() → MetaTrader5ExecutionClient → MT5 order_send()
    → fill event → Strategy.on_order_filled()
```

### Live Mode (IBKR)

```
TWS/Gateway → InteractiveBrokersDataClient (built-in) → Nautilus Bar
    → message bus → Strategy.on_bar()
    → submit_order() → InteractiveBrokersExecClient → IB API
    → fill event → Strategy.on_order_filled()
```

## Package Structure

```
trader/
├── core/
│   ├── events.py         # Internal event types (Tick, Bar, Signal, etc.)
│   ├── clock.py          # Clock/timing utilities
│   ├── constants.py      # Venue IDs, default values
│   └── instruments.py    # FX instrument factory (CurrencyPair builder)
├── config/
│   └── node.py           # BacktestEngine and TradingNode builders
├── adapters/
│   ├── metatrader/       # Custom MT5 adapter
│   │   ├── common.py     # Connection config and management
│   │   ├── provider.py   # MT5 instrument provider
│   │   ├── data.py       # LiveDataClient (tick polling → bars)
│   │   ├── execution.py  # LiveExecClient (order routing)
│   │   └── factories.py  # TradingNode factory classes
│   └── ibkr/
│       └── config.py     # IBKR adapter configuration helpers
├── data/
│   ├── pipeline.py       # DataNormalizer, DataHandler, DataPackage
│   ├── bar_builder.py    # Tick-to-bar aggregation
│   └── catalog.py        # DataFrame ↔ Nautilus Bar conversion
├── strategy/
│   ├── common.py         # GotobiCalendar (settlement date logic)
│   ├── gotobi.py         # GotobiStrategy, GotobiWithSLStrategy
│   ├── mean_reversion.py # MeanReversionStrategy
│   ├── breakout.py       # BreakoutStrategy
│   ├── rsi_macd_ma.py    # RsiMacdMaStrategy
│   ├── signals.py        # Pure signal functions
│   └── features.py       # Feature engineering (EMA, ATR, Z-score)
├── exec/
│   └── risk.py           # RiskEstimator, RiskManager, RiskLimits
├── portfolio/
│   ├── store.py          # TickerStore (position tracking)
│   ├── book.py           # VirtualBook
│   └── pnl.py            # PnL calculations
└── interfaces/
    ├── telegram_bot.py   # Control surface stub
    └── http_api.py       # API stub
```

## Key Design Decisions

1. **NautilusTrader as core engine**: Provides Cython-optimized event loop, built-in IBKR adapter, proper order management, and unified backtest/live interface.

2. **Custom MT5 adapter**: MetaTrader 5 doesn't have a built-in NautilusTrader adapter. Our custom adapter implements `LiveMarketDataClient` (tick polling via `copy_ticks_from`) and `LiveExecutionClient` (order routing via `order_send`).

3. **Shared BarBuilder**: The tick-to-bar aggregation logic is framework-agnostic and reused inside the MT5 data client.

4. **Strategy configs as frozen pydantic models**: NautilusTrader uses `StrategyConfig` (frozen=True) for type-safe, immutable configuration.

5. **Instrument-first design**: FX pairs are modeled as `CurrencyPair` objects with explicit base/quote currencies, lot sizes, and price precision. This replaces the old string-based symbol handling.
