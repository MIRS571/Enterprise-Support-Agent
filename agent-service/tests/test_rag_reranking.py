import asyncio

import pytest

from agent_service.rag.reranking import CrossEncoderReranker


class FakeCrossEncoder:
    def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        batch_size: int,
    ) -> list[float]:
        assert query == "退款问题"
        assert documents == ["文档一", "文档二"]
        assert batch_size == 4
        return [0.25, 0.75]


def test_cross_encoder_scores_documents_off_event_loop() -> None:
    reranker = CrossEncoderReranker(
        model=FakeCrossEncoder(),
        batch_size=4,
    )

    scores = asyncio.run(
        reranker.score(
            question="退款问题",
            documents=["文档一", "文档二"],
        )
    )

    assert scores == [0.25, 0.75]


def test_cross_encoder_rejects_mismatched_score_count() -> None:
    model = FakeCrossEncoder()
    model.rerank = lambda *_args, **_kwargs: [0.5]  # type: ignore[method-assign]
    reranker = CrossEncoderReranker(model=model, batch_size=4)

    with pytest.raises(RuntimeError, match="different number of scores"):
        asyncio.run(
            reranker.score(
                question="退款问题",
                documents=["文档一", "文档二"],
            )
        )
