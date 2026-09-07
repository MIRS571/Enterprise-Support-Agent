import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.documents import Document
from langgraph.runtime import Runtime

from agent_service.domain.intent import IntentAnalysis, IntentType
from agent_service.domain.order import OrderResponse, OrderStatus
from agent_service.graph import AgentContext, SupportAgentNodes
from agent_service.graph.nodes import KNOWLEDGE_UNAVAILABLE_ANSWER
from agent_service.integrations.business_service import BusinessServiceClient
from agent_service.integrations.business_service.errors import OrderNotFoundError
from agent_service.rag.retrieval import (
    KnowledgeRetriever,
    KnowledgeStoreUnavailableError,
    RetrievedChunk,
)
from agent_service.services import (
    AnswerGenerator,
    IntentAnalyzer,
    KnowledgeAnswerGenerator,
)


def create_nodes(
    *,
    intent_analyzer: IntentAnalyzer | None = None,
    answer_generator: AnswerGenerator | None = None,
    business_client: BusinessServiceClient | None = None,
) -> SupportAgentNodes:
    return SupportAgentNodes(
        intent_analyzer=(intent_analyzer or Mock(spec=IntentAnalyzer)),
        answer_generator=(answer_generator or Mock(spec=AnswerGenerator)),
        business_client=(business_client or Mock(spec=BusinessServiceClient)),
    )


def test_analyze_intent_returns_only_state_updates() -> None:
    intent_analyzer = Mock(spec=IntentAnalyzer)
    intent_analyzer.analyze = AsyncMock(
        return_value=IntentAnalysis(
            intent=IntentType.ORDER_QUERY,
            order_id="A1001",
            needs_clarification=False,
        )
    )
    nodes = create_nodes(intent_analyzer=intent_analyzer)

    result = asyncio.run(
        nodes.analyze_intent(
            {
                "message": "查询订单A1001",
            }
        )
    )

    assert result == {
        "intent": IntentType.ORDER_QUERY,
        "order_id": "A1001",
        "needs_clarification": False,
    }
    intent_analyzer.analyze.assert_awaited_once_with("查询订单A1001")


def test_analyze_intent_reuses_active_order_for_query() -> None:
    intent_analyzer = Mock(spec=IntentAnalyzer)
    intent_analyzer.analyze = AsyncMock(
        return_value=IntentAnalysis(
            intent=IntentType.ORDER_QUERY,
            order_id=None,
            needs_clarification=True,
        )
    )
    nodes = create_nodes(intent_analyzer=intent_analyzer)

    result = asyncio.run(
        nodes.analyze_intent(
            {
                "message": "那它现在到哪了？",
                "active_order_id": "A1001",
            }
        )
    )

    assert result == {
        "intent": IntentType.ORDER_QUERY,
        "order_id": "A1001",
        "needs_clarification": False,
    }


def test_analyze_intent_does_not_reuse_active_order_for_refund() -> None:
    intent_analyzer = Mock(spec=IntentAnalyzer)
    intent_analyzer.analyze = AsyncMock(
        return_value=IntentAnalysis(
            intent=IntentType.REFUND,
            order_id=None,
            needs_clarification=True,
        )
    )
    nodes = create_nodes(intent_analyzer=intent_analyzer)

    result = asyncio.run(
        nodes.analyze_intent(
            {
                "message": "那就把它退掉",
                "active_order_id": "A1001",
            }
        )
    )

    assert result == {
        "intent": IntentType.REFUND,
        "order_id": None,
        "needs_clarification": True,
    }


def test_request_clarification_returns_fixed_answer() -> None:
    nodes = create_nodes()

    result = nodes.request_clarification(
        {
            "message": "我想退款",
            "intent": IntentType.REFUND,
            "order_id": None,
            "needs_clarification": True,
        }
    )

    assert result == {
        "answer": "请提供需要处理的订单号。",
    }


def test_unsupported_returns_fixed_answer() -> None:
    nodes = create_nodes()

    result = nodes.unsupported(
        {
            "message": "我要投诉",
            "intent": IntentType.COMPLAINT,
            "order_id": None,
            "needs_clarification": False,
        }
    )

    assert result == {
        "answer": "目前我可以帮助查询订单状态和退款资格。",
    }


def test_query_order_uses_runtime_identity() -> None:
    business_client = Mock(spec=BusinessServiceClient)
    business_client.get_order = AsyncMock(
        return_value=OrderResponse(
            orderId="A1001",
            productName="机械键盘",
            quantity=1,
            totalAmount="299.00",
            status=OrderStatus.SHIPPED,
            createdAt="2026-08-20T02:30:00Z",
            cancelable=False,
            refundable=True,
        )
    )
    nodes = create_nodes(business_client=business_client)
    runtime = Runtime(
        context=AgentContext(
            tenant_id="company_001",
            user_id="U1001",
        )
    )

    result = asyncio.run(
        nodes.query_order(
            {
                "message": "帮我查U2002的订单A1001",
                "intent": IntentType.ORDER_QUERY,
                "order_id": "A1001",
                "needs_clarification": False,
            },
            runtime,
        )
    )

    assert result["order_found"] is True
    assert result["order_data"]["orderId"] == "A1001"
    business_client.get_order.assert_awaited_once_with(
        tenant_id="company_001",
        user_id="U1001",
        order_id="A1001",
    )


