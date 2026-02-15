"""
Chart generation for Telegram bot — matplotlib Agg backend → PNG bytes.

Bloomberg Terminal colour scheme.  Each ``chart_*`` function returns an
``io.BytesIO`` buffer containing a PNG image ready for ``reply_photo()``.
"""
from __future__ import annotations

import io
from typing import Any

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.colors as mcolors  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ..data.tickers import ETF_DESCRIPTIONS

# ---------------------------------------------------------------------------
# Bloomberg Terminal colour scheme
# ---------------------------------------------------------------------------
BG_COLOR = "#000000"        # pure black
HEADER_BG = "#1A1A1A"       # dark gray for table headers
TEXT_COLOR = "#FFA028"       # Bloomberg amber (primary text)
TEXT_WHITE = "#FFFFFF"       # white for emphasis / titles
GRID_COLOR = "#333333"       # dark gray gridlines
BULLISH_COLOR = "#4AF6C3"   # Bloomberg teal/green (up)
BEARISH_COLOR = "#FF433D"   # Bloomberg red (down)
NEUTRAL_COLOR = "#888888"   # mid-gray
ACCENT_COLOR = "#0068FF"    # Bloomberg blue
ACCENT2_COLOR = "#FB8B1E"   # Bloomberg orange accent

# Signal → colour mapping
SIGNAL_COLORS: dict[str, str] = {
    "Bullish": BULLISH_COLOR,
    "Sl. Bullish": "#3AC4A0",
    "Bearish": BEARISH_COLOR,
    "Sl. Bearish": "#E07030",
    "No Signal": NEUTRAL_COLOR,
    "N/A": NEUTRAL_COLOR,
    "Bullish Cont.": BULLISH_COLOR,
    "Bullish Contr.": "#3AC4A0",
    "Bearish Cont.": BEARISH_COLOR,
    "Bearish Contr.": "#E07030",
}

# Custom Bloomberg-style diverging colourmap: red → black → teal
_BBG_CMAP = mcolors.LinearSegmentedColormap.from_list(
    "bbg_div", [BEARISH_COLOR, BG_COLOR, BULLISH_COLOR], N=256,
)

# Rank heatmap: 1 (teal/good) → 10 (red/bad)
_BBG_RANK_CMAP = mcolors.LinearSegmentedColormap.from_list(
    "bbg_rank", [BULLISH_COLOR, "#1A1A1A", BEARISH_COLOR], N=256,
)


def _apply_theme(fig: plt.Figure, ax: plt.Axes | None = None) -> None:
    fig.set_facecolor(BG_COLOR)
    if ax is not None:
        ax.set_facecolor(BG_COLOR)
        ax.tick_params(colors=TEXT_COLOR, which="both")
        ax.xaxis.label.set_color(TEXT_COLOR)
        ax.yaxis.label.set_color(TEXT_COLOR)
        ax.title.set_color(TEXT_WHITE)
        for spine in ax.spines.values():
            spine.set_color(GRID_COLOR)


def _subtitle(ax: plt.Axes, data_date: str = "", frequency: str = "",
              y: float = -0.03) -> None:
    """Add a data-date / frequency subtitle below the axis title."""
    parts = []
    if data_date:
        parts.append(f"Data: {data_date}")
    if frequency:
        parts.append(f"Freq: {frequency}")
    if parts:
        ax.text(0.5, y, "  |  ".join(parts), transform=ax.transAxes,
                ha="center", va="top", fontsize=8, color=TEXT_COLOR)


def _fig_to_bytes(fig: plt.Figure, dpi: int = 150) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor(), edgecolor="none")
    buf.seek(0)
    plt.close(fig)
    return buf


def _etf_label(ticker: str) -> str:
    """Return 'SPY — S&P 500 ETF' style label."""
    desc = ETF_DESCRIPTIONS.get(ticker, "")
    return f"{ticker} — {desc}" if desc else ticker


# ---------------------------------------------------------------------------
# 1. Technical Matrix — styled table image
# ---------------------------------------------------------------------------

