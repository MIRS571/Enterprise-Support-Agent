import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from redis.exceptions import AuthenticationError, ConnectionError

from agent_service.core.config import Settings
from agent_service.core.redis import (
    RedisAvailabilityStatus,
    RedisConfigurationError,
    RedisUnavailableError,
    open_redis,
)


def test_open_redis_returns_disabled_resources() -> None:
    async def scenario() -> None:
        settings = Settings(
            _env_file=None,
            redis_enabled=False,
        )

        async with open_redis(settings) as resources:
            assert resources.client is None
            assert resources.availability.status is RedisAvailabilityStatus.DISABLED

    asyncio.run(scenario())


def test_open_redis_pings_and_closes_client(
    monkeypatch,
) -> None:
    client = Mock()
    client.ping = AsyncMock(return_value=True)
    client.aclose = AsyncMock()
    from_url = Mock(return_value=client)
    monkeypatch.setattr(
        "agent_service.core.redis.Redis.from_url",
        from_url,
    )

    async def scenario() -> None:
        settings = Settings(
            _env_file=None,
            redis_enabled=True,
            redis_url="redis://:secret@127.0.0.1:6379/0",
        )

        async with open_redis(settings) as resources:
            assert resources.client is client
            assert resources.availability.status is RedisAvailabilityStatus.UP

    asyncio.run(scenario())

    client.ping.assert_awaited_once_with()
    client.aclose.assert_awaited_once_with()


def test_open_redis_fails_when_ping_fails(
    monkeypatch,
) -> None:
    client = Mock()
    client.ping = AsyncMock(side_effect=ConnectionError("connection refused"))
    client.aclose = AsyncMock()
    monkeypatch.setattr(
        "agent_service.core.redis.Redis.from_url",
        Mock(return_value=client),
    )

    async def scenario() -> None:
        settings = Settings(
            _env_file=None,
            redis_enabled=True,
            redis_url="redis://:secret@127.0.0.1:6379/0",
        )

        with pytest.raises(
            RedisUnavailableError,
            match="Redis is unavailable",
        ):
            async with open_redis(settings):
                pass

    asyncio.run(scenario())

    client.aclose.assert_awaited_once_with()


def test_open_redis_reports_authentication_as_configuration_error(
    monkeypatch,
) -> None:
    client = Mock()
    client.ping = AsyncMock(
        side_effect=AuthenticationError("invalid password")
    )
    client.aclose = AsyncMock()
    monkeypatch.setattr(
        "agent_service.core.redis.Redis.from_url",
        Mock(return_value=client),
    )

    async def scenario() -> None:
        settings = Settings(
            _env_file=None,
            redis_enabled=True,
            redis_url="redis://:wrong@127.0.0.1:6379/0",
        )

        with pytest.raises(
            RedisConfigurationError,
            match="Redis authentication failed",
        ):
            async with open_redis(settings):
                pass

    asyncio.run(scenario())

    client.aclose.assert_awaited_once_with()
