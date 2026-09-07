import asyncio
from collections.abc import Awaitable

import httpx
import pytest

from agent_service.core.request_context import request_id_context
from agent_service.domain.order import OrderStatus
from agent_service.integrations.business_service.client import BusinessServiceClient
from agent_service.integrations.business_service.errors import (
    BusinessServiceTimeoutError,
    IdempotencyConflictError,
    IdempotencyInProgressError,
    IdempotencyUnavailableError,
    OrderNotFoundError,
    RefundNotAllowedError,
    RefundRequestOutcomeUnknownError,
    UpstreamContractError,
    UpstreamServiceError,
)


def run[T](coroutine: Awaitable[T]) -> T:
    return asyncio.run(coroutine)


def make_client(
    handler: httpx.AsyncBaseTransport,
    *,
    max_retries: int = 0,
) -> tuple[httpx.AsyncClient, BusinessServiceClient]:
    http_client = httpx.AsyncClient(
        base_url="http://business-service",
        transport=handler,
    )
    return http_client, BusinessServiceClient(http_client, max_retries)


def test_get_order_returns_validated_model() -> None:
    request_id = "c1ac5efd-1bb4-4dbf-b0e6-3a8320c4f30b"

    async def scenario() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["X-Tenant-Id"] == "company_001"
            assert request.headers["X-User-Id"] == "U1001"
            assert request.headers["X-Request-Id"] == request_id
            return httpx.Response(
                200,
                json={
                    "orderId": "A1001",
                    "productName": "机械键盘",
                    "quantity": 1,
                    "totalAmount": 299.00,
                    "status": "SHIPPED",
                    "createdAt": "2026-08-20T02:30:00Z",
                    "cancelable": False,
                    "refundable": True,
                },
            )

        http_client, client = make_client(httpx.MockTransport(handler))
        with request_id_context(request_id):
            async with http_client:
                order = await client.get_order(
                    tenant_id="company_001",
                    user_id="U1001",
                    order_id="A1001",
                )

        assert order.order_id == "A1001"
        assert order.status is OrderStatus.SHIPPED
        assert order.cancelable is False

    run(scenario())


def test_get_order_translates_not_found() -> None:
    async def scenario() -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"code": "ORDER_NOT_FOUND"})

        http_client, client = make_client(httpx.MockTransport(handler))
        async with http_client:
            with pytest.raises(OrderNotFoundError):
                await client.get_order(
                    tenant_id="company_001",
                    user_id="U1001",
                    order_id="UNKNOWN",
                )

    run(scenario())


def test_get_order_retries_timeout() -> None:
    async def scenario() -> None:
        attempts = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            raise httpx.ReadTimeout("timeout", request=request)

        http_client, client = make_client(
            httpx.MockTransport(handler),
            max_retries=1,
        )
        async with http_client:
            with pytest.raises(BusinessServiceTimeoutError):
                await client.get_order(
                    tenant_id="company_001",
                    user_id="U1001",
                    order_id="A1001",
                )

        assert attempts == 2

    run(scenario())


def test_get_order_retries_upstream_500() -> None:
    async def scenario() -> None:
        attempts = 0

        async def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(500)

        http_client, client = make_client(
            httpx.MockTransport(handler),
            max_retries=1,
        )
        async with http_client:
            with pytest.raises(UpstreamServiceError) as caught:
                await client.get_order(
                    tenant_id="company_001",
                    user_id="U1001",
                    order_id="A1001",
                )

        assert attempts == 2
        assert caught.value.status_code == 500

    run(scenario())


def test_get_order_rejects_invalid_contract() -> None:
    async def scenario() -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"id": "A1001"})

        http_client, client = make_client(httpx.MockTransport(handler))
        async with http_client:
            with pytest.raises(UpstreamContractError):
                await client.get_order(
                    tenant_id="company_001",
                    user_id="U1001",
                    order_id="A1001",
                )

    run(scenario())


def test_request_refund_returns_refunding_order_without_retry() -> None:
    request_id = "c1ac5efd-1bb4-4dbf-b0e6-3a8320c4f30b"

    async def scenario() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path == ("/api/v1/orders/A1001/refund-requests")
            assert request.headers["X-Tenant-Id"] == "company_001"
            assert request.headers["X-User-Id"] == "U1001"
            assert request.headers["Idempotency-Key"] == "refund-001"
            assert request.headers["X-Request-Id"] == request_id
            return httpx.Response(
                202,
                json={
                    "orderId": "A1001",
                    "productName": "机械键盘",
                    "quantity": 1,
                    "totalAmount": 299.00,
                    "status": "REFUNDING",
                    "createdAt": "2026-08-20T02:30:00Z",
                    "cancelable": False,
                    "refundable": False,
                },
            )

        http_client, client = make_client(
            httpx.MockTransport(handler),
            max_retries=3,
        )
        with request_id_context(request_id):
            async with http_client:
                order = await client.request_refund(
                    tenant_id="company_001",
                    user_id="U1001",
                    order_id="A1001",
                    idempotency_key="refund-001",
                )

        assert order.status is OrderStatus.REFUNDING

    run(scenario())


def test_request_refund_translates_conflict() -> None:
    async def scenario() -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                409,
                json={"code": "REFUND_NOT_ALLOWED"},
            )

        http_client, client = make_client(httpx.MockTransport(handler))
        async with http_client:
            with pytest.raises(RefundNotAllowedError):
                await client.request_refund(
                    tenant_id="company_001",
                    user_id="U1001",
                    order_id="A1002",
                    idempotency_key="refund-002",
                )

    run(scenario())


@pytest.mark.parametrize(
    ("status_code", "error_code", "expected_error"),
    [
        (409, "IDEMPOTENCY_CONFLICT", IdempotencyConflictError),
        (409, "IDEMPOTENCY_IN_PROGRESS", IdempotencyInProgressError),
        (503, "IDEMPOTENCY_UNAVAILABLE", IdempotencyUnavailableError),
        (
            504,
            "IDEMPOTENCY_OUTCOME_UNKNOWN",
            RefundRequestOutcomeUnknownError,
        ),
    ],
)
def test_request_refund_preserves_idempotency_error_contract(
    status_code: int,
    error_code: str,
    expected_error: type[Exception],
) -> None:
    async def scenario() -> None:
        async def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, json={"code": error_code})

        http_client, client = make_client(httpx.MockTransport(handler))
        async with http_client:
            with pytest.raises(expected_error):
                await client.request_refund(
                    tenant_id="company_001",
                    user_id="U1001",
                    order_id="A1001",
                    idempotency_key="refund-001",
                )

    run(scenario())


def test_request_refund_does_not_retry_unknown_timeout() -> None:
    async def scenario() -> None:
        attempts = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            raise httpx.ReadTimeout("timeout", request=request)

        http_client, client = make_client(
            httpx.MockTransport(handler),
            max_retries=3,
        )
        async with http_client:
            with pytest.raises(RefundRequestOutcomeUnknownError):
                await client.request_refund(
                    tenant_id="company_001",
                    user_id="U1001",
                    order_id="A1001",
                    idempotency_key="refund-003",
                )

        assert attempts == 1

    run(scenario())
