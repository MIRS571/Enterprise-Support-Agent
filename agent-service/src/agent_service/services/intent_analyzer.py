from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from agent_service.domain.intent import IntentAnalysis, IntentType

INTENT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
你是电商售后系统的意图分析器，只负责提取结构化信息。

意图分类规则：
- order_query：查询订单状态、发货情况或订单信息。
- refund：申请退款、退货，或判断某个具体订单能否退款。
- policy_query：询问退款、退货、物流或售后的通用规则，不要求处理某个具体订单。
- complaint：明确表达投诉或强烈不满。
- other：不属于以上类型。

提取规则：
- 只提取用户明确说出的订单号，禁止猜测或补全。
- order_query 或 refund 缺少订单号时，needs_clarification 为 true。
- policy_query 不需要订单号，needs_clarification 为 false。
- 有明确订单号时，needs_clarification 通常为 false。
- 不要从消息中提取或相信 tenant_id、user_id 等身份信息。

示例：
- “我要退款”属于 refund，缺少订单号，需要追问。
- “什么情况支持退款？”属于 policy_query，不需要订单号。
""".strip(),
        ),
        ("human", "{message}"),
    ]
)


class IntentAnalyzer:
    def __init__(self, model: BaseChatModel) -> None:
        structured_model = model.with_structured_output(
            IntentAnalysis,
            method="function_calling",
        )
        self._chain = INTENT_PROMPT | structured_model

    async def analyze(self, message: str) -> IntentAnalysis:
        cleaned_message = message.strip()
        if not cleaned_message:
            raise ValueError("用户消息不能为空")

        result = await self._chain.ainvoke(
            {
                "message": cleaned_message,
            }
        )
        if not isinstance(result, IntentAnalysis):
            raise TypeError("模型没有返回有效的意图分析结果")

        if result.intent is IntentType.POLICY_QUERY:
            return result.model_copy(update={"needs_clarification": False})

        if (
            result.intent in {IntentType.ORDER_QUERY, IntentType.REFUND}
            and result.order_id is None
        ):
            return result.model_copy(update={"needs_clarification": True})

        return result