def test_query_order_records_not_found() -> None:
    business_client = Mock(spec=BusinessServiceClient)
    business_client.get_order = AsyncMock(side_effect=OrderNotFoundError("A9999"))
    nodes = create_nodes(business_client=business_client)
    runtime = Runtime(
        context=AgentContext(
            tenant_id="company_001",
            user_id="U1001",
        )
    )

    result = asyncio.run(
        nodes.query_order(
            {
                "message": "查询A9999",
                "intent": IntentType.ORDER_QUERY,
                "order_id": "A9999",
                "needs_clarification": False,
            },
            runtime,
        )
    )

    assert result == {
        "order_found": False,
    }


def test_retrieve_knowledge_uses_runtime_tenant() -> None:
    knowledge_retriever = Mock(spec=KnowledgeRetriever)
    knowledge_retriever.retrieve = AsyncMock(
        return_value=[
            RetrievedChunk(
                document=Document(
                    page_content="未发货订单可直接申请取消。",
                    metadata={
                        "document_id": "refund-policy",
                        "title": "退款政策",
                        "section_title": "未发货订单",
                        "version": "1.0",
                    },
                ),
                score=0.82,
            )
        ]
    )
    nodes = SupportAgentNodes(
        intent_analyzer=Mock(spec=IntentAnalyzer),
        answer_generator=Mock(spec=AnswerGenerator),
        business_client=Mock(spec=BusinessServiceClient),
        knowledge_retriever=knowledge_retriever,
    )
    runtime = Runtime(
        context=AgentContext(
            tenant_id="company_001",
            user_id="U1001",
        )
    )

    result = asyncio.run(
        nodes.retrieve_knowledge(
            {
                "message": "未发货订单怎么退款？",
                "intent": IntentType.POLICY_QUERY,
                "needs_clarification": False,
            },
            runtime,
        )
    )

    knowledge_retriever.retrieve.assert_awaited_once_with(
        question="未发货订单怎么退款？",
        tenant_id="company_001",
    )
    assert "未发货订单可直接申请取消" in result["knowledge_context"]
    assert result["knowledge_references"] == [
        {
            "reference_number": 1,
            "document_id": "refund-policy",
            "title": "退款政策",
            "section_title": "未发货订单",
            "version": "1.0",
        }
    ]
    assert result["knowledge_status"] == "available"


def test_retrieve_knowledge_marks_unavailable_without_retriever() -> None:
    nodes = create_nodes()
    runtime = Runtime(
        context=AgentContext(
            tenant_id="company_001",
            user_id="U1001",
        )
    )

    result = asyncio.run(
        nodes.retrieve_knowledge(
            {
                "message": "退款政策是什么？",
                "intent": IntentType.POLICY_QUERY,
                "needs_clarification": False,
            },
            runtime,
        )
    )

    assert result == {
        "knowledge_status": "unavailable",
        "knowledge_context": "",
        "knowledge_references": [],
    }


def test_retrieve_knowledge_degrades_on_runtime_store_failure() -> None:
    knowledge_retriever = Mock(spec=KnowledgeRetriever)
    knowledge_retriever.retrieve = AsyncMock(
        side_effect=KnowledgeStoreUnavailableError("knowledge store is unavailable")
    )
    nodes = SupportAgentNodes(
        intent_analyzer=Mock(spec=IntentAnalyzer),
        answer_generator=Mock(spec=AnswerGenerator),
        business_client=Mock(spec=BusinessServiceClient),
        knowledge_retriever=knowledge_retriever,
    )
    runtime = Runtime(
        context=AgentContext(
            tenant_id="company_001",
            user_id="U1001",
        )
    )

    result = asyncio.run(
        nodes.retrieve_knowledge(
            {
                "message": "退款政策是什么？",
                "intent": IntentType.POLICY_QUERY,
                "needs_clarification": False,
            },
            runtime,
        )
    )

    assert result["knowledge_status"] == "unavailable"
    assert result["knowledge_references"] == []


def test_generate_knowledge_answer_degrades_without_rag() -> None:
    knowledge_answer_generator = Mock(spec=KnowledgeAnswerGenerator)
    knowledge_answer_generator.generate = AsyncMock()
    nodes = SupportAgentNodes(
        intent_analyzer=Mock(spec=IntentAnalyzer),
        answer_generator=Mock(spec=AnswerGenerator),
        business_client=Mock(spec=BusinessServiceClient),
        knowledge_answer_generator=knowledge_answer_generator,
    )

    result = asyncio.run(
        nodes.generate_knowledge_answer(
            {
                "message": "退款政策是什么？",
                "intent": IntentType.POLICY_QUERY,
                "needs_clarification": False,
                "knowledge_status": "unavailable",
                "knowledge_context": "",
                "knowledge_references": [],
            }
        )
    )

    assert result == {
        "answer": KNOWLEDGE_UNAVAILABLE_ANSWER,
    }
    knowledge_answer_generator.generate.assert_not_awaited()


