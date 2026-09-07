import asyncio
import importlib
from unittest.mock import AsyncMock, Mock
from uuid import UUID

from agent_service.integrations.conversation_threads import (
    ConversationThreadRepository,
)


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


def create_repository(
    connection: Mock,
) -> ConversationThreadRepository:
    pool = Mock(name="pool")
    pool.connection.return_value = FakeAsyncContextManager(connection)
    return ConversationThreadRepository(pool)


def test_create_generates_server_owned_identifiers(
    monkeypatch,
) -> None:
    thread_module = importlib.import_module(
        "agent_service.integrations.conversation_threads"
    )
    connection = Mock(name="connection")
    connection.execute = AsyncMock()
    repository = create_repository(connection)
    public_id = UUID("11111111-1111-4111-8111-111111111111")
    checkpoint_key = UUID("22222222-2222-4222-8222-222222222222")
    uuid_factory = Mock(side_effect=[public_id, checkpoint_key])
    monkeypatch.setattr(thread_module, "uuid4", uuid_factory)

    thread = asyncio.run(
        repository.create(
            tenant_id="company_001",
            user_id="U1001",
        )
    )

    assert thread.thread_id == str(public_id)
    assert thread.checkpoint_key == str(checkpoint_key)
    assert thread.tenant_id == "company_001"
    assert thread.user_id == "U1001"
    parameters = connection.execute.await_args.args[1]
    assert parameters == (
        str(public_id),
        "company_001",
        "U1001",
        str(checkpoint_key),
    )


def test_find_owned_filters_in_database() -> None:
    cursor = Mock(name="cursor")
    cursor.fetchone = AsyncMock(
        return_value={
            "thread_id": UUID("11111111-1111-4111-8111-111111111111"),
            "tenant_id": "company_001",
            "user_id": "U1001",
            "checkpoint_key": UUID("22222222-2222-4222-8222-222222222222"),
        }
    )
    connection = Mock(name="connection")
    connection.execute = AsyncMock(return_value=cursor)
    repository = create_repository(connection)

    thread = asyncio.run(
        repository.find_owned(
            thread_id="11111111-1111-4111-8111-111111111111",
            tenant_id="company_001",
            user_id="U1001",
        )
    )

    assert thread is not None
    assert thread.user_id == "U1001"
    assert connection.execute.await_args.args[1] == (
        "11111111-1111-4111-8111-111111111111",
        "company_001",
        "U1001",
    )


def test_find_owned_returns_none_without_leaking_owner() -> None:
    cursor = Mock(name="cursor")
    cursor.fetchone = AsyncMock(return_value=None)
    connection = Mock(name="connection")
    connection.execute = AsyncMock(return_value=cursor)
    repository = create_repository(connection)

    thread = asyncio.run(
        repository.find_owned(
            thread_id="11111111-1111-4111-8111-111111111111",
            tenant_id="company_001",
            user_id="U2002",
        )
    )

    assert thread is None
