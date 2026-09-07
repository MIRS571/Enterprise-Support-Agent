from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent_service.graph.nodes import SupportAgentNodes
from agent_service.graph.routing import (
    route_after_intent,
    route_after_order,
    route_after_refund_approval,
)
from agent_service.graph.state import AgentContext, AgentState


def build_support_agent_graph(
    nodes: SupportAgentNodes,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    builder = StateGraph(
        AgentState,
        context_schema=AgentContext,
    )

    builder.add_node("analyze_intent", nodes.analyze_intent)
    builder.add_node(
        "request_clarification",
        nodes.request_clarification,
    )
    builder.add_node("unsupported", nodes.unsupported)
    builder.add_node("query_order", nodes.query_order)
    builder.add_node("order_not_found", nodes.order_not_found)
    builder.add_node("generate_answer", nodes.generate_answer)
    builder.add_node(
        "request_refund_approval",
        nodes.request_refund_approval,
    )
    builder.add_node("submit_refund", nodes.submit_refund)
    builder.add_node(
        "retrieve_knowledge",
        nodes.retrieve_knowledge,
    )
    builder.add_node(
        "generate_knowledge_answer",
        nodes.generate_knowledge_answer,
    )
    builder.add_node("save_turn", nodes.save_turn)

    builder.add_edge(START, "analyze_intent")
    builder.add_conditional_edges(
        "analyze_intent",
        route_after_intent,
    )
    builder.add_edge("request_clarification", "save_turn")
    builder.add_edge("unsupported", "save_turn")
    builder.add_conditional_edges(
        "query_order",
        route_after_order,
    )
    builder.add_edge("order_not_found", "save_turn")
    builder.add_edge("generate_answer", "save_turn")
    builder.add_conditional_edges(
        "request_refund_approval",
        route_after_refund_approval,
    )
    builder.add_edge("submit_refund", "save_turn")
    builder.add_edge(
        "retrieve_knowledge",
        "generate_knowledge_answer",
    )
    builder.add_edge("generate_knowledge_answer", "save_turn")
    builder.add_edge("save_turn", END)

    return builder.compile(checkpointer=checkpointer)
