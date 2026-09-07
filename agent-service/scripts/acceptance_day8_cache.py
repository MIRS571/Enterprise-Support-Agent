import asyncio

import httpx

from agent_service.core.config import Settings
from agent_service.core.redis import (
    RedisAvailability,
    RedisAvailabilityStatus,
    open_redis,
)
from agent_service.core.redis_keys import RedisKeyBuilder
from agent_service.domain.order import OrderResponse
from agent_service.integrations.business_service import (
    BusinessServiceClient,
    CachedOrderService,
)

TENANT_ID = "company_001"
USER_ID = "U1001"
ORDER_ID = "A1001"
TEST_TTL_SECONDS = 2


class CountingOrderService:
    def __init__(self, delegate: BusinessServiceClient) -> None:
        self._delegate = delegate
        self.get_order_calls = 0

    async def get_order(
        self,
        *,
        tenant_id: str,
        user_id: str,
        order_id: str,
    ) -> OrderResponse:
        self.get_order_calls += 1
        return await self._delegate.get_order(
            tenant_id=tenant_id,
            user_id=user_id,
            order_id=order_id,
        )


async def main() -> None:
    settings = Settings()
    key_builder = RedisKeyBuilder(
        prefix=settings.redis_key_prefix,
        environment=settings.environment,
    )
    cache_key = key_builder.order_cache(
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        order_id=ORDER_ID,
    )

    async with (
        open_redis(settings) as redis_resources,
        httpx.AsyncClient(
            base_url=str(settings.business_service_base_url),
            timeout=settings.business_service_timeout_seconds,
            trust_env=False,
        ) as http_client,
    ):
        redis_client = redis_resources.client
        if redis_client is None:
            raise RuntimeError("Redis is disabled")

        delegate = CountingOrderService(
            BusinessServiceClient(
                http_client=http_client,
                max_retries=settings.business_service_max_retries,
            )
        )
        cache = CachedOrderService(
            delegate=delegate,
            redis_client=redis_client,
            key_builder=key_builder,
            ttl_seconds=TEST_TTL_SECONDS,
            availability=RedisAvailability(
                RedisAvailabilityStatus.UP,
            ),
        )

        await redis_client.delete(cache_key)
        try:
            first = await cache.get_order(
                tenant_id=TENANT_ID,
                user_id=USER_ID,
                order_id=ORDER_ID,
            )
            ttl_after_miss = await redis_client.ttl(cache_key)

            second = await cache.get_order(
                tenant_id=TENANT_ID,
                user_id=USER_ID,
                order_id=ORDER_ID,
            )
            calls_after_hit = delegate.get_order_calls

            await asyncio.sleep(TEST_TTL_SECONDS + 0.2)
            third = await cache.get_order(
                tenant_id=TENANT_ID,
                user_id=USER_ID,
                order_id=ORDER_ID,
            )

            assert first == second == third
            assert ttl_after_miss > 0
            assert calls_after_hit == 1
            assert delegate.get_order_calls == 2

            print("PASS: first lookup missed and populated Redis")
            print("PASS: second lookup hit Redis; Java calls remained 1")
            print("PASS: cache expired; Java calls increased to 2")
        finally:
            await redis_client.delete(cache_key)


if __name__ == "__main__":
    asyncio.run(main())
