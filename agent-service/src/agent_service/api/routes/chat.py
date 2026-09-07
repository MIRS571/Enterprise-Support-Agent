from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import StreamingResponse

from agent_service.api.dependencies import (
    ChatRateLimiterDep,
    ConversationThreadServiceDep,
    SupportAgentServiceDep,
    verify_internal_service_token,
)
from agent_service.api.schemas import (
    AgentResponse,
    ApprovalDecisionRequest,
    ChatRequest,
    ChatResponse,
    ThreadCreateResponse,
    response_from_result,
)
from agent_service.api.streaming import encode_agent_event_stream

router = APIRouter(
    prefix="/agent",
    tags=["Agent"],
    dependencies=[Depends(verify_internal_service_token)],
)


def clean_identity(
    *,
    tenant_id: str,
    user_id: str,
) -> tuple[str, str]:
    cleaned_tenant_id = tenant_id.strip()
    cleaned_user_id = user_id.strip()
    if not cleaned_tenant_id or not cleaned_user_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="身份请求头不能为空",
        )
    return cleaned_tenant_id, cleaned_user_id


@router.post(
    "/threads",
    response_model=ThreadCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_thread(
    service: ConversationThreadServiceDep,
    tenant_id: Annotated[
        str,
        Header(alias="X-Tenant-Id", max_length=64),
    ],
    user_id: Annotated[
        str,
        Header(alias="X-User-Id", max_length=64),
    ],
) -> ThreadCreateResponse:
    cleaned_tenant_id, cleaned_user_id = clean_identity(
        tenant_id=tenant_id,
        user_id=user_id,
    )
    thread_id = await service.create_thread(
        tenant_id=cleaned_tenant_id,
        user_id=cleaned_user_id,
    )
    return ThreadCreateResponse(thread_id=thread_id)


@router.post(
    "/chat",
    response_model=AgentResponse,
)
async def chat(
    request: ChatRequest,
    response: Response,
    service: SupportAgentServiceDep,
    rate_limiter: ChatRateLimiterDep,
    tenant_id: Annotated[
        str,
        Header(alias="X-Tenant-Id", max_length=64),
    ],
    user_id: Annotated[
        str,
        Header(alias="X-User-Id", max_length=64),
    ],
) -> AgentResponse:
    cleaned_tenant_id, cleaned_user_id = clean_identity(
        tenant_id=tenant_id,
        user_id=user_id,
    )

    if rate_limiter is not None:
        decision = await rate_limiter.check(
            tenant_id=cleaned_tenant_id,
            user_id=cleaned_user_id,
        )
        response.headers["X-RateLimit-Limit"] = str(decision.limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        response.headers["X-RateLimit-Reset"] = str(decision.reset_after_seconds)

    reply = await service.chat(
        tenant_id=cleaned_tenant_id,
        user_id=cleaned_user_id,
        thread_id=request.thread_id,
        message=request.message,
    )
    return response_from_result(
        thread_id=request.thread_id,
        result=reply,
    )


@router.post("/chat/stream")
async def stream_chat(
    request: ChatRequest,
    service: SupportAgentServiceDep,
    rate_limiter: ChatRateLimiterDep,
    tenant_id: Annotated[
        str,
        Header(alias="X-Tenant-Id", max_length=64),
    ],
    user_id: Annotated[
        str,
        Header(alias="X-User-Id", max_length=64),
    ],
) -> StreamingResponse:
    cleaned_tenant_id, cleaned_user_id = clean_identity(
        tenant_id=tenant_id,
        user_id=user_id,
    )
    headers = {
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
    }

    if rate_limiter is not None:
        decision = await rate_limiter.check(
            tenant_id=cleaned_tenant_id,
            user_id=cleaned_user_id,
        )
        headers.update(
            {
                "X-RateLimit-Limit": str(decision.limit),
                "X-RateLimit-Remaining": str(decision.remaining),
                "X-RateLimit-Reset": str(decision.reset_after_seconds),
            }
        )

    events = await service.chat_stream(
        tenant_id=cleaned_tenant_id,
        user_id=cleaned_user_id,
        thread_id=request.thread_id,
        message=request.message,
    )
    return StreamingResponse(
        content=encode_agent_event_stream(
            thread_id=request.thread_id,
            events=events,
        ),
        media_type="text/event-stream",
        headers=headers,
    )


@router.post(
    "/threads/{thread_id}/resume",
    response_model=ChatResponse,
)
async def resume_thread(
    thread_id: str,
    request: ApprovalDecisionRequest,
    service: SupportAgentServiceDep,
    tenant_id: Annotated[
        str,
        Header(alias="X-Tenant-Id", max_length=64),
    ],
    user_id: Annotated[
        str,
        Header(alias="X-User-Id", max_length=64),
    ],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        ),
    ],
) -> ChatResponse:
    cleaned_tenant_id, cleaned_user_id = clean_identity(
        tenant_id=tenant_id,
        user_id=user_id,
    )
    reply = await service.resume_refund(
        tenant_id=cleaned_tenant_id,
        user_id=cleaned_user_id,
        thread_id=thread_id,
        approved=request.approved,
        idempotency_key=idempotency_key.strip(),
    )
    return ChatResponse.from_reply(
        thread_id=thread_id,
        reply=reply,
    )
