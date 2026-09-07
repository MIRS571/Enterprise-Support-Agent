import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent_service.domain.intent import IntentAnalysis, IntentType
from agent_service.domain.order import OrderResponse, OrderStatus
from agent_service.graph import (
    AgentContext,
    SupportAgentNodes,
    build_support_agent_graph,
)


def test_graph_builder_attaches_checkpointer() -> None:
    nodes = Mock(spec=SupportAgentNodes)
    checkpointer = InMemorySaver()

    graph = build_support_agent_graph(
        nodes,
        checkpointer=checkpointer,
    )

    assert graph.checkpointer is checkpointer


from agent_service.graph.nodes import KNOWLEDGE_UNAVAILABLE_ANSWER
from agent_service.integrations.business_service import BusinessServiceClient
from agent_service.rag.retrieval import KnowledgeRetriever
from agent_service.services import (
    NO_KNOWLEDGE_ANSWER,
    AnswerGenerator,
    IntentAnalyzer,
    KnowledgeAnswerGenerator,
)


def test_graph_runs_complete_order_query_path() -> None:
    intent_analyzer = Mock(spec=IntentAnalyzer)
    intent_analyzer.analyze = AsyncMock(
        return_value=IntentAnalysis(
            intent=IntentType.ORDER_QUERY,
            order_id="A1001",
            needs_clarification=False,
        )
    )
    business_client = Mock(spec=BusinessServiceClient)
    business_client.get_order = AsyncMock(
        return_value=OrderResponse(
            orderId="A1001",
            productName="机械键盘",
            quantity=1,
            totalAmount=Decimal("299.00"),
            status=OrderStatus.SHIPPED,
            createdAt=datetime(2026, 8, 20, tzinfo=UTC),
            cancelable=False,
            refundable=True,
        )
    )
    answer_generator = Mock(spec=AnswerGenerator)
    answer_generator.generate = AsyncMock(return_value="订单A1001已经发货。")
    graph = build_support_agent_graph(
        SupportAgentNodes(
            intent_analyzer=intent_analyzer,
            answer_generator=answer_generator,
            business_client=business_client,
        )
    )

    result = asyncio.run(
        graph.ainvoke(
            {
                "message": "订单A1001到哪了？",
            },
            context=AgentContext(
                tenant_id="company_001",
                user_id="U1001",
            ),
        )
    )

    assert result["answer"] == "订单A1001已经发货。"
    assert result["order_found"] is True
    assert result["order_data"]["orderId"] == "A1001"
    assert result["active_order_id"] == "A1001"
    assert result["conversation_history"] == [
        {
            "role": "user",
            "content": "订单A1001到哪了？",
        },
        {
            "role": "assistant",
            "content": "订单A1001已经发货。",
        },
    ]


def test_graph_reuses_active_order_across_checkpointed_turns() -> None:
    intent_analyzer = Mock(spec=IntentAnalyzer)
    intent_analyzer.analyze = AsyncMock(
        side_effect=[
            IntentAnalysis(
                intent=IntentType.ORDER_QUERY,
                order_id="A1001",
                needs_clarification=False,
            ),
            IntentAnalysis(
                intent=IntentType.ORDER_QUERY,
                order_id=None,
                needs_clarification=True,
            ),
        ]
    )
    business_client = Mock(spec=BusinessServiceClient)
    business_client.get_order = AsyncMock(
        return_value=OrderResponse(
            orderId="A1001",
            productName="机械键盘",
            quantity=1,
            totalAmount=Decimal("299.00"),
            status=OrderStatus.SHIPPED,
            createdAt=datetime(2026, 8, 20, tzinfo=UTC),
            cancelable=False,
            refundable=True,
        )
    )
    answer_generator = Mock(spec=AnswerGenerator)
    answer_generator.generate = AsyncMock(
        side_effect=[
            "订单A1001已经发货。",
            "订单A1001仍处于已发货状态。",
        ]
    )
    graph = build_support_agent_graph(
        SupportAgentNodes(
            intent_analyzer=intent_analyzer,
            answer_generator=answer_generator,
            business_client=business_client,
        ),
        checkpointer=InMemorySaver(),
    )
    config = {
        "configurable": {
            "thread_id": "checkpoint-thread-001",
        }
    }
    context = AgentContext(
        tenant_id="company_001",
        user_id="U1001",
    )

    asyncio.run(
        graph.ainvoke(
            {
                "message": "查询订单A1001",
            },
            config=config,
            context=context,
        )
    )
    result = asyncio.run(
        graph.ainvoke(
            {
                "message": "那它现在到哪了？",
                "intent": None,
                "order_id": None,
                "needs_clarification": False,
                "order_data": None,
                "order_found": False,
                "knowledge_context": "",
                "knowledge_references": [],
                "knowledge_status": "no_match",
                "answer": "",
            },
            config=config,
            context=context,
        )
    )

    assert result["order_id"] == "A1001"
    assert result["active_order_id"] == "A1001"
    assert result["answer"] == "订单A1001仍处于已发货状态。"
    assert result["conversation_history"] == [
        {"role": "user", "content": "查询订单A1001"},
        {
            "role": "assistant",
            "content": "订单A1001已经发货。",
        },
        {"role": "user", "content": "那它现在到哪了？"},
        {
            "role": "assistant",
            "content": "订单A1001仍处于已发货状态。",
        },
    ]
    assert business_client.get_order.await_count == 2


