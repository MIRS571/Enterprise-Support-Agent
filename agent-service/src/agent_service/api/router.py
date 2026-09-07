from fastapi import APIRouter

from agent_service.api.routes.chat import router as chat_router
from agent_service.api.routes.health import router as health_router
from agent_service.api.routes.knowledge import router as knowledge_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(chat_router)

internal_router = APIRouter(prefix="/internal/v1")
internal_router.include_router(knowledge_router)
