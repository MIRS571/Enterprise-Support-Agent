import pytest

from agent_service.domain.intent import IntentType
from agent_service.graph import route_after_intent


@pytest.mark.parametrize(
    ("intent", "needs_clarification", "expected_node"),
    [
        (
            IntentType.REFUND,
            True,
            "request_clarification",
        ),
        (
            IntentType.COMPLAINT,
            False,
            "unsupported",
        ),
        (
            IntentType.ORDER_QUERY,
            False,
            "query_order",
        ),
        (
            IntentType.POLICY_QUERY,
            False,
            "retrieve_knowledge",
        ),
    ],
)
def test_route_after_intent(
    intent: IntentType,
    needs_clarification: bool,
    expected_node: str,
) -> None:
    result = route_after_intent(
        {
            "message": "测试消息",
            "intent": intent,
            "order_id": "A1001",
            "needs_clarification": needs_clarification,
        }
    )

    assert result == expected_node
