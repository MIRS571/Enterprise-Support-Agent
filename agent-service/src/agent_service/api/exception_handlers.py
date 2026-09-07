import logging
from datetime import UTC, datetime

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from agent_service.api.schemas import ApiErrorResponse
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
from agent_service.services import (
    ApprovalNotPendingError,
    ConversationPersistenceUnavailableError,
    ConversationThreadNotFoundError,
    RateLimitExceededError,
    RateLimitUnavailableError,
)

logger = logging.getLogger(__name__)


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    error = ApiErrorResponse(
        code=code,
        message=message,
        timestamp=datetime.now(UTC),
    )
    return JSONResponse(
        status_code=status_code,
        content=error.model_dump(mode="json"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RateLimitExceededError)
    async def handle_rate_limit_exceeded(
        _request: Request,
        exception: RateLimitExceededError,
    ) -> JSONResponse:
        response = error_response(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="RATE_LIMIT_EXCEEDED",
            message="请求过于频繁，请稍后重试。",
        )
        response.headers["Retry-After"] = str(exception.retry_after_seconds)
        return response

    @app.exception_handler(RateLimitUnavailableError)
    async def handle_rate_limit_unavailable(
        _request: Request,
        _exception: RateLimitUnavailableError,
    ) -> JSONResponse:
        return error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="RATE_LIMIT_UNAVAILABLE",
            message="请求保护服务暂时不可用，请稍后重试。",
        )

    @app.exception_handler(ConversationThreadNotFoundError)
    async def handle_conversation_thread_not_found(
        _request: Request,
        _exception: ConversationThreadNotFoundError,
    ) -> JSONResponse:
        return error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="CONVERSATION_NOT_FOUND",
            message="会话不存在。",
        )

    @app.exception_handler(ConversationPersistenceUnavailableError)
    async def handle_conversation_persistence_unavailable(
        _request: Request,
        _exception: ConversationPersistenceUnavailableError,
    ) -> JSONResponse:
        return error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="CONVERSATION_PERSISTENCE_UNAVAILABLE",
            message="会话服务暂时不可用，请稍后重试。",
        )

    @app.exception_handler(ApprovalNotPendingError)
    async def handle_approval_not_pending(
        _request: Request,
        _exception: ApprovalNotPendingError,
    ) -> JSONResponse:
        return error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="APPROVAL_NOT_PENDING",
            message="当前会话没有待确认的操作。",
        )

    @app.exception_handler(OrderNotFoundError)
    async def handle_order_not_found(
        _request: Request,
        _exception: OrderNotFoundError,
    ) -> JSONResponse:
        return error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ORDER_NOT_FOUND",
            message="订单不存在或当前用户无权访问。",
        )

    @app.exception_handler(RefundNotAllowedError)
    async def handle_refund_not_allowed(
        _request: Request,
        _exception: RefundNotAllowedError,
    ) -> JSONResponse:
        return error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="REFUND_NOT_ALLOWED",
            message="订单当前状态不允许申请退款。",
        )

    @app.exception_handler(RefundRequestOutcomeUnknownError)
    async def handle_refund_outcome_unknown(
        _request: Request,
        _exception: RefundRequestOutcomeUnknownError,
    ) -> JSONResponse:
        return error_response(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            code="REFUND_OUTCOME_UNKNOWN",
            message="退款申请结果未知，请先查询订单状态，勿重复提交。",
        )

    @app.exception_handler(IdempotencyConflictError)
    async def handle_idempotency_conflict(
        _request: Request,
        _exception: IdempotencyConflictError,
    ) -> JSONResponse:
        return error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="IDEMPOTENCY_CONFLICT",
            message="该幂等键已用于另一项请求，请更换幂等键。",
        )

    @app.exception_handler(IdempotencyInProgressError)
    async def handle_idempotency_in_progress(
        _request: Request,
        _exception: IdempotencyInProgressError,
    ) -> JSONResponse:
        return error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="IDEMPOTENCY_IN_PROGRESS",
            message="相同退款请求正在处理中，请勿重复提交。",
        )

    @app.exception_handler(IdempotencyUnavailableError)
    async def handle_idempotency_unavailable(
        _request: Request,
        _exception: IdempotencyUnavailableError,
    ) -> JSONResponse:
        return error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="IDEMPOTENCY_UNAVAILABLE",
            message="退款请求保护服务暂时不可用，请稍后重试。",
        )

    @app.exception_handler(BusinessServiceUnavailableError)
    async def handle_business_service_unavailable(
        _request: Request,
        _exception: BusinessServiceUnavailableError,
    ) -> JSONResponse:
        return error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="BUSINESS_SERVICE_UNAVAILABLE",
            message="订单服务暂时不可用，请稍后重试。",
        )

    @app.exception_handler(BusinessServiceTimeoutError)
    async def handle_business_service_timeout(
        _request: Request,
        _exception: BusinessServiceTimeoutError,
    ) -> JSONResponse:
        return error_response(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            code="BUSINESS_SERVICE_TIMEOUT",
            message="订单服务响应超时，请稍后重试。",
        )

    @app.exception_handler(UpstreamServiceError)
    async def handle_upstream_service_error(
        _request: Request,
        exception: UpstreamServiceError,
    ) -> JSONResponse:
        logger.warning(
            "business-service returned status_code=%s",
            exception.status_code,
        )
        return error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="UPSTREAM_SERVICE_ERROR",
            message="订单服务返回异常响应。",
        )

    @app.exception_handler(UpstreamContractError)
    async def handle_upstream_contract_error(
        _request: Request,
        _exception: UpstreamContractError,
    ) -> JSONResponse:
        return error_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="UPSTREAM_CONTRACT_ERROR",
            message="订单服务响应格式异常。",
        )
