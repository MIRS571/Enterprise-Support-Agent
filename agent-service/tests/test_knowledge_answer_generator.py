import asyncio
from unittest.mock import AsyncMock

from agent_service.rag.context import FormattedKnowledgeContext
from agent_service.services.knowledge_answer_generator import (
    NO_KNOWLEDGE_ANSWER,
    KnowledgeAnswerGenerator,
)


def create_generator_with_mock_chain() -> tuple[
    KnowledgeAnswerGenerator,
    AsyncMock,
]:
    generator = object.__new__(KnowledgeAnswerGenerator)
    chain = AsyncMock()
    generator._chain = chain
    return generator, chain


def test_empty_context_returns_fixed_answer_without_model_call() -> None:
    generator, chain = create_generator_with_mock_chain()

    answer = asyncio.run(
        generator.generate(
            message="软件拆封后能退款吗？",
            context=FormattedKnowledgeContext(
                text="",
                references=(),
            ),
        )
    )

    assert answer == NO_KNOWLEDGE_ANSWER
    chain.ainvoke.assert_not_awaited()


def test_non_empty_context_calls_model_with_formatted_data() -> None:
    generator, chain = create_generator_with_mock_chain()
    chain.ainvoke.return_value = "  可以参考退款政策。[资料1]  "
    context = FormattedKnowledgeContext(
        text='{"reference_documents": []}',
        references=(),
    )

    answer = asyncio.run(
        generator.generate(
            message="  怎么退款？  ",
            context=context,
        )
    )

    assert answer == "可以参考退款政策。[资料1]"
    chain.ainvoke.assert_awaited_once_with(
        {
            "message": "怎么退款？",
            "context": context.text,
        }
    )
