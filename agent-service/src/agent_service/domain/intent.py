from enum import StrEnum

from pydantic import BaseModel, Field


class IntentType(StrEnum):
    ORDER_QUERY = "order_query"
    REFUND = "refund"
    POLICY_QUERY = "policy_query"
    COMPLAINT = "complaint"
    OTHER = "other"


class IntentAnalysis(BaseModel):
    intent: IntentType = Field(
        description="用户意图，只能选择定义好的固定值",
    )
    order_id: str | None = Field(
        default=None,
        description="用户明确提到的订单号；没有提到时为 null",
    )
    needs_clarification: bool = Field(
        description="继续处理前是否需要向用户补充询问信息",
    )