def chart_technical_matrix(df: pd.DataFrame, *,
                           data_date: str = "",
                           frequency: str = "") -> io.BytesIO:
    """Render technical matrix as a coloured table image."""
    cols = ["Spot", "Trend", "Signal", "ADX Trend", "Bollinger"]
    display = df[cols].copy()

    display["Spot"] = display["Spot"].apply(
        lambda v: f"{v:.4f}" if pd.notna(v) else "—")

    n_rows = display.shape[0]
    fig_h = max(4.0, 0.35 * n_rows + 1.6)
    fig, ax = plt.subplots(figsize=(10, fig_h))
    ax.axis("off")
    _apply_theme(fig)

    table = ax.table(
        cellText=display.values,
        rowLabels=display.index,
        colLabels=display.columns,
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.4)

    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor(GRID_COLOR)
        if row == 0:  # header
            cell.set_facecolor(HEADER_BG)
            cell.set_text_props(color=TEXT_WHITE, fontweight="bold")
        elif col == -1:  # row labels
            cell.set_facecolor(HEADER_BG)
            cell.set_text_props(color=TEXT_COLOR, fontweight="bold")
        else:
            cell.set_facecolor(BG_COLOR)
            cell.set_text_props(color=TEXT_COLOR)
            col_name = display.columns[col]
            val = display.iloc[row - 1, col]
            if col_name == "Signal":
                c = SIGNAL_COLORS.get(val, NEUTRAL_COLOR)
                cell.set_text_props(color=c, fontweight="bold")
            elif col_name == "Trend":
                if val == "↑":
                    cell.set_text_props(color=BULLISH_COLOR, fontweight="bold")
                elif val == "↓":
                    cell.set_text_props(color=BEARISH_COLOR, fontweight="bold")
            elif col_name == "ADX Trend":
                if val == "Uptrend":
                    cell.set_text_props(color=BULLISH_COLOR)
                elif val == "Downtrend":
                    cell.set_text_props(color=BEARISH_COLOR)
            elif col_name == "Bollinger":
                if val == "Upper":
                    cell.set_text_props(color=BULLISH_COLOR)
                elif val == "Lower":
                    cell.set_text_props(color=BEARISH_COLOR)

    title = "Technical Matrix"
    _sub_parts = []
    if data_date:
        _sub_parts.append(f"Data: {data_date}")
    if frequency:
        _sub_parts.append(f"Freq: {frequency}")
    sub = "  |  ".join(_sub_parts)
    full_title = f"{title}\n{sub}" if sub else title
    ax.set_title(full_title, color=TEXT_WHITE, fontsize=14,
                 fontweight="bold", pad=15)
    return _fig_to_bytes(fig)


# ---------------------------------------------------------------------------
# 2. Event Analysis — styled table image
# ---------------------------------------------------------------------------

def chart_event_table(df: pd.DataFrame, *,
                      data_date: str = "",
                      frequency: str = "") -> io.BytesIO:
    """Render event analysis as a coloured table image."""
    cols = ["New Spot", "Ret vs USD", "1m Vol", "1m Vol Chg", "Signal"]
    display = df[cols].copy()

    display["New Spot"] = display["New Spot"].apply(
        lambda v: f"{v:.4f}" if pd.notna(v) else "—")
    display["Ret vs USD"] = display["Ret vs USD"].apply(
        lambda v: f"{v:+.2f}%" if pd.notna(v) else "—")
    display["1m Vol"] = display["1m Vol"].apply(
        lambda v: f"{v:.1f}%" if pd.notna(v) else "—")
    display["1m Vol Chg"] = display["1m Vol Chg"].apply(
        lambda v: f"{v:+.2f}%" if pd.notna(v) else "—")

    n_rows = display.shape[0]
    fig_h = max(4.0, 0.35 * n_rows + 1.6)
    fig, ax = plt.subplots(figsize=(10, fig_h))
    ax.axis("off")
    _apply_theme(fig)

    table = ax.table(
        cellText=display.values,
        rowLabels=display.index,
        colLabels=display.columns,
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.4)

    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor(GRID_COLOR)
        if row == 0:
            cell.set_facecolor(HEADER_BG)
            cell.set_text_props(color=TEXT_WHITE, fontweight="bold")
        elif col == -1:
            cell.set_facecolor(HEADER_BG)
            cell.set_text_props(color=TEXT_COLOR, fontweight="bold")
        else:
            cell.set_facecolor(BG_COLOR)
            cell.set_text_props(color=TEXT_COLOR)
            col_name = display.columns[col]
            if col_name == "Signal":
                val = display.iloc[row - 1, col]
                c = SIGNAL_COLORS.get(val, NEUTRAL_COLOR)
                cell.set_text_props(color=c, fontweight="bold")
            elif col_name in ("Ret vs USD", "1m Vol Chg"):
                raw = df.iloc[row - 1][col_name]
                if pd.notna(raw):
                    cell.set_text_props(
                        color=BULLISH_COLOR if raw > 0 else BEARISH_COLOR)

    sub_parts = []
    if data_date:
        sub_parts.append(f"Data: {data_date}")
    if frequency:
        sub_parts.append(f"Freq: {frequency}")
    sub = "  |  ".join(sub_parts)
    title = "Event Analysis (Vol-Guided Signals)"
    full_title = f"{title}\n{sub}" if sub else title
    ax.set_title(full_title, color=TEXT_WHITE, fontsize=14,
                 fontweight="bold", pad=15)
    return _fig_to_bytes(fig)


