from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from agent_service.domain.agent import (
    AgentApprovalRequired,
    AgentReply,
    AgentResult,
    ApprovalRequest,
    KnowledgeSource,
)
from agent_service.domain.intent import IntentType
from agent_service.domain.order import OrderStatus


class ChatRequest(BaseModel):
    thread_id: str = Field(max_length=128)
    message: str = Field(max_length=4000)

    @field_validator("thread_id", "message")
    @classmethod
    def validate_not_blank(cls, value: str) -> str:
        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("字段不能只包含空格")
        return cleaned_value


class ThreadCreateResponse(BaseModel):
    thread_id: UUID


class ApprovalDecisionRequest(BaseModel):
    approved: bool


class ApprovalDetails(BaseModel):
    operation: Literal["request_refund"]
    order_id: str
    product_name: str
    total_amount: Decimal
    status: OrderStatus

    @classmethod
    def from_approval(
        cls,
        approval: ApprovalRequest,
    ) -> "ApprovalDetails":
        return cls(**approval.model_dump())


class ChatSource(BaseModel):
    reference_number: int
    document_id: str
    title: str
    section_title: str | None
    version: str

    @classmethod
    def from_source(
        cls,
        source: KnowledgeSource,
    ) -> "ChatSource":
        return cls(
            reference_number=source.reference_number,
            document_id=source.document_id,
            title=source.title,
            section_title=source.section_title,
            version=source.version,
        )


class ChatResponse(BaseModel):
    thread_id: str
    answer: str
    intent: IntentType
    order_id: str | None = None
    sources: list[ChatSource] = Field(default_factory=list)

    @classmethod
    def from_reply(
        cls,
        *,
        thread_id: str,
        reply: AgentReply,
    ) -> "ChatResponse":
        return cls(
            thread_id=thread_id,
            answer=reply.answer,
            intent=reply.intent,
            order_id=reply.order_id,
            sources=[ChatSource.from_source(source) for source in reply.sources],
        )


class ApprovalRequiredResponse(BaseModel):
    thread_id: str
    status: Literal["approval_required"] = "approval_required"
    intent: Literal[IntentType.REFUND]
    order_id: str
    approval: ApprovalDetails

    @classmethod
    def from_result(
        cls,
        *,
        thread_id: str,
        result: AgentApprovalRequired,
    ) -> "ApprovalRequiredResponse":
        return cls(
            thread_id=thread_id,
            intent=result.intent,
            order_id=result.order_id,
            approval=ApprovalDetails.from_approval(result.approval),
        )


type AgentResponse = ChatResponse | ApprovalRequiredResponse


def response_from_result(
    *,
    thread_id: str,
    result: AgentResult,
) -> AgentResponse:
    if isinstance(result, AgentApprovalRequired):
        return ApprovalRequiredResponse.from_result(
            thread_id=thread_id,
            result=result,
        )
    return ChatResponse.from_reply(
        thread_id=thread_id,
        reply=result,
    )
