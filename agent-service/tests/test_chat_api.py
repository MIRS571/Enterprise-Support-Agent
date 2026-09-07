import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from agent_service.api.dependencies import (
    get_chat_rate_limiter,
    get_conversation_thread_service,
    get_support_agent_service,
)
from agent_service.domain.agent import (
    AgentApprovalRequired,
    AgentReply,
    AgentStreamCompleted,
    AgentStreamToken,
    ApprovalRequest,
    KnowledgeSource,
)
from agent_service.domain.intent import IntentType
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
from agent_service.main import app
from agent_service.services import (
    ApprovalNotPendingError,
    ConversationPersistenceUnavailableError,
    ConversationThreadNotFoundError,
    ConversationThreadService,
    RateLimitDecision,
    RateLimitExceededError,
    RateLimitUnavailableError,
    SupportAgentService,
)

TEST_INTERNAL_SERVICE_TOKEN = "test-internal-service-token-1234567890"


async def post_create_thread(
    service: Mock | None,
    *,
    internal_service_token: str | None = TEST_INTERNAL_SERVICE_TOKEN,
) -> httpx.Response:
    if service is not None:
        app.dependency_overrides[get_conversation_thread_service] = lambda: service
    try:
        transport = httpx.ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=transport,
                base_url="http://test-server",
            ) as client,
        ):
            headers = {
                "X-Tenant-Id": "company_001",
                "X-User-Id": "U1001",
            }
            if internal_service_token is not None:
                headers["X-Internal-Service-Token"] = internal_service_token
            return await client.post(
                "/api/v1/agent/threads",
                headers=headers,
            )
    finally:
        app.dependency_overrides.clear()


def test_create_thread_returns_server_identifier() -> None:
    service = Mock(spec=ConversationThreadService)
    service.create_thread = AsyncMock(
        return_value="11111111-1111-4111-8111-111111111111"
    )

    response = asyncio.run(post_create_thread(service))

    assert response.status_code == 201
    assert response.json() == {"thread_id": "11111111-1111-4111-8111-111111111111"}
    service.create_thread.assert_awaited_once_with(
        tenant_id="company_001",
        user_id="U1001",
    )


def test_create_thread_returns_503_without_persistence() -> None:
    response = asyncio.run(post_create_thread(None))

    assert response.status_code == 503


def test_agent_route_rejects_missing_internal_service_token() -> None:
    service = Mock(spec=ConversationThreadService)
    service.create_thread = AsyncMock()

    response = asyncio.run(
        post_create_thread(
            service,
            internal_service_token=None,
        )
    )

    assert response.status_code == 401
    service.create_thread.assert_not_awaited()


async def post_chat(
    service: Mock,
    *,
    rate_limiter: Mock | None = None,
) -> httpx.Response:
    app.dependency_overrides[get_support_agent_service] = lambda: service
    if rate_limiter is not None:
        app.dependency_overrides[get_chat_rate_limiter] = lambda: rate_limiter
    try:
        transport = httpx.ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=transport,
                base_url="http://test-server",
            ) as client,
        ):
            return await client.post(
                "/api/v1/agent/chat",
                headers={
                    "X-Internal-Service-Token": TEST_INTERNAL_SERVICE_TOKEN,
                    "X-Tenant-Id": "company_001",
                    "X-User-Id": "U1001",
                },
                json={
                    "thread_id": "thread_001",
                    "message": "帮我查询订单A1001",
                },
            )
    finally:
        app.dependency_overrides.clear()


def test_chat_returns_agent_reply() -> None:
    service = Mock(spec=SupportAgentService)
    service.chat = AsyncMock(
        return_value=AgentReply(
            answer="订单A1001已经发货。",
            intent=IntentType.ORDER_QUERY,
            order_id="A1001",
        )
    )

    response = asyncio.run(post_chat(service))

    assert response.status_code == 200
    assert response.json() == {
        "thread_id": "thread_001",
        "answer": "订单A1001已经发货。",
        "intent": "order_query",
        "order_id": "A1001",
        "sources": [],
    }
    service.chat.assert_awaited_once_with(
        tenant_id="company_001",
        user_id="U1001",
        thread_id="thread_001",
        message="帮我查询订单A1001",
    )


def test_chat_returns_rate_limit_headers() -> None:
    service = Mock(spec=SupportAgentService)
    service.chat = AsyncMock(
        return_value=AgentReply(
            answer="订单A1001已经发货。",
            intent=IntentType.ORDER_QUERY,
            order_id="A1001",
        )
    )
    limiter = Mock()
    limiter.check = AsyncMock(
        return_value=RateLimitDecision(
            limit=10,
            remaining=9,
            reset_after_seconds=60,
        )
    )

    response = asyncio.run(post_chat(service, rate_limiter=limiter))

    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "10"
    assert response.headers["X-RateLimit-Remaining"] == "9"
    assert response.headers["X-RateLimit-Reset"] == "60"


