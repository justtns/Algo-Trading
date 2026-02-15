"""Telegram command handlers for the live trading bot.

Commands:
  /trades [n]  - Show last N fills (default 10)
  /positions   - Current open positions
  /equity      - Latest equity / cash
  /status      - DB connection info
  /help        - Command list
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from ..db.reader import TradeReader
from .formatter import (
    format_fills,
    format_positions,
    format_equity,
    format_status,
)

logger = logging.getLogger(__name__)

HELP_TEXT = """<b>Live Trading Bot</b>

<b>Commands:</b>
/trades [n] - Show last N fills (default 10)
/today - Today's fills
/positions - Current open positions
/equity - Latest equity / cash
/status - DB connection info
/help - This message

<i>Fill alerts are pushed automatically when new trades execute.</i>
"""


class LiveTradingBot:
    """Telegram bot for live trade monitoring."""

    def __init__(
        self,
        token: str,
        chat_id: str,
        reader: TradeReader,
        db_path: str,
    ):
        self._token = token
        self._chat_id = chat_id
        self._reader = reader
        self._db_path = db_path
        self._app = Application.builder().token(token).build()
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        self._app.add_handler(CommandHandler("trades", self._cmd_trades))
        self._app.add_handler(CommandHandler("today", self._cmd_today))
        self._app.add_handler(CommandHandler("positions", self._cmd_positions))
        self._app.add_handler(CommandHandler("equity", self._cmd_equity))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(CommandHandler("start", self._cmd_help))

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    async def _cmd_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        limit = 10
        if context.args:
            try:
                limit = int(context.args[0])
                limit = max(1, min(limit, 50))
            except ValueError:
                pass

        try:
            fills = self._reader.get_recent_fills(limit=limit)
            messages = format_fills(fills)
            for msg in messages:
                await update.message.reply_text(msg, parse_mode="HTML")
        except Exception:
            logger.exception("Error fetching trades")
            await update.message.reply_text("Error fetching trades. Check logs.")

    async def _cmd_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            fills = self._reader.get_today_fills()
            if fills:
                messages = format_fills(fills)
            else:
                messages = ["No fills today."]
            for msg in messages:
                await update.message.reply_text(msg, parse_mode="HTML")
        except Exception:
            logger.exception("Error fetching today's trades")
            await update.message.reply_text("Error fetching today's trades.")

    async def _cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            session_id = self._reader.get_active_session_id()
            positions = self._reader.get_latest_positions(session_id)
            messages = format_positions(positions)
            for msg in messages:
                await update.message.reply_text(msg, parse_mode="HTML")
        except Exception:
            logger.exception("Error fetching positions")
            await update.message.reply_text("Error fetching positions.")

    async def _cmd_equity(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            session_id = self._reader.get_active_session_id()
            equity = self._reader.get_latest_equity(session_id)
            msg = format_equity(equity)
            await update.message.reply_text(msg, parse_mode="HTML")
        except Exception:
            logger.exception("Error fetching equity")
            await update.message.reply_text("Error fetching equity.")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            last_fill_ts = self._reader.get_last_fill_ts()
            fill_count = self._reader.get_fill_count()
            active_session = self._reader.get_active_session_id()
            msg = format_status(
                db_path=self._db_path,
                connected=self._reader.connected,
                last_fill_ts=last_fill_ts,
                fill_count=fill_count,
                active_session=active_session,
            )
            await update.message.reply_text(msg, parse_mode="HTML")
        except Exception:
            logger.exception("Error fetching status")
            await update.message.reply_text("Error fetching status.")

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(HELP_TEXT, parse_mode="HTML")

    # ------------------------------------------------------------------
    # Outbound messaging (for notifier)
    # ------------------------------------------------------------------

    async def send_message(self, text: str) -> None:
        """Send a message to the configured chat."""
        try:
            await self._app.bot.send_message(
                chat_id=self._chat_id, text=text, parse_mode="HTML",
            )
        except Exception:
            logger.exception("Failed to send message")

    @property
    def app(self) -> Application:
        return self._app
