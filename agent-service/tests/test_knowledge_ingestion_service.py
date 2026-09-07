from pathlib import Path
from typing import cast

import pytest

from agent_service.core.config import Settings
from agent_service.rag.ingestion import IngestionResult
from agent_service.rag.vector_store import VectorStoreResources
from agent_service.services import knowledge_ingestion as service_module
from agent_service.services.knowledge_ingestion import (
    InvalidTenantIdError,
    KnowledgeCatalogNotFoundError,
    KnowledgeIngestionService,
)


def create_service(
    knowledge_root: Path,
) -> KnowledgeIngestionService:
    return KnowledgeIngestionService(
        settings=Settings(
            _env_file=None,
            knowledge_base_directory=knowledge_root,
        ),
        resources=cast(VectorStoreResources, object()),
    )


def test_reindex_tenant_resolves_trusted_catalog_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    catalog_path = tmp_path / "company_001" / "catalog.json"
    catalog_path.parent.mkdir()
    catalog_path.write_text("{}", encoding="utf-8")
    captured_path: Path | None = None

    def fake_ingest_catalog(**kwargs) -> IngestionResult:
        nonlocal captured_path
        captured_path = kwargs["catalog_path"]
        return IngestionResult(document_count=2, chunk_count=9)

    monkeypatch.setattr(
        service_module,
        "ingest_catalog",
        fake_ingest_catalog,
    )

    result = create_service(tmp_path).reindex_tenant(tenant_id="company_001")

    assert captured_path == catalog_path.resolve()
    assert result == IngestionResult(document_count=2, chunk_count=9)


def test_reindex_tenant_rejects_path_traversal(
    tmp_path: Path,
) -> None:
    service = create_service(tmp_path)

    with pytest.raises(InvalidTenantIdError):
        service.reindex_tenant(tenant_id="../company_002")


def test_reindex_tenant_reports_missing_catalog(
    tmp_path: Path,
) -> None:
    service = create_service(tmp_path)

    with pytest.raises(KnowledgeCatalogNotFoundError):
        service.reindex_tenant(tenant_id="company_404")
