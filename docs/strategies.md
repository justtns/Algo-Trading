# Strategy Reference

## Gotobi Strategy

### Overview

The Gotobi strategy trades on Japanese FX settlement days. "Gotobi" refers to the 5th, 10th, 15th, 20th, 25th, and 30th of each month — dates when Japanese corporations settle cross-border payments, creating predictable intraday FX patterns.

### Calendar Logic (`GotobiCalendar`)

Located in `trader/strategy/common.py`.

Resolution rules:
1. If the day-of-month is in `{5, 10, 15, 20, 25, 30}`, it's a gotobi base date.
2. If the base date falls on Saturday, shift to the previous Friday.
3. If the base date falls on Sunday, shift to the previous Friday.
4. If the shifted date is a Japanese holiday, roll backward day-by-day until a business day is found.

Holiday detection uses the `holidays` package for Japanese national holidays, with optional custom `notrade_days` for additional settlement holidays.

### GotobiStrategy

Located in `trader/strategy/gotobi.py`.

**Config: `GotobiConfig`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `instrument_id` | str | required | NautilusTrader instrument ID |
| `bar_type` | str | required | Bar type string |
| `entry_time` | str | "01:30:00" | Entry time (HH:MM:SS) |
| `exit_time` | str | "08:30:00" | Exit time (HH:MM:SS) |
| `trade_size` | float | 1.0 | Trade size (positive=long, negative=short) |
| `contract_size` | float | 100,000 | Lot/contract size multiplier |
| `gotobi_days` | tuple | (5,10,15,20,25,30) | Which day-of-month values are gotobi |
| `use_holidays` | bool | True | Use JP holiday calendar |

**Behavior:**
- On each bar, checks if today is a resolved gotobi trading date.
- At `entry_time`: submits a market order (BUY if trade_size > 0, SELL if < 0).
- At `exit_time`: closes the position with a market order.
- Enters only once per gotobi day.

### GotobiWithSLStrategy

Same as `GotobiStrategy` but with stop-loss protection.

**Additional Config: `GotobiWithSLConfig`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `stop_loss_pct` | float or None | None | Stop distance as fraction (e.g. 0.003 = 0.3%) |

**Behavior:**
- After entry fill, places a stop-market order.
  - Long entry: stop at `entry_price * (1 - stop_loss_pct)`
  - Short entry: stop at `entry_price * (1 + stop_loss_pct)`
- At exit time, cancels any pending stop and closes position.
- Logs whether exit was TIME-EXIT or STOP-OUT.

---

## Mean Reversion Strategy

Located in `trader/strategy/mean_reversion.py`.

**Config: `MeanReversionConfig`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `instrument_id` | str | required | NautilusTrader instrument ID |
| `bar_type` | str | required | Bar type string |
| `trade_size` | float | 1.0 | Trade size |
| `contract_size` | float | 100,000 | Lot/contract size multiplier |
| `max_bars` | int | 100 | Rolling window of bars to keep |

**Signal logic** (from `trader/strategy/signals.py`):
- BUY when close < MA(20) * 0.999
- SELL when close > MA(20) * 1.001
- Otherwise neutral (no action)

Enters only when no existing position is open.

---

## Breakout Strategy

Located in `trader/strategy/breakout.py`.

**Config: `BreakoutConfig`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `instrument_id` | str | required | NautilusTrader instrument ID |
| `bar_type` | str | required | Bar type string |
| `trade_size` | float | 1.0 | Trade size |
| `contract_size` | float | 100,000 | Lot/contract size multiplier |
| `max_bars` | int | 100 | Rolling window of bars to keep |

**Signal logic** (from `trader/strategy/signals.py`):
- BUY when close >= 50-bar high
- SELL when close <= 50-bar low
- Otherwise neutral

Enters only when no existing position is open.
