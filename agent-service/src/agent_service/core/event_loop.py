import asyncio


def selector_event_loop_factory() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop()
