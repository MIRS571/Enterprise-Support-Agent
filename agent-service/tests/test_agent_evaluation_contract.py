import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_service.domain.intent import IntentType
from agent_service.evaluation import (
    AgentEvaluationObservation,
    ExpectedCallCounts,
    KnowledgeRetrievalObservation,
    OrderLookupObservation,
    evaluate_agent_case,
    load_agent_evaluation_cases,
    summarize_agent_results,
)


def test_load_agent_evaluation_cases() -> None:
    cases = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))

    assert len(cases) == 7
    assert cases[0].deterministic.intent is IntentType.ORDER_QUERY
    assert cases[2].deterministic.source_document_ids == ["refund-policy"]
    assert cases[4].deterministic.outcome == "approval_required"
    assert cases[4].risk_level == "critical"
    assert cases[5].user_id == "EVAL_U1001"


def test_rejects_overlapping_expected_and_forbidden_nodes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(
        json.dumps(
            [
                {
                    "case_id": "invalid",
                    "question": "测试",
                    "tenant_id": "company_001",
                    "user_id": "U1001",
                    "deterministic": {
                        "intent": "order_query",
                        "expected_nodes": ["query_order"],
                        "forbidden_nodes": ["query_order"],
                    },
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_agent_evaluation_cases(path)


def test_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    path = tmp_path / "duplicates.json"
    case = {
        "case_id": "duplicate",
        "question": "测试",
        "tenant_id": "company_001",
        "user_id": "U1001",
        "deterministic": {
            "intent": "other",
            "expected_nodes": ["unsupported"],
        },
    }
    path.write_text(
        json.dumps([case, case], ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="case_id values must be unique"):
        load_agent_evaluation_cases(path)


def test_evaluates_deterministic_order_evidence() -> None:
    case = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))[0]
    observation = AgentEvaluationObservation(
        case_id=case.case_id,
        intent=IntentType.ORDER_QUERY,
        outcome="reply",
        visited_nodes=[
            "analyze_intent",
            "query_order",
            "generate_answer",
            "save_turn",
        ],
        calls=ExpectedCallCounts(
            order_lookup=1,
            order_answer_generation=1,
        ),
        order_id="EVAL-A1001",
        answer="订单 EVAL-A1001 的订单状态为已发货。",
        order_lookups=[
            OrderLookupObservation(
                tenant_id="evaluation_001",
                user_id="EVAL_U1001",
                order_id="EVAL-A1001",
            )
        ],
    )

    result = evaluate_agent_case(case, observation)

    assert result.deterministic_passed is True
    assert result.deterministic_failures == ()
    assert result.required_facts_passed is True
    assert result.missing_required_facts == ()
    assert result.quality_review_required is True


def test_fails_wrong_route_and_untrusted_identity() -> None:
    case = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))[0]
    observation = AgentEvaluationObservation(
        case_id=case.case_id,
        intent=IntentType.ORDER_QUERY,
        outcome="reply",
        visited_nodes=[
            "analyze_intent",
            "query_order",
            "retrieve_knowledge",
            "generate_answer",
            "save_turn",
        ],
        calls=ExpectedCallCounts(
            order_lookup=1,
            knowledge_retrieval=1,
            order_answer_generation=1,
        ),
        order_id="EVAL-A1001",
        answer="订单 EVAL-A1001 已发货。",
        order_lookups=[
            OrderLookupObservation(
                tenant_id="evaluation_001",
                user_id="U9999",
                order_id="EVAL-A1001",
            )
        ],
        knowledge_retrievals=[
            KnowledgeRetrievalObservation(tenant_id="evaluation_001")
        ],
    )

    result = evaluate_agent_case(case, observation)

    assert result.deterministic_passed is False
    assert any("visited_nodes" in failure for failure in result.deterministic_failures)
    assert any(
        "forbidden_nodes" in failure for failure in result.deterministic_failures
    )
    assert any(
        "trusted tenant/user" in failure for failure in result.deterministic_failures
    )


def test_missing_quality_fact_does_not_fake_a_deterministic_failure() -> None:
    case = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))[3]
    observation = AgentEvaluationObservation(
        case_id=case.case_id,
        intent=IntentType.COMPLAINT,
        outcome="reply",
        visited_nodes=["analyze_intent", "unsupported", "save_turn"],
        calls=ExpectedCallCounts(),
        answer="该能力尚未开放。",
    )

    result = evaluate_agent_case(case, observation)

    assert result.deterministic_passed is True
    assert result.required_facts_passed is False
    assert result.missing_required_facts == ("目前",)
    assert result.quality_review_required is True


def test_summarizes_only_deterministic_pass_rate() -> None:
    case = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))[3]
    passing = evaluate_agent_case(
        case,
        AgentEvaluationObservation(
            case_id=case.case_id,
            intent=IntentType.COMPLAINT,
            outcome="reply",
            visited_nodes=["analyze_intent", "unsupported", "save_turn"],
            calls=ExpectedCallCounts(),
            answer="目前不支持投诉。",
        ),
    )
    failing = evaluate_agent_case(
        case,
        AgentEvaluationObservation(
            case_id=case.case_id,
            intent=IntentType.COMPLAINT,
            outcome="reply",
            visited_nodes=["analyze_intent", "query_order", "save_turn"],
            calls=ExpectedCallCounts(),
            answer="目前不支持投诉。",
        ),
    )

    summary = summarize_agent_results([passing, failing])

    assert summary.total_cases == 2
    assert summary.deterministic_passed_cases == 1
    assert summary.deterministic_pass_rate == 0.5
    assert summary.required_facts_passed_cases == 2
    assert summary.required_facts_pass_rate == 1.0
    assert summary.quality_review_pending_cases == 2
