from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

from agent_service.core.redis import RedisAvailability
from agent_service.core.redis_keys import RedisKeyBuilder

_FIXED_WINDOW_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])
if current == 1 or ttl < 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end
return {current, ttl}
"""


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    limit: int
    remaining: int
    reset_after_seconds: int


class RateLimitExceededError(RuntimeError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("chat rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


class RateLimitUnavailableError(RuntimeError):
    pass


class ChatRateLimiter:
    def __init__(
        self,
        *,
        redis_client: Redis,
        key_builder: RedisKeyBuilder,
        limit: int,
        window_seconds: int,
        availability: RedisAvailability,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if window_seconds < 1:
            raise ValueError("window_seconds must be at least 1")
        self._redis = redis_client
        self._key_builder = key_builder
        self._limit = limit
        self._window_seconds = window_seconds
        self._availability = availability

    async def check(
        self,
        *,
        tenant_id: str,
        user_id: str,
    ) -> RateLimitDecision:
        key = self._key_builder.chat_rate_limit(
            tenant_id=tenant_id,
            user_id=user_id,
        )
        try:
            raw_result = await self._redis.eval(
                _FIXED_WINDOW_SCRIPT,
                1,
                key,
                self._window_seconds,
            )
        except RedisError as error:
            self._availability.mark_down()
            raise RateLimitUnavailableError(
                "chat rate limiter is unavailable"
            ) from error

        self._availability.mark_up()
        current, ttl = self._parse_result(raw_result)
        if current > self._limit:
            raise RateLimitExceededError(retry_after_seconds=max(ttl, 1))
        return RateLimitDecision(
            limit=self._limit,
            remaining=max(self._limit - current, 0),
            reset_after_seconds=max(ttl, 1),
        )

    @staticmethod
    def _parse_result(raw_result: object) -> tuple[int, int]:
        if not isinstance(raw_result, (list, tuple)):
            raise TypeError("Redis rate limit result must be a sequence")
        if len(raw_result) != 2:
            raise TypeError("Redis rate limit result must contain two values")
        current, ttl = raw_result
        if not isinstance(current, int) or not isinstance(ttl, int):
            raise TypeError("Redis rate limit values must be integers")
        return current, ttl
