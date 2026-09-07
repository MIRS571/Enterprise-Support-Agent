from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

from agent_service.domain.intent import IntentType


class KnowledgeReferenceState(TypedDict):
    reference_number: int
    document_id: str
    title: str
    section_title: str | None
    version: str


class ConversationMessageState(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class AgentState(TypedDict):
    message: str
    conversation_history: NotRequired[list[ConversationMessageState]]
    active_order_id: NotRequired[str | None]
    intent: NotRequired[IntentType | None]
    order_id: NotRequired[str | None]
    needs_clarification: NotRequired[bool]
    order_data: NotRequired[dict[str, object] | None]
    order_found: NotRequired[bool]
    refund_approved: NotRequired[bool | None]
    knowledge_context: NotRequired[str]
    knowledge_references: NotRequired[list[KnowledgeReferenceState]]
    knowledge_status: NotRequired[Literal["available", "no_match", "unavailable"]]
    answer: NotRequired[str]


@dataclass(frozen=True, slots=True)
class AgentContext:
    tenant_id: str
    user_id: str
    idempotency_key: str | None = None
