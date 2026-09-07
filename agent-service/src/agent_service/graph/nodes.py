from langgraph.runtime import Runtime
from langgraph.types import interrupt

from agent_service.domain.intent import IntentType
from agent_service.graph.state import AgentContext, AgentState
from agent_service.integrations.business_service import OrderService
from agent_service.integrations.business_service.errors import OrderNotFoundError
from agent_service.rag.context import (
    FormattedKnowledgeContext,
    KnowledgeReference,
    format_retrieved_context,
)
from agent_service.rag.retrieval import (
    KnowledgeRetriever,
    KnowledgeStoreUnavailableError,
)
from agent_service.services.answer_generator import AnswerGenerator
from agent_service.services.intent_analyzer import IntentAnalyzer
from agent_service.services.knowledge_answer_generator import (
    KnowledgeAnswerGenerator,
)
from agent_service.tools import create_get_order_tool

KNOWLEDGE_UNAVAILABLE_ANSWER = "知识库暂时不可用，请稍后重试或联系人工客服。"
DEFAULT_HISTORY_MAX_MESSAGES = 12


class SupportAgentNodes:
    def __init__(
        self,
        *,
        intent_analyzer: IntentAnalyzer,
        answer_generator: AnswerGenerator,
        business_client: OrderService,
        knowledge_retriever: KnowledgeRetriever | None = None,
        knowledge_answer_generator: KnowledgeAnswerGenerator | None = None,
        history_max_messages: int = DEFAULT_HISTORY_MAX_MESSAGES,
    ) -> None:
        if history_max_messages < 2 or history_max_messages % 2 != 0:
            raise ValueError(
                "history_max_messages must be an even number greater than or equal to 2"
            )
        self._intent_analyzer = intent_analyzer
        self._answer_generator = answer_generator
        self._business_client = business_client
        self._knowledge_retriever = knowledge_retriever
        self._knowledge_answer_generator = knowledge_answer_generator
        self._history_max_messages = history_max_messages

    async def analyze_intent(
        self,
        state: AgentState,
    ) -> dict[str, object]:
        analysis = await self._intent_analyzer.analyze(state["message"])
        order_id = analysis.order_id
        needs_clarification = analysis.needs_clarification

        active_order_id = state.get("active_order_id")
        if (
            analysis.intent is IntentType.ORDER_QUERY
            and order_id is None
            and isinstance(active_order_id, str)
            and active_order_id.strip()
        ):
            order_id = active_order_id
            needs_clarification = False

        return {
            "intent": analysis.intent,
            "order_id": order_id,
            "needs_clarification": needs_clarification,
        }

    def request_clarification(
        self,
        _state: AgentState,
    ) -> dict[str, object]:
        return {
            "answer": "请提供需要处理的订单号。",
        }

    def unsupported(
        self,
        _state: AgentState,
    ) -> dict[str, object]:
        return {
            "answer": "目前我可以帮助查询订单状态和退款资格。",
        }

    async def query_order(
        self,
        state: AgentState,
        runtime: Runtime[AgentContext],
    ) -> dict[str, object]:
        order_id = state.get("order_id")
        if order_id is None:
            raise ValueError("查询订单节点缺少 order_id")

        order_tool = create_get_order_tool(
            client=self._business_client,
            tenant_id=runtime.context.tenant_id,
            user_id=runtime.context.user_id,
        )
        try:
            order_data = await order_tool.ainvoke(
                {
                    "order_id": order_id,
                }
            )
        except OrderNotFoundError:
            return {
                "order_found": False,
            }

        if not isinstance(order_data, dict):
            raise TypeError("订单工具没有返回有效的数据")

        return {
            "order_found": True,
            "order_data": order_data,
        }

    def order_not_found(
        self,
        state: AgentState,
    ) -> dict[str, object]:
        order_id = state.get("order_id")
        if order_id is None:
            raise ValueError("订单不存在节点缺少 order_id")

        return {
            "answer": (f"没有找到订单 {order_id}，请检查订单号是否正确。"),
        }

    async def retrieve_knowledge(
        self,
        state: AgentState,
        runtime: Runtime[AgentContext],
    ) -> dict[str, object]:
        if self._knowledge_retriever is None:
            return {
                "knowledge_status": "unavailable",
                "knowledge_context": "",
                "knowledge_references": [],
            }

        try:
            chunks = await self._knowledge_retriever.retrieve(
                question=state["message"],
                tenant_id=runtime.context.tenant_id,
            )
        except KnowledgeStoreUnavailableError:
            return {
                "knowledge_status": "unavailable",
                "knowledge_context": "",
                "knowledge_references": [],
            }
        context = format_retrieved_context(chunks)

        return {
            "knowledge_status": ("available" if chunks else "no_match"),
            "knowledge_context": context.text,
            "knowledge_references": [
                {
                    "reference_number": reference.reference_number,
                    "document_id": reference.document_id,
                    "title": reference.title,
                    "section_title": reference.section_title,
                    "version": reference.version,
                }
                for reference in context.references
            ],
        }

    async def generate_knowledge_answer(
        self,
        state: AgentState,
    ) -> dict[str, object]:
        knowledge_status = state.get("knowledge_status")
        if knowledge_status == "unavailable":
            return {
                "answer": KNOWLEDGE_UNAVAILABLE_ANSWER,
            }
        if knowledge_status not in {"available", "no_match"}:
            raise ValueError("知识库回答节点缺少 knowledge_status")
        if self._knowledge_answer_generator is None:
            raise RuntimeError("知识库回答生成器未配置")
        if "knowledge_context" not in state:
            raise ValueError("知识库回答节点缺少 knowledge_context")
        if "knowledge_references" not in state:
            raise ValueError("知识库回答节点缺少 knowledge_references")

        context = FormattedKnowledgeContext(
            text=state["knowledge_context"],
            references=tuple(
                KnowledgeReference(
                    reference_number=reference["reference_number"],
                    document_id=reference["document_id"],
                    title=reference["title"],
                    section_title=reference["section_title"],
                    version=reference["version"],
                )
                for reference in state["knowledge_references"]
            ),
        )
        answer = await self._knowledge_answer_generator.generate(
            message=state["message"],
            context=context,
        )
        return {
            "answer": answer,
        }

    async def generate_answer(
        self,
        state: AgentState,
    ) -> dict[str, object]:
        order_data = state.get("order_data")
        if not isinstance(order_data, dict):
            raise TypeError("回答生成节点缺少有效的 order_data")

        answer = await self._answer_generator.generate(
            message=state["message"],
            order_data=order_data,
        )
        return {
            "answer": answer,
        }

    def request_refund_approval(
        self,
        state: AgentState,
    ) -> dict[str, object]:
        order_id = state.get("order_id")
        order_data = state.get("order_data")
        if not isinstance(order_id, str):
            raise TypeError("退款确认节点缺少订单号")
        if not isinstance(order_data, dict):
            raise TypeError("退款确认节点缺少订单数据")

        decision = interrupt(
            {
                "operation": "request_refund",
                "order_id": order_id,
                "product_name": order_data.get("productName"),
                "total_amount": order_data.get("totalAmount"),
                "status": order_data.get("status"),
            }
        )
        if not isinstance(decision, dict):
            raise TypeError("退款确认结果必须是对象")
        approved = decision.get("approved")
        if type(approved) is not bool:
            raise TypeError("退款确认结果缺少布尔值 approved")

        if not approved:
            return {
                "refund_approved": False,
                "answer": f"已取消订单 {order_id} 的退款申请。",
            }
        return {
            "refund_approved": True,
        }

    async def submit_refund(
        self,
        state: AgentState,
        runtime: Runtime[AgentContext],
    ) -> dict[str, object]:
        order_id = state.get("order_id")
        if not isinstance(order_id, str):
            raise TypeError("提交退款节点缺少订单号")
        idempotency_key = runtime.context.idempotency_key
        if not isinstance(idempotency_key, str):
            raise TypeError("提交退款节点缺少幂等键")

        order = await self._business_client.request_refund(
            tenant_id=runtime.context.tenant_id,
            user_id=runtime.context.user_id,
            order_id=order_id,
            idempotency_key=idempotency_key,
        )
        return {
            "order_data": order.model_dump(
                mode="json",
                by_alias=True,
            ),
            "answer": (f"订单 {order_id} 的退款申请已提交，当前状态为 REFUNDING。"),
        }

    def save_turn(
        self,
        state: AgentState,
    ) -> dict[str, object]:
        answer = state.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise TypeError("保存会话前缺少有效回答")

        history = list(state.get("conversation_history", []))
        history.extend(
            [
                {
                    "role": "user",
                    "content": state["message"],
                },
                {
                    "role": "assistant",
                    "content": answer,
                },
            ]
        )

        active_order_id = state.get("active_order_id")
        current_order_id = state.get("order_id")
        if state.get("order_found") is True and isinstance(current_order_id, str):
            active_order_id = current_order_id

        return {
            "conversation_history": history[-self._history_max_messages :],
            "active_order_id": active_order_id,
        }
