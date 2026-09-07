import asyncio
from collections.abc import Iterable, Sequence
from typing import Protocol

from agent_service.core.config import Settings


class CrossEncoderModel(Protocol):
    def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        batch_size: int,
    ) -> Iterable[float]: ...


class CrossEncoderReranker:
    def __init__(
        self,
        *,
        model: CrossEncoderModel,
        batch_size: int,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")

        self._model = model
        self._batch_size = batch_size

    async def score(
        self,
        *,
        question: str,
        documents: Sequence[str],
    ) -> list[float]:
        if not documents:
            return []

        scores = await asyncio.to_thread(
            self._score_sync,
            question,
            list(documents),
        )
        if len(scores) != len(documents):
            raise RuntimeError(
                "Cross-Encoder returned a different number of scores than documents"
            )
        return scores

    def _score_sync(
        self,
        question: str,
        documents: list[str],
    ) -> list[float]:
        return [
            float(score)
            for score in self._model.rerank(
                question,
                documents,
                batch_size=self._batch_size,
            )
        ]


def create_cross_encoder_reranker(
    settings: Settings,
) -> CrossEncoderReranker | None:
    if not settings.rag_reranker_enabled:
        return None

    # FastEmbed loads ONNX Runtime native libraries. Import it only when the
    # application actually enables reranking so ordinary API and unit-test
    # imports do not pay that startup cost or require the native runtime.
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    model_options = {}
    if settings.rag_reranker_model_path is not None:
        model_options["specific_model_path"] = str(
            settings.rag_reranker_model_path.resolve()
        )

    return CrossEncoderReranker(
        model=TextCrossEncoder(
            model_name=settings.rag_reranker_model_name,
            **model_options,
        ),
        batch_size=settings.rag_reranker_batch_size,
    )
