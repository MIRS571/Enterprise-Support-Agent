from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from agent_service.api.dependencies import (
    verify_internal_service_token,
)
from agent_service.core.config import Settings, get_settings

TEST_TOKEN = "test-internal-service-token-1234567890"


def create_test_client(
    *,
    configured_token: str | None,
) -> TestClient:
    app = FastAPI()
    settings = Settings(
        _env_file=None,
        internal_service_token=configured_token,
    )
    app.dependency_overrides[get_settings] = lambda: settings

    @app.get(
        "/internal",
        dependencies=[Depends(verify_internal_service_token)],
    )
    def internal_route() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(app)


def test_internal_service_auth_accepts_matching_token() -> None:
    client = create_test_client(configured_token=TEST_TOKEN)

    response = client.get(
        "/internal",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
    )

    assert response.status_code == 200


def test_internal_service_auth_rejects_missing_or_wrong_token() -> None:
    client = create_test_client(configured_token=TEST_TOKEN)

    assert client.get("/internal").status_code == 401
    assert (
        client.get(
            "/internal",
            headers={"X-Internal-Service-Token": "wrong-token"},
        ).status_code
        == 401
    )


def test_internal_service_auth_rejects_unconfigured_server() -> None:
    client = create_test_client(configured_token=None)

    response = client.get(
        "/internal",
        headers={"X-Internal-Service-Token": TEST_TOKEN},
    )

    assert response.status_code == 503
