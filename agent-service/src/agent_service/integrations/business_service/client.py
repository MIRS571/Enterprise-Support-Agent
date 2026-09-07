import asyncio
from typing import Protocol
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from agent_service.core.request_context import get_request_id
from agent_service.domain.order import OrderResponse, OrderStatus
from agent_service.integrations.business_service.errors import (
    BusinessServiceTimeoutError,
    BusinessServiceUnavailableError,
    IdempotencyConflictError,
    IdempotencyInProgressError,
    IdempotencyUnavailableError,
    OrderNotFoundError,
    RefundNotAllowedError,
    RefundRequestOutcomeUnknownError,
    UpstreamContractError,
    UpstreamServiceError,
)


class OrderService(Protocol):
    async def get_order(
        self,
        *,
        tenant_id: str,
        user_id: str,
        order_id: str,
    ) -> OrderResponse: ...

    async def request_refund(
        self,
        *,
        tenant_id: str,
        user_id: str,
        order_id: str,
        idempotency_key: str,
    ) -> OrderResponse: ...


class BusinessServiceClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        max_retries: int,
    ) -> None:
        self._http_client = http_client
        self._max_retries = max_retries

    async def get_order(
        self,
        *,
        tenant_id: str,
        user_id: str,
        order_id: str,
    ) -> OrderResponse:
        encoded_order_id = quote(order_id, safe="")
        response = await self._get_with_retry(
            path=f"/api/v1/orders/{encoded_order_id}",
            headers=self._trusted_headers(
                tenant_id=tenant_id,
                user_id=user_id,
            ),
        )

        if response.status_code == httpx.codes.NOT_FOUND:
            raise OrderNotFoundError(order_id)

        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise UpstreamServiceError(response.status_code)

        try:
            return OrderResponse.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise UpstreamContractError(
                "business-service 的订单响应不符合约定"
            ) from error

    async def request_refund(
        self,
        *,
        tenant_id: str,
        user_id: str,
        order_id: str,
        idempotency_key: str,
    ) -> OrderResponse:
        encoded_order_id = quote(order_id, safe="")
        try:
            response = await self._http_client.post(
                (f"/api/v1/orders/{encoded_order_id}/refund-requests"),
                headers={
                    **self._trusted_headers(
                        tenant_id=tenant_id,
                        user_id=user_id,
                    ),
                    "Idempotency-Key": idempotency_key,
                },
            )
        except httpx.TimeoutException as error:
            raise RefundRequestOutcomeUnknownError(order_id) from error
        except httpx.RequestError as error:
            raise BusinessServiceUnavailableError(
                "无法连接 business-service"
            ) from error

        if response.status_code == httpx.codes.NOT_FOUND:
            raise OrderNotFoundError(order_id)
        if response.status_code == httpx.codes.CONFLICT:
            error_code = self._read_error_code(response)
            if error_code == "REFUND_NOT_ALLOWED":
                raise RefundNotAllowedError(order_id)
            if error_code == "IDEMPOTENCY_CONFLICT":
                raise IdempotencyConflictError()
            if error_code == "IDEMPOTENCY_IN_PROGRESS":
                raise IdempotencyInProgressError()
        if (
            response.status_code == httpx.codes.SERVICE_UNAVAILABLE
            and self._read_error_code(response) == "IDEMPOTENCY_UNAVAILABLE"
        ):
            raise IdempotencyUnavailableError()
        if (
            response.status_code == httpx.codes.GATEWAY_TIMEOUT
            and self._read_error_code(response)
            == "IDEMPOTENCY_OUTCOME_UNKNOWN"
        ):
            raise RefundRequestOutcomeUnknownError(order_id)
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise UpstreamServiceError(response.status_code)

        try:
            order = OrderResponse.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise UpstreamContractError(
                "business-service 的退款响应不符合约定"
            ) from error
        if order.status is not OrderStatus.REFUNDING:
            raise UpstreamContractError("business-service 没有返回 REFUNDING 状态")
        return order

    @staticmethod
    def _read_error_code(response: httpx.Response) -> str | None:
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        code = payload.get("code")
        return code if isinstance(code, str) else None

    @staticmethod
    def _trusted_headers(
        *,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, str]:
        headers = {
            "X-Tenant-Id": tenant_id,
            "X-User-Id": user_id,
        }
        request_id = get_request_id()
        if request_id is not None:
            headers["X-Request-Id"] = request_id
        return headers

    async def _get_with_retry(
        self,
        *,
        path: str,
        headers: dict[str, str],
    ) -> httpx.Response:
        total_attempts = self._max_retries + 1

        for attempt in range(total_attempts):
            try:
                response = await self._http_client.get(
                    path,
                    headers=headers,
                )
            except httpx.TimeoutException as error:
                if attempt == self._max_retries:
                    raise BusinessServiceTimeoutError(
                        "business-service 请求超时"
                    ) from error
            except httpx.RequestError as error:
                if attempt == self._max_retries:
                    raise BusinessServiceUnavailableError(
                        "无法连接 business-service"
                    ) from error
            else:
                if response.status_code < 500 or attempt == self._max_retries:
                    return response

            await asyncio.sleep(min(0.1 * (2**attempt), 1.0))

        raise AssertionError("unreachable")
