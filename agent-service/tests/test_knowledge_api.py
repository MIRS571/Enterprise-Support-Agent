from unittest.mock import Mock

from fastapi.testclient import TestClient

from agent_service.api.dependencies import (
    get_knowledge_ingestion_service,
)
from agent_service.core.config import Settings, get_settings
from agent_service.main import app
from agent_service.rag.ingestion import IngestionResult
from agent_service.services import (
    KnowledgeCatalogNotFoundError,
    KnowledgeIngestionService,
)

TEST_TOKEN = "test-internal-service-token-1234567890"


def post_reindex(
    service: Mock,
    *,
    tenant_id: str,
) -> object:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        internal_service_token=TEST_TOKEN,
    )
    app.dependency_overrides[get_knowledge_ingestion_service] = lambda: service

    try:
        with TestClient(app) as client:
            return client.post(
                "/internal/v1/knowledge/reindex",
                headers={
                    "X-Internal-Service-Token": TEST_TOKEN,
                },
                json={"tenant_id": tenant_id},
            )
    finally:
        app.dependency_overrides.clear()


def test_reindex_knowledge_returns_counts() -> None:
    service = Mock(spec=KnowledgeIngestionService)
    service.reindex_tenant.return_value = IngestionResult(
        document_count=2,
        chunk_count=9,
    )

    response = post_reindex(
        service,
        tenant_id="company_001",
    )

    assert response.status_code == 200
    assert response.json() == {
        "tenant_id": "company_001",
        "document_count": 2,
        "chunk_count": 9,
    }


def test_reindex_knowledge_rejects_invalid_tenant_id() -> None:
    service = Mock(spec=KnowledgeIngestionService)

    response = post_reindex(
        service,
        tenant_id="../company_001",
    )

    assert response.status_code == 422
    service.reindex_tenant.assert_not_called()


def test_reindex_knowledge_returns_404_for_missing_catalog() -> None:
    service = Mock(spec=KnowledgeIngestionService)
    service.reindex_tenant.side_effect = KnowledgeCatalogNotFoundError("missing")

    response = post_reindex(
        service,
        tenant_id="company_404",
    )

    assert response.status_code == 404
