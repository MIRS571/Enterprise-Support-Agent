import asyncio
from unittest.mock import AsyncMock

from agent_service.domain.intent import IntentAnalysis, IntentType
from agent_service.services.intent_analyzer import IntentAnalyzer


def test_policy_query_does_not_require_order_id() -> None:
    analyzer = object.__new__(IntentAnalyzer)
    analyzer._chain = AsyncMock()
    analyzer._chain.ainvoke.return_value = IntentAnalysis(
        intent=IntentType.POLICY_QUERY,
        order_id=None,
        needs_clarification=True,
    )

    result = asyncio.run(analyzer.analyze("已经拆封的软件支持无理由退款吗？"))

    assert result.intent is IntentType.POLICY_QUERY
    assert result.order_id is None
    assert result.needs_clarification is False


def test_refund_without_order_id_requires_clarification() -> None:
    analyzer = object.__new__(IntentAnalyzer)
    analyzer._chain = AsyncMock()
    analyzer._chain.ainvoke.return_value = IntentAnalysis(
        intent=IntentType.REFUND,
        order_id=None,
        needs_clarification=False,
    )

    result = asyncio.run(analyzer.analyze("我要退款"))

    assert result.intent is IntentType.REFUND
    assert result.order_id is None
    assert result.needs_clarification is True
