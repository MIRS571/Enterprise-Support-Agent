import re

from agent_service.core.config import Settings
from agent_service.rag.ingestion import IngestionResult, ingest_catalog
from agent_service.rag.vector_store import VectorStoreResources

TENANT_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


class InvalidTenantIdError(ValueError):
    pass


class KnowledgeCatalogNotFoundError(FileNotFoundError):
    pass


class KnowledgeIngestionService:
    def __init__(
        self,
        *,
        settings: Settings,
        resources: VectorStoreResources,
    ) -> None:
        self._settings = settings
        self._resources = resources

    def reindex_tenant(
        self,
        *,
        tenant_id: str,
    ) -> IngestionResult:
        if TENANT_ID_PATTERN.fullmatch(tenant_id) is None:
            raise InvalidTenantIdError("tenant_id contains unsupported characters")

        knowledge_root = self._settings.knowledge_base_directory.resolve()
        catalog_path = (knowledge_root / tenant_id / "catalog.json").resolve()

        try:
            catalog_path.relative_to(knowledge_root)
        except ValueError as error:
            raise InvalidTenantIdError(
                "tenant_id resolves outside the knowledge directory"
            ) from error

        if not catalog_path.is_file():
            raise KnowledgeCatalogNotFoundError(
                f"Knowledge catalog was not found for tenant '{tenant_id}'"
            )

        return ingest_catalog(
            catalog_path=catalog_path,
            settings=self._settings,
            resources=self._resources,
        )
