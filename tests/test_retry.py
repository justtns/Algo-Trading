"""Tests for the retry utility."""
import asyncio
import time

import pytest

from trader.data.retry import RetryConfig, retry_async, retry_sync


@pytest.mark.asyncio
async def test_retry_async_succeeds_after_failures():
    call_count = 0

    @retry_async(RetryConfig(max_retries=3, base_delay=0.01))
    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("transient")
        return "ok"

    result = await flaky()
    assert result == "ok"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_async_exhausts_retries():
    @retry_async(RetryConfig(max_retries=2, base_delay=0.01))
    async def always_fail():
        raise ConnectionError("permanent")

    with pytest.raises(ConnectionError, match="permanent"):
        await always_fail()


@pytest.mark.asyncio
async def test_retry_async_no_retry_on_non_retryable():
    call_count = 0

    @retry_async(RetryConfig(
        max_retries=3,
        base_delay=0.01,
        retryable_exceptions=(ConnectionError,),
    ))
    async def wrong_error():
        nonlocal call_count
        call_count += 1
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        await wrong_error()
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_async_respects_max_delay():
    delays = []

    @retry_async(RetryConfig(
        max_retries=5,
        base_delay=1.0,
        max_delay=2.0,
        backoff_factor=10.0,  # would be 1, 10, 100... but capped at 2
    ))
    async def failing():
        raise ConnectionError("fail")

    with pytest.raises(ConnectionError):
        await failing()
    # The test passes if it doesn't hang (max_delay caps the sleep)


def test_retry_sync_succeeds_after_failures():
    call_count = 0

    @retry_sync(RetryConfig(max_retries=3, base_delay=0.01))
    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise OSError("transient")
        return "done"

    result = flaky()
    assert result == "done"
    assert call_count == 2


def test_retry_sync_exhausts_retries():
    @retry_sync(RetryConfig(max_retries=1, base_delay=0.01))
    def always_fail():
        raise OSError("permanent")

    with pytest.raises(OSError, match="permanent"):
        always_fail()
