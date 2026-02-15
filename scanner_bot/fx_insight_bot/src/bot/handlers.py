"""
Telegram bot command handlers.

Commands:
  /report     - Full morning brief (all 4 components)
  /technicals - Technical Matrix only
  /signals    - Event Analysis only
  /cars       - CARS regime + signals
  /timezone   - Time Zone returns (optional: /timezone 1m, /timezone 3m)
  /status     - Data freshness info
  /help       - Command list
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from ..report.generator import ReportGenerator
from .formatter import (
    format_full_report,
    format_technical_matrix,
    format_event_table,
    format_cars,
    format_timezone_summary,
    format_timezone_heatmap,
)

logger = logging.getLogger(__name__)

HELP_TEXT = """<b>FX Quant Insight Bot</b>

<b>Commands:</b>
/report - Full daily brief (all components)
/technicals - Technical Matrix (MAA, ADX, Bollinger, S/R)
/signals - Event Analysis (vol-guided signals)
/cars - Cross-Asset Regime Switching
/timezone - Time Zone returns (add 1m or 3m for longer lookback)
/status - Data freshness
/help - This message

<i>Scheduled: Morning brief 6:30 AM ET, EOD recap 5:00 PM ET</i>
"""


class FXInsightBot:
    """Telegram bot with scheduled sends and on-demand commands."""

    def __init__(
        self,
        token: str,
        chat_id: str,
        report_gen: ReportGenerator,
    ):
        self._token = token
        self._chat_id = chat_id
        self._report = report_gen
        self._app = Application.builder().token(token).build()
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        self._app.add_handler(CommandHandler("report", self._cmd_report))
        self._app.add_handler(CommandHandler("technicals", self._cmd_technicals))
        self._app.add_handler(CommandHandler("signals", self._cmd_signals))
        self._app.add_handler(CommandHandler("cars", self._cmd_cars))
        self._app.add_handler(CommandHandler("timezone", self._cmd_timezone))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(CommandHandler("start", self._cmd_help))

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    async def _cmd_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Generating full report...")
        try:
            self._report.refresh_data(include_hourly=True)
            report = self._report.generate_morning_brief()
            messages = format_full_report(report)
            for msg in messages:
                await update.message.reply_text(msg, parse_mode="HTML")
        except Exception:
            logger.exception("Error generating report")
            await update.message.reply_text("Error generating report. Check logs.")

    async def _cmd_technicals(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Loading technicals...")
        try:
            self._report.refresh_data(include_hourly=False)
            matrix = self._report.generate_technical_matrix()
            messages = format_technical_matrix(matrix)
            for msg in messages:
                await update.message.reply_text(msg, parse_mode="HTML")
        except Exception:
            logger.exception("Error generating technicals")
            await update.message.reply_text("Error generating technicals.")

    async def _cmd_signals(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Loading event analysis...")
        try:
            self._report.refresh_data(include_hourly=False)
            ev = self._report.generate_event_table()
            messages = format_event_table(ev)
            for msg in messages:
                await update.message.reply_text(msg, parse_mode="HTML")
        except Exception:
            logger.exception("Error generating signals")
            await update.message.reply_text("Error generating event analysis.")

    async def _cmd_cars(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Loading CARS analysis...")
        try:
            self._report.refresh_data(include_hourly=False)
            cars = self._report.generate_cars()
            msg = format_cars(cars)
            await update.message.reply_text(msg, parse_mode="HTML")
        except Exception:
            logger.exception("Error generating CARS")
            await update.message.reply_text("Error generating CARS.")

    async def _cmd_timezone(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        # Parse optional lookback argument
        lookback_days = 5  # default 1 week
        if context.args:
            arg = context.args[0].lower()
            if arg in ("1m", "1mo", "1month"):
                lookback_days = 21
            elif arg in ("3m", "3mo", "3month"):
                lookback_days = 63
            elif arg in ("1w", "1wk", "1week"):
                lookback_days = 5

        await update.message.reply_text(f"Loading timezone analysis ({lookback_days}d)...")
        try:
            self._report.refresh_data(include_hourly=True)
            summary = self._report.generate_timezone_summary(lookback_days)
            msg = format_timezone_summary(summary)
            await update.message.reply_text(msg, parse_mode="HTML")

            heatmap = self._report.generate_timezone_heatmap(lookback_days)
            hm_msgs = format_timezone_heatmap(heatmap)
            for m in hm_msgs:
                await update.message.reply_text(m, parse_mode="HTML")
        except Exception:
            logger.exception("Error generating timezone analysis")
            await update.message.reply_text("Error generating timezone analysis.")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from ..data.tickers import ALL_FX_PAIRS, CROSS_ASSET

        lines = ["<b>Data Status</b>\n"]

        # Check a few representative pairs
        for pair in ["EURUSD", "USDJPY", "USDCNH"]:
            last = self._report._cache.daily_last_date(pair)
            lines.append(f"{pair} daily: {last or 'No data'}")

        for name, symbol in CROSS_ASSET.items():
            last = self._report._cache.cross_asset_last_date(symbol)
            lines.append(f"{symbol} ({name}): {last or 'No data'}")

        # Hourly
        hourly_last = self._report._cache.hourly_last_date("EURUSD")
        lines.append(f"\nEURUSD hourly: {hourly_last or 'No data'}")

        lines.append(f"\nServer time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(HELP_TEXT, parse_mode="HTML")

    # ------------------------------------------------------------------
    # Scheduled message sending
    # ------------------------------------------------------------------

    async def send_scheduled_messages(self, messages: list[str]) -> None:
        """Send pre-formatted messages to the configured chat."""
        for msg in messages:
            try:
                await self._app.bot.send_message(
                    chat_id=self._chat_id, text=msg, parse_mode="HTML",
                )
            except Exception:
                logger.exception("Failed to send scheduled message")

    @property
    def app(self) -> Application:
        return self._app
