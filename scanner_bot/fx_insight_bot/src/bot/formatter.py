"""
Telegram message formatters.

Converts DataFrames into HTML-formatted messages suitable for Telegram's
4096-character limit. Uses <pre> blocks for monospace tables.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from tabulate import tabulate

from ..data.tickers import spot_decimals, G10_PAIRS, EM_ASIA_PAIRS

MAX_MSG_LEN = 4000  # leave margin below 4096


def _header(title: str, timestamp: str | None = None) -> str:
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"<b>{title}</b>\n<i>{ts}</i>\n"


def _pre(text: str) -> str:
    return f"<pre>{text}</pre>"


def _format_spot(pair: str, val) -> str:
    if val is None:
        return "N/A"
    dec = spot_decimals(pair)
    return f"{val:.{dec}f}"


def _format_level(pair: str, val) -> str:
    if val is None:
        return "-"
    dec = spot_decimals(pair)
    return f"{val:.{dec}f}"


# ---------------------------------------------------------------------------
# Technical Matrix
# ---------------------------------------------------------------------------

def format_technical_matrix(matrix_df: pd.DataFrame, timestamp: str | None = None) -> list[str]:
    """Format Technical Matrix as Telegram HTML messages, split by G10/EM."""
    messages = []

    for group_name, pairs in [("G10", G10_PAIRS), ("EM Asia", EM_ASIA_PAIRS)]:
        group_df = matrix_df.loc[matrix_df.index.isin(pairs)]
        if group_df.empty:
            continue

        rows = []
        for pair, row in group_df.iterrows():
            rows.append([
                pair,
                _format_spot(pair, row.get("Spot")),
                row.get("Trend", ""),
                row.get("Signal", ""),
                row.get("ADX Trend", ""),
                row.get("Bollinger", ""),
                _format_level(pair, row.get("Next Support")),
                _format_level(pair, row.get("Next Resistance")),
            ])

        table = tabulate(
            rows,
            headers=["Pair", "Spot", "Tr", "Signal", "ADX", "BB", "Supp", "Res"],
            tablefmt="plain",
            stralign="right",
        )

        msg = _header(f"Technical Matrix - {group_name}", timestamp) + "\n" + _pre(table)
        messages.append(msg)

    return messages or [_header("Technical Matrix", timestamp) + "\nNo data available."]


# ---------------------------------------------------------------------------
# Event Analysis
# ---------------------------------------------------------------------------

def format_event_table(event_df: pd.DataFrame, timestamp: str | None = None) -> list[str]:
    """Format Event Analysis table."""
    messages = []

    for group_name, pairs in [("G10", G10_PAIRS), ("EM Asia", EM_ASIA_PAIRS)]:
        group_df = event_df.loc[event_df.index.isin(pairs)]
        if group_df.empty:
            continue

        rows = []
        for pair, row in group_df.iterrows():
            rv_1m = row.get("1m Vol")
            rv_chg = row.get("1m Vol Chg")
            ret = row.get("Ret vs USD")
            rows.append([
                pair,
                _format_spot(pair, row.get("New Spot")),
                f"{rv_1m:.1f}" if rv_1m is not None else "-",
                f"{rv_chg:+.1f}" if rv_chg is not None else "-",
                f"{ret:+.2f}%" if ret is not None else "-",
                row.get("Signal", ""),
            ])

        table = tabulate(
            rows,
            headers=["Pair", "Spot", "1mVol", "Chg", "RetUSD", "Signal"],
            tablefmt="plain",
            stralign="right",
        )

        msg = _header(f"Event Analysis (Proxy) - {group_name}", timestamp) + "\n" + _pre(table)
        messages.append(msg)

    return messages or [_header("Event Analysis", timestamp) + "\nNo data available."]


# ---------------------------------------------------------------------------
# CARS
# ---------------------------------------------------------------------------

def format_cars(cars_df: pd.DataFrame | None, timestamp: str | None = None) -> str:
    """Format CARS signals."""
    header = _header("CARS - Cross-Asset Regime", timestamp)

    if cars_df is None:
        return header + "\nInsufficient cross-asset data."

    regime = cars_df.attrs.get("regime", "Unknown")
    factor = cars_df.attrs.get("performing_factor", "Unknown")
    eq_z = cars_df.attrs.get("equity_z", "-")
    bd_z = cars_df.attrs.get("bond_z", "-")
    cm_z = cars_df.attrs.get("commodity_z", "-")

    meta = (
        f"Regime: <b>{regime}</b> | Factor: {factor}\n"
        f"z-scores: Equity={eq_z}, Bonds={bd_z}, Commod={cm_z}\n"
    )

    rows = []
    for ccy, row in cars_df.iterrows():
        signal = row.get("Bullish/Bearish", "")
        eq_rank = int(row.get("Equity", 0))
        rt_rank = int(row.get("Rates", 0))
        cm_rank = int(row.get("Commodity", 0))
        rows.append([ccy, signal, eq_rank, rt_rank, cm_rank])

    table = tabulate(
        rows,
        headers=["Ccy", "Signal", "Eq", "Rt", "Cm"],
        tablefmt="plain",
        stralign="right",
    )

    return header + meta + "\n" + _pre(table)


# ---------------------------------------------------------------------------
# Time Zone
# ---------------------------------------------------------------------------

def format_timezone_summary(tz_df: pd.DataFrame, timestamp: str | None = None) -> str:
    """Format timezone return summary."""
    header = _header("Time Zone Returns (1w)", timestamp)

    if tz_df is None or tz_df.empty:
        return header + "\nNo hourly data available."

    rows = []
    for pair, row in tz_df.iterrows():
        rows.append([
            pair,
            f"{row.get('America', 0):+.2f}%",
            f"{row.get('Europe', 0):+.2f}%",
            f"{row.get('Asia', 0):+.2f}%",
        ])

    table = tabulate(
        rows,
        headers=["Pair", "Amer", "Euro", "Asia"],
        tablefmt="plain",
        stralign="right",
    )
    return header + "\n" + _pre(table)


def format_timezone_heatmap(hm_df: pd.DataFrame, timestamp: str | None = None) -> list[str]:
    """Format 8-slot granular heatmap. May split into multiple messages."""
    header = _header("Time Zone Heatmap (3h slots, 1w)", timestamp)

    if hm_df is None or hm_df.empty:
        return [header + "\nNo hourly data available."]

    # Format values with color indicators
    rows = []
    for pair, row in hm_df.iterrows():
        formatted_row = [pair]
        for col in hm_df.columns:
            val = row[col]
            formatted_row.append(f"{val:+.1f}")
        rows.append(formatted_row)

    short_headers = ["Pair"] + [s.split("-")[0] for s in hm_df.columns]

    table = tabulate(rows, headers=short_headers, tablefmt="plain", stralign="right")
    msg = header + "\n" + _pre(table)

    if len(msg) > MAX_MSG_LEN:
        # Split into two messages
        mid = len(rows) // 2
        t1 = tabulate(rows[:mid], headers=short_headers, tablefmt="plain", stralign="right")
        t2 = tabulate(rows[mid:], headers=short_headers, tablefmt="plain", stralign="right")
        return [header + "\n" + _pre(t1), _pre(t2)]

    return [msg]


# ---------------------------------------------------------------------------
# Full report assembly
# ---------------------------------------------------------------------------

def format_full_report(report: dict) -> list[str]:
    """
    Convert a report dict (from ReportGenerator) into a list of
    Telegram HTML messages.
    """
    ts = report.get("timestamp")
    title = report.get("report_type", "FX Report")
    messages: list[str] = []

    # Title message
    messages.append(f"<b>{title}</b>\n<i>{ts}</i>")

    # Technical Matrix
    tm = report.get("technical_matrix")
    if tm is not None:
        messages.extend(format_technical_matrix(tm, ts))

    # Event Analysis
    ev = report.get("event_table")
    if ev is not None:
        messages.extend(format_event_table(ev, ts))

    # CARS
    cars = report.get("cars")
    messages.append(format_cars(cars, ts))

    # Time Zone
    tz_summary = report.get("timezone_summary")
    if tz_summary is not None and not tz_summary.empty:
        messages.append(format_timezone_summary(tz_summary, ts))

    tz_heatmap = report.get("timezone_heatmap")
    if tz_heatmap is not None and not tz_heatmap.empty:
        messages.extend(format_timezone_heatmap(tz_heatmap, ts))

    return messages
