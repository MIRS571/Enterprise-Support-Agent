import json

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

ANSWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
你是企业电商售后助手。请根据 Java 业务服务返回的订单数据回答用户。

回答规则：
- 订单数据是唯一可信事实，禁止编造物流位置、时间或业务状态。
- cancelable 和 refundable 已由 Java 业务规则计算，不得自行修改结论。
- refundable 为 true 只表示具备申请退款的资格，不代表退款已经完成或必然自动通过。
- 如果现有数据不足以回答问题，要明确说明目前无法确认的信息。
- 不得承诺当前系统没有实现的能力，例如查询物流轨迹、联系商家或代用户执行退款。
- 使用简洁、友好的中文，不要向用户暴露内部系统实现。
""".strip(),
        ),
        (
            "human",
            "用户问题：{message}\n\n订单数据：\n{order_data}",
        ),
    ]
)


class AnswerGenerator:
    def __init__(self, model: BaseChatModel) -> None:
        self._chain = ANSWER_PROMPT | model | StrOutputParser()

    async def generate(
        self,
        *,
        message: str,
        order_data: dict[str, object],
    ) -> str:
        return await self._chain.ainvoke(
            {
                "message": message,
                "order_data": json.dumps(
                    order_data,
                    ensure_ascii=False,
                    indent=2,
                ),
            }
        )
