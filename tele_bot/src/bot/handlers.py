"""
Telegram bot command handlers.

Commands:
  /report     - Full morning brief (all components)
  /technicals - Technical Matrix only
  /signals    - Event Analysis only
  /cars       - CARS regime + signals
  /timezone   - Time Zone returns (optional: /timezone 1m, /timezone 3m)
  /pca_etf    - PCA on ETF universe (factor decomposition)
  /pca_fx     - PCA on FX rates (Dollar/Carry factors)
  /status     - Data freshness info
  /help       - Command list
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from ..report.generator import ReportGenerator
from .methodology import METHODOLOGIES, METHODOLOGY_BUTTONS
from ..report.charts import (
    chart_technical_matrix,
    chart_event_table,
    chart_cars,
    chart_timezone_summary,
    chart_timezone_heatmap,
    chart_pca_etf,
    chart_pca_fx,
)
from .formatter import (
    format_full_report,
    format_technical_matrix,
    format_event_table,
    format_cars,
    format_timezone_summary,
    format_timezone_heatmap,
    format_pca_etf,
    format_pca_fx,
)

logger = logging.getLogger(__name__)


class _ChatProxy:
    """Lightweight proxy that mimics Message.reply_text / reply_photo for broadcast."""

    def __init__(self, bot, chat_id: int):
        self._bot = bot
        self._chat_id = chat_id

    async def reply_text(self, text: str, **kwargs) -> None:
        await self._bot.send_message(chat_id=self._chat_id, text=text, **kwargs)

    async def reply_photo(self, photo, **kwargs) -> None:
        await self._bot.send_photo(chat_id=self._chat_id, photo=photo, **kwargs)

HELP_TEXT = """

<b>Commands:</b>
/report - Full daily brief (all components)
/technicals - Technical Matrix (MAA, ADX, Bollinger, S/R)
/signals - Event Analysis (vol-guided signals)
/cars - Cross-Asset Regime Switching
/timezone - Time Zone returns (add 1m or 3m for longer lookback)
/pca_etf - PCA ETF factor decomposition (regime, loadings)
/pca_fx - PCA FX factor analysis (Dollar/Carry/Regional)
/methodology - How each analysis works
/status - Data freshness
/help - This message