def test_chat_rejects_over_limit_before_agent_call() -> None:
    service = Mock(spec=SupportAgentService)
    service.chat = AsyncMock()
    limiter = Mock()
    limiter.check = AsyncMock(
        side_effect=RateLimitExceededError(retry_after_seconds=42)
    )

    response = asyncio.run(post_chat(service, rate_limiter=limiter))

    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMIT_EXCEEDED"
    assert response.headers["Retry-After"] == "42"
    service.chat.assert_not_awaited()


def test_chat_fails_closed_before_agent_call_when_limiter_is_down() -> None:
    service = Mock(spec=SupportAgentService)
    service.chat = AsyncMock()
    limiter = Mock()
    limiter.check = AsyncMock(side_effect=RateLimitUnavailableError())

    response = asyncio.run(post_chat(service, rate_limiter=limiter))

    assert response.status_code == 503
    assert response.json()["code"] == "RATE_LIMIT_UNAVAILABLE"
    service.chat.assert_not_awaited()


def test_chat_returns_approval_required() -> None:
    service = Mock(spec=SupportAgentService)
    service.chat = AsyncMock(
        return_value=AgentApprovalRequired(
            intent=IntentType.REFUND,
            order_id="A1001",
            approval=ApprovalRequest(
                operation="request_refund",
                order_id="A1001",
                product_name="机械键盘",
                total_amount="299.00",
                status="SHIPPED",
            ),
        )
    )

    response = asyncio.run(post_chat(service))

    assert response.status_code == 200
    assert response.json() == {
        "thread_id": "thread_001",
        "status": "approval_required",
        "intent": "refund",
        "order_id": "A1001",
        "approval": {
            "operation": "request_refund",
            "order_id": "A1001",
            "product_name": "机械键盘",
            "total_amount": "299.00",
            "status": "SHIPPED",
        },
    }


async def post_chat_stream(service: Mock) -> httpx.Response:
    app.dependency_overrides[get_support_agent_service] = lambda: service
    try:
        transport = httpx.ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=transport,
                base_url="http://test-server",
            ) as client,
        ):
            return await client.post(
                "/api/v1/agent/chat/stream",
                headers={
                    "X-Internal-Service-Token": TEST_INTERNAL_SERVICE_TOKEN,
                    "X-Tenant-Id": "company_001",
                    "X-User-Id": "U1001",
                },
                json={
                    "thread_id": "thread_001",
                    "message": "帮我查询订单A1001",
                },
            )
    finally:
        app.dependency_overrides.clear()


def test_chat_stream_returns_sse_tokens_result_and_done() -> None:
    service = Mock(spec=SupportAgentService)

    async def events():
        yield AgentStreamToken(content="订单")
        yield AgentStreamToken(content="已发货。")
        yield AgentStreamCompleted(
            result=AgentReply(
                answer="订单已发货。",
                intent=IntentType.ORDER_QUERY,
                order_id="A1001",
            )
        )

    service.chat_stream = AsyncMock(return_value=events())

    response = asyncio.run(post_chat_stream(service))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    assert "event: metadata" in response.text
    assert 'data: {"content":"订单"}' in response.text
    assert "event: result" in response.text
    assert '"order_id":"A1001"' in response.text
    assert response.text.endswith(
        'event: done\ndata: {"status":"completed"}\n\n'
    )


def test_chat_stream_checks_thread_before_starting_response() -> None:
    service = Mock(spec=SupportAgentService)
    service.chat_stream = AsyncMock(
        side_effect=ConversationThreadNotFoundError()
    )

    response = asyncio.run(post_chat_stream(service))

    assert response.status_code == 404
    assert response.json()["code"] == "CONVERSATION_NOT_FOUND"


def test_chat_stream_hides_internal_error_after_stream_started() -> None:
    service = Mock(spec=SupportAgentService)

    async def events():
        yield AgentStreamToken(content="订单")
        raise RuntimeError("private provider error")

    service.chat_stream = AsyncMock(return_value=events())

    response = asyncio.run(post_chat_stream(service))

    assert response.status_code == 200
    assert "event: error" in response.text
    assert '"code":"STREAM_FAILED"' in response.text
    assert '"retryable":true' in response.text
    assert "private provider error" not in response.text
    assert "event: done" not in response.text


