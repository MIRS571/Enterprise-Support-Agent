from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Self
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_service.api.schemas.chat import (
    ApprovalRequiredResponse,
    ChatResponse,
    ThreadCreateResponse,
)
from agent_service.api.schemas.stream import (
    StreamDone,
    StreamError,
    StreamEventType,
    StreamMetadata,
    StreamToken,
)
from agent_service.domain.intent import IntentType
from agent_service.evaluation.agent import AgentEvaluationCase


class LiveEvaluationProtocolError(RuntimeError):
    """The public Java/SSE response did not satisfy the evaluation contract."""


class LiveAgentObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    outcome: Literal["reply", "approval_required"]
    intent: IntentType
    order_id: str | None = None
    source_document_ids: list[str] = Field(default_factory=list)
    answer: str = ""
    event_types: list[StreamEventType] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_public_event_sequence(self) -> Self:
        if self.event_types[0] is not StreamEventType.METADATA:
            raise ValueError("live stream must start with metadata")
        if self.event_types.count(StreamEventType.METADATA) != 1:
            raise ValueError("live stream must contain exactly one metadata event")
        if self.event_types[-1] is not StreamEventType.DONE:
            raise ValueError("live stream must end with done")
        if self.event_types.count(StreamEventType.DONE) != 1:
            raise ValueError("live stream must contain exactly one done event")
        terminal = [
            event
            for event in self.event_types
            if event
            in {
                StreamEventType.RESULT,
                StreamEventType.APPROVAL_REQUIRED,
            }
        ]
        if len(terminal) != 1:
            raise ValueError("live stream must contain exactly one terminal result")
        if self.event_types[-2] is not terminal[0]:
            raise ValueError("terminal result must immediately precede done")
        return self


@dataclass(frozen=True)
class LiveAgentCaseResult:
    case_id: str
    public_contract_passed: bool
    public_contract_failures: tuple[str, ...]
    required_facts_passed: bool
    missing_required_facts: tuple[str, ...]


@dataclass(frozen=True)
class _RawSseEvent:
    event: StreamEventType
    data: str


