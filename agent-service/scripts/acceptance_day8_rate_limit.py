import asyncio

from agent_service.core.config import Settings
from agent_service.core.redis import open_redis
from agent_service.core.redis_keys import RedisKeyBuilder
from agent_service.services.rate_limiter import (
    ChatRateLimiter,
    RateLimitExceededError,
)

TENANT_ID = "company_001"
FIRST_USER_ID = "rate_test_001"
SECOND_USER_ID = "rate_test_002"
TEST_LIMIT = 2
TEST_WINDOW_SECONDS = 2


async def main() -> None:
    settings = Settings()
    key_builder = RedisKeyBuilder(
        prefix=settings.redis_key_prefix,
        environment=settings.environment,
    )
    keys = [
        key_builder.chat_rate_limit(
            tenant_id=TENANT_ID,
            user_id=user_id,
        )
        for user_id in (FIRST_USER_ID, SECOND_USER_ID)
    ]

    async with open_redis(settings) as redis_resources:
        redis_client = redis_resources.client
        if redis_client is None:
            raise RuntimeError("Redis is disabled")

        limiter = ChatRateLimiter(
            redis_client=redis_client,
            key_builder=key_builder,
            limit=TEST_LIMIT,
            window_seconds=TEST_WINDOW_SECONDS,
            availability=redis_resources.availability,
        )

        await redis_client.delete(*keys)
        try:
            first = await limiter.check(
                tenant_id=TENANT_ID,
                user_id=FIRST_USER_ID,
            )
            second = await limiter.check(
                tenant_id=TENANT_ID,
                user_id=FIRST_USER_ID,
            )

            try:
                await limiter.check(
                    tenant_id=TENANT_ID,
                    user_id=FIRST_USER_ID,
                )
            except RateLimitExceededError as error:
                assert error.retry_after_seconds > 0
            else:
                raise AssertionError("third request should be rate limited")

            other_user = await limiter.check(
                tenant_id=TENANT_ID,
                user_id=SECOND_USER_ID,
            )
            await asyncio.sleep(TEST_WINDOW_SECONDS + 0.2)
            reset = await limiter.check(
                tenant_id=TENANT_ID,
                user_id=FIRST_USER_ID,
            )

            assert first.remaining == 1
            assert second.remaining == 0
            assert other_user.remaining == 1
            assert reset.remaining == 1

            print("PASS: the third request for one identity was limited")
            print("PASS: another user kept an independent quota")
            print("PASS: the first user's quota reset after the window")
        finally:
            await redis_client.delete(*keys)


if __name__ == "__main__":
    asyncio.run(main())
