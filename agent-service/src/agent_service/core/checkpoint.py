from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from agent_service.core.config import Settings
from agent_service.integrations.conversation_threads import (
    ConversationThreadRepository,
)


@dataclass(frozen=True, slots=True)
class PersistenceResources:
    checkpointer: BaseCheckpointSaver | None
    thread_repository: ConversationThreadRepository | None


@asynccontextmanager
async def open_checkpointer(
    settings: Settings,
) -> AsyncIterator[PersistenceResources]:
    if not settings.checkpoint_enabled:
        yield PersistenceResources(
            checkpointer=None,
            thread_repository=None,
        )
        return

    database_url = settings.checkpoint_database_url
    if database_url is None:
        raise RuntimeError("checkpoint database URL is missing")

    serializer = JsonPlusSerializer(
        allowed_msgpack_modules=[],
    )
    pool = AsyncConnectionPool(
        database_url.get_secret_value(),
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        min_size=1,
        max_size=5,
        open=False,
    )
    async with pool:
        checkpointer = AsyncPostgresSaver(
            pool,
            serde=serializer,
        )
        await checkpointer.setup()
        thread_repository = ConversationThreadRepository(pool)
        await thread_repository.setup()
        yield PersistenceResources(
            checkpointer=checkpointer,
            thread_repository=thread_repository,
        )
