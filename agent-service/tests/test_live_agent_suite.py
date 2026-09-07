import asyncio
from pathlib import Path

import httpx

from agent_service.api.schemas.stream import StreamEventType
from agent_service.evaluation import (
    LiveAgentObservation,
    LiveEvaluationProtocolError,
    load_agent_evaluation_cases,
    run_live_agent_suite,
)


def _passing_observation(case) -> LiveAgentObservation:
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
        answer=" ".join(case.quality.required_facts),
        event_types=[
            StreamEventType.METADATA,
            terminal,
            StreamEventType.DONE,
        ],
    )


class _PassingRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run_case(self, case):
        self.calls.append(case.case_id)
        return _passing_observation(case)


def test_live_suite_runs_seven_cases_in_three_rounds() -> None:
    cases = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))
    runner = _PassingRunner()

    result = asyncio.run(
        run_live_agent_suite(
            cases=cases,
            runner=runner,
        )
    )

    expected_round = [case.case_id for case in cases]
    assert runner.calls == expected_round * 3
    assert result.planned_runs == 21
    assert result.completed_runs == 21
    assert result.aborted is False
    assert all(run.result.public_contract_passed for run in result.runs)
    assert all(run.result.required_facts_passed for run in result.runs)
    assert all(len(runs) == 3 for runs in result.results_by_case().values())


def test_live_suite_records_one_case_failure_and_continues() -> None:
    cases = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))

    class Runner(_PassingRunner):
        async def run_case(self, case):
            self.calls.append(case.case_id)
            if len(self.calls) == 1:
                raise LiveEvaluationProtocolError("raw details are not persisted")
            return _passing_observation(case)

    runner = Runner()
    result = asyncio.run(run_live_agent_suite(cases=cases, runner=runner))

    assert result.aborted is False
    assert result.completed_runs == 21
    assert result.runs[0].error_code == "PUBLIC_PROTOCOL_ERROR"
    assert result.runs[0].result.public_contract_passed is False
    assert "raw details" not in repr(result)


def test_live_suite_aborts_when_java_is_unreachable() -> None:
    cases = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))

    class Runner(_PassingRunner):
        async def run_case(self, case):
            self.calls.append(case.case_id)
            raise httpx.ConnectError("private network details")

    runner = Runner()
    result = asyncio.run(run_live_agent_suite(cases=cases, runner=runner))

    assert result.aborted is True
    assert result.abort_code == "JAVA_UNREACHABLE"
    assert result.completed_runs == 1
    assert len(runner.calls) == 1
    assert "private network details" not in repr(result)
