import argparse
import asyncio
import json
from collections.abc import Sequence
from dataclasses import asdict
from math import ceil
from pathlib import Path
from statistics import mean
from time import perf_counter

from agent_service.core.config import Settings, get_settings
from agent_service.evaluation import (
    RetrievalEvaluationCase,
    evaluate_retrieval_case,
    load_retrieval_cases,
    summarize_retrieval_results,
)
from agent_service.rag import (
    KnowledgeRetriever,
    VectorStoreResources,
    create_cross_encoder_reranker,
    create_embedding_resources,
    create_vector_store_resources,
    ingest_catalog,
)

CASES_PATH = Path("data/evaluation/retrieval_cases.json")


def percentile(values: Sequence[float], percentile_value: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0 < percentile_value <= 1:
        raise ValueError("percentile_value must be in (0, 1]")

    ordered = sorted(values)
    index = max(ceil(percentile_value * len(ordered)) - 1, 0)
    return ordered[index]


async def evaluate_pipeline(
    *,
    name: str,
    retriever: KnowledgeRetriever,
    cases: list[RetrievalEvaluationCase],
    top_k: int,
    repetitions: int,
) -> dict[str, object]:
    if repetitions < 1:
        raise ValueError("repetitions must be at least 1")

    first_case_results = []
    case_reports: list[dict[str, object]] = []
    latencies_ms: list[float] = []

    # Exclude one-time model/session initialization from steady-state latency.
    warmup_case = next(case for case in cases if not case.expect_empty)
    await retriever.retrieve(
        question=warmup_case.question,
        tenant_id=warmup_case.tenant_id,
    )

    for repetition in range(repetitions):
        for case in cases:
            started = perf_counter()
            chunks = await retriever.retrieve(
                question=case.question,
                tenant_id=case.tenant_id,
            )
            elapsed_ms = (perf_counter() - started) * 1000
            latencies_ms.append(elapsed_ms)

            if repetition != 0:
                continue

            result = evaluate_retrieval_case(case, chunks)
            first_case_results.append(result)
            case_reports.append(
                {
                    **asdict(result),
                    "latency_ms": round(elapsed_ms, 3),
                    "ranking": [
                        {
                            "rank": rank,
                            "document_id": chunk.document.metadata.get(
                                "document_id"
                            ),
                            "section_title": chunk.document.metadata.get(
                                "section_title"
                            ),
                            "final_score": chunk.score,
                            "retrieval_score": chunk.retrieval_score,
                        }
                        for rank, chunk in enumerate(chunks, start=1)
                    ],
                }
            )

    summary = summarize_retrieval_results(
        first_case_results,
        top_k=top_k,
    )
    return {
        "name": name,
        "summary": asdict(summary),
        "latency_ms": {
            "sample_count": len(latencies_ms),
            "mean": round(mean(latencies_ms), 3),
            "p95": round(percentile(latencies_ms, 0.95), 3),
            "max": round(max(latencies_ms), 3),
        },
        "cases": case_reports,
    }


def reindex_all_catalogs(
    *,
    settings: Settings,
    resources: VectorStoreResources,
) -> list[dict[str, object]]:
    catalog_paths = sorted(
        settings.knowledge_base_directory.glob("*/catalog.json")
    )
    if not catalog_paths:
        raise RuntimeError(
            f"No knowledge catalogs found under {settings.knowledge_base_directory}"
        )

    reports = []
    for catalog_path in catalog_paths:
        result = ingest_catalog(
            catalog_path=catalog_path,
            settings=settings,
            resources=resources,
        )
        reports.append(
            {
                "catalog": str(catalog_path),
                **asdict(result),
            }
        )
    return reports


async def run_evaluation(
    *,
    repetitions: int,
    reindex: bool,
) -> dict[str, object]:
    settings = get_settings()
    if not settings.rag_enabled:
        raise RuntimeError("RAG is disabled")

    cases = load_retrieval_cases(CASES_PATH)
    embedding_resources = create_embedding_resources(settings)
    vector_store_resources = create_vector_store_resources(
        settings=settings,
        embeddings=embedding_resources,
    )
    reranker = create_cross_encoder_reranker(settings)
    if reranker is None:
        raise RuntimeError(
            "Reranker must be enabled for the retrieval comparison"
        )
    if vector_store_resources.dense_store is None:
        raise RuntimeError("Dense baseline store was not created")

    try:
        ingestion_reports = (
            reindex_all_catalogs(
                settings=settings,
                resources=vector_store_resources,
            )
            if reindex
            else []
        )

        dense_retriever = KnowledgeRetriever(
            store=vector_store_resources.dense_store,
            top_k=settings.rag_top_k,
        )
        hybrid_retriever = KnowledgeRetriever(
            store=vector_store_resources.store,
            top_k=settings.rag_top_k,
            candidate_k=settings.rag_candidate_k,
        )
        hybrid_rerank_retriever = KnowledgeRetriever(
            store=vector_store_resources.store,
            top_k=settings.rag_top_k,
            candidate_k=settings.rag_candidate_k,
            reranker=reranker,
        )

        dense_report = await evaluate_pipeline(
            name="dense",
            retriever=dense_retriever,
            cases=cases,
            top_k=settings.rag_top_k,
            repetitions=repetitions,
        )
        hybrid_report = await evaluate_pipeline(
            name="dense_bm25_rrf",
            retriever=hybrid_retriever,
            cases=cases,
            top_k=settings.rag_top_k,
            repetitions=repetitions,
        )
        final_report = await evaluate_pipeline(
            name="dense_bm25_rrf_cross_encoder",
            retriever=hybrid_rerank_retriever,
            cases=cases,
            top_k=settings.rag_top_k,
            repetitions=repetitions,
        )
    finally:
        vector_store_resources.client.close()

    dense_summary = dense_report["summary"]
    final_summary = final_report["summary"]
    assert isinstance(dense_summary, dict)
    assert isinstance(final_summary, dict)

    return {
        "configuration": {
            "collection": settings.qdrant_collection_name,
            "dense_embedding": settings.embedding_model_name,
            "sparse_embedding": settings.sparse_embedding_model_name,
            "fusion": "RRF",
            "reranker": settings.rag_reranker_model_name,
            "top_k": settings.rag_top_k,
            "candidate_k": settings.rag_candidate_k,
            "repetitions": repetitions,
        },
        "ingestion": ingestion_reports,
        "pipelines": [dense_report, hybrid_report, final_report],
        "baseline_to_final_delta": {
            "hit_at_k": (
                final_summary["hit_at_k"] - dense_summary["hit_at_k"]
            ),
            "mrr_at_k": (
                final_summary["mean_reciprocal_rank"]
                - dense_summary["mean_reciprocal_rank"]
            ),
            "ndcg_at_k": (
                final_summary["mean_ndcg"] - dense_summary["mean_ndcg"]
            ),
            "tenant_isolation_violations": final_summary[
                "tenant_isolation_violations"
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--reindex", action="store_true")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.repetitions < 1:
        parser.error("--repetitions must be at least 1")

    report = asyncio.run(
        run_evaluation(
            repetitions=arguments.repetitions,
            reindex=arguments.reindex,
        )
    )
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
