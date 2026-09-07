from collections.abc import AsyncIterator

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import ValidationError

from agent_service.domain.agent import (
    AgentApprovalRequired,
    AgentReply,
    AgentResult,
    AgentStreamCompleted,
    AgentStreamEvent,
    AgentStreamToken,
    ApprovalRequest,
    KnowledgeSource,
)
from agent_service.domain.intent import IntentType
from agent_service.graph.state import AgentContext
from agent_service.services.conversation_thread import (
    ConversationPersistenceUnavailableError,
    ConversationThreadService,
)

_USER_VISIBLE_STREAM_NODES = frozenset(
    {
        "generate_answer",
        "generate_knowledge_answer",
    }
)


class SupportAgentService:
    def __init__(
        self,
        *,
        graph: CompiledStateGraph,
        conversation_thread_service: (ConversationThreadService | None) = None,
    ) -> None:
        self._graph = graph
        self._conversation_thread_service = conversation_thread_service

    async def chat(
        self,
        *,
        tenant_id: str,
        user_id: str,
        thread_id: str,
        message: str,
    ) -> AgentResult:
        if self._conversation_thread_service is None:
            raise ConversationPersistenceUnavailableError

        checkpoint_key = await self._conversation_thread_service.resolve_checkpoint_key(
            thread_id=thread_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        result = await self._graph.ainvoke(
            self._new_graph_input(message),
            config={
                "configurable": {
                    "thread_id": checkpoint_key,
                }
            },
            context=AgentContext(
                tenant_id=tenant_id,
                user_id=user_id,
            ),
        )

        return self._map_graph_result(result)

    async def chat_stream(
        self,
        *,
        tenant_id: str,
        user_id: str,
        thread_id: str,
        message: str,
    ) -> AsyncIterator[AgentStreamEvent]:
        if self._conversation_thread_service is None:
            raise ConversationPersistenceUnavailableError

        checkpoint_key = await self._conversation_thread_service.resolve_checkpoint_key(
            thread_id=thread_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return self._stream_graph(
            tenant_id=tenant_id,
            user_id=user_id,
            checkpoint_key=checkpoint_key,
            message=message,
        )

    async def _stream_graph(
        self,
        *,
        tenant_id: str,
        user_id: str,
        checkpoint_key: str,
        message: str,
    ) -> AsyncIterator[AgentStreamEvent]:
        final_state: dict[str, object] | None = None

        async for event in self._graph.astream(
            self._new_graph_input(message),
            config={
                "configurable": {
                    "thread_id": checkpoint_key,
                }
            },
            context=AgentContext(
                tenant_id=tenant_id,
                user_id=user_id,
            ),
            stream_mode=["messages", "values"],
            version="v2",
        ):
            if not isinstance(event, dict):
                raise TypeError("Agent图返回了无效的流事件")

            event_type = event.get("type")
            if event_type == "messages":
                token = self._extract_user_visible_token(event.get("data"))
                if token:
                    yield AgentStreamToken(content=token)
                continue

            if event_type == "values":
                data = event.get("data")
                if not isinstance(data, dict):
                    raise TypeError("Agent图返回了无效的状态事件")
                final_state = dict(data)
                interrupts = event.get("interrupts", ())
                if interrupts:
                    final_state["__interrupt__"] = interrupts

        if final_state is None:
            raise TypeError("Agent图流没有返回最终状态")
        yield AgentStreamCompleted(
            result=self._map_graph_result(final_state),
        )

    async def resume_refund(
        self,
        *,
        tenant_id: str,
        user_id: str,
        thread_id: str,
        approved: bool,
        idempotency_key: str,
    ) -> AgentReply:
        if self._conversation_thread_service is None:
            raise ConversationPersistenceUnavailableError

        checkpoint_key = await self._conversation_thread_service.resolve_checkpoint_key(
            thread_id=thread_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        config = {
            "configurable": {
                "thread_id": checkpoint_key,
            }
        }
        snapshot = await self._graph.aget_state(config)
        if len(snapshot.interrupts) != 1:
            raise ApprovalNotPendingError
        self._validate_approval(snapshot.interrupts[0].value)

        result = await self._graph.ainvoke(
            Command(resume={"approved": approved}),
            config=config,
            context=AgentContext(
                tenant_id=tenant_id,
                user_id=user_id,
                idempotency_key=idempotency_key,
            ),
        )
        mapped_result = self._map_graph_result(result)
        if isinstance(mapped_result, AgentApprovalRequired):
            raise TypeError("退款确认恢复后仍处于暂停状态")
        return mapped_result

    def _map_graph_result(
        self,
        result: object,
    ) -> AgentResult:
        if not isinstance(result, dict):
            raise TypeError("Agent图没有返回有效的状态")

        interrupts = result.get("__interrupt__", ())
        if interrupts:
            if not isinstance(interrupts, (list, tuple)):
                raise TypeError("Agent图返回了无效的暂停信息")
            if len(interrupts) != 1:
                raise TypeError("Agent图返回了多个暂停信息")
            approval = self._validate_approval(getattr(interrupts[0], "value", None))
            intent = self._validate_intent(result.get("intent"))
            order_id = result.get("order_id")
            if intent is not IntentType.REFUND:
                raise TypeError("退款暂停缺少有效意图")
            if not isinstance(order_id, str):
                raise TypeError("退款暂停缺少有效订单号")
            if approval.order_id != order_id:
                raise TypeError("退款暂停的订单号不一致")
            return AgentApprovalRequired(
                intent=IntentType.REFUND,
                order_id=order_id,
                approval=approval,
            )

        answer = result.get("answer")
        intent = self._validate_intent(result.get("intent"))
        order_id = result.get("order_id")
        raw_sources = result.get("knowledge_references", [])

        if not isinstance(answer, str) or not answer.strip():
            raise TypeError("Agent图没有返回有效的回答")
        if order_id is not None and not isinstance(order_id, str):
            raise TypeError("Agent图返回了无效的订单号")
        if not isinstance(raw_sources, list):
            raise TypeError("Agent图返回了无效的知识来源")

        try:
            sources = [KnowledgeSource.model_validate(source) for source in raw_sources]
        except ValidationError as error:
            raise TypeError("Agent图返回了无效的知识来源") from error

        reference_numbers = [source.reference_number for source in sources]
        if len(reference_numbers) != len(set(reference_numbers)):
            raise TypeError("Agent图返回了重复的知识来源编号")

        return AgentReply(
            answer=answer,
            intent=intent,
            order_id=order_id,
            sources=sources,
        )

    @staticmethod
    def _new_graph_input(message: str) -> dict[str, object]:
        return {
            "message": message,
            "intent": None,
            "order_id": None,
            "needs_clarification": False,
            "order_data": None,
            "order_found": False,
            "refund_approved": None,
            "knowledge_context": "",
            "knowledge_references": [],
            "knowledge_status": "no_match",
            "answer": "",
        }

    @staticmethod
    def _extract_user_visible_token(data: object) -> str:
        if not isinstance(data, (list, tuple)) or len(data) != 2:
            raise TypeError("Agent图返回了无效的消息事件")
        message, metadata = data
        if not isinstance(metadata, dict):
            raise TypeError("Agent图消息缺少有效元数据")
        if metadata.get("langgraph_node") not in _USER_VISIBLE_STREAM_NODES:
            return ""

        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""

        text_parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                text_parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
        return "".join(text_parts)

    @staticmethod
    def _validate_approval(value: object) -> ApprovalRequest:
        try:
            return ApprovalRequest.model_validate(value)
        except ValidationError as error:
            raise TypeError("Agent图返回了无效的退款确认信息") from error

    @staticmethod
    def _validate_intent(value: object) -> IntentType:
        try:
            return IntentType(value)
        except (TypeError, ValueError) as error:
            raise TypeError("Agent图没有返回有效的意图") from error


class ApprovalNotPendingError(RuntimeError):
    pass
