import asyncio
import importlib
from unittest.mock import AsyncMock, Mock

from agent_service.core.config import Settings


class FakeAsyncContextManager:
    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        return None


def test_open_checkpointer_returns_none_when_disabled() -> None:
    checkpoint_module = importlib.import_module("agent_service.core.checkpoint")
    settings = Settings(
        _env_file=None,
        checkpoint_enabled=False,
    )

    async def scenario() -> None:
        async with checkpoint_module.open_checkpointer(settings) as resources:
            assert resources.checkpointer is None
            assert resources.thread_repository is None

    asyncio.run(scenario())


def test_open_checkpointer_sets_up_postgres(
    monkeypatch,
) -> None:
    checkpoint_module = importlib.import_module("agent_service.core.checkpoint")
    settings = Settings(
        _env_file=None,
        checkpoint_enabled=True,
        checkpoint_database_url=("postgresql://agent:secret@localhost/checkpoint"),
    )
    checkpointer = Mock(name="checkpointer")
    checkpointer.setup = AsyncMock()
    pool = FakeAsyncContextManager(None)
    pool._value = pool
    pool_factory = Mock(return_value=pool)
    monkeypatch.setattr(
        checkpoint_module,
        "AsyncConnectionPool",
        pool_factory,
    )
    checkpointer_factory = Mock(return_value=checkpointer)
    monkeypatch.setattr(
        checkpoint_module,
        "AsyncPostgresSaver",
        checkpointer_factory,
    )
    thread_repository = Mock(name="thread_repository")
    thread_repository.setup = AsyncMock()
    repository_factory = Mock(return_value=thread_repository)
    monkeypatch.setattr(
        checkpoint_module,
        "ConversationThreadRepository",
        repository_factory,
    )

    async def scenario() -> None:
        async with checkpoint_module.open_checkpointer(settings) as resources:
            assert resources.checkpointer is checkpointer
            assert resources.thread_repository is thread_repository

    asyncio.run(scenario())

    pool_factory.assert_called_once()
    assert pool_factory.call_args.args[0] == (
        "postgresql://agent:secret@localhost/checkpoint"
    )
    checkpointer_factory.assert_called_once()
    assert checkpointer_factory.call_args.args[0] is pool
    assert checkpointer_factory.call_args.kwargs["serde"] is not None
    checkpointer.setup.assert_awaited_once_with()
    repository_factory.assert_called_once_with(pool)
    thread_repository.setup.assert_awaited_once_with()
