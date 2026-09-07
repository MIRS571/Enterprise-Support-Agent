from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from agent_service.core.config import Settings, get_settings
from agent_service.core.redis import RedisAvailability
from agent_service.rag import RagAvailability

router = APIRouter(tags=["System"])


class ComponentHealth(BaseModel):
    status: str


class HealthResponse(BaseModel):
    service: str
    status: str
    environment: str
    components: dict[str, ComponentHealth]


@router.get("/health", response_model=HealthResponse)
async def health(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    rag_availability: RagAvailability | None = getattr(
        request.app.state,
        "rag_availability",
        None,
    )
    rag_status = (
        rag_availability.status.value if rag_availability is not None else "UNKNOWN"
    )
    redis_availability: RedisAvailability | None = getattr(
        request.app.state,
        "redis_availability",
        None,
    )
    redis_status = (
        redis_availability.status.value if redis_availability is not None else "UNKNOWN"
    )
    return HealthResponse(
        service="agent-service",
        status="UP" if rag_status == "UP" else "DEGRADED",
        environment=settings.environment,
        components={
            "rag": ComponentHealth(status=rag_status),
            "redis": ComponentHealth(status=redis_status),
        },
    )
