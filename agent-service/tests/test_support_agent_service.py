import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.messages import AIMessageChunk
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Interrupt

from agent_service.domain.agent import (
    AgentApprovalRequired,
    AgentStreamCompleted,
    AgentStreamToken,
)
from agent_service.domain.intent import IntentType
from agent_service.graph import AgentContext
from agent_service.services import (
    ApprovalNotPendingError,
    ConversationThreadService,
    SupportAgentService,
)


def approval_payload() -> dict[str, object]:
    return {
        "operation": "request_refund",
        "order_id": "A1001",
        "product_name": "机械键盘",
        "total_amount": "299.00",
        "status": "SHIPPED",
    }


def create_service(
    graph: Mock,
) -> tuple[SupportAgentService, Mock]:
    conversation_service = Mock(spec=ConversationThreadService)
    conversation_service.resolve_checkpoint_key = AsyncMock(
        return_value="22222222-2222-4222-8222-222222222222"
    )
    return (
        SupportAgentService(
            graph=graph,
            conversation_thread_service=conversation_service,
        ),
        conversation_service,
    )


def test_chat_invokes_graph_with_trusted_context() -> None:
    graph = Mock(spec=CompiledStateGraph)
    graph.ainvoke = AsyncMock(
        return_value={
            "message": "查询订单A1001",
            "intent": IntentType.ORDER_QUERY,
            "order_id": "A1001",
            "needs_clarification": False,
            "order_found": True,
            "order_data": {
                "orderId": "A1001",
                "status": "SHIPPED",
            },
            "answer": "订单A1001已经发货。",
        }
    )
    service, conversation_service = create_service(graph)

    reply = asyncio.run(
        service.chat(
            tenant_id="company_001",
            user_id="U1001",
            thread_id="11111111-1111-4111-8111-111111111111",
            message="查询订单A1001",
        )
    )

    assert reply.answer == "订单A1001已经发货。"
    assert reply.intent is IntentType.ORDER_QUERY
    assert reply.order_id == "A1001"
    assert reply.sources == []
    graph.ainvoke.assert_awaited_once_with(
        {
            "message": "查询订单A1001",
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
        },
        config={
            "configurable": {"thread_id": ("22222222-2222-4222-8222-222222222222")}
        },
        context=AgentContext(
            tenant_id="company_001",
            user_id="U1001",
        ),
    )
    conversation_service.resolve_checkpoint_key.assert_awaited_once_with(
        thread_id="11111111-1111-4111-8111-111111111111",
        tenant_id="company_001",
        user_id="U1001",
    )


def test_chat_maps_interrupt_to_approval_required() -> None:
    graph = Mock(spec=CompiledStateGraph)
    graph.ainvoke = AsyncMock(
        return_value={
            "message": "申请退款A1001",
            "intent": IntentType.REFUND,
            "order_id": "A1001",
            "__interrupt__": (
                Interrupt(
                    value=approval_payload(),
                    id="interrupt-001",
                ),
            ),
        }
    )
    service, _conversation_service = create_service(graph)

    result = asyncio.run(
        service.chat(
            tenant_id="company_001",
            user_id="U1001",
            thread_id="11111111-1111-4111-8111-111111111111",
            message="申请退款A1001",
        )
    )

    assert isinstance(result, AgentApprovalRequired)
    assert result.order_id == "A1001"
    assert result.approval.total_amount == 299


def test_chat_stream_filters_internal_messages_and_returns_result() -> None:
    graph = Mock(spec=CompiledStateGraph)

    async def events():
        yield {
            "type": "values",
            "data": {"message": "查询订单A1001", "answer": ""},
            "interrupts": (),
        }
        yield {
            "type": "messages",
            "data": (
                AIMessageChunk(content='{"intent":"order_query"}'),
                {"langgraph_node": "analyze_intent"},
            ),
        }
        yield {
            "type": "messages",
            "data": (
                AIMessageChunk(content="订单"),
                {"langgraph_node": "generate_answer"},
            ),
        }
        yield {
            "type": "messages",
            "data": (
                AIMessageChunk(content="已经发货。"),
                {"langgraph_node": "generate_answer"},
            ),
        }
        yield {
            "type": "values",
            "data": {
                "message": "查询订单A1001",
                "intent": IntentType.ORDER_QUERY,
                "order_id": "A1001",
                "answer": "订单已经发货。",
            },
            "interrupts": (),
        }

    graph.astream = Mock(return_value=events())
    service, _conversation_service = create_service(graph)

    async def collect():
        events_iterator = await service.chat_stream(
            tenant_id="company_001",
            user_id="U1001",
            thread_id="11111111-1111-4111-8111-111111111111",
            message="查询订单A1001",
        )
        return [
            event
            async for event in events_iterator
        ]

    streamed = asyncio.run(collect())

    assert [
        event.content
        for event in streamed
        if isinstance(event, AgentStreamToken)
    ] == ["订单", "已经发货。"]
    completed = streamed[-1]
    assert isinstance(completed, AgentStreamCompleted)
    assert completed.result.answer == "订单已经发货。"


