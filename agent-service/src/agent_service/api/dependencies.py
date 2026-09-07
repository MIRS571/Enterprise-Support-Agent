from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from agent_service.core.config import Settings, get_settings
from agent_service.integrations.business_service import BusinessServiceClient
from agent_service.services import (
    ChatRateLimiter,
    ConversationThreadService,
    KnowledgeIngestionService,
    SupportAgentService,
)


def get_business_service_client(
    request: Request,
) -> BusinessServiceClient:
    return request.app.state.business_service_client


BusinessServiceClientDep = Annotated[
    BusinessServiceClient,
    Depends(get_business_service_client),
]


def get_support_agent_service(
    request: Request,
) -> SupportAgentService:
    return request.app.state.support_agent_service


SupportAgentServiceDep = Annotated[
    SupportAgentService,
    Depends(get_support_agent_service),
]


def get_chat_rate_limiter(
    request: Request,
) -> ChatRateLimiter | None:
    return getattr(
        request.app.state,
        "chat_rate_limiter",
        None,
    )


ChatRateLimiterDep = Annotated[
    ChatRateLimiter | None,
    Depends(get_chat_rate_limiter),
]


def get_conversation_thread_service(
    request: Request,
) -> ConversationThreadService:
    service = getattr(
        request.app.state,
        "conversation_thread_service",
        None,
    )
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conversation persistence is unavailable",
        )
    return service


ConversationThreadServiceDep = Annotated[
    ConversationThreadService,
    Depends(get_conversation_thread_service),
]


def verify_internal_service_token(
    settings: Annotated[Settings, Depends(get_settings)],
    provided_token: Annotated[
        str | None,
        Header(alias="X-Internal-Service-Token"),
    ] = None,
) -> None:
    if settings.internal_service_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal service authentication is not configured",
        )

    expected_token = settings.internal_service_token.get_secret_value()
    token_matches = provided_token is not None and compare_digest(
        provided_token.encode("utf-8"),
        expected_token.encode("utf-8"),
    )

    if not token_matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal service credentials",
        )


InternalServiceAuthDep = Annotated[
    None,
    Depends(verify_internal_service_token),
]


def get_knowledge_ingestion_service(
    request: Request,
) -> KnowledgeIngestionService:
    service = getattr(
        request.app.state,
        "knowledge_ingestion_service",
        None,
    )
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge ingestion service is unavailable",
        )
    return service


KnowledgeIngestionServiceDep = Annotated[
    KnowledgeIngestionService,
    Depends(get_knowledge_ingestion_service),
]