def test_generate_knowledge_answer_uses_state_context() -> None:
    knowledge_answer_generator = Mock(spec=KnowledgeAnswerGenerator)
    knowledge_answer_generator.generate = AsyncMock(
        return_value="未发货订单可以直接申请取消。[资料1]"
    )
    nodes = SupportAgentNodes(
        intent_analyzer=Mock(spec=IntentAnalyzer),
        answer_generator=Mock(spec=AnswerGenerator),
        business_client=Mock(spec=BusinessServiceClient),
        knowledge_answer_generator=knowledge_answer_generator,
    )
    knowledge_context = '{"reference_documents": []}'

    result = asyncio.run(
        nodes.generate_knowledge_answer(
            {
                "message": "未发货订单怎么退款？",
                "intent": IntentType.POLICY_QUERY,
                "needs_clarification": False,
                "knowledge_context": knowledge_context,
                "knowledge_status": "available",
                "knowledge_references": [
                    {
                        "reference_number": 1,
                        "document_id": "refund-policy",
                        "title": "退款政策",
                        "section_title": "未发货订单",
                        "version": "1.0",
                    }
                ],
            }
        )
    )

    assert result == {
        "answer": "未发货订单可以直接申请取消。[资料1]",
    }
    call = knowledge_answer_generator.generate.await_args.kwargs
    assert call["message"] == "未发货订单怎么退款？"
    assert call["context"].text == knowledge_context
    assert call["context"].references[0].reference_number == 1
    assert call["context"].references[0].document_id == "refund-policy"


def test_generate_answer_uses_state_order_data() -> None:
    answer_generator = Mock(spec=AnswerGenerator)
    answer_generator.generate = AsyncMock(return_value="订单A1001已经发货。")
    nodes = create_nodes(answer_generator=answer_generator)
    order_data = {
        "orderId": "A1001",
        "status": "SHIPPED",
        "cancelable": False,
        "refundable": True,
    }

    result = asyncio.run(
        nodes.generate_answer(
            {
                "message": "订单A1001到哪了？",
                "intent": IntentType.ORDER_QUERY,
                "order_id": "A1001",
                "needs_clarification": False,
                "order_found": True,
                "order_data": order_data,
            }
        )
    )

    assert result == {
        "answer": "订单A1001已经发货。",
    }
    answer_generator.generate.assert_awaited_once_with(
        message="订单A1001到哪了？",
        order_data=order_data,
    )


def test_save_turn_appends_messages_and_tracks_active_order() -> None:
    nodes = create_nodes()

    result = nodes.save_turn(
        {
            "message": "订单A1001到哪了？",
            "conversation_history": [
                {
                    "role": "user",
                    "content": "你好",
                },
                {
                    "role": "assistant",
                    "content": "你好，请问需要什么帮助？",
                },
            ],
            "order_id": "A1001",
            "order_found": True,
            "answer": "订单A1001已经发货。",
        }
    )

    assert result == {
        "conversation_history": [
            {
                "role": "user",
                "content": "你好",
            },
            {
                "role": "assistant",
                "content": "你好，请问需要什么帮助？",
            },
            {
                "role": "user",
                "content": "订单A1001到哪了？",
            },
            {
                "role": "assistant",
                "content": "订单A1001已经发货。",
            },
        ],
        "active_order_id": "A1001",
    }


def test_save_turn_keeps_only_configured_recent_messages() -> None:
    nodes = SupportAgentNodes(
        intent_analyzer=Mock(spec=IntentAnalyzer),
        answer_generator=Mock(spec=AnswerGenerator),
        business_client=Mock(spec=BusinessServiceClient),
        history_max_messages=4,
    )

    result = nodes.save_turn(
        {
            "message": "第三个问题",
            "conversation_history": [
                {"role": "user", "content": "第一个问题"},
                {"role": "assistant", "content": "第一个回答"},
                {"role": "user", "content": "第二个问题"},
                {"role": "assistant", "content": "第二个回答"},
            ],
            "active_order_id": "A1001",
            "answer": "第三个回答",
        }
    )

    assert result == {
        "conversation_history": [
            {"role": "user", "content": "第二个问题"},
            {"role": "assistant", "content": "第二个回答"},
            {"role": "user", "content": "第三个问题"},
            {"role": "assistant", "content": "第三个回答"},
        ],
        "active_order_id": "A1001",
    }


def test_nodes_reject_odd_history_limit() -> None:
    with pytest.raises(
        ValueError,
        match="history_max_messages",
    ):
        SupportAgentNodes(
            intent_analyzer=Mock(spec=IntentAnalyzer),
            answer_generator=Mock(spec=AnswerGenerator),
            business_client=Mock(spec=BusinessServiceClient),
            history_max_messages=3,
        )