# ---------------------------------------------------------------------------
# 3. CARS — regime header + rank heatmap
# ---------------------------------------------------------------------------

def chart_cars(df: pd.DataFrame | None, *,
               data_date: str = "",
               frequency: str = "") -> io.BytesIO | None:
    """Render CARS regime info + factor ranking heatmap."""
    if df is None or df.empty:
        return None

    regime = df.attrs.get("regime", "Unknown")
    eq_z = df.attrs.get("equity_z", 0.0)
    bd_z = df.attrs.get("bond_z", 0.0)
    cm_z = df.attrs.get("commodity_z", 0.0)

    rank_cols = ["Equity", "Rates", "Commodity"]
    rank_data = df[rank_cols].values.astype(float)

    fig, (ax_info, ax_hm) = plt.subplots(
        2, 1, figsize=(8, max(4.0, 0.4 * len(df) + 2.5)),
        gridspec_kw={"height_ratios": [1, max(3, len(df) * 0.35)]},
    )
    _apply_theme(fig, ax_info)
    _apply_theme(fig, ax_hm)

    # Top panel — regime info
    ax_info.axis("off")
    regime_color = BEARISH_COLOR if regime == "Shock" else BULLISH_COLOR
    ax_info.text(0.5, 0.7, f"Regime: {regime}", color=regime_color,
                 fontsize=16, fontweight="bold", ha="center", va="center",
                 transform=ax_info.transAxes)
    z_text = (f"Equity z: {eq_z:+.2f}  |  Bond z: {bd_z:+.2f}  "
              f"|  Commodity z: {cm_z:+.2f}")
    ax_info.text(0.5, 0.25, z_text, color=TEXT_COLOR, fontsize=10,
                 ha="center", va="center", transform=ax_info.transAxes)

    # Bottom panel — rank heatmap (1=best→teal, 10=worst→red)
    norm = mcolors.Normalize(vmin=1, vmax=10)
    ax_hm.imshow(rank_data, cmap=_BBG_RANK_CMAP, norm=norm, aspect="auto")

    ax_hm.set_xticks(range(len(rank_cols)))
    ax_hm.set_xticklabels(rank_cols, color=TEXT_COLOR, fontsize=10)
    ax_hm.set_yticks(range(len(df)))
    ax_hm.set_yticklabels(df.index, color=TEXT_COLOR, fontsize=9)
    ax_hm.tick_params(length=0)

    for i in range(len(df)):
        for j in range(len(rank_cols)):
            val = int(rank_data[i, j])
            txt_color = BG_COLOR if 3 < val < 8 else TEXT_WHITE
            ax_hm.text(j, i, str(val), ha="center", va="center",
                       color=txt_color, fontsize=10, fontweight="bold")

    for i, label in enumerate(ax_hm.get_yticklabels()):
        signal = df.iloc[i]["Bullish/Bearish"]
        label.set_color(BULLISH_COLOR if signal == "Bullish" else BEARISH_COLOR)
        label.set_fontweight("bold")

    ax_hm.set_title("Factor Rankings (1 = highest sensitivity)",
                     color=TEXT_COLOR, fontsize=11, pad=8)

    sub_parts = []
    if data_date:
        sub_parts.append(f"Data: {data_date}")
    if frequency:
        sub_parts.append(f"Freq: {frequency}")
    sub = f"\n{'  |  '.join(sub_parts)}" if sub_parts else ""
    fig.suptitle(f"CARS — Cross-Asset Regime Switching{sub}",
                 color=TEXT_WHITE, fontsize=14, fontweight="bold", y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    return _fig_to_bytes(fig)


# ---------------------------------------------------------------------------
# 4. Timezone Summary — horizontal grouped bar chart
# ---------------------------------------------------------------------------

def chart_timezone_summary(df: pd.DataFrame, *,
                           data_date: str = "",
                           frequency: str = "") -> io.BytesIO:
    """Horizontal grouped bar chart of 3-zone returns."""
    zones = ["Asia", "Europe", "America"]
    existing = [z for z in zones if z in df.columns]

    fig_h = max(4.0, 0.35 * len(df) + 1.8)
    fig, ax = plt.subplots(figsize=(9, fig_h))
    _apply_theme(fig, ax)

    y = np.arange(len(df))
    bar_h = 0.25
    colors = {"Asia": ACCENT2_COLOR, "Europe": ACCENT_COLOR, "America": "#9B59B6"}

    for i, zone in enumerate(existing):
        vals = df[zone].fillna(0).values
        ax.barh(y + i * bar_h, vals, bar_h * 0.9, label=zone,
                color=colors.get(zone, ACCENT_COLOR), alpha=0.85)

    ax.set_yticks(y + bar_h * (len(existing) - 1) / 2)
    ax.set_yticklabels(df.index, fontsize=9)
    ax.axvline(0, color=GRID_COLOR, linewidth=0.8)
    ax.set_xlabel("Cumulative Return (%)", fontsize=10)
    ax.legend(loc="lower right", fontsize=9, facecolor=HEADER_BG,
              edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR)
    ax.grid(axis="x", color=GRID_COLOR, alpha=0.3)
    subtitle_parts = []
    if data_date:
        subtitle_parts.append(f"Data: {data_date}")
    if frequency:
        subtitle_parts.append(f"Freq: {frequency}")
    subtitle = "\n".join(subtitle_parts) if subtitle_parts else ""
    title = f"Time Zone Returns\n{subtitle}" if subtitle else "Time Zone Returns"
    ax.set_title(title, color=TEXT_WHITE, fontsize=13,
                 fontweight="bold")
    ax.invert_yaxis()
    return _fig_to_bytes(fig)


# ---------------------------------------------------------------------------
# 5. Timezone Heatmap — 8-slot colour heatmap
# ---------------------------------------------------------------------------

def chart_timezone_heatmap(df: pd.DataFrame, *,
                           data_date: str = "",
                           frequency: str = "") -> io.BytesIO:
    """Diverging heatmap of 8 three-hour return slots."""
    data = df.fillna(0).values.astype(float)
    vmax = max(abs(data.min()), abs(data.max()), 0.01)

    fig_h = max(4.0, 0.38 * len(df) + 1.8)
    fig, ax = plt.subplots(figsize=(10, fig_h))
    _apply_theme(fig, ax)

    norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)
    im = ax.imshow(data, cmap=_BBG_CMAP, norm=norm, aspect="auto")

    ax.set_xticks(range(len(df.columns)))
    ax.set_xticklabels(df.columns, fontsize=8, rotation=30, ha="right")
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(df.index, fontsize=9)
    ax.tick_params(length=0)

    for i in range(len(df)):
        for j in range(len(df.columns)):
            val = data[i, j]
            txt_color = TEXT_WHITE if abs(val) > vmax * 0.3 else TEXT_COLOR
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    color=txt_color, fontsize=7)

    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.ax.tick_params(colors=TEXT_COLOR, labelsize=8)
    cbar.set_label("Return (%)", color=TEXT_COLOR, fontsize=9)

    subtitle_parts = []
    if data_date:
        subtitle_parts.append(f"Data: {data_date}")
    if frequency:
        subtitle_parts.append(f"Freq: {frequency}")
    subtitle = "\n".join(subtitle_parts) if subtitle_parts else ""
    title = f"Time Zone Heatmap (3h slots, UTC)\n{subtitle}" if subtitle else "Time Zone Heatmap (3h slots, UTC)"
    ax.set_title(title, color=TEXT_WHITE,
                 fontsize=13, fontweight="bold")
    return _fig_to_bytes(fig)


