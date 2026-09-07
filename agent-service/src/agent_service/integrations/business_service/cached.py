import logging

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from agent_service.core.redis import RedisAvailability
from agent_service.core.redis_keys import RedisKeyBuilder
from agent_service.domain.order import OrderResponse
from agent_service.integrations.business_service.client import OrderService

logger = logging.getLogger(__name__)


class CachedOrderService:
    def __init__(
        self,
        *,
        delegate: OrderService,
        redis_client: Redis,
        key_builder: RedisKeyBuilder,
        ttl_seconds: int,
        availability: RedisAvailability,
    ) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be at least 1")
        self._delegate = delegate
        self._redis = redis_client
        self._key_builder = key_builder
        self._ttl_seconds = ttl_seconds
        self._availability = availability

    async def get_order(
        self,
        *,
        tenant_id: str,
        user_id: str,
        order_id: str,
    ) -> OrderResponse:
        cache_key = self._key_builder.order_cache(
            tenant_id=tenant_id,
            user_id=user_id,
            order_id=order_id,
        )
        cached_order = await self._read(cache_key)
        if cached_order is not None:
            return cached_order

        order = await self._delegate.get_order(
            tenant_id=tenant_id,
            user_id=user_id,
            order_id=order_id,
        )
        await self._write(cache_key, order)
        return order

    async def request_refund(
        self,
        *,
        tenant_id: str,
        user_id: str,
        order_id: str,
        idempotency_key: str,
    ) -> OrderResponse:
        order = await self._delegate.request_refund(
            tenant_id=tenant_id,
            user_id=user_id,
            order_id=order_id,
            idempotency_key=idempotency_key,
        )
        cache_key = self._key_builder.order_cache(
            tenant_id=tenant_id,
            user_id=user_id,
            order_id=order_id,
        )
        await self._delete(cache_key)
        return order

    async def _read(
        self,
        cache_key: str,
    ) -> OrderResponse | None:
        try:
            payload = await self._redis.get(cache_key)
        except RedisError:
            self._availability.mark_down()
            logger.exception("Redis order cache read failed")
            return None

        self._availability.mark_up()
        if payload is None:
            return None

        try:
            return OrderResponse.model_validate_json(payload)
        except (ValueError, ValidationError):
            logger.warning("Invalid order cache entry; deleting it")
            await self._delete(cache_key)
            return None

    async def _write(
        self,
        cache_key: str,
        order: OrderResponse,
    ) -> None:
        try:
            await self._redis.set(
                cache_key,
                order.model_dump_json(by_alias=True),
                ex=self._ttl_seconds,
            )
        except RedisError:
            self._availability.mark_down()
            logger.exception("Redis order cache write failed")
            return

        self._availability.mark_up()

    async def _delete(self, cache_key: str) -> None:
        try:
            await self._redis.delete(cache_key)
        except RedisError:
            self._availability.mark_down()
            logger.exception("Redis order cache delete failed")
            return

        self._availability.mark_up()
