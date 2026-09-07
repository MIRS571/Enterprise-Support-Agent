import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from qdrant_client.http.exceptions import (
    ResponseHandlingException,
    UnexpectedResponse,
)

from agent_service.core.checkpoint import open_checkpointer
from agent_service.core.config import get_settings
from agent_service.core.redis import open_redis
from agent_service.core.redis_keys import RedisKeyBuilder
from agent_service.graph import SupportAgentNodes, build_support_agent_graph
from agent_service.integrations.business_service import (
    BusinessServiceClient,
    CachedOrderService,
    OrderService,
)
from agent_service.integrations.llm import create_chat_model
from agent_service.rag import (
    KnowledgeRetriever,
    RagAvailability,
    RagAvailabilityStatus,
    create_cross_encoder_reranker,
    create_embedding_resources,
    create_vector_store_resources,
    is_knowledge_store_unavailable_error,
)
from agent_service.services import (
    AnswerGenerator,
    ChatRateLimiter,
    ConversationThreadService,
    IntentAnalyzer,
    KnowledgeAnswerGenerator,
    KnowledgeIngestionService,
    SupportAgentService,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    vector_store_resources = None
    timeout = httpx.Timeout(settings.business_service_timeout_seconds)
    model = create_chat_model(settings)
    intent_analyzer = IntentAnalyzer(model)
    answer_generator = AnswerGenerator(model)
    knowledge_answer_generator = KnowledgeAnswerGenerator(model)
    knowledge_retriever = None
    app.state.knowledge_ingestion_service = None
    app.state.conversation_thread_service = None
    app.state.redis_client = None
    app.state.chat_rate_limiter = None
    app.state.redis_key_builder = RedisKeyBuilder(
        prefix=settings.redis_key_prefix,
        environment=settings.environment,
    )
    rag_availability = RagAvailability(
        status=(
            RagAvailabilityStatus.DOWN
            if settings.rag_enabled
            else RagAvailabilityStatus.DISABLED
        )
    )
    app.state.rag_availability = rag_availability

    try:
        if settings.rag_enabled:
            embedding_resources = create_embedding_resources(settings)
            reranker = create_cross_encoder_reranker(settings)
            try:
                vector_store_resources = create_vector_store_resources(
                    settings=settings,
                    embeddings=embedding_resources,
                )
            except (
                ResponseHandlingException,
                UnexpectedResponse,
            ) as error:
                if not is_knowledge_store_unavailable_error(error):
                    raise
                logger.exception("Qdrant is unavailable; starting with RAG degraded")
            else:
                rag_availability.mark_up()
                knowledge_retriever = KnowledgeRetriever(
                    store=vector_store_resources.store,
                    top_k=settings.rag_top_k,
                    candidate_k=settings.rag_candidate_k,
                    reranker=reranker,
                    availability=rag_availability,
                )
                app.state.knowledge_ingestion_service = KnowledgeIngestionService(
                    settings=settings,
                    resources=vector_store_resources,
                )

        async with (
            open_checkpointer(settings) as persistence,
            open_redis(settings) as redis_resources,
            httpx.AsyncClient(
                base_url=str(settings.business_service_base_url),
                timeout=timeout,
                trust_env=False,
            ) as http_client,
        ):
            business_client = BusinessServiceClient(
                http_client=http_client,
                max_retries=settings.business_service_max_retries,
            )
            order_service: OrderService = business_client
            if redis_resources.client is not None:
                order_service = CachedOrderService(
                    delegate=business_client,
                    redis_client=redis_resources.client,
                    key_builder=app.state.redis_key_builder,
                    ttl_seconds=settings.order_cache_ttl_seconds,
                    availability=redis_resources.availability,
                )
                app.state.chat_rate_limiter = ChatRateLimiter(
                    redis_client=redis_resources.client,
                    key_builder=app.state.redis_key_builder,
                    limit=settings.chat_rate_limit_requests,
                    window_seconds=(settings.chat_rate_limit_window_seconds),
                    availability=redis_resources.availability,
                )
            app.state.redis_client = redis_resources.client
            app.state.redis_availability = redis_resources.availability
            nodes = SupportAgentNodes(
                intent_analyzer=intent_analyzer,
                answer_generator=answer_generator,
                business_client=order_service,
                knowledge_retriever=knowledge_retriever,
                knowledge_answer_generator=(knowledge_answer_generator),
            )
            graph = build_support_agent_graph(
                nodes,
                checkpointer=persistence.checkpointer,
            )
            app.state.business_service_client = business_client
            app.state.conversation_thread_repository = persistence.thread_repository
            conversation_thread_service = None
            if persistence.thread_repository is not None:
                conversation_thread_service = ConversationThreadService(
                    persistence.thread_repository
                )
                app.state.conversation_thread_service = conversation_thread_service
            app.state.support_agent_service = SupportAgentService(
                graph=graph,
                conversation_thread_service=(conversation_thread_service),
            )

            yield
    finally:
        if vector_store_resources is not None:
            vector_store_resources.client.close()
