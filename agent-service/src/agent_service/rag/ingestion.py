from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from langchain_core.documents import Document
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
)

from agent_service.core.config import Settings
from agent_service.rag.documents import load_and_split_catalog
from agent_service.rag.vector_store import VectorStoreResources


@dataclass(frozen=True)
class IngestionResult:
    document_count: int
    chunk_count: int


def replace_document(
    *,
    resources: VectorStoreResources,
    collection_name: str,
    chunks: list[Document],
) -> None:
    if not chunks:
        raise ValueError("Cannot replace a document without chunks")

    tenant_ids = {str(chunk.metadata["tenant_id"]) for chunk in chunks}
    document_ids = {str(chunk.metadata["document_id"]) for chunk in chunks}

    if len(tenant_ids) != 1 or len(document_ids) != 1:
        raise ValueError("All chunks must belong to one tenant and one document")

    tenant_id = tenant_ids.pop()
    document_id = document_ids.pop()
    chunk_ids = [str(chunk.metadata["chunk_id"]) for chunk in chunks]

    resources.client.delete(
        collection_name=collection_name,
        points_selector=FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(
                        key="metadata.tenant_id",
                        match=MatchValue(value=tenant_id),
                    ),
                    FieldCondition(
                        key="metadata.document_id",
                        match=MatchValue(value=document_id),
                    ),
                ]
            )
        ),
        wait=True,
    )
    resources.store.add_documents(
        documents=chunks,
        ids=chunk_ids,
    )


def ingest_catalog(
    *,
    catalog_path: Path,
    settings: Settings,
    resources: VectorStoreResources,
) -> IngestionResult:
    chunks = load_and_split_catalog(
        catalog_path,
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
    )
    chunks_by_document: dict[tuple[str, str], list[Document]] = defaultdict(list)

    for chunk in chunks:
        key = (
            str(chunk.metadata["tenant_id"]),
            str(chunk.metadata["document_id"]),
        )
        chunks_by_document[key].append(chunk)

    for document_chunks in chunks_by_document.values():
        replace_document(
            resources=resources,
            collection_name=settings.qdrant_collection_name,
            chunks=document_chunks,
        )

    return IngestionResult(
        document_count=len(chunks_by_document),
        chunk_count=len(chunks),
    )
