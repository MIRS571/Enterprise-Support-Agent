from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_service.api.schemas.stream import StreamEventType
from agent_service.domain.intent import IntentType
from agent_service.evaluation.agent import AgentEvaluationCase
from agent_service.evaluation.live_suite import (
    LiveAgentRunEvidence,
    LiveAgentSuiteResult,
)

LIVE_REPORT_SCHEMA_VERSION = "1.0"
LIVE_CI_SUCCESS = 0
LIVE_CI_FAILED = 1


class LiveAgentStabilityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    runs_per_case: int = Field(default=3, ge=2)
    public_contract_min_rate: Literal[1.0] = 1.0
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
class LiveCaseStabilityResult:
    case_id: str
    risk_level: Literal["standard", "critical"]
    total_runs: int
    public_contract_passed_runs: int
    public_contract_pass_rate: float
    required_facts_passed_runs: int
    required_facts_pass_rate: float
    passed: bool


@dataclass(frozen=True)
class LiveStabilitySummary:
    total_cases: int
    total_runs: int
    public_contract_pass_rate: float
    required_facts_pass_rate: float
    critical_cases: int
    critical_passed_cases: int
    passed: bool
    cases: tuple[LiveCaseStabilityResult, ...]


class LiveRunEvidenceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: IntentType
    outcome: Literal["reply", "approval_required"]
    order_id: str | None
    source_document_ids: list[str]
    event_types: list[StreamEventType]
    matched_required_facts: list[str]


class LiveRunReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    run_number: int = Field(ge=1)
    public_contract_passed: bool
    required_facts_passed: bool
    error_code: str | None = None
    evidence: LiveRunEvidenceReport | None = None


class LiveCaseStabilityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    risk_level: Literal["standard", "critical"]
    total_runs: int
    public_contract_passed_runs: int
    public_contract_pass_rate: float
    required_facts_passed_runs: int
    required_facts_pass_rate: float
    passed: bool


class LiveStabilityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_cases: int
    total_runs: int
    public_contract_pass_rate: float
    required_facts_pass_rate: float
    critical_cases: int
    critical_passed_cases: int
    passed: bool
    cases: list[LiveCaseStabilityReport]


class LiveAgentEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = LIVE_REPORT_SCHEMA_VERSION
    mode: Literal["live"] = "live"
    status: Literal["PASSED", "FAILED", "ABORTED"]
    generated_at: datetime
    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    planned_runs: int = Field(ge=1)
    completed_runs: int = Field(ge=1)
    abort_code: str | None = None
    ci_passed: bool
    stability: LiveStabilityReport | None
    runs: list[LiveRunReport] = Field(min_length=1)


def evaluate_live_agent_stability(
    *,
    cases: list[AgentEvaluationCase],
    suite: LiveAgentSuiteResult,
    policy: LiveAgentStabilityPolicy | None = None,
) -> LiveStabilitySummary:
    active_policy = policy or LiveAgentStabilityPolicy()
    if suite.aborted:
        raise ValueError("aborted live suite has no stability conclusion")
    expected_runs = len(cases) * active_policy.runs_per_case
    if suite.planned_runs != expected_runs or suite.completed_runs != expected_runs:
        raise ValueError("completed live suite does not contain every planned run")

    grouped = suite.results_by_case()
    case_ids = [case.case_id for case in cases]
    if set(grouped) != set(case_ids):
        raise ValueError("live suite results do not match evaluation cases")

    case_results = tuple(
        _evaluate_case_stability(
            case=case,
            results=grouped[case.case_id],
            policy=active_policy,
        )
        for case in cases
    )
    total_runs = sum(result.total_runs for result in case_results)
    contract_passed = sum(result.public_contract_passed_runs for result in case_results)
    facts_passed = sum(result.required_facts_passed_runs for result in case_results)
    facts_rate = facts_passed / total_runs
    critical = [result for result in case_results if result.risk_level == "critical"]
    cases_passed = all(result.passed for result in case_results)
    return LiveStabilitySummary(
        total_cases=len(cases),
        total_runs=total_runs,
        public_contract_pass_rate=contract_passed / total_runs,
        required_facts_pass_rate=facts_rate,
        critical_cases=len(critical),
        critical_passed_cases=sum(result.passed for result in critical),
        passed=(
            cases_passed and facts_rate >= active_policy.overall_required_facts_min_rate
        ),
        cases=case_results,
    )


