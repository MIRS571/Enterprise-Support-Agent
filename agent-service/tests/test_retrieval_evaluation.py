from math import log2
from pathlib import Path

from langchain_core.documents import Document

from agent_service.evaluation import (
    ExpectedSource,
    RetrievalCaseResult,
    RetrievalEvaluationCase,
    evaluate_retrieval_case,
    load_retrieval_cases,
    summarize_retrieval_results,
)
from agent_service.rag.retrieval import RetrievedChunk


def make_chunk(
    *,
    tenant_id: str = "company_001",
    document_id: str = "refund-policy",
    section_title: str = "未发货订单",
    content: str = "可以直接申请取消。",
    score: float = 0.9,
) -> RetrievedChunk:
    return RetrievedChunk(
        document=Document(
            page_content=content,
            metadata={
                "tenant_id": tenant_id,
                "document_id": document_id,
                "section_title": section_title,
            },
        ),
        score=score,
    )


def test_load_retrieval_cases() -> None:
    path = Path("data/evaluation/retrieval_cases.json")

    cases = load_retrieval_cases(path)

    assert len(cases) == 30
    assert cases[0].case_id == "refund-unshipped-cancel"
    assert cases[-1].expect_empty is True


def test_evaluate_case_records_rank_and_score() -> None:
    case = RetrievalEvaluationCase(
        case_id="rank-two",
        question="未发货怎么退款？",
        tenant_id="company_001",
        expected_sources=[
            ExpectedSource(
                document_id="refund-policy",
                section_title="未发货订单",
                required_keywords=["直接申请取消"],
            )
        ],
    )
    chunks = [
        make_chunk(
            document_id="shipping-policy",
            section_title="物流轨迹",
            content="物流信息。",
            score=0.95,
        ),
        make_chunk(score=0.82),
    ]

    result = evaluate_retrieval_case(case, chunks)

    assert result.passed is True
    assert result.first_relevant_rank == 2
    assert result.reciprocal_rank == 0.5
    assert result.first_relevant_score == 0.82
    assert result.relevant_ranks == (2,)
    assert result.ndcg_at_k == 1 / log2(3)


def test_evaluate_case_detects_tenant_leakage() -> None:
    case = RetrievalEvaluationCase(
        case_id="tenant-isolation",
        question="如何退款？",
        tenant_id="company_001",
        expected_sources=[ExpectedSource(document_id="refund-policy")],
    )

    result = evaluate_retrieval_case(
        case,
        [make_chunk(tenant_id="company_002")],
    )

    assert result.passed is False
    assert result.tenant_isolation_violations == 1


def test_summarize_retrieval_results() -> None:
    results = [
        RetrievalCaseResult(
            case_id="top-one",
            passed=True,
            expect_empty=False,
            returned_count=3,
            first_relevant_rank=1,
            reciprocal_rank=1.0,
            first_relevant_score=0.9,
            tenant_isolation_violations=0,
            relevant_ranks=(1,),
            ndcg_at_k=1.0,
        ),
        RetrievalCaseResult(
            case_id="top-two",
            passed=True,
            expect_empty=False,
            returned_count=3,
            first_relevant_rank=2,
            reciprocal_rank=0.5,
            first_relevant_score=0.8,
            tenant_isolation_violations=0,
            relevant_ranks=(2,),
            ndcg_at_k=1 / log2(3),
        ),
        RetrievalCaseResult(
            case_id="empty",
            passed=True,
            expect_empty=True,
            returned_count=0,
            first_relevant_rank=None,
            reciprocal_rank=None,
            first_relevant_score=None,
            tenant_isolation_violations=0,
        ),
    ]

    summary = summarize_retrieval_results(results, top_k=3)

    assert summary.total_cases == 3
    assert summary.pass_rate == 1.0
    assert summary.hit_at_k == 1.0
    assert summary.mean_reciprocal_rank == 0.75
    assert summary.mean_ndcg == (1 + 1 / log2(3)) / 2
    assert summary.empty_result_accuracy == 1.0
