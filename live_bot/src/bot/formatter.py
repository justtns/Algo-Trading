"""HTML formatters for live trading bot messages."""
from __future__ import annotations

from datetime import datetime, timezone

MAX_MSG_LEN = 4096


def _header(title: str) -> str:
    return f"<b>{title}</b>"


def _pre(text: str) -> str:
    return f"<pre>{text}</pre>"


def format_fill_alert(fill: dict) -> str:
    """Format a single fill as a push notification."""
    side = fill["side"].upper()
    symbol = fill["symbol"]
    qty = fill["qty"]
    price = fill["price"]
    strategy = fill.get("strategy_id") or "—"
    ts = fill.get("ts", "")

    # Format qty: integer if whole number, else 2 decimals
    qty_str = f"{qty:,.0f}" if qty == int(qty) else f"{qty:,.2f}"

    return (
        f"🔔 <b>FILL</b>: {side} {qty_str} {symbol} @ {price:.5g}\n"
        f"Strategy: {strategy}\n"
        f"Time: {ts}"
    )


def format_fills(fills: list[dict]) -> list[str]:
    """Format a list of fills as an HTML table."""
    if not fills:
        return [f"{_header('Recent Fills')}\n\nNo fills found."]

    lines = [_header("Recent Fills"), ""]

    header = f"{'Time':<20} {'Side':<5} {'Qty':>10} {'Symbol':<10} {'Price':>12} {'Strat'}"
    sep = "─" * 70
    table_lines = [header, sep]

    for f in fills:
        ts = f["ts"]
        # Truncate ISO timestamp to minutes
        if len(ts) > 16:
            ts = ts[:16]
        side = f["side"].upper()
        qty = f["qty"]
        qty_str = f"{qty:,.0f}" if qty == int(qty) else f"{qty:,.2f}"
        symbol = f["symbol"]
        price = f["price"]
        strategy = f.get("strategy_id") or "—"
        table_lines.append(
            f"{ts:<20} {side:<5} {qty_str:>10} {symbol:<10} {price:>12.5g} {strategy}"
        )

    lines.append(_pre("\n".join(table_lines)))

    messages = []
    current = "\n".join(lines)
    if len(current) <= MAX_MSG_LEN:
        messages.append(current)
    else:
        # Split into chunks
        chunk_lines = [lines[0], lines[1]]
        for tl in table_lines:
            test = "\n".join(chunk_lines) + _pre(tl)
            if len(test) > MAX_MSG_LEN - 100:
                messages.append("\n".join(chunk_lines))
                chunk_lines = [_header("Recent Fills (cont.)"), ""]
            chunk_lines.append(tl)
        if chunk_lines:
            messages.append("\n".join(chunk_lines))

    return messages


def format_positions(positions: list[dict]) -> list[str]:
    """Format position snapshots as an HTML table."""
    if not positions:
        return [f"{_header('Open Positions')}\n\nNo open positions."]

    lines = [_header("Open Positions"), ""]

    header = f"{'Symbol':<10} {'Qty':>10} {'Avg Px':>12} {'MTM Px':>12} {'Unrl PnL':>12}"
    sep = "─" * 60
    table_lines = [header, sep]

    total_pnl = 0.0
    for p in positions:
        symbol = p["symbol"]
        qty = p["qty"]
        qty_str = f"{qty:,.0f}" if qty == int(qty) else f"{qty:,.2f}"
        avg_px = p["avg_price"]
        mtm_px = p.get("mtm_price")
        mtm_str = f"{mtm_px:>12.5g}" if mtm_px is not None else f"{'—':>12}"
        pnl = p.get("unrealized_pnl", 0.0)
        total_pnl += pnl
        table_lines.append(
            f"{symbol:<10} {qty_str:>10} {avg_px:>12.5g} {mtm_str} {pnl:>+12.2f}"
        )

    table_lines.append(sep)
    table_lines.append(f"{'Total':>46} {total_pnl:>+12.2f}")

    lines.append(_pre("\n".join(table_lines)))
    return ["\n".join(lines)]


def format_equity(equity: dict | None) -> str:
    """Format equity snapshot."""
    if equity is None:
        return f"{_header('Equity')}\n\nNo equity data available."

    eq = equity["equity"]
    cash = equity["cash"]
    ts = equity.get("ts", "")
    strategy = equity.get("strategy_id") or "Portfolio"

    return (
        f"{_header('Equity')}\n\n"
        f"Equity:   <b>{eq:,.2f}</b>\n"
        f"Cash:     {cash:,.2f}\n"
        f"Strategy: {strategy}\n"
        f"As of:    {ts}"
    )


def format_status(
    db_path: str,
    connected: bool,
    last_fill_ts: str | None,
    fill_count: int,
    active_session: str | None,
) -> str:
    """Format bot status info."""
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"{_header('Live Bot Status')}\n\n"
        f"DB Path:    {db_path}\n"
        f"Connected:  {'Yes' if connected else 'No'}\n"
        f"Last Fill:  {last_fill_ts or 'None'}\n"
        f"Fill Count: {fill_count}\n"
        f"Session:    {active_session or 'None'}\n"
        f"Server:     {now}"
    )
