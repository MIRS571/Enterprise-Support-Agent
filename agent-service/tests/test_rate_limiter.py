import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from redis.exceptions import ConnectionError

from agent_service.core.redis import (
    RedisAvailability,
    RedisAvailabilityStatus,
)
from agent_service.core.redis_keys import RedisKeyBuilder
from agent_service.services.rate_limiter import (
    ChatRateLimiter,
    RateLimitExceededError,
    RateLimitUnavailableError,
)


def make_limiter(
    redis_client: Mock,
) -> tuple[ChatRateLimiter, RedisAvailability]:
    availability = RedisAvailability(status=RedisAvailabilityStatus.UP)
    limiter = ChatRateLimiter(
        redis_client=redis_client,
        key_builder=RedisKeyBuilder(
            prefix="esa",
            environment="test",
        ),
        limit=3,
        window_seconds=60,
        availability=availability,
    )
    return limiter, availability


def test_rate_limit_returns_remaining_quota() -> None:
    async def scenario() -> None:
        redis_client = Mock()
        redis_client.eval = AsyncMock(return_value=[1, 60])
        limiter, _availability = make_limiter(redis_client)

        decision = await limiter.check(
            tenant_id="company_001",
            user_id="U1001",
        )

        assert decision.limit == 3
        assert decision.remaining == 2
        assert decision.reset_after_seconds == 60
        args = redis_client.eval.await_args.args
        assert "INCR" in args[0]
        assert "EXPIRE" in args[0]
        assert args[1:] == (
            1,
            "esa:test:rate:chat:company_001:U1001",
            60,
        )

    asyncio.run(scenario())


def test_rate_limit_rejects_request_over_limit() -> None:
    async def scenario() -> None:
        redis_client = Mock()
        redis_client.eval = AsyncMock(return_value=[4, 42])
        limiter, _availability = make_limiter(redis_client)

        with pytest.raises(
            RateLimitExceededError,
        ) as caught:
            await limiter.check(
                tenant_id="company_001",
                user_id="U1001",
            )

        assert caught.value.retry_after_seconds == 42

    asyncio.run(scenario())


def test_rate_limit_fails_closed_when_redis_is_down() -> None:
    async def scenario() -> None:
        redis_client = Mock()
        redis_client.eval = AsyncMock(side_effect=ConnectionError("connection lost"))
        limiter, availability = make_limiter(redis_client)

        with pytest.raises(RateLimitUnavailableError):
            await limiter.check(
                tenant_id="company_001",
                user_id="U1001",
            )

        assert availability.status is RedisAvailabilityStatus.DOWN

    asyncio.run(scenario())
