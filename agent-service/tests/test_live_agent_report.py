import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx

from agent_service.api.schemas.stream import StreamEventType
from agent_service.evaluation import (
    LiveAgentObservation,
    build_live_agent_evaluation_report,
    live_agent_evaluation_exit_code,
    load_agent_evaluation_cases,
    run_live_agent_suite,
)


def _observation(case, *, answer_suffix: str = "") -> LiveAgentObservation:
    terminal = (
        StreamEventType.APPROVAL_REQUIRED
        if case.deterministic.outcome == "approval_required"
        else StreamEventType.RESULT
    )
    return LiveAgentObservation(
        case_id=case.case_id,
        outcome=case.deterministic.outcome,
        intent=case.deterministic.intent,
        order_id=case.deterministic.order_id,
        source_document_ids=case.deterministic.source_document_ids,
        answer=" ".join(case.quality.required_facts) + answer_suffix,
        event_types=[
            StreamEventType.METADATA,
            terminal,
            StreamEventType.DONE,
        ],
    )


def test_completed_live_report_is_stable_and_privacy_minimized() -> None:
    cases = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))

    class Runner:
        async def run_case(self, case):
            return _observation(case, answer_suffix=" SENSITIVE_FULL_ANSWER")

    suite = asyncio.run(run_live_agent_suite(cases=cases, runner=Runner()))
    report = build_live_agent_evaluation_report(
        cases=cases,
        suite=suite,
        model_provider="deepseek",
        model_name="deepseek-v4-flash",
        generated_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    payload = report.model_dump_json()

    assert report.status == "PASSED"
    assert report.ci_passed is True
    assert live_agent_evaluation_exit_code(report) == 0
    assert report.stability is not None
    assert report.stability.total_runs == 21
    assert report.stability.public_contract_pass_rate == 1.0
    assert report.stability.required_facts_pass_rate == 1.0
    assert len(report.runs) == 21
    assert "SENSITIVE_FULL_ANSWER" not in payload
    for case in cases:
        assert case.question not in payload
        assert case.tenant_id not in payload
        assert case.user_id not in payload


def test_aborted_report_has_no_stability_conclusion_and_fails_ci() -> None:
    cases = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))

    class Runner:
        def __init__(self) -> None:
            self.calls = 0

        async def run_case(self, case):
            self.calls += 1
            if self.calls == 5:
                raise httpx.ConnectError("private infrastructure detail")
            return _observation(case)

    suite = asyncio.run(run_live_agent_suite(cases=cases, runner=Runner()))
    report = build_live_agent_evaluation_report(
        cases=cases,
        suite=suite,
        model_provider="deepseek",
        model_name="deepseek-v4-flash",
    )
    payload = report.model_dump_json()

    assert report.status == "ABORTED"
    assert report.planned_runs == 21
    assert report.completed_runs == 5
    assert report.abort_code == "JAVA_UNREACHABLE"
    assert report.stability is None
    assert report.ci_passed is False
    assert live_agent_evaluation_exit_code(report) == 1
    assert "private infrastructure detail" not in payload


def test_one_critical_fact_miss_fails_completed_live_report() -> None:
    cases = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))

    class Runner:
        def __init__(self) -> None:
            self.no_context_runs = 0

        async def run_case(self, case):
            if case.case_id != "policy-no-context":
                return _observation(case)
            self.no_context_runs += 1
            if self.no_context_runs == 3:
                return _observation(case, answer_suffix="").model_copy(
                    update={"answer": "无法确认。"}
                )
            return _observation(case)

    suite = asyncio.run(run_live_agent_suite(cases=cases, runner=Runner()))
    report = build_live_agent_evaluation_report(
        cases=cases,
        suite=suite,
        model_provider="deepseek",
        model_name="deepseek-v4-flash",
    )

    assert report.status == "FAILED"
    assert report.stability is not None
    assert report.stability.critical_passed_cases == 2
    assert report.ci_passed is False
