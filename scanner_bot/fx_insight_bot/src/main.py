"""
FX Insight Bot entry point.

Runs the Telegram bot with:
- APScheduler cron jobs for morning brief, EOD recap, and data pre-fetch
- Telegram polling for on-demand commands
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .data.polygon_client import PolygonFXClient
from .data.cache import DataCache, DataRefresher
from .report.generator import ReportGenerator
from .bot.handlers import FXInsightBot
from .bot.formatter import format_full_report

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
        load_dotenv()  # try default locations


async def _scheduled_morning(bot: FXInsightBot, report_gen: ReportGenerator) -> None:
    logger.info("Running scheduled morning brief")
    try:
        report_gen.refresh_data(include_hourly=True)
        report = report_gen.generate_morning_brief()
        messages = format_full_report(report)
        await bot.send_scheduled_messages(messages)
        logger.info("Morning brief sent (%d messages)", len(messages))
    except Exception:
        logger.exception("Failed to send morning brief")


async def _scheduled_eod(bot: FXInsightBot, report_gen: ReportGenerator) -> None:
    logger.info("Running scheduled EOD recap")
    try:
        report_gen.refresh_data(include_hourly=False)
        report = report_gen.generate_eod_recap()
        messages = format_full_report(report)
        await bot.send_scheduled_messages(messages)
        logger.info("EOD recap sent (%d messages)", len(messages))
    except Exception:
        logger.exception("Failed to send EOD recap")


async def _scheduled_prefetch(report_gen: ReportGenerator) -> None:
    logger.info("Running scheduled data pre-fetch")
    try:
        report_gen.refresh_data(include_hourly=True)
        logger.info("Data pre-fetch complete")
    except Exception:
        logger.exception("Data pre-fetch failed")


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    config_dir = project_root / "config"

    _resolve_env(config_dir)
    settings = _load_settings(config_dir)

    # Validate required env vars
    polygon_key = os.getenv("POLYGON_API_KEY")
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not polygon_key:
        logger.error("POLYGON_API_KEY not set")
        sys.exit(1)
    if not telegram_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)
    if not telegram_chat_id:
        logger.error("TELEGRAM_CHAT_ID not set")
        sys.exit(1)

    # Init components
    polygon_settings = settings.get("polygon", {})
    client = PolygonFXClient(
        api_key=polygon_key,
        rate_limit=polygon_settings.get("rate_limit", 5),
        max_retries=polygon_settings.get("max_retries", 5),
        base_delay=polygon_settings.get("base_delay", 2.0),
    )

    cache = DataCache(project_root / "data")
    refresher = DataRefresher(
        client, cache,
        history_days=polygon_settings.get("history_days", 504),
    )
    report_gen = ReportGenerator(cache, refresher)

    bot = FXInsightBot(
        token=telegram_token,
        chat_id=telegram_chat_id,
        report_gen=report_gen,
    )

    # Setup scheduler
    schedule_settings = settings.get("schedule", {})
    tz_name = schedule_settings.get("timezone", "America/New_York")

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        scheduler = AsyncIOScheduler(timezone=tz_name)

        # Parse schedule times
        morning_time = schedule_settings.get("morning_brief", "06:30")
        eod_time = schedule_settings.get("eod_recap", "17:00")
        prefetch_time = schedule_settings.get("data_prefetch", "05:00")

        morning_h, morning_m = morning_time.split(":")
        eod_h, eod_m = eod_time.split(":")
        prefetch_h, prefetch_m = prefetch_time.split(":")

        # Data pre-fetch (daily at 5:00 AM ET)
        scheduler.add_job(
            _scheduled_prefetch,
            CronTrigger(hour=int(prefetch_h), minute=int(prefetch_m), day_of_week="mon-fri"),
            args=[report_gen],
            id="prefetch",
        )

        # Morning brief (daily at 6:30 AM ET, weekdays)
        scheduler.add_job(
            _scheduled_morning,
            CronTrigger(hour=int(morning_h), minute=int(morning_m), day_of_week="mon-fri"),
            args=[bot, report_gen],
            id="morning_brief",
        )

        # EOD recap (daily at 5:00 PM ET, weekdays)
        scheduler.add_job(
            _scheduled_eod,
            CronTrigger(hour=int(eod_h), minute=int(eod_m), day_of_week="mon-fri"),
            args=[bot, report_gen],
            id="eod_recap",
        )

        scheduler.start()
        logger.info(
            "Scheduler started: prefetch=%s, morning=%s, eod=%s (%s)",
            prefetch_time, morning_time, eod_time, tz_name,
        )
    except ImportError:
        logger.warning("apscheduler not available; scheduled sends disabled")

    # Run Telegram bot polling (blocks)
    logger.info("Starting Telegram bot polling...")
    bot.app.run_polling()


if __name__ == "__main__":
    main()
