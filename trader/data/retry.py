"""Shared retry utilities with exponential backoff for data fetchers."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from functools import wraps
from typing import Callable, Type

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    retryable_exceptions: tuple[Type[Exception], ...] = field(
        default_factory=lambda: (Exception,)
    )


def retry_async(config: RetryConfig | None = None) -> Callable:
    """Decorator for async functions with exponential backoff."""
    cfg = config or RetryConfig()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(cfg.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except cfg.retryable_exceptions as exc:
                    last_exc = exc
                    if attempt == cfg.max_retries:
                        raise
                    delay = min(
                        cfg.base_delay * (cfg.backoff_factor ** attempt),
                        cfg.max_delay,
                    )
                    logger.warning(
                        "Retry %d/%d for %s: %s. Waiting %.1fs",
                        attempt + 1,
                        cfg.max_retries,
                        func.__name__,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


def retry_sync(config: RetryConfig | None = None) -> Callable:
    """Decorator for sync functions with exponential backoff."""
    cfg = config or RetryConfig()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(cfg.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except cfg.retryable_exceptions as exc:
                    last_exc = exc
                    if attempt == cfg.max_retries:
                        raise
                    delay = min(
                        cfg.base_delay * (cfg.backoff_factor ** attempt),
                        cfg.max_delay,
                    )
                    logger.warning(
                        "Retry %d/%d for %s: %s. Waiting %.1fs",
                        attempt + 1,
                        cfg.max_retries,
                        func.__name__,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator
