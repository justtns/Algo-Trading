"""Push notifications for new trade fills."""
from __future__ import annotations

import logging

from .db.reader import TradeReader
from .bot.formatter import format_fill_alert

logger = logging.getLogger(__name__)


class FillNotifier:
    """Polls the fills table and sends alerts for new entries.

    Designed to run as an APScheduler interval job.  Tracks the last-seen
    fill id so each fill is reported exactly once.
    """

    def __init__(
        self,
        reader: TradeReader,
        send_fn,
        poll_interval: int = 5,
    ):
        self._reader = reader
        self._send_fn = send_fn  # async callable(text) -> None
        self._poll_interval = poll_interval
        self._last_seen_id: int | None = None

    def init_cursor(self) -> None:
        """Set the cursor to the current max fill id (skip existing fills)."""
        self._last_seen_id = self._reader.get_max_fill_id()
        logger.info("Fill notifier cursor initialised at id=%d", self._last_seen_id)

    async def check_new_fills(self) -> None:
        """Poll for new fills and send alerts. Called by scheduler."""
        if self._last_seen_id is None:
            self.init_cursor()
            return

        try:
            new_fills = self._reader.get_fills_after(self._last_seen_id)
            for fill in new_fills:
                msg = format_fill_alert(fill)
                await self._send_fn(msg)
                logger.info("Sent fill alert: %s %s %s @ %s",
                            fill["side"], fill["qty"], fill["symbol"], fill["price"])
                self._last_seen_id = fill["id"]
        except Exception:
            logger.exception("Error checking for new fills")

    @property
    def poll_interval(self) -> int:
        return self._poll_interval
