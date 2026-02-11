"""Plotly charting utilities for equity curves and drawdowns."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    import plotly.graph_objects as go


def _import_plotly():
    try:
        import plotly.graph_objects as go

        return go
    except ImportError:
        raise ImportError(
            "plotly is required for charting. "
            "Install with: pip install trading-system[charts]"
        )


def plot_equity_curve(
    df: pd.DataFrame,
    title: str = "Equity Curve",
    show: bool = True,
) -> go.Figure:
    """Plot equity curve from DataFrame with 'equity' column and datetime index."""
    go = _import_plotly()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=df.index, y=df["equity"], mode="lines", name="Equity")
    )
    fig.update_layout(title=title, xaxis_title="Time", yaxis_title="Equity")
    if show:
        fig.show()
    return fig


def plot_drawdown(
    dd: pd.Series,
    title: str = "Drawdown",
    show: bool = True,
) -> go.Figure:
    """Plot drawdown series as filled area chart."""
    go = _import_plotly()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dd.index, y=dd.values, fill="tozeroy", name="Drawdown"
        )
    )
    fig.update_layout(title=title, xaxis_title="Time", yaxis_title="Drawdown %")
    if show:
        fig.show()
    return fig


def plot_equity_with_drawdown(
    equity_df: pd.DataFrame,
    dd: pd.Series,
    title: str = "Strategy Performance",
    show: bool = True,
) -> go.Figure:
    """Combined subplot: equity on top, drawdown on bottom."""
    go = _import_plotly()
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.7, 0.3],
        subplot_titles=["Equity", "Drawdown"],
    )
    fig.add_trace(
        go.Scatter(
            x=equity_df.index,
            y=equity_df["equity"],
            mode="lines",
            name="Equity",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=dd.index, y=dd.values, fill="tozeroy", name="Drawdown"
        ),
        row=2,
        col=1,
    )
    fig.update_layout(title=title)
    if show:
        fig.show()
    return fig