# ---------------------------------------------------------------------------
# 6. PCA ETF — scree plot + loadings heatmap
# ---------------------------------------------------------------------------

def chart_pca_etf(report: dict | None, *,
                  data_date: str = "",
                  frequency: str = "") -> list[io.BytesIO]:
    """Return list of chart buffers: [scree_plot, loadings_heatmap]."""
    if not report:
        return []

    buffers: list[io.BytesIO] = []
    var_exp = report["variance_explained"]
    cum_var = report["cumulative_variance"]
    regime = report.get("regime", "")
    eff_dim = report.get("effective_dim", 0)
    window = report.get("window", 120)
    n_pcs = len(var_exp)
    pc_labels = [f"PC{i+1}" for i in range(n_pcs)]

    freq_label = frequency or f"Daily ({window}d rolling)"

    # --- Scree plot ---
    fig, ax = plt.subplots(figsize=(8, 4.5))
    _apply_theme(fig, ax)

    x = np.arange(n_pcs)
    ax.bar(x, [v * 100 for v in var_exp], color=ACCENT_COLOR, alpha=0.8,
           label="Individual")
    ax.plot(x, [v * 100 for v in cum_var], color=ACCENT2_COLOR, marker="o",
            linewidth=2, label="Cumulative")

    ax.set_xticks(x)
    ax.set_xticklabels(pc_labels)
    ax.set_ylabel("Variance Explained (%)", fontsize=10)
    ax.legend(loc="center right", fontsize=9, facecolor=HEADER_BG,
              edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR)
    ax.grid(axis="y", color=GRID_COLOR, alpha=0.3)

    regime_color = BEARISH_COLOR if "Concentrated" in regime else BULLISH_COLOR
    title_main = f"PCA ETF — Regime: {regime} (eff. dim = {eff_dim:.1f})"
    subtitle_parts = []
    if data_date:
        subtitle_parts.append(f"Data: {data_date}")
    if freq_label:
        subtitle_parts.append(f"Freq: {freq_label}")
    subtitle = "\n".join(subtitle_parts) if subtitle_parts else ""
    title = f"{title_main}\n{subtitle}" if subtitle else title_main
    ax.set_title(
        title,
        color=regime_color, fontsize=12, fontweight="bold",
    )
    buffers.append(_fig_to_bytes(fig))

    # --- Loadings heatmap ---
    loadings: pd.DataFrame = report["loadings"]
    data = loadings.values.astype(float)
    vmax = max(abs(data.min()), abs(data.max()), 0.01)

    # ETF labels with descriptions
    y_labels = [_etf_label(t) for t in loadings.index]

    fig_h = max(5.0, 0.35 * len(loadings) + 1.8)
    fig, ax = plt.subplots(figsize=(9, fig_h))
    _apply_theme(fig, ax)

    norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)
    im = ax.imshow(data, cmap=_BBG_CMAP, norm=norm, aspect="auto")

    ax.set_xticks(range(loadings.shape[1]))
    ax.set_xticklabels(loadings.columns, fontsize=10)
    ax.set_yticks(range(len(loadings)))
    ax.set_yticklabels(y_labels, fontsize=7)
    ax.tick_params(length=0)

    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            val = data[i, j]
            txt_color = TEXT_WHITE if abs(val) > vmax * 0.4 else TEXT_COLOR
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    color=txt_color, fontsize=7)

    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.ax.tick_params(colors=TEXT_COLOR, labelsize=8)

    title_main = "PCA ETF — Factor Loadings"
    subtitle_parts = []
    if data_date:
        subtitle_parts.append(f"Data: {data_date}")
    if freq_label:
        subtitle_parts.append(f"Freq: {freq_label}")
    subtitle = "\n".join(subtitle_parts) if subtitle_parts else ""
    title = f"{title_main}\n{subtitle}" if subtitle else title_main
    ax.set_title(title, color=TEXT_WHITE,
                 fontsize=12, fontweight="bold")
    buffers.append(_fig_to_bytes(fig))

    return buffers


