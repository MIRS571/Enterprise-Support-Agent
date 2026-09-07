import asyncio

import pytest

from agent_service.api.schemas import (
    StreamDone,
    StreamEventType,
    StreamMetadata,
    StreamToken,
)
from agent_service.api.sse import encode_sse
from agent_service.api.streaming import encode_agent_event_stream
from agent_service.domain.agent import AgentStreamToken


def test_encode_metadata_event() -> None:
    encoded = encode_sse(
        event=StreamEventType.METADATA,
        data=StreamMetadata(thread_id="thread_001"),
    )

    assert encoded == (
        'event: metadata\ndata: {"thread_id":"thread_001"}\n\n'
    )


def test_encode_token_keeps_unicode_and_escapes_newlines() -> None:
    encoded = encode_sse(
        event=StreamEventType.TOKEN,
        data=StreamToken(content="你好\n订单"),
    )

    assert encoded == (
        'event: token\ndata: {"content":"你好\\n订单"}\n\n'
    )


def test_encode_done_event() -> None:
    encoded = encode_sse(
        event=StreamEventType.DONE,
        data=StreamDone(),
    )

    assert encoded == (
        'event: done\ndata: {"status":"completed"}\n\n'
    )


def test_agent_event_stream_propagates_cancellation() -> None:
    source_closed = asyncio.Event()

    async def source():
        try:
            await asyncio.Future()
            yield AgentStreamToken(content="unreachable")
        finally:
            source_closed.set()

    async def scenario() -> None:
        stream = encode_agent_event_stream(
            thread_id="thread_001",
            events=source(),
        )
        metadata = await anext(stream)
        assert metadata.startswith("event: metadata")

        pending = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        pending.cancel()

        with pytest.raises(asyncio.CancelledError):
            await pending
        assert source_closed.is_set()

    asyncio.run(scenario())
