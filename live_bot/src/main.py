"""
Live Trading Bot entry point.

Runs the Telegram bot with:
- APScheduler interval job polling for new fills
- Telegram polling for on-demand commands (/trades, /positions, /equity)
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .db.reader import TradeReader
from .bot.handlers import LiveTradingBot
from .notifier import FillNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _load_settings(config_dir: Path) -> dict:
    settings_path = config_dir / "settings.yaml"
    if settings_path.exists():
        with open(settings_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _resolve_env(config_dir: Path) -> None:
    env_path = config_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    config_dir = project_root / "config"

    _resolve_env(config_dir)
    settings = _load_settings(config_dir)

    # Required env vars
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN_LIVE")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID_LIVE")
    db_path = os.getenv("NAUTILUS_DB_PATH")

    if not telegram_token:
        logger.error("TELEGRAM_BOT_TOKEN_LIVE not set")
        sys.exit(1)
    if not telegram_chat_id:
        logger.error("TELEGRAM_CHAT_ID_LIVE not set")
        sys.exit(1)
    if not db_path:
        logger.error("NAUTILUS_DB_PATH not set")
        sys.exit(1)

    db_file = Path(db_path)
    if not db_file.exists():
        logger.error("Database not found: %s", db_path)
        sys.exit(1)

    # Init components
    reader = TradeReader(db_path)
    reader.connect()
    logger.info("Connected to trading DB: %s", db_path)

    bot = LiveTradingBot(
        token=telegram_token,
        chat_id=telegram_chat_id,
        reader=reader,
        db_path=db_path,
    )

    # Setup fill notifier
    notifier_settings = settings.get("notifier", {})
    if notifier_settings.get("enabled", True):
        notifier = FillNotifier(
            reader=reader,
            send_fn=bot.send_message,
            poll_interval=notifier_settings.get("poll_interval", 5),
        )
        notifier.init_cursor()

        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.interval import IntervalTrigger

            scheduler = AsyncIOScheduler()
            scheduler.add_job(
                notifier.check_new_fills,
                IntervalTrigger(seconds=notifier.poll_interval),
                id="fill_notifier",
            )
            scheduler.start()
            logger.info(
                "Fill notifier started (polling every %ds)", notifier.poll_interval
            )
        except ImportError:
            logger.warning("apscheduler not available; fill notifications disabled")
    else:
        logger.info("Fill notifier disabled in settings")

    # Run Telegram bot polling (blocks)
    logger.info("Starting Live Trading Bot polling...")
    bot.app.run_polling()


if __name__ == "__main__":
    main()