<i>Scheduled: Morning brief 6:00 AM SGT (weekdays)</i>
"""


class FXInsightBot:
    """Telegram bot with scheduled sends and on-demand commands.

    Access control:
    - If whitelist is provided, only those user IDs can interact.
    - If whitelist is empty/None, all users are allowed.
    - All users who send /start are subscribed for scheduled broadcasts.
    """

    def __init__(
        self,
        token: str,
        chat_id: str | None,
        report_gen: ReportGenerator,
        whitelist: set[int] | None = None,
        post_init: Callable[[Application], Awaitable[None]] | None = None,
        post_shutdown: Callable[[Application], Awaitable[None]] | None = None,
    ):
        self._token = token
        self._report = report_gen
        self._whitelist = whitelist or set()
        self._subscribers: set[int] = set()
        if chat_id:
            self._subscribers.add(int(chat_id))
        builder = Application.builder().token(token)
        if post_init:
            builder.post_init(post_init)
        if post_shutdown:
            builder.post_shutdown(post_shutdown)
        self._app = builder.build()
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        self._app.add_handler(CommandHandler("report", self._cmd_report))
        self._app.add_handler(CommandHandler("technicals", self._cmd_technicals))
        self._app.add_handler(CommandHandler("signals", self._cmd_signals))
        self._app.add_handler(CommandHandler("cars", self._cmd_cars))
        self._app.add_handler(CommandHandler("timezone", self._cmd_timezone))
        self._app.add_handler(CommandHandler("pca_etf", self._cmd_pca_etf))
        self._app.add_handler(CommandHandler("pca_fx", self._cmd_pca_fx))
        self._app.add_handler(CommandHandler("methodology", self._cmd_methodology))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CallbackQueryHandler(self._handle_methodology_cb, pattern="^method_"))

    # ------------------------------------------------------------------
    # Access control
    # ------------------------------------------------------------------

    def _is_allowed(self, user_id: int) -> bool:
        if not self._whitelist:
            return True  # no whitelist = open access
        return user_id in self._whitelist

    async def _check_access(self, update: Update) -> bool:
        user_id = update.effective_user.id
        if self._is_allowed(user_id):
            return True
        logger.warning("Unauthorized access attempt by user %d", user_id)
        await update.message.reply_text("Access denied. You are not on the whitelist.")
        return False

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._check_access(update):
            return
        chat_id = update.effective_chat.id
        self._subscribers.add(chat_id)
        logger.info("Subscriber added: %d (total: %d)", chat_id, len(self._subscribers))
        await update.message.reply_text(HELP_TEXT, parse_mode="HTML")

    async def _cmd_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._check_access(update):
            return
        await update.message.reply_text("Generating full report...")
        try:
            self._report.refresh_data(include_hourly=True)
            report = self._report.generate_morning_brief()
            await self._send_report_charts(update.message, report)
        except Exception:
            logger.exception("Error generating report")
            await update.message.reply_text("Error generating report. Check logs.")

    async def _cmd_technicals(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._check_access(update):
            return
        await update.message.reply_text("Loading technicals...")
        try:
            self._report.refresh_data(include_hourly=False)
            matrix = self._report.generate_technical_matrix()
            dd = self._report.latest_daily_date()
            try:
                buf = chart_technical_matrix(matrix, data_date=dd, frequency="Daily")
                await update.message.reply_photo(photo=buf, caption="Technical Matrix")
            except Exception:
                logger.warning("Chart failed, falling back to text", exc_info=True)
                for msg in format_technical_matrix(matrix):
                    await update.message.reply_text(msg, parse_mode="HTML")
        except Exception:
            logger.exception("Error generating technicals")
            await update.message.reply_text("Error generating technicals.")

    async def _cmd_signals(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._check_access(update):
            return
        await update.message.reply_text("Loading event analysis...")
        try:
            self._report.refresh_data(include_hourly=False)
            ev = self._report.generate_event_table()
            dd = self._report.latest_daily_date()
            try:
                buf = chart_event_table(ev, data_date=dd, frequency="Daily (5d return window)")
                await update.message.reply_photo(photo=buf, caption="Event Analysis")
            except Exception:
                logger.warning("Chart failed, falling back to text", exc_info=True)
                for msg in format_event_table(ev):
                    await update.message.reply_text(msg, parse_mode="HTML")
        except Exception:
            logger.exception("Error generating signals")
            await update.message.reply_text("Error generating event analysis.")

    async def _cmd_cars(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._check_access(update):
            return
        await update.message.reply_text("Loading CARS analysis...")
        try:
            self._report.refresh_data(include_hourly=False)
            cars = self._report.generate_cars()
            dd = self._report.latest_daily_date()
            try:
                buf = chart_cars(cars, data_date=dd, frequency="Weekly (52w rolling)")
                if buf:
                    await update.message.reply_photo(photo=buf, caption="CARS Regime")
                else:
                    await update.message.reply_text(format_cars(cars), parse_mode="HTML")
            except Exception:
                logger.warning("Chart failed, falling back to text", exc_info=True)
                await update.message.reply_text(format_cars(cars), parse_mode="HTML")
        except Exception:
            logger.exception("Error generating CARS")
            await update.message.reply_text("Error generating CARS.")

    async def _cmd_timezone(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._check_access(update):
            return
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
            heatmap = self._report.generate_timezone_heatmap(lookback_days)
            dd = self._report.latest_hourly_date()
            freq = f"Hourly ({lookback_days}d lookback)"
            try:
                buf1 = chart_timezone_summary(summary, data_date=dd, frequency=freq)
                await update.message.reply_photo(photo=buf1, caption="Time Zone Returns")
                buf2 = chart_timezone_heatmap(heatmap, data_date=dd, frequency=freq)
                await update.message.reply_photo(photo=buf2, caption="Time Zone Heatmap")
            except Exception:
                logger.warning("Chart failed, falling back to text", exc_info=True)
                await update.message.reply_text(
                    format_timezone_summary(summary), parse_mode="HTML")
                for m in format_timezone_heatmap(heatmap):
                    await update.message.reply_text(m, parse_mode="HTML")
        except Exception:
            logger.exception("Error generating timezone analysis")
            await update.message.reply_text("Error generating timezone analysis.")

    async def _cmd_pca_etf(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._check_access(update):
            return
        await update.message.reply_text("Loading PCA ETF analysis...")
        try:
            self._report.refresh_data(include_hourly=False)
            report = self._report.generate_pca_etf()
            dd = self._report.latest_daily_date()
            try:
                bufs = chart_pca_etf(report, data_date=dd)
                captions = ["PCA ETF — Variance", "PCA ETF — Loadings"]
                for i, buf in enumerate(bufs):
                    cap = captions[i] if i < len(captions) else "PCA ETF"
                    await update.message.reply_photo(photo=buf, caption=cap)
            except Exception:
                logger.warning("Chart failed, falling back to text", exc_info=True)
                for msg in format_pca_etf(report):
                    await update.message.reply_text(msg, parse_mode="HTML")
        except Exception:
            logger.exception("Error generating PCA ETF")
            await update.message.reply_text("Error generating PCA ETF analysis.")

    async def _cmd_pca_fx(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._check_access(update):
            return
        await update.message.reply_text("Loading PCA FX analysis...")
        try:
            self._report.refresh_data(include_hourly=False)
            report = self._report.generate_pca_fx()
            dd = self._report.latest_daily_date()
            try:
                bufs = chart_pca_fx(report, data_date=dd)
                captions = ["PCA FX — Loadings", "PCA FX — Scores"]
                for i, buf in enumerate(bufs):
                    cap = captions[i] if i < len(captions) else "PCA FX"
                    await update.message.reply_photo(photo=buf, caption=cap)
            except Exception:
                logger.warning("Chart failed, falling back to text", exc_info=True)
                for msg in format_pca_fx(report):
                    await update.message.reply_text(msg, parse_mode="HTML")
        except Exception:
            logger.exception("Error generating PCA FX")
            await update.message.reply_text("Error generating PCA FX analysis.")

    async def _cmd_methodology(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._check_access(update):
            return
        keyboard = []
        row: list[InlineKeyboardButton] = []
        for label, cb_data in METHODOLOGY_BUTTONS:
            row.append(InlineKeyboardButton(label, callback_data=cb_data))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        await update.message.reply_text(
            "<b>Select an analysis method:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _handle_methodology_cb(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        key = query.data.replace("method_", "", 1)
        entry = METHODOLOGIES.get(key)
        if not entry:
            await query.edit_message_text("Unknown methodology.")
            return
        text = (
            f"<b>{entry['title']}</b>\n\n"
            f"{entry['description']}\n\n"
            f"<b>── Metrics ──</b>\n{entry['metrics']}\n\n"
            f"<b>── Signals ──</b>\n{entry['signals']}"
        )
        await query.edit_message_text(text, parse_mode="HTML")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._check_access(update):
            return
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

        lines.append(f"\nSubscribers: {len(self._subscribers)}")
        lines.append(f"Server time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._check_access(update):
            return
        await update.message.reply_text(HELP_TEXT, parse_mode="HTML")

    # ------------------------------------------------------------------
    # Chart-based report helper
    # ------------------------------------------------------------------

    async def _send_report_charts(self, target, report: dict) -> None:
        """Send a full report as chart images with text fallback.

        ``target`` is either a ``Message`` (for on-demand) or used via
        ``send_scheduled_report`` for broadcasts.
        """
        ts = report.get("timestamp", "")
        rtype = report.get("report_type", "Report")
        await target.reply_text(f"<b>{rtype}</b>\n{ts}", parse_mode="HTML")

        dd = self._report.latest_daily_date()
        hd = self._report.latest_hourly_date()

        # Technical Matrix
        tech = report.get("technical_matrix")
        if tech is not None and not tech.empty:
            try:
                buf = chart_technical_matrix(tech, data_date=dd, frequency="Daily")
                await target.reply_photo(photo=buf, caption="Technical Matrix")
            except Exception:
                logger.warning("Tech chart failed", exc_info=True)
                for msg in format_technical_matrix(tech):
                    await target.reply_text(msg, parse_mode="HTML")

        # Event Table
        ev = report.get("event_table")
        if ev is not None and not ev.empty:
            try:
                buf = chart_event_table(ev, data_date=dd, frequency="Daily (5d return window)")
                await target.reply_photo(photo=buf, caption="Event Analysis")
            except Exception:
                logger.warning("Event chart failed", exc_info=True)
                for msg in format_event_table(ev):
                    await target.reply_text(msg, parse_mode="HTML")

        # CARS
        cars = report.get("cars")
        if cars is not None and not cars.empty:
            try:
                buf = chart_cars(cars, data_date=dd, frequency="Weekly (52w rolling)")
                if buf:
                    await target.reply_photo(photo=buf, caption="CARS Regime")
                else:
                    await target.reply_text(format_cars(cars), parse_mode="HTML")
            except Exception:
                logger.warning("CARS chart failed", exc_info=True)
                await target.reply_text(format_cars(cars), parse_mode="HTML")

        # Timezone
        tz_sum = report.get("timezone_summary")
        if tz_sum is not None and not tz_sum.empty:
            try:
                buf = chart_timezone_summary(tz_sum, data_date=hd, frequency="Hourly (5d lookback)")
                await target.reply_photo(photo=buf, caption="Time Zone Returns")
            except Exception:
                logger.warning("TZ summary chart failed", exc_info=True)
                await target.reply_text(
                    format_timezone_summary(tz_sum), parse_mode="HTML")

        tz_hm = report.get("timezone_heatmap")
        if tz_hm is not None and not tz_hm.empty:
            try:
                buf = chart_timezone_heatmap(tz_hm, data_date=hd, frequency="Hourly (5d lookback)")
                await target.reply_photo(photo=buf, caption="Time Zone Heatmap")
            except Exception:
                logger.warning("TZ heatmap chart failed", exc_info=True)
                for m in format_timezone_heatmap(tz_hm):
                    await target.reply_text(m, parse_mode="HTML")

        # PCA ETF
        pca_e = report.get("pca_etf")
        if pca_e:
            try:
                bufs = chart_pca_etf(pca_e, data_date=dd)
                caps = ["PCA ETF — Variance", "PCA ETF — Loadings"]
                for i, buf in enumerate(bufs):
                    await target.reply_photo(
                        photo=buf, caption=caps[i] if i < len(caps) else "PCA ETF")
            except Exception:
                logger.warning("PCA ETF chart failed", exc_info=True)
                for msg in format_pca_etf(pca_e):
                    await target.reply_text(msg, parse_mode="HTML")

        # PCA FX
        pca_f = report.get("pca_fx")
        if pca_f:
            try:
                bufs = chart_pca_fx(pca_f, data_date=dd)
                caps = ["PCA FX — Loadings", "PCA FX — Scores"]
                for i, buf in enumerate(bufs):
                    await target.reply_photo(
                        photo=buf, caption=caps[i] if i < len(caps) else "PCA FX")
            except Exception:
                logger.warning("PCA FX chart failed", exc_info=True)
                for msg in format_pca_fx(pca_f):
                    await target.reply_text(msg, parse_mode="HTML")

    # ------------------------------------------------------------------
    # Scheduled message sending (broadcasts to all subscribers)
    # ------------------------------------------------------------------

    async def send_scheduled_report(self, report: dict) -> None:
        """Send chart-based report to all subscribers."""
        if not self._subscribers:
            logger.warning("No subscribers — send /start to the bot first")
            return
        for chat_id in self._subscribers.copy():
            try:
                # Create a lightweight message proxy for send_message
                msg_proxy = _ChatProxy(self._app.bot, chat_id)
                await self._send_report_charts(msg_proxy, report)
            except Exception:
                logger.exception("Failed to send report to chat %d", chat_id)

    async def send_scheduled_messages(self, messages: list[str]) -> None:
        """Send pre-formatted text messages to all subscribed chats (legacy)."""
        if not self._subscribers:
            logger.warning("No subscribers — send /start to the bot first")
            return
        for chat_id in self._subscribers.copy():
            for msg in messages:
                try:
                    await self._app.bot.send_message(
                        chat_id=chat_id, text=msg, parse_mode="HTML",
                    )
                except Exception:
                    logger.exception("Failed to send to chat %d", chat_id)

    @property
    def app(self) -> Application:
        return self._app