def test_chat_stream_maps_v2_interrupts_to_approval_result() -> None:
    graph = Mock(spec=CompiledStateGraph)

    async def events():
        yield {
            "type": "values",
            "data": {
                "message": "申请退款A1001",
                "intent": IntentType.REFUND,
                "order_id": "A1001",
            },
            "interrupts": (
                Interrupt(
                    value=approval_payload(),
                    id="interrupt-001",
                ),
            ),
        }

    graph.astream = Mock(return_value=events())
    service, _conversation_service = create_service(graph)

    async def collect():
        events_iterator = await service.chat_stream(
            tenant_id="company_001",
            user_id="U1001",
            thread_id="11111111-1111-4111-8111-111111111111",
            message="申请退款A1001",
        )
        return [
            event
            async for event in events_iterator
        ]

    streamed = asyncio.run(collect())

    completed = streamed[-1]
    assert isinstance(completed, AgentStreamCompleted)
    assert isinstance(completed.result, AgentApprovalRequired)
    assert completed.result.order_id == "A1001"


def test_resume_refund_uses_owned_private_checkpoint() -> None:
    graph = Mock(spec=CompiledStateGraph)
    graph.aget_state = AsyncMock(
        return_value=Mock(
            interrupts=(
                Interrupt(
                    value=approval_payload(),
                    id="interrupt-001",
                ),
            )
        )
    )
    graph.ainvoke = AsyncMock(
        return_value={
            "message": "申请退款A1001",
            "intent": "refund",
            "order_id": "A1001",
            "refund_approved": True,
            "answer": ("订单 A1001 的退款申请已提交，当前状态为 REFUNDING。"),
        }
    )
    service, conversation_service = create_service(graph)

    result = asyncio.run(
        service.resume_refund(
            tenant_id="company_001",
            user_id="U1001",
            thread_id="11111111-1111-4111-8111-111111111111",
            approved=True,
            idempotency_key="refund-001",
        )
    )

    assert result.answer.endswith("REFUNDING。")
    conversation_service.resolve_checkpoint_key.assert_awaited_once_with(
        thread_id="11111111-1111-4111-8111-111111111111",
        tenant_id="company_001",
        user_id="U1001",
    )
    config = {
        "configurable": {
            "thread_id": "22222222-2222-4222-8222-222222222222",
        }
    }
    graph.aget_state.assert_awaited_once_with(config)
    invocation = graph.ainvoke.await_args
    assert invocation.args[0].resume == {"approved": True}
    assert invocation.kwargs["config"] == config
    assert invocation.kwargs["context"].idempotency_key == "refund-001"


def test_resume_refund_rejects_thread_without_pending_approval() -> None:
    graph = Mock(spec=CompiledStateGraph)
    graph.aget_state = AsyncMock(return_value=Mock(interrupts=()))
    graph.ainvoke = AsyncMock()
    service, _conversation_service = create_service(graph)

    with pytest.raises(ApprovalNotPendingError):
        asyncio.run(
            service.resume_refund(
                tenant_id="company_001",
                user_id="U1001",
                thread_id=("11111111-1111-4111-8111-111111111111"),
                approved=True,
                idempotency_key="refund-002",
            )
        )

    graph.ainvoke.assert_not_awaited()


def test_chat_rejects_graph_result_without_answer() -> None:
    graph = Mock(spec=CompiledStateGraph)
    graph.ainvoke = AsyncMock(
        return_value={
            "message": "查询订单A1001",
            "intent": IntentType.ORDER_QUERY,
            "order_id": "A1001",
        }
    )
    service, _conversation_service = create_service(graph)

    with pytest.raises(
        TypeError,
        match="Agent图没有返回有效的回答",
    ):
        asyncio.run(
            service.chat(
                tenant_id="company_001",
                user_id="U1001",
                thread_id=("11111111-1111-4111-8111-111111111111"),
                message="查询订单A1001",
            )
        )


def test_chat_maps_graph_references_to_sources() -> None:
    graph = Mock(spec=CompiledStateGraph)
    graph.ainvoke = AsyncMock(
        return_value={
            "message": "已拆封软件能退款吗？",
            "intent": IntentType.POLICY_QUERY,
            "order_id": None,
            "answer": "不支持七天无理由退货。[资料1]",
            "knowledge_references": [
                {
                    "reference_number": 1,
                    "document_id": "refund-policy",
                    "title": "退款与退货政策",
                    "section_title": "七天无理由退货",
                    "version": "1.0",
                }
            ],
        }
    )
    service, _conversation_service = create_service(graph)

    reply = asyncio.run(
        service.chat(
            tenant_id="company_001",
            user_id="U1001",
            thread_id="11111111-1111-4111-8111-111111111111",
            message="已拆封软件能退款吗？",
        )
    )

    assert reply.sources[0].reference_number == 1
    assert reply.sources[0].document_id == "refund-policy"
    assert reply.sources[0].title == "退款与退货政策"


def test_chat_rejects_source_with_internal_fields() -> None:
    graph = Mock(spec=CompiledStateGraph)
    graph.ainvoke = AsyncMock(
        return_value={
            "message": "退款政策是什么？",
            "intent": IntentType.POLICY_QUERY,
            "answer": "请查看退款政策。[资料1]",
            "knowledge_references": [
                {
                    "reference_number": 1,
                    "document_id": "refund-policy",
                    "title": "退款与退货政策",
                    "section_title": "退款资格说明",
                    "version": "1.0",
                    "tenant_id": "company_001",
                }
            ],
        }
    )
    service, _conversation_service = create_service(graph)

    with pytest.raises(
        TypeError,
        match="Agent图返回了无效的知识来源",
    ):
        asyncio.run(
            service.chat(
                tenant_id="company_001",
                user_id="U1001",
                thread_id=("11111111-1111-4111-8111-111111111111"),
                message="退款政策是什么？",
            )
        )
