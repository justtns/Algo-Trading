"""Tests for Event Analysis proxy."""
import numpy as np
import pandas as pd
import pytest

from src.analysis.event_analysis import (
    compute_event_signal,
    _classify_signal,
    build_event_table,
)


class TestClassifySignal:
    def test_bearish_continuation(self):
        signal = _classify_signal(
            spot_ret=-1.5, rv_1m_chg=0.8, vix_chg=2.0,
            spot_threshold=1.0, rv_rise_threshold=0.5,
            rv_sharp_rise=1.0, rv_fall_threshold=-0.2,
        )
        assert signal == "Bearish Cont."

    def test_bearish_contrarian(self):
        signal = _classify_signal(
            spot_ret=1.5, rv_1m_chg=1.5, vix_chg=0.0,
            spot_threshold=1.0, rv_rise_threshold=0.5,
            rv_sharp_rise=1.0, rv_fall_threshold=-0.2,
        )
        assert signal == "Bearish Contr."

    def test_bullish_continuation(self):
        signal = _classify_signal(
            spot_ret=1.5, rv_1m_chg=-0.5, vix_chg=0.0,
            spot_threshold=1.0, rv_rise_threshold=0.5,
            rv_sharp_rise=1.0, rv_fall_threshold=-0.2,
        )
        assert signal == "Bullish Cont."

    def test_bullish_contrarian(self):
        signal = _classify_signal(
            spot_ret=-1.5, rv_1m_chg=-0.5, vix_chg=-1.0,
            spot_threshold=1.0, rv_rise_threshold=0.5,
            rv_sharp_rise=1.0, rv_fall_threshold=-0.2,
        )
        assert signal == "Bullish Contr."

    def test_no_signal(self):
        signal = _classify_signal(
            spot_ret=0.3, rv_1m_chg=0.1, vix_chg=0.1,
            spot_threshold=1.0, rv_rise_threshold=0.5,
            rv_sharp_rise=1.0, rv_fall_threshold=-0.2,
        )
        assert signal == "No Signal"


class TestComputeEventSignal:
    def test_returns_dict(self, synthetic_daily_uptrend, synthetic_vix):
        result = compute_event_signal(
            synthetic_daily_uptrend["close"],
            synthetic_vix["close"],
        )
        assert "signal" in result
        assert "rv_1m" in result
        assert "new_spot" in result

    def test_short_series(self):
        short = pd.Series([1.0] * 10)
        result = compute_event_signal(short)
        assert result["signal"] == "N/A"

    def test_no_vix(self, synthetic_daily_uptrend):
        result = compute_event_signal(synthetic_daily_uptrend["close"])
        assert result["signal"] in (
            "No Signal", "Bearish Cont.", "Bearish Contr.",
            "Bullish Cont.", "Bullish Contr.",
        )


class TestBuildEventTable:
    def test_table_structure(self, synthetic_daily_uptrend, synthetic_vix):
        data = {"EURUSD": synthetic_daily_uptrend}
        table = build_event_table(data, synthetic_vix)
        assert "Signal" in table.columns
        assert "EURUSD" in table.index

    def test_empty_pair(self):
        data = {"USDTHB": pd.DataFrame()}
        table = build_event_table(data)
        assert table.loc["USDTHB", "Signal"] == "N/A"
