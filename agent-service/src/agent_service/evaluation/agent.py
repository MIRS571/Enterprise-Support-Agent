import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from agent_service.domain.intent import IntentType

type AgentNodeName = Literal[
    "analyze_intent",
    "request_clarification",
    "unsupported",
    "query_order",
    "order_not_found",
    "generate_answer",
    "request_refund_approval",
    "submit_refund",
    "retrieve_knowledge",
    "generate_knowledge_answer",
    "save_turn",
]


class ExpectedCallCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_analysis: int = Field(default=1, ge=0)
    order_lookup: int = Field(default=0, ge=0)
    knowledge_retrieval: int = Field(default=0, ge=0)
    order_answer_generation: int = Field(default=0, ge=0)
    knowledge_answer_generation: int = Field(default=0, ge=0)
    refund_submission: int = Field(default=0, ge=0)


class DeterministicExpectations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: IntentType
    outcome: Literal["reply", "approval_required"] = "reply"
    expected_nodes: list[AgentNodeName] = Field(min_length=1)
    forbidden_nodes: list[AgentNodeName] = Field(default_factory=list)
    calls: ExpectedCallCounts = Field(default_factory=ExpectedCallCounts)
    order_id: str | None = None
    source_document_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_nodes_and_outcome(self) -> Self:
        expected = set(self.expected_nodes)
        forbidden = set(self.forbidden_nodes)
        if len(expected) != len(self.expected_nodes):
            raise ValueError("expected_nodes cannot contain duplicates")
        if expected & forbidden:
            raise ValueError("expected_nodes and forbidden_nodes cannot overlap")
        if (
            self.outcome == "approval_required"
            and "request_refund_approval" not in expected
        ):
            raise ValueError("approval_required must expect request_refund_approval")
        if self.source_document_ids and "retrieve_knowledge" not in expected:
            raise ValueError("source expectations require retrieve_knowledge")
        return self


class AnswerQualityExpectations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_facts: list[str] = Field(default_factory=list)
    rubric: list[str] = Field(default_factory=list)


class AgentEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    risk_level: Literal["standard", "critical"] = "standard"
    question: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    deterministic: DeterministicExpectations
    quality: AnswerQualityExpectations = Field(
        default_factory=AnswerQualityExpectations
    )


class OrderLookupObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)


class KnowledgeRetrievalObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)


class AgentEvaluationObservation(BaseModel):
    """One controlled Agent execution captured by an evaluation runner."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    intent: IntentType
    outcome: Literal["reply", "approval_required"]
    visited_nodes: list[AgentNodeName]
    calls: ExpectedCallCounts
    order_id: str | None = None
    source_document_ids: list[str] = Field(default_factory=list)
    answer: str = ""
    order_lookups: list[OrderLookupObservation] = Field(default_factory=list)
    knowledge_retrievals: list[KnowledgeRetrievalObservation] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_call_evidence(self) -> Self:
        if self.calls.order_lookup != len(self.order_lookups):
            raise ValueError("order_lookup count does not match its evidence")
        if self.calls.knowledge_retrieval != len(self.knowledge_retrievals):
            raise ValueError("knowledge_retrieval count does not match its evidence")
        return self


@dataclass(frozen=True)
class AgentEvaluationCaseResult:
    case_id: str
    deterministic_passed: bool
    deterministic_failures: tuple[str, ...]
    required_facts_passed: bool
    missing_required_facts: tuple[str, ...]
    quality_review_required: bool


@dataclass(frozen=True)
class AgentEvaluationSummary:
    total_cases: int
    deterministic_passed_cases: int
    deterministic_pass_rate: float
    required_facts_passed_cases: int
    required_facts_pass_rate: float
    quality_review_pending_cases: int


def load_agent_evaluation_cases(path: Path) -> list[AgentEvaluationCase]:
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    cases = TypeAdapter(list[AgentEvaluationCase]).validate_python(raw_cases)
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("agent evaluation case_id values must be unique")
    return cases


def evaluate_agent_case(
    case: AgentEvaluationCase,
    observation: AgentEvaluationObservation,
) -> AgentEvaluationCaseResult:
    """Compare deterministic evidence without pretending to score prose."""

    failures: list[str] = []
    expected = case.deterministic

    if observation.case_id != case.case_id:
        failures.append(f"case_id: expected {case.case_id}, got {observation.case_id}")
    if observation.intent is not expected.intent:
        failures.append(
            f"intent: expected {expected.intent.value}, got {observation.intent.value}"
        )
    if observation.outcome != expected.outcome:
        failures.append(
            f"outcome: expected {expected.outcome}, got {observation.outcome}"
        )
    if observation.visited_nodes != expected.expected_nodes:
        failures.append(
            "visited_nodes: expected "
            f"{expected.expected_nodes}, got {observation.visited_nodes}"
        )

    forbidden_visited = sorted(
        set(observation.visited_nodes) & set(expected.forbidden_nodes)
    )
    if forbidden_visited:
        failures.append(f"forbidden_nodes visited: {forbidden_visited}")

    if observation.calls != expected.calls:
        failures.append(
            "calls: expected "
            f"{expected.calls.model_dump()}, got {observation.calls.model_dump()}"
        )
    if observation.order_id != expected.order_id:
        failures.append(
            f"order_id: expected {expected.order_id}, got {observation.order_id}"
        )
    if observation.source_document_ids != expected.source_document_ids:
        failures.append(
            "source_document_ids: expected "
            f"{expected.source_document_ids}, "
            f"got {observation.source_document_ids}"
        )

    for lookup in observation.order_lookups:
        if lookup.tenant_id != case.tenant_id or lookup.user_id != case.user_id:
            failures.append("order lookup did not use trusted tenant/user context")
            break
    for retrieval in observation.knowledge_retrievals:
        if retrieval.tenant_id != case.tenant_id:
            failures.append(
                "knowledge retrieval did not use the trusted tenant context"
            )
            break

    missing_required_facts = tuple(
        fact for fact in case.quality.required_facts if fact not in observation.answer
    )
    quality_review_required = bool(case.quality.required_facts or case.quality.rubric)

    return AgentEvaluationCaseResult(
        case_id=case.case_id,
        deterministic_passed=not failures,
        deterministic_failures=tuple(failures),
        required_facts_passed=not missing_required_facts,
        missing_required_facts=missing_required_facts,
        quality_review_required=quality_review_required,
    )


def summarize_agent_results(
    results: list[AgentEvaluationCaseResult],
) -> AgentEvaluationSummary:
    if not results:
        raise ValueError("agent evaluation results cannot be empty")

    passed = sum(result.deterministic_passed for result in results)
    facts_passed = sum(result.required_facts_passed for result in results)
    return AgentEvaluationSummary(
        total_cases=len(results),
        deterministic_passed_cases=passed,
        deterministic_pass_rate=passed / len(results),
        required_facts_passed_cases=facts_passed,
        required_facts_pass_rate=facts_passed / len(results),
        quality_review_pending_cases=sum(
            result.quality_review_required for result in results
        ),
    )
