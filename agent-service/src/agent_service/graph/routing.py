from typing import Literal

from agent_service.domain.intent import IntentType
from agent_service.graph.state import AgentState


def route_after_intent(
    state: AgentState,
) -> Literal[
    "request_clarification",
    "unsupported",
    "query_order",
    "retrieve_knowledge",
]:
    if state["needs_clarification"]:
        return "request_clarification"

    if state["intent"] is IntentType.POLICY_QUERY:
        return "retrieve_knowledge"

    if state["intent"] in {
        IntentType.ORDER_QUERY,
        IntentType.REFUND,
    }:
        return "query_order"

    return "unsupported"


def route_after_order(
    state: AgentState,
) -> Literal[
    "generate_answer",
    "order_not_found",
    "request_refund_approval",
]:
    if not state["order_found"]:
        return "order_not_found"

    if state["intent"] is IntentType.REFUND:
        return "request_refund_approval"

    return "generate_answer"


def route_after_refund_approval(
    state: AgentState,
) -> Literal[
    "submit_refund",
    "save_turn",
]:
    if state.get("refund_approved") is True:
        return "submit_refund"

    return "save_turn"
