import asyncio
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from httpx import Headers
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import (
    ResponseHandlingException,
    UnexpectedResponse,
)
from qdrant_client.models import Distance, VectorParams

from agent_service.rag.reranking import CrossEncoderReranker
from agent_service.rag.retrieval import (
    KnowledgeRetriever,
    KnowledgeStoreUnavailableError,
    RagAvailability,
    RagAvailabilityStatus,
)


class KeywordEmbeddings(Embeddings):
    def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        if "退款" in text:
            return [1.0, 0.0, 0.0]
        if "物流" in text:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]


class FakeCrossEncoder:
    def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        batch_size: int,
    ) -> list[float]:
        assert query == "如何退款？"
        assert batch_size == 2
        return [0.1 if "通用" in document else 0.9 for document in documents]


def test_retrieve_filters_inside_qdrant_by_tenant() -> None:
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="knowledge",
        vectors_config=VectorParams(
            size=3,
            distance=Distance.COSINE,
        ),
    )
    store = QdrantVectorStore(
        client=client,
        collection_name="knowledge",
        embedding=KeywordEmbeddings(),
        validate_collection_config=False,
    )
    documents = [
        Document(
            page_content="企业一退款政策",
            metadata={"tenant_id": "company_001"},
        ),
        Document(
            page_content="企业二退款政策",
            metadata={"tenant_id": "company_002"},
        ),
        Document(
            page_content="企业一物流政策",
            metadata={"tenant_id": "company_001"},
        ),
    ]
    store.add_documents(
        documents=documents,
        ids=[str(uuid4()) for _ in documents],
    )
    retriever = KnowledgeRetriever(
        store=store,
        top_k=3,
        availability=RagAvailability(status=RagAvailabilityStatus.DOWN),
    )

    try:
        results = asyncio.run(
            retriever.retrieve(
                question="如何退款？",
                tenant_id="company_001",
            )
        )

        assert results
        assert all(
            result.document.metadata["tenant_id"] == "company_001" for result in results
        )
        assert results[0].document.page_content == "企业一退款政策"
        assert retriever._availability.status is RagAvailabilityStatus.UP
    finally:
        client.close()


@pytest.mark.parametrize(
    "source_error",
    [
        ResponseHandlingException(ConnectionError("Qdrant connection failed")),
        UnexpectedResponse(
            status_code=503,
            reason_phrase="Service Unavailable",
            content=b"unavailable",
            headers=Headers(),
        ),
    ],
)
def test_retrieve_marks_qdrant_failure_as_unavailable(
    source_error: Exception,
) -> None:
    store = Mock(spec=QdrantVectorStore)
    store.asimilarity_search_with_score = AsyncMock(side_effect=source_error)
    availability = RagAvailability(status=RagAvailabilityStatus.UP)
    retriever = KnowledgeRetriever(
        store=store,
        top_k=3,
        availability=availability,
    )

    with pytest.raises(KnowledgeStoreUnavailableError):
        asyncio.run(
            retriever.retrieve(
                question="如何退款？",
                tenant_id="company_001",
            )
        )

    assert availability.status is RagAvailabilityStatus.DOWN


def test_retrieve_does_not_hide_qdrant_authentication_error() -> None:
    authentication_error = UnexpectedResponse(
        status_code=401,
        reason_phrase="Unauthorized",
        content=b"invalid api key",
        headers=Headers(),
    )
    store = Mock(spec=QdrantVectorStore)
    store.asimilarity_search_with_score = AsyncMock(side_effect=authentication_error)
    availability = RagAvailability(status=RagAvailabilityStatus.UP)
    retriever = KnowledgeRetriever(
        store=store,
        top_k=3,
        availability=availability,
    )

    with pytest.raises(UnexpectedResponse) as captured:
        asyncio.run(
            retriever.retrieve(
                question="如何退款？",
                tenant_id="company_001",
            )
        )

    assert captured.value is authentication_error
    assert availability.status is RagAvailabilityStatus.UP


def test_retrieve_reranks_candidates_and_preserves_fusion_score() -> None:
    store = Mock(spec=QdrantVectorStore)
    store.asimilarity_search_with_score = AsyncMock(
        return_value=[
            (Document(page_content="通用退款规则"), 0.9),
            (Document(page_content="已拆封软件退款规则"), 0.7),
        ]
    )
    retriever = KnowledgeRetriever(
        store=store,
        top_k=1,
        candidate_k=2,
        reranker=CrossEncoderReranker(
            model=FakeCrossEncoder(),
            batch_size=2,
        ),
    )

    results = asyncio.run(
        retriever.retrieve(
            question="如何退款？",
            tenant_id="company_001",
        )
    )

    assert len(results) == 1
    assert results[0].document.page_content == "已拆封软件退款规则"
    assert results[0].score == 0.9
    assert results[0].retrieval_score == 0.7
    assert store.asimilarity_search_with_score.await_args.kwargs["k"] == 2
