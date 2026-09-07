from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum

from redis.asyncio import Redis
from redis.exceptions import AuthenticationError, RedisError

from agent_service.core.config import Settings


class RedisAvailabilityStatus(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    DISABLED = "DISABLED"


@dataclass
class RedisAvailability:
    status: RedisAvailabilityStatus

    def mark_up(self) -> None:
        self.status = RedisAvailabilityStatus.UP

    def mark_down(self) -> None:
        self.status = RedisAvailabilityStatus.DOWN


@dataclass(frozen=True, slots=True)
class RedisResources:
    client: Redis | None
    availability: RedisAvailability


class RedisUnavailableError(RuntimeError):
    pass


class RedisConfigurationError(RuntimeError):
    pass


@asynccontextmanager
async def open_redis(
    settings: Settings,
) -> AsyncIterator[RedisResources]:
    availability = RedisAvailability(
        status=(
            RedisAvailabilityStatus.DOWN
            if settings.redis_enabled
            else RedisAvailabilityStatus.DISABLED
        )
    )

    if not settings.redis_enabled:
        yield RedisResources(
            client=None,
            availability=availability,
        )
        return

    if settings.redis_url is None:
        raise ValueError("redis_url is required when redis_enabled is true")

    client = Redis.from_url(
        settings.redis_url.get_secret_value(),
        decode_responses=True,
        socket_connect_timeout=(settings.redis_socket_timeout_seconds),
        socket_timeout=settings.redis_socket_timeout_seconds,
        health_check_interval=30,
    )

    try:
        try:
            await client.ping()
        except AuthenticationError as error:
            availability.mark_down()
            raise RedisConfigurationError("Redis authentication failed") from error
        except RedisError as error:
            availability.mark_down()
            raise RedisUnavailableError("Redis is unavailable") from error

        availability.mark_up()
        yield RedisResources(
            client=client,
            availability=availability,
        )
    finally:
        await client.aclose()
