from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_service.evaluation.agent import (
    AgentEvaluationCase,
    AgentEvaluationCaseResult,
)


class AgentStabilityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    runs_per_case: int = Field(default=3, ge=2)
    deterministic_min_rate: Literal[1.0] = 1.0
    standard_required_facts_min_rate: float = Field(
        default=2 / 3,
        gt=0,
        le=1,
    )
    critical_required_facts_min_rate: Literal[1.0] = 1.0
    overall_required_facts_min_rate: float = Field(
        default=0.9,
        gt=0,
        le=1,
    )


@dataclass(frozen=True)
class AgentCaseStabilityResult:
    case_id: str
    risk_level: Literal["standard", "critical"]
    total_runs: int
    deterministic_passed_runs: int
    deterministic_pass_rate: float
    required_facts_passed_runs: int
    required_facts_pass_rate: float
    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True)
class AgentStabilitySummary:
    total_cases: int
    total_runs: int
    deterministic_pass_rate: float
    required_facts_pass_rate: float
    critical_cases: int
    critical_passed_cases: int
    passed: bool
    failures: tuple[str, ...]
    cases: tuple[AgentCaseStabilityResult, ...]


def evaluate_agent_stability(
    *,
    cases: list[AgentEvaluationCase],
    repeated_results: dict[str, list[AgentEvaluationCaseResult]],
    policy: AgentStabilityPolicy | None = None,
) -> AgentStabilitySummary:
    active_policy = policy or AgentStabilityPolicy()
    if not cases:
        raise ValueError("stability evaluation cases cannot be empty")

    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("stability evaluation case IDs must be unique")
    if set(repeated_results) != set(case_ids):
        raise ValueError("repeated results must match evaluation case IDs")

    case_summaries = tuple(
        _evaluate_case_stability(
            case=case,
            results=repeated_results[case.case_id],
            policy=active_policy,
        )
        for case in cases
    )
    total_runs = sum(result.total_runs for result in case_summaries)
    deterministic_passed_runs = sum(
        result.deterministic_passed_runs for result in case_summaries
    )
    required_facts_passed_runs = sum(
        result.required_facts_passed_runs for result in case_summaries
    )
    deterministic_rate = deterministic_passed_runs / total_runs
    required_facts_rate = required_facts_passed_runs / total_runs
    critical_results = [
        result for result in case_summaries if result.risk_level == "critical"
    ]

    failures: list[str] = []
    failed_cases = [result.case_id for result in case_summaries if not result.passed]
    if failed_cases:
        failures.append(f"case stability failed: {failed_cases}")
    if required_facts_rate < active_policy.overall_required_facts_min_rate:
        failures.append(
            "overall required-facts rate is below "
            f"{active_policy.overall_required_facts_min_rate:.2%}"
        )

    return AgentStabilitySummary(
        total_cases=len(cases),
        total_runs=total_runs,
        deterministic_pass_rate=deterministic_rate,
        required_facts_pass_rate=required_facts_rate,
        critical_cases=len(critical_results),
        critical_passed_cases=sum(result.passed for result in critical_results),
        passed=not failures,
        failures=tuple(failures),
        cases=case_summaries,
    )


def _evaluate_case_stability(
    *,
    case: AgentEvaluationCase,
    results: list[AgentEvaluationCaseResult],
    policy: AgentStabilityPolicy,
) -> AgentCaseStabilityResult:
    if len(results) != policy.runs_per_case:
        raise ValueError(
            f"case {case.case_id} must have exactly {policy.runs_per_case} runs"
        )
    if any(result.case_id != case.case_id for result in results):
        raise ValueError(f"case {case.case_id} contains mismatched run results")

    deterministic_passed = sum(result.deterministic_passed for result in results)
    required_facts_passed = sum(result.required_facts_passed for result in results)
    deterministic_rate = deterministic_passed / len(results)
    required_facts_rate = required_facts_passed / len(results)
    facts_threshold = (
        policy.critical_required_facts_min_rate
        if case.risk_level == "critical"
        else policy.standard_required_facts_min_rate
    )

    failures: list[str] = []
    if deterministic_rate < policy.deterministic_min_rate:
        failures.append("deterministic contract must pass every run")
    if required_facts_rate < facts_threshold:
        failures.append(
            "required-facts rate is below "
            f"{facts_threshold:.2%} for {case.risk_level} risk"
        )

    return AgentCaseStabilityResult(
        case_id=case.case_id,
        risk_level=case.risk_level,
        total_runs=len(results),
        deterministic_passed_runs=deterministic_passed,
        deterministic_pass_rate=deterministic_rate,
        required_facts_passed_runs=required_facts_passed,
        required_facts_pass_rate=required_facts_rate,
        passed=not failures,
        failures=tuple(failures),
    )
