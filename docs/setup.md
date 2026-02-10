# Setup Guide

## Prerequisites

- Python >= 3.10
- pip or uv package manager

## Installation

### Core Installation

```bash
pip install -e .
```

### With IBKR Support

```bash
pip install -e ".[ibkr]"
```

### With MetaTrader 5 Support (Windows Only)

```bash
pip install -e ".[metatrader]"
```

### Full Development Setup

```bash
pip install -e ".[ibkr,metatrader,polygon,notebooks,dev]"
```

## Broker Setup

### Interactive Brokers

1. Download and install [TWS](https://www.interactivebrokers.com/en/trading/tws.php) or [IB Gateway](https://www.interactivebrokers.com/en/trading/ibgateway-stable.php).
2. Enable API access in TWS: **Edit > Global Configuration > API > Settings**
   - Check "Enable ActiveX and Socket Clients"
   - Set Socket port: `7497` (paper) or `7496` (live)
   - Check "Allow connections from localhost only" (recommended)
3. For paper trading, use port `7497`. For live, use `7496`.
4. Note your account ID (e.g., `DU1234567` for paper).

### MetaTrader 5 (Windows)

1. Download and install [MetaTrader 5](https://www.metatrader5.com/en/download) from your broker.
2. Log in to your demo or live account.
3. Enable Algo Trading: **Tools > Options > Expert Advisors > Allow algo trading**
4. Note your login credentials:
   - Login (account number)
   - Password
   - Server name (e.g., `YourBroker-Demo`)
5. Optionally note the MT5 terminal path if not in the default location.

## Data Sources

### Polygon.io

1. Sign up at [polygon.io](https://polygon.io/) for an API key.
2. Set the environment variable: `export POLYGON_API_KEY=your_key`
3. Free tier provides delayed data; paid tiers provide real-time.

### IBKR Historical Data

The `historical_data_services/ibkr_data_fetch.py` module can fetch historical bars directly from IBKR. Requires TWS/Gateway running.

## Verify Installation

```python
import trader
print(trader.__all__)
```

This should print the list of available exports without errors.
