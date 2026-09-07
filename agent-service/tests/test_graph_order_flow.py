from unittest.mock import Mock

import pytest

from agent_service.domain.intent import IntentType
from agent_service.graph import SupportAgentNodes
from agent_service.graph.routing import (
    route_after_order,
    route_after_refund_approval,
)
from agent_service.integrations.business_service import BusinessServiceClient
from agent_service.services import AnswerGenerator, IntentAnalyzer


@pytest.mark.parametrize(
    ("order_found", "intent", "expected_node"),
    [
        (True, IntentType.ORDER_QUERY, "generate_answer"),
        (True, IntentType.REFUND, "request_refund_approval"),
        (False, IntentType.ORDER_QUERY, "order_not_found"),
        (False, IntentType.REFUND, "order_not_found"),
    ],
)
def test_route_after_order(
    order_found: bool,
    intent: IntentType,
    expected_node: str,
) -> None:
    result = route_after_order(
        {
            "message": "查询订单A1001",
            "intent": intent,
            "order_id": "A1001",
            "needs_clarification": False,
            "order_found": order_found,
        }
    )

    assert result == expected_node


@pytest.mark.parametrize(
    ("approved", "expected_node"),
    [
        (True, "submit_refund"),
        (False, "save_turn"),
        (None, "save_turn"),
    ],
)
def test_route_after_refund_approval(
    approved: bool | None,
    expected_node: str,
) -> None:
    result = route_after_refund_approval(
        {
            "message": "申请退款A1001",
            "intent": IntentType.REFUND,
            "order_id": "A1001",
            "order_found": True,
            "refund_approved": approved,
        }
    )

    assert result == expected_node


def test_order_not_found_returns_fixed_answer() -> None:
    nodes = SupportAgentNodes(
        intent_analyzer=Mock(spec=IntentAnalyzer),
        answer_generator=Mock(spec=AnswerGenerator),
        business_client=Mock(spec=BusinessServiceClient),
    )

    result = nodes.order_not_found(
        {
            "message": "查询A9999",
            "intent": IntentType.ORDER_QUERY,
            "order_id": "A9999",
            "needs_clarification": False,
            "order_found": False,
        }
    )

    assert result == {
        "answer": "没有找到订单 A9999，请检查订单号是否正确。",
    }