class JavaAgentLiveClient:
    """Black-box evaluation client that talks only to the Java boundary."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def run_case(
        self,
        case: AgentEvaluationCase,
    ) -> LiveAgentObservation:
        thread_id = await self._create_thread(case)
        events = await self._stream_case(
            case=case,
            thread_id=thread_id,
        )
        return self._build_observation(
            case=case,
            thread_id=thread_id,
            events=events,
        )

    async def _create_thread(self, case: AgentEvaluationCase) -> UUID:
        response = await self._client.post(
            "/api/v1/agent/threads",
            headers=_identity_headers(case),
        )
        response.raise_for_status()
        if response.status_code != 201:
            raise LiveEvaluationProtocolError(
                f"thread creation must return 201, got {response.status_code}"
            )
        return ThreadCreateResponse.model_validate(response.json()).thread_id

    async def _stream_case(
        self,
        *,
        case: AgentEvaluationCase,
        thread_id: UUID,
    ) -> list[_RawSseEvent]:
        async with self._client.stream(
            "POST",
            "/api/v1/agent/chat/stream",
            headers=_identity_headers(case),
            json={
                "thread_id": str(thread_id),
                "message": case.question,
            },
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("text/event-stream"):
                raise LiveEvaluationProtocolError(
                    f"expected text/event-stream, got {content_type or 'missing'}"
                )
            return [event async for event in _iter_sse(response)]

    @staticmethod
    def _build_observation(
        *,
        case: AgentEvaluationCase,
        thread_id: UUID,
        events: list[_RawSseEvent],
    ) -> LiveAgentObservation:
        if not events:
            raise LiveEvaluationProtocolError("SSE stream returned no events")

        metadata: StreamMetadata | None = None
        result: ChatResponse | None = None
        approval: ApprovalRequiredResponse | None = None

        for raw_event in events:
            if raw_event.event is StreamEventType.ERROR:
                error = StreamError.model_validate_json(raw_event.data)
                raise LiveEvaluationProtocolError(
                    f"SSE error {error.code}: {error.message}"
                )
            if raw_event.event is StreamEventType.METADATA:
                metadata = StreamMetadata.model_validate_json(raw_event.data)
            elif raw_event.event is StreamEventType.TOKEN:
                StreamToken.model_validate_json(raw_event.data)
            elif raw_event.event is StreamEventType.RESULT:
                result = ChatResponse.model_validate_json(raw_event.data)
            elif raw_event.event is StreamEventType.APPROVAL_REQUIRED:
                approval = ApprovalRequiredResponse.model_validate_json(raw_event.data)
            elif raw_event.event is StreamEventType.DONE:
                StreamDone.model_validate_json(raw_event.data)

        expected_thread_id = str(thread_id)
        if metadata is None or metadata.thread_id != expected_thread_id:
            raise LiveEvaluationProtocolError("metadata thread_id does not match")
        if (result is None) == (approval is None):
            raise LiveEvaluationProtocolError(
                "stream must contain either result or approval_required"
            )

        terminal = result or approval
        if terminal is None or terminal.thread_id != expected_thread_id:
            raise LiveEvaluationProtocolError("terminal thread_id does not match")

        if result is not None:
            return LiveAgentObservation(
                case_id=case.case_id,
                outcome="reply",
                intent=result.intent,
                order_id=result.order_id,
                source_document_ids=list(
                    dict.fromkeys(source.document_id for source in result.sources)
                ),
                answer=result.answer,
                event_types=[event.event for event in events],
            )

        assert approval is not None
        return LiveAgentObservation(
            case_id=case.case_id,
            outcome="approval_required",
            intent=approval.intent,
            order_id=approval.order_id,
            event_types=[event.event for event in events],
        )


def evaluate_live_agent_case(
    case: AgentEvaluationCase,
    observation: LiveAgentObservation,
) -> LiveAgentCaseResult:
    """Evaluate only evidence observable through the public Java API."""

    failures: list[str] = []
    expected = case.deterministic
    if observation.case_id != case.case_id:
        failures.append("case_id does not match")
    if observation.intent is not expected.intent:
        failures.append(
            f"intent: expected {expected.intent.value}, got {observation.intent.value}"
        )
    if observation.outcome != expected.outcome:
        failures.append(
            f"outcome: expected {expected.outcome}, got {observation.outcome}"
        )
    if observation.order_id != expected.order_id:
        failures.append(
            f"order_id: expected {expected.order_id}, got {observation.order_id}"
        )
    if observation.source_document_ids != expected.source_document_ids:
        failures.append(
            "source_document_ids: expected "
            f"{expected.source_document_ids}, got {observation.source_document_ids}"
        )

    public_fact_evidence = "\n".join(
        [
            observation.answer,
            observation.order_id or "",
            *observation.source_document_ids,
        ]
    )
    missing_facts = tuple(
        fact for fact in case.quality.required_facts if fact not in public_fact_evidence
    )
    return LiveAgentCaseResult(
        case_id=case.case_id,
        public_contract_passed=not failures,
        public_contract_failures=tuple(failures),
        required_facts_passed=not missing_facts,
        missing_required_facts=missing_facts,
    )


def _identity_headers(case: AgentEvaluationCase) -> dict[str, str]:
    return {
        "X-Tenant-Id": case.tenant_id,
        "X-User-Id": case.user_id,
    }


async def _iter_sse(response: httpx.Response) -> AsyncIterator[_RawSseEvent]:
    event_name: str | None = None
    data_lines: list[str] = []

    async for line in response.aiter_lines():
        if line == "":
            if event_name is not None:
                yield _RawSseEvent(
                    event=StreamEventType(event_name),
                    data="\n".join(data_lines),
                )
            event_name = None
            data_lines = []
            continue
        if line.startswith(":"):
            continue

        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)

    if event_name is not None:
        yield _RawSseEvent(
            event=StreamEventType(event_name),
            data="\n".join(data_lines),
        )
