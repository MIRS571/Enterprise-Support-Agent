import argparse
import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

from agent_service.core.config import get_settings
from agent_service.evaluation import load_retrieval_cases
from agent_service.rag import (
    KnowledgeRetriever,
    RetrievedChunk,
    create_embedding_resources,
    create_vector_store_resources,
)

CASES_PATH = Path("data/evaluation/retrieval_cases.json")
RRF_CONSTANT = 60


@dataclass
class FusionCandidate:
    chunk: RetrievedChunk
    rrf_score: float = 0.0
    best_similarity_score: float = float("-inf")
    query_ranks: dict[str, int] = field(default_factory=dict)


def fuse_rankings(
    rankings: dict[str, list[RetrievedChunk]],
) -> list[FusionCandidate]:
    candidates: dict[str, FusionCandidate] = {}

    for query_name, chunks in rankings.items():
        for rank, chunk in enumerate(chunks, start=1):
            chunk_id = chunk.document.metadata.get("chunk_id")
            if not isinstance(chunk_id, str) or not chunk_id:
                raise ValueError("retrieved chunk is missing chunk_id")

            candidate = candidates.setdefault(
                chunk_id,
                FusionCandidate(chunk=chunk),
            )
            candidate.rrf_score += 1 / (RRF_CONSTANT + rank)
            candidate.best_similarity_score = max(
                candidate.best_similarity_score,
                chunk.score,
            )
            candidate.query_ranks[query_name] = rank

    return sorted(
        candidates.values(),
        key=lambda candidate: (
            candidate.rrf_score,
            candidate.best_similarity_score,
        ),
        reverse=True,
    )


def serialize_chunk(
    *,
    rank: int,
    chunk: RetrievedChunk,
) -> dict[str, object]:
    return {
        "rank": rank,
        "document_id": chunk.document.metadata.get("document_id"),
        "section_title": chunk.document.metadata.get("section_title"),
        "score": chunk.score,
        "content": chunk.document.page_content,
    }


async def inspect_case(
    *,
    case_id: str,
    limit: int,
    rewritten_question: str | None,
) -> dict[str, object]:
    cases = load_retrieval_cases(CASES_PATH)
    selected_case = next(
        (case for case in cases if case.case_id == case_id),
        None,
    )
    if selected_case is None:
        raise ValueError(f"Unknown evaluation case: {case_id}")

    settings = get_settings()
    embedding_resources = create_embedding_resources(settings)
    vector_store_resources = create_vector_store_resources(
        settings=settings,
        embeddings=embedding_resources,
    )
    retriever = KnowledgeRetriever(
        store=vector_store_resources.store,
        top_k=limit,
    )

    questions = {"original": selected_case.question}
    if rewritten_question is not None:
        cleaned_rewritten_question = rewritten_question.strip()
        if not cleaned_rewritten_question:
            raise ValueError("rewritten question cannot be blank")
        if cleaned_rewritten_question != selected_case.question:
            questions["rewritten"] = cleaned_rewritten_question

    rankings: dict[str, list[RetrievedChunk]] = {}
    try:
        for query_name, question in questions.items():
            rankings[query_name] = await retriever.retrieve(
                question=question,
                tenant_id=selected_case.tenant_id,
            )
    finally:
        vector_store_resources.client.close()

    fused_ranking = fuse_rankings(rankings)

    return {
        "case_id": selected_case.case_id,
        "questions": questions,
        "expected_sources": [
            source.model_dump()
            for source in selected_case.expected_sources
        ],
        "query_rankings": {
            query_name: [
                serialize_chunk(rank=rank, chunk=chunk)
                for rank, chunk in enumerate(chunks, start=1)
            ]
            for query_name, chunks in rankings.items()
        },
        "fused_ranking": [
            {
                "rank": rank,
                "document_id": candidate.chunk.document.metadata.get(
                    "document_id"
                ),
                "section_title": candidate.chunk.document.metadata.get(
                    "section_title"
                ),
                "rrf_score": candidate.rrf_score,
                "best_similarity_score": (
                    candidate.best_similarity_score
                ),
                "query_ranks": candidate.query_ranks,
                "content": candidate.chunk.document.page_content,
            }
            for rank, candidate in enumerate(fused_ranking, start=1)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_id")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--rewritten-question")
    arguments = parser.parse_args()
    if arguments.limit < 1:
        parser.error("--limit must be at least 1")

    report = asyncio.run(
        inspect_case(
            case_id=arguments.case_id,
            limit=arguments.limit,
            rewritten_question=arguments.rewritten_question,
        )
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
