from dataclasses import dataclass

from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings

from agent_service.core.config import Settings


@dataclass(frozen=True)
class EmbeddingResources:
    model: Embeddings
    vector_size: int


def create_embedding_resources(settings: Settings) -> EmbeddingResources:
    model = HuggingFaceEmbeddings(
        model_name=settings.embedding_model_name,
        model_kwargs={
            "device": settings.embedding_device,
        },
        encode_kwargs={
            "normalize_embeddings": settings.embedding_normalize,
        },
    )

    probe_vector = model.embed_query("向量维度检测")

    if not probe_vector:
        raise RuntimeError("Embedding model returned an empty vector")

    return EmbeddingResources(
        model=model,
        vector_size=len(probe_vector),
    )
