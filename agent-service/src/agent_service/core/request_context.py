import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter
from uuid import UUID, uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = b"x-request-id"

logger = logging.getLogger(__name__)
_request_id: ContextVar[str | None] = ContextVar(
    "request_id",
    default=None,
)


def get_request_id() -> str | None:
    return _request_id.get()


@contextmanager
def request_id_context(request_id: str) -> Iterator[None]:
    token = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(token)


def resolve_request_id(provided_request_id: str | None) -> str:
    if provided_request_id is not None:
        try:
            return str(UUID(provided_request_id))
        except ValueError:
            pass
    return str(uuid4())


class RequestCorrelationMiddleware:
    """Propagate one safe request ID without buffering SSE responses."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = resolve_request_id(_header_value(scope))
        operation = _operation_for(
            method=str(scope.get("method", "")),
            path=str(scope.get("path", "")),
        )
        started_at = perf_counter()
        status_code = 500
        error_code = "UNHANDLED_EXCEPTION"

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, error_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                error_code = (
                    f"HTTP_{status_code}" if status_code >= 400 else "NONE"
                )
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != REQUEST_ID_HEADER
                ]
                headers.append(
                    (REQUEST_ID_HEADER, request_id.encode("ascii"))
                )
                message["headers"] = headers
            await send(message)

        with request_id_context(request_id):
            try:
                await self._app(scope, receive, send_with_request_id)
            except asyncio.CancelledError:
                error_code = "CLIENT_DISCONNECTED"
                raise
            finally:
                duration_ms = int((perf_counter() - started_at) * 1000)
                logger.info(
                    "request_completed request_id=%s operation=%s "
                    "status=%s duration_ms=%s error_code=%s",
                    request_id,
                    operation,
                    status_code,
                    duration_ms,
                    error_code,
                )


def _header_value(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name.lower() == REQUEST_ID_HEADER:
            try:
                return value.decode("ascii")
            except UnicodeDecodeError:
                return None
    return None


def _operation_for(*, method: str, path: str) -> str:
    if method == "POST" and path == "/api/v1/agent/threads":
        return "AGENT_THREAD_CREATE"
    if method == "POST" and path == "/api/v1/agent/chat/stream":
        return "AGENT_CHAT_STREAM"
    if method == "POST" and path.endswith("/resume"):
        return "AGENT_RESUME"
    if method == "POST" and path == "/internal/v1/knowledge/reindex":
        return "KNOWLEDGE_REINDEX"
    if method == "GET" and path == "/api/v1/health":
        return "HEALTH"
    return "OTHER"
