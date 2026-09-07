from uuid import UUID

from agent_service.integrations.conversation_threads import (
    ConversationThreadRepository,
)


class ConversationThreadNotFoundError(Exception):
    pass


class ConversationPersistenceUnavailableError(Exception):
    pass


class ConversationThreadService:
    def __init__(
        self,
        repository: ConversationThreadRepository,
    ) -> None:
        self._repository = repository

    async def create_thread(
        self,
        *,
        tenant_id: str,
        user_id: str,
    ) -> str:
        thread = await self._repository.create(
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return thread.thread_id

    async def resolve_checkpoint_key(
        self,
        *,
        thread_id: str,
        tenant_id: str,
        user_id: str,
    ) -> str:
        try:
            normalized_thread_id = str(UUID(thread_id))
        except ValueError as error:
            raise ConversationThreadNotFoundError from error

        thread = await self._repository.find_owned(
            thread_id=normalized_thread_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if thread is None:
            raise ConversationThreadNotFoundError

        return thread.checkpoint_key
