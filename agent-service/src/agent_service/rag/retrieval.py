from dataclasses import dataclass
from enum import StrEnum

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client.http.exceptions import (
    ResponseHandlingException,
    UnexpectedResponse,
)
from qdrant_client.models import FieldCondition, Filter, MatchValue

from agent_service.rag.reranking import CrossEncoderReranker


class RagAvailabilityStatus(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    DISABLED = "DISABLED"


@dataclass
class RagAvailability:
    status: RagAvailabilityStatus

    def mark_up(self) -> None:
        self.status = RagAvailabilityStatus.UP

    def mark_down(self) -> None:
        self.status = RagAvailabilityStatus.DOWN


class KnowledgeStoreUnavailableError(RuntimeError):
    pass


def is_knowledge_store_unavailable_error(
    error: Exception,
) -> bool:
    if isinstance(error, ResponseHandlingException):
        return True

    return (
        isinstance(error, UnexpectedResponse)
        and error.status_code is not None
        and error.status_code >= 500
    )


@dataclass(frozen=True)
class RetrievedChunk:
    document: Document
    score: float
    retrieval_score: float | None = None


class KnowledgeRetriever:
    def __init__(
        self,
        *,
        store: QdrantVectorStore,
        top_k: int,
        candidate_k: int | None = None,
        reranker: CrossEncoderReranker | None = None,
        availability: RagAvailability | None = None,
    ) -> None:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        resolved_candidate_k = candidate_k or top_k
        if resolved_candidate_k < top_k:
            raise ValueError("candidate_k must be at least top_k")

        self._store = store
        self._top_k = top_k
        self._candidate_k = resolved_candidate_k
        self._reranker = reranker
        self._availability = availability or RagAvailability(
            status=RagAvailabilityStatus.UP
        )

    async def retrieve(
        self,
        *,
        question: str,
        tenant_id: str,
    ) -> list[RetrievedChunk]:
        cleaned_question = question.strip()
        cleaned_tenant_id = tenant_id.strip()
        if not cleaned_question:
            raise ValueError("question cannot be blank")
        if not cleaned_tenant_id:
            raise ValueError("tenant_id cannot be blank")

        try:
            results = await self._store.asimilarity_search_with_score(
                query=cleaned_question,
                k=self._candidate_k,
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="metadata.tenant_id",
                            match=MatchValue(
                                value=cleaned_tenant_id,
                            ),
                        )
                    ]
                ),
            )
        except (ResponseHandlingException, UnexpectedResponse) as error:
            if not is_knowledge_store_unavailable_error(error):
                raise
            self._availability.mark_down()
            raise KnowledgeStoreUnavailableError(
                "knowledge store is unavailable"
            ) from error

        self._availability.mark_up()

        candidates = [
            RetrievedChunk(
                document=document,
                score=score,
            )
            for document, score in results
        ]

        if self._reranker is None or not candidates:
            return candidates[: self._top_k]

        rerank_scores = await self._reranker.score(
            question=cleaned_question,
            documents=[candidate.document.page_content for candidate in candidates],
        )
        reranked = [
            RetrievedChunk(
                document=candidate.document,
                score=rerank_score,
                retrieval_score=candidate.score,
            )
            for candidate, rerank_score in zip(
                candidates,
                rerank_scores,
                strict=True,
            )
        ]
        reranked.sort(key=lambda chunk: chunk.score, reverse=True)
        return reranked[: self._top_k]
