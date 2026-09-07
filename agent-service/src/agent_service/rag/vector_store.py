from dataclasses import dataclass

from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Modifier,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

from agent_service.core.config import Settings
from agent_service.rag.embeddings import EmbeddingResources


class CollectionConfigurationError(RuntimeError):
    pass


DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"


@dataclass(frozen=True)
class VectorStoreResources:
    client: QdrantClient
    store: QdrantVectorStore
    dense_store: QdrantVectorStore | None = None


def ensure_collection(
    *,
    client: QdrantClient,
    collection_name: str,
    vector_size: int,
) -> None:
    if not client.collection_exists(collection_name=collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config={
                DENSE_VECTOR_NAME: VectorParams(
                    size=vector_size,
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
        return

    collection = client.get_collection(
        collection_name=collection_name,
    )
    vectors_config = collection.config.params.vectors

    if not isinstance(vectors_config, dict):
        raise CollectionConfigurationError(
            f"Qdrant collection '{collection_name}' uses the legacy unnamed "
            "dense-vector layout; create a new collection for hybrid retrieval"
        )

    dense_config = vectors_config.get(DENSE_VECTOR_NAME)
    if dense_config is None:
        raise CollectionConfigurationError(
            f"Qdrant collection '{collection_name}' does not contain the "
            f"named dense vector '{DENSE_VECTOR_NAME}'"
        )

    if dense_config.size != vector_size:
        raise CollectionConfigurationError(
            f"Qdrant collection '{collection_name}' uses "
            f"{dense_config.size} dimensions, but the configured "
            f"embedding model produces {vector_size} dimensions"
        )

    if dense_config.distance != Distance.COSINE:
        raise CollectionConfigurationError(
            f"Qdrant collection '{collection_name}' uses "
            f"{dense_config.distance}, but {Distance.COSINE} is required"
        )

    sparse_vectors_config = collection.config.params.sparse_vectors or {}
    sparse_config = sparse_vectors_config.get(SPARSE_VECTOR_NAME)
    if sparse_config is None:
        raise CollectionConfigurationError(
            f"Qdrant collection '{collection_name}' does not contain the "
            f"named sparse vector '{SPARSE_VECTOR_NAME}'"
        )
    if sparse_config.modifier != Modifier.IDF:
        raise CollectionConfigurationError(
            f"Qdrant collection '{collection_name}' must enable the IDF "
            "modifier for BM25"
        )


def create_vector_store_resources(
    *,
    settings: Settings,
    embeddings: EmbeddingResources,
) -> VectorStoreResources:
    api_key = (
        settings.qdrant_api_key.get_secret_value()
        if settings.qdrant_api_key is not None
        else None
    )
    client = QdrantClient(
        url=str(settings.qdrant_url),
        api_key=api_key,
        trust_env=False,
    )

    try:
        sparse_embeddings = FastEmbedSparse(
            model_name=settings.sparse_embedding_model_name,
        )
        ensure_collection(
            client=client,
            collection_name=settings.qdrant_collection_name,
            vector_size=embeddings.vector_size,
        )
        store = QdrantVectorStore(
            client=client,
            collection_name=settings.qdrant_collection_name,
            embedding=embeddings.model,
            sparse_embedding=sparse_embeddings,
            retrieval_mode=RetrievalMode.HYBRID,
            vector_name=DENSE_VECTOR_NAME,
            sparse_vector_name=SPARSE_VECTOR_NAME,
            distance=Distance.COSINE,
            validate_collection_config=False,
        )
        dense_store = QdrantVectorStore(
            client=client,
            collection_name=settings.qdrant_collection_name,
            embedding=embeddings.model,
            retrieval_mode=RetrievalMode.DENSE,
            vector_name=DENSE_VECTOR_NAME,
            distance=Distance.COSINE,
            validate_collection_config=False,
        )
    except Exception:
        client.close()
        raise

    return VectorStoreResources(
        client=client,
        store=store,
        dense_store=dense_store,
    )
