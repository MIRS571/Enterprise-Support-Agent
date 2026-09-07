import logging
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_service.core.request_context import (
    RequestCorrelationMiddleware,
    get_request_id,
)

REQUEST_ID = "c1ac5efd-1bb4-4dbf-b0e6-3a8320c4f30b"


def build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestCorrelationMiddleware)

    @app.get("/probe")
    async def probe() -> dict[str, str | None]:
        return {"request_id": get_request_id()}

    return app


def test_preserves_request_id_in_context_and_response() -> None:
    with TestClient(build_app()) as client:
        response = client.get(
            "/probe",
            headers={"X-Request-Id": REQUEST_ID},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == REQUEST_ID
    assert response.json() == {"request_id": REQUEST_ID}


def test_replaces_invalid_request_id_without_logging_request_data(
    caplog,
) -> None:
    caplog.set_level(logging.INFO)

    with TestClient(build_app()) as client:
        response = client.get(
            "/probe",
            headers={"X-Request-Id": "unsafe-value"},
        )

    replacement = response.headers["X-Request-Id"]
    UUID(replacement)
    assert replacement != "unsafe-value"
    assert "unsafe-value" not in caplog.text
