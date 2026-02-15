"""Methodology explanations for each analysis component."""
from __future__ import annotations

METHODOLOGIES: dict[str, dict[str, str]] = {
    "technicals": {
        "title": "Technical Matrix",
        "description": (
            "Combines four positioning/momentum indicators to produce a "
            "directional signal for each FX pair. Inspired by BAML's "
            "FX Positioning & Technicals framework."
        ),
        "metrics": (
            "<b>MAA (Moving Average Aggregator)</b>\n"
            "Average of 28 short/long SMA crossover signals (e.g. 5/20, "
            "10/50, 20/200). Score 0-100.\n"
            "• >60 = Uptrend positioning\n"
            "• <40 = Downtrend positioning\n"
            "• 40-60 = Neutral\n\n"
            "<b>UD (Up/Down Volatility)</b>\n"
            "Ratio of downside to total realized vol, expressed as a 1-year "
            "percentile rank. High UD = greater downside moves = bearish.\n\n"
            "<b>RS (Residual Skew)</b>\n"
            "Rolling 26-week skewness of weekly returns, 1-year percentile rank. "
            "High RS = stretched long positioning.\n\n"
            "<b>ADX Trend</b>\n"
            "• <20: Range\n"
            "• 20-25: Transition\n"
            "• >25: Trending (direction from DMI+/DMI-)\n\n"
            "<b>Bollinger Bands</b>\n"
            "20-day, 2σ bands. Upper/Lower flags when spot breaches."
        ),
        "signals": (
            "<b>Uptrend (MAA>60):</b>\n"
            "• Bullish: UD<50 AND RS<50 (clean continuation)\n"
            "• Bearish: UD>80 AND RS>80 (reversal risk)\n"
            "• Sl. Bullish/Bearish: one indicator supports\n\n"
            "<b>Downtrend (MAA<40):</b>\n"
            "• Bullish: UD<20 AND RS<20 (reversal candidate)\n"
            "• Bearish: UD>50 AND RS>50 (continuation)\n"
            "• Sl. Bullish/Bearish: one indicator supports\n\n"
            "<b>Neutral (MAA 40-60):</b> No Signal"
        ),
    },
    "signals": {
        "title": "Event Analysis (Vol-Guided Signals)",
        "description": (
            "Classifies each FX pair into directional signals based on the "
            "interaction between spot returns, realized volatility changes, "
            "and VIX moves over the past week."
        ),
        "metrics": (
            "<b>Spot Return</b>\n"
            "Week-over-week close change (5 trading days), sign-corrected "
            "so positive = foreign currency strength vs USD.\n\n"
            "<b>Realized Vol (1w / 1m)</b>\n"
            "Annualized rolling volatility over 5-day and 21-day windows. "
            "Change is measured vs 5 days ago.\n\n"
            "<b>VIX Change</b>\n"
            "Weekly change in VIX proxy (VIXY ETF). Rising VIX confirms "
            "risk-off moves."
        ),
        "signals": (
            "<b>Bearish Continuation:</b>\n"
            "Spot down >1% + Vol rising >0.5% + VIX rising → "
            "risk-off trend intact\n\n"
            "<b>Bearish Contrarian:</b>\n"
            "Spot up >1% + Vol rising sharply >1% → "
            "suspicious rally, high vol suggests stress\n\n"
            "<b>Bullish Continuation:</b>\n"
            "Spot up >1% + Vol falling → "
            "healthy risk-on, low-vol rally\n\n"
            "<b>Bullish Contrarian:</b>\n"
            "Spot down >1% + Vol falling + VIX falling → "
            "oversold bounce candidate"
        ),
    },
    "cars": {
        "title": "CARS — Cross-Asset Regime Switching",
        "description": (
            "Identifies whether markets are in a Shock or Normal regime "
            "using cross-asset z-scores, then ranks G10 currencies by their "
            "sensitivity to equity, rates, and commodity factors."
        ),
        "metrics": (
            "<b>Regime Detection</b>\n"
            "Weekly z-scores (52-week window) for:\n"
            "• Equity (SPY): Shock if z < -1.0\n"
            "• Bonds (TLT): Shock if z < -1.0 (yields spiking)\n"
            "• Commodities (DBC): Shock if z < -2.0\n"
            "Any breach → Shock regime.\n\n"
            "<b>Factor Rankings</b>\n"
            "52-week rolling correlation of each currency vs SPY, TLT, DBC. "
            "Currencies ranked 1-10 per factor."
        ),
        "signals": (
            "<b>Shock Week:</b>\n"
            "Buy JPY & CHF (safe havens), Sell all others vs USD.\n\n"
            "<b>Normal Week:</b>\n"
            "Rank by dominant performing factor:\n"
            "• Top 3 → Bullish\n"
            "• Bottom 3 → Bearish\n"
            "• Middle → No Signal\n\n"
            "<b>Commodity Overlay:</b>\n"
            "If |commodity_z| > 2.0, override signal for currencies "
            "with top commodity sensitivity."
        ),
    },
    "timezone": {
        "title": "Time Zone Returns",
        "description": (
            "Decomposes FX returns by trading session to reveal which "
            "time zone is driving price action. Uses hourly bar data."
        ),
        "metrics": (
            "<b>Three Sessions (UTC):</b>\n"
            "• Asia: 00:00-08:00\n"
            "• Europe: 08:00-13:00\n"
            "• Americas: 13:00-00:00\n\n"
            "<b>Eight 3-Hour Slots:</b>\n"
            "Granular breakdown from 8am-11am through 5am-8am UTC.\n\n"
            "<b>Calculation:</b>\n"
            "Cumulative hourly returns per zone over the lookback period "
            "(default 5 days). Expressed as percentage."
        ),
        "signals": (
            "<b>How to read:</b>\n"
            "• Large positive in Asia + flat elsewhere → Asian buying pressure\n"
            "• Negative Americas + positive Europe → US selling, EU dip-buying\n"
            "• Consistent one-zone dominance → flow-driven trend\n\n"
            "<b>Lookback options:</b>\n"
            "/timezone (5d) | /timezone 1m (21d) | /timezone 3m (63d)"
        ),
    },
    "pca_etf": {
        "title": "PCA — ETF Factor Decomposition",
        "description": (
            "Runs PCA on 120-day log returns of ~25 ETFs across equities, "
            "sectors, international, fixed income, and commodities. "
            "Reveals the dominant risk factors and detects regime shifts."
        ),
        "metrics": (
            "<b>Variance Explained:</b>\n"
            "How much of total market movement each PC captures. "
            "PC1 typically 30-50% in normal markets.\n\n"
            "<b>Effective Dimensionality:</b>\n"
            "Participation ratio: (Σλ)²/Σλ². Measures how many "
            "independent factors drive the market.\n"
            "• ≈1: One factor dominates (risk-off)\n"
            "• ≈N: Fully diversified\n\n"
            "<b>Loadings:</b>\n"
            "Each ETF's weight on a PC. Large positive/negative = "
            "strongly driven by that factor."
        ),
        "signals": (
            "<b>Dimensionality Collapse:</b>\n"
            "PC1 > 60% variance OR eff. dim < 3.0 → "
            "single-factor risk-off. Correlations spike, "
            "diversification breaks down.\n\n"
            "<b>Normal:</b>\n"
            "Multiple independent factors. Read PC1 loadings for "
            "the dominant theme (e.g. risk-on/off), PC2-3 for "
            "sector rotation signals."
        ),
    },
    "pca_fx": {
        "title": "PCA — FX Factor Analysis",
        "description": (
            "Runs PCA on 120-day G10 FX returns to extract the "
            "Dollar Factor, Carry Factor, and Regional/Momentum factors. "
            "Identifies extreme factor positioning via z-scores."
        ),
        "metrics": (
            "<b>PC1 (Dollar Factor):</b>\n"
            "When >60% of FX loadings share the same sign, PC1 captures "
            "broad USD strength/weakness. Labeled 'Market Factor' otherwise.\n\n"
            "<b>PC2 (Carry Factor):</b>\n"
            "Separates high-yield (AUD, NZD) from low-yield (JPY, CHF) "
            "currencies.\n\n"
            "<b>PC3 (Regional/Momentum):</b>\n"
            "Captures residual regional or momentum effects.\n\n"
            "<b>PC Scores & Z-Scores:</b>\n"
            "Today's projection onto each factor, plus 60-day rolling "
            "z-score for extremes."
        ),
        "signals": (
            "<b>Extreme z-scores (|z| > 2):</b>\n"
            "Factor is stretched — mean-reversion likely.\n\n"
            "<b>PC1 z > +2:</b> USD extremely strong, watch for reversal.\n"
            "<b>PC1 z < -2:</b> USD extremely weak.\n"
            "<b>PC2 z > +2:</b> Carry trade extremely stretched.\n\n"
            "<b>Regime Detection:</b>\n"
            "Same as ETF PCA — Dimensionality Collapse if PC1 > 60% "
            "or eff. dim < 3.0."
        ),
    },
}

# Button labels and callback data for the inline keyboard
METHODOLOGY_BUTTONS: list[tuple[str, str]] = [
    ("Technical Matrix", "method_technicals"),
    ("Event Analysis", "method_signals"),
    ("CARS Regime", "method_cars"),
    ("Time Zone", "method_timezone"),
    ("PCA ETF", "method_pca_etf"),
    ("PCA FX", "method_pca_fx"),
]
