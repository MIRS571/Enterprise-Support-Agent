from datetime import UTC, datetime
from pathlib import Path

from agent_service.domain.intent import IntentType
from agent_service.evaluation import (
    AgentEvaluationObservation,
    ExpectedCallCounts,
    OrderLookupObservation,
    agent_evaluation_exit_code,
    build_agent_evaluation_report,
    load_agent_evaluation_cases,
)


def _order_observation(*, answer: str) -> AgentEvaluationObservation:
    return AgentEvaluationObservation(
        case_id="order-query-complete",
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
        answer=answer,
        order_lookups=[
            OrderLookupObservation(
                tenant_id="evaluation_001",
                user_id="EVAL_U1001",
                order_id="EVAL-A1001",
            )
        ],
    )


def test_report_is_minimal_and_passes_both_ci_gates() -> None:
    case = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))[0]
    observation = _order_observation(
        answer="EVAL-A1001 的订单状态是已发货。敏感完整回答不应保存。"
    )

    report = build_agent_evaluation_report(
        cases=[case],
        observations=[observation],
        mode="controlled",
        model_provider="controlled",
        model_name="deterministic-dependencies-v1",
        generated_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    payload = report.model_dump_json()

    assert report.summary.ci_passed is True
    assert agent_evaluation_exit_code(report) == 0
    assert report.cases[0].evidence.matched_required_facts == [
        "EVAL-A1001",
        "已发货",
    ]
    assert case.question not in payload
    assert case.tenant_id not in payload
    assert case.user_id not in payload
    assert observation.answer not in payload
    assert "敏感完整回答不应保存" not in payload


def test_missing_required_fact_fails_second_ci_gate() -> None:
    case = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))[0]
    report = build_agent_evaluation_report(
        cases=[case],
        observations=[_order_observation(answer="只确认订单 EVAL-A1001。")],
        mode="controlled",
        model_provider="controlled",
        model_name="deterministic-dependencies-v1",
    )

    assert report.cases[0].deterministic_passed is True
    assert report.cases[0].required_facts_passed is False
    assert report.summary.ci_passed is False
    assert agent_evaluation_exit_code(report) == 1
