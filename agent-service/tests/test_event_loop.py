import asyncio

from agent_service.core.event_loop import (
    selector_event_loop_factory,
)


def test_selector_event_loop_factory() -> None:
    event_loop = selector_event_loop_factory()

    try:
        assert isinstance(
            event_loop,
            asyncio.SelectorEventLoop,
        )
    finally:
        event_loop.close()
