import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from qdrant_client.http.exceptions import ResponseHandlingException

from agent_service.core.config import Settings
from agent_service.rag import RagAvailabilityStatus


def test_lifespan_wires_and_closes_rag_resources(
    monkeypatch,
) -> None:
    lifespan_module = importlib.import_module("agent_service.core.lifespan")
    settings = Settings(
        _env_file=None,
        rag_enabled=True,
        rag_top_k=3,
    )
    model = Mock(name="model")
    intent_analyzer = Mock(name="intent_analyzer")
    answer_generator = Mock(name="answer_generator")
    knowledge_answer_generator = Mock(name="knowledge_answer_generator")
    embeddings = Mock(name="embeddings")
    qdrant_client = Mock(name="qdrant_client")
    vector_store = Mock(name="vector_store")
    reranker = Mock(name="reranker")
    vector_store_resources = SimpleNamespace(
        client=qdrant_client,
        store=vector_store,
    )
    knowledge_retriever = Mock(name="knowledge_retriever")
    ingestion_service = Mock(name="ingestion_service")
    graph = Mock(name="graph")

    monkeypatch.setattr(
        lifespan_module,
        "get_settings",
        Mock(return_value=settings),
    )
    monkeypatch.setattr(
        lifespan_module,
        "create_chat_model",
        Mock(return_value=model),
    )
    monkeypatch.setattr(
        lifespan_module,
        "IntentAnalyzer",
        Mock(return_value=intent_analyzer),
    )
    monkeypatch.setattr(
        lifespan_module,
        "AnswerGenerator",
        Mock(return_value=answer_generator),
    )
    monkeypatch.setattr(
        lifespan_module,
        "KnowledgeAnswerGenerator",
        Mock(return_value=knowledge_answer_generator),
    )
    embedding_factory = Mock(return_value=embeddings)
    monkeypatch.setattr(
        lifespan_module,
        "create_embedding_resources",
        embedding_factory,
    )
    reranker_factory = Mock(return_value=reranker)
    monkeypatch.setattr(
        lifespan_module,
        "create_cross_encoder_reranker",
        reranker_factory,
    )
    vector_store_factory = Mock(return_value=vector_store_resources)
    monkeypatch.setattr(
        lifespan_module,
        "create_vector_store_resources",
        vector_store_factory,
    )
    retriever_factory = Mock(return_value=knowledge_retriever)
    monkeypatch.setattr(
        lifespan_module,
        "KnowledgeRetriever",
        retriever_factory,
    )
    ingestion_factory = Mock(return_value=ingestion_service)
    monkeypatch.setattr(
        lifespan_module,
        "KnowledgeIngestionService",
        ingestion_factory,
    )
    graph_factory = Mock(return_value=graph)
    monkeypatch.setattr(
        lifespan_module,
        "build_support_agent_graph",
        graph_factory,
    )

    app = FastAPI()

    async def scenario() -> None:
        async with lifespan_module.lifespan(app):
            nodes = graph_factory.call_args.args[0]
            assert nodes._knowledge_retriever is knowledge_retriever
            assert nodes._knowledge_answer_generator is knowledge_answer_generator
            assert app.state.knowledge_ingestion_service is ingestion_service
            assert app.state.rag_availability.status is RagAvailabilityStatus.UP

    asyncio.run(scenario())

    embedding_factory.assert_called_once_with(settings)
    reranker_factory.assert_called_once_with(settings)
    vector_store_factory.assert_called_once_with(
        settings=settings,
        embeddings=embeddings,
    )
    retriever_factory.assert_called_once_with(
        store=vector_store,
        top_k=3,
        candidate_k=10,
        reranker=reranker,
        availability=app.state.rag_availability,
    )
    ingestion_factory.assert_called_once_with(
        settings=settings,
        resources=vector_store_resources,
    )
    qdrant_client.close.assert_called_once_with()


def test_lifespan_starts_degraded_when_qdrant_is_unavailable(
    monkeypatch,
) -> None:
    lifespan_module = importlib.import_module("agent_service.core.lifespan")
    settings = Settings(
        _env_file=None,
        rag_enabled=True,
    )
    graph = Mock(name="graph")

    monkeypatch.setattr(
        lifespan_module,
        "get_settings",
        Mock(return_value=settings),
    )
    monkeypatch.setattr(
        lifespan_module,
        "create_chat_model",
        Mock(return_value=Mock(name="model")),
    )
    monkeypatch.setattr(
        lifespan_module,
        "create_embedding_resources",
        Mock(return_value=Mock(name="embeddings")),
    )
    monkeypatch.setattr(
        lifespan_module,
        "create_cross_encoder_reranker",
        Mock(return_value=Mock(name="reranker")),
    )
    monkeypatch.setattr(
        lifespan_module,
        "create_vector_store_resources",
        Mock(
            side_effect=ResponseHandlingException(
                ConnectionError("Qdrant connection failed")
            )
        ),
    )
    monkeypatch.setattr(
        lifespan_module,
        "build_support_agent_graph",
        Mock(return_value=graph),
    )

    app = FastAPI()

    async def scenario() -> None:
        async with lifespan_module.lifespan(app):
            assert app.state.rag_availability.status is RagAvailabilityStatus.DOWN
            assert app.state.knowledge_ingestion_service is None
            assert app.state.support_agent_service._graph is graph

    asyncio.run(scenario())
