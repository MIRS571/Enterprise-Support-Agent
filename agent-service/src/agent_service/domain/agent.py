from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_service.domain.intent import IntentType
from agent_service.domain.order import OrderStatus


class KnowledgeSource(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    reference_number: int = Field(ge=1)
    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    section_title: str | None = None
    version: str = Field(min_length=1)


class AgentReply(BaseModel):
    answer: str
    intent: IntentType
    order_id: str | None = None
    sources: list[KnowledgeSource] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["request_refund"]
    order_id: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    total_amount: Decimal = Field(ge=0)
    status: OrderStatus


class AgentApprovalRequired(BaseModel):
    intent: Literal[IntentType.REFUND]
    order_id: str = Field(min_length=1)
    approval: ApprovalRequest


type AgentResult = AgentReply | AgentApprovalRequired


class AgentStreamToken(BaseModel):
    content: str = Field(min_length=1)


class AgentStreamCompleted(BaseModel):
    result: AgentResult


type AgentStreamEvent = AgentStreamToken | AgentStreamCompleted