async def post_resume(
    service: Mock,
    *,
    approved: bool,
    idempotency_key: str | None = "refund-001",
) -> httpx.Response:
    app.dependency_overrides[get_support_agent_service] = lambda: service
    try:
        transport = httpx.ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=transport,
                base_url="http://test-server",
            ) as client,
        ):
            headers = {
                "X-Internal-Service-Token": TEST_INTERNAL_SERVICE_TOKEN,
                "X-Tenant-Id": "company_001",
                "X-User-Id": "U1001",
            }
            if idempotency_key is not None:
                headers["Idempotency-Key"] = idempotency_key
            return await client.post(
                "/api/v1/agent/threads/thread_001/resume",
                headers=headers,
                json={"approved": approved},
            )
    finally:
        app.dependency_overrides.clear()


def test_resume_returns_completed_agent_reply() -> None:
    service = Mock(spec=SupportAgentService)
    service.resume_refund = AsyncMock(
        return_value=AgentReply(
            answer=("订单 A1001 的退款申请已提交，当前状态为 REFUNDING。"),
            intent=IntentType.REFUND,
            order_id="A1001",
        )
    )

    response = asyncio.run(post_resume(service, approved=True))

    assert response.status_code == 200
    assert response.json()["answer"].endswith("REFUNDING。")
    service.resume_refund.assert_awaited_once_with(
        tenant_id="company_001",
        user_id="U1001",
        thread_id="thread_001",
        approved=True,
        idempotency_key="refund-001",
    )


def test_resume_requires_idempotency_key() -> None:
    service = Mock(spec=SupportAgentService)
    service.resume_refund = AsyncMock()

    response = asyncio.run(
        post_resume(
            service,
            approved=True,
            idempotency_key=None,
        )
    )

    assert response.status_code == 422
    service.resume_refund.assert_not_awaited()


def test_chat_returns_structured_sources() -> None:
    service = Mock(spec=SupportAgentService)
    service.chat = AsyncMock(
        return_value=AgentReply(
            answer="不支持七天无理由退货。[资料1]",
            intent=IntentType.POLICY_QUERY,
            sources=[
                KnowledgeSource(
                    reference_number=1,
                    document_id="refund-policy",
                    title="退款与退货政策",
                    section_title="七天无理由退货",
                    version="1.0",
                )
            ],
        )
    )

    response = asyncio.run(post_chat(service))

    assert response.status_code == 200
    assert response.json()["sources"] == [
        {
            "reference_number": 1,
            "document_id": "refund-policy",
            "title": "退款与退货政策",
            "section_title": "七天无理由退货",
            "version": "1.0",
        }
    ]


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (
            UpstreamServiceError(500),
            502,
            "UPSTREAM_SERVICE_ERROR",
        ),
        (
            UpstreamContractError("invalid contract"),
            502,
            "UPSTREAM_CONTRACT_ERROR",
        ),
        (
            BusinessServiceUnavailableError("unavailable"),
            503,
            "BUSINESS_SERVICE_UNAVAILABLE",
        ),
        (
            BusinessServiceTimeoutError("timeout"),
            504,
            "BUSINESS_SERVICE_TIMEOUT",
        ),
        (
            ConversationThreadNotFoundError(),
            404,
            "CONVERSATION_NOT_FOUND",
        ),
        (
            ConversationPersistenceUnavailableError(),
            503,
            "CONVERSATION_PERSISTENCE_UNAVAILABLE",
        ),
        (
            ApprovalNotPendingError(),
            409,
            "APPROVAL_NOT_PENDING",
        ),
        (
            OrderNotFoundError("A1001"),
            404,
            "ORDER_NOT_FOUND",
        ),
        (
            RefundNotAllowedError("A1001"),
            409,
            "REFUND_NOT_ALLOWED",
        ),
        (
            RefundRequestOutcomeUnknownError("A1001"),
            504,
            "REFUND_OUTCOME_UNKNOWN",
        ),
        (
            IdempotencyConflictError(),
            409,
            "IDEMPOTENCY_CONFLICT",
        ),
        (
            IdempotencyInProgressError(),
            409,
            "IDEMPOTENCY_IN_PROGRESS",
        ),
        (
            IdempotencyUnavailableError(),
            503,
            "IDEMPOTENCY_UNAVAILABLE",
        ),
    ],
)
def test_chat_maps_service_errors(
    error: Exception,
    expected_status: int,
    expected_code: str,
) -> None:
    service = Mock(spec=SupportAgentService)
    service.chat = AsyncMock(side_effect=error)

    response = asyncio.run(post_chat(service))

    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code
