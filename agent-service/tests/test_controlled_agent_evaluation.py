import asyncio
from pathlib import Path

from agent_service.evaluation import (
    evaluate_agent_case,
    load_agent_evaluation_cases,
    run_controlled_agent_case,
    summarize_agent_results,
)


def test_all_controlled_agent_cases_pass_both_ci_gates() -> None:
    cases = load_agent_evaluation_cases(Path("data/evaluation/agent_cases.json"))

    observations = [asyncio.run(run_controlled_agent_case(case)) for case in cases]
    results = [
        evaluate_agent_case(case, observation)
        for case, observation in zip(cases, observations, strict=True)
    ]
    summary = summarize_agent_results(results)

    assert summary.total_cases == 7
    assert summary.deterministic_pass_rate == 1.0
    assert summary.required_facts_pass_rate == 1.0
    assert summary.quality_review_pending_cases == 7
