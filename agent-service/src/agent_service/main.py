from fastapi import FastAPI

from agent_service.api.exception_handlers import register_exception_handlers
from agent_service.api.router import api_router, internal_router
from agent_service.core.config import get_settings
from agent_service.core.lifespan import lifespan
from agent_service.core.request_context import RequestCorrelationMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    application.add_middleware(RequestCorrelationMiddleware)
    register_exception_handlers(application)
    application.include_router(api_router)
    application.include_router(internal_router)
    return application


app = create_app()
