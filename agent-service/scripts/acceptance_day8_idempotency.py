import asyncio
import json

import httpx

from agent_service.core.config import Settings
from agent_service.core.redis import open_redis
from agent_service.core.redis_keys import RedisKeyBuilder
from agent_service.domain.order import OrderStatus
from agent_service.integrations.business_service import (
    BusinessServiceClient,
    CachedOrderService,
)
from agent_service.integrations.business_service.errors import (
    IdempotencyConflictError,
)

TENANT_ID = "company_001"
USER_ID = "U1001"
REFUND_ORDER_ID = "A1001"
CONFLICT_ORDER_ID = "A1002"
IDEMPOTENCY_KEY = "day8-acceptance-20260831-01"


async def main() -> None:
    settings = Settings()
    key_builder = RedisKeyBuilder(
        prefix=settings.redis_key_prefix,
        environment=settings.environment,
    )
    cache_key = key_builder.order_cache(
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        order_id=REFUND_ORDER_ID,
    )
    idempotency_key = key_builder.refund_idempotency(
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        idempotency_key=IDEMPOTENCY_KEY,
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
        if await redis_client.exists(idempotency_key):
            raise RuntimeError("acceptance idempotency key was already used")

        business_client = BusinessServiceClient(
            http_client=http_client,
            max_retries=settings.business_service_max_retries,
        )
        order_service = CachedOrderService(
            delegate=business_client,
            redis_client=redis_client,
            key_builder=key_builder,
            ttl_seconds=settings.order_cache_ttl_seconds,
            availability=redis_resources.availability,
        )

        await redis_client.delete(cache_key)
        before = await order_service.get_order(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            order_id=REFUND_ORDER_ID,
        )
        if before.status is not OrderStatus.SHIPPED or not before.refundable:
            raise RuntimeError("A1001 is not eligible for the acceptance refund")
        assert await redis_client.exists(cache_key) == 1

        first = await order_service.request_refund(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            order_id=REFUND_ORDER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
        )
        assert first.status is OrderStatus.REFUNDING
        assert await redis_client.exists(cache_key) == 0

        stored_payload = await redis_client.get(idempotency_key)
        if stored_payload is None:
            raise AssertionError("completed idempotency record was not stored")
        stored_record = json.loads(stored_payload)
        assert stored_record["status"] == "COMPLETED"
        assert await redis_client.ttl(idempotency_key) > 0

        replay = await order_service.request_refund(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            order_id=REFUND_ORDER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
        )
        assert replay == first

        try:
            await order_service.request_refund(
                tenant_id=TENANT_ID,
                user_id=USER_ID,
                order_id=CONFLICT_ORDER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
            )
        except IdempotencyConflictError:
            pass
        else:
            raise AssertionError("same key for another order should conflict")

        current = await business_client.get_order(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            order_id=REFUND_ORDER_ID,
        )
        assert current.status is OrderStatus.REFUNDING

        print("PASS: first request changed A1001 to REFUNDING")
        print("PASS: successful mutation invalidated the order cache")
        print("PASS: same key and request replayed the completed response")
        print("PASS: same key for A1002 returned an idempotency conflict")


if __name__ == "__main__":
    asyncio.run(main())
