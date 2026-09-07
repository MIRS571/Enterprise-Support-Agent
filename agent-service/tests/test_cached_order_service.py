import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

from redis.exceptions import ConnectionError

from agent_service.core.redis import (
    RedisAvailability,
    RedisAvailabilityStatus,
)
from agent_service.core.redis_keys import RedisKeyBuilder
from agent_service.domain.order import OrderResponse, OrderStatus
from agent_service.integrations.business_service.cached import (
    CachedOrderService,
)


def make_order(
    status: OrderStatus = OrderStatus.SHIPPED,
) -> OrderResponse:
    return OrderResponse(
        orderId="A1001",
        productName="机械键盘",
        quantity=1,
        totalAmount=Decimal("299.00"),
        status=status,
        createdAt=datetime(2026, 8, 20, tzinfo=UTC),
        cancelable=False,
        refundable=status is OrderStatus.SHIPPED,
    )


def make_service(
    *,
    delegate: Mock,
    redis_client: Mock,
) -> tuple[CachedOrderService, RedisAvailability]:
    availability = RedisAvailability(status=RedisAvailabilityStatus.UP)
    service = CachedOrderService(
        delegate=delegate,
        redis_client=redis_client,
        key_builder=RedisKeyBuilder(
            prefix="esa",
            environment="test",
        ),
        ttl_seconds=15,
        availability=availability,
    )
    return service, availability


def test_cache_miss_calls_java_and_writes_with_ttl() -> None:
    async def scenario() -> None:
        order = make_order()
        delegate = Mock()
        delegate.get_order = AsyncMock(return_value=order)
        redis_client = Mock()
        redis_client.get = AsyncMock(return_value=None)
        redis_client.set = AsyncMock(return_value=True)
        service, _availability = make_service(
            delegate=delegate,
            redis_client=redis_client,
        )

        result = await service.get_order(
            tenant_id="company_001",
            user_id="U1001",
            order_id="A1001",
        )

        assert result == order
        delegate.get_order.assert_awaited_once_with(
            tenant_id="company_001",
            user_id="U1001",
            order_id="A1001",
        )
        redis_client.set.assert_awaited_once()
        assert redis_client.set.await_args.kwargs["ex"] == 15

    asyncio.run(scenario())


def test_cache_hit_skips_java() -> None:
    async def scenario() -> None:
        order = make_order()
        delegate = Mock()
        delegate.get_order = AsyncMock()
        redis_client = Mock()
        redis_client.get = AsyncMock(return_value=order.model_dump_json(by_alias=True))
        service, _availability = make_service(
            delegate=delegate,
            redis_client=redis_client,
        )

        result = await service.get_order(
            tenant_id="company_001",
            user_id="U1001",
            order_id="A1001",
        )

        assert result == order
        delegate.get_order.assert_not_awaited()

    asyncio.run(scenario())


def test_cache_failure_bypasses_redis() -> None:
    async def scenario() -> None:
        order = make_order()
        delegate = Mock()
        delegate.get_order = AsyncMock(return_value=order)
        redis_client = Mock()
        redis_client.get = AsyncMock(side_effect=ConnectionError("connection lost"))
        redis_client.set = AsyncMock(side_effect=ConnectionError("connection lost"))
        service, availability = make_service(
            delegate=delegate,
            redis_client=redis_client,
        )

        result = await service.get_order(
            tenant_id="company_001",
            user_id="U1001",
            order_id="A1001",
        )

        assert result == order
        assert availability.status is RedisAvailabilityStatus.DOWN
        delegate.get_order.assert_awaited_once()

    asyncio.run(scenario())


def test_refund_success_deletes_owned_order_cache() -> None:
    async def scenario() -> None:
        refunding_order = make_order(OrderStatus.REFUNDING)
        delegate = Mock()
        delegate.request_refund = AsyncMock(return_value=refunding_order)
        redis_client = Mock()
        redis_client.delete = AsyncMock(return_value=1)
        service, _availability = make_service(
            delegate=delegate,
            redis_client=redis_client,
        )

        result = await service.request_refund(
            tenant_id="company_001",
            user_id="U1001",
            order_id="A1001",
            idempotency_key="refund-001",
        )

        assert result.status is OrderStatus.REFUNDING
        redis_client.delete.assert_awaited_once_with(
            "esa:test:cache:order:company_001:U1001:A1001"
        )
        delegate.request_refund.assert_awaited_once_with(
            tenant_id="company_001",
            user_id="U1001",
            order_id="A1001",
            idempotency_key="refund-001",
        )

    asyncio.run(scenario())
