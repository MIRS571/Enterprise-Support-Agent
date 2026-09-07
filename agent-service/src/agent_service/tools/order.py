from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from agent_service.integrations.business_service import OrderService


class GetOrderInput(BaseModel):
    order_id: str = Field(
        description="需要查询的订单号",
        min_length=1,
    )


def create_get_order_tool(
    *,
    client: OrderService,
    tenant_id: str,
    user_id: str,
) -> BaseTool:
    @tool(
        "get_order",
        args_schema=GetOrderInput,
    )
    async def get_order(order_id: str) -> dict[str, object]:
        """查询当前认证用户有权访问的订单及售后资格。"""
        order = await client.get_order(
            tenant_id=tenant_id,
            user_id=user_id,
            order_id=order_id,
        )
        return order.model_dump(
            mode="json",
            by_alias=True,
        )

    return get_order
