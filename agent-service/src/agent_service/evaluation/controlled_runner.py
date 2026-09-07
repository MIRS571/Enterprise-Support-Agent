import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from langchain_core.documents import Document
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime

from agent_service.domain.intent import IntentAnalysis, IntentType
from agent_service.domain.order import OrderResponse, OrderStatus
from agent_service.evaluation.agent import (
    AgentEvaluationCase,
    AgentEvaluationObservation,
    ExpectedCallCounts,
    KnowledgeRetrievalObservation,
    OrderLookupObservation,
)
from agent_service.graph.builder import build_support_agent_graph
from agent_service.graph.nodes import SupportAgentNodes
from agent_service.graph.state import AgentContext, AgentState
from agent_service.rag.context import FormattedKnowledgeContext
from agent_service.services.knowledge_answer_generator import NO_KNOWLEDGE_ANSWER

_RUNTIME_NODE_NAMES = frozenset(
    {
        "query_order",
        "retrieve_knowledge",
        "submit_refund",
    }
)


@dataclass(frozen=True)
class _ControlledChunk:
    document: Document
    score: float


@dataclass
class _RunRecorder:
    visited_nodes: list[str] = field(default_factory=list)
    intent_analysis: int = 0
    order_answer_generation: int = 0
    knowledge_answer_generation: int = 0
    refund_submission: int = 0
    order_lookups: list[OrderLookupObservation] = field(default_factory=list)
    knowledge_retrievals: list[KnowledgeRetrievalObservation] = field(
        default_factory=list
    )


class _ControlledIntentAnalyzer:
    def __init__(
        self,
        *,
        case: AgentEvaluationCase,
        recorder: _RunRecorder,
    ) -> None:
        self._case = case
        self._recorder = recorder

    async def analyze(self, _message: str) -> IntentAnalysis:
        self._recorder.intent_analysis += 1
        return IntentAnalysis(
            intent=self._case.deterministic.intent,
            order_id=self._case.deterministic.order_id,
            needs_clarification=(
                "request_clarification" in self._case.deterministic.expected_nodes
            ),
        )


class _ControlledOrderService:
    def __init__(self, recorder: _RunRecorder) -> None:
        self._recorder = recorder

    async def get_order(
        self,
        *,
        tenant_id: str,
        user_id: str,
        order_id: str,
    ) -> OrderResponse:
        self._recorder.order_lookups.append(
            OrderLookupObservation(
                tenant_id=tenant_id,
                user_id=user_id,
                order_id=order_id,
            )
        )
        return _controlled_order(order_id)

    async def request_refund(
        self,
        *,
        tenant_id: str,
        user_id: str,
        order_id: str,
        idempotency_key: str,
    ) -> OrderResponse:
        del tenant_id, user_id, idempotency_key
        self._recorder.refund_submission += 1
        return _controlled_order(order_id, status=OrderStatus.REFUNDING)


class _ControlledAnswerGenerator:
    def __init__(
        self,
        *,
        case: AgentEvaluationCase,
        recorder: _RunRecorder,
    ) -> None:
        self._case = case
        self._recorder = recorder

    async def generate(
        self,
        *,
        message: str,
        order_data: dict[str, object],
    ) -> str:
        del message, order_data
        self._recorder.order_answer_generation += 1
        return _answer_with_required_facts(self._case)


class _ControlledKnowledgeRetriever:
    def __init__(
        self,
        *,
        case: AgentEvaluationCase,
        recorder: _RunRecorder,
    ) -> None:
        self._case = case
        self._recorder = recorder

    async def retrieve(
        self,
        *,
        question: str,
        tenant_id: str,
    ) -> list[_ControlledChunk]:
        del question
        self._recorder.knowledge_retrievals.append(
            KnowledgeRetrievalObservation(tenant_id=tenant_id)
        )
        content = _answer_with_required_facts(self._case)
        return [
            _ControlledChunk(
                document=Document(
                    page_content=content,
                    metadata={
                        "tenant_id": tenant_id,
                        "document_id": document_id,
                        "title": "受控评测知识",
                        "section_title": "评测章节",
                        "version": "evaluation-v1",
                    },
                ),
                score=0.99,
            )
            for document_id in self._case.deterministic.source_document_ids
        ]


class _ControlledKnowledgeAnswerGenerator:
    def __init__(
        self,
        *,
        case: AgentEvaluationCase,
        recorder: _RunRecorder,
    ) -> None:
        self._case = case
        self._recorder = recorder

    async def generate(
        self,
        *,
        message: str,
        context: FormattedKnowledgeContext,
    ) -> str:
        del message
        self._recorder.knowledge_answer_generation += 1
        if not context.text:
            return NO_KNOWLEDGE_ANSWER
        return f"{_answer_with_required_facts(self._case)}[资料1]"


