import asyncio
import logging
from collections.abc import AsyncIterator

from agent_service.api.schemas import (
    ApprovalRequiredResponse,
    ChatResponse,
    StreamDone,
    StreamError,
    StreamEventType,
    StreamMetadata,
    StreamToken,
)
from agent_service.api.sse import encode_sse
from agent_service.core.request_context import get_request_id
from agent_service.domain.agent import (
    AgentApprovalRequired,
    AgentStreamCompleted,
    AgentStreamEvent,
    AgentStreamToken,
)

logger = logging.getLogger(__name__)


async def encode_agent_event_stream(
    *,
    thread_id: str,
    events: AsyncIterator[AgentStreamEvent],
) -> AsyncIterator[str]:
    yield encode_sse(
        event=StreamEventType.METADATA,
        data=StreamMetadata(thread_id=thread_id),
    )

    try:
        async for event in events:
            if isinstance(event, AgentStreamToken):
                yield encode_sse(
                    event=StreamEventType.TOKEN,
                    data=StreamToken(content=event.content),
                )
                continue

            if not isinstance(event, AgentStreamCompleted):
                raise TypeError("Agent服务返回了未知流事件")

            result = event.result
            if isinstance(result, AgentApprovalRequired):
                yield encode_sse(
                    event=StreamEventType.APPROVAL_REQUIRED,
                    data=ApprovalRequiredResponse.from_result(
                        thread_id=thread_id,
                        result=result,
                    ),
                )
            else:
                yield encode_sse(
                    event=StreamEventType.RESULT,
                    data=ChatResponse.from_reply(
                        thread_id=thread_id,
                        reply=result,
                    ),
                )

            yield encode_sse(
                event=StreamEventType.DONE,
                data=StreamDone(),
            )
    except asyncio.CancelledError:
        logger.info(
            "agent_stream_disconnected request_id=%s",
            get_request_id() or "missing",
        )
        raise
    except Exception:
        logger.exception(
            "agent_stream_failed request_id=%s error_code=STREAM_FAILED",
            get_request_id() or "missing",
        )
        yield encode_sse(
            event=StreamEventType.ERROR,
            data=StreamError(
                code="STREAM_FAILED",
                message="回答生成失败，请稍后重试。",
                retryable=True,
            ),
        )
