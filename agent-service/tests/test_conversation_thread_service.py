import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from agent_service.integrations.conversation_threads import (
    ConversationThread,
    ConversationThreadRepository,
)
from agent_service.services import (
    ConversationThreadNotFoundError,
    ConversationThreadService,
)


def test_create_thread_returns_public_identifier() -> None:
    repository = Mock(spec=ConversationThreadRepository)
    repository.create = AsyncMock(
        return_value=ConversationThread(
            thread_id="11111111-1111-4111-8111-111111111111",
            tenant_id="company_001",
            user_id="U1001",
            checkpoint_key=("22222222-2222-4222-8222-222222222222"),
        )
    )
    service = ConversationThreadService(repository)

    thread_id = asyncio.run(
        service.create_thread(
            tenant_id="company_001",
            user_id="U1001",
        )
    )

    assert thread_id == "11111111-1111-4111-8111-111111111111"
    repository.create.assert_awaited_once_with(
        tenant_id="company_001",
        user_id="U1001",
    )


def test_resolve_checkpoint_key_returns_internal_key() -> None:
    repository = Mock(spec=ConversationThreadRepository)
    repository.find_owned = AsyncMock(
        return_value=ConversationThread(
            thread_id="11111111-1111-4111-8111-111111111111",
            tenant_id="company_001",
            user_id="U1001",
            checkpoint_key=("22222222-2222-4222-8222-222222222222"),
        )
    )
    service = ConversationThreadService(repository)

    checkpoint_key = asyncio.run(
        service.resolve_checkpoint_key(
            thread_id="11111111-1111-4111-8111-111111111111",
            tenant_id="company_001",
            user_id="U1001",
        )
    )

    assert checkpoint_key == ("22222222-2222-4222-8222-222222222222")
    repository.find_owned.assert_awaited_once_with(
        thread_id="11111111-1111-4111-8111-111111111111",
        tenant_id="company_001",
        user_id="U1001",
    )


def test_invalid_thread_id_uses_generic_not_found() -> None:
    repository = Mock(spec=ConversationThreadRepository)
    service = ConversationThreadService(repository)

    with pytest.raises(ConversationThreadNotFoundError):
        asyncio.run(
            service.resolve_checkpoint_key(
                thread_id="not-a-uuid",
                tenant_id="company_001",
                user_id="U1001",
            )
        )

    repository.find_owned.assert_not_called()


def test_missing_or_foreign_thread_uses_generic_not_found() -> None:
    repository = Mock(spec=ConversationThreadRepository)
    repository.find_owned = AsyncMock(return_value=None)
    service = ConversationThreadService(repository)

    with pytest.raises(ConversationThreadNotFoundError):
        asyncio.run(
            service.resolve_checkpoint_key(
                thread_id=("11111111-1111-4111-8111-111111111111"),
                tenant_id="company_001",
                user_id="U2002",
            )
        )
