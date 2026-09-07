from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class OrderStatus(StrEnum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    SHIPPED = "SHIPPED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REFUNDING = "REFUNDING"
    REFUNDED = "REFUNDED"


class OrderResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    order_id: str = Field(alias="orderId")
    product_name: str = Field(alias="productName")
    quantity: int
    total_amount: Decimal = Field(alias="totalAmount")
    status: OrderStatus
    created_at: datetime = Field(alias="createdAt")
    cancelable: bool
    refundable: bool
