from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_service.domain.intent import IntentType
from agent_service.evaluation.agent import (
    AgentEvaluationCase,
    AgentEvaluationCaseResult,
    AgentEvaluationObservation,
    AgentEvaluationSummary,
    AgentNodeName,
    ExpectedCallCounts,
    evaluate_agent_case,
    summarize_agent_results,
)

REPORT_SCHEMA_VERSION = "1.0"
CI_SUCCESS = 0
CI_EVALUATION_FAILED = 1


class AgentCaseEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: IntentType
    outcome: Literal["reply", "approval_required"]
    visited_nodes: list[AgentNodeName]
    calls: ExpectedCallCounts
    source_document_ids: list[str] = Field(default_factory=list)
    matched_required_facts: list[str] = Field(default_factory=list)


class AgentCaseReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    deterministic_passed: bool
    deterministic_failures: list[str]
    required_facts_passed: bool
    missing_required_facts: list[str]
    rubric_status: Literal["pending"] = "pending"
    evidence: AgentCaseEvidence


class AgentReportSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_cases: int = Field(ge=1)
    deterministic_passed_cases: int = Field(ge=0)
    deterministic_pass_rate: float = Field(ge=0, le=1)
    required_facts_passed_cases: int = Field(ge=0)
    required_facts_pass_rate: float = Field(ge=0, le=1)
    quality_review_pending_cases: int = Field(ge=0)
    ci_passed: bool


class AgentEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = REPORT_SCHEMA_VERSION
    mode: Literal["controlled", "live"]
    generated_at: datetime
    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    summary: AgentReportSummary
    cases: list[AgentCaseReport] = Field(min_length=1)


def build_agent_evaluation_report(
    *,
    cases: list[AgentEvaluationCase],
    observations: list[AgentEvaluationObservation],
    mode: Literal["controlled", "live"],
    model_provider: str,
    model_name: str,
    generated_at: datetime | None = None,
) -> AgentEvaluationReport:
    if len(cases) != len(observations):
        raise ValueError("cases and observations must have the same length")
    if not cases:
        raise ValueError("agent evaluation report cannot be empty")

    results: list[AgentEvaluationCaseResult] = []
    case_reports: list[AgentCaseReport] = []
    for case, observation in zip(cases, observations, strict=True):
        result = evaluate_agent_case(case, observation)
        results.append(result)
        case_reports.append(
            _build_case_report(
                case=case,
                observation=observation,
                result=result,
            )
        )

    summary = summarize_agent_results(results)
    ci_passed = _both_ci_gates_pass(summary)
    return AgentEvaluationReport(
        mode=mode,
        generated_at=generated_at or datetime.now(UTC),
        model_provider=model_provider,
        model_name=model_name,
        summary=AgentReportSummary(
            **summary.__dict__,
            ci_passed=ci_passed,
        ),
        cases=case_reports,
    )


def agent_evaluation_exit_code(report: AgentEvaluationReport) -> int:
    if report.summary.ci_passed:
        return CI_SUCCESS
    return CI_EVALUATION_FAILED


def _build_case_report(
    *,
    case: AgentEvaluationCase,
    observation: AgentEvaluationObservation,
    result: AgentEvaluationCaseResult,
) -> AgentCaseReport:
    missing = set(result.missing_required_facts)
    matched_facts = [
        fact for fact in case.quality.required_facts if fact not in missing
    ]
    return AgentCaseReport(
        case_id=case.case_id,
        deterministic_passed=result.deterministic_passed,
        deterministic_failures=list(result.deterministic_failures),
        required_facts_passed=result.required_facts_passed,
        missing_required_facts=list(result.missing_required_facts),
        evidence=AgentCaseEvidence(
            intent=observation.intent,
            outcome=observation.outcome,
            visited_nodes=observation.visited_nodes,
            calls=observation.calls,
            source_document_ids=observation.source_document_ids,
            matched_required_facts=matched_facts,
        ),
    )


def _both_ci_gates_pass(summary: AgentEvaluationSummary) -> bool:
    return (
        summary.deterministic_passed_cases == summary.total_cases
        and summary.required_facts_passed_cases == summary.total_cases
    )