def build_live_agent_evaluation_report(
    *,
    cases: list[AgentEvaluationCase],
    suite: LiveAgentSuiteResult,
    model_provider: str,
    model_name: str,
    generated_at: datetime | None = None,
    policy: LiveAgentStabilityPolicy | None = None,
) -> LiveAgentEvaluationReport:
    stability = None
    status: Literal["PASSED", "FAILED", "ABORTED"]
    if suite.aborted:
        status = "ABORTED"
    else:
        summary = evaluate_live_agent_stability(
            cases=cases,
            suite=suite,
            policy=policy,
        )
        stability = _stability_report(summary)
        status = "PASSED" if summary.passed else "FAILED"

    return LiveAgentEvaluationReport(
        status=status,
        generated_at=generated_at or datetime.now(UTC),
        model_provider=model_provider,
        model_name=model_name,
        planned_runs=suite.planned_runs,
        completed_runs=suite.completed_runs,
        abort_code=suite.abort_code,
        ci_passed=status == "PASSED",
        stability=stability,
        runs=[
            LiveRunReport(
                case_id=run.case_id,
                run_number=run.run_number,
                public_contract_passed=run.result.public_contract_passed,
                required_facts_passed=run.result.required_facts_passed,
                error_code=run.error_code,
                evidence=_evidence_report(run.evidence),
            )
            for run in suite.runs
        ],
    )


def live_agent_evaluation_exit_code(report: LiveAgentEvaluationReport) -> int:
    return LIVE_CI_SUCCESS if report.ci_passed else LIVE_CI_FAILED


def _evaluate_case_stability(
    *,
    case: AgentEvaluationCase,
    results,
    policy: LiveAgentStabilityPolicy,
) -> LiveCaseStabilityResult:
    if len(results) != policy.runs_per_case:
        raise ValueError(
            f"case {case.case_id} must have exactly {policy.runs_per_case} runs"
        )
    contract_passed = sum(result.public_contract_passed for result in results)
    facts_passed = sum(result.required_facts_passed for result in results)
    contract_rate = contract_passed / len(results)
    facts_rate = facts_passed / len(results)
    facts_threshold = (
        policy.critical_required_facts_min_rate
        if case.risk_level == "critical"
        else policy.standard_required_facts_min_rate
    )
    return LiveCaseStabilityResult(
        case_id=case.case_id,
        risk_level=case.risk_level,
        total_runs=len(results),
        public_contract_passed_runs=contract_passed,
        public_contract_pass_rate=contract_rate,
        required_facts_passed_runs=facts_passed,
        required_facts_pass_rate=facts_rate,
        passed=(
            contract_rate >= policy.public_contract_min_rate
            and facts_rate >= facts_threshold
        ),
    )


def _evidence_report(
    evidence: LiveAgentRunEvidence | None,
) -> LiveRunEvidenceReport | None:
    if evidence is None:
        return None
    return LiveRunEvidenceReport(
        intent=evidence.intent,
        outcome=evidence.outcome,
        order_id=evidence.order_id,
        source_document_ids=list(evidence.source_document_ids),
        event_types=list(evidence.event_types),
        matched_required_facts=list(evidence.matched_required_facts),
    )


def _stability_report(summary: LiveStabilitySummary) -> LiveStabilityReport:
    return LiveStabilityReport(
        total_cases=summary.total_cases,
        total_runs=summary.total_runs,
        public_contract_pass_rate=summary.public_contract_pass_rate,
        required_facts_pass_rate=summary.required_facts_pass_rate,
        critical_cases=summary.critical_cases,
        critical_passed_cases=summary.critical_passed_cases,
        passed=summary.passed,
        cases=[LiveCaseStabilityReport(**result.__dict__) for result in summary.cases],
    )