def test_graph_stops_when_order_id_is_missing() -> None:
    intent_analyzer = Mock(spec=IntentAnalyzer)
    intent_analyzer.analyze = AsyncMock(
        return_value=IntentAnalysis(
            intent=IntentType.REFUND,
            order_id=None,
            needs_clarification=True,
        )
    )
    business_client = Mock(spec=BusinessServiceClient)
    answer_generator = Mock(spec=AnswerGenerator)
    graph = build_support_agent_graph(
        SupportAgentNodes(
            intent_analyzer=intent_analyzer,
            answer_generator=answer_generator,
            business_client=business_client,
        )
    )

    result = asyncio.run(
        graph.ainvoke(
            {
                "message": "我想退款",
            },
            context=AgentContext(
                tenant_id="company_001",
                user_id="U1001",
            ),
        )
    )

    assert result["answer"] == "请提供需要处理的订单号。"
    business_client.get_order.assert_not_called()
    answer_generator.generate.assert_not_called()


def create_refund_graph() -> tuple[object, Mock]:
    intent_analyzer = Mock(spec=IntentAnalyzer)
    intent_analyzer.analyze = AsyncMock(
        return_value=IntentAnalysis(
            intent=IntentType.REFUND,
            order_id="A1001",
            needs_clarification=False,
        )
    )
    business_client = Mock(spec=BusinessServiceClient)
    business_client.get_order = AsyncMock(
        return_value=OrderResponse(
            orderId="A1001",
            productName="机械键盘",
            quantity=1,
            totalAmount=Decimal("299.00"),
            status=OrderStatus.SHIPPED,
            createdAt=datetime(2026, 8, 20, tzinfo=UTC),
            cancelable=False,
            refundable=True,
        )
    )
    business_client.request_refund = AsyncMock(
        return_value=OrderResponse(
            orderId="A1001",
            productName="机械键盘",
            quantity=1,
            totalAmount=Decimal("299.00"),
            status=OrderStatus.REFUNDING,
            createdAt=datetime(2026, 8, 20, tzinfo=UTC),
            cancelable=False,
            refundable=False,
        )
    )
    graph = build_support_agent_graph(
        SupportAgentNodes(
            intent_analyzer=intent_analyzer,
            answer_generator=Mock(spec=AnswerGenerator),
            business_client=business_client,
        ),
        checkpointer=InMemorySaver(),
    )
    return graph, business_client


def test_refund_interrupt_denial_never_calls_mutation() -> None:
    graph, business_client = create_refund_graph()
    config = {
        "configurable": {
            "thread_id": "refund-denied-thread",
        }
    }
    context = AgentContext(
        tenant_id="company_001",
        user_id="U1001",
    )

    paused = asyncio.run(
        graph.ainvoke(
            {"message": "申请退款A1001"},
            config=config,
            context=context,
        )
    )

    assert paused["__interrupt__"][0].value == {
        "operation": "request_refund",
        "order_id": "A1001",
        "product_name": "机械键盘",
        "total_amount": "299.00",
        "status": "SHIPPED",
    }
    business_client.request_refund.assert_not_awaited()

    result = asyncio.run(
        graph.ainvoke(
            Command(resume={"approved": False}),
            config=config,
            context=context,
        )
    )

    assert result["refund_approved"] is False
    assert result["answer"] == "已取消订单 A1001 的退款申请。"
    business_client.request_refund.assert_not_awaited()