class _TracingNodes:
    """Record real graph node entry without changing production nodes."""

    def __init__(
        self,
        *,
        delegate: SupportAgentNodes,
        recorder: _RunRecorder,
    ) -> None:
        self._delegate = delegate
        self._recorder = recorder

    def __getattr__(self, name: str) -> Callable[..., Awaitable[object]]:
        target = getattr(self._delegate, name)

        if name in _RUNTIME_NODE_NAMES:

            async def invoke_with_runtime(
                state: AgentState,
                runtime: Runtime[AgentContext],
            ) -> object:
                self._recorder.visited_nodes.append(name)
                return await _await_if_needed(target(state, runtime))

            return invoke_with_runtime

        async def invoke_with_state(state: AgentState) -> object:
            self._recorder.visited_nodes.append(name)
            return await _await_if_needed(target(state))

        return invoke_with_state


async def run_controlled_agent_case(
    case: AgentEvaluationCase,
) -> AgentEvaluationObservation:
    """Run the real graph with deterministic in-memory dependencies."""

    recorder = _RunRecorder()
    real_nodes = SupportAgentNodes(
        intent_analyzer=_ControlledIntentAnalyzer(
            case=case,
            recorder=recorder,
        ),
        answer_generator=_ControlledAnswerGenerator(
            case=case,
            recorder=recorder,
        ),
        business_client=_ControlledOrderService(recorder),
        knowledge_retriever=_ControlledKnowledgeRetriever(
            case=case,
            recorder=recorder,
        ),
        knowledge_answer_generator=_ControlledKnowledgeAnswerGenerator(
            case=case,
            recorder=recorder,
        ),
    )
    graph = build_support_agent_graph(
        _TracingNodes(
            delegate=real_nodes,
            recorder=recorder,
        ),
        checkpointer=InMemorySaver(),
    )
    result = await graph.ainvoke(
        {"message": case.question},
        config={
            "configurable": {
                "thread_id": f"controlled-evaluation-{case.case_id}",
            }
        },
        context=AgentContext(
            tenant_id=case.tenant_id,
            user_id=case.user_id,
        ),
    )

    interrupts = result.get("__interrupt__", ())
    outcome = "approval_required" if interrupts else "reply"
    answer = result.get("answer", "")
    if interrupts:
        answer = json.dumps(
            interrupts[0].value,
            ensure_ascii=False,
            default=str,
        )
    if not isinstance(answer, str):
        raise TypeError("controlled graph returned an invalid answer")

    intent = IntentType(result.get("intent"))
    references = result.get("knowledge_references", [])
    if not isinstance(references, list):
        raise TypeError("controlled graph returned invalid knowledge references")

    return AgentEvaluationObservation(
        case_id=case.case_id,
        intent=intent,
        outcome=outcome,
        visited_nodes=recorder.visited_nodes,
        calls=ExpectedCallCounts(
            intent_analysis=recorder.intent_analysis,
            order_lookup=len(recorder.order_lookups),
            knowledge_retrieval=len(recorder.knowledge_retrievals),
            order_answer_generation=recorder.order_answer_generation,
            knowledge_answer_generation=(recorder.knowledge_answer_generation),
            refund_submission=recorder.refund_submission,
        ),
        order_id=result.get("order_id"),
        source_document_ids=[
            str(reference["document_id"])
            for reference in references
            if isinstance(reference, dict) and "document_id" in reference
        ],
        answer=answer,
        order_lookups=recorder.order_lookups,
        knowledge_retrievals=recorder.knowledge_retrievals,
    )


async def _await_if_needed(value: object) -> object:
    if inspect.isawaitable(value):
        return await value
    return value


def _controlled_order(
    order_id: str,
    *,
    status: OrderStatus = OrderStatus.SHIPPED,
) -> OrderResponse:
    return OrderResponse(
        orderId=order_id,
        productName="机械键盘",
        quantity=1,
        totalAmount=Decimal("299.00"),
        status=status,
        createdAt=datetime(2026, 8, 20, tzinfo=UTC),
        cancelable=False,
        refundable=status is OrderStatus.SHIPPED,
    )


def _answer_with_required_facts(case: AgentEvaluationCase) -> str:
    if case.quality.required_facts:
        return "；".join(case.quality.required_facts)
    return "受控评测回答。"
