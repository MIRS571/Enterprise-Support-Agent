from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import (
    QdrantVectorStore,
    RetrievalMode,
    SparseEmbeddings,
    SparseVector,
)
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Modifier,
    SparseVectorParams,
    VectorParams,
)

from agent_service.rag.documents import build_chunk_id
from agent_service.rag.ingestion import replace_document
from agent_service.rag.vector_store import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    VectorStoreResources,
)


class FakeEmbeddings(Embeddings):
    def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        length = float(len(text))
        return [length, 1.0, 0.5]


class FakeSparseEmbeddings(SparseEmbeddings):
    def embed_documents(self, texts: list[str]) -> list[SparseVector]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> SparseVector:
        return SparseVector(indices=[0], values=[float(max(len(text), 1))])


def create_test_resources() -> VectorStoreResources:
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="knowledge",
        vectors_config={
            DENSE_VECTOR_NAME: VectorParams(
                size=3,
                distance=Distance.COSINE,
            )
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: SparseVectorParams(
                modifier=Modifier.IDF,
            )
        },
    )
    store = QdrantVectorStore(
        client=client,
        collection_name="knowledge",
        embedding=FakeEmbeddings(),
        sparse_embedding=FakeSparseEmbeddings(),
        retrieval_mode=RetrievalMode.HYBRID,
        vector_name=DENSE_VECTOR_NAME,
        sparse_vector_name=SPARSE_VECTOR_NAME,
        validate_collection_config=False,
    )
    return VectorStoreResources(
        client=client,
        store=store,
    )


def make_chunk(
    *,
    content: str,
    chunk_index: int,
) -> Document:
    return Document(
        page_content=content,
        metadata={
            "tenant_id": "company_001",
            "document_id": "refund-policy",
            "chunk_index": chunk_index,
            "chunk_id": build_chunk_id(
                tenant_id="company_001",
                document_id="refund-policy",
                chunk_index=chunk_index,
            ),
        },
    )


def test_replace_document_removes_all_old_chunks() -> None:
    resources = create_test_resources()
    old_chunks = [
        make_chunk(content="old-0", chunk_index=0),
        make_chunk(content="old-1", chunk_index=1),
    ]
    resources.store.add_documents(
        documents=old_chunks,
        ids=[chunk.metadata["chunk_id"] for chunk in old_chunks],
    )

    try:
        replace_document(
            resources=resources,
            collection_name="knowledge",
            chunks=[make_chunk(content="new-0", chunk_index=0)],
        )

        points, _ = resources.client.scroll(
            collection_name="knowledge",
            with_payload=True,
            with_vectors=False,
        )
        assert len(points) == 1
        assert points[0].payload is not None
        assert points[0].payload["page_content"] == "new-0"
    finally:
        resources.client.close()
