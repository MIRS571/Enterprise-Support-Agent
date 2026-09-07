import json
from dataclasses import dataclass
from math import log2
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from agent_service.rag.retrieval import RetrievedChunk


class ExpectedSource(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    document_id: str = Field(min_length=1)
    section_title: str | None = None
    required_keywords: list[str] = Field(default_factory=list)


class RetrievalEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    expected_sources: list[ExpectedSource] = Field(default_factory=list)
    expect_empty: bool = False

    @model_validator(mode="after")
    def validate_expectation(self) -> Self:
        if self.expect_empty == bool(self.expected_sources):
            raise ValueError(
                "exactly one of expect_empty or expected_sources is required"
            )
        return self


@dataclass(frozen=True)
class RetrievalCaseResult:
    case_id: str
    passed: bool
    expect_empty: bool
    returned_count: int
    first_relevant_rank: int | None
    reciprocal_rank: float | None
    first_relevant_score: float | None
    tenant_isolation_violations: int
    relevant_ranks: tuple[int, ...] = ()
    ndcg_at_k: float | None = None


@dataclass(frozen=True)
class RetrievalEvaluationSummary:
    top_k: int
    total_cases: int
    pass_rate: float
    positive_cases: int
    hit_at_k: float
    mean_reciprocal_rank: float
    mean_ndcg: float
    empty_cases: int
    empty_result_accuracy: float
    tenant_isolation_violations: int


def load_retrieval_cases(path: Path) -> list[RetrievalEvaluationCase]:
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    return TypeAdapter(list[RetrievalEvaluationCase]).validate_python(raw_cases)


def matches_expected_source(
    chunk: RetrievedChunk,
    expected: ExpectedSource,
) -> bool:
    metadata = chunk.document.metadata
    if metadata.get("document_id") != expected.document_id:
        return False
    if (
        expected.section_title is not None
        and metadata.get("section_title") != expected.section_title
    ):
        return False
    return all(
        keyword in chunk.document.page_content for keyword in expected.required_keywords
    )


def evaluate_retrieval_case(
    case: RetrievalEvaluationCase,
    chunks: list[RetrievedChunk],
) -> RetrievalCaseResult:
    isolation_violations = sum(
        chunk.document.metadata.get("tenant_id") != case.tenant_id for chunk in chunks
    )

    relevant_ranks: list[int] = []
    matched_expected_indexes: set[int] = set()
    first_rank: int | None = None
    first_score: float | None = None
    if not case.expect_empty:
        for rank, chunk in enumerate(chunks, start=1):
            for expected_index, expected in enumerate(case.expected_sources):
                if expected_index in matched_expected_indexes:
                    continue
                if matches_expected_source(chunk, expected):
                    matched_expected_indexes.add(expected_index)
                    relevant_ranks.append(rank)
                    if first_rank is None:
                        first_rank = rank
                        first_score = chunk.score
                    break

    if case.expect_empty:
        passed = not chunks and isolation_violations == 0
        reciprocal_rank = None
        ndcg_at_k = None
    else:
        passed = first_rank is not None and isolation_violations == 0
        reciprocal_rank = 1 / first_rank if first_rank is not None else 0.0
        dcg = sum(1 / log2(rank + 1) for rank in relevant_ranks)
        ideal_relevant_count = min(len(case.expected_sources), len(chunks))
        ideal_dcg = sum(
            1 / log2(rank + 1)
            for rank in range(1, ideal_relevant_count + 1)
        )
        ndcg_at_k = dcg / ideal_dcg if ideal_dcg else 0.0

    return RetrievalCaseResult(
        case_id=case.case_id,
        passed=passed,
        expect_empty=case.expect_empty,
        returned_count=len(chunks),
        first_relevant_rank=first_rank,
        reciprocal_rank=reciprocal_rank,
        first_relevant_score=first_score,
        tenant_isolation_violations=isolation_violations,
        relevant_ranks=tuple(relevant_ranks),
        ndcg_at_k=ndcg_at_k,
    )


def summarize_retrieval_results(
    results: list[RetrievalCaseResult],
    *,
    top_k: int,
) -> RetrievalEvaluationSummary:
    if not results:
        raise ValueError("retrieval evaluation results cannot be empty")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    positive_results = [result for result in results if not result.expect_empty]
    empty_results = [result for result in results if result.expect_empty]
    positive_count = len(positive_results)
    empty_count = len(empty_results)

    hit_at_k = (
        sum(
            result.first_relevant_rank is not None
            and result.first_relevant_rank <= top_k
            for result in positive_results
        )
        / positive_count
        if positive_count
        else 0.0
    )
    mean_reciprocal_rank = (
        sum(
            result.reciprocal_rank or 0.0
            if result.first_relevant_rank is not None
            and result.first_relevant_rank <= top_k
            else 0.0
            for result in positive_results
        )
        / positive_count
        if positive_count
        else 0.0
    )
    mean_ndcg = (
        sum(result.ndcg_at_k or 0.0 for result in positive_results)
        / positive_count
        if positive_count
        else 0.0
    )
    empty_result_accuracy = (
        sum(result.passed for result in empty_results) / empty_count
        if empty_count
        else 0.0
    )

    return RetrievalEvaluationSummary(
        top_k=top_k,
        total_cases=len(results),
        pass_rate=sum(result.passed for result in results) / len(results),
        positive_cases=positive_count,
        hit_at_k=hit_at_k,
        mean_reciprocal_rank=mean_reciprocal_rank,
        mean_ndcg=mean_ndcg,
        empty_cases=empty_count,
        empty_result_accuracy=empty_result_accuracy,
        tenant_isolation_violations=sum(
            result.tenant_isolation_violations for result in results
        ),
    )
