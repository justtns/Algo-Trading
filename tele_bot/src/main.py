"""
FX Insight Bot entry point.

Runs the Telegram bot with:
- APScheduler cron jobs for morning brief (6 AM SGT) and data pre-fetch
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


def _parse_chat_id(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    # Allow inline comments in .env values (e.g. "12345 # optional")
    cleaned = raw_value.split("#", 1)[0].strip()
    if not cleaned:
        return None
    if not cleaned.isdigit():
        logger.warning("TELEGRAM_CHAT_ID is not numeric; ignoring value")
        return None
    return cleaned


async def _scheduled_morning(bot: FXInsightBot, report_gen: ReportGenerator) -> None:
    logger.info("Running scheduled morning brief")
    try:
        report_gen.refresh_data(include_hourly=True, force=True)
        report = report_gen.generate_morning_brief()
        await bot.send_scheduled_report(report)
        logger.info("Morning brief sent (charts)")
    except Exception:
        logger.exception("Failed to send morning brief")


async def _scheduled_prefetch(report_gen: ReportGenerator) -> None:
    logger.info("Running scheduled data pre-fetch")
    try:
        report_gen.refresh_data(include_hourly=True, force=True)
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
    telegram_chat_id = _parse_chat_id(os.getenv("TELEGRAM_CHAT_ID"))

    if not polygon_key:
        logger.error("POLYGON_API_KEY not set")
        sys.exit(1)
    if not telegram_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)
    if not telegram_chat_id:
        logger.info("TELEGRAM_CHAT_ID not set — will capture from first /start message")

    # Init components
    polygon_settings = settings.get("polygon", {})
    client = PolygonFXClient(
        api_key=polygon_key,
        rate_limit=polygon_settings.get("rate_limit", 5),
        max_retries=polygon_settings.get("max_retries", 5),
        base_delay=polygon_settings.get("base_delay", 2.0),
    )

    cache_settings = settings.get("cache", {})
    cache = DataCache(project_root / "data")
    refresher = DataRefresher(
        client, cache,
        history_days=polygon_settings.get("history_days", 504),
        cooldown_minutes=cache_settings.get("cooldown_minutes", 15),
    )
    report_gen = ReportGenerator(cache, refresher)

    # Parse whitelist from settings (list of Telegram user IDs)
    telegram_settings = settings.get("telegram", {})
    whitelist_raw = telegram_settings.get("whitelist", [])
    whitelist = set(int(uid) for uid in whitelist_raw) if whitelist_raw else None

    # Setup scheduler
    schedule_settings = settings.get("schedule", {})
    tz_name = schedule_settings.get("timezone", "America/New_York")
    scheduler = None
    post_init = None
    post_shutdown = None
    cron_trigger = None

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        scheduler = AsyncIOScheduler(timezone=tz_name)
        cron_trigger = CronTrigger

        # Parse schedule times
        morning_time = schedule_settings.get("morning_brief", "06:00")
        prefetch_time = schedule_settings.get("data_prefetch", "05:00")

        morning_h, morning_m = morning_time.split(":")
        prefetch_h, prefetch_m = prefetch_time.split(":")

        async def _post_init(app: object) -> None:
            scheduler.start()
            logger.info(
                "Scheduler started: prefetch=%s, morning=%s (%s)",
                prefetch_time, morning_time, tz_name,
            )

        async def _post_shutdown(app: object) -> None:
            scheduler.shutdown()

        post_init = _post_init
        post_shutdown = _post_shutdown
    except ImportError:
        logger.warning("apscheduler not available; scheduled sends disabled")

    bot = FXInsightBot(
        token=telegram_token,
        chat_id=telegram_chat_id,
        report_gen=report_gen,
        whitelist=whitelist,
        post_init=post_init,
        post_shutdown=post_shutdown,
    )

    if scheduler:
        # Data pre-fetch (daily at 5:00 AM SGT, weekdays)
        scheduler.add_job(
            _scheduled_prefetch,
            cron_trigger(hour=int(prefetch_h), minute=int(prefetch_m), day_of_week="mon-fri"),
            args=[report_gen],
            id="prefetch",
        )

        # Morning brief (daily at 6:00 AM SGT, weekdays)
        scheduler.add_job(
            _scheduled_morning,
            cron_trigger(hour=int(morning_h), minute=int(morning_m), day_of_week="mon-fri"),
            args=[bot, report_gen],
            id="morning_brief",
        )

    # Run Telegram bot polling (blocks)
    logger.info("Starting Telegram bot polling...")
    bot.app.run_polling()


if __name__ == "__main__":
    main()
