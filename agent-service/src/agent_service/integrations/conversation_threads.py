from dataclasses import dataclass
from uuid import uuid4

from psycopg_pool import AsyncConnectionPool


@dataclass(frozen=True, slots=True)
class ConversationThread:
    thread_id: str
    tenant_id: str
    user_id: str
    checkpoint_key: str


class ConversationThreadRepository:
    def __init__(
        self,
        pool: AsyncConnectionPool,
    ) -> None:
        self._pool = pool

    async def setup(self) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_threads (
                    thread_id UUID PRIMARY KEY,
                    tenant_id VARCHAR(64) NOT NULL,
                    user_id VARCHAR(64) NOT NULL,
                    checkpoint_key UUID NOT NULL UNIQUE,
                    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT agent_threads_status_check
                        CHECK (status IN ('ACTIVE', 'CLOSED'))
                )
                """
            )
            await connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_agent_threads_owner
                ON agent_threads (tenant_id, user_id, thread_id)
                """
            )

    async def create(
        self,
        *,
        tenant_id: str,
        user_id: str,
    ) -> ConversationThread:
        thread = ConversationThread(
            thread_id=str(uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            checkpoint_key=str(uuid4()),
        )

        async with self._pool.connection() as connection:
            await connection.execute(
                """
                INSERT INTO agent_threads (
                    thread_id,
                    tenant_id,
                    user_id,
                    checkpoint_key
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    thread.thread_id,
                    thread.tenant_id,
                    thread.user_id,
                    thread.checkpoint_key,
                ),
            )

        return thread

    async def find_owned(
        self,
        *,
        thread_id: str,
        tenant_id: str,
        user_id: str,
    ) -> ConversationThread | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT
                    thread_id,
                    tenant_id,
                    user_id,
                    checkpoint_key
                FROM agent_threads
                WHERE thread_id = %s
                  AND tenant_id = %s
                  AND user_id = %s
                  AND status = 'ACTIVE'
                """,
                (thread_id, tenant_id, user_id),
            )
            row = await cursor.fetchone()

        if row is None:
            return None

        return ConversationThread(
            thread_id=str(row["thread_id"]),
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            checkpoint_key=str(row["checkpoint_key"]),
        )