def test_refund_interrupt_approval_calls_mutation_once() -> None:
    graph, business_client = create_refund_graph()
    config = {
        "configurable": {
            "thread_id": "refund-approved-thread",
        }
    }
    context = AgentContext(
        tenant_id="company_001",
        user_id="U1001",
        idempotency_key="refund-001",
    )
    asyncio.run(
        graph.ainvoke(
            {"message": "申请退款A1001"},
            config=config,
            context=context,
        )
    )

    result = asyncio.run(
        graph.ainvoke(
            Command(resume={"approved": True}),
            config=config,
            context=context,
        )
    )

    assert result["refund_approved"] is True
    assert result["order_data"]["status"] == "REFUNDING"
    assert result["answer"] == ("订单 A1001 的退款申请已提交，当前状态为 REFUNDING。")
    business_client.request_refund.assert_awaited_once_with(
        tenant_id="company_001",
        user_id="U1001",
        order_id="A1001",
        idempotency_key="refund-001",
    )


def test_graph_runs_complete_policy_query_path() -> None:
    intent_analyzer = Mock(spec=IntentAnalyzer)
    intent_analyzer.analyze = AsyncMock(
        return_value=IntentAnalysis(
            intent=IntentType.POLICY_QUERY,
            order_id=None,
            needs_clarification=False,
        )
    )
    knowledge_retriever = Mock(spec=KnowledgeRetriever)
    knowledge_retriever.retrieve = AsyncMock(return_value=[])
    knowledge_answer_generator = Mock(spec=KnowledgeAnswerGenerator)
    knowledge_answer_generator.generate = AsyncMock(return_value=NO_KNOWLEDGE_ANSWER)
    business_client = Mock(spec=BusinessServiceClient)
    order_answer_generator = Mock(spec=AnswerGenerator)
    graph = build_support_agent_graph(
        SupportAgentNodes(
            intent_analyzer=intent_analyzer,
            answer_generator=order_answer_generator,
            business_client=business_client,
            knowledge_retriever=knowledge_retriever,
            knowledge_answer_generator=knowledge_answer_generator,
        )
    )

    result = asyncio.run(
        graph.ainvoke(
            {
                "message": "已拆封软件支持无理由退款吗？",
            },
            context=AgentContext(
                tenant_id="company_001",
                user_id="U1001",
            ),
        )
    )

    assert result["answer"] == NO_KNOWLEDGE_ANSWER
    assert result["knowledge_context"] == ""
    assert result["knowledge_status"] == "no_match"
    assert result["knowledge_references"] == []
    knowledge_retriever.retrieve.assert_awaited_once_with(
        question="已拆封软件支持无理由退款吗？",
        tenant_id="company_001",
    )
    business_client.get_order.assert_not_called()
    order_answer_generator.generate.assert_not_called()


def test_graph_degrades_policy_query_when_rag_is_unavailable() -> None:
    intent_analyzer = Mock(spec=IntentAnalyzer)
    intent_analyzer.analyze = AsyncMock(
        return_value=IntentAnalysis(
            intent=IntentType.POLICY_QUERY,
            order_id=None,
            needs_clarification=False,
        )
    )
    knowledge_answer_generator = Mock(spec=KnowledgeAnswerGenerator)
    knowledge_answer_generator.generate = AsyncMock()
    business_client = Mock(spec=BusinessServiceClient)
    order_answer_generator = Mock(spec=AnswerGenerator)
    graph = build_support_agent_graph(
        SupportAgentNodes(
            intent_analyzer=intent_analyzer,
            answer_generator=order_answer_generator,
            business_client=business_client,
            knowledge_answer_generator=knowledge_answer_generator,
        )
    )

    result = asyncio.run(
        graph.ainvoke(
            {
                "message": "退款政策是什么？",
            },
            context=AgentContext(
                tenant_id="company_001",
                user_id="U1001",
            ),
        )
    )

    assert result["answer"] == KNOWLEDGE_UNAVAILABLE_ANSWER
    assert result["knowledge_status"] == "unavailable"
    assert result["knowledge_references"] == []
    knowledge_answer_generator.generate.assert_not_awaited()
    business_client.get_order.assert_not_called()
