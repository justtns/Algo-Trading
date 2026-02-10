import pandas as pd

from trader.strategy.signals import rsi_macd_ma_signal


def _bars_from_close(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.1 for c in closes],
            "low": [c - 0.1 for c in closes],
            "close": closes,
            "volume": [1.0] * len(closes),
        },
    )


def test_rsi_macd_ma_signal_returns_zero_when_insufficient_bars():
    bars = _bars_from_close([100.0, 101.0, 99.0, 100.0])
    assert rsi_macd_ma_signal(bars) == 0.0


def test_rsi_macd_ma_signal_sells_when_requested_conditions_align():
    bars = _bars_from_close([95.0, 95.0, 95.0, 95.0, 98.0, 98.0, 100.0, 95.0])

    signal = rsi_macd_ma_signal(
        bars,
        rsi_period=2,
        rsi_oversold=40.0,
        rsi_overbought=60.0,
        macd_fast=2,
        macd_slow=3,
        macd_signal=2,
        ma_fast=2,
        ma_slow=3,
    )
    assert signal == -1.0


def test_rsi_macd_ma_signal_buys_when_requested_opposite_conditions_align():
    bars = _bars_from_close([95.0, 95.0, 95.0, 95.0, 95.0, 98.0, 95.0, 102.0])

    signal = rsi_macd_ma_signal(
        bars,
        rsi_period=2,
        rsi_oversold=40.0,
        rsi_overbought=60.0,
        macd_fast=2,
        macd_slow=3,
        macd_signal=2,
        ma_fast=2,
        ma_slow=3,
    )
    assert signal == 1.0


def test_rsi_macd_ma_signal_requires_ma_confirmation():
    bars = _bars_from_close([95.0, 95.0, 95.0, 95.0, 98.0, 98.0, 100.0, 95.0])

    signal = rsi_macd_ma_signal(
        bars,
        rsi_period=2,
        rsi_oversold=40.0,
        rsi_overbought=60.0,
        macd_fast=2,
        macd_slow=3,
        macd_signal=2,
        ma_fast=3,
        ma_slow=2,
    )
    assert signal == 0.0
