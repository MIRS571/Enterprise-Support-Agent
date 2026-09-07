import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Modifier,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

from agent_service.rag.vector_store import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    CollectionConfigurationError,
    ensure_collection,
)


def test_ensure_collection_creates_missing_collection() -> None:
    client = QdrantClient(":memory:")

    try:
        ensure_collection(
            client=client,
            collection_name="knowledge",
            vector_size=384,
        )

        vectors = client.get_collection(
            collection_name="knowledge",
        ).config.params.vectors
        assert isinstance(vectors, dict)
        assert vectors[DENSE_VECTOR_NAME].size == 384
        assert vectors[DENSE_VECTOR_NAME].distance == Distance.COSINE
        sparse_vectors = client.get_collection(
            collection_name="knowledge",
        ).config.params.sparse_vectors
        assert sparse_vectors is not None
        assert sparse_vectors[SPARSE_VECTOR_NAME].modifier == Modifier.IDF
    finally:
        client.close()


def test_ensure_collection_accepts_compatible_collection() -> None:
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="knowledge",
        vectors_config={
            DENSE_VECTOR_NAME: VectorParams(
                size=384,
                distance=Distance.COSINE,
            )
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: SparseVectorParams(
                index=SparseIndexParams(on_disk=False),
                modifier=Modifier.IDF,
            )
        },
    )

    try:
        ensure_collection(
            client=client,
            collection_name="knowledge",
            vector_size=384,
        )
    finally:
        client.close()


def test_ensure_collection_rejects_size_mismatch_without_deleting() -> None:
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="knowledge",
        vectors_config={
            DENSE_VECTOR_NAME: VectorParams(
                size=768,
                distance=Distance.COSINE,
            )
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: SparseVectorParams(
                modifier=Modifier.IDF,
            )
        },
    )

    try:
        with pytest.raises(
            CollectionConfigurationError,
            match="768 dimensions",
        ):
            ensure_collection(
                client=client,
                collection_name="knowledge",
                vector_size=384,
            )

        assert client.collection_exists(
            collection_name="knowledge",
        )
    finally:
        client.close()
