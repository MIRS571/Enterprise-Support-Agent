from dataclasses import dataclass
from typing import Literal, Protocol

import httpx
from pydantic import ValidationError

from agent_service.api.schemas.stream import StreamEventType
from agent_service.domain.intent import IntentType
from agent_service.evaluation.agent import AgentEvaluationCase
from agent_service.evaluation.live import (
    LiveAgentCaseResult,
    LiveAgentObservation,
    LiveEvaluationProtocolError,
    evaluate_live_agent_case,
)


class LiveAgentCaseRunner(Protocol):
    async def run_case(
        self,
        case: AgentEvaluationCase,
    ) -> LiveAgentObservation: ...


@dataclass(frozen=True)
class LiveAgentRunEvidence:
    intent: IntentType
    outcome: Literal["reply", "approval_required"]
    order_id: str | None
    source_document_ids: tuple[str, ...]
    event_types: tuple[StreamEventType, ...]
    matched_required_facts: tuple[str, ...]


@dataclass(frozen=True)
class LiveAgentRunRecord:
    case_id: str
    run_number: int
    result: LiveAgentCaseResult
    error_code: str | None = None
    evidence: LiveAgentRunEvidence | None = None


@dataclass(frozen=True)
class LiveAgentSuiteResult:
    planned_runs: int
    completed_runs: int
    aborted: bool
    abort_code: str | None
    runs: tuple[LiveAgentRunRecord, ...]

    def results_by_case(self) -> dict[str, list[LiveAgentCaseResult]]:
        grouped: dict[str, list[LiveAgentCaseResult]] = {}
        for run in self.runs:
            grouped.setdefault(run.case_id, []).append(run.result)
        return grouped


async def run_live_agent_suite(
    *,
    cases: list[AgentEvaluationCase],
    runner: LiveAgentCaseRunner,
    runs_per_case: int = 3,
) -> LiveAgentSuiteResult:
    if not cases:
        raise ValueError("live evaluation cases cannot be empty")
    if runs_per_case < 1:
        raise ValueError("runs_per_case must be at least 1")

    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("live evaluation case IDs must be unique")

    planned_runs = len(cases) * runs_per_case
    records: list[LiveAgentRunRecord] = []
    for run_number in range(1, runs_per_case + 1):
        for case in cases:
            try:
                observation = await runner.run_case(case)
                result = evaluate_live_agent_case(case, observation)
                record = LiveAgentRunRecord(
                    case_id=case.case_id,
                    run_number=run_number,
                    result=result,
                    evidence=_build_run_evidence(
                        case=case,
                        observation=observation,
                        result=result,
                    ),
                )
            except _EXPECTED_LIVE_FAILURES as error:
                abort, error_code = _classify_live_failure(error)
                record = LiveAgentRunRecord(
                    case_id=case.case_id,
                    run_number=run_number,
                    result=_failed_case_result(
                        case=case,
                        error_code=error_code,
                    ),
                    error_code=error_code,
                )
                records.append(record)
                if abort:
                    return LiveAgentSuiteResult(
                        planned_runs=planned_runs,
                        completed_runs=len(records),
                        aborted=True,
                        abort_code=error_code,
                        runs=tuple(records),
                    )
                continue

            records.append(record)

    return LiveAgentSuiteResult(
        planned_runs=planned_runs,
        completed_runs=len(records),
        aborted=False,
        abort_code=None,
        runs=tuple(records),
    )


_EXPECTED_LIVE_FAILURES = (
    LiveEvaluationProtocolError,
    ValidationError,
    httpx.HTTPError,
)


def _classify_live_failure(error: Exception) -> tuple[bool, str]:
    if isinstance(error, LiveEvaluationProtocolError):
        return False, "PUBLIC_PROTOCOL_ERROR"
    if isinstance(error, ValidationError):
        return False, "PUBLIC_PAYLOAD_INVALID"
    if isinstance(error, httpx.TimeoutException):
        return True, "SYSTEM_TIMEOUT"
    if isinstance(error, httpx.ConnectError):
        return True, "JAVA_UNREACHABLE"
    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code
        is_global = status_code in {401, 403, 429, 500, 502, 503}
        return is_global, f"HTTP_{status_code}"
    if isinstance(error, httpx.HTTPError):
        return False, "HTTP_TRANSPORT_ERROR"
    raise TypeError(f"unsupported live evaluation error: {type(error).__name__}")


def _failed_case_result(
    *,
    case: AgentEvaluationCase,
    error_code: str,
) -> LiveAgentCaseResult:
    return LiveAgentCaseResult(
        case_id=case.case_id,
        public_contract_passed=False,
        public_contract_failures=(f"run_error:{error_code}",),
        required_facts_passed=False,
        missing_required_facts=tuple(case.quality.required_facts),
    )


def _build_run_evidence(
    *,
    case: AgentEvaluationCase,
    observation: LiveAgentObservation,
    result: LiveAgentCaseResult,
) -> LiveAgentRunEvidence:
    missing = set(result.missing_required_facts)
    return LiveAgentRunEvidence(
        intent=observation.intent,
        outcome=observation.outcome,
        order_id=observation.order_id,
        source_document_ids=tuple(observation.source_document_ids),
        event_types=tuple(observation.event_types),
        matched_required_facts=tuple(
            fact for fact in case.quality.required_facts if fact not in missing
        ),
    )