# ---------------------------------------------------------------------------
# 7. PCA FX — loadings heatmap + PC score bar chart
# ---------------------------------------------------------------------------

def chart_pca_fx(report: dict | None, *,
                 data_date: str = "",
                 frequency: str = "") -> list[io.BytesIO]:
    """Return list of chart buffers: [loadings_heatmap, scores_bar]."""
    if not report:
        return []

    buffers: list[io.BytesIO] = []
    regime = report.get("regime", "")
    eff_dim = report.get("effective_dim", 0)
    labels = report.get("labels", {})
    window = report.get("window", 120)

    freq_label = frequency or f"Daily ({window}d rolling)"

    # --- Loadings heatmap ---
    loadings: pd.DataFrame = report["loadings"]
    data = loadings.values.astype(float)
    vmax = max(abs(data.min()), abs(data.max()), 0.01)

    fig_h = max(4.0, 0.4 * len(loadings) + 1.8)
    fig, ax = plt.subplots(figsize=(7, fig_h))
    _apply_theme(fig, ax)

    norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)
    im = ax.imshow(data, cmap=_BBG_CMAP, norm=norm, aspect="auto")

    col_labels = [f"{c}\n({labels.get(c, '')})" if labels.get(c) else c
                  for c in loadings.columns]
    ax.set_xticks(range(loadings.shape[1]))
    ax.set_xticklabels(col_labels, fontsize=9)
    ax.set_yticks(range(len(loadings)))
    ax.set_yticklabels(loadings.index, fontsize=9)
    ax.tick_params(length=0)

    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            val = data[i, j]
            txt_color = TEXT_WHITE if abs(val) > vmax * 0.4 else TEXT_COLOR
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    color=txt_color, fontsize=8)

    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.ax.tick_params(colors=TEXT_COLOR, labelsize=8)

    regime_color = BEARISH_COLOR if "Concentrated" in regime else BULLISH_COLOR
    title_main = f"PCA FX — Regime: {regime} (eff. dim = {eff_dim:.1f})"
    subtitle_parts = []
    if data_date:
        subtitle_parts.append(f"Data: {data_date}")
    if freq_label:
        subtitle_parts.append(f"Freq: {freq_label}")
    subtitle = "\n".join(subtitle_parts) if subtitle_parts else ""
    title = f"{title_main}\n{subtitle}" if subtitle else title_main
    ax.set_title(
        title,
        color=regime_color, fontsize=12, fontweight="bold",
    )
    buffers.append(_fig_to_bytes(fig))

    # --- PC scores + z-scores bar chart ---
    pc_scores = report.get("pc_scores")
    pc_zscores = report.get("pc_zscores")
    if pc_scores is not None and pc_zscores is not None:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 4))
        _apply_theme(fig, ax1)
        _apply_theme(fig, ax2)

        x = np.arange(len(pc_scores))
        score_labels = [f"{k}\n({labels.get(k, '')})" if labels.get(k) else k
                        for k in pc_scores.index]

        # Scores
        ax1.bar(x, pc_scores.values, color=ACCENT_COLOR, alpha=0.85)
        ax1.set_xticks(x)
        ax1.set_xticklabels(score_labels, fontsize=8)
        ax1.set_title("PC Scores (latest)", color=TEXT_WHITE, fontsize=11)
        ax1.grid(axis="y", color=GRID_COLOR, alpha=0.3)
        ax1.axhline(0, color=GRID_COLOR, linewidth=0.8)

        # Z-scores with color coding
        z_vals = pc_zscores.values
        z_colors = []
        for z in z_vals:
            if abs(z) > 2:
                z_colors.append(BEARISH_COLOR)
            elif abs(z) > 1:
                z_colors.append(ACCENT2_COLOR)
            else:
                z_colors.append(BULLISH_COLOR)

        ax2.bar(x, z_vals, color=z_colors, alpha=0.85)
        ax2.set_xticks(x)
        ax2.set_xticklabels(score_labels, fontsize=8)
        ax2.set_title("PC Z-Scores (60d rolling)", color=TEXT_WHITE,
                      fontsize=11)
        ax2.axhline(2, color=BEARISH_COLOR, linestyle="--", alpha=0.5)
        ax2.axhline(-2, color=BEARISH_COLOR, linestyle="--", alpha=0.5)
        ax2.axhline(0, color=GRID_COLOR, linewidth=0.8)
        ax2.grid(axis="y", color=GRID_COLOR, alpha=0.3)

        title_main = "PCA FX — Factor Scores"
        subtitle_parts = []
        if data_date:
            subtitle_parts.append(f"Data: {data_date}")
        if freq_label:
            subtitle_parts.append(f"Freq: {freq_label}")
        subtitle = "\n".join(subtitle_parts) if subtitle_parts else ""
        title = f"{title_main}\n{subtitle}" if subtitle else title_main
        fig.suptitle(title, color=TEXT_WHITE,
                     fontsize=12, fontweight="bold")
        fig.tight_layout(rect=[0, 0, 1, 0.93])
        buffers.append(_fig_to_bytes(fig))

    return buffers
