from pathlib import Path

import pytest

from agent_service.evaluation import (
    AgentEvaluationCaseResult,
    evaluate_agent_stability,
    load_agent_evaluation_cases,
)


def _run_result(
    case_id: str,
    *,
    deterministic_passed: bool = True,
    required_facts_passed: bool = True,
) -> AgentEvaluationCaseResult:
    return AgentEvaluationCaseResult(
        case_id=case_id,
        deterministic_passed=deterministic_passed,
        deterministic_failures=(
            () if deterministic_passed else ("controlled failure",)
        ),
        required_facts_passed=required_facts_passed,
        missing_required_facts=(() if required_facts_passed else ("required fact",)),
        quality_review_required=True,
    )


def _all_passing_results(
    case_ids: list[str],
) -> dict[str, list[AgentEvaluationCaseResult]]:
    return {case_id: [_run_result(case_id) for _ in range(3)] for case_id in case_ids}


def test_three_stable_runs_pass() -> None:
    cases = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))
    results = _all_passing_results([case.case_id for case in cases])

    summary = evaluate_agent_stability(
        cases=cases,
        repeated_results=results,
    )

    assert summary.total_cases == 7
    assert summary.total_runs == 21
    assert summary.deterministic_pass_rate == 1.0
    assert summary.required_facts_pass_rate == 1.0
    assert summary.critical_cases == 3
    assert summary.critical_passed_cases == 3
    assert summary.passed is True


def test_one_critical_failure_fails_the_whole_baseline() -> None:
    cases = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))
    results = _all_passing_results([case.case_id for case in cases])
    critical_case_id = "refund-requires-approval"
    results[critical_case_id][2] = _run_result(
        critical_case_id,
        required_facts_passed=False,
    )

    summary = evaluate_agent_stability(
        cases=cases,
        repeated_results=results,
    )

    critical = next(
        result for result in summary.cases if result.case_id == critical_case_id
    )
    assert critical.required_facts_pass_rate == pytest.approx(2 / 3)
    assert critical.passed is False
    assert summary.critical_passed_cases == 2
    assert summary.passed is False


def test_one_standard_fact_miss_can_pass_the_stability_threshold() -> None:
    cases = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))
    results = _all_passing_results([case.case_id for case in cases])
    standard_case_id = "order-query-complete"
    results[standard_case_id][1] = _run_result(
        standard_case_id,
        required_facts_passed=False,
    )

    summary = evaluate_agent_stability(
        cases=cases,
        repeated_results=results,
    )

    standard = next(
        result for result in summary.cases if result.case_id == standard_case_id
    )
    assert standard.required_facts_pass_rate == pytest.approx(2 / 3)
    assert summary.required_facts_pass_rate == pytest.approx(20 / 21)
    assert standard.passed is True
    assert summary.passed is True


def test_any_deterministic_failure_fails_the_baseline() -> None:
    cases = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))
    results = _all_passing_results([case.case_id for case in cases])
    case_id = "order-query-complete"
    results[case_id][0] = _run_result(
        case_id,
        deterministic_passed=False,
    )

    summary = evaluate_agent_stability(
        cases=cases,
        repeated_results=results,
    )

    assert summary.deterministic_pass_rate == pytest.approx(20 / 21)
    assert summary.passed is False


def test_rejects_wrong_run_count() -> None:
    cases = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))
    results = _all_passing_results([case.case_id for case in cases])
    results[cases[0].case_id].pop()

    with pytest.raises(ValueError, match="exactly 3 runs"):
        evaluate_agent_stability(
            cases=cases,
            repeated_results=results,
        )
